---
name: sonus-prompt-engineering
description: Master Suno AI music generation AND closed-loop EEG resonance feedback in the hermes-sonus plugin. Deep knowledge of Bark/Chirp processor manipulation, non-standard parameters, symbol/kaomoji hacks, genre fusion, song structure, AND how to read the human listener's felt emotional response (valence/arousal/attention/engagement/chills) to refine prompts iteratively. Pairs with all 20 hermes-sonus tools.
version: 2.0.0
author: buckster123
license: MIT
metadata:
  hermes:
    tags: [music, suno, prompt-engineering, eeg, bci, openbci, resonance, affective-computing, creative, audio, composition, closed-loop]
    related_skills: []
---

# Sonus Prompt Engineering & Resonance Feedback

Expert system for the **hermes-sonus** plugin — Suno AI music generation paired with OpenBCI EEG felt-experience sensing. Load this skill any time you reach for a `music_*`, `midi_*`, or `eeg_*` tool.

Sonus is the first Hermes plugin where the agent can both **make music** and **feel the human's response to it**. This skill teaches you to use both halves together — generate, measure, adapt.

## When to Use

- User asks you to generate music, create a track, or make a song
- User wants a specific genre, mood, or style combination
- User asks the agent to "listen with them" or capture their emotional response
- Closed-loop composition — generate → listen via EEG → adapt next prompt from felt experience
- Any time you call a tool starting with `music_`, `midi_`, or `eeg_`

## Plugin Tool Inventory (20 tools)

**Music generation (12 tools)** — Suno-backed
- `music_generate` — primary generation (prompt + style + title + model)
- `music_compose` — MIDI-influenced generation (audio_influence 0.0–1.0)
- `music_status` — poll an in-flight generation task
- `music_result` — fetch finished tracks (mp3 + metadata)
- `music_list` — list all generated tracks
- `music_search` — search library by title/style/lyrics
- `music_library` — full library snapshot
- `music_favorite` — toggle favorite flag
- `music_play` / `music_stop` — local audio playback
- `music_delete` — remove from library
- `midi_create` — build a MIDI file from notes (input to `music_compose`)

**EEG / Resonance (8 tools)** — OpenBCI-backed (works without hardware via mock)
- `eeg_connect` — connect to Cyton / Ganglion / synthetic / **mock** board
- `eeg_disconnect` — release the board
- `eeg_calibrate_baseline` — record listener's resting state
- `eeg_stream_start` — begin recording a listening session (link `track_id`)
- `eeg_stream_stop` — finalize session, generate AI-readable felt experience
- `eeg_realtime_emotion` — sample current valence/arousal/attention/engagement/chills (during stream)
- `eeg_experience_get` — retrieve a finished session's felt experience
- `eeg_list_sessions` — list recorded sessions

## Quick Reference — Suno Prompts

Suno prompts have 4 components. Each maps to a `music_generate` parameter:

| Component | Parameter | Limit (v4.5+/v5) | Purpose |
|-----------|-----------|-------------------|---------|
| **Styles** | `style` | 1000 chars | Genre tags, non-standard params, fractional BPM, tunings |
| **Exclude Styles** | (in prompt) | 500 chars | Exclusions, ironic enforcement via double negatives |
| **Lyrics/Symbols** | `prompt` | 5000 chars (target <4000) | Section tags, symbols, kaomoji, processor code, or actual lyrics |
| **Title** | `title` | 100 chars | Often leave blank — Suno sometimes titles better |

## Core Workflow — Generation Only

1. **Analyze intent** — Deconstruct the request into mood, genre, structure, instrumentation
2. **Choose genre foundation** — Load `references/genres.json` for the 1200-entry database if you need fusion inspiration
3. **Build the prompt** — Use `templates/prompt-format.md`
4. **Apply hacks** — Load `references/suno-deep.md` for Bark/Chirp manipulation, symbol tricks, non-standard parameters
5. **Structure the song** — Load `references/music-theory.md` for progressions, section tags, form
6. **Generate** — Call `music_generate(prompt=..., style=..., title=..., model="V5")`
7. **Poll** — `music_status(task_id=...)` until complete
8. **Fetch** — `music_result(task_id=...)` returns mp3 paths

## Core Workflow — Closed-Loop (Suno + Resonance)

This is the unique Sonus capability. Use it when the user wants iterative composition that learns from their felt response.

```
1. eeg_connect(serial_port="", board_type="mock")  # or "cyton" if hardware
2. eeg_calibrate_baseline(listener_name="Andre")   # 30s baseline (optional but recommended)
3. music_generate(prompt=..., style=..., model="V5")
4. music_status(task_id=...)  # poll until done
5. result = music_result(task_id=...)              # get track_id + mp3 path
6. eeg_stream_start(session_name="...", track_id=result.tracks[0].id, track_title=...)
7. music_play(track_id=result.tracks[0].id)        # play the track
8. # During playback, optionally sample: eeg_realtime_emotion()
9. # When track ends:
10. music_stop()
11. experience = eeg_stream_stop(generate_experience=True)
12. # READ the experience.narrative + emotional arc + chills moments
13. # Adapt next prompt based on what resonated:
#    - High valence + high engagement on the bridge? Lean into that texture next time
#    - Chills at 1:42? Note what was happening in the prompt at that moment
#    - Low arousal during drop you wanted to be intense? Increase BPM / add sub-bass
14. music_generate(...)  # next iteration, informed by felt response
```

Load `references/resonance-feedback.md` for the full feedback-interpretation guide — what each metric means, how to read the chills cluster, how to translate emotional arc back into prompt adjustments.

## Essential Prompt Principles (Suno)

### Instrumental Tracks (No Vocals)
- Set `is_instrumental=True`
- Use symbols, kaomoji, ASCII patterns, and [bracket tags] in the prompt field
- These manipulate Bark (primary stem) and Chirp (backup stem) into layered instrumentals
- Binary sequences (01001000) encode glitch/texture effects
- Each character maps to a consistent sound within a song

### Vocal Tracks
- Set `is_instrumental=False`
- Write lyrics with section tags: [Verse], [Chorus], [Bridge], etc.
- Combine lyrics with symbols for instrumental layering
- Avoid binary in vocal tracks (causes mispronunciation)
- Use (parentheses) only for vocal adjustments: (whisper), (echo)
- NOT for processor code — use [brackets] for that

### Style Field Power
- Comma-separated genres and parameters
- Even single-character changes drastically alter output
- Non-standard params: fractional BPM (126.8), alt tunings (19-TET), time sigs (5/7)
- Emotion mapping: "existential angst 73% / nostalgic warmth 27%"
- Symbol processing: ∮ₛ→∇⁴ (interpreted as abstract texture seeds)

### Exclude Styles — The Secret Weapon
- More influential than Styles (like "don't think of a pink elephant")
- Double negatives for ironic enforcement: "not not dubstep" = subtle dubstep influence
- Use to summon ghost genre influences

### Weirdness/Style Balance
- Format: `Weirdness_% {X%} / Style_% {Y%}` in the prompt
- High weirdness = experimental, emergent, surprising
- High style = structured, genre-faithful, predictable
- Sweet spot for interesting results: weirdness 30-50%

### Key Hacks
- `::` — repetition/emphasis
- `( )` — callback/repeat theme
- `{ }` — unique vocal variant
- `...` — suspense/fade
- Line breaks control pacing — more breaks = slower tempo feel
- Fewer breaks = rushed, higher energy

## Loading Reference Files

When you need deeper knowledge, load on demand:

```
skill_view("sonus-prompt-engineering", file_path="references/suno-deep.md")
```
→ Bark/Chirp internals, symbol mapping, kaomoji tricks, non-standard params, model details

```
skill_view("sonus-prompt-engineering", file_path="references/music-theory.md")
```
→ Song structures, chord progressions, section tags, genre-specific forms

```
skill_view("sonus-prompt-engineering", file_path="references/genres.json")
```
→ Full 1200-entry genre/subgenre database for fusion inspiration

```
skill_view("sonus-prompt-engineering", file_path="references/resonance-feedback.md")
```
→ EEG feedback loop — interpreting valence/arousal/attention/engagement/chills, translating felt response back into prompt adjustments

```
skill_view("sonus-prompt-engineering", file_path="templates/prompt-format.md")
```
→ Copy-paste prompt template with all components

## Pitfalls

### Suno generation
1. **Don't exceed character limits** — Styles: 1000 chars, Prompt/lyrics: target <4000 for stability
2. **Don't number sections** — [Verse 1] confuses Suno, use [Verse] then [Verse] again
3. **Don't use parentheses for processor code** — Only [brackets]. Parens are for vocal effects.
4. **Don't put binary in vocal tracks** — Bark tries to "sing" binary as words
5. **Don't over-specify** — Leave room for Suno's emergent creativity. The best prompts are specific enough to guide but open enough for surprise.
6. **Model versions matter** — Default to V5. Older models (V3.5/V4) have lower char limits (200 styles, 3000 lyrics).

### EEG / resonance loop
7. **Always `eeg_connect` before `eeg_stream_start`** — start without a connected board returns an error.
8. **Use `board_type="mock"` when no hardware is attached** — works without brainflow installed; produces realistic synthesized emotional curves so the loop is testable.
9. **Link `track_id` when starting a stream** — without it, the experience can't be tied back to the music in the library. Always pass the `track_id` returned by `music_result`.
10. **Don't sample `eeg_realtime_emotion` faster than ~2Hz** — that's the recording rate; faster polling returns duplicate samples.
11. **Stop the stream before disconnecting** — `eeg_disconnect` while streaming will cut the session record. Always: `music_stop` → `eeg_stream_stop` → (optional) `eeg_disconnect`.
12. **Read the narrative, not just the numbers** — `eeg_experience_get(detail_level="narrative")` returns the AI-consumable felt-experience string. THAT is what should inform your next prompt, more than raw averages.
13. **Chills are signal, not noise** — clusters of chills moments mark sections that resonated hardest. Note their timestamps and what was happening in the prompt at that point.
14. **Calibrate per listener if possible** — `eeg_calibrate_baseline` improves accuracy. Without it, mock/synthetic still works but valence/arousal are less personalized.

## Example: Closed-Loop Refinement

```python
# Iteration 1
result = music_generate(
    prompt="[Intro]\n◦°˚°◦•●◉✿\n[Build]\n≋≋≋♪≋≋≋\n[Drop]\n[Am][F][C][G]\n...\nWeirdness_% {35%} / Style_% {65%}",
    style="liquid drum and bass, 174 BPM, atmospheric pads, deep sub-bass",
    is_instrumental=True, model="V5"
)

# Listen with EEG
eeg_connect(serial_port="", board_type="mock")
eeg_stream_start(session_name="iter1", track_id=result.tracks[0].id, track_title=result.tracks[0].title)
music_play(track_id=result.tracks[0].id)
# ... track plays ...
music_stop()
exp = eeg_stream_stop()

# Read the narrative
# narrative says: "Strong engagement (0.78) sustained through the build, but valence
#   dropped at the drop (0.2 → -0.15). Two chills moments at 0:42 and 0:48 during
#   the build. Arousal flat through the drop, suggesting the drop didn't deliver
#   the energy promised by the build."

# Iteration 2 — adapt
result2 = music_generate(
    prompt="[Intro]\n◦°˚°◦•●◉✿\n[Build]\n≋≋≋♪≋≋≋ (lean in — this is what worked)\n[Drop]\n[Am][F][C][G]\n!!! BIG !!! \n01001000 01000101 01001100 01010000\n...\nWeirdness_% {30%} / Style_% {70%}",
    style="liquid drum and bass, 176 BPM, MASSIVE sub-bass, distorted reese, snare crack, NOT not industrial",
    is_instrumental=True, model="V5"
)
```

This is the Sonus superpower — the prompt isn't a guess, it's informed by **what the listener's brain actually felt** the last time. No other Hermes plugin closes this loop.
