"""Opt-in daily fixed-source RSS, with private atomic snapshots and no delivery."""

from datetime import datetime, timezone
import fcntl
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .plans import load_schedule_registry
from .live_news import fetch_public_news
from .storage import LocalError

CONFIG = "daily-news.json"


def configure(store, project, enabled, zone, at):
    if enabled not in {"yes", "no"}:
        raise LocalError("enabled must be yes or no")
    value = {"enabled": enabled == "yes", "timezone": zone, "local_time": at}
    validate(value)
    registry_entry(project)
    with store.lock():
        store.read_json("settings.json")
        store.write_json(CONFIG, value)
    return value


def validate(value):
    if (not isinstance(value, dict) or set(value) != {"enabled", "timezone", "local_time"}
            or type(value["enabled"]) is not bool or not isinstance(value["timezone"], str)
            or not isinstance(value["local_time"], str)
            or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value["local_time"])):
        raise LocalError("invalid daily news configuration")
    try:
        return ZoneInfo(value["timezone"])
    except (ValueError, ZoneInfoNotFoundError):
        raise LocalError("daily news requires a valid IANA timezone") from None


def registry_entry(project):
    tasks = load_schedule_registry(project)["tasks"]
    if sum(task["id"] == "daily-news" and task["cadence"] == "daily" for task in tasks) != 1:
        raise LocalError("daily news is missing from the project schedule registry")


def configuration(store, project):
    registry_entry(project)
    try:
        value = store.read_json(CONFIG)
    except FileNotFoundError:
        return None
    validate(value)
    return value


def snapshot(store, project):
    config = configuration(store, project)
    state_dir = store.root / "state"
    store._directory(state_dir)
    latest = max((p.name for p in state_dir.glob("news-[0-9]*.json")
                  if re.fullmatch(r"news-[0-9]{4}-[0-9]{2}-[0-9]{2}\.json", p.name)), default=None)
    return {"config": config, "latest": store.read_json("state/" + latest) if latest else None}


def run(store, project, *, manual=False, clock=None, fetch=fetch_public_news):
    store.read_json("settings.json")
    lock = store._path("state/.daily-news-lock")
    with os.fdopen(os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "busy", "saved": False}
        config = configuration(store, project)
        if config is None or (not manual and not config["enabled"]):
            return {"status": "disabled", "saved": False}
        started = (clock or (lambda: datetime.now(timezone.utc)))()
        local = started.astimezone(validate(config))
        day = local.date().isoformat()
        if not manual and local.strftime("%H:%M") < config["local_time"]:
            return {"status": "not_due", "date": day, "saved": False}
        path = f"state/news-{day}.json"
        try:
            prior = store.read_json(path)
        except FileNotFoundError:
            prior = None
        if prior is not None and (prior["status"] != "failed" or not manual):
            return {"status": "reused", "date": day, "saved": False}
        result = fetch()
        successes = sum(source["status"] == "fetched" for source in result["sources"])
        status = ("failed" if not successes else "partial"
                  if successes < len(result["sources"]) else "complete")
        # The path and complete payload are committed together; no detached reference
        # or separate ledger transaction. An interrupted fetch can be retried safely.
        result = dict(result, persisted=True)
        store.write_json(path, {"date": day, "started_at": started.isoformat(),
                               "trigger": "manual" if manual else "schedule",
                               "status": status, "result": result})
        return {"status": status, "date": day, "saved": True, "articles": len(result["articles"])}
