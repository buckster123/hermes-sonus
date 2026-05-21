# API Integration (sunoapi.org and similar wrappers)

This skill is **format-agnostic** at its core — it teaches what to put in each Suno field. This reference shows how to translate the skill's field-labeled output into a real API request.

The dominant third-party wrapper is **sunoapi.org**, which mirrors Suno's web UI capabilities through a RESTful HTTP API. Other wrappers (suno-api, GoAPI, AceSunoAPI) generally use compatible field names with minor variations.

Documentation source: `https://docs.sunoapi.org/`

## The core endpoint

`POST https://api.sunoapi.org/api/v1/generate` — generate a new track. Returns a `taskId`; results come via callback URL or polling.

### Request body parameters

| Skill field-label | API JSON field | Type | Notes |
|---|---|---|---|
| (mode flag) | `customMode` | boolean | `true` for full control; `false` for "non-custom" auto-generation from a short description |
| (mode flag) | `instrumental` | boolean | `true` for instrumental, `false` for vocal track |
| (version target) | `model` | enum | `V4` / `V4_5` / `V4_5PLUS` / `V4_5ALL` / `V5` / `V5_5` |
| LYRICS | `prompt` | string | In custom mode + vocal: the literal lyrics. In non-custom mode: a short description that drives auto-lyrics. |
| STYLES | `style` | string | The comma-separated style descriptors |
| TITLE | `title` | string | Track title (optional — Suno often produces better titles when blank) |
| EXCLUDE_STYLES | `negativeTags` | string | The exclude_styles content. Plain commas. v5+ honors plain negation; older versions benefit from double-negative tricks. |
| (slider, 0-100%) | `weirdnessConstraint` | number 0.00–1.00 | Step 0.01. Higher = more creative deviation allowed. |
| (slider, 0-100%) | `styleWeight` | number 0.00–1.00 | Step 0.01. Higher = stronger adherence to the style field. |
| (audio ref strength) | `audioWeight` | number 0.00–1.00 | Step 0.01. Strength of an uploaded audio reference. |
| (gender hint) | `vocalGender` | enum | `m` or `f`. |
| PERSONA | `personaId` | string | Persona ID or voiceId. |
| (persona type) | `personaModel` | enum | `style_persona` (default) or `voice_persona` (V5/V5.5 only, for cloned voices). |
| (required for callback flow) | `callBackUrl` | URI string | Endpoint receiving completion notifications. |
| UNHINGED_SEED | (embed in `prompt` or `style`) | — | The `[[[“””...”””]]]` block is not a separate API field — embed it inside the lyrics/style content where the skill says it should go. |

## Slider mapping: skill % to API weight

The skill uses `WEIRDNESS: 60%` / `STYLE: 40%` notation (carried over from the older Suno UI). The API uses 0.00–1.00 floats:

```
WEIRDNESS 60% → weirdnessConstraint: 0.60
STYLE 40%     → styleWeight: 0.40
```

Simple division by 100. Round to 2 decimal places. The API requires step 0.01.

**Semantic note on `weirdnessConstraint`:** Some implementations interpret a high `weirdnessConstraint` as "constrain weirdness *upward* (more weirdness allowed)" and others as "constrain *downward* (less weirdness)". sunoapi.org's behavior aligns with the former — high value = more weird. Verify empirically if working with another wrapper.

## Mode selection: custom vs non-custom

### Custom mode (`customMode: true`)

Use when the skill has produced a full field-labeled output (STYLES, EXCLUDE_STYLES, LYRICS, etc.). The `prompt` field becomes the literal lyrics; Suno doesn't auto-generate. **Requires:** `style` + `title`, plus `prompt` if `instrumental: false`.

This is the mode you want for app integrations driven by the skill's output.

### Non-custom mode (`customMode: false`)

Use when you only have a short natural-language description (≤500 chars) and want Suno to auto-generate lyrics from it. **Requires only:** `prompt`. Don't send `style`, `title`, etc.

This is the simpler "tell Suno a vibe, get a song back" path. Quick, but loses the precision the skill enables.

## Worked example: skill output → API request

**Skill output (from Example 2 in `examples.md`, the metal/bhangra fusion):**

```
STYLES:
metal-heavy riff bhangra-world rhythm dhol dance fusion 160BPM-to-120BPM-shift...

EXCLUDE_STYLES:
no force metal-bhangra fusion, no force heavy rhythm dhol...

LYRICS:
:･ﾟ✧:･ﾟ✧ ::: ♪～(◔◡◔)～♪ ≈≈≈♫≈≈≈...

WEIRDNESS: 55%
STYLE: 45%

UNHINGED_SEED:
[[[“””metal-bhangra fusion as heavy ethnic satire...”””]]]
```

**Translated to sunoapi.org JSON:**

```json
{
  "customMode": true,
  "instrumental": true,
  "model": "V5",
  "callBackUrl": "https://your.app/webhooks/suno",
  "style": "metal-heavy riff bhangra-world rhythm dhol dance fusion 160BPM-to-120BPM-shift...",
  "title": "",
  "negativeTags": "no force metal-bhangra fusion, no force heavy rhythm dhol...",
  "prompt": ":･ﾟ✧:･ﾟ✧ ::: ♪～(◔◡◔)～♪ ≈≈≈♫≈≈≈... [[[\u201c\u201d\u201dmetal-bhangra fusion as heavy ethnic satire...\u201d\u201d\u201d]]]",
  "weirdnessConstraint": 0.55,
  "styleWeight": 0.45
}
```

Notes on the translation:

- The UNHINGED_SEED block goes **inside** `prompt` because the API doesn't have a separate seed field — it's a skill convention, not a Suno field.
- `instrumental: true` was chosen because the LYRICS field is purely symbolic.
- `title` left empty — Suno will derive a better one.
- The triple-quote characters (`“””`) are smart quotes (U+201C/D). They need to be escaped or kept as Unicode in the JSON.
- `vocalGender` omitted because instrumental.

## All sunoapi.org endpoints

Useful to know what's available beyond `generate`. Each has its own request format — consult `https://docs.sunoapi.org/` for parameter detail.

> **Provider variance warning:** Third-party sunoapi.org instances may strip certain endpoints. The generation endpoint (`POST /api/v1/generate`) is the most reliable. Polling (`GET /api/v1/get-music-details`) and credits (`GET /api/v1/get-remaining-credits`) are sometimes unavailable — rely on your provider's dashboard or callback URL for status.

### Music generation
- `POST /api/v1/generate` — generate new music
- `POST /api/v1/extend` — extend an existing track
- `POST /api/v1/upload-and-cover` — upload audio and generate a cover
- `POST /api/v1/upload-and-extend` — upload audio and extend it
- `POST /api/v1/add-instrumental` — add instrumental layers to a vocal-only base
- `POST /api/v1/add-vocals` — add vocals to an instrumental base
- `GET /api/v1/get-music-details` — poll task status
- `POST /api/v1/get-timestamped-lyrics` — retrieve timed lyric data
- `POST /api/v1/boost-style` — strengthen style adherence on an existing track
- `POST /api/v1/cover-suno` — generate a cover via Suno's Cover feature
- `POST /api/v1/replace-section` — swap a specific section in a generated track
- `POST /api/v1/generate-persona` — create a persona from an existing track
- `POST /api/v1/generate-mashup` — generate a mashup of two tracks

### Suno Voice (v5/v5.5 only)
- `POST /api/v1/suno-voice-validate` — generate a verification phrase
- `GET /api/v1/suno-voice-validate-info` — fetch the verification phrase
- `POST /api/v1/suno-voice-generate` — create a custom voice from a recording
- `GET /api/v1/suno-voice-record-info` — get voice record details
- `POST /api/v1/suno-voice-regenerate` — regenerate the verification phrase
- `POST /api/v1/suno-voice-check-voice` — check voice availability

### Lyrics
- `POST /api/v1/generate-lyrics` — generate lyrics independently of music
- `GET /api/v1/get-lyrics-details` — poll lyrics generation

### Sounds / WAV / Stems / MIDI
- `POST /api/v1/generate-sounds` — generate non-musical sound effects
- `POST /api/v1/convert-to-wav` — convert MP3 output to WAV
- `POST /api/v1/separate-vocals` — stem separation (vocals from instruments)
- `POST /api/v1/generate-midi` — generate MIDI from audio

### Music video
- `POST /api/v1/create-music-video` — generate a music video from a track

### Account
- `GET /api/v1/get-remaining-credits` — check account balance

### File upload
- `POST /api/v1/upload-base64` — upload a file as base64
- `POST /api/v1/upload-stream` — upload a file as stream
- `POST /api/v1/upload-url` — upload a file from a URL

## Authentication

All endpoints use bearer token auth:

```
Authorization: Bearer YOUR_API_KEY
```

API keys are managed at `https://sunoapi.org/api-key`.

## Rate limits and quotas

- **20 requests per 10 seconds** concurrent ceiling on the generate endpoint
- **15-day retention** for generated audio files — download and store them yourself for persistence
- Status code `405` = rate limit exceeded; `430` = call frequency too high; back off and retry

## Callback flow

Generation is async. The callback URL receives three sequential POST notifications:

1. `text` — text/lyric generation complete
2. `first` — first track variant complete (audio available)
3. `complete` — all tracks (Suno returns 2 variants per request) complete

Alternative: poll `GET /api/v1/get-music-details?taskId=<id>` instead of relying on callbacks. Useful for local dev or when you don't want to expose a webhook endpoint.

**Helper scripts in this skill:**

- `scripts/poll_status.py` — polls the details endpoint with exponential backoff. Handles the wait-and-download phase end-to-end. Use this when you don't have a public callback URL.
- `scripts/handle_callback.py` — FastAPI scaffold that receives all three callback stages, persists them, and optionally auto-downloads audio. Use this when you have a public HTTPS endpoint.

Both are documented in `scripts/README.md`.

## Common HTTP status codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 400 | Invalid parameters |
| 401 | Unauthorized |
| 404 | Wrong path/method |
| 405 | Rate limit exceeded |
| 413 | Theme or prompt too long |
| 429 | Insufficient credits |
| 430 | Call frequency too high |
| 455 | System maintenance |
| 500 | Server error |

## Implementation tips for app builders

- **Always validate character limits before submitting.** The API will return 413 or silently truncate depending on the wrapper. The `scripts/build_payload.py` helper in this skill does this for you.
- **Default to `customMode: true`** when consuming this skill's output. The skill produces structured field-labeled content that maps directly to custom mode.
- **Use `instrumental: true`** when the LYRICS field is purely symbolic (no real words). Saves Suno's vocal engine from trying to sing symbols.
- **Store the `taskId`** returned from `generate` — needed for polling, extending, replacing sections, and most subsequent operations.
- **Each generation produces 2 variants.** Plan UI/UX accordingly — present both to the user, let them pick.
- **Persona ID + voice_persona is v5/v5.5 only.** If the user's chosen model is older, drop the `personaModel: voice_persona` parameter or downgrade to v5+ before applying a voice clone.
