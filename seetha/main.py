"""
Seetha — open-source desktop AI assistant.

Tkinter UI shell: splash, avatar, chat window, Deep Research dashboard,
and the Settings window where users add their own API keys.

No accounts. No login. Everything runs on the user's machine with the
user's own keys.
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext
import webbrowser
import re
import threading
import time
import os

from queue import Queue

from seetha.logger import setup_logger
from seetha.core import SeethaService
from seetha.avatar import SeethaAvatar
from seetha.settings_ui import SettingsWindow
from seetha.command_bar import CommandBar
from seetha import ai_client

logger = setup_logger()

COLORS = {
    "bg_dark": "#0d1117",
    "bg_secondary": "#161b22",
    "fg_primary": "#c9d1d9",
    "fg_secondary": "#8b949e",
    "accent_green": "#00ff00",
    "accent_blue": "#58a6ff",
    "btn_green": "#238636",
    "btn_green_hover": "#2ea043",
    "btn_blue": "#1f6feb",
    "btn_red": "#da3633",
    "border": "#30363d",
    "selection": "#58a6ff",
}


# ============================================================
# Splash Screen
# ============================================================

class SplashScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)

        w, h = 420, 260
        ws = self.winfo_screenwidth()
        hs = self.winfo_screenheight()
        x = (ws - w) // 2
        y = (hs - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=COLORS["bg_dark"])

        tk.Label(
            self, text="SEETHA AI", font=("Segoe UI", 26, "bold"),
            bg=COLORS["bg_dark"], fg=COLORS["accent_green"]
        ).pack(pady=(36, 5))

        tk.Label(
            self, text="Open Source Edition", font=("Segoe UI", 11),
            bg=COLORS["bg_dark"], fg="white"
        ).pack()

        tk.Label(
            self, text="Created by Adharsh Kumar Bachu", font=("Segoe UI", 9),
            bg=COLORS["bg_dark"], fg=COLORS["fg_secondary"]
        ).pack(pady=(4, 0))

        self.status_lbl = tk.Label(
            self, text="Initializing...", font=("Consolas", 10),
            bg=COLORS["bg_dark"], fg=COLORS["fg_secondary"]
        )
        self.status_lbl.pack(pady=(40, 0))
        self.update()

    def update_status(self, text):
        if self.winfo_exists():
            self.status_lbl.config(text=text)
            self.update()


# ============================================================
# Deep Research Dashboard
# ============================================================

class ResearchDashboard(tk.Toplevel):
    def __init__(self, parent, on_research_callback):
        super().__init__(parent)
        self.on_research_callback = on_research_callback

        self.title("Seetha Deep Research Engine")
        self.geometry("900x700")
        self.configure(bg=COLORS["bg_dark"])

        # Header
        header = tk.Frame(self, bg=COLORS["bg_dark"])
        header.pack(fill="x", pady=15, padx=15)

        tk.Label(
            header, text="DEEP RESEARCH COMMAND BOARD",
            font=("Segoe UI", 16, "bold"), bg=COLORS["bg_dark"], fg=COLORS["accent_green"]
        ).pack(side="left")

        # Log Area
        self.log_area = scrolledtext.ScrolledText(
            self, width=100, height=35, font=("Consolas", 11),
            bg=COLORS["bg_dark"], fg=COLORS["fg_primary"],
            selectbackground=COLORS["selection"], insertbackground=COLORS["accent_green"],
            bd=0, highlightthickness=1, highlightbackground=COLORS["border"]
        )
        self.log_area.pack(expand=True, fill="both", padx=15, pady=5)

        self.log_area.tag_config("highlight", foreground="#00ff00")
        self.log_area.tag_config("analysis", foreground="#3399ff")
        self.log_area.tag_config("warning", foreground="#ffa657")
        self.log_area.tag_config("error", foreground="#ff7b72")
        self.log_area.tag_config("header", foreground="#79c0ff", font=("Consolas", 12, "bold"))
        self.log_area.tag_config("user_input", foreground="#d2a8ff", font=("Consolas", 11, "italic"))
        self.log_area.tag_config("white", foreground="#ffffff")
        self.log_area.tag_config("hyperlink", foreground="#58a6ff", underline=1)
        self.log_area.tag_bind("hyperlink", "<Enter>", lambda e: self.log_area.config(cursor="hand2"))
        self.log_area.tag_bind("hyperlink", "<Leave>", lambda e: self.log_area.config(cursor=""))

        # Input Area
        input_frame = tk.Frame(self, bg=COLORS["bg_secondary"], pady=15)
        input_frame.pack(fill="x", side="bottom")

        btn_send = tk.Button(
            input_frame, text="RESEARCH", command=self.trigger_search,
            bg=COLORS["btn_green"], fg="white", font=("Segoe UI", 10, "bold"),
            activebackground=COLORS["btn_green_hover"], activeforeground="white", bd=0, padx=20
        )
        btn_send.pack(side="right", padx=(0, 15), ipady=5)

        btn_dl = tk.Button(
            input_frame, text="Download Report", command=self.download_report,
            bg=COLORS["btn_blue"], fg="white", font=("Segoe UI", 10, "bold"), bd=0, padx=10
        )
        btn_dl.pack(side="right", padx=(0, 10), ipady=5)

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            input_frame, textvariable=self.entry_var, font=("Segoe UI", 12),
            bg=COLORS["bg_dark"], fg="white", insertbackground="white", relief="flat", bd=5
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(15, 10), ipady=5)
        self.entry.bind("<Return>", self.trigger_search)
        self.entry.focus_set()

        # Status Bar
        self.status_var = tk.StringVar(value="Ready to Analyze.")
        tk.Label(
            self, textvariable=self.status_var, font=("Consolas", 9),
            bg=COLORS["bg_secondary"], fg=COLORS["fg_secondary"], anchor="w", padx=10
        ).pack(fill="x", side="bottom")

    def log(self, message, tag=None):
        def _append():
            url_pattern = r'(https?://\S+)'
            parts = re.split(url_pattern, message)
            for part in parts:
                if re.match(url_pattern, part):
                    link_tag = f"link-{len(self.log_area.get('1.0', tk.END))}"
                    self.log_area.insert(tk.END, part, ("hyperlink", tag, link_tag))
                    self.log_area.tag_bind(link_tag, "<Button-1>", lambda e, url=part: webbrowser.open(url))
                else:
                    self.log_area.insert(tk.END, part, tag)
            self.log_area.insert(tk.END, "\n")
            self.log_area.see(tk.END)
        self.after(0, _append)

    def download_report(self):
        content = self.log_area.get("1.0", tk.END)
        if not content.strip():
            messagebox.showinfo("Empty", "Nothing to download yet!")
            return
        try:
            html_content = f"""<html>
<head><style>
body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 40px; }}
pre {{ background: #161b22; color: #c9d1d9; padding: 20px; border-radius: 8px; white-space: pre-wrap; border: 1px solid #30363d; }}
h1 {{ color: #00ff00; border-bottom: 2px solid #30363d; padding-bottom: 10px; }}
.btn {{ background: #238636; color: white; padding: 10px 20px; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; margin-bottom: 20px; }}
@media print {{ .no-print {{ display: none; }} body {{ background: white; color: black; }} pre {{ background: white; color: black; border: 1px solid #ccc; }} }}
</style></head>
<body>
<button class="btn no-print" onclick="window.print()">Save as PDF / Print</button>
<h1>Seetha Research Report</h1>
<p>Generated on {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
<hr style="border-color: #30363d;">
<pre>{content}</pre>
</body></html>"""

            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
            filename = f"Seetha_Research_Report_{int(time.time())}.html"
            full_path = os.path.join(downloads_path, filename)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            webbrowser.open(full_path)
            messagebox.showinfo("Saved", f"Report saved to Downloads:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def trigger_search(self, event=None):
        query = self.entry_var.get().strip()
        if not query:
            return
        self.entry_var.set("")
        self.execute_query(query)

    def execute_query(self, query):
        self.log(f"\n> COMMAND: {query}", "user_input")
        self.status_var.set("Initializing task...")
        if self.on_research_callback:
            threading.Thread(target=self.on_research_callback, args=(self, query), daemon=True).start()

    def set_status(self, message):
        self.after(0, lambda: self.status_var.set(message))


# ============================================================
# Chat Window
# ============================================================

class ChatWindow(tk.Toplevel):
    def __init__(self, parent, process_callback):
        super().__init__(parent)
        self.title("Seetha ChatBox")
        self.geometry("500x700")
        self.configure(bg=COLORS["bg_secondary"])
        self.process_callback = process_callback

        # Input Area (pack first to reserve space at bottom)
        input_frame = tk.Frame(self, bg=COLORS["bg_secondary"])
        input_frame.pack(fill="x", side="bottom", padx=15, pady=15)

        self.btn_send = tk.Button(
            input_frame, text="SEND", command=self.send_command,
            bg=COLORS["btn_green"], fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", height=2, width=8
        )
        self.btn_send.pack(side="right", anchor="s", padx=(5, 0))

        self.input_text = tk.Text(
            input_frame, height=3, font=("Segoe UI", 12),
            bg=COLORS["bg_dark"], fg="white", insertbackground="white",
            bd=1, highlightbackground=COLORS["border"], wrap="word"
        )
        self.input_text.pack(side="left", fill="both", expand=True)

        self.input_text.bind("<Return>", self._handle_return)
        self.input_text.bind("<Shift-Return>", lambda e: None)
        self.input_text.focus_set()

        # History Area
        self.history = scrolledtext.ScrolledText(
            self, width=60, height=30, font=("Segoe UI", 11),
            bg=COLORS["bg_dark"], fg=COLORS["fg_primary"],
            selectbackground=COLORS["selection"], insertbackground=COLORS["accent_green"],
            bd=0, highlightthickness=0, wrap="word"
        )
        self.history.pack(expand=True, fill="both", padx=15, pady=(15, 0))

        self.history.tag_config("user", foreground="#79c0ff")
        self.history.tag_config("seetha", foreground="#00ff00")
        self.history.tag_config("system", foreground=COLORS["fg_secondary"], font=("Consolas", 9, "italic"))
        self.history.insert(tk.END, "--- Start of Conversation ---\n", "system")
        self.history.configure(state="disabled")

    def _handle_return(self, event):
        self.send_command()
        return "break"

    def send_command(self):
        text = self.input_text.get("1.0", tk.END).strip()
        if text:
            self.input_text.delete("1.0", tk.END)
            self.add_message("You", text)
            threading.Thread(target=self.process_callback, args=(text,), daemon=True).start()

    def add_message(self, sender, text):
        def _append():
            self.history.configure(state="normal")
            if sender == "You":
                self.history.insert(tk.END, f"\nYou:\n{text}\n", "user")
            elif sender == "Seetha":
                self.history.insert(tk.END, f"\nSeetha:\n{text}\n", "seetha")
            else:
                self.history.insert(tk.END, f"\n[{sender}]: {text}\n", "system")
            self.history.configure(state="disabled")
            self.history.see(tk.END)
        self.after(0, _append)


# ============================================================
# Main Application
# ============================================================

class SeethaApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()

        # State
        self.is_active = False
        self.show_avatar = True
        self.chat_window = None
        self.settings_window = None
        self.command_bar = None
        self.tray_icon = None

        # Splash
        self.splash = SplashScreen(root)

        # Service Layer
        self.ui_queue = Queue()
        self.service = SeethaService(self.ui_queue)

        # Start UI polling and async component loading
        self._poll_ui_queue()
        threading.Thread(target=self.service.initialize_components, daemon=True).start()

    # ========================
    # UI Queue Polling
    # ========================

    def _poll_ui_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                self._handle_ui_event(msg)
        except Exception:
            pass
        self.root.after(50, self._poll_ui_queue)

    def _handle_ui_event(self, msg):
        event = msg.get("type")
        data = msg.get("data")

        if event == "status":
            self._update_status(data)
        elif event == "ready":
            self._finalize_launch()
        elif event == "chat_message":
            self._on_chat_message(data["sender"], data["text"])
        elif event == "avatar_start":
            if self.show_avatar and hasattr(self, 'avatar'):
                self.avatar.start_speaking()
        elif event == "avatar_stop":
            if self.show_avatar and hasattr(self, 'avatar'):
                self.avatar.stop_speaking()
        elif event == "launch_research":
            self._launch_research_dashboard(data.get("query"))
        elif event == "reminder":
            self._on_reminder(data.get("text", ""))
        elif event == "error":
            messagebox.showerror("System Error", str(data))

    def _on_reminder(self, text):
        """Makes a due reminder IMPOSSIBLE to miss: log line, Windows
        tray notification, and the window pops to the front briefly."""
        self._log(f"⏰ REMINDER: {text}")

        # Windows notification balloon via the tray icon
        if self.tray_icon:
            try:
                self.tray_icon.notify(f"⏰ {text}", "Seetha Reminder")
            except Exception as e:
                logger.warning(f"Tray notification failed: {e}")

        # Bring the window to the front so the reminder is seen even
        # if sound is muted
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(4000, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _update_status(self, text):
        if hasattr(self, 'splash') and self.splash.winfo_exists():
            self.splash.update_status(text)
        if hasattr(self, 'status_label'):
            self.status_label.config(text=text)

    # ========================
    # Launch Sequence
    # ========================

    def _finalize_launch(self):
        if hasattr(self, 'splash') and self.splash.winfo_exists():
            self.splash.destroy()
        self.root.deiconify()
        self.root.title("Seetha - Open Source AI Assistant")
        self.root.geometry("450x950")
        self.root.configure(bg=COLORS["bg_dark"])
        self._setup_ui()
        self._setup_tray_and_hotkey()
        self._log("System initialized successfully.")
        self._log("Tip: Press Ctrl+Space anywhere for the command bar. Closing this window minimizes to tray.")

        # First-run experience: no AI key yet -> open Settings with a hint
        if not ai_client.has_brain_key():
            self._log("No AI key found. Opening Settings — add your free NVIDIA key.")
            self.root.after(600, self._open_settings)

    def _setup_tray_and_hotkey(self):
        """Tray icon + global Ctrl+Space hotkey. Both are optional extras —
        failures never block the app."""
        # Command bar (created hidden, reused forever)
        self.command_bar = CommandBar(self.root, on_submit=self._command_bar_submit)

        # Tray icon — lets Seetha live in the background
        try:
            from seetha.tray import create_tray
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", "seetha_main.png"
            )
            self.tray_icon = create_tray(
                icon_path,
                on_show=lambda: self.root.after(0, self._show_window),
                on_command_bar=lambda: self.root.after(0, self._toggle_command_bar),
                on_quit=lambda: self.root.after(0, self._quit_app),
            )
        except Exception as e:
            logger.warning(f"Tray setup failed: {e}")
            self.tray_icon = None

        # Close button: minimize to tray when a tray icon exists,
        # otherwise quit normally.
        if self.tray_icon:
            self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

        # Global hotkey (works even when another app has focus)
        try:
            import keyboard
            keyboard.add_hotkey(
                "ctrl+space",
                lambda: self.root.after(0, self._toggle_command_bar),
            )
            logger.info("Global hotkey Ctrl+Space registered.")
        except Exception as e:
            logger.warning(f"Global hotkey unavailable: {e}")

    def _hide_to_tray(self):
        self.root.withdraw()
        logger.info("Seetha minimized to tray.")

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()

    def _toggle_command_bar(self):
        if self.command_bar and self.command_bar.winfo_exists():
            self.command_bar.toggle()

    def _command_bar_submit(self, text):
        self._log(f"[Command Bar] {text}")
        threading.Thread(target=self._process_text_input, args=(text,), daemon=True).start()

    def _quit_app(self):
        logger.info("Quitting Seetha.")
        try:
            self.service.stop_service()
        except Exception:
            pass
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.root.destroy()

    def _setup_ui(self):
        # Status Label
        self.status_label = tk.Label(
            self.root, text="Status: Ready",
            font=("Segoe UI", 13), bg=COLORS["bg_dark"], fg="white"
        )
        self.status_label.pack(pady=10)

        # Top Buttons
        btn_frame = tk.Frame(self.root, bg=COLORS["bg_dark"])
        btn_frame.pack(anchor="ne", padx=10)

        tk.Button(
            btn_frame, text="⚙ Settings", command=self._open_settings,
            font=("Segoe UI", 9, "bold"), bg=COLORS["border"], fg="white", relief="flat", padx=10
        ).pack(side="left", padx=5)

        # Avatar
        self.avatar_frame = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self.avatar_frame.pack(pady=10)

        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        self.avatar = SeethaAvatar(self.avatar_frame, assets_dir)
        self.avatar.pack()

        self.btn_avatar_toggle = tk.Button(
            self.root, text="Hide Face", command=self._toggle_avatar,
            bg="pink", fg="black", font=("Segoe UI", 9), relief="flat"
        )
        self.btn_avatar_toggle.pack(pady=5)

        # Activate Button
        self.btn_toggle = tk.Button(
            self.root, text="Activate Seetha", command=self._toggle_activation,
            bg=COLORS["btn_green"], fg="white", font=("Segoe UI", 12, "bold"),
            height=2, width=20, relief="flat"
        )
        self.btn_toggle.pack(pady=10)

        # Chat Button
        tk.Button(
            self.root, text="START CHAT", command=self._open_chat_window,
            bg=COLORS["accent_blue"], fg="white", font=("Segoe UI", 10, "bold"),
            width=20, relief="flat"
        ).pack(pady=5)

        # Research Button
        tk.Button(
            self.root, text="🔬 DEEP RESEARCH", command=lambda: self._launch_research_dashboard(None),
            bg="#8957e5", fg="white", font=("Segoe UI", 10, "bold"),
            width=20, relief="flat"
        ).pack(pady=5)

        # Log Area
        self.log_area = scrolledtext.ScrolledText(
            self.root, width=45, height=12, font=("Consolas", 10),
            bg=COLORS["bg_dark"], fg=COLORS["fg_primary"],
            insertbackground=COLORS["accent_green"],
            selectbackground=COLORS["selection"],
            bd=0, highlightthickness=1, highlightbackground=COLORS["border"]
        )
        self.log_area.pack(pady=10, padx=10, fill="x")

    # ========================
    # Helpers
    # ========================

    def _log(self, message):
        logger.info(message)
        if hasattr(self, 'log_area'):
            self.root.after(0, lambda: self._log_impl(message))

    def _log_impl(self, message):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)

    def _on_chat_message(self, sender, text):
        self._log(f"{sender}: {text}")
        if self.chat_window and self.chat_window.winfo_exists():
            display_sender = "You" if sender == "User" else sender
            self.chat_window.add_message(display_sender, text)

    # ========================
    # User Actions
    # ========================

    def _open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(self.root, on_saved=lambda: self._log("Settings saved."))

    def _toggle_activation(self):
        if self.is_active:
            self.is_active = False
            self.service.stop_service()
            self.btn_toggle.config(text="Activate Seetha", bg=COLORS["btn_green"])
            self._update_status("Status: Ready")
            self._log("Seetha deactivated.")
        else:
            self.is_active = True
            self.btn_toggle.config(text="Deactivate Seetha", bg=COLORS["btn_red"])
            self._update_status("Status: Listening...")
            self._log("Seetha activated. Listening for commands...")
            self.service.start_service()

    def _toggle_avatar(self):
        if self.show_avatar:
            self.show_avatar = False
            self.avatar.pack_forget()
            self.btn_avatar_toggle.config(text="Show Face")
        else:
            self.show_avatar = True
            self.avatar.pack()
            self.btn_avatar_toggle.config(text="Hide Face")

    def _open_chat_window(self):
        if self.chat_window and self.chat_window.winfo_exists():
            self.chat_window.lift()
            return
        self.chat_window = ChatWindow(self.root, self._process_text_input)

    def _process_text_input(self, text):
        if not text or not self.service.brain:
            return
        # Note: ChatWindow already echoed the user's message — only log here,
        # or the message would appear twice in the chat history.
        self._log(f"User: {text}")
        try:
            result = self.service.brain.process(text)
            if not result:
                return

            response_text, action, params = result

            if response_text:
                self.service.speak(response_text)

            if action and self.service.dispatcher:
                result_msg = self.service.dispatcher.dispatch(action, params or {})
                if result_msg:
                    self.service.speak(result_msg)

        except Exception as e:
            logger.error(f"Chat Processing Error: {e}", exc_info=True)
            self.service.speak("Sorry Boss, I had a brain freeze.")

    # ========================
    # Research Dashboard
    # ========================

    def _launch_research_dashboard(self, query):
        def _launch():
            try:
                dboard = ResearchDashboard(self.root, on_research_callback=self._run_research_task)
                if query:
                    dboard.execute_query(query)
            except Exception as e:
                self._log(f"Error launching research dashboard: {e}")
        self.root.after(0, _launch)

    def _run_research_task(self, dboard, query):
        try:
            from seetha.premium_research import ResearchEngine
            import json as _json

            engine = ResearchEngine()

            for event_str in engine.execute_task(query):
                data = _json.loads(event_str)
                etype = data.get("event")
                payload = data.get("payload")

                def _update_ui(p_etype=etype, p_payload=payload):
                    text = p_payload.get("display_text", "")
                    if p_etype == "insight_verified":
                        dboard.log(text, "highlight")
                    elif p_etype == "analysis_progress":
                        dboard.log(text, "analysis")
                    elif p_etype == "final_report":
                        dboard.log("\n=== RESEARCH REPORT ===", "header")
                        dboard.log(p_payload.get("report_content", ""), "white")
                    elif p_etype == "confidence":
                        dboard.log(text, "white")
                    elif p_etype == "error":
                        dboard.log(text, "error")
                    else:
                        dboard.log(text, "white")

                dboard.after(0, _update_ui)

        except Exception as e:
            dboard.after(0, lambda: dboard.log(f"CRITICAL ERROR: {e}", "error"))


# ============================================================
# Entry Point
# ============================================================

def launch_app():
    root = tk.Tk()
    SeethaApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        launch_app()
    except Exception as e:
        logger.critical(f"Fatal Application Crash: {e}", exc_info=True)
