"""Real loopback HTTP acceptance with temporary synthetic stores; server always stops."""

import json
from pathlib import Path
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.runtime import SETTINGS
from assistant_dot.storage import PrivateStore
from assistant_dot.workbench import WorkbenchServer


def request(server, route, data=None, headers=None, method=None, authenticated=True):
    values = {"X-Local-Token": server.token} if authenticated else {}
    if data is not None:
        values.update({"Origin": server.origin, "Content-Type": "application/json"})
    if headers:
        for key, value in headers.items():
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
    body = json.dumps(data).encode() if data is not None else None
    call = Request(server.origin + route, data=body, headers=values, method=method)
    try:
        response = urlopen(call, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        text = response.read().decode()
        return response.status, text, response.headers


def main():
    with tempfile.TemporaryDirectory(prefix="assistant-workbench-http-") as directory:
        store = PrivateStore(Path(directory), PROJECT)
        store.initialize(dict(SETTINGS))
        store.capture("SYNTHETIC_NOTE_MUST_STAY_PRIVATE")
        server = WorkbenchServer(store, PROJECT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            assert server.server_address[0] == "127.0.0.1"
            status, text, headers = request(server, "/", authenticated=False)
            assert status == 200 and server.token in text and "/assets/workbench.js" in text
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
            assert headers["Cache-Control"] == "no-store" and headers["X-Frame-Options"] == "DENY"
            for route in ("/assets/workbench.js", "/assets/console.css"):
                assert request(server, route, authenticated=False)[0] == 200
            assert request(server, "/api/state", authenticated=False)[0] == 403
            assert request(server, "/api/state", headers={"X-Local-Token":"invalid"})[0] == 403
            assert request(server, "/api/state", headers={"Host":"untrusted.invalid"})[0] == 403
            assert request(server, "/api/state", headers={"Origin":"https://untrusted.invalid"})[0] == 403
            assert request(server, "/", headers={"Sec-Fetch-Site":"cross-site"}, authenticated=False)[0] == 403
            navigation = {"Sec-Fetch-Site":"cross-site","Sec-Fetch-Mode":"navigate","Sec-Fetch-Dest":"document"}
            assert request(server, "/", headers=navigation, authenticated=False)[0] == 200
            assert request(server, "/api/state", headers=navigation)[0] == 403
            assert request(server, "/", headers=dict(navigation, **{"Sec-Fetch-Dest":"iframe"}), authenticated=False)[0] == 403
            assert request(server, "/api/pause", {"paused":True}, headers={"Origin":None})[0] == 403
            assert request(server, "/api/pause", {"paused":True}, headers={"Content-Type":"text/plain"})[0] == 400
            assert request(server, "/api/pause", {"paused":True}, headers={"Content-Length":"20000"})[0] == 400
            assert request(server, "/api/pause", {"paused":"yes"})[0] == 400
            assert request(server, "/api/pause", {"paused":True,"network_enabled":True})[0] == 400
            assert request(server, "/api/run", {"workflow_id":"demo-news","request_id":"invalid"})[0] == 400
            assert request(server, "/api/run", {"workflow_id":"real-news","request_id":str(uuid4())})[0] == 400
            assert request(server, "/api/state", method="OPTIONS")[0] == 403
            assert request(server, "/../settings.json")[0] == 404
            assert request(server, "/api/enable", {})[0] == 404
            print("PASS: loopback binding, token, Host/Origin, CSRF, payload limits, fixed routes and security headers")

            status, text, _ = request(server, "/api/state")
            assert status == 200 and "SYNTHETIC_NOTE_MUST_STAY_PRIVATE" not in text
            assert json.loads(text)["tasks"] == []
            payload = {"workflow_id":"demo-news","request_id":str(uuid4())}
            first = json.loads(request(server, "/api/run", payload)[1])
            second = json.loads(request(server, "/api/run", payload)[1])
            assert first["task"]["state"] == "succeeded" and second["reused"] is True
            assert first["task"]["task_id"] == second["task"]["task_id"]
            assert "idempotency_key" not in first["task"]
            assert request(server, "/api/pause", {"paused":True})[0] == 200
            assert request(server, "/api/run", {"workflow_id":"demo-news","request_id":str(uuid4())})[0] == 400
            assert request(server, "/api/pause", {"paused":False})[0] == 200
            assert request(server, "/api/inspect", {})[0] == 200
            print("PASS: private state filtering, idempotent manual run, pause/resume and inspection")

            window = {"since":"2026-11-04T00:00:00Z","at":"2026-11-04T12:00:00Z"}
            before = (store.root / "state/tasks.json").read_bytes()
            status, text, _ = request(server, "/api/plans/preview", window)
            assert status == 200 and json.loads(text)["executed"] is False
            assert not (store.root / "state/plans.json").exists()
            assert (store.root / "state/tasks.json").read_bytes() == before
            result = json.loads(request(server, "/api/plans/reconcile", window)[1])
            ready = next(item for item in result["ledger"]["records"] if item["status"] == "ready")
            status, text, _ = request(server, "/api/plans/run", {"id":ready["id"],"at":window["at"]})
            assert status == 200 and json.loads(text)["task"]["state"] == "succeeded"
            again = json.loads(request(server, "/api/plans/run", {"id":ready["id"],"at":window["at"]})[1])
            assert again["executed"] is False
            status, text, _ = request(server, "/api/state")
            data = json.loads(text)
            assert status == 200 and data["watermark"] is not None and data["task_count"] == 2
            assert data["settings"]["scheduler_enabled"] is False and data["settings"]["network_enabled"] is False
            print("PASS: preview without writes, reconciliation without execution and explicit plan run replay")
            news = {"at":"2026-01-15T12:00:00Z","interests":["technology"]}
            snapshot = {p.relative_to(store.root).as_posix():p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
            assert request(server, "/api/news/preview", news, authenticated=False)[0] == 403
            assert request(server, "/api/news/preview", news, headers={"Origin":None})[0] == 403
            assert request(server, "/api/news/preview", dict(news, interests=["inferred-identity"]))[0] == 400
            assert request(server, "/api/news/preview", dict(news, enable_network=True))[0] == 400
            status, text, _ = request(server, "/api/news/preview", news)
            result = json.loads(text)
            assert status == 200 and result["mode"] == "synthetic_preview" and result["persisted"] is False
            assert "SYNTHETIC_NOTE_MUST_STAY_PRIVATE" not in text
            assert len(result["lanes"]["major_public"]) == 3
            assert result["lanes"]["personal_relevant"][0]["topic"] == "technology"
            assert snapshot == {p.relative_to(store.root).as_posix():p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
            assert data["news_preview"]["live_news"] is False
            print("PASS: authenticated news preview, ephemeral interests, private state unchanged and truthful live status")
            with patch("assistant_dot.workbench.fetch_public_news",return_value={"mode":"manual_public_feeds","articles":[],"sources":[]}) as fetched:
                assert request(server,"/api/news/fetch",{},authenticated=False)[0] == 403
                assert fetched.call_count == 0
                assert request(server,"/api/news/fetch",{"url":"https://untrusted.invalid"})[0] == 400
                assert fetched.call_count == 0
                assert request(server,"/api/news/fetch",{})[0] == 200
                assert fetched.call_count == 1
                server.server_news_lock.acquire()
                try: assert request(server,"/api/news/fetch",{})[0] == 400
                finally: server.server_news_lock.release()
            with patch("assistant_dot.workbench.apple_calendar",return_value={"authorization":"not_determined","requested_access":False}) as calendar:
                assert request(server,"/api/calendar/status",{"read_events":True})[0] == 400
                assert calendar.call_count == 0
                assert request(server,"/api/calendar/status",{})[0] == 200
            with patch("assistant_dot.workbench.feishu_status",return_value={"status":"unavailable"}) as feishu:
                assert request(server,"/api/feishu/status",{"profile":"synthetic-work"})[0] == 200
                assert feishu.call_args.args == ("synthetic-work",)
            assert request(server,"/api/calendar/events",{})[0] == 404
            assert request(server,"/api/feishu/send",{})[0] == 404
            assert snapshot == {p.relative_to(store.root).as_posix():p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
            print("PASS: manual public fetch only, no arbitrary endpoints, concurrent fetch guard and no private read/write web routes")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive()
    print("PASS: 5 HTTP acceptance groups; temporary foreground service stopped")


if __name__ == "__main__":
    main()
