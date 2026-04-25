"""
Suno API Client for Hermes Music Plugin

Clean wrapper around the sunoapi.org REST API.
Handles submission, polling, audio download, and upload-cover (composition).
"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False
    RetryError = Exception  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

SUNO_API_BASE = "https://api.sunoapi.org/api/v1"

# Model character limits
MODEL_LIMITS = {
    "V3_5": {"prompt": 3000, "style": 200, "title": 80},
    "V4":   {"prompt": 3000, "style": 200, "title": 80},
    "V4_5": {"prompt": 5000, "style": 1000, "title": 100},
    "V5":   {"prompt": 5000, "style": 1000, "title": 100},
}


def _get_api_key() -> str:
    """Get the Suno API key from environment."""
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
    else:
        return requests.request(method, url, **kwargs)


def submit_generation(
    prompt: str,
    style: str = "",
    title: str = "",
    model: str = "V5",
    is_instrumental: bool = True,
) -> str:
    """Submit a generation request to Suno. Returns the suno_task_id."""
    payload = {
        "model": model,
        "instrumental": is_instrumental,
        "customMode": True,
        "prompt": prompt,
        "callBackUrl": "https://localhost/callback",  # Required but unused (we poll)
    }
    if title:
        payload["title"] = title
    if style:
        payload["style"] = style

    logger.info("Submitting to Suno: model=%s, instrumental=%s", model, is_instrumental)

    response = _api_call("POST", f"{SUNO_API_BASE}/generate", headers=_headers(), json=payload)

    if response.status_code != 200:
        raise Exception(f"Suno API HTTP {response.status_code}: {response.text[:200]}")

    result = response.json()
    if result.get("code") != 200:
        raise Exception(f"Suno API error: {result.get('msg', 'Unknown error')}")

    suno_task_id = result.get("data", {}).get("taskId")
    if not suno_task_id:
        raise Exception("No taskId in Suno response")

    logger.info("Suno task submitted: %s", suno_task_id)
    return suno_task_id


def poll_completion(suno_task_id: str, max_wait: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
    """Poll Suno for generation completion. Returns tracks info on success."""
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            response = _api_call(
                "GET",
                f"{SUNO_API_BASE}/generate/record-info",
                headers=headers,
                params={"taskId": suno_task_id},
                timeout=10,
            )

            if response.status_code != 200:
                logger.warning("Status check HTTP %d", response.status_code)
                time.sleep(poll_interval)
                continue

            result = response.json()
            if result.get("code") != 200:
                logger.warning("Status API error: %s", result.get("msg"))
                time.sleep(poll_interval)
                continue

            data = result.get("data", {})
            status = data.get("status", "UNKNOWN")

            if status == "SUCCESS":
                suno_data = data.get("response", {}).get("sunoData", [])
                if suno_data:
                    tracks = []
                    for track in suno_data:
                        tracks.append({
                            "audio_url": track.get("audioUrl"),
                            "title": track.get("title"),
                            "duration": track.get("duration", 0),
                            "clip_id": track.get("id"),
                        })
                    return {"success": True, "tracks": tracks}
                return {"success": False, "error": "No audio data in completed response"}

            elif status == "FAILED":
                error_msg = data.get("response", {}).get("errorMessage", "Unknown failure")
                return {"success": False, "error": f"Suno generation failed: {error_msg}"}

            # Still in progress
            logger.debug("Suno status: %s", status)

        except (requests.RequestException, RetryError) as e:
            logger.warning("Poll error (will retry): %s", e)

        time.sleep(poll_interval)

    return {"success": False, "error": f"Generation timed out after {max_wait}s"}


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


def upload_audio(file_path: str) -> Dict[str, Any]:
    """Upload audio file to Suno for use as composition reference. Returns upload info."""
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

    suno_task_id = result.get("data", {}).get("taskId")
    if not suno_task_id:
        return {"success": False, "error": "No taskId in upload-cover response"}

    return {"success": True, "suno_task_id": suno_task_id}
