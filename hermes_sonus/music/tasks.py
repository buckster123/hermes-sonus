"""
Music Task Manager for Hermes Music Plugin

Manages the lifecycle of music generation tasks:
create → submit → poll → download → complete/fail

Persists task state to JSON for durability across sessions.
"""

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import suno

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TrackInfo:
    """Represents a single audio track within a generation task.

    Suno produces 2 tracks per request. Each gets independent curation state.
    """
    file: str = ""
    audio_url: str = ""
    duration: float = 0.0
    clip_id: str = ""
    title: str = ""
    favorite: bool = False
    archived: bool = False
    play_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "audio_url": self.audio_url,
            "duration": self.duration,
            "clip_id": self.clip_id,
            "title": self.title,
            "favorite": self.favorite,
            "archived": self.archived,
            "play_count": self.play_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackInfo":
        return cls(
            file=data.get("file", ""),
            audio_url=data.get("audio_url", ""),
            duration=data.get("duration", 0.0),
            clip_id=data.get("clip_id", ""),
            title=data.get("title", ""),
            favorite=data.get("favorite", False),
            archived=data.get("archived", False),
            play_count=data.get("play_count", 0),
        )


@dataclass
class MusicTask:
    """Represents a music generation task."""
    task_id: str
    prompt: str
    style: str = ""
    title: str = ""
    model: str = "V5"
    is_instrumental: bool = True
    status: TaskStatus = TaskStatus.PENDING
    progress: str = "Queued"
    suno_task_id: Optional[str] = None
    # Track list — replaces the old single audio_file/audio_url/duration/clip_id
    tracks: List[TrackInfo] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Curation fields
    agent_id: Optional[str] = None
    favorite: bool = False
    play_count: int = 0
    tags: List[str] = field(default_factory=list)

    # --- Backward-compat properties ---

    @property
    def audio_file(self) -> Optional[str]:
        """Return the first non-archived track's file (backward compat)."""
        for t in self.tracks:
            if not t.archived and t.file:
                return t.file
        # Fall back to any track with a file
        for t in self.tracks:
            if t.file:
                return t.file
        return None

    @property
    def audio_url(self) -> Optional[str]:
        for t in self.tracks:
            if not t.archived and t.audio_url:
                return t.audio_url
        return None

    @property
    def duration(self) -> float:
        for t in self.tracks:
            if not t.archived and t.duration:
                return t.duration
        if self.tracks:
            return self.tracks[0].duration
        return 0.0

    @property
    def clip_id(self) -> Optional[str]:
        for t in self.tracks:
            if not t.archived and t.clip_id:
                return t.clip_id
        return None

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def active_tracks(self) -> List[TrackInfo]:
        return [t for t in self.tracks if not t.archived]

    def get_track(self, track_num: int) -> Optional[TrackInfo]:
        """Get track by 1-indexed number."""
        idx = track_num - 1
        if 0 <= idx < len(self.tracks):
            return self.tracks[idx]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "style": self.style,
            "title": self.title,
            "model": self.model,
            "is_instrumental": self.is_instrumental,
            "status": self.status.value,
            "progress": self.progress,
            "suno_task_id": self.suno_task_id,
            "tracks": [t.to_dict() for t in self.tracks],
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "agent_id": self.agent_id,
            "favorite": self.favorite,
            "play_count": self.play_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MusicTask":
        try:
            status = TaskStatus(data.get("status", "pending"))
        except ValueError:
            status = TaskStatus.PENDING

        # --- v1 → v2 migration ---
        # Old format had audio_file/audio_url/duration/clip_id as top-level strings.
        # New format uses a tracks list.
        tracks_raw = data.get("tracks")
        if tracks_raw is not None:
            tracks = [TrackInfo.from_dict(t) for t in tracks_raw]
        elif data.get("audio_file"):
            # Migrate old single-track format
            tracks = [TrackInfo(
                file=data.get("audio_file", ""),
                audio_url=data.get("audio_url", ""),
                duration=data.get("duration", 0.0),
                clip_id=data.get("clip_id", ""),
                title=data.get("title", ""),
                favorite=data.get("favorite", False),
                play_count=data.get("play_count", 0),
            )]
        else:
            tracks = []

        return cls(
            task_id=data["task_id"],
            prompt=data.get("prompt", ""),
            style=data.get("style", ""),
            title=data.get("title", ""),
            model=data.get("model", "V5"),
            is_instrumental=data.get("is_instrumental", True),
            status=status,
            progress=data.get("progress", "Queued"),
            suno_task_id=data.get("suno_task_id"),
            tracks=tracks,
            error=data.get("error"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            agent_id=data.get("agent_id"),
            favorite=data.get("favorite", False),
            play_count=data.get("play_count", 0),
            tags=data.get("tags", []),
        )


class MusicTaskManager:
    """Manages music generation tasks with JSON persistence."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.music_dir = data_dir / "audio"
        self.midi_dir = data_dir / "midi"
        self.archive_dir = data_dir / "archive"
        self.tasks_file = data_dir / "tasks.json"
        self.tasks: Dict[str, MusicTask] = {}
        self._lock = threading.Lock()

        # Ensure directories exist
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.midi_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self._load_tasks()

    def _load_tasks(self):
        """Load tasks from JSON file, auto-migrating v1 format."""
        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, "r") as f:
                    data = json.load(f)
                migrated = False
                for task_id, task_data in data.items():
                    task = MusicTask.from_dict(task_data)
                    # Scan for orphaned _2.mp3 files from v1 era
                    if len(task.tracks) == 1 and task.tracks[0].file:
                        sibling = self._find_sibling_track(task.tracks[0].file)
                        if sibling:
                            task.tracks.append(TrackInfo(
                                file=sibling,
                                audio_url="",
                                duration=task.tracks[0].duration,  # estimate
                                clip_id="",
                                title=task.title,
                            ))
                            migrated = True
                            logger.info("Discovered orphan track 2: %s", sibling)
                    self.tasks[task_id] = task
                if migrated:
                    self._save_tasks()
                    logger.info("Migrated tasks with discovered track 2 files")
                logger.info("Loaded %d music tasks", len(self.tasks))
        except Exception as e:
            logger.error("Error loading music tasks: %s", e)

    @staticmethod
    def _find_sibling_track(track1_path: str) -> Optional[str]:
        """Given a _1.mp3 path, check if a _2.mp3 sibling exists."""
        p = Path(track1_path)
        name = p.stem  # e.g. Ghost_in_the_Wire_7972_714_1
        if name.endswith("_1"):
            sibling_name = name[:-1] + "2" + p.suffix  # _2.mp3
            sibling_path = p.parent / sibling_name
            if sibling_path.exists():
                return str(sibling_path)
        return None

    def _save_tasks(self):
        """Save tasks to JSON file."""
        try:
            self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
            data = {tid: t.to_dict() for tid, t in self.tasks.items()}
            with open(self.tasks_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Error saving music tasks: %s", e)

    def create_task(
        self,
        prompt: str,
        style: str = "",
        title: str = "",
        model: str = "V5",
        is_instrumental: bool = True,
        agent_id: Optional[str] = None,
    ) -> MusicTask:
        """Create a new music task."""
        task_id = f"music_{int(datetime.now().timestamp() * 1000)}_{random.randint(100, 999)}"
        task = MusicTask(
            task_id=task_id,
            prompt=prompt,
            style=style,
            title=title,
            model=model,
            is_instrumental=is_instrumental,
            agent_id=agent_id,
        )
        with self._lock:
            self.tasks[task_id] = task
            self._save_tasks()
        logger.info("Created music task %s: %s...", task_id, prompt[:50])
        return task

    def get_task(self, task_id: str) -> Optional[MusicTask]:
        return self.tasks.get(task_id)

    def list_tasks(self, limit: int = 10) -> List[MusicTask]:
        sorted_tasks = sorted(
            self.tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )
        return sorted_tasks[:limit]

    def archive_track(self, task_id: str, track_num: int) -> Dict[str, Any]:
        """Archive a specific track — move file to archive/ and mark archived."""
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        track = task.get_track(track_num)
        if not track:
            return {"success": False, "error": f"Track {track_num} not found (task has {task.track_count} tracks)"}

        if track.archived:
            return {"success": False, "error": f"Track {track_num} is already archived"}

        # Move file to archive directory
        old_path = Path(track.file)
        if old_path.exists():
            new_path = self.archive_dir / old_path.name
            try:
                old_path.rename(new_path)
                track.file = str(new_path)
                logger.info("Moved %s → %s", old_path.name, new_path)
            except Exception as e:
                logger.error("Failed to move file to archive: %s", e)
                # Still mark archived even if move fails

        track.archived = True
        self._save_tasks()

        return {
            "success": True,
            "task_id": task_id,
            "track": track_num,
            "title": task.title,
            "archived_file": track.file,
            "message": f"Archived track {track_num} of '{task.title}'",
        }

    def delete_track(self, task_id: str, track_num: int) -> Dict[str, Any]:
        """Permanently delete a track file from disk."""
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        track = task.get_track(track_num)
        if not track:
            return {"success": False, "error": f"Track {track_num} not found"}

        deleted_file = track.file
        if track.file:
            p = Path(track.file)
            if p.exists():
                try:
                    p.unlink()
                    logger.info("Deleted file: %s", p)
                except Exception as e:
                    logger.error("Failed to delete file: %s", e)
                    return {"success": False, "error": f"Failed to delete: {e}"}

        track.file = ""
        track.archived = True
        self._save_tasks()

        return {
            "success": True,
            "task_id": task_id,
            "track": track_num,
            "title": task.title,
            "deleted_file": deleted_file,
            "message": f"Permanently deleted track {track_num} of '{task.title}'",
        }

    def archive_task(self, task_id: str) -> Dict[str, Any]:
        """Archive all tracks in a task."""
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        archived = 0
        for i, track in enumerate(task.tracks, 1):
            if not track.archived:
                self.archive_track(task_id, i)
                archived += 1

        return {
            "success": True,
            "task_id": task_id,
            "title": task.title,
            "tracks_archived": archived,
            "message": f"Archived {archived} track(s) from '{task.title}'",
        }

    def delete_task(self, task_id: str) -> Dict[str, Any]:
        """Permanently delete all tracks and remove the task."""
        task = self.get_task(task_id)
        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        deleted = 0
        for i in range(len(task.tracks), 0, -1):
            self.delete_track(task_id, i)
            deleted += 1

        title = task.title
        with self._lock:
            del self.tasks[task_id]
            self._save_tasks()

        return {
            "success": True,
            "task_id": task_id,
            "title": title,
            "tracks_deleted": deleted,
            "message": f"Permanently deleted '{title}' ({deleted} tracks)",
        }

    def run_task(self, task_id: str) -> Dict[str, Any]:
        """Run a music generation task (blocking). Downloads all tracks."""
        task = self.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        task.status = TaskStatus.GENERATING
        task.started_at = datetime.now().isoformat()
        task.progress = "Starting generation..."
        self._save_tasks()

        try:
            # Submit to Suno (skip if already submitted, e.g. music_compose)
            if task.suno_task_id:
                suno_task_id = task.suno_task_id
            else:
                task.progress = "Submitting to Suno API..."
                self._save_tasks()
                suno_task_id = suno.submit_generation(
                    prompt=task.prompt,
                    style=task.style,
                    title=task.title,
                    model=task.model,
                    is_instrumental=task.is_instrumental,
                )
                task.suno_task_id = suno_task_id

            task.progress = "Queued at Suno..."
            self._save_tasks()

            # Poll for completion
            result = suno.poll_completion(suno_task_id)

            if not result.get("success"):
                raise Exception(result.get("error", "Unknown error"))

            tracks = result.get("tracks", [])
            track_count = len(tracks)
            task.progress = f"Downloading {track_count} track(s)..."
            self._save_tasks()

            # Download all tracks and store as TrackInfo
            task.tracks = []
            downloaded_files = []

            for i, track_info in enumerate(tracks):
                try:
                    safe_title = re.sub(r"[^\w\-]", "_", track_info.get("title", f"track_{i+1}"))
                    filename = f"{safe_title}_{task_id[-8:]}_{i+1}.mp3"
                    output_path = str(self.music_dir / filename)

                    audio_file = suno.download_audio(track_info["audio_url"], output_path)

                    ti = TrackInfo(
                        file=audio_file,
                        audio_url=track_info.get("audio_url", ""),
                        duration=track_info.get("duration", 0.0),
                        clip_id=track_info.get("clip_id", ""),
                        title=track_info.get("title", ""),
                    )
                    task.tracks.append(ti)
                    downloaded_files.append(audio_file)
                except Exception as e:
                    logger.error("Failed to download track %d: %s", i + 1, e)

            if not downloaded_files:
                raise Exception("Failed to download any tracks")

            # Set task-level metadata from first track
            first = task.tracks[0]
            task.title = first.title or task.title or f"Track_{task_id[-8:]}"
            task.status = TaskStatus.COMPLETED
            task.progress = f"Complete ({track_count} tracks)"
            task.completed_at = datetime.now().isoformat()
            self._save_tasks()

            logger.info("Music task %s completed: %d tracks", task_id, track_count)
            return {
                "success": True,
                "audio_file": first.file,
                "audio_files": downloaded_files,
                "tracks": [t.to_dict() for t in task.tracks],
                "track_count": track_count,
            }

        except Exception as e:
            logger.error("Music task %s failed: %s", task_id, e)
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.progress = f"Failed: {str(e)[:100]}"
            task.completed_at = datetime.now().isoformat()
            self._save_tasks()
            return {"success": False, "error": str(e)}
