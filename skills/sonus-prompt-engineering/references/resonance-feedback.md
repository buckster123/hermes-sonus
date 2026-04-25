# Resonance Feedback — Reading the Felt Experience

Deep reference for interpreting EEG/BCI output from `hermes-sonus` and translating it back into Suno prompt adjustments. Load this when you're running the closed-loop composition workflow.

## The Four Metrics + Chills

The `eeg_realtime_emotion` and saved session moments expose five dimensions:

### 1. Valence (-1.0 to +1.0)
**What it measures:** emotional pleasantness. Frontal alpha asymmetry — left frontal activation = approach/positive, right frontal = withdrawal/negative.

| Range | Reading |
|-------|---------|
| +0.6 to +1.0 | Strongly positive — joy, awe, beauty, "this is gorgeous" |
| +0.2 to +0.6 | Pleasant — comfortable, enjoying it |
| -0.2 to +0.2 | Neutral — neither drawn in nor pushed away |
| -0.6 to -0.2 | Unpleasant — uncomfortable, bored, mismatched |
| -1.0 to -0.6 | Strongly negative — actively averse |

**Prompt translation:**
- Section with persistent negative valence → texture/harmony is wrong for this listener. Try different tonal center, less dissonance, warmer instrumentation.
- Sudden valence dip mid-section → likely a specific element (snare hit, vocal layer, harmonic clash). Check chills/event timestamps near the dip.
- High valence everywhere = safe but possibly bland. A track with no negative valence dips often lacks tension.

### 2. Arousal (0.0 to 1.0)
**What it measures:** physiological activation / energy. Beta/alpha ratio across central electrodes.

| Range | Reading |
|-------|---------|
| 0.8 to 1.0 | Highly activated — the drop hit, intense climax, danceable energy |
| 0.5 to 0.8 | Engaged energy — moving, alert |
| 0.3 to 0.5 | Calm-attentive — meditative listening |
| 0.0 to 0.3 | Low activation — relaxed, possibly drifting |

**Prompt translation:**
- Drop / climax with low arousal = it didn't land. Add: faster BPM, sub-bass, snare crack, distorted lead, "MASSIVE", "wall of sound", reese bass.
- Ambient track aiming for calm but arousal stays high → too busy. Strip layers: fewer percussion elements, longer note durations, lower BPM, more space between events.
- Mismatched arousal/valence: high arousal + negative valence = alarming/abrasive (sometimes intended, often not). High arousal + positive valence = euphoric.

### 3. Attention (0.0 to 1.0)
**What it measures:** focused concentration. Theta/beta ratio at frontal electrodes (lower theta + higher beta = more focused attention).

| Range | Reading |
|-------|---------|
| 0.7 to 1.0 | Locked in — actively processing, leaning forward |
| 0.4 to 0.7 | Steady attention — listening normally |
| 0.0 to 0.4 | Drifting — background music level only |

**Prompt translation:**
- Attention drops mid-track → section is repetitive or predictable. Add a variation, modulation, instrument swap, or section change.
- Attention drops at intro → intro is too long/slow to hook. Front-load a memorable element.
- Sustained high attention through long ambient sections is a strong positive signal — the texture is genuinely captivating.

### 4. Engagement (0.0 to 1.0)
**What it measures:** the integrated "are they with the music" score. Composite of attention + arousal + valence stability.

| Range | Reading |
|-------|---------|
| 0.7 to 1.0 | Fully engaged — with the music, riding it |
| 0.4 to 0.7 | Engaged but not absorbed |
| 0.0 to 0.4 | Disengaged — the music is happening to them, not with them |

**Prompt translation:**
- This is the single best summary metric. If average engagement < 0.4 across the track, the prompt's overall direction is wrong for this listener. Pivot genre or mood substantially.
- Engagement spikes mark resonant sections — replicate their structural / harmonic / textural features in the next iteration.

### 5. Chills (event detector)
**What it measures:** discrete frisson events — sudden physiological response associated with deeply moving moments. Detected via simultaneous arousal spike + valence spike + galvanic-skin-response proxy.

Each chills event has a timestamp. **Chills are the gold standard signal of resonance.** Almost nothing else matters as much.

**Prompt translation:**
- Cluster of chills at a specific timestamp → mark that section in the prompt. What was happening there? A key change? A vocal entry? A drop? The texture introduction? **Replicate that structure.**
- Zero chills across a track → prompt is functional but not moving. Add an emotional inflection point: a key change, a sudden silence, an unexpected texture, a "(whisper) ..." vocal entry, a dramatic dynamic shift.
- Chills clustering at section boundaries (intro → verse, build → drop) means the transitions are landing hard. Lean into transition design in the next iteration.
- Chills inside a verse rather than the chorus = the verse is more evocative than the hook. Promote verse material to the chorus.

## The Felt Experience Format

`eeg_stream_stop` and `eeg_experience_get` return an AI-readable narrative. Three detail levels:

### `detail_level="narrative"` (recommended for prompt iteration)
A compact natural-language paragraph summarizing:
- Overall emotional arc (e.g., "calm intro → sustained engagement through the verse → strong frisson cluster at the chorus → fade with positive afterglow")
- Peak moments with timestamps
- Chills events
- Any notable mismatches between intent and felt response

**Read this first.** It's what the engine summarized for you specifically to inform the next prompt.

### `detail_level="summary"`
Adds aggregate stats: mean/peak/trough valence, mean arousal, mean attention, mean engagement, total chills count, session duration.

### `detail_level="full"`
Every recorded moment (2Hz sampling). Use only when narrative + summary aren't enough — for example, when you want to plot the emotional arc or correlate moments to specific lyric lines.

## Reading Order

1. **Narrative first** — it tells you the story.
2. **Chills timestamps next** — they tell you where it landed.
3. **Engagement curve** — tells you where attention drifted.
4. **Valence/arousal extremes** — tells you what worked and what didn't.
5. **Translate to prompt** — adjust style tags, restructure sections, tune weirdness/style ratio.

## Anti-Patterns

- **Don't chase pure positive valence.** Music with no negative or tense moments is often forgettable. Tension → release is what produces chills.
- **Don't over-fit to one listener.** A single session is data, not gospel. Two listeners may want opposite things from "epic cinematic ambient."
- **Don't ignore the narrative for the numbers.** The narrative captures temporal structure that averaged metrics flatten.
- **Don't iterate without playback overlap.** If the user didn't actually listen to the track during streaming, the session captured ambient brain state, not music response. Always: `music_play` → `eeg_stream_start` (or vice versa, but overlap them).

## Calibration Notes

- `eeg_calibrate_baseline(listener_name=...)` records 30s of resting state to anchor the listener's neutral. Run it once per listener per session.
- Without calibration, valence/arousal use a generic baseline — still useful, but interpret deltas rather than absolute values. If uncalibrated valence stays around +0.1 to +0.3 the whole track, that may just be the listener's neutral, not "mildly positive."
- Mock board produces synthetic curves with realistic shape but generic baseline — perfect for testing the pipeline, not for real listener insight.

## Hardware vs Mock

- **Mock** (`board_type="mock"`): software-only, no brainflow needed. Realistic emotional arc generators. Use for development, demos, and any agent run without hardware.
- **Synthetic** (`board_type="synthetic"`): brainflow's built-in test data. Slightly more realistic raw EEG patterns but still synthesized.
- **Cyton** (8-ch, 250Hz) / **Ganglion** (4-ch, 200Hz): real OpenBCI hardware. Cyton recommended for emotion sensing — frontal asymmetry needs at least 4 frontal electrodes.

The prompt-engineering loop is identical regardless of source — the agent reads the narrative the same way. Mock just produces "what a typical listener might feel" rather than "what THIS listener actually felt."
