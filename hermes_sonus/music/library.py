"""
Music Library for Hermes Music Plugin

Browse, search, favorite, and play songs from the music library.
Track-aware: each generation produces multiple tracks with independent curation.
"""

import logging
from typing import Any, Dict, List, Optional

from .tasks import MusicTaskManager, MusicTask, TrackInfo, TaskStatus
from .player import play_audio, stop_playback, is_playing, find_player

logger = logging.getLogger(__name__)


def _track_summary(task: MusicTask) -> List[Dict[str, Any]]:
    """Build a summary list of tracks for a task."""
    tracks = []
    for i, t in enumerate(task.tracks, 1):
        tracks.append({
            "track": i,
            "file": t.file,
            "duration": t.duration,
            "favorite": t.favorite,
            "archived": t.archived,
            "play_count": t.play_count,
        })
    return tracks


def browse_library(
    manager: MusicTaskManager,
    agent_id: Optional[str] = None,
    favorites_only: bool = False,
    status: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Browse the music library with optional filters."""
    try:
        sorted_tasks = sorted(
            manager.tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )

        filtered = []
        for task in sorted_tasks:
            if agent_id and task.agent_id != agent_id:
                continue
            if favorites_only and not task.favorite:
                continue
            if status and task.status.value != status:
                continue
            filtered.append(task)
            if len(filtered) >= limit:
                break

        total_duration = sum(t.duration for t in filtered if t.duration)
        completed_count = sum(1 for t in filtered if t.status == TaskStatus.COMPLETED)

        songs = []
        for t in filtered:
            songs.append({
                "task_id": t.task_id,
                "title": t.title or "Untitled",
                "agent_id": t.agent_id,
                "status": t.status.value,
                "favorite": t.favorite,
                "play_count": t.play_count,
                "duration": t.duration,
                "audio_file": t.audio_file,
                "is_instrumental": t.is_instrumental,
                "track_count": t.track_count,
                "tracks": _track_summary(t),
                "created_at": t.created_at,
            })

        return {
            "songs": songs,
            "count": len(songs),
            "completed_count": completed_count,
            "total_duration": total_duration,
            "total_in_library": len(manager.tasks),
        }

    except Exception as e:
        logger.error("Error browsing library: %s", e)
        return {"error": str(e)}


def search_songs(
    manager: MusicTaskManager,
    query: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search songs by title, prompt, or style."""
    try:
        query_lower = query.lower()
        matches = []

        for task in manager.tasks.values():
            searchable = f"{task.title} {task.prompt} {task.style}".lower()
            if query_lower in searchable:
                matches.append((task, searchable.count(query_lower)))

        matches.sort(key=lambda x: (-x[1], x[0].created_at), reverse=True)

        results = []
        for task, _score in matches[:limit]:
            results.append({
                "task_id": task.task_id,
                "title": task.title or "Untitled",
                "agent_id": task.agent_id,
                "status": task.status.value,
                "favorite": task.favorite,
                "duration": task.duration,
                "audio_file": task.audio_file,
                "track_count": task.track_count,
                "tracks": _track_summary(task),
                "prompt_preview": task.prompt[:100] + ("..." if len(task.prompt) > 100 else ""),
                "created_at": task.created_at,
            })

        return {
            "results": results,
            "count": len(results),
            "query": query,
            "total_searched": len(manager.tasks),
        }

    except Exception as e:
        logger.error("Error searching music: %s", e)
        return {"error": str(e)}


def toggle_favorite(
    manager: MusicTaskManager,
    task_id: str,
    track: Optional[int] = None,
    favorite: Optional[bool] = None,
) -> Dict[str, Any]:
    """Toggle or set favorite status for a song or specific track.

    Args:
        task_id: The task to modify.
        track: 1-indexed track number. If None, toggles the task-level favorite.
        favorite: Explicit value. If None, toggles current state.
    """
    try:
        task = manager.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        if track is not None:
            # Track-level favorite
            ti = task.get_track(track)
            if not ti:
                return {"success": False, "error": f"Track {track} not found (task has {task.track_count} tracks)"}
            if favorite is not None:
                ti.favorite = favorite
            else:
                ti.favorite = not ti.favorite
            manager._save_tasks()
            return {
                "success": True,
                "task_id": task_id,
                "track": track,
                "title": task.title,
                "favorite": ti.favorite,
                "message": f"{'⭐ Favorited' if ti.favorite else '☆ Unfavorited'}: {task.title} (track {track})",
            }
        else:
            # Task-level favorite
            if favorite is not None:
                task.favorite = favorite
            else:
                task.favorite = not task.favorite
            manager._save_tasks()
            return {
                "success": True,
                "task_id": task_id,
                "title": task.title,
                "favorite": task.favorite,
                "message": f"{'⭐ Favorited' if task.favorite else '☆ Unfavorited'}: {task.title}",
            }

    except Exception as e:
        logger.error("Error toggling favorite: %s", e)
        return {"success": False, "error": str(e)}


def play_song(
    manager: MusicTaskManager,
    task_id: str,
    track: int = 1,
) -> Dict[str, Any]:
    """Play a specific track from a song using local audio player.

    Args:
        task_id: The task to play.
        track: 1-indexed track number (default: 1).
    """
    try:
        task = manager.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        if task.status != TaskStatus.COMPLETED:
            return {
                "success": False,
                "error": f"Song not ready. Status: {task.status.value}",
            }

        ti = task.get_track(track)
        if not ti:
            return {
                "success": False,
                "error": f"Track {track} not found (task has {task.track_count} tracks)",
            }

        if ti.archived:
            return {
                "success": False,
                "error": f"Track {track} is archived",
            }

        if not ti.file:
            return {"success": False, "error": f"Track {track} has no audio file"}

        # Play audio (auto-stops previous)
        play_result = play_audio(ti.file, auto_stop=True)

        if not play_result.get("success"):
            # Fall back to just returning the path (for MEDIA: delivery)
            ti.play_count += 1
            task.play_count += 1
            manager._save_tasks()
            return {
                "success": True,
                "task_id": task_id,
                "title": task.title,
                "track": track,
                "track_count": task.track_count,
                "audio_file": ti.file,
                "duration": ti.duration,
                "play_count": ti.play_count,
                "player": None,
                "player_error": play_result.get("error"),
                "message": f"Now playing: {task.title} (track {track}/{task.track_count})",
            }

        # Update play counts
        ti.play_count += 1
        task.play_count += 1
        manager._save_tasks()

        return {
            "success": True,
            "task_id": task_id,
            "title": task.title,
            "track": track,
            "track_count": task.track_count,
            "audio_file": ti.file,
            "duration": ti.duration,
            "play_count": ti.play_count,
            "player": play_result.get("player"),
            "pid": play_result.get("pid"),
            "message": f"Now playing: {task.title} (track {track}/{task.track_count}) via {play_result.get('player')}",
        }

    except Exception as e:
        logger.error("Error playing music: %s", e)
        return {"success": False, "error": str(e)}
