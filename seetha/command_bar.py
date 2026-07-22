"""
Spotlight-style command bar.

Summoned from ANYWHERE with Ctrl+Space (or the tray menu): a slim,
borderless, always-on-top input floating near the top of the screen.
Type a command, press Enter, and it flows through the normal
Brain -> Dispatcher pipeline. Escape hides it.
"""

import tkinter as tk

from seetha.logger import setup_logger

logger = setup_logger()

COLORS = {
    "bg_dark": "#0d1117",
    "bg_secondary": "#161b22",
    "fg_secondary": "#8b949e",
    "accent_green": "#00ff00",
    "border": "#30363d",
}


class CommandBar(tk.Toplevel):
    def __init__(self, parent, on_submit):
        super().__init__(parent)
        self.on_submit = on_submit

        self.overrideredirect(True)          # no title bar — Spotlight look
        self.attributes("-topmost", True)

        w, h = 680, 92
        ws = self.winfo_screenwidth()
        x = (ws - w) // 2
        y = int(self.winfo_screenheight() * 0.18)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Border frame for a subtle glow edge
        outer = tk.Frame(self, bg=COLORS["accent_green"])
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=COLORS["bg_dark"])
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(
            inner, text="🎙  Ask Seetha anything — Enter to run, Esc to hide",
            font=("Segoe UI", 8), bg=COLORS["bg_dark"], fg=COLORS["fg_secondary"],
            anchor="w",
        ).pack(fill="x", padx=14, pady=(8, 0))

        self.entry = tk.Entry(
            inner, font=("Segoe UI", 16),
            bg=COLORS["bg_dark"], fg="white", insertbackground=COLORS["accent_green"],
            relief="flat", bd=0,
        )
        self.entry.pack(fill="x", padx=14, pady=(4, 10), ipady=6)

        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.bind("<FocusOut>", self._on_focus_out)

        self.withdraw()  # start hidden

    # ------------------------------------------------------------------

    def toggle(self):
        if self.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def show(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(50, self._grab_focus)

    def _grab_focus(self):
        try:
            self.focus_force()
            self.entry.focus_set()
            self.entry.select_range(0, tk.END)
        except Exception:
            pass

    def hide(self):
        try:
            self.withdraw()
        except Exception:
            pass

    def _on_focus_out(self, event):
        # Hide when the user clicks elsewhere (like Spotlight),
        # but only if focus truly left this window.
        try:
            if self.focus_get() is None:
                self.hide()
        except Exception:
            self.hide()

    def _submit(self, event=None):
        text = self.entry.get().strip()
        if not text:
            self.hide()
            return
        self.entry.delete(0, tk.END)
        self.hide()
        logger.info(f"Command bar: {text!r}")
        try:
            self.on_submit(text)
        except Exception as e:
            logger.error(f"Command bar submit error: {e}", exc_info=True)
