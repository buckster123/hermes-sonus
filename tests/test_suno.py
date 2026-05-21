"""Tests for the Suno API client (mocked)."""

import pytest
from unittest.mock import patch, MagicMock
import requests

from hermes_sonus.music.suno import (
    _get_api_key,
    submit_generation,
    poll_completion,
    download_audio,
    MODEL_LIMITS,
)


class TestApiKey:
    def test_get_api_key_set(self, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key_123")
        assert _get_api_key() == "test_key_123"

    def test_get_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("SUNO_API_KEY", raising=False)
        with pytest.raises(ValueError, match="SUNO_API_KEY not set"):
            _get_api_key()


class TestModelLimits:
    def test_v5_limits(self):
        assert MODEL_LIMITS["V5"]["lyrics"] == 5000
        assert MODEL_LIMITS["V5"]["style"] == 1000

    def test_v4_limits(self):
        assert MODEL_LIMITS["V4"]["lyrics"] == 3000
        assert MODEL_LIMITS["V4"]["style"] == 200


class TestSubmitGeneration:
    @patch("hermes_sonus.music.suno.requests.request")
    def test_successful_submission(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {"taskId": "suno_task_abc123"},
        }
        mock_request.return_value = mock_response

        task_id = submit_generation(prompt="ambient vibes", style="electronic")
        assert task_id == "suno_task_abc123"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_api_error(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("HTTP 500")
        mock_request.return_value = mock_response

        with pytest.raises(requests.HTTPError, match="HTTP 500"):
            submit_generation(prompt="test")


class TestPollCompletion:
    @patch("hermes_sonus.music.suno.requests.request")
    def test_immediate_success(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {
                "response": {
                    "sunoData": [
                        {
                            "audioUrl": "https://example.com/audio.mp3",
                            "title": "Test Track",
                            "duration": 120,
                            "id": "clip_123",
                        }
                    ]
                },
            },
        }
        mock_request.return_value = mock_response

        result = poll_completion("suno_task_abc", max_wait=5)
        assert result["success"] is True
        assert len(result["tracks"]) == 1
        assert result["tracks"][0]["title"] == "Test Track"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_failure(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {
                "status": "FAILED",
                "response": {"errorMessage": "Content policy violation"},
            },
        }
        mock_request.return_value = mock_response

        result = poll_completion("suno_task_abc", max_wait=5)
        assert result["success"] is False
        assert "failed" in result["error"]


class TestDownloadAudio:
    @patch("hermes_sonus.music.suno.requests.request")
    def test_download(self, mock_request, tmp_path, monkeypatch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"fake audio data"]
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        output = str(tmp_path / "test.mp3")
        result = download_audio("https://example.com/audio.mp3", output)
        assert result == output
        assert (tmp_path / "test.mp3").read_bytes() == b"fake audio data"


class TestAdvancedEditing:
    @patch("hermes_sonus.music.suno.requests.request")
    def test_separate_stems(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "stem_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import separate_stems
        result = separate_stems("task_abc", track_index=0)
        assert result == "stem_task_1"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_replace_section(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "replace_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import replace_section
        result = replace_section("task_abc", section_type="chorus", new_lyrics="New chorus line")
        assert result == "replace_task_1"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_boost_style(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "boost_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import boost_style
        result = boost_style("task_abc", target_style="ambient electronic")
        assert result == "boost_task_1"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_convert_to_wav(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "wav_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import convert_to_wav
        result = convert_to_wav("task_abc")
        assert result == "wav_task_1"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_create_music_video(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "video_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import create_music_video
        result = create_music_video("task_abc")
        assert result == "video_task_1"

    @patch("hermes_sonus.music.suno.requests.request")
    def test_generate_sounds(self, mock_request, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "test_key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": {"taskId": "sound_task_1"}}
        mock_request.return_value = mock_response

        from hermes_sonus.music.suno import generate_sounds
        result = generate_sounds("thunderstorm with distant wolves", duration=10)
        assert result == "sound_task_1"
