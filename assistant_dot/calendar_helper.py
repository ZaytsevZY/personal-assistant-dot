"""Verified local app identity; authorization is explicit CLI, never a web action."""

import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
import tempfile

from .process import bounded_process
from .storage import LocalError

APP_NAME = "Personal Assistant Calendar Reader"
APP_ID = "org.personalassistantdot.calendarreader"
SOURCES = ("scripts/calendar_bridge.swift", "native/calendar-reader/main.swift")


def application_directory():
    # A home directory may itself be a Git worktree. Use a private per-user
    # subdirectory of the standard Shared directory, never a shared data store.
    return Path("/Users") / "Shared" / ("PersonalAssistantDot-" + str(os.getuid()))


def source_hashes(project):
    return {path: hashlib.sha256((Path(project) / path).read_bytes()).hexdigest() for path in SOURCES}


def owned(path, directory=False):
    info = path.lstat()
    if (info.st_uid != os.getuid() or (stat.S_IMODE(info.st_mode) & 0o077)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise LocalError("calendar helper requires owned private files and real directories")


class CalendarHelper:
    def __init__(self, project, app=None, execute=bounded_process):
        self.project = Path(project)
        self.app = Path(app) if app else application_directory() / (APP_NAME + ".app")
        self.receipt = self.app.parent / (APP_NAME + ".receipt.json")
        self.execute = execute

    def verify(self):
        if sys.platform != "darwin":
            raise LocalError("calendar helper requires macOS")
        if self.app.name != APP_NAME + ".app" or self.app.resolve() != self.app.absolute():
            raise LocalError("calendar helper path is not the expected real application")
        for path in (self.app.parent, self.app, self.app / "Contents", self.app / "Contents/MacOS", self.app / "Contents/Resources"):
            owned(path, directory=True)
        binary = self.app / "Contents/MacOS/CalendarReader"
        manifest_path = self.app / "Contents/Resources/source-manifest.json"
        info_path = self.app / "Contents/Info.plist"
        for path, size in ((self.receipt, 32768), (manifest_path, 32768), (info_path, 65536), (binary, 16000000)):
            owned(path)
            if path.stat().st_size > size:
                raise LocalError("calendar helper file exceeds limits")
        receipt = json.loads(self.receipt.read_text())
        manifest = json.loads(manifest_path.read_text())
        info = plistlib.loads(info_path.read_bytes())
        expected = source_hashes(self.project)
        if not isinstance(receipt, dict) or not isinstance(info, dict):
            raise LocalError("calendar helper metadata is not an object")
        if (receipt.get("schema_version") != 1 or receipt.get("bundle_id") != APP_ID
                or receipt.get("sources") != expected or manifest != {"bundle_id": APP_ID, "sources": expected}
                or receipt.get("binary_sha256") != hashlib.sha256(binary.read_bytes()).hexdigest()
                or info.get("CFBundleIdentifier") != APP_ID or info.get("CFBundleExecutable") != "CalendarReader"
                or not info.get("NSCalendarsFullAccessUsageDescription")):
            raise LocalError("calendar helper identity or source receipt does not match; no app launched")
        self.execute(["/usr/bin/codesign", "--verify", "--strict", str(self.app)], timeout=10, limit=4096)

    def invoke(self, arguments):
        if (not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments)
                or not (arguments in [["status"], ["calendars"]]
                        or (len(arguments) == 3 and arguments[0] == "resolve")
                        or (len(arguments) == 4 and arguments[0] in {"events", "verify"}))
                or any(not arg or len(arg) > 200 or any(ord(c) < 32 for c in arg) for arg in arguments)):
            raise LocalError("only explicit bounded read operations use the result channel")
        self.verify()
        with tempfile.TemporaryDirectory(prefix="assistant-calendar-call-") as directory:
            root = Path(directory).resolve()
            result = root / "result.json"
            self.execute(["/usr/bin/open", "-W", "-n", str(self.app), "--args", *arguments, "--result", str(result)],
                         timeout=25, limit=4096)
            owned(result)
            if result.stat().st_size > 262144:
                raise LocalError("calendar helper result exceeds limits")
            value = json.loads(result.read_text())
        if not isinstance(value, dict) or value.get("bundle_id") != APP_ID:
            raise LocalError("calendar helper returned an unexpected identity")
        return value

    def authorize(self):
        try:
            state = self.invoke(["status"])
        except (OSError, ValueError, LocalError):
            return {"status": "helper_unavailable", "requested_access": False, "raw_errors_returned": False}
        if state.get("readable") is True:
            return {"status": "already_authorized", "requested_access": False, "bundle_id": APP_ID}
        if state.get("authorization") != "not_determined":
            return {"status": "system_settings_required", "authorization": state.get("authorization"),
                    "requested_access": False, "bundle_id": APP_ID}
        # open returns after launch; only the human can grant the system prompt.
        try:
            self.execute(["/usr/bin/open", "-n", str(self.app), "--args", "authorize"], timeout=10, limit=4096)
        except (OSError, LocalError):
            return {"status": "authorization_launch_uncertain", "requested_access": None, "bundle_id": APP_ID,
                    "system_grant_verified": False, "calendar_data_read": False, "raw_errors_returned": False}
        return {"status": "awaiting_user_system_decision", "requested_access": True, "bundle_id": APP_ID,
                "app_name": APP_NAME, "system_grant_verified": False, "calendar_data_read": False}
