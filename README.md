# 💽 Hermes Sonus v2.0

> **Sonic alchemy for [Hermes Agent](https://github.com/NousResearch/hermes-agent).** Suno AI music generation (V4–V5.5), MIDI composition, music library with album/EP batch workflows, voice cloning, stem separation, section replacement, style boosting, music video generation, sound effects — and an OpenBCI / felt-experience EEG layer. Now with **dual-mode architecture**: native Hermes tools + standalone MCP server.

Built for the Nous Research / Hermes Agent dashboard hackathon (Apr 24–25, 2026). v2.0 is a ground-up refactor of the hackathon-era codebase into a production-quality plugin.

---

## What's in the box

A single Hermes plugin (`hermes-sonus`) shipping four layers:

| Layer | What it does |
|---|---|
| **24 native CLI tools** | Full Suno surface — generate, extend, lyrics, clone voice, batch albums, stems, sections, boost, video, sounds. Plus MIDI, library, playback, and 8 EEG tools. |
| **MCP server** (`hermes-sonus-mcp`) | Standalone FastMCP server exposing the full Suno API as 16+ MCP tools. Works with Claude Desktop, Hermes, or any MCP client via stdio or SSE. |
| **Dashboard** (`/sonus`) | Studio (generate + poll), Library (browse / favorite / play A/B variants), Albums (DNA manifest projects), Resonance (EEG live HUD), Advanced (stems / sections / boost). |
| **Sidebar HUD slot** | Caduceus crest that blooms into a live valence/arousal/attention/engagement bar when EEG streams. |

The closed-loop pitch in one diagram:

```
                 prompt —▶ Suno —▶ MP3 (track 1, track 2)
                   ◀                     |
                   |                     ▼
                generation        listener hears it
                   ◀                     |
                   |                     ▼
            felt-experience      OpenBCI EEG (or mock)
              narrative   ◀——   valence/arousal/attention/chills
                                       (recorded as JSON)
```

The agent reads what the human felt and uses that to shape the next prompt — or the next track's DNA in an album project. Music plugins exist; **closed-loop sonic plugins for AI agents do not.**

---

## Dual-mode architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  MCP Layer (hermes_sonus.mcp.server)                             │
│  — FastMCP server, stdio/SSE                                      │
│  — 16+ tools: generate, poll, download, album, extend, lyrics,   │
│    voice cloning, stems, sections, boost, wav, video, sounds     │
│  — Handles all Suno API wire protocol                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Plugin Layer (hermes_sonus.music)                                │
│  — 24 native Hermes tools                                         │
│  — Local state: music library (JSON), album projects, playback    │
│  — EEG closed-loop (OpenBCI / brainflow)                          │
│  — Cerebro memory hooks (auto-remember favorites)                 │
└─────────────────────────────────────────────────────────────────┘
```

The plugin is as thin as possible over the Suno API. The MCP server does the heavy lifting; the plugin adds what MCP cannot: local library persistence, EEG hardware integration, audio playback, and Cerebro memory hooks.

---

## Install

```bash
# Clone into Hermes' plugins directory
git clone https://github.com/buckster123/hermes-sonus ~/.hermes/plugins/hermes-sonus
cd ~/.hermes/plugins/hermes-sonus

# Install dependencies
pip install -e ".[dev,all]"

# Set your Suno API key
export SUNO_API_KEY=...your key from sunoapi.org...

# Enable the plugin
hermes plugins enable hermes-sonus
hermes dashboard
```

### MCP server (standalone)

```yaml
# In your Hermes config or Claude Desktop config:
mcp_servers:
  sonus:
    command: hermes-sonus-mcp
    env:
      SUNO_API_KEY: ${SUNO_API_KEY}
      SUNO_CALLBACK_URL: https://your.app/callback
```

Or run directly:
```bash
hermes-sonus-mcp --transport sse --port 8765
```

---

## CLI tools

All 24 `music` tools + 8 `eeg` tools are auto-registered.

### `music` toolset (24 tools)

| Tool | Description |
|---|---|
| `music_generate` | Generate music with Suno (V4–V5.5), blocking or async |
| `music_status` | Poll generation progress |
| `music_result` | Get completed audio with both A/B variants |
| `music_list` | Recent generation tasks |
| `music_play` / `music_stop` | Play/stop locally via mpg123/ffplay |
| `music_favorite` | Toggle favorite per song or per track — auto-remembered to Cerebro |
| `music_library` | Browse with filters (favorites, agent_id, status) |
| `music_search` | Search by title/prompt/style |
| `music_delete` | Archive or permanently delete |
| `midi_create` | Create MIDI from notes (no API key needed) |
| `music_compose` | Use MIDI as compositional reference for AI generation |
| `music_extend` | Extend an existing track |
| `music_generate_lyrics` | Generate lyrics independently |
| `music_clone_voice_validate` / `music_clone_voice_create` | Voice cloning workflow |
| `music_check_credits` | Query API balance |
| `music_generate_album` | Batch generate from DNA/explicit manifest (YAML/JSON) |
| `music_separate_stems` | Stem separation (vocals from instruments) |
| `music_replace_section` | Replace a section with new lyrics |
| `music_boost_style` | Strengthen style adherence |
| `music_convert_to_wav` | MP3 → WAV conversion |
| `music_create_video` | Generate music video from track |
| `music_generate_sounds` | Non-musical sound effects |

### `eeg` toolset (8 tools)

| Tool | Description |
|---|---|
| `eeg_connect` / `eeg_disconnect` | OpenBCI Cyton / Ganglion / synthetic / mock |
| `eeg_stream_start` / `eeg_stream_stop` | Record listening session, generate felt-experience JSON |
| `eeg_realtime_emotion` | Live valence / arousal / attention / engagement / chills |
| `eeg_experience_get` | Retrieve past session — full / summary / narrative |
| `eeg_calibrate_baseline` | Personal baseline calibration |
| `eeg_list_sessions` | Browse recorded sessions |

---

## Dashboard backend (FastAPI)

`hermes-sonus` mounts its own router at `/api/plugins/hermes-sonus/*`:

```
GET  /capabilities                    → feature gating
POST /generate                        → kick off Suno task
POST /album                           → batch album from manifest
GET  /albums                          → list album projects
GET  /albums/{id}                     → album with per-track status
GET  /tasks/{id}/status               → polling
GET  /tasks/{id}/audio/{track}        → MP3 streaming with Range support
POST /tasks/{id}/favorite             → per-track favorite
POST /tasks/{id}/stems                → stem separation
POST /tasks/{id}/replace-section      → section replacement
POST /tasks/{id}/boost-style          → style boost
POST /tasks/{id}/convert-wav          → WAV conversion
POST /tasks/{id}/video                → music video
POST /sounds                          → sound effects
POST /eeg/connect                     → board_type: cyton|ganglion|synthetic|mock
POST /eeg/session/start  /  stop      → record listening sessions
GET  /eeg/state                       → live emotion sample (1Hz polling target)
GET  /eeg/sessions/{id}?detail=...    → felt-experience retrieval
```

---

## Bundled skill — `sonus-prompt-engineering`

Ships at `skills/sonus-prompt-engineering/`:

- Suno prompt engineering — Bark/Chirp manipulation, kaomoji/symbol hacks, non-standard parameters, exclude-styles tricks, weirdness/style balance
- API integration guide (`references/api-integration.md`)
- 6 worked examples including DNA-mode album manifests (`references/examples.md`)
- Prompt template (`references/template.md`)
- EEG → Album DNA mapping guide (`references/eeg-album-dna.md`)

Install:
```bash
cp -r skills/sonus-prompt-engineering ~/.hermes/skills/
```

---

## Architecture

```
hermes-sonus/
├── plugin.yaml                  # CLI/gateway plugin manifest (24+8 tools, MCP server)
├── pyproject.toml               # PyPI metadata + hermes-sonus-mcp entrypoint
├── hermes_sonus/
│   ├── __init__.py              # register(ctx) — 24 music tools
│   ├── api.py                   # FastAPI router (25+ endpoints)
│   ├── music/
│   │   ├── __init__.py          # Tool handlers + schemas
│   │   ├── suno.py            # Thin adapter over MCP layer
│   │   ├── tasks.py           # MusicTask + AlbumProject + persistence
│   │   ├── library.py         # Browse, search, favorite, Cerebro hooks
│   │   ├── midi.py            # MIDI creation with midiutil
│   │   ├── player.py          # Local playback (mpg123/ffplay)
│   │   └── library.py         # Library operations
│   ├── mcp/                 # MCP server + helpers
│   │   ├── server.py          # FastMCP server (16+ tools)
│   │   ├── build_payload.py   # Field parser + validator
│   │   ├── poll_status.py     # Exponential backoff polling
│   │   ├── batch_generate.py  # Album manifest DNA/explicit mode
│   │   ├── http_client.py     # Shared urllib helpers
│   │   └── handle_callback.py # FastAPI callback receiver
│   └── eeg/                 # OpenBCI + felt-experience
│       ├── __init__.py
│       ├── processor.py
│       └── ...
├── dashboard/               # Dashboard plugin (prebuilt static assets)
├── tests/                   # pytest suite (~140 tests)
│   ├── test_mcp_layer.py
│   ├── test_album.py
│   ├── test_suno.py
│   └── ...
└── skills/
    └── sonus-prompt-engineering/
        ├── SKILL.md
        └── references/
```

Data lives at `~/.hermes/sonus/{music,eeg}/` with JSON persistence for tasks, albums, and EEG sessions.

---

## Development

```bash
git clone https://github.com/buckster123/hermes-sonus
cd hermes-sonus
pip install -e ".[dev,all]"
pytest tests/ -v
```

Tests cover: MCP payload building, polling logic, album manifest parsing, advanced endpoint mocking, signal processing, MIDI creation, library filters, player routing, and EEG handlers in mock mode (no hardware required).

---

## License

MIT. See `LICENSE`.

---

*"µηδεν σταθμός — everything flows."* — built by Andre + Hermes for the Nous Research hackathon, April 2026. v2.0 refactor, May 2026.
