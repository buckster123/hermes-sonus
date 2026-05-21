#!/usr/bin/env python3
"""
poll_status.py — Poll the sunoapi.org task-status endpoint until generation completes.

Suno's generate endpoint returns immediately with a taskId. Audio takes 30s-3min to be
ready. This script polls GET /api/v1/get-music-details until status hits a terminal
state, with exponential backoff between polls.

Optionally downloads the final audio files (Suno returns 2 variants per task) to disk
when complete.

Usage:
    python poll_status.py --task-id 5c79be8e --api-key $SUNO_API_KEY
    python poll_status.py -t 5c79be8e -k $SUNO_API_KEY --wait --download ./audio/
    python poll_status.py -t 5c79be8e -k $SUNO_API_KEY --once

Doesn't require the request that created the task — only the taskId. So you can fire
your generate request via any means (curl, build_payload.py | curl, custom client) and
hand off the taskId to this script for the wait-and-download phase.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Default sunoapi.org details endpoint. Override with --base-url for alt wrappers.
DEFAULT_BASE_URL = "https://api.sunoapi.org"
DETAILS_PATH = "/api/v1/generate/record-info"

# Terminal states (stop polling once we hit any of these)
TERMINAL_STATES = {"complete", "error", "failed", "cancelled", "expired"}

# Initial poll interval and cap for exponential backoff
INITIAL_POLL_INTERVAL = 5.0   # seconds
MAX_POLL_INTERVAL = 30.0
BACKOFF_FACTOR = 1.5
DEFAULT_TIMEOUT = 600  # 10 minutes — Suno generation is usually 30s-3min


def fetch_status(base_url: str, task_id: str, api_key: str) -> dict:
    """Single status fetch. Returns parsed JSON response."""
    url = f"{base_url.rstrip('/')}{DETAILS_PATH}?taskId={task_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        return {
            "code": e.code,
            "msg": f"HTTP {e.code}: {e.reason}",
            "data": None,
            "_error": True,
        }
    except urllib.error.URLError as e:
        return {
            "code": 0,
            "msg": f"Connection error: {e.reason}",
            "data": None,
            "_error": True,
        }


def extract_status(response: dict) -> str:
    """Best-effort status extraction from response. Returns lowercased status string."""
    if response.get("_error"):
        return "error"
    data = response.get("data") or {}
    # sunoapi.org wraps the actual task data in different shapes depending on stage.
    # Common patterns: data.status, data.response.status, data.callbackType
    for key in ("status", "callbackType", "state"):
        if key in data and data[key]:
            return str(data[key]).lower().strip()
    # Nested response (e.g., when a track has actually been generated)
    response_inner = data.get("response") if isinstance(data, dict) else None
    if isinstance(response_inner, dict):
        for key in ("status", "callbackType", "state"):
            if key in response_inner and response_inner[key]:
                return str(response_inner[key]).lower().strip()
    # If we have audio URLs, treat it as complete
    if extract_audio_urls(response):
        return "complete"
    return "pending"


def extract_audio_urls(response: dict) -> list[dict]:
    """Pull audio URLs and metadata from a completed response. Returns list of track dicts."""
    if response.get("_error"):
        return []
    data = response.get("data") or {}
    # Common locations for the tracks array
    tracks = []
    for path in [
        ("response", "sunoData"),
        ("response", "data"),
        ("sunoData",),
        ("tracks",),
        ("data",),
    ]:
        cursor = data
        for segment in path:
            if isinstance(cursor, dict) and segment in cursor:
                cursor = cursor[segment]
            else:
                cursor = None
                break
        if isinstance(cursor, list):
            tracks = cursor
            break
    # Normalize each track entry
    result = []
    for t in tracks:
        if not isinstance(t, dict):
            continue
        audio_url = (
            t.get("audioUrl")
            or t.get("audio_url")
            or t.get("streamAudioUrl")
            or t.get("stream_audio_url")
            or t.get("sourceAudioUrl")
        )
        if audio_url:
            result.append(
                {
                    "id": t.get("id") or t.get("audioId") or t.get("trackId"),
                    "title": t.get("title", ""),
                    "audio_url": audio_url,
                    "image_url": t.get("imageUrl") or t.get("image_url"),
                    "duration": t.get("duration"),
                    "tags": t.get("tags") or t.get("style"),
                }
            )
    return result


def download_track(track: dict, output_dir: Path, task_id: str, index: int) -> Path | None:
    """Download a single track's audio file. Returns the path on success, None on failure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # Build a safe filename
    title = (track.get("title") or "").strip()
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:60]
    safe_title = safe_title.strip().replace(" ", "_") or f"track_{index}"
    # Audio URL usually .mp3; preserve extension if present
    audio_url = track["audio_url"]
    ext = ".mp3"
    for candidate in (".mp3", ".wav", ".ogg", ".m4a"):
        if candidate in audio_url.lower():
            ext = candidate
            break
    filename = f"{task_id[:12]}__{index}__{safe_title}{ext}"
    out_path = output_dir / filename
    try:
        print(f"  downloading track {index}: {audio_url}", file=sys.stderr)
        with urllib.request.urlopen(audio_url, timeout=120) as resp:
            with open(out_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        print(f"  saved: {out_path}", file=sys.stderr)
        return out_path
    except Exception as e:
        print(f"  download failed: {e}", file=sys.stderr)
        return None


def poll_loop(
    base_url: str,
    task_id: str,
    api_key: str,
    timeout: int,
    verbose: bool,
) -> dict:
    """Poll until terminal state or timeout. Returns the final response dict."""
    start = time.time()
    interval = INITIAL_POLL_INTERVAL
    iteration = 0
    last_status = None

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            return {
                "_error": True,
                "code": 408,
                "msg": f"Polling timeout after {timeout}s",
                "data": None,
            }

        iteration += 1
        response = fetch_status(base_url, task_id, api_key)
        status = extract_status(response)

        if verbose or status != last_status:
            elapsed_s = int(elapsed)
            print(
                f"[poll #{iteration}, t+{elapsed_s}s] status={status}",
                file=sys.stderr,
            )
            last_status = status

        if status in TERMINAL_STATES:
            return response

        # Sleep with backoff
        time.sleep(interval)
        interval = min(interval * BACKOFF_FACTOR, MAX_POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task-id", "-t", required=True, help="Task ID from generate response")
    parser.add_argument(
        "--api-key",
        "-k",
        default=os.environ.get("SUNO_API_KEY"),
        help="API key (or set SUNO_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SUNO_BASE_URL", DEFAULT_BASE_URL),
        help=f"API base URL (default: {DEFAULT_BASE_URL}; or SUNO_BASE_URL env var)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single status check, no polling (overrides --wait)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        default=True,
        help="Poll until completion (default behavior)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Max wait time in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--download",
        metavar="DIR",
        help="Download audio files to DIR after completion",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log every poll iteration (default: only status changes)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: --api-key required (or set SUNO_API_KEY env var)", file=sys.stderr)
        sys.exit(2)

    # Single-shot or polled
    if args.once:
        response = fetch_status(args.base_url, args.task_id, args.api_key)
    else:
        response = poll_loop(
            args.base_url, args.task_id, args.api_key, args.timeout, args.verbose
        )

    # Optional download
    if args.download and not response.get("_error"):
        tracks = extract_audio_urls(response)
        if tracks:
            print(f"\n{len(tracks)} track(s) ready for download:", file=sys.stderr)
            output_dir = Path(args.download)
            paths = []
            for i, track in enumerate(tracks, 1):
                path = download_track(track, output_dir, args.task_id, i)
                if path:
                    paths.append(str(path))
            response["_downloaded"] = paths
        else:
            print("No audio URLs found in response — nothing to download.", file=sys.stderr)

    # Emit response
    if args.pretty:
        print(json.dumps(response, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(response, ensure_ascii=False))

    # Exit code reflects success/failure
    if response.get("_error") or extract_status(response) in {"error", "failed", "cancelled", "expired"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
