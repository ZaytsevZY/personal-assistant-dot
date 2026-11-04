"""Foreground synthetic planning and durable reconciliation; never a timer."""

from datetime import datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .runtime import TaskRunner, WORKFLOWS
from .storage import LocalError


UTC = timezone.utc
LEDGER = "state/plans.json"


def load_schedule_registry(project):
    value = json.loads((Path(project) / "config/schedules.example.json").read_text())
    if (not isinstance(value, dict) or value.get("registry_mode") != "single_project_registry"
            or value.get("scheduler_implemented") is not False
            or not isinstance(value.get("tasks"), list)
            or any(value.get(key) is not None for key in ("backend", "timezone", "output_channel"))):
        raise LocalError("central schedule registry is unsupported or attempts to enable delivery")
    tasks = value["tasks"]
    if len(tasks) != 2 or any(not isinstance(task, dict) or not isinstance(task.get("id"), str) for task in tasks):
        raise LocalError("central schedule registry must contain the two disabled task definitions")
    expected = {"daily-news": "daily", "weekly-open-source-review": "weekly"}
    if ({task.get("id") for task in tasks} != set(expected)
            or any(task.get("enabled") is not False or task.get("cadence") != expected[task["id"]]
                   or task.get("local_time") is not None or task.get("weekday") is not None for task in tasks)):
        raise LocalError("this MVP only previews the disabled, unconfigured central schedules")
    if value.get("manual_plans_file") != "config/plans.example.json":
        raise LocalError("manual plan registry reference must use the project configuration")
    return value


def timestamp(value):
    try:
        if not isinstance(value, str) or len(value) > 40 or "T" not in value:
            raise ValueError()
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        result = result.astimezone(UTC)
        if not 1970 <= result.year <= 9998:
            raise ValueError()
        return result
    except (ValueError, OverflowError):
        raise LocalError("timestamps require an ISO date/time with explicit UTC offset, years 1970-9998") from None


def validate_plans(value):
    keys = {"schema_version", "mode", "lookback_days", "max_records", "dst_gap_policy", "dst_fold_policy", "plans"}
    if (not isinstance(value, dict) or set(value) != keys or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or value["mode"] != "manual_only"
            or value["dst_gap_policy"] != "skip" or value["dst_fold_policy"] != "earlier"
            or type(value["lookback_days"]) is not int or not 1 <= value["lookback_days"] <= 31
            or type(value["max_records"]) is not int or not 1 <= value["max_records"] <= 500
            or not isinstance(value["plans"], list) or not 1 <= len(value["plans"]) <= 8):
        raise LocalError("manual plan configuration is invalid or attempts unsupported execution")
    seen = set()
    fields = {"id", "workflow_id", "timezone", "cadence", "local_time", "weekday", "missed_policy", "max_lateness_minutes"}
    for plan in value["plans"]:
        if (not isinstance(plan, dict) or set(plan) != fields
                or not isinstance(plan["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", plan["id"])
                or plan["id"] in seen or plan["workflow_id"] not in WORKFLOWS
                or plan["cadence"] not in ("daily", "weekly")
                or not isinstance(plan["local_time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", plan["local_time"])
                or (plan["cadence"] == "daily" and plan["weekday"] is not None)
                or (plan["cadence"] == "weekly" and (type(plan["weekday"]) is not int or not 0 <= plan["weekday"] <= 6))
                or plan["missed_policy"] not in ("coalesce_latest", "skip_expired")
                or type(plan["max_lateness_minutes"]) is not int or not 0 <= plan["max_lateness_minutes"] <= 10080
                or not isinstance(plan["timezone"], str) or len(plan["timezone"]) > 64):
            raise LocalError("plan fields must describe a supported synthetic daily or weekly workflow")
        try:
            ZoneInfo(plan["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise LocalError("plan timezone is unavailable in the installed IANA timezone database") from None
        seen.add(plan["id"])
    return value


def load_plans(project, store=None):
    registry = load_schedule_registry(project)
    if store is not None and store._path("plans.json").exists():
        return validate_plans(store.read_json("plans.json", limit=64_000))
    return validate_plans(json.loads((Path(project) / registry["manual_plans_file"]).read_text()))


def digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def occurrence(plan, day, revision):
    wall = datetime.combine(day, time.fromisoformat(plan["local_time"]))
    zone = ZoneInfo(plan["timezone"])
    candidates = set()
    for fold in (0, 1):
        candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == wall:
            candidates.add(candidate)
    if candidates:
        anchor = min(candidates)
        kind = "ambiguous_earlier" if len(candidates) == 2 else "normal"
    else:
        # An anchor selects the audit window; it is NOT an actual scheduled instant.
        anchor = wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
        kind = "nonexistent"
    local = wall.isoformat(timespec="minutes")
    identifier = hashlib.sha256((revision + "|" + plan["id"] + "|" + local + "|" + kind).encode()).hexdigest()[:32]
    return {"id": identifier, "plan_id": plan["id"], "workflow_id": plan["workflow_id"],
            "timezone": plan["timezone"], "local_time": local, "anchor": anchor.isoformat(),
            "due_at": anchor.isoformat() if candidates else None, "kind": kind,
            "status": "ready" if candidates else "skipped", "reason": "due" if candidates else "dst_gap",
            "task_id": None}


def preview(config, since, at):
    config = validate_plans(config)
    start, end = timestamp(since), timestamp(at)
    if end < start:
        raise LocalError("evaluation time cannot precede the window start")
    effective = max(start, end - timedelta(days=config["lookback_days"]))
    revision = digest(config)
    records = []
    for plan in config["plans"]:
        zone = ZoneInfo(plan["timezone"])
        day = effective.astimezone(zone).date() - timedelta(days=1)
        last = end.astimezone(zone).date() + timedelta(days=1)
        selected = []
        while day <= last:
            if plan["cadence"] == "daily" or day.weekday() == plan["weekday"]:
                item = occurrence(plan, day, revision)
                if effective < datetime.fromisoformat(item["anchor"]) <= end:
                    selected.append(item)
            day += timedelta(days=1)
        valid = [item for item in selected if item["due_at"] is not None]
        latest = max((item["due_at"] for item in valid), default=None)
        for item in valid:
            if plan["missed_policy"] == "coalesce_latest" and item["due_at"] != latest:
                item.update(status="skipped", reason="coalesced")
            elif plan["missed_policy"] == "skip_expired" and end - timestamp(item["due_at"]) > timedelta(minutes=plan["max_lateness_minutes"]):
                item.update(status="skipped", reason="expired")
        records.extend(selected)
    records.sort(key=lambda item: (item["anchor"], item["plan_id"]))
    return {"mode": "manual_only", "config_digest": revision, "records": records,
            "window": {"requested_since": start.isoformat(), "effective_since": effective.isoformat(),
                       "at": end.isoformat(), "older_history_skipped": effective > start},
            "executed": False}


class PlanEngine:
    """All private mutations share the core writer transaction, never a daemon."""

    def __init__(self, store, project, runner=None):
        self.store, self.project = store, project
        self.runner = runner if runner is not None else TaskRunner(store)

    def _load_locked(self, config):
        revision = digest(config)
        if not self.store._path(LEDGER).exists():
            return {"schema_version": 1, "config_digest": revision, "watermark": None, "records": [], "last_window": None}
        value = self.store.read_json(LEDGER)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "config_digest", "watermark", "records", "last_window"}
                or value["schema_version"] != 1 or value["config_digest"] != revision
                or not isinstance(value["records"], list) or len(value["records"]) > config["max_records"]):
            raise LocalError("plan ledger is invalid or configuration changed; explicit migration is required")
        if value["watermark"] is not None:
            timestamp(value["watermark"])
        plans = {plan["id"]: plan for plan in config["plans"]}
        seen = set()
        for item in value["records"]:
            if (not isinstance(item, dict) or not isinstance(item.get("plan_id"), str)
                    or item["plan_id"] not in plans or not isinstance(item.get("local_time"), str)):
                raise LocalError("plan ledger record is invalid")
            try:
                day = datetime.fromisoformat(item["local_time"]).date()
                plan = plans[item["plan_id"]]
                expected = occurrence(plan, day, revision)
            except (ValueError, OverflowError):
                raise LocalError("plan ledger calendar record is invalid") from None
            fixed = ("id", "plan_id", "workflow_id", "timezone", "local_time", "anchor", "due_at", "kind")
            if (set(item) != set(expected) or any(item[key] != expected[key] for key in fixed)
                    or (plan["cadence"] == "weekly" and day.weekday() != plan["weekday"])
                    or item["id"] in seen or item["status"] not in ("ready", "skipped", "running", "succeeded", "failed", "uncertain")
                    or not isinstance(item["reason"], str)
                    or (item["task_id"] is not None and (not isinstance(item["task_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", item["task_id"])))
                    or (item["kind"] == "nonexistent" and item["status"] != "skipped")):
                raise LocalError("plan ledger record integrity check failed")
            seen.add(item["id"])
        return value

    def _sync_locked(self, ledger):
        tasks = self.runner._tasks()
        self.runner._recover_interrupted(tasks)
        indexed = {(task["workflow_id"], task["idempotency_key"]): task for task in tasks}
        for item in ledger["records"]:
            if item["status"] in ("skipped", "succeeded", "failed"):
                continue
            task = indexed.get((item["workflow_id"], "plan_" + item["id"]))
            if task is not None:
                item.update(status=task["state"], task_id=task["task_id"], reason="core_task_state")
            elif item["status"] == "running":
                item.update(status="uncertain", reason="interrupted_before_core_record")

    def _reconcile_locked(self, config, at, since=None):
        ledger = self._load_locked(config)
        end = timestamp(at)
        previous = ledger["watermark"]
        if previous is None:
            if since is None:
                raise LocalError("first reconciliation requires an explicit --since boundary")
            start = timestamp(since)
        else:
            start = timestamp(previous)
            if since is not None and timestamp(since) != start:
                raise LocalError("--since must match the saved watermark; history is never silently reset")
        result = preview(config, start.isoformat(), end.isoformat())
        self._sync_locked(ledger)
        existing = {item["id"] for item in ledger["records"]}
        ledger["records"].extend(item for item in result["records"] if item["id"] not in existing)
        if len(ledger["records"]) > config["max_records"]:
            raise LocalError("plan ledger capacity reached; explicit archival or migration is required")
        for plan in config["plans"]:
            group = [item for item in ledger["records"] if item["plan_id"] == plan["id"] and item["status"] == "ready"]
            latest = max((item["due_at"] for item in group), default=None)
            for item in group:
                if plan["missed_policy"] == "coalesce_latest" and item["due_at"] != latest:
                    item.update(status="skipped", reason="superseded")
                elif plan["missed_policy"] == "skip_expired" and end - timestamp(item["due_at"]) > timedelta(minutes=plan["max_lateness_minutes"]):
                    item.update(status="skipped", reason="expired")
        ledger.update(watermark=end.isoformat(), last_window=result["window"])
        self.store.write_json(LEDGER, ledger)
        self.store.audit("plans_reconciled", added=len(existing.symmetric_difference({item["id"] for item in ledger["records"]})), older_history_skipped=result["window"]["older_history_skipped"])
        return ledger

    def reconcile(self, at, since=None):
        with self.store.lock():
            self.runner.settings()
            config = load_plans(self.project, self.store)
            return {"status": "reconciled", "ledger": self._reconcile_locked(config, at, since), "executed": False}

    def state(self):
        with self.store.lock():
            self.runner.settings()
            config = load_plans(self.project, self.store)
            ledger = self._load_locked(config)
            if ledger["watermark"] is not None:
                self._sync_locked(ledger)
                self.store.write_json(LEDGER, ledger)
            return {"status": "available" if ledger["watermark"] else "not_initialized", "ledger": ledger}

    def snapshot(self):
        with self.store.lock():
            self.runner.settings()
            config = load_plans(self.project, self.store)
            return {"config": config, "ledger": self._load_locked(config)}

    def execute(self, identifier, at):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise LocalError("invalid occurrence ID")
        with self.store.lock():
            settings = self.runner.settings()
            config = load_plans(self.project, self.store)
            before = self._load_locked(config)
            if not any(item["id"] == identifier for item in before["records"]):
                raise LocalError("occurrence was not found; reconcile a window first")
            ledger = self._reconcile_locked(config, at)
            item = next(item for item in ledger["records"] if item["id"] == identifier)
            if item["status"] != "ready":
                return {"reused": True, "occurrence": item, "executed": False}
            if settings["paused"]:
                raise LocalError("manual runner is paused; use /resume to allow synthetic runs")
            item.update(status="running", reason="manual_claim")
            self.store.write_json(LEDGER, ledger)
            result = self.runner._run_locked(item["workflow_id"], "plan_" + identifier)
            task = result["task"]
            item.update(status=task["state"], task_id=task["task_id"], reason="core_task_state")
            self.store.write_json(LEDGER, ledger)
            self.store.audit("plan_manual_run_finished", occurrence_id=identifier, state=item["status"])
            return {"reused": result["reused"], "occurrence": item, "task": task, "executed": not result["reused"]}
