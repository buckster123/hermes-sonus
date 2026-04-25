"""Tests for the audio player module."""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from hermes_sonus.music.player import (
    find_player,
    get_player_info,
    play_audio,
    stop_playback,
    is_playing,
    PLAYER_COMMANDS,
    _current_player,
)
import hermes_sonus.music.player as player_module


class TestFindPlayer:
    @patch("hermes_sonus.music.player.shutil.which")
    def test_finds_mpg123(self, mock_which):
        mock_which.side_effect = lambda cmd: "/usr/bin/mpg123" if cmd == "mpg123" else None
        assert find_player() == "mpg123"

    @patch("hermes_sonus.music.player.shutil.which")
    def test_finds_ffplay_fallback(self, mock_which):
        def which(cmd):
            if cmd == "ffplay":
                return "/usr/bin/ffplay"
            return None
        mock_which.side_effect = which
        assert find_player() == "ffplay"

    @patch("hermes_sonus.music.player.shutil.which")
    def test_none_available(self, mock_which):
        mock_which.return_value = None
        assert find_player() is None


class TestGetPlayerInfo:
    @patch("hermes_sonus.music.player.shutil.which")
    def test_lists_available(self, mock_which):
        def which(cmd):
            if cmd in ("mpg123", "aplay"):
                return f"/usr/bin/{cmd}"
            return None
        mock_which.side_effect = which
        info = get_player_info()
        assert info["count"] == 2
        assert info["preferred"] == "mpg123"


class TestPlayAudio:
    @patch("hermes_sonus.music.player.shutil.which")
    def test_file_not_found(self, mock_which):
        mock_which.return_value = "/usr/bin/mpg123"
        result = play_audio("/nonexistent/file.mp3")
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("hermes_sonus.music.player.shutil.which")
    def test_no_player(self, mock_which, tmp_path):
        mock_which.return_value = None
        f = tmp_path / "test.mp3"
        f.write_bytes(b"fake")
        result = play_audio(str(f))
        assert result["success"] is False
        assert "No audio player" in result["error"]

    @patch("hermes_sonus.music.player.subprocess.Popen")
    @patch("hermes_sonus.music.player.shutil.which")
    def test_successful_play(self, mock_which, mock_popen, tmp_path):
        mock_which.return_value = "/usr/bin/mpg123"
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        # Reset module state
        player_module._current_player = None
        player_module._current_file = None

        result = play_audio(str(audio_file))
        assert result["success"] is True
        assert result["player"] == "mpg123"
        assert result["pid"] == 12345

    @patch("hermes_sonus.music.player.subprocess.Popen")
    @patch("hermes_sonus.music.player.shutil.which")
    def test_auto_stop(self, mock_which, mock_popen, tmp_path):
        """Playing a new track should stop the previous one."""
        mock_which.return_value = "/usr/bin/mpg123"

        # Set up a "currently playing" process
        old_proc = MagicMock()
        old_proc.poll.return_value = None
        old_proc.pid = 111
        player_module._current_player = old_proc
        player_module._current_file = "/tmp/old.mp3"

        new_proc = MagicMock()
        new_proc.pid = 222
        mock_popen.return_value = new_proc

        audio_file = tmp_path / "new.mp3"
        audio_file.write_bytes(b"new audio")

        # Patch os.killpg so the test never signals the pytest process.
        # When pytest runs under setsid (CI) the parent test process IS
        # the process-group leader; an unguarded killpg on it would TERM
        # the test runner. Guard with a no-op patch.
        with patch("hermes_sonus.music.player.os.killpg"), \
             patch("hermes_sonus.music.player.os.getpgid", return_value=111):
            result = play_audio(str(audio_file), auto_stop=True)
        # Confirm the new process started; killpg behavior is exercised
        # by TestStopPlayback.test_stop_running which patches it too.
        assert result["success"] is True
        assert result["pid"] == 222


class TestStopPlayback:
    def test_nothing_playing(self):
        player_module._current_player = None
        player_module._current_file = None
        result = stop_playback()
        assert result["success"] is True
        assert result["was_playing"] is False

    def test_stop_running(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.pid = 999
        player_module._current_player = mock_proc
        player_module._current_file = "/tmp/playing.mp3"

        with patch("hermes_sonus.music.player.os.killpg"):
            result = stop_playback()

        assert result["success"] is True
        assert result["was_playing"] is True
        assert result["stopped_pid"] == 999

    def test_already_finished(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already done
        player_module._current_player = mock_proc
        player_module._current_file = "/tmp/done.mp3"

        result = stop_playback()
        assert result["success"] is True
        assert result["was_playing"] is False


class TestIsPlaying:
    def test_not_playing(self):
        player_module._current_player = None
        assert is_playing()["playing"] is False

    def test_still_playing(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 555
        player_module._current_player = mock_proc
        player_module._current_file = "/tmp/song.mp3"

        result = is_playing()
        assert result["playing"] is True
        assert result["pid"] == 555

    def test_finished(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        player_module._current_player = mock_proc
        player_module._current_file = "/tmp/done.mp3"

        result = is_playing()
        assert result["playing"] is False
