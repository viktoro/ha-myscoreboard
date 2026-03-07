"""Test setup — mock homeassistant so we can import pure functions without HA installed."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

# Stub out homeassistant and its submodules before importing anything
for mod_name in [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.exceptions",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Add custom_components to the import path
_comp_dir = Path(__file__).resolve().parent.parent / "custom_components"
if str(_comp_dir) not in sys.path:
    sys.path.insert(0, str(_comp_dir))
