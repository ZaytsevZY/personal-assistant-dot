"""Run with python3 -m assistant_dot; commands never execute shell text."""

import argparse
import json
from pathlib import Path
import sys

from .runtime import TaskRunner, validate_settings
from .console import export_console, load_schedule_registry
from .storage import LocalError, PrivateStore, now
from .plans import PlanEngine, load_plans, preview
from .news import bundled_preview, REFERENCE_AT
from .live_news import fetch_public_news
from .news_sources import source_catalog
from .connections import feishu_status, feishu_messages, apple_calendar


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
        "/plans": "show effective manual-only synthetic plans; optional private override",
        "/plans-preview --since ISO --at ISO": "analyze a bounded due window without writes or execution",
        "/plans-copy": "copy public plan defaults to private plans.json without overwriting",
        "/plans-reconcile --at ISO [--since ISO]": "persist due/skipped occurrences; does not execute",
        "/plans-state": "inspect the private ledger and reconcile interrupted task outcomes",
        "/plans-run ID [--at ISO]": "manually execute one eligible synthetic occurrence",
        "/workbench [--port NUMBER]": "run the interactive loopback workbench in the foreground; Ctrl-C stops it",
        "/news-preview [--at ISO] [--interests TOPIC,TOPIC]": "read-only synthetic news; explicit topics only for this preview; no profile saved",
        "/news-fetch [--sources ID,ID]": "manually fetch fixed official public RSS feeds; no account, storage or delivery",
        "/news-sources": "show reviewed sources, usage boundaries and deferred candidates without fetching",
        "/feishu-status --profile NAME": "inspect selected existing CLI profile locally; no login, switch or message read",
        "/feishu-read --profile NAME --chat-id ID --since ISO --until ISO": "explicit one-chat read, at most 7 days/20 messages; private root required; no send",
        "/calendar-status": "inspect EventKit permission without requesting access or reading events",
        "/calendar-calendars": "read local calendar identifiers only if already authorized; private root required",
        "/calendar-events --calendar-id ID --since ISO --until ISO": "read one chosen calendar, at most 7 days/200 events; private root required",
    },
    "not_configured": ["natural_language_agent", "comprehensive_news_search", "feishu_send", "dot_push", "calendar_write", "market_data", "background_scheduler"],
}


def flags(arguments, allowed, required=()):
    if len(arguments) % 2:
        raise LocalError("plan options require explicit flag/value pairs; use /h")
    result = {}
    for index in range(0, len(arguments), 2):
        key, value = arguments[index:index + 2]
        if key not in allowed or key in result:
            raise LocalError("unsupported or duplicate plan option; use /h")
        result[key] = value
    if any(key not in result for key in required):
        raise LocalError("required plan time boundaries are missing; use /h")
    return result


def command(arguments, private_root=None):
    name = arguments[0] if arguments else "/h"
    rest = arguments[1:]
    if name in {"/h", "/help"} and not rest:
        return HELP
    if name == "/runtime" and not rest:
        return {"status": "local_only", "available_adapter": "synthetic", "private_store_checked": False, "agent_replaceable": True,
                "console_mode": "interactive_loopback", "manual_planning": True,
                "news_preview": "synthetic_read_only",
                "manual_public_news": True, "network_flag_scope": "synthetic_task_runner",
                "network_enabled": False, "delivery_enabled": False, "scheduler_enabled": False}
    if name == "/schedule" and not rest:
        registry = load_schedule_registry(PROJECT)
        return {"status": "not_running", "registry": registry, "changes_supported": False}
    if name == "/news-preview":
        options = flags(rest, {"--at", "--interests"})
        topics = options["--interests"].split(",") if options.get("--interests") else []
        return bundled_preview(PROJECT, options.get("--at", REFERENCE_AT), topics)
    if name == "/news-fetch":
        options = flags(rest, {"--sources"})
        return fetch_public_news(options["--sources"].split(",") if "--sources" in options else None)
    if name == "/news-sources" and not rest:
        return source_catalog()
    if name == "/feishu-status":
        options = flags(rest, {"--profile"}, ("--profile",))
        return feishu_status(options["--profile"])
    if name == "/calendar-status" and not rest:
        return apple_calendar(PROJECT)
    if name in {"/news", "/calendar", "/market", "/review"}:
        return {"status": "not_configured", "command": name, "external_actions_performed": False}
    if name in {"/plans", "/plans-preview"}:
        if private_root:
            store = PrivateStore(private_root, PROJECT)
            with store.lock():
                TaskRunner(store).settings()
                config = load_plans(PROJECT, store)
        else:
            config = load_plans(PROJECT)
        if name == "/plans" and not rest:
            return {"mode": "manual_only", "config": config, "scheduler_enabled": False}
        if name == "/plans-preview":
            options = flags(rest, {"--at", "--since"}, ("--at", "--since"))
            return preview(config, options["--since"], options["--at"])
        raise LocalError("invalid plan command arguments; use /h")
    if name not in {"init", "/capture", "/tasks", "/status", "/run", "/pause", "/resume", "/console", "/plans-copy", "/plans-reconcile", "/plans-state", "/plans-run", "/workbench", "/feishu-read", "/calendar-calendars", "/calendar-events"}:
        raise LocalError("command is not implemented; use /h")
    if not private_root:
        raise LocalError("--private-root is required; no default private directory is created")
    store = PrivateStore(private_root, PROJECT)
    if name in {"/feishu-read", "/calendar-calendars", "/calendar-events"}:
        TaskRunner(store).settings()
        if name == "/feishu-read":
            options = flags(rest, {"--profile", "--chat-id", "--since", "--until"}, ("--profile", "--chat-id", "--since", "--until"))
            return feishu_messages(options["--profile"], options["--chat-id"], options["--since"], options["--until"])
        if name == "/calendar-calendars" and not rest:
            return apple_calendar(PROJECT, "calendars")
        if name == "/calendar-events":
            options = flags(rest, {"--calendar-id", "--since", "--until"}, ("--calendar-id", "--since", "--until"))
            return apple_calendar(PROJECT, "events", options["--calendar-id"], options["--since"], options["--until"])
        raise LocalError("invalid read-only connection command")
    if name == "/workbench":
        from .workbench import serve
        options = flags(rest, {"--port"})
        try:
            port = int(options.get("--port", "0"))
        except ValueError:
            raise LocalError("port must be an integer") from None
        return serve(store, PROJECT, port)
    if name == "init" and not rest:
        settings = json.loads((PROJECT / "config/local-runtime.example.json").read_text())
        store.initialize(validate_settings(settings))
        return {"status": "initialized", "mode": "local_only", "scheduler_enabled": False}
    if name == "/console" and not rest:
        return export_console(store, PROJECT)
    runner = TaskRunner(store)
    if name == "/plans-copy" and not rest:
        with store.lock():
            runner.settings()
            if store._path("plans.json").exists():
                raise LocalError("private plan configuration already exists; it will not be overwritten")
            store.write_json("plans.json", load_plans(PROJECT))
            store.audit("manual_plans_copied")
        return {"status": "copied", "private_file": "plans.json", "scheduler_enabled": False}
    engine = PlanEngine(store, PROJECT, runner)
    if name == "/plans-state" and not rest:
        return engine.state()
    if name == "/plans-reconcile":
        options = flags(rest, {"--at", "--since"}, ("--at",))
        return engine.reconcile(options["--at"], options.get("--since"))
    if name == "/plans-run" and rest:
        options = flags(rest[1:], {"--at"})
        return engine.execute(rest[0], options.get("--at", now()))
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
    return 3 if task.get("state") in {"failed", "uncertain"} or result.get("occurrence", {}).get("status") in {"failed", "uncertain"} else 0


if __name__ == "__main__":
    sys.exit(main())
