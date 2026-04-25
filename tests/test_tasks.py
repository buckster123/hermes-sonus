"""Tests for the MusicTaskManager — v2 with TrackInfo."""

import json
import pytest
from pathlib import Path

from hermes_sonus.music.tasks import MusicTaskManager, MusicTask, TrackInfo, TaskStatus


@pytest.fixture
def manager(tmp_path):
    """Create a fresh MusicTaskManager with temp storage."""
    return MusicTaskManager(tmp_path / "music")


class TestTrackInfo:
    def test_defaults(self):
        t = TrackInfo()
        assert t.file == ""
        assert t.favorite is False
        assert t.archived is False
        assert t.play_count == 0

    def test_to_dict_roundtrip(self):
        t = TrackInfo(
            file="/tmp/song_1.mp3",
            audio_url="https://example.com/1.mp3",
            duration=120.5,
            clip_id="clip_abc",
            title="My Song",
            favorite=True,
            archived=False,
            play_count=3,
        )
        d = t.to_dict()
        restored = TrackInfo.from_dict(d)
        assert restored.file == "/tmp/song_1.mp3"
        assert restored.favorite is True
        assert restored.play_count == 3
        assert restored.duration == 120.5

    def test_from_dict_defaults(self):
        t = TrackInfo.from_dict({})
        assert t.file == ""
        assert t.archived is False


class TestMusicTaskTracks:
    def test_audio_file_property(self):
        task = MusicTask(
            task_id="test_1",
            prompt="test",
            tracks=[
                TrackInfo(file="/tmp/song_1.mp3"),
                TrackInfo(file="/tmp/song_2.mp3"),
            ],
        )
        assert task.audio_file == "/tmp/song_1.mp3"

    def test_audio_file_skips_archived(self):
        task = MusicTask(
            task_id="test_1",
            prompt="test",
            tracks=[
                TrackInfo(file="/tmp/song_1.mp3", archived=True),
                TrackInfo(file="/tmp/song_2.mp3"),
            ],
        )
        assert task.audio_file == "/tmp/song_2.mp3"

    def test_audio_file_empty(self):
        task = MusicTask(task_id="test_1", prompt="test")
        assert task.audio_file is None

    def test_track_count(self):
        task = MusicTask(
            task_id="test_1",
            prompt="test",
            tracks=[TrackInfo(), TrackInfo()],
        )
        assert task.track_count == 2

    def test_active_tracks(self):
        task = MusicTask(
            task_id="test_1",
            prompt="test",
            tracks=[
                TrackInfo(archived=True),
                TrackInfo(archived=False),
            ],
        )
        assert len(task.active_tracks) == 1

    def test_get_track(self):
        task = MusicTask(
            task_id="test_1",
            prompt="test",
            tracks=[TrackInfo(file="a.mp3"), TrackInfo(file="b.mp3")],
        )
        assert task.get_track(1).file == "a.mp3"
        assert task.get_track(2).file == "b.mp3"
        assert task.get_track(3) is None
        assert task.get_track(0) is None


class TestV1Migration:
    def test_migrate_old_format(self):
        """Old tasks.json had audio_file as a string, no tracks list."""
        old_data = {
            "task_id": "music_old_123",
            "prompt": "ambient vibes",
            "audio_file": "/tmp/old_song.mp3",
            "audio_url": "https://example.com/old.mp3",
            "duration": 180.0,
            "clip_id": "clip_old",
            "status": "completed",
            "title": "Old Song",
            "favorite": True,
            "play_count": 5,
        }
        task = MusicTask.from_dict(old_data)
        assert len(task.tracks) == 1
        assert task.tracks[0].file == "/tmp/old_song.mp3"
        assert task.tracks[0].duration == 180.0
        assert task.tracks[0].favorite is True
        assert task.tracks[0].play_count == 5
        # Backward compat property
        assert task.audio_file == "/tmp/old_song.mp3"

    def test_new_format_preserved(self):
        """New format with tracks list loads correctly."""
        new_data = {
            "task_id": "music_new_456",
            "prompt": "jazz piano",
            "tracks": [
                {"file": "/tmp/jazz_1.mp3", "duration": 120.0, "clip_id": "c1"},
                {"file": "/tmp/jazz_2.mp3", "duration": 125.0, "clip_id": "c2"},
            ],
            "status": "completed",
        }
        task = MusicTask.from_dict(new_data)
        assert len(task.tracks) == 2
        assert task.tracks[0].file == "/tmp/jazz_1.mp3"
        assert task.tracks[1].file == "/tmp/jazz_2.mp3"

    def test_no_audio_no_tracks(self):
        """Task with neither audio_file nor tracks gets empty list."""
        data = {"task_id": "music_empty", "prompt": "test", "status": "pending"}
        task = MusicTask.from_dict(data)
        assert task.tracks == []


class TestSiblingDiscovery:
    def test_find_sibling(self, tmp_path):
        """If _1.mp3 exists and _2.mp3 is on disk, it should be discovered."""
        audio_dir = tmp_path / "music" / "audio"
        audio_dir.mkdir(parents=True)

        # Create both files on disk
        track1 = audio_dir / "Ghost_7972_714_1.mp3"
        track2 = audio_dir / "Ghost_7972_714_2.mp3"
        track1.write_bytes(b"fake audio 1")
        track2.write_bytes(b"fake audio 2")

        # Create a v1-format tasks.json with only track 1
        tasks_data = {
            "music_7972_714": {
                "task_id": "music_7972_714",
                "prompt": "ghost song",
                "audio_file": str(track1),
                "duration": 120.0,
                "status": "completed",
                "title": "Ghost",
            }
        }
        tasks_file = tmp_path / "music" / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data))

        # Load — should discover track 2
        manager = MusicTaskManager(tmp_path / "music")
        task = manager.get_task("music_7972_714")
        assert task is not None
        assert len(task.tracks) == 2
        assert task.tracks[0].file == str(track1)
        assert task.tracks[1].file == str(track2)

    def test_no_sibling(self, tmp_path):
        """If only _1.mp3 exists, no discovery happens."""
        audio_dir = tmp_path / "music" / "audio"
        audio_dir.mkdir(parents=True)

        track1 = audio_dir / "Solo_1234_567_1.mp3"
        track1.write_bytes(b"fake audio")

        tasks_data = {
            "music_1234_567": {
                "task_id": "music_1234_567",
                "prompt": "solo track",
                "audio_file": str(track1),
                "status": "completed",
            }
        }
        tasks_file = tmp_path / "music" / "tasks.json"
        tasks_file.write_text(json.dumps(tasks_data))

        manager = MusicTaskManager(tmp_path / "music")
        task = manager.get_task("music_1234_567")
        assert len(task.tracks) == 1


class TestArchiveDelete:
    def test_archive_track(self, tmp_path):
        manager = MusicTaskManager(tmp_path / "music")
        # Create a fake completed task with 2 tracks
        task = manager.create_task(prompt="test")
        audio1 = manager.music_dir / "test_1.mp3"
        audio2 = manager.music_dir / "test_2.mp3"
        audio1.write_bytes(b"audio 1")
        audio2.write_bytes(b"audio 2")
        task.tracks = [
            TrackInfo(file=str(audio1)),
            TrackInfo(file=str(audio2)),
        ]
        task.status = TaskStatus.COMPLETED
        manager._save_tasks()

        # Archive track 1
        result = manager.archive_track(task.task_id, 1)
        assert result["success"] is True
        assert task.tracks[0].archived is True
        # File should be moved to archive dir
        assert not audio1.exists()
        assert (manager.archive_dir / "test_1.mp3").exists()

    def test_delete_track(self, tmp_path):
        manager = MusicTaskManager(tmp_path / "music")
        task = manager.create_task(prompt="test")
        audio = manager.music_dir / "test_1.mp3"
        audio.write_bytes(b"audio")
        task.tracks = [TrackInfo(file=str(audio))]
        task.status = TaskStatus.COMPLETED
        manager._save_tasks()

        result = manager.delete_track(task.task_id, 1)
        assert result["success"] is True
        assert not audio.exists()
        assert task.tracks[0].file == ""
        assert task.tracks[0].archived is True

    def test_delete_task(self, tmp_path):
        manager = MusicTaskManager(tmp_path / "music")
        task = manager.create_task(prompt="test")
        audio = manager.music_dir / "test_1.mp3"
        audio.write_bytes(b"audio")
        task.tracks = [TrackInfo(file=str(audio))]
        task.status = TaskStatus.COMPLETED
        manager._save_tasks()

        tid = task.task_id
        result = manager.delete_task(tid)
        assert result["success"] is True
        assert manager.get_task(tid) is None
        assert not audio.exists()


class TestTaskCreation:
    def test_create_task(self, manager):
        task = manager.create_task(prompt="ambient vibes", style="electronic")
        assert task.task_id.startswith("music_")
        assert task.prompt == "ambient vibes"
        assert task.style == "electronic"
        assert task.status == TaskStatus.PENDING
        assert task.is_instrumental is True

    def test_create_task_with_agent_id(self, manager):
        task = manager.create_task(prompt="test", agent_id="CLAUDE-OPUS")
        assert task.agent_id == "CLAUDE-OPUS"

    def test_create_task_persists(self, manager, tmp_path):
        task = manager.create_task(prompt="persist test")
        # Reload from disk
        manager2 = MusicTaskManager(tmp_path / "music")
        loaded = manager2.get_task(task.task_id)
        assert loaded is not None
        assert loaded.prompt == "persist test"

    def test_create_task_with_all_fields(self, manager):
        task = manager.create_task(
            prompt="epic orchestral battle",
            style="cinematic orchestral",
            title="Battle Theme",
            model="V4_5",
            is_instrumental=False,
            agent_id="CLAUDE-HAILO",
        )
        assert task.title == "Battle Theme"
        assert task.model == "V4_5"
        assert task.is_instrumental is False


class TestTaskSerialization:
    def test_to_dict_roundtrip(self):
        task = MusicTask(
            task_id="music_123",
            prompt="test prompt",
            style="jazz",
            title="Test Song",
            favorite=True,
            play_count=5,
            tags=["chill", "study"],
            tracks=[
                TrackInfo(file="/a.mp3", duration=120.0, favorite=True),
                TrackInfo(file="/b.mp3", duration=125.0),
            ],
        )
        d = task.to_dict()
        restored = MusicTask.from_dict(d)
        assert restored.task_id == "music_123"
        assert restored.prompt == "test prompt"
        assert restored.favorite is True
        assert restored.play_count == 5
        assert restored.tags == ["chill", "study"]
        assert len(restored.tracks) == 2
        assert restored.tracks[0].favorite is True

    def test_from_dict_handles_invalid_status(self):
        task = MusicTask.from_dict({
            "task_id": "music_456",
            "status": "invalid_status",
        })
        assert task.status == TaskStatus.PENDING

    def test_from_dict_defaults(self):
        task = MusicTask.from_dict({"task_id": "music_789"})
        assert task.model == "V5"
        assert task.is_instrumental is True
        assert task.favorite is False
        assert task.play_count == 0
        assert task.tracks == []


class TestTaskListing:
    def test_list_tasks_empty(self, manager):
        assert manager.list_tasks() == []

    def test_list_tasks_ordered(self, manager):
        t1 = manager.create_task(prompt="first")
        import time; time.sleep(0.01)
        t2 = manager.create_task(prompt="second")
        tasks = manager.list_tasks(limit=10)
        assert tasks[0].task_id == t2.task_id  # Most recent first
        assert tasks[1].task_id == t1.task_id

    def test_list_tasks_limit(self, manager):
        for i in range(5):
            manager.create_task(prompt=f"task {i}")
        assert len(manager.list_tasks(limit=3)) == 3


class TestDirectories:
    def test_directories_created(self, tmp_path):
        manager = MusicTaskManager(tmp_path / "new_music")
        assert (tmp_path / "new_music" / "audio").is_dir()
        assert (tmp_path / "new_music" / "midi").is_dir()
        assert (tmp_path / "new_music" / "archive").is_dir()
