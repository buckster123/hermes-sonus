#!/usr/bin/env python3
"""Lightweight probe of all Suno API endpoints to verify paths exist.

Sends minimal/empty payloads so we get 400/401/422/500 (route exists)
rather than 404 (route missing). Does NOT charge credits for bad payloads.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hermes_sonus.mcp.http_client import api_post, api_get, SUNO_BASE_URL, SUNO_API_KEY

POST_ENDPOINTS = [
    # (path, minimal_payload, description)
    ("/api/v1/generate", {"prompt": "test", "tags": "test"}, "Generate"),
    ("/api/v1/generate/extend", {"audio_id": "test", "prompt": "test"}, "Extend"),
    ("/api/v1/lyrics", {"prompt": "test"}, "Generate lyrics"),
    ("/api/v1/voice/validate", {"callBackUrl": "http://localhost/test"}, "Voice validate"),
    ("/api/v1/voice/generate", {"audio_id": "test", "callBackUrl": "http://localhost/test"}, "Voice generate"),
    ("/api/v1/vocal-removal/generate", {"audio_id": "test"}, "Vocal removal"),
    ("/api/v1/generate/replace-section", {"audio_id": "test", "section": "intro", "prompt": "test"}, "Replace section"),
    ("/api/v1/style/generate", {"audio_id": "test"}, "Boost style"),
    ("/api/v1/wav/generate", {"audio_id": "test"}, "Convert to WAV"),
    ("/api/v1/mp4/generate", {"audio_id": "test"}, "Create music video"),
    ("/api/v1/generate/sounds", {"prompt": "test"}, "Generate sounds"),
    ("/api/v1/generate/upload-cover", {"audio_url": "http://localhost/test"}, "Upload and cover"),
    ("/api/v1/generate/upload-extend", {"audio_url": "http://localhost/test", "prompt": "test"}, "Upload and extend"),
    ("/api/v1/generate/add-instrumental", {"audio_id": "test"}, "Add instrumental"),
    ("/api/v1/generate/add-vocals", {"audio_id": "test"}, "Add vocals"),
    ("/api/v1/generate/get-timestamped-lyrics", {"audio_id": "test"}, "Timestamped lyrics"),
    ("/api/v1/suno/cover/generate", {"audio_id": "test"}, "Cover Suno"),
    ("/api/v1/generate/generate-persona", {"audio_id": "test"}, "Generate persona"),
    ("/api/v1/generate/mashup", {"audio_ids": ["test1", "test2"]}, "Generate mashup"),
    ("/api/v1/midi/generate", {"audio_id": "test"}, "Generate MIDI"),
    ("/api/file-base64-upload", {"filename": "test.mp3", "data": "dGVzdA=="}, "Upload base64"),
    ("/api/file-stream-upload", {"filename": "test.mp3"}, "Upload stream"),
    ("/api/file-url-upload", {"url": "http://localhost/test"}, "Upload URL"),
    ("/api/v1/voice/check-voice", {"voice_id": "test"}, "Check voice"),
]

GET_ENDPOINTS = [
    ("/api/v1/generate/record-info?taskId=test", "Poll task status (dummy id)"),
    ("/api/v1/generate/credit", "Credits"),
    ("/api/v1/voice/record-info?voiceId=test", "Voice record info"),
    ("/api/v1/lyrics/record-info?taskId=test", "Lyrics record info"),
    ("/api/v1/wav/record-info?taskId=test", "WAV record info"),
    ("/api/v1/vocal-removal/record-info?taskId=test", "Vocal removal record info"),
    ("/api/v1/midi/record-info?taskId=test", "MIDI record info"),
    ("/api/v1/mp4/record-info?taskId=test", "MP4 record info"),
    ("/api/v1/suno/cover/record-info?taskId=test", "Cover record info"),
]


def classify(resp: dict) -> tuple[str, str]:
    code = resp.get("code", resp.get("status", resp.get("statusCode", 0)))
    msg = resp.get("msg", resp.get("message", resp.get("error", str(resp))))
    if code == 404:
        return "MISS", f"404 — {msg[:80]}"
    if code == 0 and resp.get("_error"):
        return "ERR", msg[:80]
    if code in (400, 401, 403, 422, 429, 500, 502, 503):
        return "OK", f"{code} — {msg[:80]}"
    if code == 200:
        return "OK", f"{code} — {msg[:80]}"
    return "???", f"{code} — {msg[:80]}"


def main():
    if not SUNO_API_KEY:
        print("ERROR: SUNO_API_KEY not set")
        sys.exit(1)

    print(f"Probing {SUNO_BASE_URL} …\n")

    print("=" * 70)
    print("POST endpoints")
    print("=" * 70)
    miss_post = []
    for path, payload, desc in POST_ENDPOINTS:
        resp = api_post(path, payload)
        status, detail = classify(resp)
        icon = "✅" if status == "OK" else ("❌" if status == "MISS" else "⚠️")
        print(f"{icon} {desc:30s} {path:45s} → {detail}")
        if status == "MISS":
            miss_post.append((path, desc))

    print()
    print("=" * 70)
    print("GET endpoints")
    print("=" * 70)
    miss_get = []
    for path, desc in GET_ENDPOINTS:
        resp = api_get(path)
        status, detail = classify(resp)
        icon = "✅" if status == "OK" else ("❌" if status == "MISS" else "⚠️")
        print(f"{icon} {desc:30s} {path:45s} → {detail}")
        if status == "MISS":
            miss_get.append((path, desc))

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = len(POST_ENDPOINTS) + len(GET_ENDPOINTS)
    misses = len(miss_post) + len(miss_get)
    print(f"Total endpoints probed: {total}")
    print(f"Routes that 404 (likely wrong path): {misses}")
    if misses:
        print("\nMissing routes:")
        for path, desc in miss_post + miss_get:
            print(f"  ❌ {desc}: {path}")
    else:
        print("\nAll probed routes responded (no 404s).")


if __name__ == "__main__":
    main()
