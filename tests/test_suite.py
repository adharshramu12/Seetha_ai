"""
Seetha AI — release test suite.

Run before every release / pull request:

    python -m tests.test_suite          (from the project root, on Windows)

Design goals:
  * NO network calls, NO API keys needed — everything runs offline.
  * NO GUI windows opened, NO keyboard/mouse moved.
  * NO pollution of the real user's settings/memory (uses a temp dir).
  * Finishes in seconds.
"""

import os
import sys
import tempfile
import unittest

# ------------------------------------------------------------------
# Isolate ALL persistent state into a throwaway directory BEFORE any
# seetha import (SettingsStore / MemoryManager read LOCALAPPDATA at
# first use).
# ------------------------------------------------------------------
_TMP = tempfile.mkdtemp(prefix="seetha_test_")
os.environ["LOCALAPPDATA"] = _TMP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestImports(unittest.TestCase):
    """Every module must import cleanly — catches missing deps and typos."""

    MODULES = [
        "seetha.logger", "seetha.settings_store", "seetha.config",
        "seetha.ai_client", "seetha.rules", "seetha.memory",
        "seetha.actions", "seetha.whatsapp_addon", "seetha.youtube_addon",
        "seetha.brain", "seetha.mouth", "seetha.ears", "seetha.dispatcher",
        "seetha.core", "seetha.premium_research", "seetha.tray",
        "seetha.command_bar", "seetha.settings_ui", "seetha.avatar",
        "seetha.main",
    ]

    def test_all_modules_import(self):
        for mod in self.MODULES:
            with self.subTest(module=mod):
                __import__(mod)


class TestRulesEngine(unittest.TestCase):
    """Natural phrasings must resolve locally (no AI round-trip)."""

    @classmethod
    def setUpClass(cls):
        from seetha.rules import RulesEngine
        cls.rules = RulesEngine()

    def _action(self, text):
        result = self.rules.match(text)
        return result[1] if result else None

    def _params(self, text):
        result = self.rules.match(text)
        return result[2] if result else None

    def test_volume_phrasings(self):
        for phrase in ["volume up", "increase the volume", "make it louder",
                       "turn the sound up", "raise volume"]:
            self.assertEqual(self._action(phrase), "control_volume", phrase)
            self.assertEqual(self._params(phrase)["action"], "up", phrase)
        for phrase in ["volume down", "decrease the volume",
                       "reduce the volume a little", "turn the sound down"]:
            self.assertEqual(self._params(phrase)["action"], "down", phrase)
        self.assertEqual(self._params("mute")["action"], "mute")

    def test_brightness_phrasings(self):
        for phrase in ["brightness up", "increase the brightness", "make it brighter"]:
            self.assertEqual(self._action(phrase), "control_brightness", phrase)
            self.assertEqual(self._params(phrase)["action"], "up", phrase)
        for phrase in ["decrease the brightness", "dim the screen"]:
            self.assertEqual(self._params(phrase)["action"], "down", phrase)

    def test_brightness_set_level(self):
        p = self._params("set brightness to 40")
        self.assertEqual(p["action"], "set")
        self.assertEqual(p["level"], 40)

    def test_screenshot(self):
        self.assertEqual(self._action("take a screenshot"), "take_screenshot")
        self.assertEqual(self._action("capture the screen"), "take_screenshot")

    def test_open_close_apps(self):
        self.assertEqual(self._action("open chrome"), "open_app")
        self.assertEqual(self._params("open the chrome browser please")["app_name"], "chrome")
        self.assertEqual(self._action("close notepad"), "close_app")
        self.assertEqual(self._params("close the whatsapp app")["app_name"], "whatsapp")
        self.assertEqual(self._action("close everything"), "close_all_apps")

    def test_compound_open(self):
        p = self._params("open notepad and calculator")
        self.assertEqual(p["apps"], ["notepad", "calculator"])

    def test_multistep_goes_to_ai(self):
        # "open X and write Y" is a multi-step task — must NOT be
        # swallowed by the rules engine; the AI builds a plan for it.
        self.assertIsNone(self.rules.match("open notepad and write a poem"))

    def test_meeting(self):
        self.assertEqual(self._action("create a google meeting"), "create_instant_meeting")


class TestMemory(unittest.TestCase):
    def setUp(self):
        from seetha.memory import MemoryManager
        # Fresh non-singleton instance in the temp dir
        self.mem = MemoryManager()
        self.mem._data = {"facts": [], "reminders": []}

    def test_fact_roundtrip(self):
        self.mem.add_fact("my exam is on Friday")
        self.assertIn("my exam is on Friday", self.mem.get_facts())

    def test_fact_dedupe(self):
        self.mem.add_fact("same fact")
        self.mem.add_fact("same fact")
        self.assertEqual(len(self.mem.get_facts()), 1)

    def test_forget(self):
        self.mem.add_fact("my exam is on Friday")
        removed = self.mem.forget("exam")
        self.assertEqual(removed, 1)
        self.assertEqual(self.mem.get_facts(), [])

    def test_reminder_due_firing(self):
        from datetime import datetime, timedelta
        self.mem.add_reminder("past task", datetime.now() - timedelta(seconds=5))
        self.mem.add_reminder("future task", datetime.now() + timedelta(hours=1))
        due = self.mem.pop_due_reminders()
        self.assertEqual([d["text"] for d in due], ["past task"])
        pending = self.mem.pending_reminders()
        self.assertEqual([p["text"] for p in pending], ["future task"])


class TestReminderParsing(unittest.TestCase):
    def _parse(self, text):
        from seetha.memory import parse_reminder
        return parse_reminder(text)

    def test_relative(self):
        task, _ = self._parse("remind me in 10 minutes to drink water")
        self.assertEqual(task, "drink water")

    def test_after_variant(self):
        task, _ = self._parse("remind me to drink water after 2 minutes now - ok seetha")
        self.assertEqual(task, "drink water")

    def test_absolute_pm(self):
        task, due = self._parse("remind me at 6 pm to call amma")
        self.assertEqual(task, "call amma")
        self.assertEqual((due.hour, due.minute), (18, 0))

    def test_tomorrow(self):
        from datetime import datetime
        task, due = self._parse("remind me tomorrow at 9 to pay the bill")
        self.assertEqual(task, "pay the bill")
        self.assertGreater(due, datetime.now())

    def test_unparseable(self):
        self.assertIsNone(self._parse("remind me"))


class TestBrainOffline(unittest.TestCase):
    """Brain behavior that must work WITHOUT any AI key."""

    @classmethod
    def setUpClass(cls):
        from seetha.brain import SeethaBrain
        cls.brain = SeethaBrain()

    def test_memory_intents(self):
        resp, _, _ = self.brain.process("remember my mom name is Lakshmi")
        self.assertIn("remember", resp.lower())
        resp, _, _ = self.brain.process("what do you remember")
        self.assertIn("lakshmi", resp.lower())
        resp, _, _ = self.brain.process("forget Lakshmi")
        self.assertIn("forgotten", resp.lower())

    def test_research_intent(self):
        resp, action, params = self.brain.process("research about ISRO")
        self.assertEqual(action, "start_research_task")
        self.assertEqual(params["query"], "isro")

    def test_rules_priority(self):
        _, action, _ = self.brain.process("increase the volume")
        self.assertEqual(action, "control_volume")

    def test_whatsapp_regex_fallback(self):
        intent = self.brain.whatsapp_manager._regex_intent(
            "send a whatsapp message to Ramu saying hello boss")
        self.assertEqual(intent["contact_query"], "Ramu")
        self.assertEqual(intent["message"], "hello boss")

    def test_json_extraction(self):
        payload = 'noise {"response": "hi", "action": "open_app"} trailing'
        self.assertEqual(
            self.brain.extract_json(payload),
            '{"response": "hi", "action": "open_app"}')


class TestDispatcherCoverage(unittest.TestCase):
    """Every action Seetha can emit must have a dispatcher handler —
    otherwise users hear 'I don't know how to perform action X'."""

    # Actions promised to the AI in brain.SYSTEM_PROMPT + emitted by rules
    ACTIONS = [
        "open_app", "close_app", "open_multiple_apps", "close_all_apps",
        "close_active_window", "play_song", "type_text", "send_whatsapp",
        "control_volume", "control_brightness", "media_control",
        "take_screenshot", "search_file", "create_instant_meeting",
        "execute_plan", "play_youtube", "start_research_task",
        "close_tab", "select_all", "empty_recycle_bin", "click_element",
        "search_in_app", "read_screen", "open_desktop_icon",
        "open_taskbar_icon", "start_chat_mode", "stop_chat_mode",
        "whatsapp_call", "open_whatsapp_chat", "send_active_chat_message",
        "write_code_in_notepad",
    ]

    def test_all_actions_have_handlers(self):
        from seetha.dispatcher import ActionDispatcher
        for action in self.ACTIONS:
            with self.subTest(action=action):
                self.assertTrue(
                    hasattr(ActionDispatcher, f"handle_{action}"),
                    f"Missing handler: handle_{action}")

    def test_prompt_actions_subset(self):
        """Every '- action_name' the AI is told about must be tested above."""
        import re
        from seetha.brain import SYSTEM_PROMPT
        promised = set(re.findall(r"^- (\w+)", SYSTEM_PROMPT, re.MULTILINE))
        missing = promised - set(self.ACTIONS)
        self.assertFalse(missing, f"SYSTEM_PROMPT promises untested actions: {missing}")


class TestSettingsStore(unittest.TestCase):
    def test_roundtrip_and_clear(self):
        from seetha.settings_store import SettingsStore
        store = SettingsStore()  # fresh instance in temp LOCALAPPDATA
        store.set_many({"NVIDIA_API_KEY": "nvapi-test123", "EMPTY": ""})
        self.assertEqual(store.get("NVIDIA_API_KEY"), "nvapi-test123")
        self.assertEqual(store.get("EMPTY"), "")

        # Reload from disk — must persist
        store2 = SettingsStore()
        self.assertEqual(store2.get("NVIDIA_API_KEY"), "nvapi-test123")

        # Empty value removes the override
        store2.set_many({"NVIDIA_API_KEY": ""})
        self.assertEqual(SettingsStore().get("NVIDIA_API_KEY"), "")

    def test_key_specs_render_fields(self):
        from seetha.settings_store import KEY_SPECS
        for spec in KEY_SPECS:
            for field in ("name", "label", "section"):
                self.assertIn(field, spec)


class TestAIClientOffline(unittest.TestCase):
    def test_no_key_graceful(self):
        """With no keys configured, chat_completion must return the
        friendly no-key message, not crash."""
        from seetha import ai_client
        from seetha.config import get_key
        if get_key("NVIDIA_API_KEY") or get_key("GROQ_API_KEY"):
            self.skipTest("Real keys present in this environment")
        content, err = ai_client.chat_completion([{"role": "user", "content": "hi"}])
        self.assertIsNone(content)
        self.assertEqual(err, ai_client.NO_KEY_MSG)


if __name__ == "__main__":
    print(f"[test-suite] isolated state dir: {_TMP}")
    unittest.main(verbosity=2)
