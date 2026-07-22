"""
RulesEngine — instant, local, free intent matching.

Runs BEFORE any AI call. If a command matches here, it executes directly
(volume, brightness, open/close apps, media, screenshots) with zero
latency and zero API usage — no matter how the user phrases it.
"""

import re
from seetha.logger import setup_logger

logger = setup_logger()

# Filler words stripped from app-name targets so "open the chrome browser
# please" resolves to "chrome".
_FILLER_PATTERNS = [
    r"\bplease\b", r"\bfor me\b", r"\bnow\b", r"\bbuddy\b", r"\bboss\b",
    r"\bcan you\b", r"\bcould you\b", r"\bwill you\b",
]
_LEADING_ARTICLES = r"^(?:the|a|an|my)\s+"
_TRAILING_DESCRIPTORS = r"\s+(?:app|apps|application|software|program|browser|window)$"


def _clean_target(target: str) -> str:
    """Normalizes an app-name target extracted from a sentence."""
    target = target.strip().rstrip(".!?,")
    for pat in _FILLER_PATTERNS:
        target = re.sub(pat, "", target)
    target = re.sub(r"\s{2,}", " ", target).strip()
    target = re.sub(_LEADING_ARTICLES, "", target)
    target = re.sub(_TRAILING_DESCRIPTORS, "", target)
    return target.strip()


class RulesEngine:
    def __init__(self):
        logger.info("Rules Engine Initialized.")

    def match(self, text):
        """
        Input: User text (string)
        Output: (response, action, params) or None
        """
        if not text:
            return None
        text = text.lower().strip()

        # ------------------------------------------------------------
        # 1. VOLUME — word-based so ANY phrasing works:
        #    "volume up", "increase the volume", "make it louder",
        #    "turn the sound up", "reduce volume a bit", "mute"
        # ------------------------------------------------------------
        mentions_volume = bool(re.search(r"\b(volume|vol|sound|audio)\b", text))

        if mentions_volume or re.search(r"\b(louder|quieter)\b", text):
            up_words = r"\b(up|increase|increes|raise|louder|loud|high|higher|max|maximum|full|boost)\b"
            down_words = r"\b(down|decrease|decres|lower|reduce|quieter|less|low|minimum|min)\b"
            if re.search(up_words, text):
                return None, "control_volume", {"action": "up"}
            if re.search(down_words, text):
                return None, "control_volume", {"action": "down"}

        if re.search(r"\b(mute|silence|unmute)\b", text) or "turn off sound" in text or "turn off volume" in text:
            return None, "control_volume", {"action": "mute"}

        # ------------------------------------------------------------
        # 2. BRIGHTNESS — same word-based approach, plus exact levels:
        #    "brightness up", "decrease the brightness", "dim the screen",
        #    "make it brighter", "set brightness to 40"
        # ------------------------------------------------------------
        set_match = re.search(r"\b(?:set|change|make)\b.*\bbright\w*\b.*?(\d{1,3})", text)
        if set_match:
            level = max(0, min(100, int(set_match.group(1))))
            return None, "control_brightness", {"action": "set", "level": level}

        mentions_brightness = bool(re.search(r"\bbright\w*\b", text)) or "screen light" in text

        if mentions_brightness or re.search(r"\b(dim|dimmer)\b", text):
            up_words = r"\b(up|increase|increes|raise|brighter|high|higher|max|maximum|full)\b|brighten"
            down_words = r"\b(down|decrease|decres|lower|reduce|dim|dimmer|less|low|minimum|min)\b"
            if re.search(up_words, text):
                return None, "control_brightness", {"action": "up"}
            if re.search(down_words, text):
                return None, "control_brightness", {"action": "down"}

        # ------------------------------------------------------------
        # 3. SCREENSHOT (deterministic, no AI needed)
        # ------------------------------------------------------------
        if re.search(r"\b(screenshot|screen shot|capture (the )?screen)\b", text):
            return None, "take_screenshot", {}

        # ------------------------------------------------------------
        # 4. MEDIA
        # ------------------------------------------------------------
        if any(x in text for x in ["next song", "next video", "next track", "skip song", "skip this"]):
            return "Skipping.", "media_control", {"command": "next"}
        elif any(x in text for x in ["pause", "stop music", "pause music", "stop the music", "stop the song"]):
            return "Pausing.", "media_control", {"command": "pause"}
        elif any(x in text for x in ["resume", "play music", "start music", "continue the song"]):
            return "Resuming.", "media_control", {"command": "play"}

        # ------------------------------------------------------------
        # 5. CLOSE APPS
        # ------------------------------------------------------------
        if any(x in text for x in ["close all apps", "close all appps", "close everything", "close all windows"]):
            return "Closing all apps, Boss.", "close_all_apps", {}

        match = re.search(r"\b(close|clse|kill|stop|terminate|quit|exit)\s+(.+)", text)
        if match:
            target = _clean_target(match.group(2))
            # Ignore chat/voice specific keywords
            if not target or target in ["chat mode", "talking", "listening", "voice", "conversation"]:
                return None
            return f"Closing {target}.", "close_app", {"app_name": target}

        # ------------------------------------------------------------
        # 6. INSTANT MEETING
        # ------------------------------------------------------------
        if "meeting" in text or "meet" in text:
            triggers = ["create", "start", "instant", "google", "make", "setup", "new", "generate", "host"]
            if any(t in text for t in triggers):
                return "Creating an instant meeting for you, Boss.", "create_instant_meeting", {}

        # ------------------------------------------------------------
        # 7. OPEN APPS (catch-all, typo-tolerant, compound-aware)
        #    "open chrome", "opne notepad", "launch the calculator app",
        #    "open notepad and calculator"
        # ------------------------------------------------------------
        match = re.search(r"\b(open|opn|opne|launch|start|run|play)\s+(.+)", text)
        if match:
            target = _clean_target(match.group(2))
            if not target:
                return None

            # Compound: "open notepad and calculator" -> both apps.
            # BUT "open notepad and write a poem" is a MULTI-STEP TASK —
            # if any part starts with an action verb, hand the whole
            # command to the AI so it can build a proper plan.
            action_verbs = (
                "write", "type", "send", "compose", "draft", "create", "make",
                "tell", "say", "search", "set", "take", "message", "call",
                "generate", "add", "note", "put",
            )
            parts = [
                _clean_target(p) for p in re.split(r"\s+(?:and|then|,)\s+", target)
                if _clean_target(p)
            ]
            if any(p.split(" ")[0] in action_verbs for p in parts):
                return None  # let the AI plan the multi-step task

            if len(parts) > 1:
                return f"Opening {', '.join(parts)} for you.", "open_multiple_apps", {"apps": parts}

            return f"Opening {target} for you.", "open_app", {"app_name": target}

        return None
