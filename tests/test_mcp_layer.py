"""Tests for the Hermes-Sonus MCP layer."""

import json
import pytest

from hermes_sonus.mcp.build_payload import (
    ParsedFields,
    build_payload,
    merge_unhinged_seed_into_lyrics,
    parse_input,
    validate_limits,
    MODEL_LIMITS,
)
from hermes_sonus.mcp.poll_status import (
    extract_audio_urls,
    extract_status,
    TERMINAL_STATES,
)
from hermes_sonus.mcp.batch_generate import (
    parse_manifest,
    fields_dict_to_parsed,
    detect_instrumental,
    merge_field,
)


class TestParseInput:
    def test_basic_fields(self):
        text = """STYLES: electronic ambient, 120BPM
LYRICS: [Verse]
Hello world
TITLE: Test Song
WEIRDNESS: 60%
STYLE: 40%
"""
        fields = parse_input(text)
        assert fields.styles == "electronic ambient, 120BPM"
        assert fields.lyrics == "[Verse]\nHello world"
        assert fields.title == "Test Song"
        assert fields.weirdness_pct == 0.6
        assert fields.style_pct == 0.4

    def test_no_fields_fallback(self):
        fields = parse_input("just some random text")
        assert fields.lyrics == "just some random text"

    def test_unhinged_seed(self):
        text = "STYLES: test\nUNHINGED_SEED: satirical description here"
        fields = parse_input(text)
        assert fields.unhinged_seed == "satirical description here"


class TestBuildPayload:
    def test_basic_payload(self):
        fields = ParsedFields()
        fields.styles = "electronic"
        fields.lyrics = "[Verse]\nHello"
        fields.title = "Test"
        fields.weirdness_pct = 0.6
        fields.style_pct = 0.4

        payload = build_payload(fields, "V5", "https://cb.example", False, True)
        assert payload["customMode"] is True
        assert payload["instrumental"] is False
        assert payload["model"] == "V5"
        assert payload["style"] == "electronic"
        assert payload["prompt"] == "[Verse]\nHello"
        assert payload["title"] == "Test"
        assert payload["weirdnessConstraint"] == 0.6
        assert payload["styleWeight"] == 0.4

    def test_instrumental_no_lyrics(self):
        fields = ParsedFields()
        fields.styles = "ambient"
        payload = build_payload(fields, "V5", "https://cb.example", True, True)
        assert payload["instrumental"] is True
        assert "prompt" not in payload

    def test_non_custom_mode(self):
        fields = ParsedFields()
        fields.lyrics = "A short description"
        payload = build_payload(fields, "V5", "https://cb.example", False, False)
        assert payload["customMode"] is False
        assert payload["prompt"] == "A short description"


class TestValidateLimits:
    def test_v5_within_limits(self):
        fields = ParsedFields()
        fields.styles = "a" * 1000
        fields.lyrics = "b" * 4000
        fields.title = "c" * 100
        warnings = validate_limits(fields, "V5", False, True)
        assert not warnings

    def test_style_overflow(self):
        fields = ParsedFields()
        fields.styles = "a" * 1001
        warnings = validate_limits(fields, "V5", True, True)
        assert any("STYLES is 1001 chars" in w for w in warnings)

    def test_lyrics_stability_target(self):
        fields = ParsedFields()
        fields.styles = "test"
        fields.lyrics = "b" * 4100
        warnings = validate_limits(fields, "V5", False, True)
        assert any("stability target" in w for w in warnings)

    def test_missing_required(self):
        fields = ParsedFields()
        warnings = validate_limits(fields, "V5", False, True)
        assert any("STYLES is empty" in w for w in warnings)
        assert any("LYRICS is empty" in w for w in warnings)


class TestMergeUnhingedSeed:
    def test_into_lyrics(self):
        fields = ParsedFields()
        fields.lyrics = "hello"
        fields.unhinged_seed = "[[[seed]]]"
        merge_unhinged_seed_into_lyrics(fields)
        assert "hello" in fields.lyrics
        assert "[[[seed]]]" in fields.lyrics

    def test_into_styles_when_no_lyrics(self):
        fields = ParsedFields()
        fields.styles = "ambient"
        fields.unhinged_seed = "[[[seed]]]"
        merge_unhinged_seed_into_lyrics(fields)
        assert "[[[seed]]]" in fields.styles


class TestExtractStatus:
    def test_complete_from_sunodata(self):
        resp = {
            "code": 200,
            "data": {
                "response": {
                    "sunoData": [{"audioUrl": "https://x.mp3"}]
                }
            }
        }
        assert extract_status(resp) == "complete"

    def test_pending(self):
        resp = {"code": 200, "data": {"status": "pending"}}
        assert extract_status(resp) == "pending"

    def test_error(self):
        resp = {"code": 500, "msg": "fail", "_error": True}
        assert extract_status(resp) == "error"

    def test_nested_status(self):
        resp = {"code": 200, "data": {"response": {"status": "complete"}}}
        assert extract_status(resp) == "complete"


class TestExtractAudioUrls:
    def test_from_sunodata(self):
        resp = {
            "code": 200,
            "data": {
                "response": {
                    "sunoData": [
                        {
                            "audioUrl": "https://x.mp3",
                            "title": "Song",
                            "id": "abc",
                        }
                    ]
                }
            }
        }
        tracks = extract_audio_urls(resp)
        assert len(tracks) == 1
        assert tracks[0]["audio_url"] == "https://x.mp3"

    def test_empty(self):
        assert extract_audio_urls({}) == []


class TestTerminalStates:
    def test_terminal_membership(self):
        assert "complete" in TERMINAL_STATES
        assert "error" in TERMINAL_STATES
        assert "failed" in TERMINAL_STATES
        assert "pending" not in TERMINAL_STATES


class TestBatchManifest:
    def test_explicit_mode(self):
        manifest = {
            "model": "V5",
            "callback_url": "https://cb.example",
            "tracks": [
                {"title": "Track 1", "styles": "ambient", "lyrics": "hello"},
                {"title": "Track 2", "styles": "metal", "lyrics": "world"},
            ],
        }
        tracks, settings = parse_manifest(manifest)
        assert len(tracks) == 2
        assert tracks[0]["title"] == "Track 1"
        assert tracks[1]["styles"] == "metal"

    def test_dna_mode(self):
        manifest = {
            "model": "V5",
            "callback_url": "https://cb.example",
            "album_dna": {
                "album_title": "Test Album",
                "styles": "ambient",
                "weirdness_pct": 35,
            },
            "tracks": [
                {"styles": "ethereal pads"},
                {"styles": "tribal percussion", "weirdness_pct": 50},
            ],
        }
        tracks, settings = parse_manifest(manifest)
        assert len(tracks) == 2
        assert "ambient" in tracks[0]["styles"]
        assert "ethereal pads" in tracks[0]["styles"]
        assert tracks[0]["weirdness_pct"] == 35
        assert tracks[1]["weirdness_pct"] == 50

    def test_dna_override_sigil(self):
        manifest = {
            "model": "V5",
            "tracks": [
                {"styles": "! pure noise"},
            ],
            "album_dna": {"styles": "ambient"},
        }
        tracks, _ = parse_manifest(manifest)
        assert tracks[0]["styles"] == "pure noise"

    def test_invalid_manifest(self):
        with pytest.raises(ValueError, match="'tracks' key"):
            parse_manifest({"model": "V5"})


class TestDetectInstrumental:
    def test_symbolic(self):
        fields = ParsedFields()
        fields.lyrics = "≈≈≈♫≈≈≈ ∞♪∞"
        assert detect_instrumental(fields, None) is True

    def test_real_words(self):
        fields = ParsedFields()
        fields.lyrics = "Hello world this is lyrics"
        assert detect_instrumental(fields, None) is False

    def test_override(self):
        fields = ParsedFields()
        fields.lyrics = "hello"
        assert detect_instrumental(fields, True) is True


class TestFieldsDictToParsed:
    def test_conversion(self):
        d = {
            "styles": "ambient",
            "weirdness_pct": "60%",
            "style_pct": 0.4,
            "unhinged_seed": "seed",
        }
        fields = fields_dict_to_parsed(d)
        assert fields.styles == "ambient"
        assert fields.weirdness_pct == 0.6
        assert fields.style_pct == 0.4
        assert fields.unhinged_seed == "seed"
