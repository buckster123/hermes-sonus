"""Tests for the music library functions — v2 with track-aware operations."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from hermes_sonus.music.tasks import MusicTaskManager, MusicTask, TrackInfo, TaskStatus
from hermes_sonus.music.library import browse_library, search_songs, toggle_favorite, play_song


@pytest.fixture
def manager(tmp_path):
    mgr = MusicTaskManager(tmp_path / "music")

    # Create test tasks with dual tracks
    t1 = mgr.create_task(prompt="ambient electronic vibes", style="ambient electronic", title="Chill Waves", agent_id="CLAUDE-OPUS")
    t1.status = TaskStatus.COMPLETED
    t1.tracks = [
        TrackInfo(file="/tmp/chill_waves_1.mp3", duration=120.0),
        TrackInfo(file="/tmp/chill_waves_2.mp3", duration=122.0),
    ]

    t2 = mgr.create_task(prompt="epic orchestral battle", style="cinematic", title="Battle Theme", agent_id="CLAUDE-HAILO")
    t2.status = TaskStatus.COMPLETED
    t2.favorite = True
    t2.tracks = [
        TrackInfo(file="/tmp/battle_1.mp3", duration=180.0),
        TrackInfo(file="/tmp/battle_2.mp3", duration=175.0, favorite=True),
    ]

    t3 = mgr.create_task(prompt="jazz improv", style="jazz piano", title="Night Jazz")
    t3.status = TaskStatus.FAILED
    t3.error = "API timeout"

    mgr._save_tasks()
    return mgr


class TestBrowseLibrary:
    def test_browse_all(self, manager):
        result = browse_library(manager)
        assert result["count"] == 3
        assert result["total_in_library"] == 3

    def test_browse_includes_tracks(self, manager):
        result = browse_library(manager)
        completed = [s for s in result["songs"] if s["status"] == "completed"]
        assert len(completed) >= 1
        # Completed songs should have track info
        for song in completed:
            assert "tracks" in song
            assert "track_count" in song

    def test_browse_by_agent(self, manager):
        result = browse_library(manager, agent_id="CLAUDE-OPUS")
        assert result["count"] == 1
        assert result["songs"][0]["title"] == "Chill Waves"

    def test_browse_favorites_only(self, manager):
        result = browse_library(manager, favorites_only=True)
        assert result["count"] == 1
        assert result["songs"][0]["title"] == "Battle Theme"

    def test_browse_by_status(self, manager):
        result = browse_library(manager, status="failed")
        assert result["count"] == 1
        assert result["songs"][0]["title"] == "Night Jazz"

    def test_browse_limit(self, manager):
        result = browse_library(manager, limit=2)
        assert result["count"] == 2


class TestSearchSongs:
    def test_search_by_title(self, manager):
        result = search_songs(manager, "battle")
        assert result["count"] == 1
        assert result["results"][0]["title"] == "Battle Theme"

    def test_search_includes_tracks(self, manager):
        result = search_songs(manager, "battle")
        assert "tracks" in result["results"][0]
        assert "track_count" in result["results"][0]

    def test_search_by_style(self, manager):
        result = search_songs(manager, "jazz")
        assert result["count"] == 1

    def test_search_by_prompt(self, manager):
        result = search_songs(manager, "ambient")
        assert result["count"] == 1

    def test_search_no_results(self, manager):
        result = search_songs(manager, "reggaeton")
        assert result["count"] == 0

    def test_search_case_insensitive(self, manager):
        result = search_songs(manager, "BATTLE")
        assert result["count"] == 1


class TestToggleFavorite:
    def test_toggle_task_level(self, manager):
        tasks = manager.list_tasks()
        non_fav = [t for t in tasks if not t.favorite][0]
        result = toggle_favorite(manager, non_fav.task_id)
        assert result["success"] is True
        assert result["favorite"] is True

    def test_toggle_track_level(self, manager):
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        result = toggle_favorite(manager, completed.task_id, track=2)
        assert result["success"] is True
        assert "track" in result

    def test_toggle_off(self, manager):
        tasks = manager.list_tasks()
        fav = [t for t in tasks if t.favorite][0]
        result = toggle_favorite(manager, fav.task_id)
        assert result["success"] is True
        assert result["favorite"] is False

    def test_set_explicit(self, manager):
        tasks = manager.list_tasks()
        result = toggle_favorite(manager, tasks[0].task_id, favorite=True)
        assert result["favorite"] is True

    def test_not_found(self, manager):
        result = toggle_favorite(manager, "nonexistent")
        assert result["success"] is False

    def test_invalid_track(self, manager):
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        result = toggle_favorite(manager, completed.task_id, track=99)
        assert result["success"] is False


class TestPlaySong:
    @patch("hermes_sonus.music.library.play_audio")
    def test_play_track_1(self, mock_play, manager):
        mock_play.return_value = {"success": True, "player": "mpg123", "pid": 1234}
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        result = play_song(manager, completed.task_id, track=1)
        assert result["success"] is True
        assert result["track"] == 1
        assert result["player"] == "mpg123"

    @patch("hermes_sonus.music.library.play_audio")
    def test_play_track_2(self, mock_play, manager):
        mock_play.return_value = {"success": True, "player": "mpg123", "pid": 1234}
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        result = play_song(manager, completed.task_id, track=2)
        assert result["success"] is True
        assert result["track"] == 2
        assert result["track_count"] == 2

    @patch("hermes_sonus.music.library.play_audio")
    def test_play_increments_count(self, mock_play, manager):
        mock_play.return_value = {"success": True, "player": "mpg123", "pid": 1234}
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        play_song(manager, completed.task_id, track=1)
        play_song(manager, completed.task_id, track=1)
        assert completed.tracks[0].play_count == 2
        assert completed.play_count == 2

    @patch("hermes_sonus.music.library.play_audio")
    def test_play_no_player_fallback(self, mock_play, manager):
        """If no player available, still succeed with file path."""
        mock_play.return_value = {"success": False, "error": "No audio player found"}
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        result = play_song(manager, completed.task_id, track=1)
        assert result["success"] is True
        assert result["player"] is None
        assert result["player_error"] is not None

    def test_play_failed_song(self, manager):
        tasks = manager.list_tasks()
        failed = [t for t in tasks if t.status == TaskStatus.FAILED][0]
        result = play_song(manager, failed.task_id)
        assert result["success"] is False

    def test_play_not_found(self, manager):
        result = play_song(manager, "nonexistent")
        assert result["success"] is False

    @patch("hermes_sonus.music.library.play_audio")
    def test_play_archived_track(self, mock_play, manager):
        tasks = manager.list_tasks()
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED][0]
        completed.tracks[0].archived = True
        manager._save_tasks()
        result = play_song(manager, completed.task_id, track=1)
        assert result["success"] is False
        assert "archived" in result["error"]
