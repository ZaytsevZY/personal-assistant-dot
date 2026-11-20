"""Offline acceptance for opt-in daily RSS and durable duplicate protection."""

from datetime import datetime, timezone
import fcntl
from pathlib import Path
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot import daily_news
from assistant_dot.storage import LocalError, PrivateStore


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "private"
        store = PrivateStore(root, PROJECT)
        store.initialize({})
        calls = []

        def clock(hour, day=10):
            return lambda: datetime(2026, 1, day, hour, tzinfo=timezone.utc)

        def fetch(*states):
            def fake():
                calls.append(states)
                return {"sources": [{"status": state} for state in states],
                        "articles": [{"title": "synthetic"}] if "fetched" in states else [],
                        "persisted": False, "delivery_enabled": False}
            return fake

        assert daily_news.run(store, PROJECT, fetch=fetch())["status"] == "disabled"
        try:
            daily_news.configure(store, PROJECT, "yes", "Not/AZone", "09:00")
        except LocalError:
            pass
        else:
            raise AssertionError("accepted invalid timezone")
        daily_news.configure(store, PROJECT, "yes", "Asia/Singapore", "09:00")
        assert daily_news.run(store, PROJECT, clock=clock(0), fetch=fetch())["status"] == "not_due"
        with (root / "state/.daily-news-lock").open("rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            assert daily_news.run(store, PROJECT, clock=clock(1), fetch=fetch())["status"] == "busy"
        assert not calls

        first = daily_news.run(store, PROJECT, clock=clock(1), fetch=fetch("fetched", "unavailable"))
        assert first == {"status": "partial", "date": "2026-01-10", "saved": True, "articles": 1}
        reopened = PrivateStore(root, PROJECT)
        saved = daily_news.snapshot(reopened, PROJECT)["latest"]
        assert saved["trigger"] == "schedule" and saved["result"]["persisted"] is True
        assert saved["result"]["delivery_enabled"] is False
        before = (root / "state/news-2026-01-10.json").read_bytes()
        assert daily_news.run(reopened, PROJECT, clock=clock(2), fetch=fetch())["status"] == "reused"
        assert before == (root / "state/news-2026-01-10.json").read_bytes() and len(calls) == 1

        assert daily_news.run(store, PROJECT, clock=clock(1, 11), fetch=fetch("unavailable"))["status"] == "failed"
        assert daily_news.run(store, PROJECT, clock=clock(2, 11), fetch=fetch())["status"] == "reused"
        assert daily_news.run(store, PROJECT, clock=clock(2, 11), manual=True, fetch=fetch("fetched"))["status"] == "complete"
        assert daily_news.snapshot(reopened, PROJECT)["latest"]["trigger"] == "manual"
        assert len(list((root / "state").glob("news-*.json"))) == 2
        assert (root / "state/news-2026-01-11.json").stat().st_mode & 0o077 == 0

        daily_news.configure(store, PROJECT, "no", "Asia/Singapore", "09:00")
        assert daily_news.run(store, PROJECT, clock=clock(1, 12), fetch=fetch())["status"] == "disabled"
        assert len(calls) == 3
        print("OK: daily due, busy, partial, restart, duplicate, failure/retry, rollover, private permissions, disabled")


if __name__ == "__main__":
    main()
