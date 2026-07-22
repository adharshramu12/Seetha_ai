"""
SeethaService — the orchestration core.

Runs the Listen -> Process -> Dispatch -> Speak loop on a background
thread, fully decoupled from the Tkinter UI. All UI updates travel
through a thread-safe queue as {"type": ..., "data": ...} events.
"""

import threading
import time
from queue import Queue

from seetha.logger import setup_logger

logger = setup_logger()


class SeethaService:
    def __init__(self, ui_queue: Queue):
        self.ui_queue = ui_queue
        self.running = False

        self.actions = None
        self.ears = None
        self.mouth = None
        self.brain = None
        self.dispatcher = None

        self.chat_mode_active = False

        self._lock = threading.RLock()

    def initialize_components(self):
        """Lazy-loads all components in a background thread."""
        logger.info("Service: Initializing Core Components...")
        try:
            self.emit_ui("status", "Loading Actions Engine...")
            from seetha.actions import SeethaActions
            self.actions = SeethaActions()

            self.emit_ui("status", "Loading Hearing System...")
            from seetha.ears import SeethaEars
            self.ears = SeethaEars()

            self.emit_ui("status", "Loading Speech Engine...")
            from seetha.mouth import SeethaMouth
            self.mouth = SeethaMouth()

            self.emit_ui("status", "Loading Neural Engine...")
            from seetha.brain import SeethaBrain
            self.brain = SeethaBrain(self.actions)

            self.emit_ui("status", "Starting Dispatcher...")
            from seetha.dispatcher import ActionDispatcher
            self.dispatcher = ActionDispatcher(self)

            # Reminder scheduler runs for the app's whole lifetime,
            # independent of whether voice listening is active.
            threading.Thread(target=self._reminder_loop, daemon=True).start()

            logger.info("Service: All components loaded successfully.")
            self.emit_ui("ready", None)
            return True
        except Exception as e:
            logger.error(f"Service Init Failed: {e}", exc_info=True)
            self.emit_ui("error", str(e))
            return False

    def start_service(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()

    def stop_service(self):
        self.running = False
        self.chat_mode_active = False

    def emit_ui(self, event_type, data):
        self.ui_queue.put({"type": event_type, "data": data})

    def speak(self, text):
        if not text or not self.mouth:
            return
        self.emit_ui("avatar_start", None)
        self.emit_ui("chat_message", {"sender": "Seetha", "text": text})
        try:
            self.mouth.speak(text)
        finally:
            self.emit_ui("avatar_stop", None)

    def _run_loop(self):
        """Main AI Loop: Listen -> Process -> Dispatch -> Speak"""
        logger.info("Service: AI Loop Started.")

        while self.running:
            if not self.ears or not self.brain:
                time.sleep(1)
                continue

            try:
                self.emit_ui("status", "Listening...")
                command = self.ears.listen()

                if not command:
                    continue

                self.emit_ui("chat_message", {"sender": "User", "text": command})
                self.emit_ui("status", "Processing...")

                result = self.brain.process(command)
                if not result:
                    continue

                response_text, action, params = result

                if response_text:
                    self.speak(response_text)

                if action and self.dispatcher:
                    self.emit_ui("status", f"Executing: {action}...")
                    try:
                        result_msg = self.dispatcher.dispatch(action, params or {})
                        if result_msg:
                            self.speak(result_msg)
                    except Exception as e:
                        logger.error(f"Dispatcher Error: {e}", exc_info=True)
                        self.speak("I tried to do that, but something went wrong.")

            except Exception as e:
                logger.error(f"Loop Error: {e}", exc_info=True)
                time.sleep(1)

        logger.info("Service: AI Loop Stopped.")

    # ==========================================
    # Reminder Scheduler
    # ==========================================

    def _reminder_loop(self):
        """Checks every 10s for due reminders and announces them with
        sound + Windows notification + voice."""
        from seetha.memory import MemoryManager
        logger.info("Reminder scheduler started.")
        while True:
            try:
                for reminder in MemoryManager.instance().pop_due_reminders():
                    text = reminder.get("text", "your reminder")
                    logger.info(f"Reminder due: {text}")

                    # 1. Audible alert chime (independent of TTS)
                    try:
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except Exception:
                        pass

                    # 2. Visual notification (tray balloon + window popup,
                    #    handled by the UI layer)
                    self.emit_ui("reminder", {"text": text})
                    self.emit_ui("status", "Reminder!")

                    # 3. Voice announcement
                    self.speak(f"Boss, reminder: {text}!")
                    self.emit_ui("status", "Ready")
            except Exception as e:
                logger.error(f"Reminder loop error: {e}")
            time.sleep(10)

    # ==========================================
    # Chat Mode (WhatsApp auto-reply loop)
    # ==========================================

    def start_chat_mode_thread(self, contact):
        if self.chat_mode_active:
            return
        self.chat_mode_active = True
        threading.Thread(target=self._chat_mode_loop, args=(contact,), daemon=True).start()

    def stop_chat_mode_thread(self):
        self.chat_mode_active = False

    def _chat_mode_loop(self, contact):
        logger.info(f"Chat Mode active with {contact}")
        self.emit_ui("status", f"Chat Mode: {contact}")

        while self.chat_mode_active and self.running:
            try:
                content = self.actions.read_specific_chat_area()
                if content:
                    response, action, params = self.brain.process(
                        content, mode="chat_mode", contact=contact
                    )
                    if response and action == "type_text":
                        self.actions.type_text(params.get("text", ""))
                        import pyautogui
                        pyautogui.press("enter")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Chat Mode Error: {e}")
                time.sleep(2)

        logger.info("Chat Mode stopped.")

    # ==========================================
    # Proxy methods for Dispatcher / UI compatibility
    # ==========================================

    def log(self, message):
        logger.info(message)

    def set_status(self, text):
        self.emit_ui("status", text)

    def launch_research_dashboard(self, query):
        self.emit_ui("launch_research", {"query": query})
