"""Conversation loop: listen -> understand -> act -> speak, on its own thread."""
from __future__ import annotations

import threading

from ai.brain import Brain
from ai.replies import t
from store.store_controller import StoreController
from utils.events import events


class ConversationEngine:
    def __init__(self, store: StoreController, brain: Brain, speaker, listener, settings):
        self.store = store
        self.brain = brain
        self.speaker = speaker
        self.listener = listener
        self.settings = settings
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- lifecycle ----
    def start(self) -> bool:
        if self.active:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="conversation", daemon=True)
        self._thread.start()
        return True

    def stop(self, farewell: bool = True) -> None:
        """Called when the camera sees the customer leave."""
        if not self.active:
            return
        self._stop.set()
        self.speaker.stop()
        if farewell:
            self.speaker.say(t("bye", self.settings.language), block=False)

    def join(self, timeout: float = 5.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ---- text mode (no mic / camera) ----
    def handle_text(self, text: str) -> str:
        parsed = self.brain.understand(text, history=self.store.session.history if self.store.session else [], state=self.store.state_text())
        events.add("intent", parsed.describe())
        reply = self.store.handle(parsed)
        return reply.text

    # ---- voice loop ----
    def _run(self) -> None:
        lang = self.settings.language
        greeting = self.store.begin_session()
        events.add("robot", greeting)
        self.speaker.say(greeting, block=True)
        silent_turns = 0
        try:
            while not self._stop.is_set() and self.store.conversation_active:
                events.add("listen", "listening...")
                text = self.listener.listen()
                if self._stop.is_set():
                    break
                if not text:
                    silent_turns += 1
                    if silent_turns >= self.settings.max_silent_turns:
                        msg = t("idle_end", lang)
                        events.add("robot", msg)
                        self.speaker.say(msg, block=True)
                        break
                    continue
                silent_turns = 0
                events.add("customer", text)
                parsed = self.brain.understand(text, history=self.store.session.history, state=self.store.state_text())
                events.add("intent", parsed.describe())
                reply = self.store.handle(parsed)
                events.add("robot", reply.text)
                self.speaker.say(reply.text, block=True)
                if reply.end:
                    break
        except Exception as exc:  # keep the camera loop alive whatever happens here
            events.add("error", f"conversation crashed: {exc!r}")
        finally:
            self.store.end_session()
            events.add("session", "conversation ended")


def start_conversation():
    """Backwards compatible entry point used by the first prototype."""
    from store.inventory import Inventory
    from store.ledger import Ledger
    from utils.config import load_settings
    from voice.speech_to_text import Listener
    from voice.text_to_speech import Speaker

    settings = load_settings()
    inventory = Inventory(settings.products_file)
    ledger = Ledger(settings.database_file)
    speaker = Speaker(settings.tts_backend, settings.language, settings.tts_rate)
    listener = Listener(settings.stt_backend, settings.stt_model, settings.stt_language, speaker=speaker)
    store = StoreController(inventory, ledger, settings=settings, on_event=events.add)
    engine = ConversationEngine(store, Brain(inventory, settings), speaker, listener, settings)
    engine._run()
