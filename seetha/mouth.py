"""
SeethaMouth — text-to-speech.

pyttsx3 / Windows SAPI is NOT thread-safe: an engine created on one
thread silently fails when spoken from another (this is why reminders
used to fire without any sound). Fix: ONE dedicated speech worker
thread owns the engine; every speak() from any thread is queued to it.
speak() still blocks until the sentence finishes so avatar lip-sync
stays accurate.
"""

import queue
import threading

from seetha.logger import setup_logger

logger = setup_logger()


class SeethaMouth:
    def __init__(self):
        self._queue = queue.Queue()
        self._engine = None
        self._worker = threading.Thread(target=self._run, daemon=True, name="SeethaSpeech")
        self._worker.start()

    # ------------------------------------------------------------------
    # Worker thread — the ONLY place the engine is created and used
    # ------------------------------------------------------------------

    def _init_engine(self):
        import pyttsx3
        engine = pyttsx3.init()
        try:
            voices = engine.getProperty("voices")
            for voice in voices:
                if "female" in voice.name.lower() or "zira" in voice.name.lower():
                    engine.setProperty("voice", voice.id)
                    break
            engine.setProperty("rate", 170)
        except Exception as e:
            logger.warning(f"Voice selection failed (using default): {e}")
        return engine

    def _run(self):
        while True:
            text, done = self._queue.get()
            try:
                if self._engine is None:
                    self._engine = self._init_engine()
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                logger.error(f"TTS error, recreating engine: {e}")
                # One retry with a fresh engine — a stuck SAPI engine
                # otherwise stays silent forever.
                try:
                    self._engine = self._init_engine()
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e2:
                    logger.error(f"TTS retry failed: {e2}")
                    self._engine = None
            finally:
                done.set()

    # ------------------------------------------------------------------
    # Public API (callable from ANY thread)
    # ------------------------------------------------------------------

    def speak(self, text):
        """Speaks the text. Blocks until finished (for avatar sync)."""
        if not text:
            return
        logger.info(f"Seetha: {text}")
        done = threading.Event()
        self._queue.put((text, done))
        # Generous timeout so a hung engine can't freeze the caller forever
        done.wait(timeout=90)

    def stop(self):
        """Requests the current utterance to stop."""
        logger.info("Seetha: [Interrupted/Stopped]")
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception as e:
            logger.error(f"Error stopping speech: {e}")
