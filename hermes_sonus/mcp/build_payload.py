#!/usr/bin/env python3
"""
build_payload.py — Convert this skill's field-labeled output into a sunoapi.org JSON payload.

Parses a text blob with sections like:
    STYLES: ...
    EXCLUDE_STYLES: ...
    LYRICS: ...
    TITLE: ...
    WEIRDNESS: 60%
    STYLE: 40%
    UNHINGED_SEED: [[[...]]]

…and emits a JSON request body for the sunoapi.org /api/v1/generate endpoint.

Also validates character limits against the chosen model and warns on overflows.

Usage:
    python build_payload.py --input prompt.txt --model V5 --callback https://your.app/webhook
    cat prompt.txt | python build_payload.py --model V5_5 --callback https://your.app/webhook
    python build_payload.py --input prompt.txt --model V5 --instrumental --no-vocals

Doesn't make HTTP requests — pure transformer. Pipe the output to curl/httpie if you want to fire it.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Optional


# Per-model character limits in custom mode
# (style, lyrics_prompt, title)
MODEL_LIMITS = {
    "V4":         {"style": 200,  "lyrics": 3000, "title": 80,  "nonCustomPrompt": 500},
    "V4_5":       {"style": 1000, "lyrics": 5000, "title": 100, "nonCustomPrompt": 500},
    "V4_5PLUS":   {"style": 1000, "lyrics": 5000, "title": 100, "nonCustomPrompt": 500},
    "V4_5ALL":    {"style": 1000, "lyrics": 5000, "title": 80,  "nonCustomPrompt": 500},
    "V5":         {"style": 1000, "lyrics": 5000, "title": 100, "nonCustomPrompt": 500},
    "V5_5":       {"style": 1000, "lyrics": 5000, "title": 100, "nonCustomPrompt": 500},
}

# Lyrics stability target — Suno's parser gets sloppy near the upper limit
LYRICS_STABILITY_TARGET = 4000

# Recognized field labels in the skill output. Case-insensitive, terminated by colon.
FIELD_PATTERN = re.compile(
    r"^(STYLES?|EXCLUDE_STYLES?|NEGATIVE_TAGS?|LYRICS|TITLE|WEIRDNESS|STYLE|UNHINGED_?SEED|VOCAL_GENDER|MODEL|PERSONA_?ID|PERSONA_?MODEL)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParsedFields:
    styles: Optional[str] = None
    exclude_styles: Optional[str] = None
    lyrics: Optional[str] = None
    title: Optional[str] = None
    weirdness_pct: Optional[float] = None
    style_pct: Optional[float] = None
    unhinged_seed: Optional[str] = None
    vocal_gender: Optional[str] = None
    persona_id: Optional[str] = None
    persona_model: Optional[str] = None
    model_hint: Optional[str] = None


def parse_input(text: str) -> ParsedFields:
    """
    Walk through the input, splitting on field labels.
    Each field's value is everything from its label until the next label or EOF.
    """
    fields = ParsedFields()
    # Find all field-label positions
    matches = list(FIELD_PATTERN.finditer(text))
    if not matches:
        # No labeled fields. Treat the whole input as lyrics if it looks lyrical, otherwise as styles.
        fields.lyrics = text.strip()
        return fields

    for i, m in enumerate(matches):
        label = m.group(1).upper().replace("_", "")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()

        if label in ("STYLES", "STYLE") and i + 1 < len(matches):
            # Disambiguate: "STYLE: 40%" is the slider; "STYLES: ..." is the descriptive field.
            # Heuristic: if value is a short percentage, it's the slider.
            if re.match(r"^\d{1,3}\s*%?\s*$", value):
                fields.style_pct = _parse_pct(value)
                continue

        if label == "STYLES":
            fields.styles = value
        elif label == "STYLE":
            # The plural form is preferred for the descriptive field; if we got "STYLE:" with a non-percentage,
            # assume it's the descriptive field.
            if re.match(r"^\d{1,3}\s*%?\s*$", value):
                fields.style_pct = _parse_pct(value)
            else:
                fields.styles = value
        elif label in ("EXCLUDESTYLES", "NEGATIVETAGS"):
            fields.exclude_styles = value
        elif label == "LYRICS":
            fields.lyrics = value
        elif label == "TITLE":
            fields.title = value
        elif label == "WEIRDNESS":
            fields.weirdness_pct = _parse_pct(value)
        elif label == "UNHINGEDSEED":
            fields.unhinged_seed = value
        elif label == "VOCALGENDER":
            v = value.strip().lower()
            if v in ("m", "f", "male", "female"):
                fields.vocal_gender = v[0]
        elif label == "PERSONAID":
            fields.persona_id = value
        elif label == "PERSONAMODEL":
            fields.persona_model = value.strip().lower()
        elif label == "MODEL":
            fields.model_hint = value.strip().upper()

    return fields


def _parse_pct(value: str) -> Optional[float]:
    """Parse '60', '60%', '0.6' into a float in [0, 1]."""
    v = value.strip().rstrip("%").strip()
    try:
        n = float(v)
        if n > 1.0:
            return n / 100.0
        return n
    except ValueError:
        return None


def merge_unhinged_seed_into_lyrics(fields: ParsedFields) -> None:
    """
    The skill convention is to embed the unhinged seed inside the lyrics or styles.
    Append to lyrics if present, otherwise to styles.
    """
    if not fields.unhinged_seed:
        return
    seed = fields.unhinged_seed.strip()
    if fields.lyrics:
        fields.lyrics = fields.lyrics.rstrip() + "\n\n" + seed
    elif fields.styles:
        fields.styles = fields.styles.rstrip() + " " + seed
    else:
        fields.lyrics = seed


def validate_limits(fields: ParsedFields, model: str, instrumental: bool, custom_mode: bool) -> list:
    """Return a list of warnings about character limit issues."""
    warnings = []
    if model not in MODEL_LIMITS:
        warnings.append(f"unknown model '{model}'; defaulting limits to V5 (1000/5000/100)")
        limits = MODEL_LIMITS["V5"]
    else:
        limits = MODEL_LIMITS[model]

    if not custom_mode:
        # Non-custom mode uses only `prompt` with a 500-char limit.
        prompt = fields.lyrics or fields.styles or ""
        if len(prompt) > limits["nonCustomPrompt"]:
            warnings.append(
                f"non-custom prompt is {len(prompt)} chars but limit for {model} is {limits['nonCustomPrompt']}; "
                "will be silently truncated by Suno"
            )
        return warnings

    # Custom mode
    if fields.styles:
        if len(fields.styles) > limits["style"]:
            warnings.append(
                f"STYLES is {len(fields.styles)} chars but limit for {model} is {limits['style']}; "
                "will be silently truncated"
            )

    if fields.lyrics:
        if len(fields.lyrics) > limits["lyrics"]:
            warnings.append(
                f"LYRICS is {len(fields.lyrics)} chars but limit for {model} is {limits['lyrics']}; "
                "will be silently truncated"
            )
        elif len(fields.lyrics) > LYRICS_STABILITY_TARGET:
            warnings.append(
                f"LYRICS is {len(fields.lyrics)} chars; under the {limits['lyrics']} limit but over the "
                f"~{LYRICS_STABILITY_TARGET} stability target. Suno's parser may get sloppy."
            )

    if fields.title and len(fields.title) > limits["title"]:
        warnings.append(
            f"TITLE is {len(fields.title)} chars but limit for {model} is {limits['title']}; "
            "will be silently truncated"
        )

    # Required field checks
    if not fields.styles:
        warnings.append("STYLES is empty — required in custom mode")
    if not instrumental and not fields.lyrics:
        warnings.append("LYRICS is empty and instrumental=False — vocal track needs lyrics")

    # Persona model + version compatibility
    if fields.persona_model == "voice_persona" and model not in ("V5", "V5_5"):
        warnings.append(
            f"personaModel=voice_persona requires V5 or V5_5; current model is {model}. "
            "Either upgrade the model or use style_persona."
        )

    return warnings


def build_payload(
    fields: ParsedFields,
    model: str,
    callback_url: str,
    instrumental: bool,
    custom_mode: bool,
) -> dict:
    """Build the sunoapi.org request body."""
    body = {
        "customMode": custom_mode,
        "instrumental": instrumental,
        "model": model,
        "callBackUrl": callback_url,
    }

    if custom_mode:
        if fields.styles:
            body["style"] = fields.styles
        if fields.title is not None:
            body["title"] = fields.title
        else:
            body["title"] = ""
        if fields.lyrics and not instrumental:
            body["prompt"] = fields.lyrics
        elif fields.lyrics and instrumental:
            # Even when instrumental, include the symbol-lyrics as the prompt — Suno reads them
            # as instrumental-shaping content. This deviates from the API doc's "only style+title
            # required when instrumental:true" but in practice works and is the skill's design.
            body["prompt"] = fields.lyrics
        if fields.exclude_styles:
            body["negativeTags"] = fields.exclude_styles
    else:
        # Non-custom: only prompt
        body["prompt"] = (fields.lyrics or fields.styles or "").strip()

    # Sliders → weights
    if fields.weirdness_pct is not None:
        body["weirdnessConstraint"] = round(fields.weirdness_pct, 2)
    if fields.style_pct is not None:
        body["styleWeight"] = round(fields.style_pct, 2)

    # Optional fields
    if fields.vocal_gender and not instrumental:
        body["vocalGender"] = fields.vocal_gender
    if fields.persona_id:
        body["personaId"] = fields.persona_id
        if fields.persona_model:
            body["personaModel"] = fields.persona_model

    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", "-i", help="Path to input file (stdin if omitted)")
    parser.add_argument("--model", "-m", default="V5", help="Suno model: V4 / V4_5 / V4_5PLUS / V4_5ALL / V5 / V5_5")
    parser.add_argument("--callback", "-c", required=True, help="Callback URL for async completion")
    parser.add_argument("--instrumental", action="store_true", help="Force instrumental=true")
    parser.add_argument("--no-instrumental", action="store_true", help="Force instrumental=false")
    parser.add_argument("--non-custom", action="store_true", help="Use non-custom mode (auto-lyrics from short description)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    # Read input
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    fields = parse_input(text)

    # Decide instrumental flag
    if args.instrumental:
        instrumental = True
    elif args.no_instrumental:
        instrumental = False
    else:
        # Heuristic: if lyrics are mostly non-alphabetic (>60% non-word chars), assume instrumental
        if fields.lyrics:
            word_chars = sum(1 for c in fields.lyrics if c.isalpha() or c.isspace())
            instrumental = (word_chars / max(len(fields.lyrics), 1)) < 0.4
        else:
            instrumental = True

    # Use the model hint from input if present and command-line is the default
    model = args.model
    if fields.model_hint and args.model == "V5":
        model = fields.model_hint

    custom_mode = not args.non_custom

    # Merge unhinged seed into lyrics
    merge_unhinged_seed_into_lyrics(fields)

    # Validate
    warnings = validate_limits(fields, model, instrumental, custom_mode)

    # Build payload
    payload = build_payload(fields, model, args.callback, instrumental, custom_mode)

    # Emit
    if warnings:
        print("WARNINGS:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        print("", file=sys.stderr)

    if args.pretty:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
