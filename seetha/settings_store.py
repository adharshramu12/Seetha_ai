"""
Local settings store for Seetha.

All API keys and preferences live in ONE json file on the USER'S machine:
    %LOCALAPPDATA%/Seetha/settings.json   (e.g. C:/Users/you/AppData/Local/Seetha)

Nothing is ever sent to a Seetha server — there is no Seetha server.
Precedence when reading a key:  settings.json  >  environment / .env
"""

import json
import os
import threading
from pathlib import Path

from seetha.logger import setup_logger

logger = setup_logger()

# ------------------------------------------------------------------
# Declarative catalogue of every configurable key.
# The Settings UI renders itself from this list, so adding a new
# integration later = add one entry here, nothing else.
# ------------------------------------------------------------------
KEY_SPECS = [
    # --- AI Brain ---
    {
        "name": "NVIDIA_API_KEY",
        "label": "NVIDIA NIM API Key",
        "placeholder": "nvapi-...",
        "help_url": "https://build.nvidia.com",
        "secret": True,
        "required": True,
        "section": "AI Brain  (required)",
        "hint": "Free key from build.nvidia.com — this powers Seetha's thinking.",
    },
    {
        "name": "NIM_MODEL",
        "label": "NVIDIA Model",
        "placeholder": "meta/llama-3.3-70b-instruct",
        "help_url": "https://build.nvidia.com/models",
        "secret": False,
        "required": False,
        "section": "AI Brain  (required)",
        "hint": "Leave empty for the default. Any chat model ID from build.nvidia.com works.",
    },
    {
        "name": "NIM_VISION_MODEL",
        "label": "NVIDIA Vision Model",
        "placeholder": "meta/llama-3.2-11b-vision-instruct",
        "help_url": "https://build.nvidia.com/models",
        "secret": False,
        "required": False,
        "section": "AI Brain  (required)",
        "hint": "Used by the agent loop to VERIFY actions on screen. Leave empty for the default.",
    },
    {
        "name": "GROQ_API_KEY",
        "label": "Groq API Key  (fallback)",
        "placeholder": "gsk_...",
        "help_url": "https://console.groq.com/keys",
        "secret": True,
        "required": False,
        "section": "AI Brain  (required)",
        "hint": "Optional backup brain (also free). Used only if NVIDIA fails.",
    },
    # --- Research Add-ons ---
    {
        "name": "GOOGLE_API_KEY",
        "label": "Google Gemini API Key",
        "placeholder": "AIza...",
        "help_url": "https://aistudio.google.com/apikey",
        "secret": True,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "Improves Deep Research report writing.",
    },
    {
        "name": "SERPAPI_API_KEY",
        "label": "SerpAPI Key",
        "placeholder": "64-character hex key",
        "help_url": "https://serpapi.com/manage-api-key",
        "secret": True,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "Google-quality search results for research. Falls back to DuckDuckGo without it.",
    },
    {
        "name": "NASA_API_KEY",
        "label": "NASA API Key",
        "placeholder": "from api.nasa.gov",
        "help_url": "https://api.nasa.gov",
        "secret": True,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "Space / astronomy questions in Deep Research.",
    },
    {
        "name": "OPENSKY_USERNAME",
        "label": "OpenSky Username",
        "placeholder": "your OpenSky client id",
        "help_url": "https://opensky-network.org",
        "secret": False,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "Live flight-tracking data in Deep Research.",
    },
    {
        "name": "OPENSKY_PASSWORD",
        "label": "OpenSky Password / Secret",
        "placeholder": "your OpenSky client secret",
        "help_url": "https://opensky-network.org",
        "secret": True,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "",
    },
    {
        "name": "TREFLE_API_TOKEN",
        "label": "Trefle API Token",
        "placeholder": "usr-...",
        "help_url": "https://trefle.io",
        "secret": True,
        "required": False,
        "section": "Deep Research add-ons  (optional)",
        "hint": "Plant / botany data in Deep Research.",
    },
]


class SettingsStore:
    """Thread-safe singleton around settings.json."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "SettingsStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def __init__(self):
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Seetha"
        self.path = base / "settings.json"
        self._data = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read settings file ({self.path}): {e}")
            self._data = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
        except Exception as e:
            logger.error(f"Could not write settings file ({self.path}): {e}")

    def get(self, name: str) -> str:
        """Stored value for a key, '' if unset."""
        val = self._data.get(name, "")
        return val.strip() if isinstance(val, str) else ""

    def set_many(self, values: dict):
        """Update several keys at once and persist."""
        for k, v in values.items():
            if isinstance(v, str):
                v = v.strip()
            if v:
                self._data[k] = v
            else:
                self._data.pop(k, None)  # empty value = remove override
        self._save()
        logger.info(f"Settings saved to {self.path}")

    def as_dict(self) -> dict:
        return dict(self._data)
