"""Small synchronous runner. No network, model, account or scheduler integrations."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Protocol
from uuid import uuid4

from .storage import LocalError, PrivateStore, now


WORKFLOWS = ("demo-news", "demo-open-source")
SETTINGS = {"schema_version": 1, "adapter": "synthetic", "paused": False,
            "network_enabled": False, "delivery_enabled": False, "scheduler_enabled": False}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) != set(SETTINGS):
        raise LocalError("unsupported local settings fields")
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["adapter"] != "synthetic" or type(value["paused"]) is not bool
            or any(value[field] is not False for field in
                   ("network_enabled", "delivery_enabled", "scheduler_enabled"))):
        raise LocalError("local MVP only supports synthetic execution with external actions disabled")
    return value


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    workflow_id: str
    policy_version: str
    permission_ceiling: tuple = ("produce_synthetic_draft",)


@dataclass(frozen=True)
class Draft:
    markdown: str
    synthetic: bool = True


class AgentAdapter(Protocol):
    name: str

    def prepare(self, task: TaskRequest) -> bool:
        """Return whether this adapter supports this local request."""

    def run(self, task: TaskRequest) -> Draft:
        """Return a draft; persistence and output paths belong to the runner."""


class SyntheticAdapter:
    name = "synthetic"

    def prepare(self, task):
        return task.workflow_id in WORKFLOWS

    def run(self, task):
        if task.workflow_id == "demo-news":
            return Draft("# 合成新闻演示\n\n这是测试数据，不是真实新闻；未检索网络。\n\n"
                         "- 时政：虚构机构发布讨论草案，尚未生效。\n"
                         "- 经济：虚构统计仅演示观察期与发布时间的区别。\n"
                         "- 科技：虚构项目发布演示版本，未经实测。\n\n"
                         "来源与独立核实：无，本次不具备新闻核实能力。\n")
        if task.workflow_id == "demo-open-source":
            return Draft("# 合成开源调研演示\n\n这是测试数据，没有考察真实项目。\n\n"
                         "候选：虚构项目。许可证、版本、维护与安全状态均未核实。\n"
                         "建议：仅展示提案格式，不安装、不改策略、不发布。\n")
        raise LocalError("workflow is not supported by this adapter")


class TaskRunner:
    def __init__(self, store: PrivateStore, adapter=None):
        self.store = store
        self.adapter = adapter if adapter is not None else SyntheticAdapter()
        try:
            policy = json.loads((Path(__file__).resolve().parents[1] / "config/policy.example.json").read_text())
            version = policy.get("policy_version") if isinstance(policy, dict) else None
            if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", version):
                raise ValueError()
            self.policy_version = version
        except (OSError, ValueError):
            raise LocalError("public policy version is unavailable or invalid") from None

    def settings(self):
        return validate_settings(self.store.read_json("settings.json", limit=64_000))

    def _tasks(self):
        value = self.store.read_json("state/tasks.json")
        if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("tasks"), list):
            raise LocalError("task state format is invalid")
        tasks = value["tasks"]
        seen = set()
        for item in tasks:
            if (not isinstance(item, dict) or not isinstance(item.get("task_id"), str)
                    or not re.fullmatch(r"[a-f0-9]{32}", item["task_id"])
                    or item["task_id"] in seen or item.get("workflow_id") not in WORKFLOWS
                    or not isinstance(item.get("idempotency_key"), str)
                    or not isinstance(item.get("state"), str)
                    or item["state"] not in {"ready", "running", "succeeded", "failed", "uncertain"}):
                raise LocalError("task record is invalid")
            seen.add(item["task_id"])
        return tasks

    def _save(self, tasks):
        self.store.write_json("state/tasks.json", {"schema_version": 1, "tasks": tasks})

    def _recover_interrupted(self, tasks):
        interrupted = [task for task in tasks if task["state"] in {"ready", "running"}]
        if interrupted:
            for task in interrupted:
                task.update(state="uncertain", updated_at=now())
            self._save(tasks)
            for task in interrupted:
                self.store.audit("interrupted_task_detected", task_id=task["task_id"])

    def list_tasks(self):
        with self.store.lock():
            self.settings()
            tasks = self._tasks()
            self._recover_interrupted(tasks)
            return tasks

    def snapshot(self):
        """Read state consistently without reconciling or changing task records."""
        with self.store.lock():
            return {"settings": self.settings(), "tasks": self._tasks()}

    def inspect(self, task_id):
        if not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise LocalError("invalid task ID")
        with self.store.lock():
            self.settings()
            tasks = self._tasks()
            self._recover_interrupted(tasks)
            for task in tasks:
                if task["task_id"] == task_id:
                    return task
        raise LocalError("task was not found")

    def pause(self, paused):
        with self.store.lock():
            settings = self.settings()
            settings["paused"] = paused
            self.store.write_json("settings.json", settings)
            self.store.audit("manual_runner_paused" if paused else "manual_runner_resumed")
        return {"paused": paused, "scheduler_enabled": False}

    def run(self, workflow_id, idempotency_key=None):
        if workflow_id not in WORKFLOWS:
            raise LocalError("workflow is not configured; only demo workflows can run")
        if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", idempotency_key):
            raise LocalError("idempotency key requires 1 to 80 letters, digits, underscores or hyphens")
        key = idempotency_key if idempotency_key is not None else uuid4().hex
        with self.store.lock():
            settings = self.settings()
            tasks = self._tasks()
            # Holding the writer lock proves no other local run still owns these records.
            self._recover_interrupted(tasks)
            for task in tasks:
                if task["workflow_id"] == workflow_id and task["idempotency_key"] == key:
                    return {"reused": True, "task": task}
            if settings["paused"]:
                raise LocalError("manual runner is paused; use /resume to allow manual demos")
            task_id = uuid4().hex
            request = TaskRequest(task_id, workflow_id, self.policy_version)
            if not self.adapter.prepare(request):
                raise LocalError("adapter does not support this workflow")
            task = {"task_id": task_id, "workflow_id": workflow_id, "idempotency_key": key,
                    "adapter": self.adapter.name, "policy_version": request.policy_version,
                    "state": "ready", "created_at": now(), "updated_at": now(),
                    "synthetic": True, "artifact_refs": [], "verified_side_effects": []}
            tasks.append(task)
            self._save(tasks)
            task.update(state="running", updated_at=now())
            self._save(tasks)
            self.store.audit("task_started", task_id=task_id, workflow_id=workflow_id)
            try:
                draft = self.adapter.run(request)
                if not isinstance(draft, Draft) or draft.synthetic is not True or not isinstance(draft.markdown, str) or len(draft.markdown) > 1_000_000:
                    raise LocalError("adapter returned an invalid synthetic draft")
                relative = "resources/drafts/" + task_id + ".md"
                self.store.write_text(relative, draft.markdown)
                task.update(state="succeeded", artifact_refs=[relative])
            except Exception:
                task.update(state="failed", error="local_adapter_or_storage_failure")
            task["updated_at"] = now()
            self._save(tasks)
            self.store.audit("task_finished", task_id=task_id, state=task["state"])
            return {"reused": False, "task": task}
