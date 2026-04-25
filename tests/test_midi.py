"""Tests for MIDI creation."""

import pytest
from pathlib import Path

from hermes_sonus.music.midi import create_midi, _parse_note, HAS_MIDIUTIL


class TestParseNote:
    def test_midi_number_string(self):
        assert _parse_note("60") == 60

    def test_c4(self):
        assert _parse_note("C4") == 60

    def test_a4(self):
        assert _parse_note("A4") == 69

    def test_sharp(self):
        assert _parse_note("F#4") == 66

    def test_case_insensitive(self):
        assert _parse_note("c4") == 60
        assert _parse_note("f#3") == 54

    def test_default_octave(self):
        assert _parse_note("C") == 60  # Default octave 4

    def test_invalid_note(self):
        with pytest.raises(ValueError, match="Invalid note"):
            _parse_note("X4")


@pytest.mark.skipif(not HAS_MIDIUTIL, reason="midiutil not installed")
class TestCreateMidi:
    def test_basic_creation(self, tmp_path):
        result = create_midi(
            notes=[60, 64, 67, 72],
            tempo=120,
            title="test_melody",
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["note_count"] == 4
        assert result["tempo"] == 120
        assert Path(result["midi_file"]).exists()

    def test_note_names(self, tmp_path):
        result = create_midi(
            notes=["C4", "E4", "G4", "C5"],
            title="note_names",
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["note_count"] == 4

    def test_rests(self, tmp_path):
        result = create_midi(
            notes=["C4", "R", "E4", 0, "G4"],
            title="with_rests",
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["note_count"] == 3  # R and 0 are rests

    def test_sharps_and_flats(self, tmp_path):
        result = create_midi(
            notes=["F#4", "Bb3", "C#5"],
            title="accidentals",
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["note_count"] == 3

    def test_duration_calculation(self, tmp_path):
        result = create_midi(
            notes=[60, 64, 67, 72],
            tempo=60,  # 1 beat per second
            note_duration=1.0,
            title="duration_test",
            output_dir=tmp_path,
        )
        assert result["success"] is True
        assert result["duration_seconds"] == 4.0  # 4 notes * 1 beat * 1 sec/beat

    def test_invalid_note(self, tmp_path):
        result = create_midi(
            notes=[60, None],  # None is invalid
            title="invalid",
            output_dir=tmp_path,
        )
        assert result["success"] is False

    def test_empty_notes(self, tmp_path):
        result = create_midi(notes=[], title="empty", output_dir=tmp_path)
        assert result["success"] is True
        assert result["note_count"] == 0


class TestCreateMidiNoMidiutil:
    def test_missing_midiutil_error(self, tmp_path, monkeypatch):
        import hermes_sonus.music.midi as midi_mod
        monkeypatch.setattr(midi_mod, "HAS_MIDIUTIL", False)
        result = create_midi(notes=[60], output_dir=tmp_path)
        assert result["success"] is False
        assert "midiutil" in result["error"]
