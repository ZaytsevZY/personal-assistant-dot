"""Explicit foreground loopback workbench; fixed assets and authenticated local API."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from uuid import UUID
from threading import Lock

from .plans import PlanEngine, load_plans, preview
from .runtime import TaskRunner
from .storage import LocalError
from .news import bundled_preview, REFERENCE_AT, TOPICS, POLICY_VERSION
from .live_news import fetch_public_news
from .news_sources import source_catalog
from .connections import feishu_status, apple_calendar


ASSETS = Path(__file__).resolve().parent
POLICY = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
          "img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def task_summary(task):
    return {key: task.get(key) for key in ("task_id", "workflow_id", "state", "created_at", "synthetic")}


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required).issubset(value) or set(value) - set(required) - set(optional):
        raise LocalError("invalid action fields")
    return value


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, store, project, port=0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise LocalError("port must be an integer between 0 and 65535")
        self.store, self.project = store, Path(project)
        self.runner = TaskRunner(store)
        self.runner.settings()
        self.engine = PlanEngine(store, project, self.runner)
        self.token = secrets.token_hex(32)
        self.server_news_lock = Lock()
        super().__init__(("127.0.0.1", port), WorkbenchHandler)
        self.host = "127.0.0.1:" + str(self.server_address[1])
        self.origin = "http://" + self.host

    def state(self):
        snapshot = self.runner.snapshot()
        planned = self.engine.snapshot()
        record_fields = ("id", "plan_id", "workflow_id", "due_at", "local_time", "timezone", "status", "reason")
        return {"mode": "manual_only", "settings": snapshot["settings"],
                "tasks": [task_summary(task) for task in snapshot["tasks"][-100:] if task.get("synthetic") is True],
                "task_count": sum(task.get("synthetic") is True for task in snapshot["tasks"]),
                "plan_config": planned["config"], "watermark": planned["ledger"]["watermark"],
                "occurrences": [{key: item.get(key) for key in record_fields} for item in planned["ledger"]["records"][-100:]],
                "limits": {"task_rows": 100, "plan_rows": 100},
                "news_preview": {"implemented": True, "mode": "synthetic_preview", "reference_at": REFERENCE_AT,
                                 "topics": list(TOPICS), "policy_version": POLICY_VERSION, "live_news": False},
                "public_news": {"implemented": True, "mode": "manual_fixed_public_feeds", "fact_checking": False, "catalog": source_catalog()},
                "connections": {"feishu": "explicit_profile_status_and_cli_read", "apple_calendar": "permission_guarded_cli_read", "writes": False},
                "unavailable": ["background_scheduler", "news_fact_checking", "feishu_send", "dot_push", "calendar_write", "market_data"]}

    def action(self, route, data):
        if route == "/api/feishu/status":
            fields(data, ("profile",))
            return feishu_status(data["profile"])
        if route == "/api/calendar/status":
            fields(data, ())
            return apple_calendar(self.project)
        if route == "/api/news/fetch":
            fields(data, (), ("sources",))
            if "sources" in data and not isinstance(data["sources"], list):
                raise LocalError("sources must be an explicit array of registered IDs")
            if not self.server_news_lock.acquire(blocking=False):
                raise LocalError("public news request already in progress")
            try:
                return fetch_public_news(data.get("sources"))
            finally:
                self.server_news_lock.release()
        if route == "/api/news/preview":
            fields(data, ("at", "interests"))
            return bundled_preview(self.project, data["at"], data["interests"])
        if route == "/api/run":
            fields(data, ("workflow_id", "request_id"))
            if not isinstance(data["workflow_id"], str) or not isinstance(data["request_id"], str):
                raise LocalError("workflow and request ID must be strings")
            try:
                if str(UUID(data["request_id"])) != data["request_id"]:
                    raise ValueError()
            except ValueError:
                raise LocalError("invalid request ID") from None
            result = self.runner.run(data["workflow_id"], "ui_" + data["request_id"])
            return {"reused": result["reused"], "task": task_summary(result["task"])}
        if route == "/api/pause":
            fields(data, ("paused",))
            if type(data["paused"]) is not bool:
                raise LocalError("paused must be a boolean")
            return self.runner.pause(data["paused"])
        if route == "/api/inspect":
            fields(data, ())
            self.runner.list_tasks()
            return self.engine.state()
        if route == "/api/plans/preview":
            fields(data, ("since", "at"))
            with self.store.lock():
                self.runner.settings()
                config = load_plans(self.project, self.store)
            return preview(config, data["since"], data["at"])
        if route == "/api/plans/reconcile":
            fields(data, ("at",), ("since",))
            return self.engine.reconcile(data["at"], data.get("since"))
        if route == "/api/plans/run":
            fields(data, ("id", "at"))
            result = self.engine.execute(data["id"], data["at"])
            if "task" in result:
                result["task"] = task_summary(result["task"])
            return result
        raise LocalError("action is not implemented")


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "AssistantLocal"
    sys_version = ""

    def setup(self):
        super().setup()
        self.request.settimeout(5)

    def log_message(self, format, *args):
        pass  # Never log request bodies, private paths, tokens or user input.

    def _reply(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False)
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(encoded)

    def _allowed(self, api=False, write=False):
        if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") != self.server.host:
            return False
        if len(self.headers.get_all("Origin", [])) > 1 or len(self.headers.get_all("X-Local-Token", [])) > 1:
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            top_navigation = (not api and not write and self.path == "/" and origin is None
                              and self.headers.get("Sec-Fetch-Mode") == "navigate"
                              and self.headers.get("Sec-Fetch-Dest") == "document")
            if not top_navigation:
                return False
        if write and origin != self.server.origin:
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Local-Token", "").encode(), self.server.token.encode()):
            return False
        return True

    def do_GET(self):
        route = urlsplit(self.path)
        if route.query or route.fragment or route.netloc:
            self._reply(404, {"status": "error", "message": "route not found"})
            return
        if not self._allowed(api=route.path.startswith("/api/")):
            self._reply(403, {"status": "error", "message": "local request rejected"})
            return
        try:
            if route.path == "/":
                document = (ASSETS / "workbench.html").read_text().replace("__LOCAL_TOKEN__", self.server.token)
                self._reply(200, document, "text/html; charset=utf-8")
            elif route.path in {"/assets/console.css", "/assets/workbench.js"}:
                name = route.path.rsplit("/", 1)[1]
                self._reply(200, (ASSETS / name).read_text(), "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8")
            elif route.path == "/api/state":
                self._reply(200, self.server.state())
            else:
                self._reply(404, {"status": "error", "message": "route not found"})
        except (LocalError, OSError, ValueError):
            self._reply(409, {"status": "error", "message": "local state unavailable; inspect configuration or retry after active commands finish"})

    def do_POST(self):
        if not self._allowed(api=True, write=True):
            self._reply(403, {"status": "error", "message": "local request rejected"})
            return
        routes = {"/api/run", "/api/pause", "/api/inspect", "/api/plans/preview", "/api/plans/reconcile", "/api/plans/run", "/api/news/preview", "/api/news/fetch", "/api/feishu/status", "/api/calendar/status"}
        if self.path not in routes:
            self._reply(404, {"status": "error", "message": "action not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (not 1 <= length <= 16_384 or len(self.headers.get_all("Content-Length", [])) != 1
                    or self.headers.get("Transfer-Encoding") is not None
                    or self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json"):
                raise LocalError("a bounded JSON request body is required")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            self._reply(200, self.server.action(self.path, data))
        except LocalError as error:
            self._reply(400, {"status": "error", "message": str(error)})
        except (ValueError, UnicodeError):
            self._reply(400, {"status": "error", "message": "invalid JSON request"})
        except Exception:
            self._reply(500, {"status": "error", "message": "local action outcome uncertain; inspect state before retrying"})

    def do_OPTIONS(self):
        self._reply(403, {"status": "error", "message": "cross-origin requests are not supported"})


def serve(store, project, port=0):
    server = WorkbenchServer(store, project, port)
    print(json.dumps({"status": "listening", "url": server.origin, "mode": "foreground_manual_only"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"status": "stopped", "scheduler_enabled": False}
