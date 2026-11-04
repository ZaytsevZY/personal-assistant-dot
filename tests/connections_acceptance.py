"""Synthetic bridge acceptance. No account messages or calendar events are read."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.connections import apple_calendar, feishu_messages, feishu_status
from assistant_dot.__main__ import command
from assistant_dot.storage import LocalError


def rejected(call):
    try:
        call()
    except LocalError:
        return
    raise AssertionError("unsafe input accepted")


def main():
    calls=[]
    identity={"identities":{"bot":{"status":"ready","available":True},"user":{"status":"needs_refresh","available":True,"openId":"SYNTHETIC_PRIVATE_ID"}},"appId":"SYNTHETIC_PRIVATE_APP"}
    def execute(args,**kwargs):
        calls.append(args)
        return json.dumps(identity).encode()
    with patch("assistant_dot.connections.shutil.which",return_value="/synthetic/lark-cli"):
        status=feishu_status("synthetic-work",execute)
        assert calls[-1] == ["/synthetic/lark-cli","--profile","synthetic-work","auth","status","--json"]
        assert status["server_verified"] is status["profile_switched"] is status["writes_implemented"] is False
        assert "SYNTHETIC_PRIVATE" not in json.dumps(status)
        rejected(lambda:feishu_status("--login",execute))
        rejected(lambda:feishu_messages("synthetic-work","oc_synthetic","2026-01-15T00:00:00Z","2026-01-16T00:00:00Z",execute))
        assert all("+chat-messages-list" not in call for call in calls)
        rejected(lambda:feishu_messages("synthetic-work","oc_synthetic","2026-01-01T00:00:00Z","2026-01-16T00:00:00Z",execute))
        print("PASS: explicit per-call profiles, no global switching, redacted status and fail-closed expired identity")

        identity["identities"]["user"]["status"]="ready"
        def read(args,**kwargs):
            calls.append(args)
            return json.dumps(identity if "auth" in args else {"items":[{"content":"Synthetic private message"}]}).encode()
        result=feishu_messages("synthetic-personal","oc_synthetic","2026-01-15T00:00:00Z","2026-01-16T00:00:00Z",read)
        assert result["persisted"] is False and result["attachments_downloaded"] is False
        args=calls[-1]
        assert args[1:3] == ["--profile","synthetic-personal"]
        assert "--no-reactions" in args and "--download-resources" not in args
        assert args[args.index("--page-size")+1] == "20" and args[args.index("--as")+1] == "user"
        assert not any("send" in part or part == "use" for call in calls for part in call)
        print("PASS: bounded one-chat read arguments, selected identity and no send/download path")

    with patch("assistant_dot.connections.sys.platform","darwin"), patch("assistant_dot.connections.Path.is_file",return_value=True), patch("assistant_dot.connections.Path.is_symlink",return_value=False):
        def native(args,**kwargs):
            calls.append(args)
            return b'{"authorization":"not_determined","readable":false,"requested_access":false,"writes_implemented":false}'
        status=apple_calendar(PROJECT,execute=native)
        assert status["requested_access"] is False and calls[-1][-1] == "status"
        assert "-module-cache-path" in calls[-1]
        rejected(lambda:apple_calendar(PROJECT,"request-access",execute=native))
        rejected(lambda:apple_calendar(PROJECT,"events",None,"2026-01-15T00:00:00Z","2026-01-16T00:00:00Z",execute=native))
        rejected(lambda:apple_calendar(PROJECT,"events","synthetic-calendar","2026-01-01T00:00:00Z","2026-01-16T00:00:00Z",execute=native))
        assert apple_calendar(PROJECT,"events","synthetic-calendar","2026-01-15T00:00:00Z","2026-01-16T00:00:00Z",execute=native)["readable"] is False
        assert calls[-1][-4:] == ["events","synthetic-calendar","2026-01-15T00:00:00+00:00","2026-01-16T00:00:00+00:00"]
    bridge=(PROJECT/"scripts/calendar_bridge.swift").read_text()
    assert "requestFullAccess" not in bridge and "requestAccess(" not in bridge and ".save(" not in bridge and ".remove(" not in bridge
    rejected(lambda:command(["/calendar-calendars"]))
    rejected(lambda:command(["/feishu-read","--profile","synthetic-work"]))
    print("PASS: native permission guard, explicit calendar/window, isolated compiler cache and private CLI boundary")
    print("PASS: 3 connection acceptance groups; synthetic processes only")


if __name__ == "__main__":
    main()
