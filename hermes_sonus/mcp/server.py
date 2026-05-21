#!/usr/bin/env python3
"""
suno_mcp_server.py — MCP server exposing Suno API operations as tools for AI assistants.

Built on the official Python MCP SDK (FastMCP). Wraps the helper scripts in this skill
to give an AI assistant direct access to the full Suno generation workflow:

  - generate_song          — fire a generate request from skill-style field input
  - check_status           — poll a task's status
  - download_track         — download a completed track's audio
  - generate_album         — batch generate from a YAML/JSON manifest
  - extend_track           — extend an existing generated track
  - generate_lyrics        — get lyrics without generating audio
  - clone_voice_validate   — generate a verification phrase for voice cloning
  - clone_voice_create     — create a voice clone from a recording
  - list_endpoints         — list all Suno API endpoints with descriptions
  - check_credits          — check remaining API credits

Install:
    pip install mcp fastmcp pyyaml

Run as MCP server (stdio transport, default for Claude Desktop):
    python suno_mcp_server.py

Run with HTTP transport for remote clients:
    python suno_mcp_server.py --transport sse --port 8765

Configuration via environment variables:
    SUNO_API_KEY        — Your sunoapi.org API key (required)
    SUNO_BASE_URL       — API base URL (default: https://api.sunoapi.org)
    SUNO_CALLBACK_URL   — Default callback URL for generate requests (optional;
                          some tools need a callback even if you don't process it)
    SUNO_DOWNLOAD_DIR   — Where to save downloaded audio (default: ./suno_downloads/)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: mcp SDK not installed.\n"
        "  Install: pip install mcp pyyaml\n"
        "  Docs:    https://modelcontextprotocol.io/",
        file=sys.stderr,
    )
    sys.exit(2)

# Import helper logic from the local mcp package
from .build_payload import (
    ParsedFields,
    validate_limits,
    build_payload,
    merge_unhinged_seed_into_lyrics,
    MODEL_LIMITS,
)
from .poll_status import (
    fetch_status,
    extract_status,
    extract_audio_urls,
    download_track as _download_track,
    TERMINAL_STATES,
)
from .http_client import (
    api_post as _post,
    api_get as _get,
    _require_api_key,
    SUNO_API_KEY,
    SUNO_BASE_URL,
    SUNO_CALLBACK_URL as _ENV_CALLBACK_URL,
)

# --- Local configuration ---

SUNO_CALLBACK_URL = os.environ.get("SUNO_CALLBACK_URL", "").strip() or _ENV_CALLBACK_URL
SUNO_DOWNLOAD_DIR = Path(os.environ.get("SUNO_DOWNLOAD_DIR", "./suno_downloads"))
MODELS = Literal["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"]

# --- MCP server setup ---

mcp = FastMCP(
    name="suno-prompting",
    instructions=(
        "MCP server providing Suno AI music generation tools. "
        "Use generate_song to create music from skill-style field input "
        "(STYLES, EXCLUDE_STYLES, LYRICS, WEIRDNESS, STYLE). "
        "Use check_status to poll a task, download_track to retrieve audio. "
        "Use generate_album for multi-track projects via manifest. "
        "See list_endpoints for the full Suno API surface."
    ),
)


# --- Tools ---


@mcp.tool()
def generate_song(
    styles: str,
    lyrics: str = "",
    exclude_styles: str = "",
    title: str = "",
    weirdness_pct: float = 50.0,
    style_pct: float = 50.0,
    unhinged_seed: str = "",
    model: str = "V5",
    instrumental: bool | None = None,
    vocal_gender: str = "",
    callback_url: str = "",
) -> dict:
    """Generate a Suno song from skill-style field inputs.

    Takes the standard Suno prompt fields (styles, exclude_styles, lyrics, sliders, etc.),
    validates them against the model's character limits, builds a sunoapi.org payload, and
    fires the request. Returns the task ID and initial response.

    Args:
        styles: The music style descriptors. Comma-separated. e.g., "dream pop, breathy female vocals, 80BPM, warm reverb"
        lyrics: The lyrics or symbol-as-instrumental content. For vocal songs, real words.
                For instrumental, use symbols/kaomoji/binary. Can include section tags like [Verse], [Chorus].
        exclude_styles: Styles or elements to exclude. Comma-separated. e.g., "no autotune, no electronic drums"
        title: Optional title. Leave blank for Suno to auto-generate (often produces better titles).
        weirdness_pct: 0-100. Higher = more creative deviation. Default 50.
        style_pct: 0-100. Higher = stronger adherence to styles field. Default 50.
        unhinged_seed: Optional satirical context block. Will be wrapped in [[[ "" "" "" ]]] and embedded.
        model: Suno model. One of V4, V4_5, V4_5PLUS, V4_5ALL, V5, V5_5. Default V5.
        instrumental: True for instrumental, False for vocal, None (default) auto-detects from lyrics content.
        vocal_gender: "m" or "f" hint for vocal gender. Ignored if instrumental.
        callback_url: Where Suno should POST async results. Falls back to SUNO_CALLBACK_URL env var.

    Returns:
        Dict with task_id (if successful), full API response, validation warnings, and the payload sent.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    callback = callback_url or SUNO_CALLBACK_URL
    if not callback:
        return {
            "error": "callback_url required (or set SUNO_CALLBACK_URL env var). "
            "Suno is async — it needs somewhere to send results."
        }

    # Build fields
    fields = ParsedFields()
    fields.styles = styles
    fields.exclude_styles = exclude_styles or None
    fields.lyrics = lyrics or None
    fields.title = title or None
    fields.weirdness_pct = max(0.0, min(1.0, weirdness_pct / 100.0))
    fields.style_pct = max(0.0, min(1.0, style_pct / 100.0))
    fields.unhinged_seed = None
    if unhinged_seed:
        # Wrap in the canonical bracket form if user didn't
        seed = unhinged_seed.strip()
        if not seed.startswith("[[["):
            seed = f'[[[“””{seed}”””]]]'
        fields.unhinged_seed = seed
    fields.vocal_gender = vocal_gender.lower() if vocal_gender else None

    merge_unhinged_seed_into_lyrics(fields)

    # Auto-detect instrumental if not specified
    if instrumental is None:
        if fields.lyrics:
            word_chars = sum(1 for c in fields.lyrics if c.isalpha() or c.isspace())
            instrumental = (word_chars / max(len(fields.lyrics), 1)) < 0.4
        else:
            instrumental = True

    # Validate
    warnings = validate_limits(fields, model, instrumental, True)

    # Build payload
    payload = build_payload(fields, model, callback, instrumental, True)

    # Fire
    response = _post("/api/v1/generate", payload)
    task_id = None
    if response.get("code") == 200 and isinstance(response.get("data"), dict):
        task_id = response["data"].get("taskId")

    return {
        "task_id": task_id,
        "model": model,
        "instrumental": instrumental,
        "warnings": warnings,
        "response": response,
        "payload": payload,
    }


@mcp.tool()
def check_status(task_id: str) -> dict:
    """Check the status of a generation task.

    Use this to see if a task is still pending, complete, or failed.
    For long-running waits, prefer check_status_until_done.

    Args:
        task_id: The taskId returned from generate_song or similar.

    Returns:
        Dict with status (pending/complete/error/etc.), audio URLs if ready, raw response.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    response = fetch_status(SUNO_BASE_URL, task_id, SUNO_API_KEY)
    status = extract_status(response)
    tracks = extract_audio_urls(response)

    return {
        "task_id": task_id,
        "status": status,
        "is_complete": status in TERMINAL_STATES,
        "tracks": tracks,
        "track_count": len(tracks),
        "response": response,
    }


@mcp.tool()
def check_status_until_done(task_id: str, timeout_seconds: int = 300) -> dict:
    """Poll a task's status until it completes or times out.

    Suno generation usually finishes in 30-180 seconds. This tool blocks until the task
    reaches a terminal state, with exponential backoff between polls.

    Args:
        task_id: The taskId to wait on.
        timeout_seconds: Max wait time. Default 300 (5 min). Raise for slow generations.

    Returns:
        Dict with final status, audio tracks (if complete), and total wait time.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    start = time.time()
    interval = 5.0
    iterations = 0

    while True:
        elapsed = time.time() - start
        if elapsed > timeout_seconds:
            response = fetch_status(SUNO_BASE_URL, task_id, SUNO_API_KEY)
            return {
                "task_id": task_id,
                "status": "timeout",
                "is_complete": False,
                "wait_seconds": int(elapsed),
                "iterations": iterations,
                "last_response": response,
            }

        iterations += 1
        response = fetch_status(SUNO_BASE_URL, task_id, SUNO_API_KEY)
        status = extract_status(response)

        if status in TERMINAL_STATES:
            tracks = extract_audio_urls(response)
            return {
                "task_id": task_id,
                "status": status,
                "is_complete": True,
                "wait_seconds": int(elapsed),
                "iterations": iterations,
                "tracks": tracks,
                "track_count": len(tracks),
                "response": response,
            }

        time.sleep(min(interval, 30.0))
        interval *= 1.5


@mcp.tool()
def download_track(
    task_id: str,
    download_dir: str = "",
    track_index: int | None = None,
) -> dict:
    """Download generated audio file(s) from a completed task to local disk.

    Args:
        task_id: The taskId with completed audio.
        download_dir: Local directory for saved files. Defaults to SUNO_DOWNLOAD_DIR env var or ./suno_downloads/.
        track_index: Optional 1-based index to download only one track. If None, downloads all variants.

    Returns:
        Dict with list of saved file paths, or an error if the task isn't complete.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    response = fetch_status(SUNO_BASE_URL, task_id, SUNO_API_KEY)
    status = extract_status(response)
    if status not in TERMINAL_STATES:
        return {
            "error": f"Task is in status '{status}' — not complete. Use check_status_until_done first."
        }

    tracks = extract_audio_urls(response)
    if not tracks:
        return {"error": "No audio URLs found in response. Task may have failed."}

    out_dir = Path(download_dir or SUNO_DOWNLOAD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, track in enumerate(tracks, 1):
        if track_index is not None and i != track_index:
            continue
        path = _download_track(track, out_dir, task_id, i)
        if path:
            saved.append(str(path))

    return {
        "task_id": task_id,
        "saved_files": saved,
        "track_count": len(tracks),
        "downloaded": len(saved),
    }


@mcp.tool()
def generate_album(
    manifest_text: str,
    manifest_format: Literal["yaml", "json"] = "yaml",
    fire: bool = False,
    callback_url: str = "",
) -> dict:
    """Generate multiple coherent Suno tracks from an album/EP manifest.

    The manifest defines either explicit per-track field sets, or an `album_dna` block
    plus track deltas (DNA mode). See Example 6 in references/examples.md for the schema.

    Args:
        manifest_text: The manifest content as a string (YAML or JSON).
        manifest_format: "yaml" or "json". Determines how to parse manifest_text.
        fire: If True, actually POSTs the requests (with rate limiting). If False, returns built payloads only.
        callback_url: Override the manifest's callback_url. Falls back to SUNO_CALLBACK_URL env var.

    Returns:
        Dict with built payloads, task_ids (if fired), and per-track warnings.
    """
    err = _require_api_key() if fire else None
    if err:
        return {"error": err}

    # Parse manifest
    try:
        if manifest_format == "yaml":
            try:
                import yaml  # type: ignore
            except ImportError:
                return {"error": "PyYAML not installed. Run: pip install pyyaml. Or use manifest_format='json'."}
            manifest = yaml.safe_load(manifest_text)
        else:
            manifest = json.loads(manifest_text)
    except Exception as e:
        return {"error": f"Manifest parse error: {e}"}

    # Import batch logic from local package
    try:
        from .batch_generate import (
            parse_manifest,
            fields_dict_to_parsed,
            detect_instrumental,
            fire_request,
            SAFE_INTERVAL,
        )
    except ImportError as e:
        return {"error": f"Could not import batch_generate: {e}"}

    try:
        resolved_tracks, settings = parse_manifest(manifest)
    except Exception as e:
        return {"error": f"Manifest invalid: {e}"}

    callback = callback_url or settings.get("callback_url") or SUNO_CALLBACK_URL
    if not callback:
        return {"error": "callback_url required (in manifest, parameter, or SUNO_CALLBACK_URL env var)"}

    model = settings.get("model", "V5")
    custom_mode = settings.get("custom_mode", True)

    # Build payloads
    payloads = []
    all_warnings = []
    for i, track_dict in enumerate(resolved_tracks):
        fields = fields_dict_to_parsed(track_dict)
        merge_unhinged_seed_into_lyrics(fields)
        instrumental = detect_instrumental(fields, settings.get("instrumental"))
        warnings = validate_limits(fields, model, instrumental, custom_mode)
        if warnings:
            all_warnings.append({"track_index": i + 1, "warnings": warnings})
        payload = build_payload(fields, model, callback, instrumental, custom_mode)
        payloads.append(payload)

    result = {
        "track_count": len(payloads),
        "model": model,
        "warnings": all_warnings,
        "payloads": payloads,
    }

    # Fire if requested
    if fire:
        fired = []
        for i, p in enumerate(payloads, 1):
            if i > 1:
                time.sleep(SAFE_INTERVAL)
            response = fire_request(p, SUNO_API_KEY, SUNO_BASE_URL)
            task_id = None
            if response.get("code") == 200 and isinstance(response.get("data"), dict):
                task_id = response["data"].get("taskId")
            fired.append({
                "track_index": i,
                "title": p.get("title"),
                "task_id": task_id,
                "response": response,
            })
        result["fired"] = fired
        result["task_ids"] = [f["task_id"] for f in fired if f["task_id"]]

    return result


@mcp.tool()
def extend_track(
    task_id: str,
    audio_id: str,
    prompt: str = "",
    style: str = "",
    title: str = "",
    continue_at: int = 0,
    model: str = "V5",
    callback_url: str = "",
) -> dict:
    """Extend an existing generated track with additional content.

    Args:
        task_id: The original task_id whose track will be extended.
        audio_id: The audio_id of the specific track variant to extend (each task generates 2).
        prompt: Optional lyrics for the extension. Leave empty to continue current style.
        style: Optional style override for the extension.
        title: Optional title for the extended track.
        continue_at: Seconds into the original to start extending from. 0 = continue from end.
        model: Model to use for the extension.
        callback_url: Callback URL. Falls back to SUNO_CALLBACK_URL env var.

    Returns:
        Dict with new task_id and response.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    callback = callback_url or SUNO_CALLBACK_URL
    if not callback:
        return {"error": "callback_url required"}

    payload = {
        "audioId": audio_id,
        "taskId": task_id,
        "model": model,
        "callBackUrl": callback,
        "continueAt": continue_at,
    }
    if prompt:
        payload["prompt"] = prompt
    if style:
        payload["style"] = style
    if title:
        payload["title"] = title

    response = _post("/api/v1/extend", payload)
    new_task_id = None
    if response.get("code") == 200 and isinstance(response.get("data"), dict):
        new_task_id = response["data"].get("taskId")

    return {
        "new_task_id": new_task_id,
        "original_task_id": task_id,
        "original_audio_id": audio_id,
        "response": response,
    }


@mcp.tool()
def generate_lyrics(prompt: str, callback_url: str = "") -> dict:
    """Generate lyrics independently of music. Useful for prepping lyrics before generation.

    Args:
        prompt: Short description of the desired lyrical content. Max ~200 chars works best.
        callback_url: Callback URL. Falls back to SUNO_CALLBACK_URL env var.

    Returns:
        Dict with task_id; poll separately for the actual lyrics output.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    callback = callback_url or SUNO_CALLBACK_URL
    if not callback:
        return {"error": "callback_url required"}

    response = _post(
        "/api/v1/generate-lyrics",
        {"prompt": prompt, "callBackUrl": callback},
    )
    task_id = None
    if response.get("code") == 200 and isinstance(response.get("data"), dict):
        task_id = response["data"].get("taskId")

    return {"task_id": task_id, "response": response}


@mcp.tool()
def clone_voice_validate(callback_url: str = "") -> dict:
    """Start the voice cloning workflow by requesting a verification phrase.

    Voice cloning (v5/v5.5 only) requires the source person to record a specific
    verification phrase to prove consent. This tool initiates that workflow.

    Args:
        callback_url: Callback URL where Suno will send the phrase. Falls back to SUNO_CALLBACK_URL.

    Returns:
        Dict with task_id; poll the result to get the verification phrase.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    callback = callback_url or SUNO_CALLBACK_URL
    if not callback:
        return {"error": "callback_url required"}

    response = _post("/api/v1/suno-voice-validate", {"callBackUrl": callback})
    return {
        "task_id": response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None,
        "next_step": (
            "Wait for the verification phrase via callback, then have the source person record "
            "themselves saying that phrase + a sample of their natural voice. Then call clone_voice_create."
        ),
        "response": response,
    }


@mcp.tool()
def clone_voice_create(
    audio_url: str,
    task_id: str,
    callback_url: str = "",
) -> dict:
    """Create a voice clone from a verification recording.

    Call this after clone_voice_validate and after the source person has recorded the
    verification phrase + natural voice sample. The audio_url should be a publicly
    accessible URL to that recording (upload via the file-upload endpoints first if needed).

    Args:
        audio_url: Public URL to the recording (the verification phrase + natural voice).
        task_id: The task_id from clone_voice_validate (links the recording to the verification).
        callback_url: Callback URL where the new voiceId will be sent.

    Returns:
        Dict with new task_id; poll for the resulting voiceId.
    """
    err = _require_api_key()
    if err:
        return {"error": err}

    callback = callback_url or SUNO_CALLBACK_URL
    if not callback:
        return {"error": "callback_url required"}

    response = _post(
        "/api/v1/suno-voice-generate",
        {
            "audioUrl": audio_url,
            "taskId": task_id,
            "callBackUrl": callback,
        },
    )
    return {
        "task_id": response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None,
        "next_step": (
            "Wait for the voiceId via callback. Once you have it, pass it as `personaId` with "
            "`personaModel='voice_persona'` in generate_song to sing in that voice. "
            "Voice clones only work with V5 or V5_5 models."
        ),
        "response": response,
    }


@mcp.tool()
def check_credits() -> dict:
    """Check remaining API credits on the sunoapi.org account.

    Returns:
        Dict with credit balance (when supported by the API provider).
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    result = _get("/api/v1/get-remaining-credits")
    if result.get("status") == 404 or result.get("code") == 404:
        return {
            "available": "unknown",
            "note": (
                "The credits endpoint is not exposed by this sunoapi.org instance. "
                "Generation works; credit queries are provider-dependent. "
                "Check your dashboard at https://sunoapi.org directly."
            ),
        }
    return result


# --- Advanced audio editing (v2.0 Phase C) ---


@mcp.tool()
def separate_stems(task_id: str, track_index: int = 0) -> dict:
    """Separate vocals from instruments for a completed track.

    Args:
        task_id: The task_id of the completed track to process.
        track_index: Which variant to process (0 or 1, since Suno returns 2 tracks).

    Returns:
        Dict with new task_id for the stem separation job.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/separate-vocals", {
        "taskId": task_id,
        "trackIndex": track_index,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    new_task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": new_task_id, "response": response}


@mcp.tool()
def replace_section(task_id: str, section_type: str, new_lyrics: str) -> dict:
    """Replace a specific section in a generated track with new lyrics.

    Args:
        task_id: The task_id of the track to edit.
        section_type: Section to replace — e.g., "verse", "chorus", "bridge".
        new_lyrics: The new lyrics for that section.

    Returns:
        Dict with new task_id for the edited track.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/replace-section", {
        "taskId": task_id,
        "sectionType": section_type,
        "newLyrics": new_lyrics,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    new_task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": new_task_id, "response": response}


@mcp.tool()
def boost_style(task_id: str, target_style: str) -> dict:
    """Strengthen style adherence on an existing generated track.

    Args:
        task_id: The task_id of the track to enhance.
        target_style: The style direction to boost toward.

    Returns:
        Dict with new task_id for the boosted track.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/boost-style", {
        "taskId": task_id,
        "targetStyle": target_style,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    new_task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": new_task_id, "response": response}


@mcp.tool()
def convert_to_wav(task_id: str) -> dict:
    """Convert a generated track's MP3 output to WAV format.

    Args:
        task_id: The task_id of the track to convert.

    Returns:
        Dict with new task_id for the conversion job.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/convert-to-wav", {
        "taskId": task_id,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    new_task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": new_task_id, "response": response}


@mcp.tool()
def create_music_video(task_id: str) -> dict:
    """Generate a music video from a completed track.

    Args:
        task_id: The task_id of the track to visualize.

    Returns:
        Dict with new task_id for the video generation job.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/create-music-video", {
        "taskId": task_id,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    new_task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": new_task_id, "response": response}


@mcp.tool()
def generate_sounds(prompt: str, duration: int = 5, model: str = "V5") -> dict:
    """Generate non-musical sound effects from a text description.

    Args:
        prompt: Description of the desired sound (e.g., "thunderstorm with distant wolves").
        duration: Length in seconds. Default 5.
        model: Model to use. Default V5.

    Returns:
        Dict with task_id for the sound generation job.
    """
    err = _require_api_key()
    if err:
        return {"error": err}
    response = _post("/api/v1/generate-sounds", {
        "prompt": prompt,
        "duration": duration,
        "model": model,
        "callBackUrl": SUNO_CALLBACK_URL or "https://localhost/callback",
    })
    task_id = response.get("data", {}).get("taskId") if isinstance(response.get("data"), dict) else None
    return {"task_id": task_id, "response": response}


@mcp.tool()
def list_endpoints() -> dict:
    """List all Suno API endpoints available via sunoapi.org with brief descriptions.

    Useful when you need to know what's possible. Not all are exposed as MCP tools —
    refer to references/api-integration.md in this skill for full payload details.

    Returns:
        Dict with categorized endpoint list.
    """
    return {
        "music_generation": {
            "POST /api/v1/generate": "Generate new music (handled by generate_song tool)",
            "POST /api/v1/extend": "Extend a track (handled by extend_track tool)",
            "POST /api/v1/upload-and-cover": "Upload audio and generate a cover",
            "POST /api/v1/upload-and-extend": "Upload audio and extend it",
            "POST /api/v1/add-instrumental": "Add instrumental layers to a vocal-only base",
            "POST /api/v1/add-vocals": "Add vocals to an instrumental base",
            "GET /api/v1/get-music-details": "Poll task status (handled by check_status)",
            "POST /api/v1/get-timestamped-lyrics": "Retrieve timed lyric data",
            "POST /api/v1/boost-style": "Strengthen style adherence on an existing track",
            "POST /api/v1/cover-suno": "Generate a cover via Suno's Cover feature",
            "POST /api/v1/replace-section": "Swap a specific section in a generated track",
            "POST /api/v1/generate-persona": "Create a persona from an existing track",
            "POST /api/v1/generate-mashup": "Generate a mashup of two tracks",
        },
        "suno_voice_v5_v5_5_only": {
            "POST /api/v1/suno-voice-validate": "Generate verification phrase (handled by clone_voice_validate)",
            "POST /api/v1/suno-voice-generate": "Create voice clone (handled by clone_voice_create)",
            "GET /api/v1/suno-voice-record-info": "Get voice record details",
            "POST /api/v1/suno-voice-check-voice": "Check voice availability",
        },
        "lyrics": {
            "POST /api/v1/generate-lyrics": "Generate lyrics only (handled by generate_lyrics tool)",
        },
        "post_processing": {
            "POST /api/v1/convert-to-wav": "Convert MP3 to WAV",
            "POST /api/v1/separate-vocals": "Stem separation (vocals from instruments)",
            "POST /api/v1/generate-midi": "Generate MIDI from audio",
        },
        "music_video": {
            "POST /api/v1/create-music-video": "Generate a music video from a track",
        },
        "account": {
            "GET /api/v1/get-remaining-credits": "Check credit balance (handled by check_credits)",
        },
        "file_upload": {
            "POST /api/v1/upload-base64": "Upload a file as base64",
            "POST /api/v1/upload-stream": "Upload a file as stream",
            "POST /api/v1/upload-url": "Upload a file from a URL",
        },
        "documentation_url": "https://docs.sunoapi.org/",
    }


# --- Resources (read-only context for the AI) ---


@mcp.resource("suno://models")
def list_models() -> str:
    """Returns the list of available Suno models with their character limits."""
    return json.dumps({
        model: limits
        for model, limits in MODEL_LIMITS.items()
    }, indent=2)


@mcp.resource("suno://config")
def get_config() -> str:
    """Returns the current MCP server configuration (with API key redacted)."""
    return json.dumps({
        "base_url": SUNO_BASE_URL,
        "callback_url": SUNO_CALLBACK_URL or "(not set)",
        "download_dir": str(SUNO_DOWNLOAD_DIR.absolute()),
        "api_key": "(set)" if SUNO_API_KEY else "(not set — required for most tools)",
    }, indent=2)


# --- Prompts ---


@mcp.prompt()
def song_prompt_template(genre: str, mood: str = "", instrumental: bool = False) -> str:
    """Generate a starter Suno field-labeled prompt for a given genre and mood.

    Use this as a starting point when composing a generate_song call.
    """
    inst_note = "instrumental — use symbols/kaomoji for lyrics field" if instrumental else "vocal song — write real lyrics"
    return f"""Compose a Suno prompt for: {genre}{f', mood: {mood}' if mood else ''} ({inst_note})

Build these fields:

STYLES: 
  [genre + 2-3 specific descriptors + 1 BPM/key/tuning param]

EXCLUDE_STYLES:
  [things that would clash with the genre]

LYRICS:
  [{'symbol-based instrumental content with section tags' if instrumental else 'real lyrics with [Verse]/[Chorus] structure'}]

WEIRDNESS_%: [25-75 depending on how experimental]
STYLE_%: [opposite of weirdness usually]

UNHINGED_SEED: [optional short ironic concept block]

When ready, call generate_song with the field values."""


# --- Entry point ---


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport: stdio (default, for Claude Desktop) or sse (HTTP for remote clients)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host for SSE transport")
    parser.add_argument("--port", type=int, default=8765, help="Port for SSE transport")
    args = parser.parse_args()

    if not SUNO_API_KEY:
        print(
            "WARNING: SUNO_API_KEY not set. Tools requiring API access will return errors. "
            "Set it before connecting clients.",
            file=sys.stderr,
        )

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
