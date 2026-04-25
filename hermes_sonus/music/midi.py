"""
MIDI Creation for Hermes Music Plugin

Create MIDI files from note names/numbers for use with the composition pipeline.
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

try:
    from midiutil import MIDIFile
    HAS_MIDIUTIL = True
except ImportError:
    HAS_MIDIUTIL = False
    MIDIFile = None  # type: ignore[misc,assignment]


# Note name → semitone offset
NOTE_MAP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _parse_note(note_str: str) -> int:
    """Parse note string to MIDI number. Supports 'C4', 'F#3', 'Bb5', or '60'."""
    note_str = note_str.strip()

    if note_str.isdigit():
        return int(note_str)

    note_str = note_str.upper()
    base_note = note_str[0]
    if base_note not in NOTE_MAP:
        raise ValueError(f"Invalid note: {note_str}")

    midi_num = NOTE_MAP[base_note]
    idx = 1

    if len(note_str) > idx:
        if note_str[idx] == "#":
            midi_num += 1
            idx += 1
        elif note_str[idx] == "B" and idx + 1 < len(note_str):
            # Flat — but only if followed by a digit (octave), not another note letter
            midi_num -= 1
            idx += 1

    octave = int(note_str[idx:]) if idx < len(note_str) else 4
    return midi_num + (octave + 1) * 12


def create_midi(
    notes: List[Union[int, str]],
    tempo: int = 120,
    note_duration: float = 0.5,
    title: str = "composition",
    velocity: int = 100,
    rest_between: float = 0.0,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Create a MIDI file from a list of notes.

    Args:
        notes: MIDI numbers (60) or note names ('C4', 'F#3'). Use 0 or 'R' for rests.
        tempo: BPM (default 120)
        note_duration: Duration per note in beats (0.5 = eighth note)
        title: Filename stem
        velocity: Note loudness 0-127
        rest_between: Gap between notes in beats
        output_dir: Directory for output (defaults to current dir)

    Returns:
        Dict with midi_file path and composition details.
    """
    if not HAS_MIDIUTIL:
        return {
            "success": False,
            "error": "midiutil not installed. Run: pip install hermes-music[midi]",
        }

    try:
        parsed_notes = []
        for note in notes:
            if note == 0 or (isinstance(note, str) and note.upper() == "R"):
                parsed_notes.append(None)  # Rest
            elif isinstance(note, int):
                parsed_notes.append(note)
            elif isinstance(note, str):
                parsed_notes.append(_parse_note(note))
            else:
                return {"success": False, "error": f"Invalid note format: {note}"}

        midi = MIDIFile(1)
        track = 0
        channel = 0
        current_time = 0.0

        midi.addTempo(track, 0, tempo)

        note_count = 0
        for note in parsed_notes:
            if note is not None:
                midi.addNote(track, channel, note, current_time, note_duration, velocity)
                note_count += 1
            current_time += note_duration + rest_between

        safe_title = re.sub(r"[^\w\-]", "_", title)
        timestamp = int(time.time())
        filename = f"{safe_title}_{timestamp}.mid"

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            midi_path = output_dir / filename
        else:
            midi_path = Path(filename)

        with open(midi_path, "wb") as f:
            midi.writeFile(f)

        total_duration = current_time * (60 / tempo)

        return {
            "success": True,
            "midi_file": str(midi_path),
            "title": title,
            "note_count": note_count,
            "tempo": tempo,
            "duration_seconds": round(total_duration, 2),
            "duration_beats": round(current_time, 2),
            "message": f"MIDI created: {filename}. Use with music_compose(midi_file='{midi_path}', ...)",
        }

    except Exception as e:
        logger.error("Error creating MIDI: %s", e)
        return {"success": False, "error": str(e)}
