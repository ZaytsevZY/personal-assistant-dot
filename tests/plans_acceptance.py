"""Synthetic acceptance tests for foreground plans; no timers or accounts."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.plans import LEDGER, PlanEngine, load_plans, preview, validate_plans
from assistant_dot.runtime import SETTINGS, SyntheticAdapter, TaskRunner
from assistant_dot.storage import LocalError, PrivateStore


def rejected(action):
    try:
        action()
    except LocalError:
        return
    raise AssertionError("expected safe rejection")


def fixture(parent, name, config=None):
    store = PrivateStore(parent / name, PROJECT)
    store.initialize(dict(SETTINGS))
    if config is not None:
        store.write_json("plans.json", config)
    return store, PlanEngine(store, PROJECT)


def cli(root, *args, expected=0):
    result = subprocess.run([sys.executable, "-B", "-m", "assistant_dot", "--private-root", str(root), *args],
                            cwd=PROJECT, capture_output=True, text=True, timeout=10)
    assert result.returncode == expected, (result.stdout, result.stderr)
    assert not result.stderr
    return json.loads(result.stdout)


def test_calendar_and_validation(parent):
    config = load_plans(PROJECT)
    result = preview(config, "2026-11-01T00:00:00Z", "2026-11-04T12:00:00Z")
    daily = [item for item in result["records"] if item["plan_id"] == "demo-daily"]
    assert len(daily) == 4 and sum(item["status"] == "ready" for item in daily) == 1
    assert next(item for item in result["records"] if item["plan_id"] == "demo-weekly")["reason"] == "expired"
    assert preview(config, "2026-11-04T08:00:00Z", "2026-11-04T08:00:00Z")["records"] == []
    assert len(preview(config, "2026-11-04T07:59:59Z", "2026-11-04T08:00:00Z")["records"]) == 1
    assert preview(config, "2026-11-04T15:59:59+08:00", "2026-11-04T16:00:00+08:00")["records"][0]["due_at"] == "2026-11-04T08:00:00+00:00"
    rejected(lambda: preview(config, "2026-11-04T00:00:00", "2026-11-05T00:00:00Z"))
    rejected(lambda: preview(config, "2026-11-05T00:00:00Z", "2026-11-04T00:00:00Z"))
    for mutate in (lambda v: v.update(mode="automatic"), lambda v: v.update(output_channel="synthetic"),
                   lambda v: v["plans"][0].update(workflow_id="real-news"),
                   lambda v: v["plans"][0].update(timezone="Missing/Zone"),
                   lambda v: v["plans"][0].update(local_time="24:00")):
        changed = json.loads(json.dumps(config))
        mutate(changed)
        rejected(lambda: validate_plans(changed))


def test_timezone_gaps_folds_and_offsets(parent):
    config = load_plans(PROJECT)
    config["plans"] = [dict(config["plans"][0], timezone="America/New_York", local_time="02:30")]
    gap = preview(config, "2026-03-08T00:00:00Z", "2026-03-09T00:00:00Z")["records"]
    assert len(gap) == 1 and gap[0]["reason"] == "dst_gap" and gap[0]["due_at"] is None
    config["plans"][0]["local_time"] = "01:30"
    fold = preview(config, "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z")["records"]
    assert len(fold) == 1 and fold[0]["kind"] == "ambiguous_earlier"
    assert fold[0]["due_at"] == "2026-11-01T05:30:00+00:00"
    assert preview(config, "2026-11-01T05:40:00Z", "2026-11-01T07:00:00Z")["records"] == []
    config["plans"][0].update(timezone="Asia/Kathmandu", local_time="08:00")
    fractional = preview(config, "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z")["records"]
    assert fractional[0]["due_at"] == "2026-11-01T02:15:00+00:00"
    config["plans"][0].update(timezone="UTC", local_time="08:00")
    assert preview(config, "1970-01-01T00:00:00Z", "1970-01-02T00:00:00Z")["records"]


def test_persistence_replay_and_missed_policy(parent):
    store, engine = fixture(parent, "durable")
    rejected(lambda: engine.reconcile("2026-11-01T12:00:00Z"))
    assert not (store.root / LEDGER).exists()
    first = engine.reconcile("2026-11-01T12:00:00Z", "2026-11-01T00:00:00Z")["ledger"]
    old = first["records"][0]["id"]
    assert TaskRunner(store).list_tasks() == []
    again = PlanEngine(store, PROJECT).reconcile("2026-11-01T12:00:00Z")["ledger"]
    assert len(again["records"]) == len(first["records"])
    second = engine.reconcile("2026-11-04T12:00:00Z")["ledger"]
    assert next(item for item in second["records"] if item["id"] == old)["reason"] == "superseded"
    latest = next(item for item in second["records"] if item["status"] == "ready")
    done = engine.execute(latest["id"], "2026-11-04T12:00:00Z")
    assert done["task"]["state"] == "succeeded"
    repeated = PlanEngine(store, PROJECT).execute(latest["id"], "2026-11-04T12:00:00Z")
    assert repeated["reused"] is True and len(TaskRunner(store).list_tasks()) == 1
    before = (store.root / LEDGER).read_bytes()
    rejected(lambda: engine.reconcile("2026-11-03T00:00:00Z"))
    assert (store.root / LEDGER).read_bytes() == before
    long_gap = engine.reconcile("2027-02-01T12:00:00Z")["ledger"]
    assert long_gap["last_window"]["older_history_skipped"] is True
    assert len(long_gap["records"]) < 50


def test_expiry_pause_capacity_and_config_revision(parent):
    store, engine = fixture(parent, "expiry")
    ledger = engine.reconcile("2026-11-02T10:00:00Z", "2026-11-02T00:00:00Z")["ledger"]
    weekly = next(item for item in ledger["records"] if item["plan_id"] == "demo-weekly")
    assert weekly["status"] == "ready"
    skipped = engine.execute(weekly["id"], "2026-11-02T12:00:00Z")
    assert skipped["executed"] is False and skipped["occurrence"]["reason"] == "expired"
    daily = next(item for item in ledger["records"] if item["plan_id"] == "demo-daily")
    TaskRunner(store).pause(True)
    rejected(lambda: engine.execute(daily["id"], "2026-11-02T12:00:00Z"))
    assert TaskRunner(store).list_tasks() == []
    config = load_plans(PROJECT)
    config["plans"][0]["local_time"] = "08:30"
    store.write_json("plans.json", config)
    rejected(engine.state)
    small = load_plans(PROJECT)
    small["max_records"] = 1
    limited, engine = fixture(parent, "capacity", small)
    rejected(lambda: engine.reconcile("2026-11-04T12:00:00Z", "2026-11-01T00:00:00Z"))
    assert not (limited.root / LEDGER).exists()


def test_interruption_and_cross_file_recovery(parent):
    store, engine = fixture(parent, "interruption")
    record = engine.reconcile("2026-11-04T12:00:00Z", "2026-11-04T00:00:00Z")["ledger"]["records"][0]
    class Interrupted(SyntheticAdapter):
        def run(self, task):
            raise KeyboardInterrupt()
    try:
        PlanEngine(store, PROJECT, TaskRunner(store, Interrupted())).execute(record["id"], "2026-11-04T12:00:00Z")
        assert False
    except KeyboardInterrupt:
        pass
    inspected = PlanEngine(store, PROJECT).state()["ledger"]["records"][0]
    assert inspected["status"] == "uncertain"
    result = engine.execute(record["id"], "2026-11-04T12:00:00Z")
    assert result["executed"] is False and not list((store.root / "resources/drafts").iterdir())

    store, engine = fixture(parent, "after-core-success")
    record = engine.reconcile("2026-11-04T12:00:00Z", "2026-11-04T00:00:00Z")["ledger"]["records"][0]
    original = store.write_json
    def interrupted_write(relative, value):
        if relative == LEDGER and any(item["status"] == "succeeded" for item in value["records"]):
            raise OSError("synthetic ledger write failure")
        return original(relative, value)
    store.write_json = interrupted_write
    try:
        engine.execute(record["id"], "2026-11-04T12:00:00Z")
        assert False
    except OSError:
        pass
    finally:
        store.write_json = original
    recovered = PlanEngine(store, PROJECT).execute(record["id"], "2026-11-04T12:00:00Z")
    assert recovered["occurrence"]["status"] == "succeeded" and recovered["executed"] is False
    assert len(list((store.root / "resources/drafts").iterdir())) == 1


def test_cli_private_configuration_and_links(parent):
    store, engine = fixture(parent, "cli")
    cli(store.root, "/plans-copy")
    cli(store.root, "/plans-copy", expected=2)
    assert cli(store.root, "/plans")["mode"] == "manual_only"
    cli(store.root, "/plans-preview", "--since", "2026-11-04T00:00:00Z", "--at", "2026-11-04T12:00:00Z")
    assert not (store.root / LEDGER).exists()
    result = cli(store.root, "/plans-reconcile", "--since", "2026-11-04T00:00:00Z", "--at", "2026-11-04T12:00:00Z")
    identifier = result["ledger"]["records"][0]["id"]
    assert cli(store.root, "/plans-run", identifier, "--at", "2026-11-04T12:00:00Z")["task"]["state"] == "succeeded"
    cli(store.root, "/plans-state")
    (store.root / LEDGER).unlink()
    outside = parent / "plan-sentinel.json"
    outside.write_text("synthetic sentinel")
    (store.root / LEDGER).symlink_to(outside)
    cli(store.root, "/plans-state", expected=2)
    assert outside.read_text() == "synthetic sentinel"


def main():
    cases = [value for name, value in globals().items() if name.startswith("test_")]
    with tempfile.TemporaryDirectory(prefix="assistant-plan-acceptance-") as temporary:
        for case in cases:
            case(Path(temporary))
            print("PASS:", case.__name__)
    print("PASS: %s synthetic planning acceptance groups" % len(cases))


if __name__ == "__main__":
    main()
