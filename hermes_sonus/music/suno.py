"""
Suno API Client for Hermes Music Plugin — v2.0 Thin Adapter.

Delegates payload construction, validation, and polling to the MCP layer
(hermes_sonus.mcp.*). Uses requests for HTTP to stay consistent with the
existing plugin stack.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False
    RetryError = Exception  # type: ignore[misc,assignment]

from hermes_sonus.mcp.build_payload import (
    ParsedFields,
    build_payload,
    merge_unhinged_seed_into_lyrics,
    validate_limits,
    MODEL_LIMITS,
)
from hermes_sonus.mcp.poll_status import (
    extract_audio_urls,
    extract_status,
    poll_loop,
)

__all__ = [
    "MODEL_LIMITS",
    "submit_generation",
    "poll_completion",
    "download_audio",
    "upload_audio",
    "submit_upload_cover",
    "submit_extend",
    "submit_lyrics",
    "clone_voice_validate",
    "clone_voice_create",
    "check_credits",
]

logger = logging.getLogger(__name__)

SUNO_API_BASE = "https://api.sunoapi.org/api/v1"


def _get_api_key() -> str:
    key = os.environ.get("SUNO_API_KEY", "")
    if not key:
        raise ValueError(
            "SUNO_API_KEY not set. Get one at https://sunoapi.org "
            "and add it to ~/.hermes/.env"
        )
    return key


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _api_call(method: str, url: str, **kwargs) -> requests.Response:
    """Make an API call with optional tenacity retry."""
    kwargs.setdefault("timeout", 30)
    if HAS_TENACITY:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
        )
        def _call():
            return requests.request(method, url, **kwargs)
        return _call()
    return requests.request(method, url, **kwargs)


def _extract_task_id(result: Dict[str, Any]) -> str:
    if result.get("code") == 200 and isinstance(result.get("data"), dict):
        tid = result["data"].get("taskId")
        if tid:
            return str(tid)
    raise ValueError(f"No taskId in response: {result.get('msg', result)}")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def submit_generation(
    prompt: str,
    style: str = "",
    title: str = "",
    model: str = "V5",
    is_instrumental: bool = True,
    exclude_styles: str = "",
    weirdness_pct: Optional[float] = None,
    style_pct: Optional[float] = None,
    vocal_gender: str = "",
    persona_id: str = "",
    persona_model: str = "",
) -> str:
    """Submit a generation request to Suno. Returns the suno_task_id."""
    fields = ParsedFields()
    fields.styles = style or None
    fields.lyrics = prompt or None
    fields.title = title or None
    fields.exclude_styles = exclude_styles or None
    fields.weirdness_pct = weirdness_pct
    fields.style_pct = style_pct
    fields.vocal_gender = vocal_gender.lower() if vocal_gender else None
    fields.persona_id = persona_id or None
    fields.persona_model = persona_model or None

    merge_unhinged_seed_into_lyrics(fields)
    warnings = validate_limits(fields, model, is_instrumental, custom_mode=True)
    if warnings:
        logger.warning("Validation warnings: %s", warnings)

    payload = build_payload(
        fields,
        model,
        callback_url="https://localhost/callback",
        instrumental=is_instrumental,
        custom_mode=True,
    )

    logger.info("Submitting to Suno: model=%s, instrumental=%s", model, is_instrumental)
    response = _api_call("POST", f"{SUNO_API_BASE}/generate", headers=_headers(), json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise ValueError(f"Suno API error: {result.get('msg', 'Unknown error')}")

    task_id = _extract_task_id(result)
    logger.info("Suno task submitted: %s", task_id)
    return task_id


def poll_completion(suno_task_id: str, max_wait: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
    """Poll Suno for generation completion. Returns tracks info on success."""
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    start_time = __import__("time").time()

    while __import__("time").time() - start_time < max_wait:
        try:
            response = _api_call(
                "GET",
                f"{SUNO_API_BASE}/get-music-details",
                headers=headers,
                params={"taskId": suno_task_id},
                timeout=10,
            )
            if response.status_code != 200:
                __import__("time").sleep(poll_interval)
                continue

            result = response.json()
            status = extract_status(result)

            if status == "complete":
                tracks = extract_audio_urls(result)
                if tracks:
                    return {
                        "success": True,
                        "tracks": [
                            {
                                "audio_url": t["audio_url"],
                                "title": t.get("title", ""),
                                "duration": t.get("duration", 0),
                                "clip_id": t.get("id", ""),
                            }
                            for t in tracks
                        ],
                    }
                return {"success": False, "error": "No audio data in completed response"}

            if status in {"error", "failed", "cancelled", "expired"}:
                return {"success": False, "error": f"Suno generation failed: {status}"}

        except Exception:
            pass

        __import__("time").sleep(poll_interval)

    return {"success": False, "error": f"Generation timed out after {max_wait}s"}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_audio(audio_url: str, output_path: str) -> str:
    """Download audio from URL to local path. Returns the output path."""
    response = _api_call("GET", audio_url, headers={}, timeout=60, stream=True)
    response.raise_for_status()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info("Downloaded audio to %s", output_path)
    return str(output)


# ---------------------------------------------------------------------------
# Upload & Cover
# ---------------------------------------------------------------------------

def upload_audio(file_path: str) -> Dict[str, Any]:
    """Upload audio file to Suno for use as composition reference."""
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    with open(file_path, "rb") as f:
        response = _api_call(
            "POST",
            f"{SUNO_API_BASE}/upload-audio",
            headers=headers,
            files={"file": (Path(file_path).name, f, "audio/mpeg")},
            timeout=60,
        )
    if response.status_code != 200:
        return {"success": False, "error": f"Upload HTTP {response.status_code}: {response.text[:200]}"}
    result = response.json()
    if result.get("code") != 200:
        return {"success": False, "error": f"Upload error: {result.get('msg', 'Unknown')}"}
    upload_url = result.get("data", {}).get("audioUrl")
    if not upload_url:
        return {"success": False, "error": "No audioUrl in upload response"}
    return {"success": True, "upload_url": upload_url}


def submit_upload_cover(
    upload_url: str,
    style: str,
    title: str,
    prompt: str = "",
    instrumental: bool = True,
    audio_weight: float = 0.5,
    style_weight: float = 0.5,
    weirdness: float = 0.3,
    model: str = "V5",
) -> Dict[str, Any]:
    """Submit an upload-cover request (MIDI composition pipeline). Returns suno_task_id."""
    payload = {
        "audioUrl": upload_url,
        "model": model,
        "instrumental": instrumental,
        "customMode": True,
        "style": style,
        "title": title,
        "audioWeight": audio_weight,
        "styleWeight": style_weight,
        "weirdness": weirdness,
        "callBackUrl": "https://localhost/callback",
    }
    if prompt:
        payload["prompt"] = prompt

    response = _api_call("POST", f"{SUNO_API_BASE}/upload-cover", headers=_headers(), json=payload)
    if response.status_code != 200:
        return {"success": False, "error": f"Upload-cover HTTP {response.status_code}: {response.text[:200]}"}
    result = response.json()
    if result.get("code") != 200:
        return {"success": False, "error": f"Upload-cover error: {result.get('msg', 'Unknown')}"}
    return {"success": True, "suno_task_id": _extract_task_id(result)}


# ---------------------------------------------------------------------------
# Extended endpoints (v2.0)
# ---------------------------------------------------------------------------

def submit_extend(
    task_id: str,
    audio_id: str,
    prompt: str = "",
    style: str = "",
    title: str = "",
    continue_at: int = 0,
    model: str = "V5",
) -> str:
    """Extend an existing track. Returns new task_id."""
    payload = {
        "audioId": audio_id,
        "taskId": task_id,
        "model": model,
        "callBackUrl": "https://localhost/callback",
        "continueAt": continue_at,
    }
    if prompt:
        payload["prompt"] = prompt
    if style:
        payload["style"] = style
    if title:
        payload["title"] = title

    response = _api_call("POST", f"{SUNO_API_BASE}/extend", headers=_headers(), json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise ValueError(f"Extend error: {result.get('msg', 'Unknown error')}")
    return _extract_task_id(result)


def submit_lyrics(prompt: str) -> str:
    """Generate lyrics independently. Returns task_id."""
    payload = {
        "prompt": prompt,
        "callBackUrl": "https://localhost/callback",
    }
    response = _api_call("POST", f"{SUNO_API_BASE}/generate-lyrics", headers=_headers(), json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise ValueError(f"Lyrics error: {result.get('msg', 'Unknown error')}")
    return _extract_task_id(result)


def clone_voice_validate() -> str:
    """Start voice cloning workflow. Returns task_id."""
    payload = {"callBackUrl": "https://localhost/callback"}
    response = _api_call("POST", f"{SUNO_API_BASE}/suno-voice-validate", headers=_headers(), json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise ValueError(f"Voice validate error: {result.get('msg', 'Unknown error')}")
    return _extract_task_id(result)


def clone_voice_create(audio_url: str, task_id: str) -> str:
    """Create voice clone from recording. Returns task_id."""
    payload = {
        "audioUrl": audio_url,
        "taskId": task_id,
        "callBackUrl": "https://localhost/callback",
    }
    response = _api_call("POST", f"{SUNO_API_BASE}/suno-voice-generate", headers=_headers(), json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise ValueError(f"Voice create error: {result.get('msg', 'Unknown error')}")
    return _extract_task_id(result)


def check_credits() -> Dict[str, Any]:
    """Check remaining API credits."""
    response = _api_call("GET", f"{SUNO_API_BASE}/get-remaining-credits", headers=_headers())
    response.raise_for_status()
    return response.json()
