"""Tests for album/batch generation workflow (Phase B)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from hermes_sonus.music.tasks import (
    MusicTaskManager,
    AlbumProject,
    TaskStatus,
    MusicTask,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_manager(tmp_path: Path) -> MusicTaskManager:
    return MusicTaskManager(tmp_path)


# ---------------------------------------------------------------------------
# AlbumProject dataclass
# ---------------------------------------------------------------------------

class TestAlbumProject:
    def test_to_dict_roundtrip(self):
        album = AlbumProject(
            album_id="album_123",
            title="Test Album",
            model="V5",
            track_task_ids=["t1", "t2"],
            status=TaskStatus.GENERATING,
            progress="Fired 2 track(s)",
        )
        d = album.to_dict()
        assert d["album_id"] == "album_123"
        assert d["status"] == "generating"
        assert d["track_task_ids"] == ["t1", "t2"]

        restored = AlbumProject.from_dict(d)
        assert restored.album_id == album.album_id
        assert restored.status == album.status
        assert restored.track_task_ids == album.track_task_ids

    def test_from_dict_unknown_status_defaults_pending(self):
        restored = AlbumProject.from_dict({
            "album_id": "a1",
            "status": "weird_status",
        })
        assert restored.status == TaskStatus.PENDING


# ---------------------------------------------------------------------------
# MusicTaskManager album CRUD
# ---------------------------------------------------------------------------

class TestMusicTaskManagerAlbums:
    def test_create_album(self, tmp_path):
        mgr = _fresh_manager(tmp_path)
        manifest = {
            "album_title": "Neon Nights",
            "tracks": [{"title": "Track 1"}, {"title": "Track 2"}],
        }
        album = mgr.create_album(title="Neon Nights", manifest=manifest, model="V5")
        assert album.title == "Neon Nights"
        assert album.album_id.startswith("album_")
        assert album.status == TaskStatus.PENDING
        assert mgr.get_album(album.album_id) is album

    def test_list_albums_sorted(self, tmp_path):
        mgr = _fresh_manager(tmp_path)
        a1 = mgr.create_album(title="First", manifest={"tracks": []})
        a2 = mgr.create_album(title="Second", manifest={"tracks": []})
        albums = mgr.list_albums(limit=10)
        assert albums[0].album_id == a2.album_id  # newest first
        assert albums[1].album_id == a1.album_id

    def test_update_album_status(self, tmp_path):
        mgr = _fresh_manager(tmp_path)
        album = mgr.create_album(title="Test", manifest={"tracks": []})
        mgr.update_album_status(album.album_id, TaskStatus.COMPLETED, progress="Done")
        updated = mgr.get_album(album.album_id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.progress == "Done"
        assert updated.completed_at is not None

    def test_persistence(self, tmp_path):
        mgr = _fresh_manager(tmp_path)
        album = mgr.create_album(title="Persisted", manifest={"tracks": []})
        album_id = album.album_id

        # New manager instance, same directory
        mgr2 = _fresh_manager(tmp_path)
        restored = mgr2.get_album(album_id)
        assert restored is not None
        assert restored.title == "Persisted"


# ---------------------------------------------------------------------------
# music_generate_album handler
# ---------------------------------------------------------------------------

class TestMusicGenerateAlbumHandler:
    @pytest.fixture(autouse=True)
    def reset_singleton(self, monkeypatch, tmp_path):
        """Give each test a fresh manager in a temp dir."""
        from hermes_sonus import music as _music_mod
        mgr = MusicTaskManager(tmp_path)
        monkeypatch.setattr(_music_mod, "_manager", mgr)
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        monkeypatch.setenv("SUNO_BASE_URL", "https://test.sunoapi.org")
        yield
        monkeypatch.setattr(_music_mod, "_manager", None)

    def test_missing_manifest(self):
        from hermes_sonus.music import _handle_music_generate_album
        result = json.loads(_handle_music_generate_album({}))
        assert result["success"] is False
        assert "manifest_text or manifest_file" in result["error"]

    def test_invalid_manifest_text(self):
        from hermes_sonus.music import _handle_music_generate_album
        result = json.loads(_handle_music_generate_album({"manifest_text": "not yaml or json"}))
        assert result["success"] is False
        assert "Invalid manifest" in result["error"]

    def test_missing_callback(self):
        from hermes_sonus.music import _handle_music_generate_album
        manifest = json.dumps({"tracks": [{"title": "T1"}]})
        result = json.loads(_handle_music_generate_album({"manifest_text": manifest}))
        assert result["success"] is False
        assert "callback_url required" in result["error"]

    @patch("hermes_sonus.mcp.batch_generate.fire_request")
    @patch("hermes_sonus.music.tasks.MusicTaskManager.run_task")
    def test_explicit_mode_blocking(self, mock_run_task, mock_fire):
        from hermes_sonus.music import _handle_music_generate_album, _get_manager
        mock_fire.return_value = {
            "code": 200,
            "data": {"taskId": "suno_abc"},
        }
        mock_run_task.return_value = {
            "success": True,
            "tracks": [{"file": "/tmp/test.mp3", "audio_url": "", "duration": 120, "title": "Song A"}],
            "track_count": 1,
        }

        manifest = {
            "model": "V5",
            "callback_url": "https://test.app/cb",
            "tracks": [
                {"title": "Song A", "styles": "pop", "lyrics": "la la la"},
                {"title": "Song B", "styles": "rock", "lyrics": "na na na"},
            ],
        }
        result = json.loads(_handle_music_generate_album({
            "manifest_text": json.dumps(manifest),
            "blocking": True,
            "callback_url": "https://test.app/cb",
        }))
        assert result["success"] is True
        assert result["track_count"] == 2
        assert result["tracks_fired"] == 2
        assert len(result["track_task_ids"]) == 2
        assert mock_fire.call_count == 2

        # Verify album persisted
        mgr = _get_manager()
        album = mgr.get_album(result["album_id"])
        assert album is not None
        assert album.title == "Album_2tracks"  # fallback since no album_title in manifest

    @patch("hermes_sonus.mcp.batch_generate.fire_request")
    def test_dna_mode(self, mock_fire):
        from hermes_sonus.music import _handle_music_generate_album
        mock_fire.return_value = {
            "code": 200,
            "data": {"taskId": "suno_xyz"},
        }

        manifest = {
            "model": "V5",
            "callback_url": "https://test.app/cb",
            "album_dna": {
                "album_title": "Cosmic Journey",
                "styles": "ambient electronic",
                "weirdness_pct": 40,
            },
            "tracks": [
                {"styles": "ethereal pads"},
                {"styles": "deep bass, tribal drums"},
            ],
        }
        result = json.loads(_handle_music_generate_album({
            "manifest_text": json.dumps(manifest),
            "blocking": False,
            "callback_url": "https://test.app/cb",
        }))
        assert result["success"] is True
        assert result["title"] == "Cosmic Journey"
        assert result["track_count"] == 2
        assert result["tracks_fired"] == 2

    @patch("hermes_sonus.mcp.batch_generate.fire_request")
    def test_continue_on_error(self, mock_fire):
        from hermes_sonus.music import _handle_music_generate_album
        # First call succeeds, second fails
        mock_fire.side_effect = [
            {"code": 200, "data": {"taskId": "suno_1"}},
            {"code": 429, "msg": "Rate limited"},
        ]

        manifest = {
            "model": "V5",
            "callback_url": "https://test.app/cb",
            "tracks": [
                {"title": "Good"},
                {"title": "Bad"},
            ],
        }
        result = json.loads(_handle_music_generate_album({
            "manifest_text": json.dumps(manifest),
            "blocking": False,
            "continue_on_error": True,
        }))
        assert result["success"] is True
        assert result["tracks_fired"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["track"] == 2

    @patch("hermes_sonus.mcp.batch_generate.fire_request")
    def test_stop_on_first_error(self, mock_fire):
        from hermes_sonus.music import _handle_music_generate_album
        mock_fire.return_value = {"code": 429, "msg": "Rate limited"}

        manifest = {
            "callback_url": "https://test.app/cb",
            "tracks": [{"title": "T1"}, {"title": "T2"}],
        }
        result = json.loads(_handle_music_generate_album({
            "manifest_text": json.dumps(manifest),
            "blocking": False,
            "continue_on_error": False,
        }))
        assert result["success"] is True
        assert result["tracks_fired"] == 0
        assert len(result["errors"]) == 1
        assert mock_fire.call_count == 1  # stopped after first failure

    @patch("hermes_sonus.mcp.batch_generate.fire_request")
    def test_manifest_file_path(self, mock_fire, tmp_path):
        from hermes_sonus.music import _handle_music_generate_album
        mock_fire.return_value = {"code": 200, "data": {"taskId": "suno_f"}}

        manifest_path = tmp_path / "album.json"
        manifest_path.write_text(json.dumps({
            "callback_url": "https://test.app/cb",
            "tracks": [{"title": "From File"}],
        }))
        result = json.loads(_handle_music_generate_album({
            "manifest_file": str(manifest_path),
            "blocking": False,
        }))
        assert result["success"] is True
        assert result["track_count"] == 1
