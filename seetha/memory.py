"""
Persistent memory for Seetha.

Facts the user tells Seetha ("remember my exam is on Friday") and
reminders ("remind me at 6pm to call amma") survive restarts in ONE
local file:

    %LOCALAPPDATA%/Seetha/memory.json

Facts are injected into the AI system prompt so Seetha talks like she
actually knows you. Reminders are fired by a scheduler thread in
core.SeethaService.
"""

import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from seetha.logger import setup_logger

logger = setup_logger()


class MemoryManager:
    """Thread-safe singleton around memory.json."""

    _instance = None
    _cls_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "MemoryManager":
        with cls._cls_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def __init__(self):
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "Seetha"
        self.path = base / "memory.json"
        self._lock = threading.Lock()
        self._data = {"facts": [], "reminders": []}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._data["facts"] = data.get("facts", [])
                    self._data["reminders"] = data.get("reminders", [])
        except Exception as e:
            logger.warning(f"Could not read memory file: {e}")

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Could not write memory file: {e}")

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    def add_fact(self, text: str):
        text = text.strip().rstrip(".")
        if not text:
            return
        with self._lock:
            # Avoid exact duplicates
            if any(f["text"].lower() == text.lower() for f in self._data["facts"]):
                return
            self._data["facts"].append({
                "text": text,
                "created": datetime.now().isoformat(timespec="seconds"),
            })
            # Keep memory bounded
            self._data["facts"] = self._data["facts"][-100:]
            self._save()
        logger.info(f"Memory: remembered '{text}'")

    def get_facts(self, limit: int = 25):
        with self._lock:
            return [f["text"] for f in self._data["facts"][-limit:]]

    def forget(self, query: str) -> int:
        """Removes facts containing the query. Returns how many were removed."""
        query = query.strip().lower()
        if len(query) < 3:
            return 0
        with self._lock:
            before = len(self._data["facts"])
            self._data["facts"] = [
                f for f in self._data["facts"] if query not in f["text"].lower()
            ]
            removed = before - len(self._data["facts"])
            if removed:
                self._save()
        return removed

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def add_reminder(self, task: str, due: datetime):
        with self._lock:
            self._data["reminders"].append({
                "text": task.strip(),
                "due": due.isoformat(timespec="seconds"),
                "done": False,
            })
            self._save()
        logger.info(f"Reminder set: '{task}' at {due}")

    def pending_reminders(self):
        now = datetime.now()
        with self._lock:
            return [
                r for r in self._data["reminders"]
                if not r["done"] and datetime.fromisoformat(r["due"]) > now
            ]

    def pop_due_reminders(self):
        """Returns reminders whose time has arrived and marks them done."""
        now = datetime.now()
        due = []
        with self._lock:
            for r in self._data["reminders"]:
                if not r["done"] and datetime.fromisoformat(r["due"]) <= now:
                    r["done"] = True
                    due.append(r)
            if due:
                # Prune old completed reminders
                self._data["reminders"] = [
                    r for r in self._data["reminders"]
                    if not r["done"] or datetime.fromisoformat(r["due"]) > now - timedelta(days=2)
                ]
                self._save()
        return due


# ----------------------------------------------------------------------
# Natural-language reminder parsing
# ----------------------------------------------------------------------

def parse_reminder(text: str):
    """
    Parses phrasings like:
      "remind me in 10 minutes to drink water"
      "remind me at 6 pm to call amma"
      "remind me to submit the form at 6:30pm"
      "remind me tomorrow at 9 to pay the bill"
    Returns (task, due_datetime) or None.
    """
    m = re.search(r"\bremind me\b(.*)", text, re.IGNORECASE)
    if not m:
        return None
    body = m.group(1).strip()
    if not body:
        return None

    now = datetime.now()
    due = None

    # --- "in/after N minutes/hours/seconds" ---
    rel = re.search(r"\b(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b", body, re.IGNORECASE)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("sec"):
            due = now + timedelta(seconds=n)
        elif unit.startswith(("min",)):
            due = now + timedelta(minutes=n)
        else:
            due = now + timedelta(hours=n)
        body = body.replace(rel.group(0), " ")

    # --- "at H(:MM)? (am|pm)?" (optionally "tomorrow") ---
    if due is None:
        at = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", body, re.IGNORECASE)
        if at:
            hour = int(at.group(1))
            minute = int(at.group(2) or 0)
            meridiem = (at.group(3) or "").replace(".", "").lower()
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            if hour > 23 or minute > 59:
                return None

            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            tomorrow = re.search(r"\btomorrow\b", body, re.IGNORECASE)
            if tomorrow:
                due += timedelta(days=1)
                body = re.sub(r"\btomorrow\b", " ", body, flags=re.IGNORECASE)
            elif due <= now:
                # No am/pm given and that time already passed today?
                # Try the pm interpretation first, else tomorrow.
                if not meridiem and hour < 12 and due.replace(hour=hour + 12) > now:
                    due = due.replace(hour=hour + 12)
                else:
                    due += timedelta(days=1)
            body = body.replace(at.group(0), " ")

    if due is None:
        return None

    # --- The task is what's left ---
    task = re.sub(r"\s{2,}", " ", body).strip()
    task = re.sub(r"^(?:to|that|about)\s+", "", task, flags=re.IGNORECASE).strip()
    # Strip trailing chatter: "... now - ok seetha", "... please seetha"
    task = re.sub(r"[-–,\s]*(?:ok|okay|please|pls)?\s*seetha\W*$", "", task, flags=re.IGNORECASE)
    task = re.sub(r"\s+now$", "", task, flags=re.IGNORECASE)
    task = task.strip(" ,.-")
    if not task:
        task = "your reminder"
    return task, due
