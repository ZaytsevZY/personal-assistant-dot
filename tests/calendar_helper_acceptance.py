"""Synthetic app receipts and IPC; never launches EventKit or requests access."""

import hashlib
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.calendar_helper import APP_ID, APP_NAME, CalendarHelper, source_hashes
from assistant_dot.storage import LocalError
from assistant_dot.__main__ import command


def rejected(call):
    try:
        call()
    except (LocalError, OSError, ValueError):
        return
    raise AssertionError("unsafe helper accepted")


def main():
    with tempfile.TemporaryDirectory(prefix="synthetic-calendar-") as directory:
        root = Path(directory).resolve()
        app = root / (APP_NAME + ".app")
        binary = app / "Contents/MacOS/CalendarReader"
        binary.parent.mkdir(parents=True)
        resources = app / "Contents/Resources"
        resources.mkdir()
        binary.write_bytes(b"synthetic binary; never executable")
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier":APP_ID,
            "CFBundleExecutable":"CalendarReader", "NSCalendarsFullAccessUsageDescription":"Synthetic purpose"}))
        manifest = {"bundle_id":APP_ID,"sources":source_hashes(PROJECT)}
        (resources / "source-manifest.json").write_text(json.dumps(manifest))
        receipt = root / (APP_NAME + ".receipt.json")
        receipt.write_text(json.dumps({**manifest,"schema_version":1,
            "binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest()}))
        for path in [app,*app.rglob("*"),receipt]:
            path.chmod(0o700 if path.is_dir() else 0o600)
        calls=[]
        authorization="not_determined"
        def execute(args,**kwargs):
            calls.append(args)
            if "--result" in args:
                result=Path(args[-1])
                assert not result.exists() and result.parent.stat().st_mode & 0o077 == 0
                assert "authorize" not in args
                fd=os.open(result,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,"w") as stream:
                    json.dump({"bundle_id":APP_ID,"authorization":authorization,
                               "readable":authorization=="full_access"},stream)
            return b""
        helper=CalendarHelper(PROJECT,app,execute)
        with patch("assistant_dot.calendar_helper.sys.platform","darwin"):
            helper.verify()
            rejected(lambda:helper.invoke(["authorize"]))
            rejected(lambda:helper.invoke(["unknown"]))
            result=helper.invoke(["status"])
            assert result["readable"] is False and all("authorize" not in call for call in calls)
            assert not Path(calls[-1][-1]).exists()
            print("PASS: verified identity, bounded private local IPC and result cleanup; no implicit access request")
            assert helper.authorize()["status"]=="awaiting_user_system_decision"
            assert calls[-1] == ["/usr/bin/open","-n",str(app),"--args","authorize"]
            authorization="denied"
            before=len(calls)
            assert helper.authorize()["status"]=="system_settings_required"
            assert all("authorize" not in call for call in calls[before:])
            authorization="full_access"
            assert helper.authorize()["status"]=="already_authorized"
            authorization="not_determined"
            def failed_launch(args,**kwargs):
                if args[-1]=="authorize":
                    raise LocalError("synthetic launch failure")
                return execute(args,**kwargs)
            helper.execute=failed_launch
            assert helper.authorize()["status"]=="authorization_launch_uncertain"
            helper.execute=execute
            print("PASS: explicit request only when undetermined; denial never retries, existing grant never prompts")
            before=len(calls)
            binary.write_bytes(b"modified synthetic binary")
            rejected(helper.verify)
            assert len(calls)==before
            binary.write_bytes(b"synthetic binary; never executable")
            receipt.chmod(0o644)
            rejected(helper.verify)
            receipt.chmod(0o600)
            real=receipt.with_suffix(".backup")
            receipt.rename(real);receipt.symlink_to(real)
            rejected(helper.verify)
            print("PASS: binary substitution, exposed receipt and symlink fail before launch")
    with patch("assistant_dot.__main__.CalendarHelper") as mock:
        mock.return_value.authorize.return_value={"status":"synthetic"}
        assert command(["/calendar-authorize"])["status"]=="synthetic"
        mock.return_value.authorize.assert_called_once_with()
    source=(PROJECT / "native/calendar-reader/main.swift").read_text()
    branch=source[source.index('if args == ["authorize"]'):source.index('if args.isEmpty')]
    assert "calendarRead(" not in branch and "requestFullAccessToEvents" in branch
    assert "asyncAfter" in source and "O_NOFOLLOW" in source
    assert "/api/calendar/authorize" not in (PROJECT / "assistant_dot/workbench.py").read_text()
    print("PASS: permission-only native branch, process deadline and no web authorization endpoint")
    print("PASS: 4 calendar helper acceptance groups; synthetic only")


if __name__ == "__main__":
    main()
