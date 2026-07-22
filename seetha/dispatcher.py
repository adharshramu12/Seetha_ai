"""
ActionDispatcher — executes actions decided by the Brain.

Every action name maps to a handle_<action> method. The dispatcher only
talks to the Service layer (speak/status/UI events) and the Actions
engine — it knows nothing about Tkinter.
"""

import time

from seetha.logger import setup_logger

logger = setup_logger()


class ActionDispatcher:
    def __init__(self, service_context):
        """
        service_context: the SeethaService instance (provides .actions,
        .brain, .ears, .speak(), .emit_ui(), ...).
        """
        self.service = service_context
        self.actions = self.service.actions

    def dispatch(self, action_name: str, params: dict):
        """Routes an action to its handler. Returns a result message or None."""
        method_name = f"handle_{action_name}"

        # Late binding in case components weren't ready at init
        if not self.actions and self.service.actions:
            self.actions = self.service.actions

        if hasattr(self, method_name):
            try:
                handler = getattr(self, method_name)
                return handler(params)
            except Exception as e:
                logger.error(f"Error executing {action_name}: {e}", exc_info=True)
                return f"Sorry Boss, I encountered an error while trying to {action_name.replace('_', ' ')}."
        else:
            logger.warning(f"Unknown action: {action_name}")
            return f"Sorry Boss, I don't know how to perform action: {action_name}"

    # ==========================
    # Agentic Plan Executor  (observe -> act -> VERIFY -> retry)
    # ==========================

    # Actions worth verifying on screen. Fast actions (volume etc.)
    # are not verified — verification costs a vision call.
    VERIFIABLE_ACTIONS = {"open_app", "close_app"}

    def handle_execute_plan(self, params):
        """
        Executes a multi-step plan from the Brain, one action at a time.
        After each verifiable step it takes a screenshot, asks a vision
        model "did that work?", and RETRIES once if it didn't — the
        observe->act->verify agent pattern. If no vision provider is
        configured, it degrades gracefully to blind execution.
        """
        steps = params.get("steps") or []
        if not steps:
            return None

        total = len(steps)
        logger.info(f"Executing agentic plan with {total} step(s).")
        failures = []

        for i, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            action = step.get("action")
            p = step.get("parameters") or {}

            # Safety: no nested plans
            if not action or action == "execute_plan":
                continue

            logger.info(f"Plan step {i}/{total}: {action} {p}")
            self.service.emit_ui("status", f"Step {i}/{total}: {action.replace('_', ' ')}...")

            step_failed = False
            try:
                msg = self.dispatch(action, p)
                if msg and "sorry" in msg.lower():
                    step_failed = True
            except Exception as e:
                logger.error(f"Plan step failed ({action}): {e}", exc_info=True)
                step_failed = True

            # Give newly-opened apps time to take keyboard focus before
            # the next step (critical for open_app -> type_text chains).
            if action in ("open_app", "open_multiple_apps"):
                time.sleep(2.5)
            else:
                time.sleep(0.5)

            # ---- OBSERVE & VERIFY ----
            if not step_failed and action in self.VERIFIABLE_ACTIONS:
                verdict = self._verify_step(action, p)
                if verdict is False:
                    logger.warning(f"Verification says step {i} ({action}) did NOT work. Retrying once...")
                    self.service.emit_ui("status", f"Step {i}/{total}: retrying...")
                    try:
                        self.dispatch(action, p)
                        time.sleep(2.5)
                    except Exception:
                        pass
                    if self._verify_step(action, p) is False:
                        step_failed = True

            if step_failed:
                failures.append(action.replace("_", " "))

        if failures:
            return f"Task finished, Boss, but I had trouble with: {', '.join(failures)}."
        return "All tasks completed, Boss!"

    def _verify_step(self, action, params):
        """
        Screenshots the desktop and asks a vision model whether the
        action visibly succeeded.
        Returns True (worked), False (didn't), or None (can't verify —
        no vision provider / vision error; treated as success).
        """
        try:
            import pyautogui
            from seetha import ai_client

            shot = pyautogui.screenshot()
            target = params.get("app_name") or params.get("apps") or ""
            question = (
                f"A Windows assistant just performed the action '{action}' "
                f"targeting '{target}'. Look at this screenshot of the desktop. "
                f"Did the action visibly succeed (for open_app: is that application's "
                f"window now visible; for close_app: is it gone)? "
                f"Reply with exactly YES or NO followed by a very short reason."
            )
            answer, err = ai_client.vision_completion(question, shot, max_tokens=60)
            if not answer:
                logger.debug(f"Verification unavailable ({err}) — continuing blind.")
                return None

            logger.info(f"Verification[{action} -> {target}]: {answer[:120]}")
            head = answer.strip().upper()[:12]
            if head.startswith("NO"):
                return False
            if head.startswith("YES"):
                return True
            return None  # ambiguous — don't punish the step
        except Exception as e:
            logger.warning(f"Verification error: {e}")
            return None

    # ==========================
    # Action Handlers
    # ==========================

    def handle_search_file(self, params):
        filename = params.get("filename")
        result = self.actions.search_file(filename)
        if result:
            return f"Boss, I found the file at {result}"
        return f"Sorry Boss, I couldn't find the file {filename}."

    def handle_open_app(self, params):
        app_name = params.get("app_name")
        if self.actions.open_app(app_name):
            return f"{app_name} opened. Task completed, Boss."
        return f"Sorry Boss, I couldn't open {app_name}."

    def handle_open_multiple_apps(self, params):
        apps = params.get("apps", [])
        self.actions.open_multiple_apps(apps)
        return "Task completed, Boss."

    def handle_type_text(self, params):
        text = params.get("text")
        if self.actions.type_text(text):
            return "Typing completed, Boss."
        return "Sorry Boss, I couldn't type that."

    def handle_send_whatsapp(self, params):
        contact = params.get("contact")
        message = params.get("message")

        if hasattr(self.service.brain, "whatsapp_manager"):
            self.service.brain.whatsapp_manager.execute_automation(contact, message)
        else:
            self.actions.send_whatsapp(contact, message)

        return f"Sending message to {contact}."

    def handle_open_whatsapp_chat(self, params):
        contact = params.get("contact")
        self.service.speak("Boss, I found the contact chat. What can I do now?")
        self.actions.open_whatsapp_chat(contact)
        return None

    def handle_send_active_chat_message(self, params):
        message = params.get("message")
        self.actions.send_active_chat_message(message)
        return "Message sent, Boss."

    def handle_open_desktop_icon(self, params):
        name = params.get("name")
        if self.actions.open_desktop_icon(name):
            return f"Opening {name} from desktop."
        return f"Sorry Boss, I couldn't find {name} on the desktop."

    def handle_open_taskbar_icon(self, params):
        name = params.get("name")
        if self.actions.open_taskbar_icon(name):
            return f"Opening {name} from taskbar."
        return f"Sorry Boss, I couldn't find {name} on the taskbar."

    def handle_select_all(self, params):
        self.actions.select_all()
        return "Selected all items, Boss."

    def handle_empty_recycle_bin(self, params):
        # Destructive — voice confirmation required
        self.service.speak("Boss, this will delete everything in the bin forever. Say 'Confirm' to proceed.")
        confirmation = self.service.ears.listen()
        if confirmation and "confirm" in confirmation.lower():
            if self.actions.empty_recycle_bin():
                return "Recycle Bin emptied, Boss."
            return "Sorry Boss, I couldn't empty the Recycle Bin."
        return "Action cancelled for security."

    def handle_media_control(self, params):
        command = params.get("command")
        if self.actions.media_control(command):
            return f"Media command '{command}' executed."
        return f"Sorry Boss, I couldn't execute '{command}'."

    def handle_close_app(self, params):
        app_name = params.get("app_name")
        if self.actions.close_app(app_name):
            return f"The task is completed, Boss. Closed {app_name}."
        return f"Sorry Boss, I couldn't close {app_name}."

    def handle_close_tab(self, params):
        self.actions.close_tab()
        return "Closed the tab, Boss."

    def handle_close_all_apps(self, params):
        self.service.speak("Closing all apps, Boss. Give me a second.")
        if self.actions.close_all_apps():
            return "All apps closed, Boss."
        return "Sorry Boss, I couldn't close everything."

    def handle_close_active_window(self, params):
        self.actions.close_active_window()
        return "Closed the window, Boss."

    def handle_play_song(self, params):
        song_name = params.get("song_name")
        self.service.speak(f"Playing {song_name} on YouTube.")
        if self.actions.play_song(song_name):
            return "Song started. Task completed, Boss."
        return f"Sorry Boss, I couldn't play {song_name}."

    def handle_whatsapp_call(self, params):
        contact = params.get("contact")
        video = params.get("video", False)
        type_str = "Video Call" if video else "Voice Call"
        self.service.speak(f"Starting {type_str} to {contact}.")
        self.actions.whatsapp_call(contact, video)
        return None

    def handle_start_chat_mode(self, params):
        contact = params.get("contact")
        self.service.speak(f"Starting Chat Mode with {contact}. Say 'Stop' to end.")
        self.actions.open_whatsapp_chat(contact)
        self.service.start_chat_mode_thread(contact)
        return None

    def handle_stop_chat_mode(self, params):
        self.service.stop_chat_mode_thread()
        return "Chat mode stopped, Boss."

    def handle_search_in_app(self, params):
        query = params.get("query")
        self.service.speak(f"Searching for {query}.")
        self.actions.search_in_app(query)
        return None

    def handle_read_screen(self, params):
        self.service.speak("Reading screen content...")
        content = self.actions.read_screen()

        if content:
            logger.info(f"Screen Content: {content[:100]}...")
            self.service.speak("I've read it. Analyzing...")

            new_prompt = (f"I have read the screen. The content is:\n{content}\n\n"
                          f"Based on this, fulfill my previous request.")
            response_text, action, sub_params = self.service.brain.process(new_prompt)

            if response_text:
                self.service.speak(response_text)
            if action == "type_text":
                self.handle_type_text(sub_params)
                return "Typing reply."
            return None
        return "I couldn't read anything."

    def handle_control_volume(self, params):
        action = params.get("action")
        if self.actions.control_volume(action):
            if action == "mute":
                return "Muted. Task completed, Boss."
            return f"Volume turned {action}. Task completed, Boss."
        return "Sorry Boss, I couldn't adjust the volume."

    def handle_control_brightness(self, params):
        action = params.get("action")
        level = params.get("level")
        if self.actions.control_brightness(action, level=level):
            if action == "set":
                return f"Brightness set to {level} percent. Task completed, Boss."
            return f"Brightness turned {action}. Task completed, Boss."
        return "Sorry Boss, I couldn't adjust the brightness."

    def handle_click_element(self, params):
        text = params.get("text")
        self.service.speak(f"Clicking {text}, Boss.")
        if self.actions.click_element(text):
            return None
        return f"Sorry Boss, I couldn't find {text} to click."

    def handle_take_screenshot(self, params):
        self.service.speak("Taking screenshot, Boss.")
        path = self.actions.take_screenshot()
        if path:
            return f"Saved screenshot to {path}"
        return "Sorry Boss, I couldn't take the screenshot."

    def handle_write_code_in_notepad(self, params):
        files = params.get("files")
        if self.actions.write_code_in_notepad(files):
            return "Boss, I completed the task."
        return "Sorry Boss, I had trouble writing to Notepad."

    def handle_see_object(self, params):
        return "Camera is not available in this version."

    def handle_start_research_task(self, params):
        query = params.get("query")
        logger.info(f"Starting Deep Research: {query}")
        self.service.emit_ui("status", "Researching...")
        self.service.launch_research_dashboard(query)
        return None

    def handle_play_youtube(self, params):
        query = params.get("query")
        if not query:
            return None

        self.service.speak(f"Playing {query} on YouTube.")
        import webbrowser
        from duckduckgo_search import DDGS

        url = f"https://www.youtube.com/results?search_query={query}"
        try:
            with DDGS() as ddgs:
                results = list(ddgs.videos(query, max_results=1))
                if results and "content" in results[0]:
                    url = results[0]["content"]
                    logger.info(f"Found Direct Video: {url}")
        except Exception as e:
            logger.error(f"Direct Play Error: {e}")

        webbrowser.open(url)
        return None

    def handle_create_instant_meeting(self, params):
        self.service.speak("Creating a meeting and saving the link to Notepad for you, Boss.")
        result = self.actions.create_instant_meeting()
        if result:
            # result is the room URL — put it on the clipboard too so the
            # user can paste it anywhere.
            try:
                import pyperclip
                pyperclip.copy(result)
            except Exception:
                pass
            return f"Meeting ready and saved to Notepad, Boss. The link is {result}"
        return "Sorry Boss, I couldn't create the meeting. Please make sure a browser is open and try again."
