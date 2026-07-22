# Seetha AI 🎙️ — Open Source Desktop AI Assistant for Windows

> Talk to your computer. Seetha listens, answers with a voice and an animated
> avatar, and actually *does things* — opens apps, plays songs, sends WhatsApp
> messages, controls volume/brightness, and runs multi-source deep research.

**Created by [Adharsh Kumar Bachu](https://github.com/adharshramu12)** · MIT License

**Bring your own (free) API key. No account. No server. No telemetry.**
Your keys and your data never leave your machine.

```
🎤 Ears (voice) ──▶ 🧠 Brain (rules + AI) ──▶ ⚡ Dispatcher ──▶ 🖱 Actions (automation)
                          │                                        │
                          ▼                                        ▼
                     🔊 Mouth (TTS)                          👩 Avatar (UI)
```

---

## ✨ What Seetha can do

| Category | Examples of what you can say |
|---|---|
| **Talk** | "Good morning", "Who are you?", anything — real AI conversation |
| **Open / close apps** | "Open Chrome", "Close Notepad", "Close everything" |
| **Multi-step tasks** 🤖 | "Open Notepad and write a poem about rain" — the AI plans the steps, executes them, and **verifies each one on screen** with a vision model |
| **Music & media** | "Play melody songs", "Pause", "Next song", "Mute" |
| **System control** | "Increase the volume", "Dim the screen", "Set brightness to 40", "Take a screenshot" — any phrasing, executed directly |
| **Memory** 🧠 | "Remember my exam is on Friday", "What do you remember?", "Forget that" — survives restarts, injected into every conversation |
| **Reminders** ⏰ | "Remind me at 6 pm to call amma" — chime + Windows notification + voice |
| **WhatsApp** | "Send a WhatsApp message to Ramu saying I'm on my way" |
| **YouTube** | "Play that new Seetha Ramam song" — finds and plays it |
| **Deep Research** | "Research about ISRO's next mission" — multi-source verified report |
| **Meetings** | "Create an instant meeting" — Google Meet link saved to Notepad + clipboard |
| **Files** | "Search for my resume" |

**Lives in the background like a real assistant:** closing the window
minimizes to the system tray, and **Ctrl+Space** summons a Spotlight-style
command bar from anywhere in Windows.

Everything is **free and unlocked** — there are no tiers, no credits, no login.

---

## 🚀 Quick Start (2 minutes)

### 1. Install

```bash
git clone https://github.com/adharshramu12/Seetha_ai.git
cd Seetha_ai
```

Then just **double-click `StartSeetha.bat`** — it creates a virtual
environment and installs everything on first run.

<details>
<summary>Manual install (if you prefer)</summary>

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m seetha.main
```

Requires **Windows 10/11** and **Python 3.10+** from
[python.org](https://python.org) (tick "Add to PATH" during install).
</details>

### 2. Add your free AI key

On first launch Seetha opens the **⚙ Settings** window automatically:

1. Go to **[build.nvidia.com](https://build.nvidia.com)** → sign in (free)
   → open any chat model → click **Get API Key** → copy the `nvapi-...` key.
2. Paste it into **NVIDIA NIM API Key** in Settings → **Save & Test AI**.

That's it. Click **Activate Seetha** and start talking.

> Keys are stored only at `%LOCALAPPDATA%\Seetha\settings.json` on your PC
> and are sent only to the provider you got them from.

### 3. Optional keys (more powers)

All optional — add them in the same Settings window whenever you want:

| Key | What it unlocks | Get it free at |
|---|---|---|
| Groq | Backup AI brain if NVIDIA is down | [console.groq.com/keys](https://console.groq.com/keys) |
| Google Gemini | Better Deep Research reports | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| SerpAPI | Google-quality research search | [serpapi.com](https://serpapi.com) |
| NASA | Space data in research | [api.nasa.gov](https://api.nasa.gov) |
| OpenSky | Live flight tracking in research | [opensky-network.org](https://opensky-network.org) |
| Trefle | Plant/botany data in research | [trefle.io](https://trefle.io) |

---

## 🏗 Architecture

Clean separation between UI, orchestration, cognition, and automation —
each layer talks only to the next one:

| Layer | File | Responsibility |
|---|---|---|
| **UI** | [`seetha/main.py`](seetha/main.py) | Tkinter shell: splash, avatar, chat, research dashboard, tray wiring |
| **Command Bar** | [`seetha/command_bar.py`](seetha/command_bar.py) | Spotlight-style Ctrl+Space overlay |
| **Tray** | [`seetha/tray.py`](seetha/tray.py) | System-tray icon, notifications, background lifetime |
| **Settings** | [`seetha/settings_ui.py`](seetha/settings_ui.py), [`seetha/settings_store.py`](seetha/settings_store.py) | API-key management, local JSON store |
| **Service** | [`seetha/core.py`](seetha/core.py) | Background Listen→Process→Dispatch→Speak loop + reminder scheduler; talks to UI via a thread-safe queue |
| **Brain** | [`seetha/brain.py`](seetha/brain.py) | Intent detection: memory → addons → rules first (free, instant) → AI plans last |
| **Memory** | [`seetha/memory.py`](seetha/memory.py) | Persistent facts + reminders (`%LOCALAPPDATA%/Seetha/memory.json`) |
| **AI Client** | [`seetha/ai_client.py`](seetha/ai_client.py) | `chat_completion()` + `vision_completion()`: NVIDIA NIM → Groq |
| **Dispatcher** | [`seetha/dispatcher.py`](seetha/dispatcher.py) | Action handlers + agentic plan executor (act → screenshot → verify → retry) |
| **Actions** | [`seetha/actions.py`](seetha/actions.py) | Windows automation: PyAutoGUI, pywinauto, psutil |
| **Ears / Mouth** | [`seetha/ears.py`](seetha/ears.py), [`seetha/mouth.py`](seetha/mouth.py) | Speech-to-text (Google STT) / thread-safe text-to-speech worker |
| **Avatar** | [`seetha/avatar.py`](seetha/avatar.py) | Animated face with blinking + flicker-free lip-sync |
| **Research** | [`seetha/premium_research.py`](seetha/premium_research.py) | Multi-source evidence collection, fact verification, confidence scoring |

### Command processing order (cheap → expensive)

1. **YouTube intent** — "play/watch/listen" phrasing
2. **Research intent** — "research/investigate/deep dive" (typo-tolerant)
3. **WhatsApp intent** — AI extraction with a keyless regex fallback
4. **Rules engine** — instant local matches (volume, open, close, media...)
5. **General AI** — full conversation with your NVIDIA NIM key; the model
   can also return `{"action": ...}` JSON to trigger any automation

Seetha degrades gracefully: with **no key at all** the rules engine, app
control, media control and YouTube heuristics still work — only the free-form
conversation asks you to add a key.

---

## 🔒 Privacy

- **No accounts, no backend, no analytics.** The code you read is everything.
- API keys live in `%LOCALAPPDATA%\Seetha\settings.json` — on your disk only.
- Voice goes to Google's speech-recognition API (via the `SpeechRecognition`
  library); AI prompts go directly to the provider whose key **you** added.
  Nothing is routed through any Seetha server, because there isn't one.

---

## 🧰 Troubleshooting

| Problem | Fix |
|---|---|
| `PyAudio` fails to install | `pip install pipwin && pipwin install pyaudio` |
| Mic not detected | Check Windows Privacy Settings → Microphone access |
| "No AI key configured" | Settings → paste NVIDIA key → Save & Test AI |
| Voice replies but no actions | Run from a normal (non-admin) terminal — GUI automation can't reach elevated windows |
| WhatsApp automation misses | Keep WhatsApp Desktop installed and logged in |

Logs live at `%LOCALAPPDATA%\Seetha\logs\seetha.log` — attach the tail of
that file when opening an issue.

---

## 🧪 Testing

The offline release suite (no keys, no network, no GUI needed) runs in seconds:

```bash
python -m tests.test_suite
```

28 tests cover module imports, the rules engine's natural-language matching,
memory/reminder parsing and firing, keyless degradation, and — importantly —
that **every action the AI is allowed to emit has a dispatcher handler**.
Run it before every PR.

## 🤝 Contributing

PRs welcome! Good first issues:

- Load WhatsApp contacts from a user-editable `contacts.json`
- More rules in [`seetha/rules.py`](seetha/rules.py) (free = fast for everyone)
- Additional AI providers in [`seetha/ai_client.py`](seetha/ai_client.py) (Ollama for fully-local!)
- Linux/macOS support for [`seetha/actions.py`](seetha/actions.py)

Keep the layering: UI never touches automation directly; everything flows
through the Service → Brain → Dispatcher pipeline.

## 👨‍💻 Author

**Seetha AI** was created and is maintained by **Adharsh Kumar Bachu**.

If Seetha helps you, a ⭐ on this repo means a lot!

## 📄 License

[MIT](LICENSE) © Adharsh Kumar Bachu — do anything, just keep the notice.
