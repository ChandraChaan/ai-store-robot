"""Text to speech.

Backends (all free):
  say   - macOS built-in voices, offline. Telugu = Geeta, Hindi = Lekha, Indian English = Rishi.
  edge  - Microsoft Edge neural voices via the edge-tts package (needs internet, no key).
  none  - just print.

Speech runs on a worker thread so the camera loop never blocks; callers can
wait for an utterance to finish or interrupt the robot mid-sentence.
"""
from __future__ import annotations

import asyncio
import os
import platform
import queue
import shutil
import subprocess
import tempfile
import threading
import time

SAY_VOICES = {"te": "Geeta", "hi": "Lekha", "en": "Rishi", "ta": "Vani", "kn": "Soumya"}
EDGE_VOICES = {"te": "te-IN-ShrutiNeural", "hi": "hi-IN-SwaraNeural", "en": "en-IN-NeerjaNeural"}


class Speaker:
    def __init__(self, backend: str = "say", language: str = "te", rate: int = 170):
        self.language = language
        self.rate = rate
        self.backend = self._pick_backend(backend)
        self._queue: queue.Queue = queue.Queue()
        self._process: subprocess.Popen | None = None
        self._speaking = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._stop_all = threading.Event()
        self.last_speech_start = 0.0
        self.last_speech_end = 0.0
        self.on_speak = None  # optional callback(text) for logging/dashboard
        self._thread = threading.Thread(target=self._worker, name="speaker", daemon=True)
        self._thread.start()
        self._available_voices = self._list_say_voices() if self.backend == "say" else set()

    # ---- backend selection ----
    def _pick_backend(self, backend: str) -> str:
        backend = (backend or "say").lower()
        if backend == "say" and (platform.system() != "Darwin" or not shutil.which("say")):
            if shutil.which("espeak-ng"):
                return "espeak"
            print("TTS: 'say' not available on this OS, falling back to print only")
            return "none"
        if backend == "edge":
            try:
                import edge_tts  # noqa: F401
            except ImportError:
                print("TTS: edge-tts not installed (pip install edge-tts), using 'say'")
                return self._pick_backend("say")
        return backend

    @staticmethod
    def _list_say_voices() -> set[str]:
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
            return {line.split()[0] for line in out.splitlines() if line.strip()}
        except Exception:
            return set()

    # ---- public API ----
    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set() or not self._queue.empty()

    def say(self, text: str, lang: str | None = None, block: bool = True) -> None:
        text = (text or "").strip()
        if not text:
            return
        done = threading.Event()
        self._idle.clear()
        self._queue.put((text, lang or self.language, done))
        if block:
            done.wait()

    def wait(self, timeout: float | None = None) -> None:
        self._idle.wait(timeout)

    def spoke_since(self, when: float) -> bool:
        return self._speaking.is_set() or self.last_speech_end >= when

    def stop(self) -> None:
        """Interrupt current speech and drop anything queued."""
        try:
            while True:
                _, _, done = self._queue.get_nowait()
                done.set()
        except queue.Empty:
            pass
        proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def shutdown(self) -> None:
        self._stop_all.set()
        self.stop()
        self._queue.put(None)

    # ---- worker ----
    def _worker(self) -> None:
        while not self._stop_all.is_set():
            item = self._queue.get()
            if item is None:
                break
            text, lang, done = item
            self._speaking.set()
            self.last_speech_start = time.time()
            try:
                if self.on_speak:
                    try:
                        self.on_speak(text)
                    except Exception:
                        pass
                self._speak_now(text, lang)
            except Exception as exc:
                print("Speech error:", exc)
            finally:
                self.last_speech_end = time.time()
                self._speaking.clear()
                done.set()
                if self._queue.empty():
                    self._idle.set()

    def _speak_now(self, text: str, lang: str) -> None:
        if self.backend == "say":
            voice = SAY_VOICES.get(lang)
            cmd = ["say", "-r", str(self.rate)]
            if voice and (not self._available_voices or voice in self._available_voices):
                cmd += ["-v", voice]
            self._run(cmd + [text])
        elif self.backend == "espeak":
            self._run(["espeak-ng", "-v", lang, "-s", str(self.rate), text])
        elif self.backend == "edge":
            self._speak_edge(text, lang)
        else:
            pass  # 'none': text is already printed by the event log

    def _run(self, cmd: list[str]) -> None:
        self._process = subprocess.Popen(cmd)
        try:
            self._process.wait()
        finally:
            self._process = None

    def _speak_edge(self, text: str, lang: str) -> None:
        import edge_tts

        voice = EDGE_VOICES.get(lang, EDGE_VOICES["en"])
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            path = tmp.name
        try:
            asyncio.run(edge_tts.Communicate(text, voice).save(path))
            player = "afplay" if shutil.which("afplay") else ("mpg123" if shutil.which("mpg123") else None)
            if player:
                self._run([player, path])
        except Exception as exc:
            print("edge-tts failed, falling back to say:", exc)
            self.backend = self._pick_backend("say")
            self._speak_now(text, lang)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


_default_speaker: Speaker | None = None


def speak(text: str, lang: str = "te") -> None:
    """Simple blocking helper kept for backwards compatibility."""
    global _default_speaker
    if _default_speaker is None:
        _default_speaker = Speaker(language=lang)
    _default_speaker.say(text, lang=lang, block=True)
