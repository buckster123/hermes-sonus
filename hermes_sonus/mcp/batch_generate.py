#!/usr/bin/env python3
"""
batch_generate.py — Generate multiple coherent Suno prompts from an album/EP manifest.

Takes a manifest file (YAML or JSON) describing a multi-track project and emits N
validated sunoapi.org payloads — one per track. Optionally fires the requests at the
API with rate limiting and stores the taskIds for downstream polling.

Two manifest modes:

1. **Explicit mode** — each track has its own complete field set (STYLES, LYRICS, etc.).
   This is the simple case: just a list of full prompts in structured form.

2. **DNA mode** — the manifest defines an "album_dna" (shared style fragments) and a
   list of "tracks" where each track is a small variation delta. The script merges
   each track's delta with the shared DNA to produce N coherent-but-distinct prompts.

Usage:
    # Just build payloads, emit as JSON array to stdout
    python batch_generate.py --input album.yaml --model V5

    # Fire requests with rate limiting (max 20 req/10s per Suno's ceiling)
    python batch_generate.py --input album.yaml --model V5 --fire \\
        --api-key $SUNO_API_KEY --callback https://your.app/cb

    # Save built payloads to per-track files instead of stdout JSON array
    python batch_generate.py --input album.yaml --output-dir ./payloads/

Manifest formats: YAML and JSON both accepted (detected by file extension or content).
See examples in references/examples.md for the manifest schema.

This script imports build_payload.py from the same scripts/ dir, so run it from the
skill's scripts/ directory or have the directory on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Try YAML; degrade gracefully if not available
try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

# Import field-parsing logic from the local package
try:
    from .build_payload import (
        ParsedFields,
        validate_limits,
        build_payload,
        merge_unhinged_seed_into_lyrics,
        MODEL_LIMITS,
    )
except ImportError:
    # Fallback for direct execution without package context
    from build_payload import (
        ParsedFields,
        validate_limits,
        build_payload,
        merge_unhinged_seed_into_lyrics,
        MODEL_LIMITS,
    )


# Suno's rate limit ceiling per sunoapi.org docs: 20 requests per 10 seconds
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW = 10.0
# Be conservative — leave headroom
SAFE_INTERVAL = RATE_LIMIT_WINDOW / RATE_LIMIT_REQUESTS * 1.5  # 0.75s between requests


# --- Manifest loading ---


def load_manifest(path: Path) -> dict:
    """Load YAML or JSON manifest. Auto-detect by extension and content."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    # JSON first if extension suggests so or content starts with `{` or `[`
    stripped = text.lstrip()
    if suffix in {".json"} or (suffix not in {".yaml", ".yml"} and stripped.startswith(("{", "["))):
        return json.loads(text)

    # Try YAML
    if HAVE_YAML:
        return yaml.safe_load(text)

    # Fallback: try JSON anyway in case extension is misleading
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"ERROR: manifest is not JSON, and PyYAML is not installed for YAML support.\n"
            f"  Install PyYAML: pip install pyyaml\n"
            f"  Or convert {path} to JSON. Parse error: {e}"
        )


# --- DNA merging ---


def merge_field(dna_value: str | None, track_value: str | None, separator: str = ", ") -> str | None:
    """
    Merge a DNA field value with a track-specific value.
    Track value APPENDS to DNA value (so DNA establishes baseline, track adds specificity).
    If track value starts with '!' it OVERRIDES (replaces DNA entirely).
    """
    if track_value is not None and track_value.startswith("!"):
        return track_value[1:].lstrip()
    if dna_value and track_value:
        return f"{dna_value}{separator}{track_value}"
    return track_value if track_value is not None else dna_value


def merge_lyrics(dna_lyrics: str | None, track_lyrics: str | None) -> str | None:
    """For lyrics, track value REPLACES DNA (since each track has unique lyrics by definition)."""
    if track_lyrics is not None:
        return track_lyrics
    return dna_lyrics


def resolve_track(album_dna: dict, track_def: dict, track_index: int) -> dict:
    """
    Merge album DNA + per-track delta into a single field dict.
    Returns a dict with the same keys ParsedFields uses.
    """
    resolved = {}

    # Standard fields: DNA + track delta merged
    for field, sep in [
        ("styles", ", "),
        ("exclude_styles", ", "),
    ]:
        resolved[field] = merge_field(album_dna.get(field), track_def.get(field), sep)

    # Lyrics: track overrides DNA
    resolved["lyrics"] = merge_lyrics(album_dna.get("lyrics"), track_def.get("lyrics"))

    # Single-value fields: track wins if present, otherwise DNA
    for field in ("title", "weirdness_pct", "style_pct", "unhinged_seed",
                  "vocal_gender", "persona_id", "persona_model", "model_hint"):
        resolved[field] = track_def.get(field, album_dna.get(field))

    # Auto-generate title if not specified and DNA has an album_title pattern
    if resolved.get("title") is None and album_dna.get("album_title"):
        resolved["title"] = f"{album_dna['album_title']} — Track {track_index + 1}"

    return resolved


# --- Manifest processing ---


def parse_manifest(manifest: dict) -> tuple[list[dict], dict]:
    """
    Parse a manifest into a list of resolved track field-dicts plus global settings.
    Returns: (resolved_tracks, global_settings)

    global_settings includes: model, callback_url, instrumental (per-track overridable)
    """
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a YAML/JSON object at the top level")

    # Pull global settings
    settings = {
        "model": manifest.get("model", "V5"),
        "callback_url": manifest.get("callback_url") or manifest.get("callBackUrl"),
        "instrumental": manifest.get("instrumental"),
        "custom_mode": manifest.get("custom_mode", True),
    }

    # Two manifest modes
    if "tracks" in manifest and "album_dna" in manifest:
        # DNA mode
        album_dna = manifest["album_dna"] or {}
        track_defs = manifest["tracks"]
        if not isinstance(track_defs, list):
            raise ValueError("'tracks' must be a list")
        resolved = [resolve_track(album_dna, t or {}, i) for i, t in enumerate(track_defs)]
    elif "tracks" in manifest:
        # Explicit mode — each track is a full field set
        track_defs = manifest["tracks"]
        if not isinstance(track_defs, list):
            raise ValueError("'tracks' must be a list")
        # Apply track-level fields directly
        resolved = []
        for i, t in enumerate(track_defs):
            t = t or {}
            resolved.append({
                "styles": t.get("styles"),
                "exclude_styles": t.get("exclude_styles"),
                "lyrics": t.get("lyrics"),
                "title": t.get("title"),
                "weirdness_pct": t.get("weirdness_pct"),
                "style_pct": t.get("style_pct"),
                "unhinged_seed": t.get("unhinged_seed"),
                "vocal_gender": t.get("vocal_gender"),
                "persona_id": t.get("persona_id"),
                "persona_model": t.get("persona_model"),
                "model_hint": t.get("model_hint"),
            })
    else:
        raise ValueError("Manifest must contain a 'tracks' key (and optionally 'album_dna')")

    return resolved, settings


def fields_dict_to_parsed(d: dict) -> ParsedFields:
    """Convert a resolved field dict into a ParsedFields dataclass."""
    fields = ParsedFields()
    fields.styles = d.get("styles")
    fields.exclude_styles = d.get("exclude_styles")
    fields.lyrics = d.get("lyrics")
    fields.title = d.get("title")
    fields.weirdness_pct = _normalize_pct(d.get("weirdness_pct"))
    fields.style_pct = _normalize_pct(d.get("style_pct"))
    fields.unhinged_seed = d.get("unhinged_seed")
    fields.vocal_gender = d.get("vocal_gender")
    fields.persona_id = d.get("persona_id")
    fields.persona_model = d.get("persona_model")
    fields.model_hint = d.get("model_hint")
    return fields


def _normalize_pct(v: Any) -> float | None:
    """Accept '60%', '60', 60, 0.6, etc. Return float in [0,1] or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) / 100.0 if v > 1.0 else float(v)
    if isinstance(v, str):
        s = v.strip().rstrip("%").strip()
        try:
            n = float(s)
            return n / 100.0 if n > 1.0 else n
        except ValueError:
            return None
    return None


def detect_instrumental(fields: ParsedFields, override: Any) -> bool:
    """Heuristic: lyrics with mostly non-alphabetic chars → instrumental."""
    if override is not None:
        return bool(override)
    if not fields.lyrics:
        return True
    word_chars = sum(1 for c in fields.lyrics if c.isalpha() or c.isspace())
    return (word_chars / max(len(fields.lyrics), 1)) < 0.4


# --- API firing with rate limiting ---


def fire_request(payload: dict, api_key: str, base_url: str = "https://api.sunoapi.org") -> dict:
    """POST a payload to the generate endpoint. Returns the parsed response."""
    url = f"{base_url}/api/v1/generate"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            return json.loads(body)
        except Exception:
            return {"code": e.code, "msg": f"HTTP {e.code}: {e.reason}", "_error": True}
    except urllib.error.URLError as e:
        return {"code": 0, "msg": f"Connection error: {e.reason}", "_error": True}


# --- Main ---


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True, help="Manifest file (YAML or JSON)")
    parser.add_argument("--model", "-m", default=None,
                        help="Override the model from the manifest (V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5)")
    parser.add_argument("--callback", "-c",
                        help="Override the callback URL from the manifest")
    parser.add_argument("--output-dir", "-o",
                        help="Write each payload to a separate file in this dir (default: stdout JSON array)")
    parser.add_argument("--fire", action="store_true",
                        help="Actually POST requests to the API (default: dry-run, payloads only)")
    parser.add_argument("--api-key", "-k", default=os.environ.get("SUNO_API_KEY"),
                        help="API key (or set SUNO_API_KEY env var). Required when --fire.")
    parser.add_argument("--base-url", default=os.environ.get("SUNO_BASE_URL", "https://api.sunoapi.org"),
                        help="API base URL (default: https://api.sunoapi.org)")
    parser.add_argument("--rate-interval", type=float, default=SAFE_INTERVAL,
                        help=f"Seconds between requests when firing (default: {SAFE_INTERVAL})")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="When firing, continue if a track fails (default: stop on first error)")
    args = parser.parse_args()

    # Load and parse manifest
    manifest_path = Path(args.input)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(2)
    manifest = load_manifest(manifest_path)
    resolved_tracks, settings = parse_manifest(manifest)

    # Apply CLI overrides
    if args.model:
        settings["model"] = args.model
    if args.callback:
        settings["callback_url"] = args.callback
    model = settings["model"]
    callback_url = settings["callback_url"]

    # Validate
    if not callback_url:
        print("ERROR: callback_url required (set in manifest or pass --callback)", file=sys.stderr)
        sys.exit(2)
    if args.fire and not args.api_key:
        print("ERROR: --fire requires --api-key or SUNO_API_KEY env var", file=sys.stderr)
        sys.exit(2)

    # Build payloads
    payloads = []
    all_warnings = []
    for i, track_dict in enumerate(resolved_tracks):
        fields = fields_dict_to_parsed(track_dict)
        merge_unhinged_seed_into_lyrics(fields)
        instrumental = detect_instrumental(fields, settings.get("instrumental"))

        warnings = validate_limits(fields, model, instrumental, settings["custom_mode"])
        if warnings:
            all_warnings.append((i, warnings))

        payload = build_payload(
            fields, model, callback_url, instrumental, settings["custom_mode"]
        )
        payloads.append(payload)

    # Report warnings to stderr
    if all_warnings:
        print(f"WARNINGS across {len(all_warnings)} track(s):", file=sys.stderr)
        for idx, warns in all_warnings:
            print(f"  Track {idx + 1}:", file=sys.stderr)
            for w in warns:
                print(f"    - {w}", file=sys.stderr)
        print("", file=sys.stderr)

    # Write payloads
    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(payloads, 1):
            title_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (p.get("title") or f"track_{i}"))[:40]
            path = out_dir / f"{i:02d}__{title_safe}.json"
            path.write_text(json.dumps(p, indent=2 if args.pretty else None, ensure_ascii=False))
            print(f"  wrote {path}", file=sys.stderr)
    elif not args.fire:
        # Default: emit JSON array to stdout
        out = json.dumps(payloads, indent=2 if args.pretty else None, ensure_ascii=False)
        print(out)

    # Fire if requested
    if args.fire:
        print(f"\nFiring {len(payloads)} request(s) with {args.rate_interval}s spacing...",
              file=sys.stderr)
        results = []
        for i, p in enumerate(payloads, 1):
            if i > 1:
                time.sleep(args.rate_interval)
            print(f"  [{i}/{len(payloads)}] firing track '{p.get('title') or '(untitled)'}'...",
                  file=sys.stderr)
            response = fire_request(p, args.api_key, args.base_url)
            task_id = None
            if response.get("code") == 200 and response.get("data"):
                task_id = response["data"].get("taskId") or response["data"].get("task_id")
            results.append({
                "track_index": i,
                "title": p.get("title"),
                "task_id": task_id,
                "response": response,
            })
            if task_id:
                print(f"      → taskId: {task_id}", file=sys.stderr)
            else:
                print(f"      → FAILED: {response.get('msg', 'unknown error')}", file=sys.stderr)
                if not args.continue_on_error:
                    print("      Stopping. Use --continue-on-error to fire remaining tracks anyway.",
                          file=sys.stderr)
                    print(json.dumps(results, indent=2 if args.pretty else None, ensure_ascii=False))
                    sys.exit(1)

        # Final results to stdout
        print(json.dumps(results, indent=2 if args.pretty else None, ensure_ascii=False))


if __name__ == "__main__":
    main()
