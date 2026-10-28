"""Conversation loop: listen -> understand -> act -> speak, on its own thread."""
from __future__ import annotations

import threading

from brain.llm import Brain
from brain.replies import t
from core.events import events
from shop.controller import StoreController


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
        if not self.active:
            return
        self._stop.set()
        self.speaker.stop()
        if farewell:
            self.speaker.say(t("bye", self.settings.language), block=False)

    def join(self, timeout: float = 5.0) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ---- one utterance (shared by voice loop and text mode) ----
    def handle_text(self, text: str) -> str:
        history = self.store.session.history if self.store.session else []
        parsed = self.brain.understand(text, history=history, state=self.store.state_text())
        events.add("intent", parsed.describe())
        return self.store.handle(parsed).text

    # ---- voice loop ----
    def _run(self) -> None:
        lang = self.settings.language
        greeting = self.store.begin_session()
        events.add("robot", greeting)
        self.speaker.say(greeting, block=True)
        silent_turns = 0
        try:
            while not self._stop.is_set() and self.store.conversation_active:
                text = self.listener.listen()
                if self._stop.is_set() or not self.store.conversation_active:
                    break
                if not text:
                    if self.store.awaiting_payment:
                        continue                      # customer is scanning the QR; keep waiting quietly
                    silent_turns += 1
                    if silent_turns >= self.settings.max_silent_turns and not self.store.session.cart:
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
            events.add("session", "conversation ended")
