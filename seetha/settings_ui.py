"""
Settings window — the one visible place where users add their own
API keys. Rendered dynamically from settings_store.KEY_SPECS, so new
integrations appear here automatically.

Keys are stored ONLY on the user's machine:
    %LOCALAPPDATA%/Seetha/settings.json
"""

import threading
import webbrowser
import tkinter as tk
from tkinter import ttk

from seetha.settings_store import SettingsStore, KEY_SPECS
from seetha import ai_client
from seetha.logger import setup_logger

logger = setup_logger()

COLORS = {
    "bg_dark": "#0d1117",
    "bg_secondary": "#161b22",
    "fg_primary": "#c9d1d9",
    "fg_secondary": "#8b949e",
    "accent_green": "#00ff00",
    "accent_blue": "#58a6ff",
    "btn_green": "#238636",
    "btn_blue": "#1f6feb",
    "border": "#30363d",
}


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self.store = SettingsStore.instance()
        self.entries = {}       # key name -> tk.Entry
        self.secret_state = {}  # key name -> bool (currently hidden?)

        self.title("Seetha Settings — API Keys")
        self.geometry("640x760")
        self.configure(bg=COLORS["bg_dark"])
        self.minsize(560, 500)

        # ---------- Header ----------
        tk.Label(
            self, text="⚙  Settings", font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg_dark"], fg=COLORS["accent_green"]
        ).pack(pady=(18, 2))

        tk.Label(
            self,
            text="Your keys are stored only on this computer and are sent\n"
                 "only to the provider you got them from. Never to us.",
            font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["fg_secondary"],
            justify="center",
        ).pack(pady=(0, 10))

        # ---------- Scrollable body ----------
        body = tk.Frame(self, bg=COLORS["bg_dark"])
        body.pack(fill="both", expand=True, padx=4)

        self.canvas = tk.Canvas(body, bg=COLORS["bg_dark"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=COLORS["bg_dark"])

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._inner_id, width=e.width),
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind("<Destroy>", self._unbind_wheel)

        self._build_rows()

        # ---------- Footer ----------
        footer = tk.Frame(self, bg=COLORS["bg_secondary"])
        footer.pack(fill="x", side="bottom")

        self.status_lbl = tk.Label(
            footer, text=f"Stored at: {self.store.path}", font=("Consolas", 8),
            bg=COLORS["bg_secondary"], fg=COLORS["fg_secondary"], wraplength=600,
        )
        self.status_lbl.pack(pady=(8, 2))

        btns = tk.Frame(footer, bg=COLORS["bg_secondary"])
        btns.pack(pady=(2, 12))

        tk.Button(
            btns, text="💾  Save", command=self._save,
            bg=COLORS["btn_green"], fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", width=14, pady=4,
        ).pack(side="left", padx=6)

        self.btn_test = tk.Button(
            btns, text="🔌  Save & Test AI", command=self._save_and_test,
            bg=COLORS["btn_blue"], fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", width=16, pady=4,
        )
        self.btn_test.pack(side="left", padx=6)

        tk.Button(
            btns, text="Close", command=self.destroy,
            bg=COLORS["border"], fg="white", font=("Segoe UI", 11),
            relief="flat", width=10, pady=4,
        ).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Row construction
    # ------------------------------------------------------------------

    def _build_rows(self):
        current_section = None
        for spec in KEY_SPECS:
            if spec["section"] != current_section:
                current_section = spec["section"]
                self._add_section_header(current_section)
            self._add_key_row(spec)

    def _add_section_header(self, title):
        frame = tk.Frame(self.inner, bg=COLORS["bg_dark"])
        frame.pack(fill="x", padx=16, pady=(18, 4))
        tk.Label(
            frame, text=title.upper(), font=("Segoe UI", 11, "bold"),
            bg=COLORS["bg_dark"], fg=COLORS["accent_blue"], anchor="w",
        ).pack(fill="x")
        tk.Frame(frame, bg=COLORS["border"], height=1).pack(fill="x", pady=(2, 0))

    def _add_key_row(self, spec):
        name = spec["name"]
        row = tk.Frame(self.inner, bg=COLORS["bg_dark"])
        row.pack(fill="x", padx=16, pady=(10, 0))

        # Label line (+ required star + Get-key link)
        label_line = tk.Frame(row, bg=COLORS["bg_dark"])
        label_line.pack(fill="x")

        label_text = spec["label"] + ("  *" if spec.get("required") else "")
        tk.Label(
            label_line, text=label_text, font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg_dark"], fg="white", anchor="w",
        ).pack(side="left")

        if spec.get("help_url"):
            link = tk.Label(
                label_line, text="Get key →", font=("Segoe UI", 9, "underline"),
                bg=COLORS["bg_dark"], fg=COLORS["accent_blue"], cursor="hand2",
            )
            link.pack(side="right")
            link.bind("<Button-1>", lambda e, url=spec["help_url"]: webbrowser.open(url))

        # Entry line (+ show/hide for secrets)
        entry_line = tk.Frame(row, bg=COLORS["bg_dark"])
        entry_line.pack(fill="x", pady=(3, 0))

        is_secret = spec.get("secret", False)
        entry = tk.Entry(
            entry_line, font=("Consolas", 10),
            bg=COLORS["bg_secondary"], fg="white", insertbackground="white",
            relief="flat", show="•" if is_secret else "",
        )
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        entry.insert(0, self.store.get(name))
        self.entries[name] = entry
        self.secret_state[name] = is_secret

        if is_secret:
            btn = tk.Button(
                entry_line, text="👁", font=("Segoe UI", 9),
                bg=COLORS["border"], fg="white", relief="flat", width=3,
                command=lambda n=name: self._toggle_secret(n),
            )
            btn.pack(side="right")

        # Hint line (placeholder guidance)
        hint = spec.get("hint") or ""
        placeholder = spec.get("placeholder") or ""
        hint_text = f"e.g. {placeholder}" if placeholder else ""
        if hint:
            hint_text = f"{hint}   {hint_text}".strip()
        if hint_text:
            tk.Label(
                row, text=hint_text, font=("Segoe UI", 8),
                bg=COLORS["bg_dark"], fg=COLORS["fg_secondary"], anchor="w",
                wraplength=560, justify="left",
            ).pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------
    # Behaviors
    # ------------------------------------------------------------------

    def _toggle_secret(self, name):
        hidden = self.secret_state.get(name, True)
        self.entries[name].config(show="" if hidden else "•")
        self.secret_state[name] = not hidden

    def _collect(self):
        return {name: entry.get() for name, entry in self.entries.items()}

    def _save(self):
        self.store.set_many(self._collect())
        self._set_status("✓ Saved. Keys are stored only on this computer.", COLORS["accent_green"])
        if self.on_saved:
            try:
                self.on_saved()
            except Exception:
                pass

    def _save_and_test(self):
        self._save()
        self.btn_test.config(state="disabled", text="Testing...")
        self._set_status("Contacting AI provider...", "#ffa657")

        def _worker():
            ok, msg = ai_client.test_connection()
            color = COLORS["accent_green"] if ok else "#ff7b72"

            def _done():
                if self.winfo_exists():
                    self._set_status(msg, color)
                    self.btn_test.config(state="normal", text="🔌  Save & Test AI")

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _set_status(self, text, color):
        self.status_lbl.config(text=text, fg=color)

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _unbind_wheel(self, event):
        if event.widget is self:
            try:
                self.canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
