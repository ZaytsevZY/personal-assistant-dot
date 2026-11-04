"""Run with python3 -m assistant_dot; commands never execute shell text."""

import argparse
import json
from pathlib import Path
import sys

from .runtime import TaskRunner, validate_settings
from .console import export_console, load_schedule_registry
from .storage import LocalError, PrivateStore


PROJECT = Path(__file__).resolve().parents[1]
HELP = {
    "status": "local_only",
    "commands": {
        "/h": "show implemented commands and unavailable integrations",
        "init": "initialize a new external private directory with --private-root",
        "/capture TEXT | /capture --stdin": "save an unclassified private note; stdin avoids shell history",
        "/tasks": "list private task records",
        "/status ID": "inspect a task; flag interrupted execution as uncertain",
        "/run demo-news|demo-open-source [--key VALUE]": "run synthetic data only; optional replay protection",
        "/pause | /resume": "pause/resume manual demo runs, not a background scheduler",
        "/runtime": "show local capabilities without account details",
        "/schedule": "show the central registry; all schedules remain disabled",
        "/console": "export a read-only local HTML snapshot and hypothetical UTC preview",
    },
    "not_configured": ["natural_language_agent", "live_news", "feishu", "dot_push", "calendar", "market_data", "live_console_controls", "scheduler"],
}


def command(arguments, private_root=None):
    name = arguments[0] if arguments else "/h"
    rest = arguments[1:]
    if name in {"/h", "/help"} and not rest:
        return HELP
    if name == "/runtime" and not rest:
        return {"status": "local_only", "available_adapter": "synthetic", "private_store_checked": False, "agent_replaceable": True,
                "console_mode": "read_only_local_snapshot",
                "network_enabled": False, "delivery_enabled": False, "scheduler_enabled": False}
    if name == "/schedule" and not rest:
        registry = load_schedule_registry(PROJECT)
        return {"status": "not_running", "registry": registry, "changes_supported": False}
    if name in {"/news", "/calendar", "/market", "/review"}:
        return {"status": "not_configured", "command": name, "external_actions_performed": False}
    if name not in {"init", "/capture", "/tasks", "/status", "/run", "/pause", "/resume", "/console"}:
        raise LocalError("command is not implemented; use /h")
    if not private_root:
        raise LocalError("--private-root is required; no default private directory is created")
    store = PrivateStore(private_root, PROJECT)
    if name == "init" and not rest:
        settings = json.loads((PROJECT / "config/local-runtime.example.json").read_text())
        store.initialize(validate_settings(settings))
        return {"status": "initialized", "mode": "local_only", "scheduler_enabled": False}
    if name == "/console" and not rest:
        return export_console(store, PROJECT)
    runner = TaskRunner(store)
    if name == "/capture":
        runner.settings()
        text = sys.stdin.read(20_001) if rest == ["--stdin"] else " ".join(rest)
        return store.capture(text)
    if name == "/tasks" and not rest:
        return {"tasks": runner.list_tasks()}
    if name == "/status" and len(rest) == 1:
        return {"task": runner.inspect(rest[0])}
    if name in {"/pause", "/resume"} and not rest:
        return runner.pause(name == "/pause")
    if name == "/run" and (len(rest) == 1 or (len(rest) == 3 and rest[1] == "--key")):
        return runner.run(rest[0], rest[2] if len(rest) == 3 else None)
    raise LocalError("invalid command arguments; use /h")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local-only personal assistant MVP")
    parser.add_argument("--private-root", help="external, non-Git private data directory")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        result = command(args.command, args.private_root)
    except (LocalError, OSError, UnicodeError, ValueError) as exc:
        # Filesystem errors may include private paths; do not echo their details.
        message = str(exc) if isinstance(exc, LocalError) else "local storage or configuration is unavailable"
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    task = result.get("task", {})
    return 3 if task.get("state") in {"failed", "uncertain"} else 0


if __name__ == "__main__":
    sys.exit(main())
