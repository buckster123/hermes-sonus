"""
Hermes Music Plugin
===================

Music generation for Hermes Agent — Suno AI generation, MIDI composition,
and music library management.

Provides 12 tools in the "music" toolset:
  - music_generate, music_status, music_result, music_list
  - music_favorite, music_library, music_search, music_play
  - music_stop, music_delete
  - midi_create, music_compose

Install: pip install hermes-music
Config:  SUNO_API_KEY in ~/.hermes/.env
"""

__version__ = "1.0.0"

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton for the task manager
# ---------------------------------------------------------------------------

_manager: Optional["tasks.MusicTaskManager"] = None


def _get_data_dir() -> Path:
    """Get the music plugin data directory, respecting Hermes profiles."""
    try:
        from hermes_constants import get_hermes_home
        base = get_hermes_home()
    except ImportError:
        base = Path.home() / ".hermes"
    return base / "sonus" / "music"


def _get_manager():
    """Get or create the singleton MusicTaskManager."""
    global _manager
    if _manager is None:
        from .tasks import MusicTaskManager
        _manager = MusicTaskManager(_get_data_dir())
    return _manager


# ---------------------------------------------------------------------------
# Check function — tools only appear when SUNO_API_KEY is set
# ---------------------------------------------------------------------------

def _check_suno_available() -> bool:
    return bool(os.environ.get("SUNO_API_KEY"))


def _check_midi_available() -> bool:
    """MIDI tools work without API key (local only), just need midiutil."""
    try:
        import midiutil  # noqa: F401
        return True
    except ImportError:
        return False


def _check_always() -> bool:
    """Tools that always work (music_stop, etc.)."""
    return True


# ---------------------------------------------------------------------------
# Tool handlers — thin wrappers that return JSON strings
# ---------------------------------------------------------------------------

def _handle_music_generate(args: dict, **kw) -> str:
    from .tasks import TaskStatus
    manager = _get_manager()

    prompt = args.get("prompt", "")
    style = args.get("style", "")
    title = args.get("title", "")
    model = args.get("model", "V5")
    is_instrumental = args.get("is_instrumental", True)
    blocking = args.get("blocking", True)
    agent_id = args.get("agent_id", "")

    task = manager.create_task(
        prompt=prompt,
        style=style,
        title=title,
        model=model,
        is_instrumental=is_instrumental,
        agent_id=agent_id or None,
    )

    if blocking:
        result = manager.run_task(task.task_id)
        task = manager.get_task(task.task_id)
        if result.get("success"):
            return json.dumps({
                "success": True,
                "task_id": task.task_id,
                "title": task.title,
                "audio_file": task.audio_file,
                "audio_url": task.audio_url,
                "duration": task.duration,
                "tracks": result.get("tracks", []),
                "track_count": result.get("track_count", 1),
                "message": f"Music generated: {task.title} ({task.duration:.0f}s) — {result.get('track_count', 1)} tracks",
            })
        else:
            return json.dumps({
                "success": False,
                "task_id": task.task_id,
                "error": result.get("error", "Generation failed"),
            })
    else:
        # Async: run in background thread
        thread = threading.Thread(target=manager.run_task, args=(task.task_id,), daemon=True)
        thread.start()
        return json.dumps({
            "success": True,
            "task_id": task.task_id,
            "status": "generating",
            "message": f"Generation started. Poll with music_status('{task.task_id}'). Takes 2-4 minutes.",
        })


def _handle_music_status(args: dict, **kw) -> str:
    manager = _get_manager()
    task_id = args.get("task_id", "")
    task = manager.get_task(task_id)

    if not task:
        return json.dumps({"error": f"Task {task_id} not found"})

    elapsed = ""
    if task.started_at:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(task.started_at)
            elapsed = f"{(datetime.now() - start).total_seconds():.0f}s"
        except Exception:
            pass

    return json.dumps({
        "task_id": task.task_id,
        "status": task.status.value,
        "progress": task.progress,
        "title": task.title,
        "elapsed": elapsed,
        "model": task.model,
        "track_count": task.track_count,
    })


def _handle_music_result(args: dict, **kw) -> str:
    manager = _get_manager()
    task_id = args.get("task_id", "")
    task = manager.get_task(task_id)

    if not task:
        return json.dumps({"error": f"Task {task_id} not found"})

    from .tasks import TaskStatus
    if task.status != TaskStatus.COMPLETED:
        return json.dumps({
            "error": f"Task not completed yet. Status: {task.status.value}",
            "progress": task.progress,
        })

    tracks = []
    for i, t in enumerate(task.tracks, 1):
        tracks.append({
            "track": i,
            "file": t.file,
            "duration": t.duration,
            "clip_id": t.clip_id,
            "audio_url": t.audio_url,
            "favorite": t.favorite,
            "archived": t.archived,
        })

    return json.dumps({
        "task_id": task.task_id,
        "title": task.title,
        "audio_file": task.audio_file,
        "audio_url": task.audio_url,
        "duration": task.duration,
        "clip_id": task.clip_id,
        "model": task.model,
        "is_instrumental": task.is_instrumental,
        "track_count": task.track_count,
        "tracks": tracks,
    })


def _handle_music_list(args: dict, **kw) -> str:
    manager = _get_manager()
    limit = args.get("limit", 10)
    tasks = manager.list_tasks(limit=limit)

    return json.dumps({
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title or "Untitled",
                "status": t.status.value,
                "model": t.model,
                "duration": t.duration,
                "audio_file": t.audio_file,
                "agent_id": t.agent_id,
                "track_count": t.track_count,
                "created_at": t.created_at,
            }
            for t in tasks
        ],
        "count": len(tasks),
        "total": len(manager.tasks),
    })


def _handle_music_favorite(args: dict, **kw) -> str:
    from .library import toggle_favorite
    manager = _get_manager()
    return json.dumps(toggle_favorite(
        manager,
        task_id=args.get("task_id", ""),
        track=args.get("track"),
        favorite=args.get("favorite"),
    ))


def _handle_music_library(args: dict, **kw) -> str:
    from .library import browse_library
    manager = _get_manager()
    return json.dumps(browse_library(
        manager,
        agent_id=args.get("agent_id"),
        favorites_only=args.get("favorites_only", False),
        status=args.get("status"),
        limit=args.get("limit", 20),
    ))


def _handle_music_search(args: dict, **kw) -> str:
    from .library import search_songs
    manager = _get_manager()
    return json.dumps(search_songs(
        manager,
        query=args.get("query", ""),
        limit=args.get("limit", 10),
    ))


def _handle_music_play(args: dict, **kw) -> str:
    from .library import play_song
    manager = _get_manager()
    return json.dumps(play_song(
        manager,
        task_id=args.get("task_id", ""),
        track=args.get("track", 1),
    ))


def _handle_music_stop(args: dict, **kw) -> str:
    from .player import stop_playback, is_playing
    status = is_playing()
    if not status.get("playing"):
        return json.dumps({"success": True, "message": "Nothing is currently playing"})
    result = stop_playback()
    return json.dumps(result)


def _handle_music_delete(args: dict, **kw) -> str:
    manager = _get_manager()
    task_id = args.get("task_id", "")
    track = args.get("track")
    permanent = args.get("permanent", False)

    if not task_id:
        return json.dumps({"success": False, "error": "task_id is required"})

    if track is not None:
        # Single track operation
        if permanent:
            result = manager.delete_track(task_id, track)
        else:
            result = manager.archive_track(task_id, track)
    else:
        # Whole task
        if permanent:
            result = manager.delete_task(task_id)
        else:
            result = manager.archive_task(task_id)

    return json.dumps(result)


def _handle_midi_create(args: dict, **kw) -> str:
    from .midi import create_midi
    manager = _get_manager()
    return json.dumps(create_midi(
        notes=args.get("notes", []),
        tempo=args.get("tempo", 120),
        note_duration=args.get("note_duration", 0.5),
        title=args.get("title", "composition"),
        velocity=args.get("velocity", 100),
        rest_between=args.get("rest_between", 0.0),
        output_dir=manager.midi_dir,
    ))


def _handle_music_compose(args: dict, **kw) -> str:
    from . import suno
    from .tasks import TaskStatus
    manager = _get_manager()

    midi_file = args.get("midi_file", "")
    style = args.get("style", "")
    title = args.get("title", "")
    audio_influence = args.get("audio_influence", 0.5)
    prompt = args.get("prompt", "")
    instrumental = args.get("instrumental", True)
    style_weight = args.get("style_weight", 0.5)
    weirdness = args.get("weirdness", 0.3)
    model = args.get("model", "V5")
    blocking = args.get("blocking", True)
    agent_id = args.get("agent_id", "")

    midi_path = Path(midi_file)
    if not midi_path.exists():
        return json.dumps({"success": False, "error": f"MIDI file not found: {midi_file}"})

    # Step 1: Convert MIDI to audio
    temp_mp3 = str(manager.music_dir / f"_compose_ref_{int(time.time())}.mp3")
    convert_result = _midi_to_audio(str(midi_path), temp_mp3)
    if not convert_result.get("success"):
        return json.dumps({"success": False, "error": f"MIDI conversion failed: {convert_result.get('error')}"})

    # Step 2: Upload to Suno
    upload_result = suno.upload_audio(convert_result["audio_path"])
    _cleanup_file(temp_mp3)
    if not upload_result.get("success"):
        return json.dumps({"success": False, "error": f"Upload failed: {upload_result.get('error')}"})

    # Step 3: Submit upload-cover
    cover_result = suno.submit_upload_cover(
        upload_url=upload_result["upload_url"],
        style=style,
        title=title,
        prompt=prompt,
        instrumental=instrumental,
        audio_weight=audio_influence,
        style_weight=style_weight,
        weirdness=weirdness,
        model=model,
    )
    if not cover_result.get("success"):
        return json.dumps({"success": False, "error": f"Upload-cover failed: {cover_result.get('error')}"})

    # Create task to track
    task = manager.create_task(
        prompt=f"[COMPOSED] {prompt}" if prompt else f"[COMPOSED] {style}",
        style=style,
        title=title,
        model=model,
        is_instrumental=instrumental,
        agent_id=agent_id or None,
    )
    task.suno_task_id = cover_result["suno_task_id"]
    task.status = TaskStatus.GENERATING
    task.started_at = __import__("datetime").datetime.now().isoformat()
    task.progress = f"Composing with audio_influence={audio_influence:.2f}..."
    manager._save_tasks()

    if blocking:
        result = manager.run_task(task.task_id)
        task = manager.get_task(task.task_id)
        if result.get("success"):
            return json.dumps({
                "success": True,
                "task_id": task.task_id,
                "audio_file": task.audio_file,
                "title": task.title,
                "duration": task.duration,
                "track_count": task.track_count,
                "tracks": result.get("tracks", []),
                "audio_influence": audio_influence,
                "style": style,
                "message": f"Composition complete: {task.title} ({task.track_count} tracks)",
            })
        else:
            return json.dumps({
                "success": False,
                "task_id": task.task_id,
                "error": result.get("error", "Generation failed"),
            })
    else:
        thread = threading.Thread(target=manager.run_task, args=(task.task_id,), daemon=True)
        thread.start()
        return json.dumps({
            "success": True,
            "task_id": task.task_id,
            "status": "generating",
            "audio_influence": audio_influence,
            "message": f"Composition started. Poll with music_status('{task.task_id}'). Takes 2-4 minutes.",
        })


def _midi_to_audio(midi_path: str, output_path: str) -> Dict[str, Any]:
    """Convert MIDI to audio using timidity or fluidsynth."""
    for cmd_template in [
        ["timidity", midi_path, "-Ow", "-o", output_path],
        ["fluidsynth", "-ni", "/usr/share/sounds/sf2/FluidR3_GM.sf2", midi_path, "-F", output_path, "-r", "44100"],
    ]:
        try:
            result = subprocess.run(cmd_template, capture_output=True, timeout=30)
            if result.returncode == 0 and Path(output_path).exists():
                return {"success": True, "audio_path": output_path}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return {
        "success": False,
        "error": "No MIDI synthesizer found. Install timidity or fluidsynth: "
                 "sudo apt install timidity (or brew install timidity)",
    }


def _cleanup_file(path: str):
    """Silently remove a file."""
    try:
        Path(path).unlink()
    except Exception:
        pass


def _handle_music_check_credits(args: dict, **kw) -> str:
    from . import suno
    try:
        result = suno.check_credits()
        data = result.get("data", {})
        return json.dumps({
            "success": True,
            "credits_remaining": data.get("remaining", "unknown"),
            "credits_total": data.get("total", "unknown"),
            "raw": result,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_generate_album(args: dict, **kw) -> str:
    """Generate multiple coherent tracks from a manifest (DNA or explicit mode)."""
    from pathlib import Path as _Path
    from hermes_sonus.mcp.batch_generate import parse_manifest, fields_dict_to_parsed, detect_instrumental, fire_request
    from hermes_sonus.mcp.build_payload import build_payload, validate_limits, merge_unhinged_seed_into_lyrics
    from .tasks import TaskStatus

    manager = _get_manager()
    if manager is None:
        return json.dumps({"success": False, "error": "Failed to initialize task manager"})

    manifest_text = args.get("manifest_text", "")
    manifest_file = args.get("manifest_file", "")
    model = args.get("model", "V5")
    callback_url = args.get("callback_url", "")
    blocking = args.get("blocking", True)
    agent_id = args.get("agent_id", "")
    continue_on_error = args.get("continue_on_error", True)
    rate_interval = args.get("rate_interval", 0.75)

    # Load manifest
    try:
        if manifest_file:
            mf = _Path(manifest_file)
            if not mf.exists():
                return json.dumps({"success": False, "error": f"Manifest file not found: {manifest_file}"})
            text = mf.read_text(encoding="utf-8")
            try:
                manifest = json.loads(text)
            except Exception:
                try:
                    import yaml as _yaml
                    manifest = _yaml.safe_load(text)
                except Exception:
                    return json.dumps({"success": False, "error": "Manifest is not valid JSON or YAML"})
        elif manifest_text:
            try:
                manifest = json.loads(manifest_text)
            except Exception:
                try:
                    import yaml as _yaml
                    manifest = _yaml.safe_load(manifest_text)
                except Exception:
                    return json.dumps({"success": False, "error": "Manifest text is not valid JSON or YAML"})
        else:
            return json.dumps({"success": False, "error": "Provide manifest_text or manifest_file"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Failed to load manifest: {e}"})

    # Parse manifest into resolved tracks + settings
    try:
        resolved_tracks, settings = parse_manifest(manifest)
    except ValueError as e:
        return json.dumps({"success": False, "error": f"Invalid manifest: {e}"})

    # Override settings from args
    if model:
        settings["model"] = model
    if callback_url:
        settings["callback_url"] = callback_url
    model = settings["model"]
    callback_url = settings.get("callback_url", "")

    # Validate callback
    if not callback_url:
        return json.dumps({"success": False, "error": "callback_url required (set in manifest or pass as arg)"})

    # Build payloads and create album project
    album_title = manifest.get("album_title") or manifest.get("title")
    if not album_title:
        dna = manifest.get("album_dna", {})
        album_title = dna.get("album_title") if isinstance(dna, dict) else None
    if not album_title:
        album_title = f"Album_{len(resolved_tracks)}tracks"
    album = manager.create_album(
        title=album_title,
        manifest=manifest,
        model=model,
        agent_id=agent_id or None,
    )

    payloads = []
    all_warnings = []
    for i, track_dict in enumerate(resolved_tracks):
        fields = fields_dict_to_parsed(track_dict)
        merge_unhinged_seed_into_lyrics(fields)
        instrumental = detect_instrumental(fields, settings.get("instrumental"))
        warnings = validate_limits(fields, model, instrumental, settings.get("custom_mode", True))
        if warnings:
            all_warnings.append({"track_index": i + 1, "warnings": warnings})
        payload = build_payload(fields, model, callback_url, instrumental, settings.get("custom_mode", True))
        payloads.append(payload)

    # Create MusicTasks for each track
    track_tasks = []
    for i, payload in enumerate(payloads):
        # Extract a prompt from the payload for the task record
        prompt_text = payload.get("prompt", "")
        if not prompt_text:
            prompt_text = payload.get("gpt_description_prompt", "")
        style_text = payload.get("style", "")
        title_text = payload.get("title", f"{album_title} — Track {i + 1}")

        task = manager.create_task(
            prompt=prompt_text,
            style=style_text,
            title=title_text,
            model=model,
            is_instrumental=payload.get("instrumental", True),
            agent_id=agent_id or None,
        )
        track_tasks.append(task)
        album.track_task_ids.append(task.task_id)
    manager._save_albums()

    # Fire generation requests with rate limiting
    api_key = os.environ.get("SUNO_API_KEY", "")
    base_url = os.environ.get("SUNO_BASE_URL", "https://api.sunoapi.org")

    fired = []
    errors = []
    for i, (payload, task) in enumerate(zip(payloads, track_tasks), 1):
        if i > 1:
            time.sleep(rate_interval)
        try:
            response = fire_request(payload, api_key, base_url)
            task_id_from_api = None
            if response.get("code") == 200 and response.get("data"):
                task_id_from_api = response["data"].get("taskId") or response["data"].get("task_id")
            if task_id_from_api:
                task.suno_task_id = task_id_from_api
                task.status = TaskStatus.GENERATING
                task.started_at = __import__("datetime").datetime.now().isoformat()
                task.progress = "Queued at Suno..."
                manager._save_tasks()
                fired.append({"track": i, "task_id": task.task_id, "suno_task_id": task_id_from_api, "status": "fired"})
            else:
                err_msg = response.get("msg", "Unknown API error")
                errors.append({"track": i, "task_id": task.task_id, "error": err_msg})
                task.status = TaskStatus.FAILED
                task.error = err_msg
                manager._save_tasks()
                if not continue_on_error:
                    break
        except Exception as e:
            err_msg = str(e)
            errors.append({"track": i, "task_id": task.task_id, "error": err_msg})
            task.status = TaskStatus.FAILED
            task.error = err_msg
            manager._save_tasks()
            if not continue_on_error:
                break

    # Update album status
    if errors and len(errors) == len(track_tasks):
        manager.update_album_status(album.album_id, TaskStatus.FAILED, error=f"All {len(errors)} tracks failed")
    elif errors:
        manager.update_album_status(album.album_id, TaskStatus.GENERATING,
                                    progress=f"Fired {len(fired)}/{len(track_tasks)} tracks, {len(errors)} failed")
    else:
        manager.update_album_status(album.album_id, TaskStatus.GENERATING,
                                    progress=f"Fired {len(fired)} track(s), polling...")

    if blocking:
        # Poll each track to completion sequentially
        for ft in fired:
            task = manager.get_task(ft["task_id"])
            if not task or task.status == TaskStatus.FAILED:
                continue
            try:
                result = manager.run_task(task.task_id)
                if not result.get("success"):
                    ft["status"] = "failed"
                    ft["error"] = result.get("error", "Unknown")
                else:
                    ft["status"] = "completed"
                    ft["tracks"] = result.get("tracks", [])
            except Exception as e:
                ft["status"] = "failed"
                ft["error"] = str(e)

        # Final album status
        completed_count = sum(1 for ft in fired if ft["status"] == "completed")
        if completed_count == len(fired):
            manager.update_album_status(album.album_id, TaskStatus.COMPLETED,
                                        progress=f"All {completed_count} tracks complete")
        else:
            manager.update_album_status(album.album_id, TaskStatus.COMPLETED if completed_count > 0 else TaskStatus.FAILED,
                                        progress=f"{completed_count}/{len(fired)} tracks complete")

        return json.dumps({
            "success": True,
            "album_id": album.album_id,
            "title": album.title,
            "model": album.model,
            "track_count": len(track_tasks),
            "tracks_fired": len(fired),
            "tracks_completed": completed_count,
            "errors": errors,
            "warnings": all_warnings,
            "track_task_ids": album.track_task_ids,
            "fired_details": fired,
            "message": f"Album '{album.title}' complete: {completed_count}/{len(track_tasks)} tracks generated.",
        })
    else:
        # Non-blocking: return immediately, user polls individual tasks
        return json.dumps({
            "success": True,
            "album_id": album.album_id,
            "title": album.title,
            "model": album.model,
            "track_count": len(track_tasks),
            "tracks_fired": len(fired),
            "errors": errors,
            "warnings": all_warnings,
            "track_task_ids": album.track_task_ids,
            "message": (
                f"Album '{album.title}' fired {len(fired)}/{len(track_tasks)} tracks. "
                f"Poll individual tasks with music_status()."
            ),
        })


def _handle_music_extend(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.submit_extend(
            task_id=args.get("task_id", ""),
            audio_id=args.get("audio_id", ""),
            prompt=args.get("prompt", ""),
            style=args.get("style", ""),
            title=args.get("title", ""),
            continue_at=args.get("continue_at", 0),
            model=args.get("model", "V5"),
        )
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"Extension started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_generate_lyrics(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.submit_lyrics(prompt=args.get("prompt", ""))
        return json.dumps({
            "success": True,
            "task_id": task_id,
            "message": f"Lyrics generation started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_clone_voice_validate(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.clone_voice_validate()
        return json.dumps({
            "success": True,
            "task_id": task_id,
            "message": (
                "Voice cloning validation started. "
                f"Poll with music_status('{task_id}') to get the verification phrase. "
                "Have the person record themselves saying the phrase + a voice sample, "
                "upload it publicly, then call music_clone_voice_create."
            ),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_clone_voice_create(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.clone_voice_create(
            audio_url=args.get("audio_url", ""),
            task_id=args.get("task_id", ""),
        )
        return json.dumps({
            "success": True,
            "task_id": task_id,
            "message": (
                "Voice clone creation started. "
                f"Poll with music_status('{task_id}') to get the voiceId. "
                "Use it as personaId with personaModel='voice_persona' in music_generate."
            ),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_separate_stems(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.separate_stems(
            task_id=args.get("task_id", ""),
            track_index=args.get("track_index", 0),
        )
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"Stem separation started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_replace_section(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.replace_section(
            task_id=args.get("task_id", ""),
            section_type=args.get("section_type", ""),
            new_lyrics=args.get("new_lyrics", ""),
        )
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"Section replacement started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_boost_style(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.boost_style(
            task_id=args.get("task_id", ""),
            target_style=args.get("target_style", ""),
        )
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"Style boost started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_convert_to_wav(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.convert_to_wav(task_id=args.get("task_id", ""))
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"WAV conversion started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_create_video(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.create_music_video(task_id=args.get("task_id", ""))
        return json.dumps({
            "success": True,
            "new_task_id": task_id,
            "message": f"Music video generation started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _handle_music_generate_sounds(args: dict, **kw) -> str:
    from . import suno
    try:
        task_id = suno.generate_sounds(
            prompt=args.get("prompt", ""),
            duration=args.get("duration", 5),
            model=args.get("model", "V5"),
        )
        return json.dumps({
            "success": True,
            "task_id": task_id,
            "message": f"Sound generation started. Poll with music_status('{task_id}').",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI format for Hermes)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = {
    "music_generate": {
        "name": "music_generate",
        "description": (
            "Generate AI music via Suno. By default waits until complete and returns "
            "the audio file path. Set blocking=False to return immediately with task_id "
            "for polling. Generation takes 2-4 minutes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Music description or lyrics. Be specific about mood, genre, instruments, tempo.",
                },
                "style": {
                    "type": "string",
                    "description": "Style tags (e.g., 'electronic ambient', 'jazz piano', 'epic orchestral')",
                },
                "title": {
                    "type": "string",
                    "description": "Song title (optional, auto-generated if empty)",
                },
                "model": {
                    "type": "string",
                    "enum": ["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"],
                    "description": "Suno model version. V5 is default. V5_5 adds voice cloning.",
                },
                "is_instrumental": {
                    "type": "boolean",
                    "description": "True for instrumental (no vocals), False for AI vocals",
                },
                "exclude_styles": {
                    "type": "string",
                    "description": "Styles to exclude. Can use double negatives for ironic enforcement.",
                },
                "weirdness_pct": {
                    "type": "number",
                    "description": "Creative deviation 0-100. Default 50.",
                },
                "style_pct": {
                    "type": "number",
                    "description": "Style adherence 0-100. Default 50.",
                },
                "blocking": {
                    "type": "boolean",
                    "description": "If True (default), waits for completion. If False, returns task_id for polling.",
                },
                "agent_id": {
                    "type": "string",
                    "description": "ID of the creating agent for attribution.",
                },
            },
            "required": ["prompt"],
        },
    },
    "music_status": {
        "name": "music_status",
        "description": "Check the progress of a music generation task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by music_generate()",
                },
            },
            "required": ["task_id"],
        },
    },
    "music_result": {
        "name": "music_result",
        "description": (
            "Get the result of a completed music generation — audio file path, URL, "
            "title, duration, and all tracks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID returned by music_generate()",
                },
            },
            "required": ["task_id"],
        },
    },
    "music_list": {
        "name": "music_list",
        "description": "List recent music generation tasks with status, title, and file paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tasks to return (default 10)",
                },
            },
            "required": [],
        },
    },
    "music_favorite": {
        "name": "music_favorite",
        "description": "Toggle or set favorite status for a song or specific track.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID of the song to favorite",
                },
                "track": {
                    "type": "integer",
                    "description": "1-indexed track number to favorite. Omit to favorite the whole song.",
                },
                "favorite": {
                    "type": "boolean",
                    "description": "True to favorite, False to unfavorite. Omit to toggle.",
                },
            },
            "required": ["task_id"],
        },
    },
    "music_library": {
        "name": "music_library",
        "description": "Browse the music library with filters — by agent, favorites, or status.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Filter by creator agent ID",
                },
                "favorites_only": {
                    "type": "boolean",
                    "description": "Only show favorited songs",
                },
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "pending", "generating"],
                    "description": "Filter by status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum songs to return (default 20)",
                },
            },
            "required": [],
        },
    },
    "music_search": {
        "name": "music_search",
        "description": "Search songs by title, prompt, or style text.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text to match against title, prompt, or style",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            "required": ["query"],
        },
    },
    "music_play": {
        "name": "music_play",
        "description": (
            "Play a song — plays audio locally via mpg123 (or similar), auto-stops "
            "any currently playing track. Returns the audio file path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID of the song to play",
                },
                "track": {
                    "type": "integer",
                    "description": "Which track to play, 1-indexed (default: 1). Suno generates 2 tracks per song.",
                },
            },
            "required": ["task_id"],
        },
    },
    "music_stop": {
        "name": "music_stop",
        "description": "Stop the currently playing audio track.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "music_delete": {
        "name": "music_delete",
        "description": (
            "Archive or permanently delete a song or specific track. "
            "By default archives (moves to archive folder). "
            "Use permanent=True to delete files from disk."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID of the song",
                },
                "track": {
                    "type": "integer",
                    "description": "1-indexed track number. Omit to archive/delete all tracks.",
                },
                "permanent": {
                    "type": "boolean",
                    "description": "If True, permanently delete files. If False (default), move to archive.",
                },
            },
            "required": ["task_id"],
        },
    },
    "midi_create": {
        "name": "midi_create",
        "description": (
            "Create a MIDI file from a list of notes. Use to compose melodies, arpeggios, or chord "
            "progressions, then pass the output to music_compose() for AI-generated music based on "
            "your composition. Notes: MIDI numbers (60=C4) or names ('C4', 'F#3', 'Bb5'). "
            "Use 'R' or 0 for rests."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "description": "Notes: MIDI numbers (60, 64, 67) or names ('C4', 'E4', 'G4'). 0 or 'R' for rests.",
                },
                "tempo": {
                    "type": "integer",
                    "description": "Beats per minute (default 120)",
                },
                "note_duration": {
                    "type": "number",
                    "description": "Duration per note in beats (0.5 = eighth note, 1.0 = quarter)",
                },
                "title": {
                    "type": "string",
                    "description": "Filename for the MIDI file",
                },
                "velocity": {
                    "type": "integer",
                    "description": "Note loudness 0-127 (default 100)",
                },
                "rest_between": {
                    "type": "number",
                    "description": "Gap between notes in beats (default 0.0)",
                },
            },
            "required": ["notes"],
        },
    },
    "music_compose": {
        "name": "music_compose",
        "description": (
            "Generate music using a MIDI file as compositional reference. Your MIDI (melody, chords, "
            "rhythm) is converted to audio and used as reference for Suno AI. audio_influence controls "
            "how closely Suno follows your composition (0.2=free, 0.5=balanced, 0.8=close)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "midi_file": {
                    "type": "string",
                    "description": "Path to a MIDI file to use as reference",
                },
                "style": {
                    "type": "string",
                    "description": "Style tags (e.g., 'dark electronic ambient', 'jazz piano')",
                },
                "title": {
                    "type": "string",
                    "description": "Track title",
                },
                "audio_influence": {
                    "type": "number",
                    "description": "How much MIDI reference affects output (0.0-1.0, default 0.5)",
                },
                "prompt": {
                    "type": "string",
                    "description": "Additional description (becomes lyrics if not instrumental)",
                },
                "instrumental": {
                    "type": "boolean",
                    "description": "True for instrumental, False for AI vocals (default True)",
                },
                "style_weight": {
                    "type": "number",
                    "description": "How strongly to apply style tags (0.0-1.0, default 0.5)",
                },
                "weirdness": {
                    "type": "number",
                    "description": "Creative deviation (0.0-1.0, default 0.3)",
                },
                "model": {
                    "type": "string",
                    "enum": ["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"],
                    "description": "Suno model version (default V5)",
                },
                "blocking": {
                    "type": "boolean",
                    "description": "Wait for completion (True) or return task_id for polling (False)",
                },
                "agent_id": {
                    "type": "string",
                    "description": "ID of the creating agent for attribution",
                },
            },
            "required": ["midi_file", "style", "title"],
        },
    },
    "music_extend": {
        "name": "music_extend",
        "description": "Extend an existing generated track with additional content.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Original task_id"},
                "audio_id": {"type": "string", "description": "Audio ID of the specific track variant to extend"},
                "prompt": {"type": "string", "description": "Optional lyrics for the extension"},
                "style": {"type": "string", "description": "Optional style override"},
                "title": {"type": "string", "description": "Optional title for extended track"},
                "continue_at": {"type": "integer", "description": "Seconds into original to start from (0 = end)"},
                "model": {"type": "string", "enum": ["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"], "description": "Model for extension"},
            },
            "required": ["task_id", "audio_id"],
        },
    },
    "music_generate_lyrics": {
        "name": "music_generate_lyrics",
        "description": "Generate lyrics independently of music generation.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Short description of desired lyrical content"},
            },
            "required": ["prompt"],
        },
    },
    "music_clone_voice_validate": {
        "name": "music_clone_voice_validate",
        "description": "Start voice cloning workflow. Returns a task_id and verification phrase.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "music_clone_voice_create": {
        "name": "music_clone_voice_create",
        "description": "Create a voice clone from a recording after validation.",
        "parameters": {
            "type": "object",
            "properties": {
                "audio_url": {"type": "string", "description": "Public URL to the verification recording"},
                "task_id": {"type": "string", "description": "task_id from music_clone_voice_validate"},
            },
            "required": ["audio_url", "task_id"],
        },
    },
    "music_check_credits": {
        "name": "music_check_credits",
        "description": "Check remaining Suno API credits.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "music_generate_album": {
        "name": "music_generate_album",
        "description": (
            "Generate multiple coherent tracks from an album/EP manifest (YAML/JSON). "
            "Supports DNA mode (shared style fragments + per-track deltas) or explicit mode "
            "(complete field set per track). Rate-limited firing to respect API ceilings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "manifest_text": {
                    "type": "string",
                    "description": "Raw manifest as JSON or YAML string. Provide this OR manifest_file.",
                },
                "manifest_file": {
                    "type": "string",
                    "description": "Path to a JSON or YAML manifest file. Provide this OR manifest_text.",
                },
                "model": {
                    "type": "string",
                    "enum": ["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"],
                    "description": "Override model from manifest.",
                },
                "callback_url": {
                    "type": "string",
                    "description": "Override callback URL from manifest (required if not in manifest).",
                },
                "blocking": {
                    "type": "boolean",
                    "description": "If True (default), waits for all tracks. If False, returns immediately with task_ids.",
                },
                "agent_id": {
                    "type": "string",
                    "description": "ID of the creating agent for attribution.",
                },
                "continue_on_error": {
                    "type": "boolean",
                    "description": "Continue firing remaining tracks if one fails (default True).",
                },
                "rate_interval": {
                    "type": "number",
                    "description": "Seconds between API requests (default 0.75).",
                },
            },
            "required": [],
        },
    },
    "music_separate_stems": {
        "name": "music_separate_stems",
        "description": "Separate vocals from instruments for a completed track.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task_id of the completed track to process"},
                "track_index": {"type": "integer", "description": "Which variant to process (0 or 1). Default 0."},
            },
            "required": ["task_id"],
        },
    },
    "music_replace_section": {
        "name": "music_replace_section",
        "description": "Replace a section in a generated track with new lyrics.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task_id of the track to edit"},
                "section_type": {"type": "string", "description": "Section to replace: verse, chorus, bridge, etc."},
                "new_lyrics": {"type": "string", "description": "The new lyrics for that section"},
            },
            "required": ["task_id", "section_type", "new_lyrics"],
        },
    },
    "music_boost_style": {
        "name": "music_boost_style",
        "description": "Strengthen style adherence on an existing generated track.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task_id of the track to enhance"},
                "target_style": {"type": "string", "description": "The style direction to boost toward"},
            },
            "required": ["task_id", "target_style"],
        },
    },
    "music_convert_to_wav": {
        "name": "music_convert_to_wav",
        "description": "Convert a generated track's MP3 output to WAV format.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task_id of the track to convert"},
            },
            "required": ["task_id"],
        },
    },
    "music_create_video": {
        "name": "music_create_video",
        "description": "Generate a music video from a completed track.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task_id of the track to visualize"},
            },
            "required": ["task_id"],
        },
    },
    "music_generate_sounds": {
        "name": "music_generate_sounds",
        "description": "Generate non-musical sound effects from a text description.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the desired sound"},
                "duration": {"type": "integer", "description": "Length in seconds. Default 5."},
                "model": {"type": "string", "enum": ["V4", "V4_5", "V4_5PLUS", "V4_5ALL", "V5", "V5_5"], "description": "Model to use"},
            },
            "required": ["prompt"],
        },
    },
}

# Handler dispatch map
TOOL_HANDLERS = {
    "music_generate": _handle_music_generate,
    "music_status": _handle_music_status,
    "music_result": _handle_music_result,
    "music_list": _handle_music_list,
    "music_favorite": _handle_music_favorite,
    "music_library": _handle_music_library,
    "music_search": _handle_music_search,
    "music_play": _handle_music_play,
    "music_stop": _handle_music_stop,
    "music_delete": _handle_music_delete,
    "midi_create": _handle_midi_create,
    "music_compose": _handle_music_compose,
    "music_extend": _handle_music_extend,
    "music_generate_lyrics": _handle_music_generate_lyrics,
    "music_clone_voice_validate": _handle_music_clone_voice_validate,
    "music_clone_voice_create": _handle_music_clone_voice_create,
    "music_check_credits": _handle_music_check_credits,
    "music_generate_album": _handle_music_generate_album,
    "music_separate_stems": _handle_music_separate_stems,
    "music_replace_section": _handle_music_replace_section,
    "music_boost_style": _handle_music_boost_style,
    "music_convert_to_wav": _handle_music_convert_to_wav,
    "music_create_video": _handle_music_create_video,
    "music_generate_sounds": _handle_music_generate_sounds,
}


# ---------------------------------------------------------------------------
# Plugin entry point — called by Hermes PluginManager
# ---------------------------------------------------------------------------

def register(ctx):
    """Register all music tools with Hermes."""
    toolset = "music"

    for name, schema in TOOL_SCHEMAS.items():
        handler = TOOL_HANDLERS[name]

        # midi_create doesn't need SUNO_API_KEY
        if name == "midi_create":
            check_fn = _check_midi_available
            requires_env = []
        elif name in ("music_stop",):
            check_fn = _check_always
            requires_env = []
        else:
            check_fn = _check_suno_available
            requires_env = ["SUNO_API_KEY"]

        ctx.register_tool(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env,
            emoji="🎵" if "music" in name else "🎹",
        )

    logger.info("Hermes Music Plugin v%s registered %d tools", __version__, len(TOOL_SCHEMAS))
