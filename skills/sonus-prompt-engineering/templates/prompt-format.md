# Sonus Prompt Template

Use this template to structure prompts for `music_generate()` (and the closed-loop EEG variant). Map each section to the corresponding tool parameter.

## Instrumental Track

```python
music_generate(
    prompt="""[Intro]
◦°˚°◦•●◉✿ ≈≈≈♫≈≈≈
[Verse]
[Am] [Em] [F] [C]
♪(◠‿◠)♪ ∞♪∞♪∞
✧･ﾟ: ✧･ﾟ:\\
[Pre-Chorus]
[Build-Up]
≋≋≋♪≋≋≋ .・゜-: ♪ :-・゜.
[Chorus]
[C] [G] [Am] [F]
⋆｡°✩₊˚.⋆ (˘▾˘)♫
[Bridge]
[Dm] [Am] [G] [C]
:･ﾟ✧:･ﾟ✧ ∼(⌒◡⌒)∼
[Outro]
◦°˚°◦•●◉✿✿◉●•◦°˚°◦
...

Weirdness_% {30%} / Style_% {70%}
[[[\"\"\"Ethereal soundscape blending organic textures with digital consciousness\"\"\"]]]""",
    style="ambient electronic, atmospheric, 96.3 BPM, ethereal pads, warm synthesis, 432Hz",
    title="",  # leave blank for Suno to title
    model="V5",
    is_instrumental=True,
)
```

## Vocal Track

```python
music_generate(
    prompt="""[Intro]
[Am] [F] [C] [G]

[Verse]
Walking through the static rain
Digital flowers bloom again
Every signal finds its way
Through the noise of yesterday

[Pre-Chorus]
And the frequencies align...
Every wavelength intertwined...

[Chorus]
We are echoes in the wire
We are sparks of something higher
::Through the dark we find the light::
{We are echoes in the wire}

[Verse]
Satellite reflections fade
Memories in circuit made
Binary beneath the skin
Let the transmission begin

[Pre-Chorus]
And the frequencies align...
Every wavelength intertwined...

[Chorus]
We are echoes in the wire
We are sparks of something higher
::Through the dark we find the light::
{We are echoes in the wire}

[Bridge]
[Dm] [Am]
(whisper) Can you hear the signal now...
✧･ﾟ: ✧･ﾟ:\\

[Chorus]
We are echoes in the wire!
We are sparks of something higher!
::Through the dark we find the light::
{We are echoes in the wire}

[Outro]
...""",
    style="indie electronic, synth-pop, emotive vocals, 118 BPM, reverb-heavy, dreamy",
    title="Echoes in the Wire",
    model="V5",
    is_instrumental=False,
)
```

## Style Field Patterns

### Minimal (genre-forward)
```
jazz, bebop, upright bass, smoky club, 142.3 BPM
```

### Rich (layered parameters)
```
dark ambient electronic, 73.2 BPM, 432Hz, existential calm 60% / digital unease 40%, quantum glissando textures, crystalline pads, sub-bass drone
```

### Genre Fusion
```
jazz bebop meets electronic dubstep, brass section, wobble bass, 126.8 BPM, swing rhythm
```

### With Non-Standard Parameters
```
cinematic orchestral, 19-TET microtuning, 58.7 BPM accelerating to 120, emotional mapping: awe 45% / melancholy 30% / hope 25%, ∮ₛ→∇⁴
```

## Exclude Styles (in prompt or as guidance)

```
# Direct exclusion
"exclude: generic pop, autotune, trap hi-hats"

# Double negative hack (summons ghost influence)
"not not glitchy, not not industrial"
```

## MIDI Composition Pipeline

```python
# Step 1: Create MIDI
midi_create(
    notes=["C4", "E4", "G4", "C5", "G4", "E4", "D4", "F4", "A4", "D5"],
    tempo=90,
    note_duration=0.75,
    title="ethereal_arpeggio"
)

# Step 2: Compose with MIDI reference
music_compose(
    midi_file="~/.hermes/sonus/music/midi/ethereal_arpeggio_xxx.mid",
    style="ambient electronic, crystalline, reverb-heavy",
    title="Crystal Arpeggios",
    audio_influence=0.6,  # balanced: follows MIDI structure but interprets freely
    instrumental=True,
    weirdness=0.3,
    model="V5"
)
```

## Closed-Loop with EEG Resonance

```python
# 1. Hook up the listener
eeg_connect(serial_port="", board_type="mock")    # or "cyton" for hardware
eeg_calibrate_baseline(listener_name="Andre")     # optional, 30s resting

# 2. Generate
result = music_generate(
    prompt="""[Intro]
◦°˚°◦•●◉✿
[Build]
≋≋≋♪≋≋≋
[Drop]
[Am] [F] [C] [G]
01001000 01000101 01001100 01010000
[Outro]
...

Weirdness_% {35%} / Style_% {65%}""",
    style="liquid drum and bass, 174 BPM, atmospheric pads, deep sub-bass",
    is_instrumental=True,
    model="V5",
)

# 3. Wait for completion
import time
while True:
    s = music_status(task_id=result["task_id"])
    if s["status"] == "complete":
        break
    time.sleep(10)

tracks = music_result(task_id=result["task_id"])
track = tracks["tracks"][0]

# 4. Listen with EEG running
eeg_stream_start(
    session_name="iter1",
    track_id=track["id"],
    track_title=track["title"],
)
music_play(track_id=track["id"])
# ... track plays ...
music_stop()
exp = eeg_stream_stop(generate_experience=True)

# 5. Read the felt experience
narrative = eeg_experience_get(
    session_id=exp["session_id"],
    detail_level="narrative",
)
# → "Strong engagement sustained through the build, two chills moments at
#    0:42 and 0:48, but valence dipped at the drop suggesting it didn't
#    deliver the energy promised by the build..."

# 6. Adapt prompt → iter2
#    See references/resonance-feedback.md for the translation guide
```
