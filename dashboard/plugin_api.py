"""Dashboard backend for hermes-sonus.

Loaded by the dashboard plugin system as a standalone file (via
``importlib.util.spec_from_file_location``), so the plugin root is NOT
on ``sys.path``. We inject it ourselves before importing the
package-level router.

The CLI/gateway plugin loader uses a different code path that imports
``hermes_sonus`` directly — that one already has the root on sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from hermes_sonus.api import router  # noqa: E402,F401
