import time

from integrations.sheets import SheetsSync


def test_disabled_without_url(tmp_path):
    s = SheetsSync("", outbox_file=tmp_path / "out.jsonl")
    s.send("bills", {"a": 1})
    assert not s.enabled and s.pending() == 0


def test_rows_spool_when_offline_and_flush_later(tmp_path):
    online = {"ok": False}
    sent = []

    def poster(row):
        if not online["ok"]:
            raise OSError("no internet")
        sent.append(row)
        return True

    s = SheetsSync("https://example.invalid/exec", token="t", outbox_file=tmp_path / "out.jsonl", poster=poster)
    s.send("bills", {"bill": 1, "total": 50})
    deadline = time.time() + 5
    while s.failed == 0 and time.time() < deadline:
        time.sleep(0.05)
    assert s.failed == 1 and (tmp_path / "out.jsonl").exists() and s.pending() == 1
    online["ok"] = True
    s._flush_outbox()
    assert sent and sent[0]["bill"] == 1 and sent[0]["token"] == "t" and s.pending() == 0
    s.stop()
