"""FastAPI router for the hermes-sonus dashboard plugin.

Wraps the existing music + eeg tool handlers in HTTP endpoints. The
dashboard UI calls these via ``SDK.fetchJSON("/api/plugins/hermes-sonus/...")``.

All endpoints either return JSON (parsed from the underlying handler's
JSON-string return) or stream a file (audio).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from hermes_sonus import music as _music
from hermes_sonus import eeg as _eeg

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(handler, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a tool handler and parse its JSON-string return value."""
    raw = handler(args or {})
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {"raw": raw}


# ---------------------------------------------------------------------------
# Capabilities (UI uses this to gate features)
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    suno_key = bool(os.environ.get("SUNO_API_KEY"))

    has_brainflow = False
    try:
        import brainflow  # noqa: F401
        has_brainflow = True
    except ImportError:
        pass

    has_midiutil = False
    try:
        import midiutil  # noqa: F401
        has_midiutil = True
    except ImportError:
        pass

    has_player = False
    for cmd in ("mpg123", "ffplay", "aplay", "afplay"):
        from shutil import which
        if which(cmd):
            has_player = True
            break

    return {
        "suno": suno_key,
        "eeg_hardware": has_brainflow,
        "eeg_mock": True,           # mock mode always works
        "midi_compose": has_midiutil,
        "local_player": has_player,
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Music — generation + library
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    style: str = ""
    title: str = ""
    model: str = "V5"
    is_instrumental: bool = True
    blocking: bool = False  # dashboard always polls
    agent_id: str = "dashboard"


@router.post("/generate")
async def music_generate(body: GenerateRequest) -> Dict[str, Any]:
    return _call(_music._handle_music_generate, body.model_dump())


@router.get("/tasks")
async def music_list(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    return _call(_music._handle_music_list, {"limit": limit})


@router.get("/tasks/{task_id}")
async def music_get(task_id: str) -> Dict[str, Any]:
    return _call(_music._handle_music_result, {"task_id": task_id})


@router.get("/tasks/{task_id}/status")
async def music_status(task_id: str) -> Dict[str, Any]:
    return _call(_music._handle_music_status, {"task_id": task_id})


@router.get("/tasks/{task_id}/audio/{track}")
async def music_audio(task_id: str, track: int):
    """Stream the MP3 for a given track. The dashboard uses this in a
    plain ``<audio>`` element so it auto-plays and scrubs with no extra
    engineering."""
    manager = _music._get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task {task_id} not found")
    try:
        track_info = task.tracks[track - 1]
    except (IndexError, AttributeError):
        raise HTTPException(404, f"Track {track} not found for task {task_id}")
    file_path = Path(track_info.file)
    if not file_path.exists():
        raise HTTPException(404, f"Audio file missing on disk: {file_path}")
    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        headers={"Accept-Ranges": "bytes"},
    )


class FavoriteRequest(BaseModel):
    track: Optional[int] = None
    favorite: Optional[bool] = None


@router.post("/tasks/{task_id}/favorite")
async def music_favorite(task_id: str, body: FavoriteRequest) -> Dict[str, Any]:
    args = {"task_id": task_id}
    if body.track is not None:
        args["track"] = body.track
    if body.favorite is not None:
        args["favorite"] = body.favorite
    return _call(_music._handle_music_favorite, args)


class DeleteRequest(BaseModel):
    track: Optional[int] = None
    permanent: bool = False


@router.post("/tasks/{task_id}/delete")
async def music_delete(task_id: str, body: DeleteRequest) -> Dict[str, Any]:
    return _call(_music._handle_music_delete, {"task_id": task_id, **body.model_dump()})


@router.get("/search")
async def music_search(q: str = Query(...), limit: int = 25) -> Dict[str, Any]:
    return _call(_music._handle_music_search, {"query": q, "limit": limit})


class ComposeRequest(BaseModel):
    midi_file: str
    style: str
    title: str
    audio_influence: float = 0.5
    prompt: str = ""
    instrumental: bool = True
    style_weight: float = 0.5
    weirdness: float = 0.3
    model: str = "V5"
    blocking: bool = False
    agent_id: str = "dashboard"


@router.post("/compose")
async def music_compose(body: ComposeRequest) -> Dict[str, Any]:
    return _call(_music._handle_music_compose, body.model_dump())


# ---------------------------------------------------------------------------
# Album projects
# ---------------------------------------------------------------------------

class AlbumGenerateRequest(BaseModel):
    manifest_text: str = ""
    manifest_file: str = ""
    model: str = "V5"
    callback_url: str = ""
    blocking: bool = False
    agent_id: str = "dashboard"
    continue_on_error: bool = True
    rate_interval: float = 0.75


@router.post("/album")
async def album_generate(body: AlbumGenerateRequest) -> Dict[str, Any]:
    return _call(_music._handle_music_generate_album, body.model_dump())


@router.get("/albums")
async def album_list(limit: int = Query(25, ge=1, le=500)) -> Dict[str, Any]:
    manager = _music._get_manager()
    albums = manager.list_albums(limit=limit)
    return {
        "albums": [
            {
                "album_id": a.album_id,
                "title": a.title,
                "status": a.status.value,
                "model": a.model,
                "track_count": len(a.track_task_ids),
                "progress": a.progress,
                "created_at": a.created_at,
                "agent_id": a.agent_id,
            }
            for a in albums
        ],
        "count": len(albums),
        "total": len(manager.albums),
    }


@router.get("/albums/{album_id}")
async def album_get(album_id: str) -> Dict[str, Any]:
    manager = _music._get_manager()
    album = manager.get_album(album_id)
    if not album:
        raise HTTPException(404, f"Album {album_id} not found")

    tracks = []
    for tid in album.track_task_ids:
        task = manager.get_task(tid)
        if task:
            tracks.append({
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "progress": task.progress,
                "audio_file": task.audio_file,
                "audio_url": task.audio_url,
                "duration": task.duration,
                "track_count": task.track_count,
                "error": task.error,
            })
        else:
            tracks.append({"task_id": tid, "status": "unknown", "error": "Task not found"})

    return {
        "album_id": album.album_id,
        "title": album.title,
        "status": album.status.value,
        "model": album.model,
        "progress": album.progress,
        "error": album.error,
        "created_at": album.created_at,
        "completed_at": album.completed_at,
        "agent_id": album.agent_id,
        "tracks": tracks,
        "manifest": album.manifest,
    }


# ---------------------------------------------------------------------------
# EEG — connection + sessions + live state
# ---------------------------------------------------------------------------

class EEGConnectRequest(BaseModel):
    serial_port: str = ""
    board_type: str = "mock"


@router.post("/eeg/connect")
async def eeg_connect(body: EEGConnectRequest) -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_connect, body.model_dump())


@router.post("/eeg/disconnect")
async def eeg_disconnect() -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_disconnect, {})


class EEGSessionStartRequest(BaseModel):
    session_name: str = "dashboard-session"
    track_id: str = ""
    track_title: str = ""
    listener_name: str = "User"


@router.post("/eeg/session/start")
async def eeg_session_start(body: EEGSessionStartRequest) -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_stream_start, body.model_dump())


@router.post("/eeg/session/stop")
async def eeg_session_stop() -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_stream_stop, {"generate_experience": True})


@router.get("/eeg/state")
async def eeg_live_state() -> Dict[str, Any]:
    """Latest live emotion sample. Dashboard polls this at ~1Hz."""
    return _call(_eeg._handle_eeg_realtime_emotion, {})


@router.get("/eeg/sessions")
async def eeg_list_sessions(limit: int = 25) -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_list_sessions, {"limit": limit})


@router.get("/eeg/sessions/{session_id}")
async def eeg_get_session(session_id: str, detail: str = "summary") -> Dict[str, Any]:
    return _call(_eeg._handle_eeg_experience_get, {
        "session_id": session_id,
        "detail_level": detail,
    })
