"""
Hermes Sonus — sonic alchemy for Hermes Agent.

Combines Suno AI music generation, MIDI composition, library management,
and OpenBCI EEG / "felt experience" sensing into a single Hermes plugin
with both CLI tools (20 total) and a dashboard surface.

Layout:
    hermes_sonus/
    ├── music/      — 12 music tools (Suno + MIDI + library + player)
    ├── eeg/        — 8 EEG tools (OpenBCI + mock + emotion mapping)
    └── api.py      — FastAPI router used by the dashboard plugin

Data lives at ~/.hermes/sonus/{music,eeg}/.
"""

import logging

__version__ = "1.0.0"

logger = logging.getLogger(__name__)


def register(ctx):
    """Plugin entry point — called once by the Hermes PluginManager."""
    from . import music, eeg
    music.register(ctx)
    eeg.register(ctx)
    logger.info("hermes-sonus v%s registered (music + eeg toolsets)", __version__)
