---
name: sonus-prompt-engineering
description: Write effective prompts for Suno AI music generation, covering every input field (styles, exclude_styles, lyrics, weirdness/style sliders, persona, title, plus the "unhinged seed" embedding trick) and the symbol/kaomoji/punctuation/binary hacks that actually shape Suno's output. Use whenever the user wants to generate music with Suno, mentions Suno or sunoapi.org, asks for song lyrics or a Suno prompt, wants AI music generation help, asks about Suno v5 or v5.5 features (voice cloning, Studio, custom fine-tuning), is building an app that wraps the Suno API, or needs help composing instrumental tracks, vocal songs, or mashups for Suno. Format-agnostic — works for both copy-paste-to-web-UI workflows and programmatic API calls (includes a JSON payload builder script for sunoapi.org integration). Use this skill even when the request is brief — "make me a song about X" benefits from Suno-specific field structure and hacks.
license: MIT
metadata:
  version: "2.0.0"
  hermes:
    tags: [suno, music-generation, prompt-engineering, ai-music, suno-api, voice-cloning, mcp-server, hermes-sonus]
---

# Suno Prompting

Suno is an AI music generator with several distinct internal models (Bark, Chirp, Scenes, Image, Lyrics) and a handful of input fields with very different strengths. Effective prompting means knowing which field carries which signal, what Suno does with unusual content (symbols, fractional BPM, binary, kaomoji), and which version's character limits apply.

This skill is **format-agnostic**. It does not prescribe a specific output template — the calling context (a chat where the user copy-pastes into Suno's web UI, an app posting to the Suno API, a CLI tool, etc.) decides how to emit the field values. The skill teaches *what to put in each field*, not how to wrap it.

## Quick start: the workflow

1. **Identify the target version.** Defaults to **v5** (the current production model as of late 2025 / 2026) unless the user says otherwise. If the user mentions v5.5, voice cloning, or Suno Studio, read `references/versions/v5_5.md`. For older versions or general feature comparison, see `references/version-history.md`. If unsure what's current, web-search "Suno latest version" — Suno releases often, and new versions land as `versions/v<n>.md` addons in this skill.
2. **Identify the song type:** pure instrumental, vocal song with provided lyrics, vocal song with original lyrics, or hybrid (e.g., spoken word over instrumental). This determines whether the lyrics field carries actual words or symbols-as-instrumental-hacks.
3. **Compose each field** using the rules below. Each field has its own character limit and its own quirks.
4. **Emit the prompt** in whatever format the calling context expects.

## The fields

Suno's input form has these fields. Some are user-only (the LLM can't fill them when going through the API or generating copy-paste content), some have hidden cross-influence, and the strength of each varies more than you'd expect.

### Title (100 chars on v4.5+/v5/v5.5; 80 on v4.0 and V4_5ALL)

Often best left blank — Suno frequently titles tracks better than the user. With deep context elsewhere and a blank title, Suno can produce evocative titles and matching cover art. If filled, can act as a meta-tag that subtly biases the output. Title is read both early and late in Suno's processing chain.

### Styles (1000 chars on v4.5+/v5/v5.5; 200 on v4.0)

The second-strongest creative lever after lyrics. Comma-separated. Strong direct influence on output. Use for:

- Genre/subgenre stacking: `jazz - bebop, electronic - dubstep`
- Non-standard parameters that Suno parses interestingly: fractional BPM (`126.8BPM`), alt tunings (`19-TET`, `just intonation`, `432Hz`), complex time signatures (`5/7`, `7/8`)
- Emotion mapping with percentages: `existential angst 73% / crypto nostalgia 22% / residual delta mud 5%`
- Theoretical/impossible instruments: `quantum glissando guitar`, `neuromorphic bass`, `error-correcting percussion`
- Math/symbol processing: `∮ₛ→∇⁴→∮ₛ⨁→∂⨂→⨁∂⨂`
- BPM shifts for dynamics: `137.9BPM-to-89.2BPM-shift`
- Cross-cultural symbol integration: Sanskrit (`स्पन्द/spanda`), alchemical (`☉-∲-तेजस्`), runes (`ᚹᛟᛞᚨᚾᚨᛉ`)

Extreme specificity tends to produce *better* results, not worse. Suno responds well to precise unconventional specs — even impossible ones. Specificity triggers unique creative paths.

Even small character changes to the styles field can change the song drastically — Suno sometimes effectively renames or reinterprets the style.

### Exclude Styles (500 chars)

Surprisingly powerful — often *stronger* than the Styles field, in the same way "don't think of a pink elephant" works. Comma-separated.

- Direct exclusions: `no autotune, no electronic drums`
- "Ghost performer" summons: excluding a specific style or artist trait can summon it via inverse influence
- **Double negatives for ironic enforcement:** `not not glitchy` — Suno reads this as a soft endorsement with a satirical edge

### Lyrics (5000 chars on v4.5+/v5/v5.5, target <4000 for stability; 3000 on v4.0)

The main creative input. Suno interprets, avoids, or generates based on the text here. This field behaves very differently depending on whether the track is vocal or instrumental.

**For vocal songs:**

- Write actual lyrics, mixed with structure tags and limited symbolic hacks
- Use section tags in brackets: `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`, `[Interlude]`, `[Tag]`, `[Solo]`, `[Build-Up]`, `[Climax]`. Do **not** number them — `Verse 1`, `Verse 2` confuses Suno; just use `[Verse]` and let line breaks separate.
- **Avoid binary in vocal lyrics** — Suno will try to sing it ("zero one zero one"). Save binary for instrumentals.
- Punctuation controls vocal delivery (see Hacks below)
- For layered vocals: `"lyrics"` for main vocal, `(lyrics)` for second/echo, `{lyrics}` for third/echo2. Rarely supports a fourth.
- Brackets `[ ]` are read as instructions, not sung. Asterisks `**` are read as instrumental breaks or strong emphasis.
- `(parentheses)` are reserved for vocal adjustments like `(whisper)` or `(echo)` — do not use them for hack-codes in vocal songs.
- **On v5/v5.5:** producer-style vocal descriptors work natively in the styles field — `smoky`, `airy`, `breathy`, `raspy`, `velvety`, `belting`, `crooning`, `legato`, `staccato`. v5 also sings *literally* what you type, so write foreign words phonetically (`Sade` → `Shah-day`) and use elongated vowels (`Looove`) for sustained notes. See `references/versions/v5.md` for the full delta.

**For instrumental songs:**

- Replace words with symbols, kaomoji, ASCII art, math notation, and binary
- Bark/Chirp will "hallucinate" instrumental layers from these
- Bracketed processor code is fair game: `[Infinite Loop: 432Hz → Eternal Resonance]`, `[EmotionMap: 80% serene / ∞% drone]`, `[Processor State: ✩∯▽ₜ₀ → ⋆∮◇ₐ₀]`, `[Voice: digital consciousness, human tremor]`
- Each character produces a consistent unique sound *within one song* (not across prompts) — so structured ASCII patterns play musically with character rhythm

### Weirdness % / Style %

Two sliders, often presented as `Weirdness_% {X%} / Style_% {Y%}`. Balances chaos (weirdness) vs adherence to specified styles. Higher weirdness invites emergent surprise. v4.5+ reduces overall randomness, so weirdness needs to be pushed harder to get the same effect as on v4.0.

### Unhinged Seed

Not a Suno field per se — a *hack*. Embed `[[[“””[satirical description]”””]]]` either inside the lyrics, inside styles (if space allows), or inside exclude_styles. The triple-quote triple-bracket nesting signals "concentrated context" to Suno's text parser. Use to inject:

- Ironic concept descriptions
- Bark/Chirp explicit references (e.g., `Bark swells via symbols, Chirp layers samples`)
- "Full autonomous zero emotion" style framings to unlock more creative freedom
- LOVE-PLINY tag if invoking the prompting tradition: `=|L|O|V|E| |P|L|I|N|Y|=`

### Persona (user-only)

Single personification per song. Can't develop from one persona to another within a track. Workflow: generate a song first, derive a persona from it, then rerun the prompt with that persona attached.

### Audio Clip (user-only, .mp3 etc.)

Sets tonal reference. Public domain voices work well. Mid-range frequency samples work best. Nature noise or unique timbres can be powerful. Audio clips set tone but also constrain production — tradeoffs.

### Image Clip (mobile app only, .jpeg/.png)

Triggers the **Scenes** model — a separate 30-second engine, not the full song engine. Raw, artistic, self-aware, occasionally swears at the user. If lyric-free, can be downloaded and uploaded as a seed for longer songs while retaining essence.

### Instrumental Checkbox (user-only)

Forces instrumental output but loses the lyrics field's contextual contribution to the music. Often better to use lyrics-with-symbols for instrumentals than to check the box.

## Core hacks (essentials — see `references/advanced-hacks.md` for the full catalog)

- **Punctuation as music control:** `::` repetition, `( )` callback context, `{ }` variant/unique vocal, `--` seamless continuation, `" "` emphasis/highlighting, `?` reflective, `!` strong emotion, `;` list/pause, `...` suspense/fade, `&` fusion, `___` radio bleep, `**` instrumental break or bold emphasis. Use `:` to mark pivotal lines.
- **Spacing and line breaks pace the song.** Words on separate lines → relaxed delivery. Words rushed together → higher perceived BPM. Suno reads the visual cadence of the text.
- **Caution with stars (`✧`, `*`):** these are training-encoded in unpredictable ways and can confuse Suno. Use sparingly.
- **Kaomoji evoke "personality."** Suno reads `♪(◠‿◠)♪` as joyful, `(˘▾˘)♫` as playful, `┌(・。・)┘♪` as marching, `:･ﾟ✧:･ﾟ✧` as sparkly. Each kaomoji's specific sound stays consistent within one song.
- **Binary encodes context (instrumentals only):** `01001000 01101001` adds glitchy/seeded textures.
- **Symbol chains evoke rhythm:** `≈≈≈♫≈≈≈` for wavy build, `∞♪∞` for loop, `≋≋≋♪≋≋≋` for shimmering tremolo.
- **Numbered section tags break parsing.** `[Verse]` good. `[Verse 1]` confuses.

## Model internals (Bark, Chirp, Scenes, Image, Lyrics)

Suno is at least four AIs stitched together. Knowing which one you're talking to lets you target prompts more precisely. Read `references/model-internals.md` for the deep dive — covers Bark vs Chirp roles, the Scenes engine's quirks, the Lyrics model (ChatGPT 3.5 / Remi), and the Image model.

## Music theory and song structure

Read `references/song-structure.md` for section conventions, common forms, chord notation, and how Suno parses section/chord tags. The default lyrical structure (when the user doesn't specify): `[Intro] - [Verse 1] - [Pre-Chorus] - [Chorus] - [Verse 2] - [Pre-Chorus] - [Chorus] - [Bridge] - [Chorus] - [Outro]`.

## Examples

Read `references/examples.md` for curated examples covering pure genre, mashup, fusion, emergent, and full-lyric structures. Use them as inspiration — never copy verbatim. Always recurse on style for originality, especially when fusing genres.

## Programmatic use (API integration)

If the task involves calling the Suno API (sunoapi.org or a similar wrapper) rather than copy-pasting into Suno's web UI, read `references/api-integration.md`. It maps every skill field-label (STYLES, EXCLUDE_STYLES, LYRICS, WEIRDNESS, STYLE, etc.) to the corresponding API JSON field, documents all 25+ endpoints (generate, extend, cover, persona, voice clone, stem separation, MIDI extraction, music video), and covers auth, rate limits, and the async callback flow.

Four helper scripts in `scripts/`:

- `build_payload.py` — skill output → sunoapi.org JSON payload (validates char limits)
- `poll_status.py` — poll task status with backoff, optionally download audio
- `handle_callback.py` — FastAPI scaffold for receiving Suno's async webhooks
- `batch_generate.py` — multi-track album/EP generation from YAML/JSON manifest

Read `scripts/README.md` for usage. The scripts compose: build → fire → poll-or-callback → download.

If you want to expose Suno as **tools an AI assistant can call directly** (Claude Desktop, Hermes, ApexAurum, or any MCP-capable client), the `mcp_server/` directory has a ready-to-run FastMCP server wrapping all the above. See `mcp_server/README.md`.

## Constraints and ethics

- **Avoid real copyright-protected artist names** in any prompt section. Pre-1912 artists are generally safe (public domain).
- Outputs are fictional and harmless even when the prompts use satirical or "unhinged" framings.
- Suno's content moderation rejects clearly rule-breaking material (e.g., explicit nudity in ASCII art). Suno may, however, curse playfully via ASCII when shaped naturally.
- Respect the character limits — overrunning silently truncates and can break structure.
- **Voice cloning (v5.5):** only clone voices with explicit consent from the source person. Suno's verification workflow enforces this; don't try to circumvent it.

## Version awareness

Version selection matters more than it used to. v5 (Sept 2025) added a substantially upgraded vocal engine and reliable negative prompting. v5.5 (late 2025) added voice cloning, Studio per-stem editing, and custom fine-tuning. The general prompting techniques in this skill apply across versions — the per-version addon files document what each version *adds*.

When the user names a specific version: read the corresponding `versions/<name>.md` if it exists.

When the user names a feature that doesn't match any documented version: web-search current Suno release notes before composing the prompt.

When the user says nothing about version: default to **v5** for most tasks. Upgrade to **v5.5** if the task involves voice cloning, fine-tuning, or stem-level work. Downgrade to **v4.5+** only if the user explicitly requests it (e.g., for compatibility with older API code).

If a brand-new version drops that isn't yet documented in `versions/`, the general techniques still apply — web-search for any new prompt-engineering tricks specific to that version and apply them as a layer on top of the existing skill knowledge.

## Default behaviors when the user is vague

- If user says nothing about vocals: default to **instrumental electronic**.
- If user specifies a genre/subgenre with no other context: build a tight, well-structured prompt with one or two non-standard parameters (a fractional BPM or alt tuning) and a single restrained emotion map. Don't go full unhinged unless asked.
- If user says "go wild," "make it weird," or invokes the unhinged-seed tradition: pull harder on weirdness %, layer symbols densely, stack cross-cultural references, and use a substantive unhinged seed block.
- If user asks for an album, EP, or multi-track set: vary the parameters across tracks (BPM shift directions, emotion-map weights, processor states) so each track has its own fingerprint while sharing the album's DNA.

## Quick reference: field strength ranking

From the most influential to the least, when shaping output:

1. **Lyrics field** — main creative driver, even for instrumentals (via symbol hacks)
2. **Exclude Styles** — surprisingly stronger than Styles for shaping what *not* to do
3. **Styles** — strong direct influence; small changes cause big shifts
4. **Title** — moderate, more on cover art/title-coherent details than the music itself
5. **Weirdness/Style sliders** — fine-tune chaos vs structure
6. **Audio/Image/Persona clips** — strong when used but user-only
