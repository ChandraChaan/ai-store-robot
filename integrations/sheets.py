"""Google Sheets sync through a free Apps Script web app (no Google Cloud project).

Setup (one time, 5 minutes):
  1. Create a Google Sheet.  Extensions -> Apps Script.  Paste integrations/apps_script.gs.
  2. Set TOKEN in the script to a password of your choice.  Deploy -> New deployment ->
     Web app, execute as "Me", access "Anyone".  Copy the web app URL.
  3. Put the URL in config.json as "sheets_webhook_url" and the password as "sheets_token".

Rows are sent in the background. If the internet is down they wait in
data/outbox.jsonl and are sent later, so nothing is lost.
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


class SheetsSync:
    def __init__(self, url: str, token: str = "", outbox_file: str | Path = "data/outbox.jsonl", on_event=None, poster=None):
        self.url = (url or "").strip()
        self.token = token or ""
        self.outbox = Path(outbox_file)
        self.on_event = on_event or (lambda kind, text: None)
        self._post = poster or self._http_post
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self.sent = 0
        self.failed = 0
        self.last_error = ""
        self.last_sent_at: float | None = None
        self._thread = None
        if self.enabled:
            self._thread = threading.Thread(target=self._worker, name="sheets", daemon=True)
            self._thread.start()

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    # ---- public ----
    def send(self, row_type: str, data: dict) -> None:
        row = {"type": row_type, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "token": self.token, **data}
        if not self.enabled:
            return
        self._queue.put(row)

    def pending(self) -> int:
        n = self._queue.qsize()
        if self.outbox.exists():
            try:
                n += sum(1 for line in self.outbox.read_text(encoding="utf-8").splitlines() if line.strip())
            except OSError:
                pass
        return n

    def status(self) -> dict:
        return {"enabled": self.enabled, "sent": self.sent, "failed": self.failed, "pending": self.pending(),
                "last_error": self.last_error, "last_sent_at": self.last_sent_at}

    def stop(self) -> None:
        self._stop.set()

    # ---- worker ----
    def _http_post(self, row: dict) -> bool:
        body = json.dumps(row, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:  # Apps Script answers after a redirect
            text = resp.read().decode("utf-8", "ignore")
        return '"ok"' in text or "ok" in text.lower()

    def _try_send(self, row: dict) -> bool:
        try:
            ok = self._post(row)
            if ok:
                self.sent += 1
                self.last_sent_at = time.time()
                self.last_error = ""
            return ok
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.last_error = str(exc)[:200]
            return False

    def _spool(self, row: dict) -> None:
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _flush_outbox(self) -> None:
        if not self.outbox.exists():
            return
        try:
            lines = [ln for ln in self.outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            return
        remaining = []
        for i, line in enumerate(lines):
            if remaining:  # a send failed; keep the rest for later
                remaining.append(line)
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not self._try_send(row):
                remaining.append(line)
        self.outbox.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
        if not remaining:
            try:
                self.outbox.unlink()
            except OSError:
                pass

    def _worker(self) -> None:
        last_flush = 0.0
        while not self._stop.is_set():
            try:
                row = self._queue.get(timeout=1.0)
            except queue.Empty:
                row = None
            if row is not None:
                if not self._try_send(row):
                    self.failed += 1
                    self._spool(row)
                    self.on_event("sheets", f"offline, saved row for later ({self.last_error})")
            if time.monotonic() - last_flush > 30:
                last_flush = time.monotonic()
                self._flush_outbox()
