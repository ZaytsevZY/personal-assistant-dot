"""Offline acceptance tests using only temporary synthetic private stores."""

import json
import base64
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.runtime import Draft, SyntheticAdapter, TaskRunner
from assistant_dot.storage import LocalError, PrivateStore
from assistant_dot.console import load_schedule_registry


def cli(*arguments, root=None, input_text=None, expected=0):
    argv = [sys.executable, "-B", "-m", "assistant_dot"]
    if root is not None:
        argv += ["--private-root", str(root)]
    process = subprocess.run(argv + list(arguments), cwd=PROJECT, input=input_text,
                             text=True, capture_output=True, timeout=10)
    assert process.returncode == expected, (process.returncode, process.stdout, process.stderr)
    assert not process.stderr, process.stderr
    return json.loads(process.stdout)


def initialized(parent, name):
    root = parent / name
    assert cli("init", root=root)["status"] == "initialized"
    return root


def test_help_and_capabilities(parent):
    assert "/h" in cli("/h")["commands"]
    assert cli("/runtime")["network_enabled"] is False
    for name in ("/news", "/calendar", "/market", "/review"):
        assert cli(name)["status"] == "not_configured"
    assert all(not task["enabled"] for task in cli("/schedule")["registry"]["tasks"])
    assert cli("natural language input", expected=2)["status"] == "error"
    assert cli("/tasks", expected=2)["status"] == "error"


def test_private_capture_and_permissions(parent):
    root = initialized(parent, "capture")
    note = "Synthetic note: $(touch SHOULD_NOT_EXIST)\nThis is an idea, not a commitment."
    result = cli("/capture", "--stdin", root=root, input_text=note)
    saved = json.loads((root / result["private_file"]).read_text())
    assert saved["text"] == note and saved["classification"] == "unclassified"
    assert note not in (root / "audit/events.jsonl").read_text()
    assert not (PROJECT / "SHOULD_NOT_EXIST").exists()
    for path in [root, *root.rglob("*")]:
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    cli("/capture", " ", root=root, expected=2)
    cli("init", root=root, expected=2)
    assert json.loads((root / result["private_file"]).read_text())["text"] == note


def test_directory_boundaries(parent):
    forbidden = PROJECT / "private-test-probe"
    cli("init", root=forbidden, expected=2)
    assert not forbidden.exists()
    cli("init", root=PROJECT, expected=2)
    other = parent / "other-git-tree"
    other.mkdir()
    (other / ".git").mkdir()
    cli("init", root=other / "private", expected=2)
    assert not (other / "private").exists()
    link = parent / "project-link"
    link.symlink_to(PROJECT, target_is_directory=True)
    cli("init", root=link, expected=2)
    populated = parent / "populated"
    populated.mkdir(mode=0o700)
    (populated / "keep.txt").write_text("synthetic sentinel")
    cli("init", root=populated, expected=2)
    assert (populated / "keep.txt").read_text() == "synthetic sentinel"
    permissive = parent / "permissive"
    permissive.mkdir(mode=0o755)
    permissive.chmod(0o755)
    cli("init", root=permissive, expected=2)
    assert not list(permissive.iterdir())


def test_run_replay_pause_and_scope(parent):
    root = initialized(parent, "runner")
    first = cli("/run", "demo-news", "--key", "sample", root=root)
    task = first["task"]
    assert task["state"] == "succeeded" and task["synthetic"] is True
    assert task["verified_side_effects"] == []
    artifact = root / task["artifact_refs"][0]
    assert "合成新闻演示" in artifact.read_text()
    original = artifact.stat().st_mtime_ns
    replay = cli("/run", "demo-news", "--key", "sample", root=root)
    assert replay["reused"] is True and replay["task"]["task_id"] == task["task_id"]
    assert artifact.stat().st_mtime_ns == original
    assert len(cli("/tasks", root=root)["tasks"]) == 1
    assert cli("/status", task["task_id"], root=root)["task"]["state"] == "succeeded"
    cli("/status", "../settings.json", root=root, expected=2)
    cli("/run", "daily-news", root=root, expected=2)
    cli("/run", "demo-news", "--key", "../unsafe", root=root, expected=2)
    assert cli("/pause", root=root)["paused"] is True
    cli("/run", "demo-open-source", root=root, expected=2)
    assert cli("/resume", root=root)["scheduler_enabled"] is False
    assert cli("/run", "demo-open-source", root=root)["task"]["state"] == "succeeded"


def test_config_and_state_fail_closed(parent):
    root = initialized(parent, "bad-config")
    config_file = root / "settings.json"
    settings = json.loads(config_file.read_text())
    for field in ("network_enabled", "delivery_enabled", "scheduler_enabled"):
        changed = dict(settings, **{field: True})
        config_file.write_text(json.dumps(changed))
        cli("/run", "demo-news", root=root, expected=2)
    config_file.write_text(json.dumps(dict(settings, unsupported="synthetic")))
    cli("/tasks", root=root, expected=2)
    config_file.write_text(json.dumps(settings))
    (root / "state/tasks.json").write_text("not JSON")
    cli("/tasks", root=root, expected=2)
    assert (root / "state/tasks.json").read_text() == "not JSON"


def test_symlinks_and_hardlinks(parent):
    root = initialized(parent, "links")
    outside = parent / "external-sentinel.json"
    outside.write_text("synthetic sentinel")
    state = root / "state/tasks.json"
    original = state.read_bytes()
    state.unlink()
    state.symlink_to(outside)
    cli("/tasks", root=root, expected=2)
    assert outside.read_text() == "synthetic sentinel"
    state.unlink()
    state.write_bytes(original)
    state.chmod(0o600)
    os.link(state, parent / "state-hardlink")
    cli("/tasks", root=root, expected=2)
    (parent / "state-hardlink").unlink()
    drafts = root / "resources/drafts"
    drafts.rmdir()
    drafts.symlink_to(parent, target_is_directory=True)
    result = cli("/run", "demo-news", root=root, expected=3)
    assert result["task"]["state"] == "failed"
    assert not (parent / (result["task"]["task_id"] + ".md")).exists()


def test_lock_contention(parent):
    root = initialized(parent, "locked")
    store = PrivateStore(root, PROJECT)
    with store.lock():
        result = cli("/run", "demo-news", root=root, expected=2)
        assert "busy" in result["message"]
    assert cli("/tasks", root=root)["tasks"] == []


def test_interruption_and_adapter_replacement(parent):
    root = initialized(parent, "interrupted")
    store = PrivateStore(root, PROJECT)

    class Interrupted(SyntheticAdapter):
        name = "synthetic-interruption"

        def run(self, task):
            raise KeyboardInterrupt()

    try:
        TaskRunner(store, Interrupted()).run("demo-news", "interruption")
        assert False, "synthetic interruption should propagate"
    except KeyboardInterrupt:
        pass
    record = json.loads((root / "state/tasks.json").read_text())["tasks"][0]
    assert record["state"] == "running"
    assert cli("/status", record["task_id"], root=root, expected=3)["task"]["state"] == "uncertain"
    assert cli("/run", "demo-news", "--key", "interruption", root=root, expected=3)["reused"] is True
    assert not list((root / "resources/drafts").iterdir())

    class Replacement(SyntheticAdapter):
        name = "synthetic-replacement"

        def run(self, task):
            return Draft("# Synthetic replacement adapter\nNo network or external actions.\n")

    first = TaskRunner(store).run("demo-open-source", "replacement")
    second = TaskRunner(store, Replacement()).run("demo-open-source", "replacement")
    assert second["reused"] is True and second["task"]["task_id"] == first["task"]["task_id"]
    third = TaskRunner(store, Replacement()).run("demo-open-source", "different")
    assert third["task"]["adapter"] == "synthetic-replacement" and third["task"]["state"] == "succeeded"


def test_readonly_console_export(parent):
    root = initialized(parent, "console")
    cli("/capture", "--stdin", root=root, input_text="SYNTHETIC_NOTE_MUST_NOT_APPEAR_IN_CONSOLE")
    cli("/run", "demo-news", "--key", "console", root=root)
    tasks_file = root / "state/tasks.json"
    state = json.loads(tasks_file.read_text())
    state["tasks"][0]["state"] = "running"
    state["tasks"][0]["created_at"] = '</td><script>alert("synthetic")</script>'
    state["tasks"][0]["idempotency_key"] = "private-demo"
    excluded = dict(state["tasks"][0], task_id="f" * 32, synthetic=False,
                    idempotency_key="excluded", created_at="SYNTHETIC_EXCLUDED_RECORD")
    state["tasks"].append(excluded)
    tasks_file.write_text(json.dumps(state))
    before_state = tasks_file.read_bytes()
    before_settings = (root / "settings.json").read_bytes()
    result = cli("/console", root=root)
    assert result["mode"] == "read_only_local_snapshot"
    path = root / result["private_file"]
    document = path.read_text()
    assert "SYNTHETIC_NOTE_MUST_NOT_APPEAR_IN_CONSOLE" not in document
    assert "private-demo" not in document
    assert "SYNTHETIC_EXCLUDED_RECORD" not in document
    assert '</td><script>alert("synthetic")</script>' not in document
    assert "&lt;/td&gt;&lt;script&gt;" in document
    assert "需核对" in document and "不会保存、启用或触发任务" in document
    assert tasks_file.read_bytes() == before_state
    assert (root / "settings.json").read_bytes() == before_settings
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    class ConsoleParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.policy = ""
            self.inline = {"script": "", "style": ""}
            self.current = None
            self.remote_resources = []
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if "id" in values:
                self.ids.add(values["id"])
            if tag == "meta" and values.get("http-equiv") == "Content-Security-Policy":
                self.policy = values["content"]
            if tag in self.inline:
                self.current = tag
            if "src" in values or (tag == "link" and "href" in values):
                self.remote_resources.append(values)

        def handle_endtag(self, tag):
            if tag == self.current:
                self.current = None

        def handle_data(self, data):
            if self.current:
                self.inline[self.current] += data

    parser = ConsoleParser()
    parser.feed(document)
    assert not parser.remote_resources
    assert {"reference", "daily-time", "weekly-day", "weekly-time", "preview-count",
            "preview-button", "preview-results", "preview-error", "task-filter"}.issubset(parser.ids)
    assert "connect-src 'none'" in parser.policy and "default-src 'none'" in parser.policy
    for content in parser.inline.values():
        digest = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
        assert "'sha256-" + digest + "'" in parser.policy
    path.unlink()
    outside = parent / "console-sentinel.html"
    outside.write_text("synthetic sentinel")
    path.symlink_to(outside)
    cli("/console", root=root, expected=2)
    assert outside.read_text() == "synthetic sentinel"
    cli("/console", expected=2)


def test_central_registry_refuses_activation(parent):
    project = parent / "registry-project"
    (project / "config").mkdir(parents=True)
    original = json.loads((PROJECT / "config/schedules.example.json").read_text())
    target = project / "config/schedules.example.json"
    target.write_text(json.dumps(original))
    assert load_schedule_registry(project)["scheduler_implemented"] is False
    for mutate in (lambda v: v["tasks"][0].update(enabled=True),
                   lambda v: v.update(output_channel="synthetic-channel"),
                   lambda v: v["tasks"][0].update(local_time="08:00"),
                   lambda v: v["tasks"][0].update(id=["invalid"])):
        value = json.loads(json.dumps(original))
        mutate(value)
        target.write_text(json.dumps(value))
        try:
            load_schedule_registry(project)
            assert False, "modified schedule must be rejected"
        except LocalError:
            pass


def main():
    cases = [value for name, value in globals().items() if name.startswith("test_")]
    with tempfile.TemporaryDirectory(prefix="assistant-local-acceptance-") as temporary:
        parent = Path(temporary)
        for case in cases:
            case(parent)
            print("PASS:", case.__name__)
    print("PASS: %s offline acceptance groups; synthetic data only" % len(cases))


if __name__ == "__main__":
    main()
