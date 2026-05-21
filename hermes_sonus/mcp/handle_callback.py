#!/usr/bin/env python3
"""
handle_callback.py — FastAPI scaffold for receiving Suno's async generation callbacks.

When you POST to /api/v1/generate with a callBackUrl, Suno sends three sequential
callbacks to that URL as generation progresses:

  1. `text`     — text/lyric generation complete
  2. `first`    — first track variant complete (audio available)
  3. `complete` — all tracks complete (Suno returns 2 variants per task)

This script provides a minimal but production-shaped FastAPI server that:

  - Accepts callbacks at POST /suno/callback
  - Validates the payload shape
  - Persists each callback to a configurable directory as JSON
  - Optionally downloads audio files when 'first' or 'complete' callbacks arrive
  - Optionally forwards callbacks to a user-defined webhook URL
  - Exposes GET /tasks/{taskId} for inspecting received callbacks for a given task

Run:
    pip install fastapi uvicorn
    python handle_callback.py --port 8000 --output-dir ./callbacks/

Or via uvicorn directly:
    uvicorn handle_callback:app --host 0.0.0.0 --port 8000

Then point your generate request's callBackUrl at: http://YOUR_HOST:8000/suno/callback

Environment variables (alternative to flags when running via uvicorn):
    SUNO_CALLBACK_OUTPUT_DIR   — directory to write callbacks (default: ./callbacks)
    SUNO_CALLBACK_DOWNLOAD     — "1" to auto-download audio (default: off)
    SUNO_CALLBACK_FORWARD_URL  — optional URL to forward callbacks to
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError:
    print("ERROR: fastapi not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(2)


# --- Configuration via env vars (allows running with `uvicorn handle_callback:app`) ---
OUTPUT_DIR = Path(os.environ.get("SUNO_CALLBACK_OUTPUT_DIR", "./callbacks"))
AUTO_DOWNLOAD = os.environ.get("SUNO_CALLBACK_DOWNLOAD", "").strip() in {"1", "true", "yes"}
FORWARD_URL = os.environ.get("SUNO_CALLBACK_FORWARD_URL", "").strip() or None

# Known callback types (from sunoapi.org docs)
KNOWN_CALLBACK_TYPES = {"text", "first", "complete", "error"}


app = FastAPI(
    title="Suno Callback Handler",
    description="Receives async generation callbacks from Suno API",
    version="1.0.0",
)


# --- Helpers ---


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_dir(task_id: str) -> Path:
    """Return the directory for a given task's callbacks, creating it if needed."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)[:64]
    d = OUTPUT_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_task_id(payload: dict) -> str | None:
    """Best-effort task ID extraction. Sunoapi.org puts it at data.task_id or data.taskId."""
    data = payload.get("data") or {}
    for key in ("task_id", "taskId", "id"):
        if isinstance(data, dict) and key in data and data[key]:
            return str(data[key])
    for key in ("task_id", "taskId"):
        if key in payload and payload[key]:
            return str(payload[key])
    return None


def extract_callback_type(payload: dict) -> str | None:
    """Pull the callbackType field (text/first/complete) from common locations."""
    data = payload.get("data") or {}
    for key in ("callbackType", "callback_type", "type"):
        if isinstance(data, dict) and key in data and data[key]:
            return str(data[key]).lower().strip()
    return payload.get("callbackType") or payload.get("type")


def extract_tracks(payload: dict) -> list[dict]:
    """Extract track-level data (audio URLs etc.) from a 'first' or 'complete' callback."""
    data = payload.get("data") or {}
    tracks = []
    # Common paths where sunoapi.org puts the track list
    for path in [
        ("data",),
        ("sunoData",),
        ("response", "sunoData"),
        ("response", "data"),
        ("tracks",),
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
    return [t for t in tracks if isinstance(t, dict)]


def download_audio(track: dict, dest_dir: Path) -> Path | None:
    """Download an audio URL to dest_dir. Returns path on success."""
    audio_url = (
        track.get("audioUrl")
        or track.get("audio_url")
        or track.get("streamAudioUrl")
        or track.get("sourceAudioUrl")
    )
    if not audio_url:
        return None
    title = (track.get("title") or "").strip()
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:60].strip().replace(" ", "_") or "track"
    track_id = (track.get("id") or track.get("audioId") or str(int(time.time())))[:12]
    ext = ".mp3"
    for candidate in (".mp3", ".wav", ".ogg", ".m4a"):
        if candidate in audio_url.lower():
            ext = candidate
            break
    out_path = dest_dir / f"{track_id}__{safe_title}{ext}"
    try:
        with urllib.request.urlopen(audio_url, timeout=120) as resp:
            with open(out_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        return out_path
    except Exception as e:
        print(f"download failed for {audio_url}: {e}", file=sys.stderr)
        return None


async def forward_callback(payload: dict) -> None:
    """Forward callback to user-configured webhook. Fire-and-forget; logs failures."""
    if not FORWARD_URL:
        return
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            FORWARD_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"forward to {FORWARD_URL} failed: {e}", file=sys.stderr)


# --- Routes ---


@app.get("/")
async def index():
    return {
        "service": "suno-callback-handler",
        "version": "1.0.0",
        "output_dir": str(OUTPUT_DIR.absolute()),
        "auto_download": AUTO_DOWNLOAD,
        "forward_url": FORWARD_URL,
        "endpoints": {
            "POST /suno/callback": "Receive Suno callbacks",
            "GET /tasks/{task_id}": "List callbacks received for a task",
            "GET /tasks/{task_id}/latest": "Most recent callback for a task",
            "GET /healthz": "Health check",
        },
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "timestamp": now_iso()}


@app.post("/suno/callback")
async def receive_callback(request: Request):
    """Accept a Suno generation callback. Persist, optionally download, forward."""
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")

    task_id = extract_task_id(payload)
    if not task_id:
        # Save under "unknown" but still 200 so Suno doesn't retry-spam
        task_id = f"unknown_{int(time.time())}"

    callback_type = extract_callback_type(payload) or "unknown"

    # Persist the raw callback
    dest = task_dir(task_id)
    timestamp = now_iso().replace(":", "-")
    callback_path = dest / f"{timestamp}__{callback_type}.json"
    record = {
        "received_at": now_iso(),
        "callback_type": callback_type,
        "task_id": task_id,
        "payload": payload,
    }
    callback_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))

    # Auto-download audio when applicable
    downloaded: list[str] = []
    if AUTO_DOWNLOAD and callback_type in {"first", "complete"}:
        audio_dir = dest / "audio"
        audio_dir.mkdir(exist_ok=True)
        for track in extract_tracks(payload):
            path = download_audio(track, audio_dir)
            if path:
                downloaded.append(str(path))

    # Optional forward
    await forward_callback(payload)

    return JSONResponse(
        {
            "received": True,
            "task_id": task_id,
            "callback_type": callback_type,
            "saved_to": str(callback_path),
            "downloaded": downloaded if downloaded else None,
        }
    )


@app.get("/tasks/{task_id}")
async def list_task_callbacks(task_id: str):
    """List all callback files received for a given task ID."""
    dest = task_dir(task_id)
    files = sorted(dest.glob("*.json"))
    return {
        "task_id": task_id,
        "callbacks": [
            {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            for f in files
        ],
        "audio_files": [str(p) for p in (dest / "audio").glob("*") if (dest / "audio").exists()],
    }


@app.get("/tasks/{task_id}/latest")
async def latest_task_callback(task_id: str):
    """Return the most recently received callback for a task."""
    dest = task_dir(task_id)
    files = sorted(dest.glob("*.json"))
    if not files:
        raise HTTPException(status_code=404, detail=f"No callbacks received for task {task_id}")
    latest = files[-1]
    return json.loads(latest.read_text())


# --- CLI entrypoint for `python handle_callback.py` ---


def main():
    global OUTPUT_DIR, AUTO_DOWNLOAD, FORWARD_URL

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SUNO_CALLBACK_OUTPUT_DIR", "./callbacks"),
        help="Directory for received callbacks (default: ./callbacks)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Auto-download audio when first/complete callbacks arrive",
    )
    parser.add_argument(
        "--forward",
        metavar="URL",
        help="Forward each callback to this URL (POST)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload for development",
    )
    args = parser.parse_args()

    # Apply CLI args to module-level config
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.download:
        AUTO_DOWNLOAD = True
    if args.forward:
        FORWARD_URL = args.forward

    # Reset via env so reload workers see the same config
    os.environ["SUNO_CALLBACK_OUTPUT_DIR"] = str(OUTPUT_DIR)
    if AUTO_DOWNLOAD:
        os.environ["SUNO_CALLBACK_DOWNLOAD"] = "1"
    if FORWARD_URL:
        os.environ["SUNO_CALLBACK_FORWARD_URL"] = FORWARD_URL

    print(
        f"Suno callback handler listening on {args.host}:{args.port}\n"
        f"  output_dir:   {OUTPUT_DIR.absolute()}\n"
        f"  auto_download: {AUTO_DOWNLOAD}\n"
        f"  forward_url:  {FORWARD_URL or '(none)'}\n"
        f"  callback URL: http://{args.host}:{args.port}/suno/callback",
        file=sys.stderr,
    )

    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
        sys.exit(2)

    uvicorn.run(
        "handle_callback:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
