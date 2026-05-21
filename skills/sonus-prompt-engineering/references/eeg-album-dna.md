# EEG → Album DNA Mapping

Hermes-Sonus v2.0 closes the loop between felt-experience (EEG) and generative music. After an EEG listening session, the agent can extract emotional peaks and translate them into DNA fragments for the next track in an album.

## Workflow

1. **Generate track N** via `music_generate` or as part of an album
2. **Stream EEG** via `eeg_stream_start` while the listener hears track N
3. **Stop session** via `eeg_stream_stop` → produces felt-experience JSON
4. **Parse narrative** for high-engagement / chills sections:
   - Look for `"emotional_peak"` or `"possible_chills"` event flags
   - Note the timecodes and associated musical qualities (if annotated)
5. **Map to DNA fragments**:
   - "Ethereal pads triggered high engagement at 2:15" → add `"ethereal pads"` to `album_dna.styles`
   - "Tribal percussion caused arousal spike" → add `"tribal percussion, deep sub-bass"` to next track's delta
   - "Silence before drop produced chills" → add `"sparse arrangement, dramatic drop"` to DNA
6. **Generate track N+1** using the enriched album DNA

## Example mapping

```yaml
# After EEG session on Track 1:
album_dna:
  album_title: "Resonance Study"
  styles: "ambient electronic, downtempo, 432Hz tuning"
  # Enriched from EEG feedback:
  weirdness_pct: 30  # lowered because high engagement came from predictability

tracks:
  - title: "Track 1 — Baseline"
    styles: "ethereal pads, slow evolving"
    # ... generated and listened to with EEG

  - title: "Track 2 — Response"
    # EEG showed chills at the drop and sustained engagement on pads
    styles: "ethereal pads, dramatic drop, sparse arrangement"
    weirdness_pct: 25  # even lower for tighter emotional control
```

## Cerebro integration

Store the mapping as a Cerebro schema tagged with `suno:eeg-mapping` so future sessions can recall which musical elements produced which emotional responses for this listener.

```
Schema: "Ethereal pads + 432Hz tuning → high engagement + chills at drops"
Tags: suno:eeg-mapping, suno:style:ambient, listener:andrey
```

This turns the album from a static collection into an **adaptive emotional journey**.
