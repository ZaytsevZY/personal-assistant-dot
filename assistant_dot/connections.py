"""Explicit local read-only bridges. No login, permission requests or writes."""

from datetime import timedelta
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

from .plans import timestamp
from .process import bounded_process
from .storage import LocalError


def profile_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", value):
        raise LocalError("an explicit safe CLI profile name is required")
    return value


def feishu_status(profile, execute=bounded_process):
    profile_name(profile)
    executable = shutil.which("lark-cli")
    if not executable:
        return {"status": "cli_missing", "writes_implemented": False}
    try:
        value = json.loads(execute([executable, "--profile", profile, "auth", "status", "--json"], timeout=15, limit=65536))
        identities = value["identities"]
        if not isinstance(identities, dict):
            raise ValueError()
        states = {}
        for name in ("bot", "user"):
            identity = identities.get(name, {})
            status = identity.get("status")
            states[name] = {"status": status if status in {"ready", "needs_refresh", "not_configured", "expired", "missing"} else "unknown",
                            "available": identity.get("available") is True}
        return {"status": "local_credentials_inspected", "profile": profile, "identities": states,
                "server_verified": False, "profile_switched": False, "writes_implemented": False}
    except (LocalError, ValueError, KeyError, TypeError, AttributeError, OSError):
        return {"status": "unavailable", "profile": profile, "raw_errors_returned": False, "writes_implemented": False}


def feishu_messages(profile, chat_id, start, end, execute=bounded_process):
    """Only a user-invoked CLI read of one explicit chat and bounded time window.

    Not exposed in the web API and never exercised with a real account in tests.
    """
    profile_name(profile)
    if not isinstance(chat_id, str) or not re.fullmatch(r"oc_[A-Za-z0-9]{1,100}", chat_id):
        raise LocalError("an explicit chat ID is required")
    first, last = timestamp(start), timestamp(end)
    if not first < last <= first + timedelta(days=7):
        raise LocalError("message reads require a window of at most seven days")
    status = feishu_status(profile, execute)
    identity = status.get("identities", {}).get("user", {})
    if identity.get("status") != "ready" or identity.get("available") is not True:
        raise LocalError("selected user identity is not ready; no login or refresh was attempted")
    executable = shutil.which("lark-cli")
    if not executable:
        raise LocalError("lark-cli is unavailable")
    value = json.loads(execute([executable, "--profile", profile, "im", "+chat-messages-list", "--as", "user",
                               "--chat-id", chat_id, "--start", first.isoformat(), "--end", last.isoformat(),
                               "--page-size", "20", "--no-reactions", "--json"], timeout=20, limit=262144))
    # Raw account response remains only in the explicitly invoked local CLI.
    return {"status": "read", "profile": profile, "private_response": value,
            "persisted": False, "attachments_downloaded": False, "writes_implemented": False}


def apple_calendar(project, action="status", calendar_id=None, start=None, end=None, execute=bounded_process):
    if sys.platform != "darwin":
        return {"status": "macos_required", "requested_access": False}
    args = [action]
    if action == "events":
        if not isinstance(calendar_id, str) or not 1 <= len(calendar_id) <= 200 or any(ord(c) < 32 for c in calendar_id):
            raise LocalError("an explicit calendar ID is required; names do not select an account")
        first, last = timestamp(start), timestamp(end)
        if not first < last <= first + timedelta(days=7):
            raise LocalError("calendar reads require a window of at most seven days")
        # Swift formatter uses whole seconds; do not silently broaden precision.
        if first.microsecond or last.microsecond:
            raise LocalError("calendar boundaries require whole seconds")
        args.extend([calendar_id, first.isoformat(), last.isoformat()])
    elif action not in {"status", "calendars"}:
        raise LocalError("calendar action is not implemented")
    script = Path(project) / "scripts/calendar_bridge.swift"
    if script.is_symlink() or not script.is_file() or not Path("/usr/bin/swift").is_file():
        return {"status": "bridge_unavailable", "requested_access": False}
    try:
        with tempfile.TemporaryDirectory(prefix="assistant-calendar-modules-") as cache:
            result = json.loads(execute(["/usr/bin/swift", "-module-cache-path", cache, str(script), *args], timeout=40, limit=262144))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (LocalError, ValueError, OSError):
        return {"status": "bridge_unavailable", "requested_access": False, "raw_errors_returned": False}
