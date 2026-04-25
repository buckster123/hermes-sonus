"""
Audio Player for Hermes Music Plugin

Detects available audio players (mpg123, ffplay, aplay, paplay) and provides
non-blocking playback with auto-stop of previous tracks.
"""

import logging
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Currently playing process — module-level singleton for auto-stop
_current_player: Optional[subprocess.Popen] = None
_current_file: Optional[str] = None

# Player preference order
PLAYER_COMMANDS = ["mpg123", "ffplay", "aplay", "paplay"]

# How each player takes a file argument
PLAYER_ARGS = {
    "mpg123": lambda f: ["mpg123", f],
    "ffplay": lambda f: ["ffplay", "-nodisp", "-autoexit", f],
    "aplay": lambda f: ["aplay", f],
    "paplay": lambda f: ["paplay", f],
}

# Install hints per platform
INSTALL_HINTS = {
    "mpg123": "sudo apt install mpg123  (or brew install mpg123 on macOS)",
    "ffplay": "sudo apt install ffmpeg  (or brew install ffmpeg on macOS)",
}


def find_player() -> Optional[str]:
    """Find the best available audio player on this system.

    Returns the command name or None if nothing found.
    """
    for cmd in PLAYER_COMMANDS:
        if shutil.which(cmd):
            return cmd
    return None


def get_player_info() -> Dict[str, Any]:
    """Return info about available audio players."""
    available = []
    for cmd in PLAYER_COMMANDS:
        path = shutil.which(cmd)
        if path:
            available.append({"name": cmd, "path": path})

    return {
        "available": available,
        "preferred": available[0]["name"] if available else None,
        "count": len(available),
    }


def play_audio(
    file_path: str,
    player: Optional[str] = None,
    auto_stop: bool = True,
) -> Dict[str, Any]:
    """Play an audio file in the background.

    Args:
        file_path: Path to the audio file (mp3, wav, etc.)
        player: Force a specific player. Auto-detects if None.
        auto_stop: If True, stop any currently playing track first.

    Returns:
        Dict with success, pid, player used, etc.
    """
    global _current_player, _current_file

    # Validate file exists
    p = Path(file_path)
    if not p.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    # Find player
    if player:
        if not shutil.which(player):
            return {"success": False, "error": f"Player '{player}' not found on this system"}
    else:
        player = find_player()
        if not player:
            hints = "\n".join(f"  {h}" for h in INSTALL_HINTS.values())
            return {
                "success": False,
                "error": f"No audio player found. Install one:\n{hints}",
            }

    # Auto-stop previous playback
    if auto_stop:
        stop_result = stop_playback()
        if stop_result.get("was_playing"):
            logger.info("Auto-stopped previous playback: %s", stop_result.get("file"))

    # Build command
    cmd_builder = PLAYER_ARGS.get(player)
    if not cmd_builder:
        return {"success": False, "error": f"Unknown player: {player}"}

    cmd = cmd_builder(str(p))

    try:
        # Launch in background, suppress output
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,  # own process group for clean kill
        )
        _current_player = proc
        _current_file = str(p)

        logger.info("Playing %s with %s (pid %d)", p.name, player, proc.pid)
        return {
            "success": True,
            "file": str(p),
            "player": player,
            "pid": proc.pid,
        }

    except Exception as e:
        logger.error("Failed to start playback: %s", e)
        return {"success": False, "error": f"Playback failed: {e}"}


def stop_playback() -> Dict[str, Any]:
    """Stop the currently playing audio."""
    global _current_player, _current_file

    if _current_player is None:
        return {"success": True, "was_playing": False, "message": "Nothing is playing"}

    was_file = _current_file
    was_pid = _current_player.pid

    try:
        # Check if still running
        if _current_player.poll() is None:
            # Kill the entire process group
            try:
                os.killpg(os.getpgid(_current_player.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                # Process already gone or can't kill group, try direct
                try:
                    _current_player.terminate()
                except ProcessLookupError:
                    pass

            # Brief wait for clean shutdown
            try:
                _current_player.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(_current_player.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        _current_player.kill()
                    except ProcessLookupError:
                        pass

            logger.info("Stopped playback (pid %d): %s", was_pid, was_file)
            _current_player = None
            _current_file = None
            return {
                "success": True,
                "was_playing": True,
                "stopped_pid": was_pid,
                "file": was_file,
                "message": f"Stopped playback: {Path(was_file).name if was_file else 'unknown'}",
            }
        else:
            # Already finished
            _current_player = None
            _current_file = None
            return {"success": True, "was_playing": False, "message": "Previous track already finished"}

    except Exception as e:
        logger.error("Error stopping playback: %s", e)
        _current_player = None
        _current_file = None
        return {"success": False, "error": str(e)}


def is_playing() -> Dict[str, Any]:
    """Check if audio is currently playing."""
    global _current_player, _current_file

    if _current_player is None:
        return {"playing": False}

    if _current_player.poll() is None:
        return {
            "playing": True,
            "file": _current_file,
            "pid": _current_player.pid,
        }
    else:
        # Process finished
        _current_player = None
        _current_file = None
        return {"playing": False}
