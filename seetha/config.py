"""
Configuration for Seetha (open-source edition).

Every key is optional and belongs to the USER. Two ways to provide them:

  1. In-app:  ⚙ Settings window  (recommended — stored in
              %LOCALAPPDATA%/Seetha/settings.json)
  2. Developer style: a .env file in the project root (see .env.example)

Precedence: Settings window value > .env / environment variable.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from seetha.logger import setup_logger

logger = setup_logger()

# .env support for developers (optional — the Settings UI is the main path)
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def get_key(name: str, default: str = "") -> str:
    """
    Live lookup for an API key / setting.
    Checks the user's local Settings first, then the environment.
    Always call this at USE time (not import time) so keys saved in
    the Settings window take effect immediately, without a restart.
    """
    # Imported lazily to avoid a circular import at module load
    from seetha.settings_store import SettingsStore

    val = SettingsStore.instance().get(name)
    if val:
        return val

    env_val = os.getenv(name, "")
    return env_val.strip() if env_val else default
