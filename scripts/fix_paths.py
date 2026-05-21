#!/usr/bin/env python3
"""Bulk-fix Suno API endpoint paths from official OpenAPI specs."""

import re
from pathlib import Path

# Mapping: old path -> new path
PATH_MAP = {
    # Main API
    '"/api/v1/extend"': '"/api/v1/generate/extend"',
    '"/api/v1/generate-lyrics"': '"/api/v1/lyrics"',
    '"/api/v1/separate-vocals"': '"/api/v1/vocal-removal/generate"',
    '"/api/v1/replace-section"': '"/api/v1/generate/replace-section"',
    '"/api/v1/boost-style"': '"/api/v1/style/generate"',
    '"/api/v1/convert-to-wav"': '"/api/v1/wav/generate"',
    '"/api/v1/create-music-video"': '"/api/v1/mp4/generate"',
    '"/api/v1/generate-sounds"': '"/api/v1/generate/sounds"',
    '"/api/v1/upload-and-cover"': '"/api/v1/generate/upload-cover"',
    '"/api/v1/upload-and-extend"': '"/api/v1/generate/upload-extend"',
    '"/api/v1/add-instrumental"': '"/api/v1/generate/add-instrumental"',
    '"/api/v1/add-vocals"': '"/api/v1/generate/add-vocals"',
    '"/api/v1/get-timestamped-lyrics"': '"/api/v1/generate/get-timestamped-lyrics"',
    '"/api/v1/cover-suno"': '"/api/v1/suno/cover/generate"',
    '"/api/v1/generate-persona"': '"/api/v1/generate/generate-persona"',
    '"/api/v1/generate-mashup"': '"/api/v1/generate/mashup"',
    '"/api/v1/generate-midi"': '"/api/v1/midi/generate"',
    # Voice API
    '"/api/v1/suno-voice-validate"': '"/api/v1/voice/validate"',
    '"/api/v1/suno-voice-generate"': '"/api/v1/voice/generate"',
    '"/api/v1/suno-voice-check-voice"': '"/api/v1/voice/check-voice"',
    '"/api/v1/suno-voice-record-info"': '"/api/v1/voice/record-info"',
    # File upload API (note: these are NOT under /api/v1/)
    '"/api/v1/upload-base64"': '"/api/file-base64-upload"',
    '"/api/v1/upload-stream"': '"/api/file-stream-upload"',
    '"/api/v1/upload-url"': '"/api/file-url-upload"',
    # Also fix any backtick-quoted mentions in docs/listings
    "`POST /api/v1/extend`": "`POST /api/v1/generate/extend`",
    "`POST /api/v1/generate-lyrics`": "`POST /api/v1/lyrics`",
    "`POST /api/v1/separate-vocals`": "`POST /api/v1/vocal-removal/generate`",
    "`POST /api/v1/replace-section`": "`POST /api/v1/generate/replace-section`",
    "`POST /api/v1/boost-style`": "`POST /api/v1/style/generate`",
    "`POST /api/v1/convert-to-wav`": "`POST /api/v1/wav/generate`",
    "`POST /api/v1/create-music-video`": "`POST /api/v1/mp4/generate`",
    "`POST /api/v1/generate-sounds`": "`POST /api/v1/generate/sounds`",
    "`POST /api/v1/upload-and-cover`": "`POST /api/v1/generate/upload-cover`",
    "`POST /api/v1/upload-and-extend`": "`POST /api/v1/generate/upload-extend`",
    "`POST /api/v1/add-instrumental`": "`POST /api/v1/generate/add-instrumental`",
    "`POST /api/v1/add-vocals`": "`POST /api/v1/generate/add-vocals`",
    "`POST /api/v1/get-timestamped-lyrics`": "`POST /api/v1/generate/get-timestamped-lyrics`",
    "`POST /api/v1/cover-suno`": "`POST /api/v1/suno/cover/generate`",
    "`POST /api/v1/generate-persona`": "`POST /api/v1/generate/generate-persona`",
    "`POST /api/v1/generate-mashup`": "`POST /api/v1/generate/mashup`",
    "`POST /api/v1/generate-midi`": "`POST /api/v1/midi/generate`",
    "`POST /api/v1/suno-voice-validate`": "`POST /api/v1/voice/validate`",
    "`GET /api/v1/suno-voice-validate-info`": "`GET /api/v1/voice/validate-info`",
    "`POST /api/v1/suno-voice-generate`": "`POST /api/v1/voice/generate`",
    "`GET /api/v1/suno-voice-record-info`": "`GET /api/v1/voice/record-info`",
    "`POST /api/v1/suno-voice-check-voice`": "`POST /api/v1/voice/check-voice`",
    "`POST /api/v1/upload-base64`": "`POST /api/file-base64-upload`",
    "`POST /api/v1/upload-stream`": "`POST /api/file-stream-upload`",
    "`POST /api/v1/upload-url`": "`POST /api/file-url-upload`",
    # Also fix any string mentions in docs/listings
    "'/api/v1/extend'": "'/api/v1/generate/extend'",
    "'/api/v1/generate-lyrics'": "'/api/v1/lyrics'",
    "'/api/v1/separate-vocals'": "'/api/v1/vocal-removal/generate'",
    "'/api/v1/replace-section'": "'/api/v1/generate/replace-section'",
    "'/api/v1/boost-style'": "'/api/v1/style/generate'",
    "'/api/v1/convert-to-wav'": "'/api/v1/wav/generate'",
    "'/api/v1/create-music-video'": "'/api/v1/mp4/generate'",
    "'/api/v1/generate-sounds'": "'/api/v1/generate/sounds'",
    "'/api/v1/upload-and-cover'": "'/api/v1/generate/upload-cover'",
    "'/api/v1/upload-and-extend'": "'/api/v1/generate/upload-extend'",
    "'/api/v1/add-instrumental'": "'/api/v1/generate/add-instrumental'",
    "'/api/v1/add-vocals'": "'/api/v1/generate/add-vocals'",
    "'/api/v1/get-timestamped-lyrics'": "'/api/v1/generate/get-timestamped-lyrics'",
    "'/api/v1/cover-suno'": "'/api/v1/suno/cover/generate'",
    "'/api/v1/generate-persona'": "'/api/v1/generate/generate-persona'",
    "'/api/v1/generate-mashup'": "'/api/v1/generate/mashup'",
    "'/api/v1/generate-midi'": "'/api/v1/midi/generate'",
    "'/api/v1/suno-voice-validate'": "'/api/v1/voice/validate'",
    "'/api/v1/suno-voice-generate'": "'/api/v1/voice/generate'",
    "'/api/v1/suno-voice-check-voice'": "'/api/v1/voice/check-voice'",
    "'/api/v1/suno-voice-record-info'": "'/api/v1/voice/record-info'",
    "'/api/v1/upload-base64'": "'/api/file-base64-upload'",
    "'/api/v1/upload-stream'": "'/api/file-stream-upload'",
    "'/api/v1/upload-url'": "'/api/file-url-upload'",
}

# Files to process
FILES = [
    Path("hermes_sonus/mcp/server.py"),
    Path("hermes_sonus/music/suno.py"),
    Path("hermes_sonus/music/__init__.py"),
    Path("hermes_sonus/api.py"),
    Path("tests/test_suno.py"),
    Path("tests/test_album.py"),
    Path("tests/test_mcp_layer.py"),
    Path("skills/sonus-prompt-engineering/references/api-integration.md"),
]


def fix_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in PATH_MAP.items():
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        print(f"  Updated: {path}")
        return 1
    else:
        print(f"  No changes: {path}")
        return 0


def main():
    changed = 0
    for f in FILES:
        if f.exists():
            changed += fix_file(f)
        else:
            print(f"  Missing: {f}")
    print(f"\nTotal files changed: {changed}")


if __name__ == "__main__":
    main()
