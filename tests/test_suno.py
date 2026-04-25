"""Tests for the Suno API client (mocked)."""

import pytest
from unittest.mock import patch, MagicMock

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
        assert MODEL_LIMITS["V5"]["prompt"] == 5000
        assert MODEL_LIMITS["V5"]["style"] == 1000

    def test_v3_5_limits(self):
        assert MODEL_LIMITS["V3_5"]["prompt"] == 3000


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
        mock_response.text = "Internal Server Error"
        mock_request.return_value = mock_response

        with pytest.raises(Exception, match="HTTP 500"):
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
                "status": "SUCCESS",
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
        assert "Content policy" in result["error"]


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
