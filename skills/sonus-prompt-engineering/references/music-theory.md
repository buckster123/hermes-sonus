# Music Theory for Suno Prompts

## Song Structure — Section Tags

Use these as `[Section]` tags in the prompt/lyrics field. Don't number them — [Verse] not [Verse 1].

### Common Sections
| Section | Purpose | Example Progression |
|---------|---------|-------------------|
| `[Intro]` | Set mood/tone | [C-Am-F-G] in C |
| `[Verse]` | Narrative, storytelling | [Am-F-C-G] in Am |
| `[Pre-Chorus]` | Build tension | [Em-Bm-C-D] in G |
| `[Chorus]` | Hook, memorable peak | [C-G-Am-F] in C |
| `[Post-Chorus]` | Emphasize hook | [F-G-Em-Am] in Am |
| `[Bridge]` | Contrast, key change | [Bm-G-A-F#m] in D |
| `[Outro]` | Resolve, fade | [C-G-Am-F] fade in C |
| `[Interlude]` | Instrumental break | [E-A-B] in E |
| `[Solo]` | Instrument solo | [Am-Dm-G-C] in Am |
| `[Build-Up]` | Energy escalation | [Em → G → C → D] |
| `[Breakdown]` | Strip to minimal | Single element |
| `[Climax]` | Peak intensity | Full arrangement |
| `[Tag]` | Short repeated phrase | Hook repetition |

### Default Song Structure
```
[Intro] → [Verse] → [Pre-Chorus] → [Chorus] → [Verse] → [Pre-Chorus] → [Chorus] → [Bridge] → [Chorus] → [Outro]
```

## Standard Song Forms

| Form | Pattern | Best For |
|------|---------|----------|
| Verse-Chorus (ABAB) | Verse/Chorus alternating | Pop, Rock, Country |
| AABA | Verse/Verse/Bridge/Verse | Jazz standards, Classic |
| Strophic (AAA) | Same section repeated | Folk, hymns, chants |
| 12-Bar Blues | I-I-I-I / IV-IV-I-I / V-IV-I-I | Blues, Blues-Rock |
| Through-Composed | All unique sections | Classical, Progressive |
| Rondo (ABACA) | Recurring A section | Classical, EDM |
| Build-Drop | Build → Drop → Build → Drop | EDM, Electronic |

## Chord Progressions

### Universal Progressions
| Name | Numerals | In C Major | Mood |
|------|----------|-----------|------|
| Pop Canon | I-V-vi-IV | C-G-Am-F | Uplifting, anthemic |
| Jazz ii-V-I | ii-V-I | Dm-G-C | Sophisticated, resolving |
| Sad/Emotional | vi-IV-I-V | Am-F-C-G | Melancholy, cinematic |
| Pachelbel | I-V-vi-iii-IV-I-IV-V | C-G-Am-Em-F-C-F-G | Grand, sweeping |
| Blues | I-I-I-I-IV-IV-I-I-V-IV-I-I | C repeated pattern | Raw, soulful |
| Dark/Tense | i-bVI-bIII-bVII | Am-F-C-G | Minor key tension |
| Andalusian | iv-bIII-bII-I | Dm-C-Bb-A | Spanish, exotic |

### Genre-Specific Progressions
- **Pop/Rock**: I-V-vi-IV, vi-IV-I-V
- **Jazz**: ii-V-I, I-vi-ii-V (turnaround)
- **Blues**: 12-bar, I-IV-I-V-IV-I
- **EDM**: i-bVI-bIII-bVII (minor key power)
- **Hip-Hop**: Often modal, single chord vamp, i-iv or i-bVII
- **Country**: I-IV-V, I-V-vi-IV in major keys
- **Classical**: Functional harmony, modulations

## Chord Notation in Suno Prompts

Place chord tags at the start of lines/sections:
```
[Verse]
[Am] [Em] [F] [C]
≈≈≈♫≈≈≈ ∞♪∞
```

Chain progressions with emotion descriptors:
```
[Verse] [Am] [F] [G] [Em] — questioning, searching
[Chorus] [C] [G] [Am] [F] — resolving, triumphant
```

## Key Signatures and Mood

| Key | General Mood |
|-----|-------------|
| C Major | Bright, simple, pure |
| G Major | Warm, pastoral, optimistic |
| D Major | Triumphant, joyful |
| A Major | Confident, radiant |
| E Major | Powerful, brilliant |
| F Major | Gentle, pastoral |
| Bb Major | Bold, majestic |
| A Minor | Melancholy, reflective |
| E Minor | Sad, introspective |
| D Minor | Serious, dark |
| B Minor | Dark, brooding |
| F# Minor | Mysterious, tense |

## Dynamics and Expression

Use in prompts for intensity control:
- `[pp]` pianissimo — very soft
- `[p]` piano — soft
- `[mp]` mezzo-piano — moderately soft
- `[mf]` mezzo-forte — moderately loud
- `[f]` forte — loud
- `[ff]` fortissimo — very loud
- `[crescendo]` — gradually louder
- `[decrescendo]` — gradually softer

## Tempo Ranges by Genre

| Genre | Typical BPM |
|-------|-------------|
| Ambient | 60-90 |
| Hip-Hop | 80-115 |
| R&B/Soul | 60-100 |
| Pop | 100-130 |
| House | 120-130 |
| Techno | 125-150 |
| Rock | 110-140 |
| Drum & Bass | 160-180 |
| Dubstep | 138-142 (half-time feel) |
| Metal | 100-180+ |
| Jazz | 60-200 (varies widely) |

Use fractional BPM for groove (e.g., 126.8 instead of 127).

## Advanced Techniques

### Modulation
- Half-step up in final chorus for energy lift
- Relative minor/major shifts for emotional contrast
- Chromatic modulation for dramatic tension

### Meter Changes
- `4/4 to 3/4` — creates waltz-like flow shift
- `7/8` — progressive/math rock tension
- `5/4` — asymmetric, unsettled feeling

### Counterpoint
- Layer independent melodic lines
- Use section tags for different instruments: `[Cello Line]` `[Violin Response]`

### Ostinato
- Repeating riff or pattern: `[C-Bb-Ab-G]` looped
- Foundation for building layers on top

### Genre-Specific Section Patterns
- **Pop/Rock**: Verse-Chorus + Guitar Solo + Bridge
- **Hip-Hop**: Beat loops, minimal chord movement, 808s
- **Country**: AABA form, I-IV-V in major keys
- **EDM**: Build → Drop → Build → Drop, minimal harmonic movement
- **Classical**: Through-Composed, modulating, development sections
- **Jazz**: Head → Solos → Head, ii-V-I turnarounds
