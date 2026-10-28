"""Speech to text with voice-activity based recording.

Instead of a fixed 5 second recording, we listen until the customer stops
talking (silence after speech) or a maximum duration is reached.

Backends (all free/offline):
  faster-whisper  - CTranslate2 Whisper, fastest on CPU (default when installed)
  whisper         - original openai-whisper (needs torch)
  typed           - keyboard input, for development without a microphone
  none            - always returns "" (camera-only demo)
"""
from __future__ import annotations

import sys
import time

import numpy as np

SAMPLE_RATE = 16000


class Listener:
    def __init__(
        self,
        backend: str = "auto",
        model_size: str = "small",
        language: str = "te",
        max_seconds: float = 8.0,
        silence_seconds: float = 1.2,
        start_timeout: float = 5.0,
        speaker=None,
    ):
        self.language = None if language in ("", "auto", None) else language
        self.max_seconds = max_seconds
        self.silence_seconds = silence_seconds
        self.start_timeout = start_timeout
        self.speaker = speaker
        self.model_size = model_size
        self._model = None
        self.backend = self._pick_backend(backend)
        self.last_audio_seconds = 0.0
        self.last_transcribe_seconds = 0.0

    # ---- backend selection ----
    def _pick_backend(self, backend: str) -> str:
        backend = (backend or "auto").lower()
        if backend in ("typed", "none"):
            return backend
        candidates = ["faster-whisper", "whisper"] if backend == "auto" else [backend]
        for cand in candidates:
            try:
                if cand == "faster-whisper":
                    import faster_whisper  # noqa: F401
                elif cand == "whisper":
                    import whisper  # noqa: F401
                else:
                    continue
                import sounddevice  # noqa: F401
                return cand
            except ImportError:
                continue
            except OSError as exc:  # portaudio missing
                print("Audio input not available:", exc)
                break
        print("STT: no speech backend available, falling back to typed input")
        return "typed"

    def _load_model(self):
        if self._model is not None:
            return self._model
        t0 = time.time()
        if self.backend == "faster-whisper":
            from faster_whisper import WhisperModel

            print(f"Loading faster-whisper '{self.model_size}' (first run downloads the model)...")
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        elif self.backend == "whisper":
            import whisper

            print(f"Loading whisper '{self.model_size}'...")
            self._model = whisper.load_model(self.model_size)
        print(f"Speech model ready in {time.time() - t0:.1f}s")
        return self._model

    def warm_up(self) -> None:
        if self.backend in ("faster-whisper", "whisper"):
            self._load_model()

    # ---- recording ----
    def record(self) -> np.ndarray | None:
        """Record until silence. Returns float32 mono 16 kHz audio, or None if nobody spoke."""
        import sounddevice as sd

        block = int(SAMPLE_RATE * 0.03)  # 30 ms
        chunks: list[np.ndarray] = []
        noise_levels: list[float] = []
        speech_started = False
        silence_run = 0.0
        total = 0.0
        threshold = 0.015

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=block) as stream:
            start = time.monotonic()
            while True:
                data, _ = stream.read(block)
                mono = data[:, 0]
                rms = float(np.sqrt(np.mean(mono ** 2)) + 1e-9)
                elapsed = time.monotonic() - start

                if not speech_started:
                    if elapsed < 0.4:          # calibrate on ambient noise
                        noise_levels.append(rms)
                        if elapsed >= 0.39 and noise_levels:
                            threshold = max(0.012, float(np.median(noise_levels)) * 3.5)
                        continue
                    chunks.append(mono.copy())
                    if len(chunks) > 10:        # keep ~300 ms of pre-roll
                        chunks.pop(0)
                    if rms > threshold:
                        speech_started = True
                    elif elapsed > self.start_timeout:
                        return None
                    continue

                chunks.append(mono.copy())
                total += 0.03
                silence_run = silence_run + 0.03 if rms < threshold else 0.0
                if silence_run >= self.silence_seconds or total >= self.max_seconds:
                    break

        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        self.last_audio_seconds = len(audio) / SAMPLE_RATE
        if self.last_audio_seconds < 0.4:
            return None
        return audio

    # ---- transcription ----
    def transcribe(self, audio: np.ndarray) -> str:
        model = self._load_model()
        t0 = time.time()
        text = ""
        if self.backend == "faster-whisper":
            segments, _info = model.transcribe(
                audio, language=self.language, beam_size=2, vad_filter=True, condition_on_previous_text=False
            )
            text = " ".join(seg.text.strip() for seg in segments)
        elif self.backend == "whisper":
            result = model.transcribe(audio, language=self.language, fp16=False)
            text = result.get("text", "")
        self.last_transcribe_seconds = time.time() - t0
        return text.strip()

    def listen(self) -> str:
        """Wait for the robot to finish talking, then listen and return the transcript ("" if nothing)."""
        if self.speaker is not None:
            self.speaker.wait()
        if self.backend == "none":
            time.sleep(1.0)
            return ""
        if self.backend == "typed":
            try:
                sys.stdout.write("You: ")
                sys.stdout.flush()
                return sys.stdin.readline().strip()
            except (EOFError, KeyboardInterrupt):
                return ""
        started = time.time()
        audio = self.record()
        if audio is None:
            return ""
        if self.speaker is not None and self.speaker.spoke_since(started):
            return ""   # the robot talked while we were recording (e.g. counter bill); don't transcribe ourselves
        text = self.transcribe(audio)
        if text:
            print(f"  (heard {self.last_audio_seconds:.1f}s, transcribed in {self.last_transcribe_seconds:.1f}s)")
        return text


_default_listener: Listener | None = None


def listen() -> str:
    """Backwards compatible helper."""
    global _default_listener
    if _default_listener is None:
        _default_listener = Listener()
    return _default_listener.listen()
