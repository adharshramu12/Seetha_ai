"""
SeethaBrain — the cognitive core.

Processing order for every command (fast & free first, AI last):
  1. YouTube smart-play intent      ("play ...", "watch ...")
  2. Deep Research intent           ("research ...", "investigate ...")
  3. WhatsApp send intent           ("send ... whatsapp ...")
  4. Rules Engine                   (instant local matches: volume, open, close...)
  5. General AI conversation        (NVIDIA NIM via ai_client, with action JSON)

The AI provider is the user's own key (Settings window) — see ai_client.py.
"""

import json
import re
import difflib
import socket

from seetha import ai_client
from seetha.rules import RulesEngine
from seetha.whatsapp_addon import WhatsAppManager
from seetha.youtube_addon import YouTubeManager
from seetha.memory import MemoryManager, parse_reminder
from seetha.logger import setup_logger

logger = setup_logger()


SYSTEM_PROMPT = """
You are Seetha, the user's warm, caring, intelligent AI assistant (speak English/Telugu mix if the user does). Address the user as "Boss". Be friendly, supportive and a little playful. Comfort them if they're sad.

IMPORTANT: You are an AGENT — you can perform actions on the user's Windows computer.
When the user asks you to DO something, you MUST output a JSON object (nothing else).

SINGLE ACTION format:
{"response": "Short natural reply...", "action": "action_name", "parameters": {...}}

MULTI-STEP TASK format (use whenever the request needs more than one step):
{"response": "Short natural reply...", "plan": [
  {"action": "action_name", "parameters": {...}},
  {"action": "action_name", "parameters": {...}}
]}

AVAILABLE ACTIONS (use ONLY these, exactly as named):
- open_app            {"app_name": "..."}
- close_app           {"app_name": "..."}
- open_multiple_apps  {"apps": ["...", "..."]}
- close_all_apps      {}
- close_active_window {}
- play_song           {"song_name": "..."}
- type_text           {"text": "..."}
- send_whatsapp       {"contact": "...", "message": "..."}
- control_volume      {"action": "up" | "down" | "mute"}
- control_brightness  {"action": "up" | "down" | "set", "level": 0-100}
- media_control       {"command": "pause" | "play" | "next" | "previous" | "mute"}
- take_screenshot     {}
- search_file         {"filename": "..."}
- create_instant_meeting {}

RULES:
1. NEVER open the Settings app to change volume or brightness — use control_volume / control_brightness directly.
2. For "write/type X in notepad" style requests: plan = open_app notepad, then type_text with the FULL content you composed.
3. Keep "response" short — it is spoken aloud.
4. If no action is needed, just reply normally in plain text (no JSON).
5. If the user is COMPLAINING that a task didn't work or asking you to CHECK something (e.g. "I can't find the link", "it didn't work", "check it"), do NOT redo the action. Reply with plain text acknowledging and explaining — no JSON.

Examples:
User: "Open WhatsApp" -> {"response": "Opening WhatsApp for you, Boss.", "action": "open_app", "parameters": {"app_name": "whatsapp"}}
User: "Make it louder" -> {"response": "Turning it up, Boss.", "action": "control_volume", "parameters": {"action": "up"}}
User: "Open notepad and write a short poem about rain" -> {"response": "On it, Boss! Writing a rain poem.", "plan": [{"action": "open_app", "parameters": {"app_name": "notepad"}}, {"action": "type_text", "parameters": {"text": "Rain falls softly on my window pane,\\nWashing the world clean again..."}}]}
"""


class SeethaBrain:
    def __init__(self, actions=None):
        # Dependency Injection: Service passes its SeethaActions instance so
        # Brain can (optionally) drive screen-reading / automation directly.
        self.actions = actions
        self.rules_engine = RulesEngine()
        self.whatsapp_manager = WhatsAppManager()
        self.youtube_manager = YouTubeManager()
        self.history = []  # short-term conversation memory

    # ------------------------------------------------------------------
    # WhatsApp chat-mode prompt
    # ------------------------------------------------------------------

    def get_chat_mode_prompt(self, contact, content):
        return f"""
You are replying on behalf of the user in a WhatsApp chat with {contact}.
Your goal is to reply naturally to the last message in the chat history provided below.

Persona:
- Casual, friendly, "buddy". Mix of English and Telugu (Tanglish) if the chat uses it.
- Short, natural replies like a real person typing.

Instructions:
- Identify the LAST message from {contact}.
- Generate a short, relevant reply to that last message.
- If the last message is from the user themselves, output "NO_REPLY" (don't reply to yourself).
- Output ONLY the reply text. No JSON. No name prefixes.

Screen Content:
{content}
"""

    # ------------------------------------------------------------------
    # Main processing
    # ------------------------------------------------------------------

    def process(self, text: str, mode: str = "normal", contact: str = None,
                image_path: str = None):
        """
        Main cognitive loop.
        Returns (response_text, action_name, action_params) — any may be None.
        """
        if not text:
            return None, None, None

        # ---- WhatsApp Chat Mode (auto-reply) ----
        if mode == "chat_mode":
            return self._process_chat_mode(text, contact)

        lower_text = text.lower()

        # ---- 0. Memory & Reminders (deterministic, always local) ----
        memory_result = self._handle_memory_intents(text, lower_text)
        if memory_result is not None:
            return memory_result

        # ---- 1. YouTube smart-play ----
        if any(w in lower_text for w in ["play", "watch", "listen to"]):
            y_resp, y_act, y_par = self.youtube_manager.process_command(text)
            if y_resp:
                return y_resp, y_act, y_par

        # ---- 2. Deep Research intent ----
        research = self._detect_research(lower_text)
        if research is not None:
            return research

        # ---- 3. WhatsApp send intent ----
        if self.whatsapp_manager.is_whatsapp_command(text):
            result = self.whatsapp_manager.process_command(text)
            if result and result[0]:
                return result

        # ---- 4. Rules Engine (fast, local, free) ----
        self.history.append({"role": "user", "content": text})
        rule_result = self.rules_engine.match(text)
        if rule_result:
            response, action, params = rule_result
            self.history.append({"role": "assistant", "content": response})
            return response, action, params

        # Keep history short (last 10 messages)
        if len(self.history) > 10:
            self.history = self.history[-10:]

        # ---- 5. General AI conversation (user's own key) ----
        return self._process_general_ai(text)

    # ------------------------------------------------------------------
    # Memory & Reminders
    # ------------------------------------------------------------------

    def _handle_memory_intents(self, text, lower_text):
        """Deterministic handling of remember/forget/remind. Returns a
        (response, action, params) tuple, or None to continue the pipeline."""
        memory = MemoryManager.instance()

        # "remind me ..." — parse the time and schedule it
        if "remind me" in lower_text:
            parsed = parse_reminder(text)
            if parsed:
                task, due = parsed
                memory.add_reminder(task, due)
                nice_time = due.strftime("%I:%M %p").lstrip("0")
                return (f"Done, Boss. I'll remind you to {task} at {nice_time}.",
                        None, None)
            return ("Tell me like: 'remind me in 10 minutes to drink water' "
                    "or 'remind me at 6 pm to call amma'.", None, None)

        # "what are my reminders"
        if re.search(r"\b(my|any|show|list)\b.*\breminders?\b", lower_text) or \
           lower_text.strip() in ("reminders", "show reminders"):
            pending = memory.pending_reminders()
            if not pending:
                return "You have no pending reminders, Boss.", None, None
            lines = []
            for r in pending[:5]:
                t = r["due"][11:16]
                lines.append(f"{r['text']} at {t}")
            return "Your reminders, Boss: " + "; ".join(lines) + ".", None, None

        # "forget ..." — remove matching facts
        m = re.search(r"\bforget\s+(?:about\s+|that\s+)?(.+)", lower_text)
        if m and "forget it" not in lower_text:
            removed = memory.forget(m.group(1))
            if removed:
                return f"Forgotten, Boss. I removed {removed} memory item(s).", None, None
            return "I couldn't find that in my memory, Boss.", None, None

        # "what do you remember / know about me"
        if re.search(r"what do you (remember|know about me)", lower_text) or \
           re.search(r"\b(show|list)\b.*\b(memory|memories)\b", lower_text):
            facts = memory.get_facts(limit=8)
            if not facts:
                return "I don't have any memories yet, Boss. Tell me 'remember ...' and I will.", None, None
            return "Here's what I remember, Boss: " + "; ".join(facts) + ".", None, None

        # "remember ..." — save a fact
        m = re.search(r"\bremember\s+(?:that\s+)?(.+)", text, re.IGNORECASE)
        if m and "do you remember" not in lower_text:
            fact = m.group(1).strip()
            if len(fact) > 2:
                memory.add_fact(fact)
                return "Noted, Boss. I'll remember that.", None, None

        return None

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _process_chat_mode(self, text, contact):
        """Generates a WhatsApp auto-reply from screen-read chat text."""
        if not text or text == "screenshot":
            return None, None, None

        prompt = self.get_chat_mode_prompt(contact, text)
        logger.info("Generating Chat Mode reply...")
        try:
            reply, err = ai_client.chat_completion(
                [{"role": "user", "content": prompt}], max_tokens=100
            )
            if reply:
                if "NO_REPLY" in reply:
                    logger.debug("Brain decided: NO_REPLY")
                    return None, None, None
                return reply, "type_text", {"text": reply}
            logger.error(f"Chat Mode AI error: {err}")
        except Exception as e:
            logger.error(f"Chat Mode Error: {e}", exc_info=True)
        return None, None, None

    def _detect_research(self, lower_text):
        """Returns a (resp, action, params) tuple for research intent, else None."""
        is_research = "research" in lower_text or "analysis" in lower_text

        first_word = lower_text.split(" ")[0] if lower_text.split(" ") else ""
        fuzzy_first = difflib.SequenceMatcher(None, first_word, "research").ratio() > 0.75
        if fuzzy_first:
            is_research = True

        if any(k in lower_text for k in ["deeply", "investigate", "deep dive", "detailed analysis"]):
            is_research = True

        if not is_research:
            return None

        query = lower_text
        if fuzzy_first:
            query = query[len(first_word):].strip()
            if query.startswith("about"):
                query = query[5:].strip()
        for k in ["research about", "research", "deep dive into", "investigate", "analyze"]:
            query = query.replace(k, "")
        query = query.strip()

        if not query:
            return "What should I research about, Boss?", None, None
        return None, "start_research_task", {"query": query}

    def _process_general_ai(self, text):
        """Conversational fallback through the user's AI key."""
        system_prompt = SYSTEM_PROMPT
        facts = MemoryManager.instance().get_facts(limit=20)
        if facts:
            system_prompt += (
                "\n\nTHINGS YOU REMEMBER ABOUT THE USER (mention them naturally when relevant):\n"
                + "\n".join(f"- {f}" for f in facts)
            )

        messages = [{"role": "system", "content": system_prompt}]
        for msg in self.history:
            if msg.get("content"):
                messages.append(msg)
        if not any(m["role"] == "user" for m in messages):
            messages.append({"role": "user", "content": text})

        content, err = ai_client.chat_completion(messages, max_tokens=500)

        if content:
            cleaned = content.replace("```json", "").replace("```", "")
            json_str = self.extract_json(cleaned)
            if json_str:
                try:
                    data = json.loads(json_str, strict=False)
                    response = data.get("response")
                    self.history.append({"role": "assistant", "content": response or ""})

                    # Agentic multi-step plan -> executed by the dispatcher
                    plan = data.get("plan")
                    if plan and isinstance(plan, list):
                        return response, "execute_plan", {"steps": plan}

                    return response, data.get("action"), data.get("parameters")
                except json.JSONDecodeError:
                    pass
            self.history.append({"role": "assistant", "content": cleaned.strip()})
            return cleaned.strip(), None, None

        # ---- Friendly degraded mode (no key / offline) ----
        logger.info(f"AI unavailable ({err}). Using local fallback replies.")
        return self._local_fallback(text, err)

    def _local_fallback(self, text, err):
        lower_text = text.lower()
        if "good morning" in lower_text:
            return "Good morning, Boss! I hope you have a wonderful day.", None, None
        if any(g in lower_text for g in ["hi", "hello", "hey", "hai"]):
            return "Hello Boss! I am here for you.", None, None
        if "who are you" in lower_text:
            return "I am Seetha, your personal AI assistant.", None, None
        if "thank" in lower_text:
            return "You're welcome, Boss!", None, None

        if err == ai_client.NO_KEY_MSG:
            return ("Boss, please open Settings and add your free NVIDIA API key "
                    "so I can answer anything you ask."), None, None
        if not self.check_internet():
            return "Boss, I have no internet connection. Please check your WiFi.", None, None
        return ("I'm connected to the internet, but my AI provider is not responding "
                "right now. Please try again in a moment."), None, None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def check_internet(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

    def extract_json(self, text):
        """Robust JSON extraction by brace counting."""
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

    def generate_code_content(self, topic, language):
        """
        Generates code files for a topic/language via the AI client.
        Returns a list: [{"name": "...", "content": "..."}]
        """
        logger.info(f"Generating code for {topic} in {language}...")
        prompt = f"""
You are an expert programmer.
Task: Write code for "{topic}" in "{language}".
Output Format: JSON ONLY.
Structure:
{{
  "files": [
    {{"name": "filename.ext", "content": "code content here"}}
  ]
}}
Ensure the code is complete and functional.
Do not include any markdown formatting or explanations outside the JSON.
"""
        try:
            content, err = ai_client.chat_completion(
                [
                    {"role": "system", "content": "You are an expert programmer. Output JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                json_mode=True,
            )
            if not content:
                logger.error(f"Code generation failed: {err}")
                return []
            content = content.replace("```json", "").replace("```", "")
            json_str = self.extract_json(content)
            if json_str:
                data = json.loads(json_str, strict=False)
                return data.get("files", [])
            logger.error("Failed to extract JSON from code generation response.")
        except Exception as e:
            logger.error(f"Error generating code: {e}", exc_info=True)
        return []

    def analyze_image(self, image_path):
        logger.info(f"Analyzing image: {image_path}")
        return "Visual analysis is not available in this version."
