"""
WhatsApp automation add-on.

Handles "send a whatsapp message to X saying Y" style commands:
  1. Intent extraction  — user's AI key (regex fallback works keyless)
  2. Contact resolution — fuzzy match against the local contact list
  3. Execution          — GUI automation (open app, search, type, send)
"""

import json
import time
import difflib
import re
import pyautogui
import pyperclip
import webbrowser

from seetha import ai_client
from seetha.logger import setup_logger

logger = setup_logger()


class WhatsAppManager:
    def __init__(self, app_interface=None):
        self.app = app_interface  # optional: to speak/ask questions

        # Contact list used for fuzzy resolution.
        # TODO (community): load from a user-editable contacts.json
        self.contacts = [
            "Adharsh", "Adharsh Kumar", "Adharsh Kumar SIM2",
            "Ramu", "Ramu Daddy", "Ram", "Ramu BSNL",
            "Sita", "Sita Mom",
            "Boss", "My Love",
        ]

    def is_whatsapp_command(self, text):
        """Fast regex check to see if this module should handle the request."""
        return bool(re.search(r"(send|message).*(whatsapp)", text.lower()))

    def process_command(self, text):
        """
        Main entry point.
        Returns (response_text, action_name, params).
        """
        logger.info(f"WhatsApp add-on handling: {text}")

        intent = self._extract_intent(text)
        if not intent:
            return "Sorry Boss, I couldn't understand who to message.", None, None

        raw_contact = intent.get("contact_query")
        message_body = intent.get("message")
        if not raw_contact or not message_body:
            return "I need both a contact name and a message, Boss.", None, None

        resolved = self._resolve_contact(raw_contact)
        if resolved == "AskUser":
            return f"I found multiple contacts matching '{raw_contact}'. Please be more specific.", None, None
        if not resolved:
            return f"Sorry Boss, I couldn't find a contact named '{raw_contact}'.", None, None

        return (f"Sending message to {resolved}.", "send_whatsapp",
                {"contact": resolved, "message": message_body})

    # ------------------------------------------------------------------
    # Intent extraction
    # ------------------------------------------------------------------

    def _extract_intent(self, text):
        """AI extraction first; deterministic regex fallback if no key/offline."""
        prompt = f"""
        Extract intent from: "{text}"
        Return JSON ONLY:
        {{
          "contact_query": "<name>",
          "message": "<content>",
          "confidence": 1.0
        }}
        """
        try:
            content, err = ai_client.chat_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=200,
                json_mode=True,
            )
            if content:
                json_str = self._extract_json(content)
                if json_str:
                    return json.loads(json_str)
            else:
                logger.debug(f"AI intent extraction unavailable ({err}), trying regex.")
        except Exception as e:
            logger.warning(f"Intent extraction failed: {e}")

        return self._regex_intent(text)

    @staticmethod
    def _regex_intent(text):
        """
        Keyless fallback for common phrasings:
          "send a whatsapp message to Ramu saying hello"
          "send whatsapp to Ramu that I am coming"
          "message Ramu on whatsapp: hello"
        """
        patterns = [
            r"(?:send|message).*?whatsapp.*?to\s+(?P<contact>[\w\s]+?)\s+(?:saying|that|:)\s+(?P<msg>.+)",
            r"(?:send|message)\s+(?P<contact2>[\w\s]+?)\s+on\s+whatsapp\s*(?:saying|that|:)?\s*(?P<msg2>.+)",
            r"whatsapp\s+(?P<contact3>[\w\s]+?)\s+(?:saying|that|:)\s+(?P<msg3>.+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                groups = m.groupdict()
                contact = groups.get("contact") or groups.get("contact2") or groups.get("contact3")
                msg = groups.get("msg") or groups.get("msg2") or groups.get("msg3")
                if contact and msg:
                    return {"contact_query": contact.strip(), "message": msg.strip(), "confidence": 0.6}
        return None

    @staticmethod
    def _extract_json(text):
        start = text.find("{")
        if start == -1:
            return None
        count = 0
        for i, char in enumerate(text[start:], start):
            if char == "{":
                count += 1
            elif char == "}":
                count -= 1
                if count == 0:
                    return text[start:i + 1]
        return None

    # ------------------------------------------------------------------
    # Contact resolution
    # ------------------------------------------------------------------

    def _resolve_contact(self, query):
        query_norm = query.lower().strip()
        candidates = self.contacts

        for c in candidates:
            if c.lower() == query_norm:
                return c

        matches = difflib.get_close_matches(query, candidates, n=3, cutoff=0.6)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        s1 = difflib.SequenceMatcher(None, query, matches[0]).ratio()
        s2 = difflib.SequenceMatcher(None, query, matches[1]).ratio()
        if s1 > 0.85 and (s1 - s2) > 0.1:
            return matches[0]
        return "AskUser"

    # ------------------------------------------------------------------
    # Automation
    # ------------------------------------------------------------------

    def execute_automation(self, contact, message):
        """GUI automation: open WhatsApp, find the contact, send the message."""
        logger.info(f"Executing WhatsApp automation -> {contact}: {message}")

        webbrowser.open("whatsapp://")
        time.sleep(3)

        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)
        pyautogui.write(contact)
        time.sleep(1.0)

        pyautogui.press("down")
        pyautogui.press("enter")
        time.sleep(0.5)

        # Clipboard paste handles emojis / special characters reliably
        pyperclip.copy(message)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)

        pyautogui.press("enter")
        return True
