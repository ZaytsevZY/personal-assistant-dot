#!/usr/bin/env python3
"""Check the proposed public working-tree snapshot. No network or private reads.

This is a limited heuristic. It does not scan Git history or replace human review.
"""

import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
ERRORS = []


def fail(message):
    ERRORS.append(message)


def require(condition, message):
    if not condition:
        fail(message)


def load_json(relative):
    candidate = ROOT
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            fail(f"{relative}: refusing to read a symbolic link")
            return None
    if not candidate.resolve().is_relative_to(ROOT):
        fail(f"{relative}: refusing to read outside repository")
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{relative}: invalid or unreadable JSON ({type(exc).__name__})")
        return None


def check():
    manifest = load_json("public-files.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        fail("public-files.json: expected files array")
        return
    entries = manifest["files"]
    if not all(isinstance(item, str) for item in entries):
        fail("public-files.json: file names must be strings")
        return
    require(len(entries) == len(set(entries)), "public-files.json: duplicate paths")
    allowed = set(entries)
    for item in allowed:
        path = PurePosixPath(item)
        require(not path.is_absolute() and ".." not in path.parts and str(path) == item,
                "public-files.json: unsafe or noncanonical path")
    if ERRORS:
        return

    actual = set()
    allowed_directories = {
        str(parent)
        for item in allowed
        for parent in PurePosixPath(item).parents
        if str(parent) != "."
    }
    # Never traverse .git; reject links before following any file reference.
    pending = [ROOT]
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            relative = child.relative_to(ROOT).as_posix()
            if relative == ".git":
                require(not child.is_symlink(), ".git: unexpected symbolic link")
                continue
            if child.is_symlink():
                fail(f"{relative}: symbolic links are not allowed")
            elif child.is_dir():
                if child.name == "__pycache__":
                    # Known ignored bytecode is never a public candidate.
                    continue
                elif relative in allowed_directories:
                    pending.append(child)
                else:
                    fail(f"{relative}: unapproved directory; contents not inspected")
            elif child.is_file():
                actual.add(relative)
            else:
                fail(f"{relative}: unsupported filesystem entry")
    for item in sorted(actual - allowed):
        fail(f"{item}: not in public allowlist; do not publish")
    for item in sorted(allowed - actual):
        fail(f"{item}: allowlisted file is missing")

    patterns = {
        "private home path": re.compile(r"/(?:U[s]ers|home)/[^\s<>]+"),
        "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
        "AWS access key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
        "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        "credential assignment": re.compile(
            r'''(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)["']?\s*[:=]\s*["'][A-Za-z0-9_+/=-]{12,}["']'''
        ),
    }
    for item in sorted(allowed & actual):
        path = ROOT / item
        # Do not follow symlinked parent directories from a manifest entry.
        if any(part.is_symlink() for part in [path, *path.parents] if part != ROOT.parent):
            fail(f"{item}: symlinked path is not allowed")
            continue
        if not path.resolve().is_relative_to(ROOT):
            fail(f"{item}: resolves outside repository")
            continue
        if path.stat().st_size > 500_000:
            fail(f"{item}: exceeds public text size limit")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            fail(f"{item}: unreadable UTF-8 text")
            continue
        for label, pattern in patterns.items():
            if pattern.search(content):
                fail(f"{item}: possible {label}; inspect privately")
        if path.suffix == ".json":
            load_json(item)
        if path.suffix == ".md":
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
                if urlparse(link).scheme or link.startswith("#"):
                    continue
                target = (path.parent / unquote(link.split("#", 1)[0])).resolve()
                require(target.is_relative_to(ROOT) and target.is_file(),
                        f"{item}: broken or nonlocal relative link")

    policy = load_json("config/policy.example.json")
    runtime = load_json("config/runtime.example.json")
    local_settings = load_json("config/local-runtime.example.json")
    schedules = load_json("config/schedules.example.json")
    sources = load_json("config/sources.example.json")
    try:
        require(policy["mode"] == "local_mvp", "project must declare the local-only MVP")
        require(policy["project_name"] == "personal-assistant-dot", "project name must match")
        require(policy["integrations"]["desktop_console"] == {
                    "implemented": True, "mode": "interactive_loopback", "default_access": "local_only"},
                "workbench must remain a local-only interactive service")
        require(policy["runtime_file"] in allowed, "runtime config must be allowlisted")
        require(runtime["status"] == "local_mvp", "runtime status must match the local MVP")
        require(policy["local_runtime_file"] in allowed
                and runtime["local_runner"]["config_file"] == policy["local_runtime_file"],
                "local config references must agree and be allowlisted")
        require(runtime["local_runner"]["implemented"] is True
                and runtime["local_runner"]["available_adapter"] == "synthetic",
                "only the synthetic local runner is implemented")
        require(local_settings == {"schema_version": 1, "adapter": "synthetic", "paused": False,
                                   "network_enabled": False, "delivery_enabled": False, "scheduler_enabled": False},
                "public local settings must keep all external actions disabled")
        require(runtime["control_host"]["initial_choice"] == "dot",
                "initial development/control host must match the documented starting point")
        for role in ("control_host", "execution_agent", "model_service", "scheduler_backend", "output_channel"):
            require(runtime[role]["replaceable"] is True and runtime[role]["active_adapter"] is None,
                    "draft roles must be replaceable and not imply an active adapter")
        require(runtime["portable_state"]["private_root"] is None
                and runtime["portable_state"]["platform_memory_is_source_of_truth"] is False,
                "portable state must remain private and independent of platform memory")
        require(runtime["adapter_requirements"]["selection_grants_permissions"] is False,
                "agent selection cannot grant permissions")
        require(policy["publication"] == {"automatic_commits": False, "automatic_pushes": False},
                "automatic publication must remain disabled in this draft")
        require(policy["privacy"]["private_root"] is None,
                "public example cannot include a private data path")
        require(policy["privacy"]["training_on_private_data"] is False,
                "private training cannot be enabled in this draft")
        require(set(policy["news"]["required_coverage"]) == {"politics", "economics", "technology"},
                "major news coverage must include all three topics")
        allocation = policy["news"]["allocation"]
        require(set(allocation) == {"major_public", "personal_relevant", "exploration"},
                "news allocation must contain the three designed lanes")
        require(all(isinstance(x, (int, float)) and 0 < x <= 1 for x in allocation.values())
                and abs(sum(allocation.values()) - 1) < 1e-9,
                "news allocation must be positive and sum to one")
        require(policy["news"]["major_news_floor_cannot_be_learned_away"] is True,
                "major news floor must remain protected")
        require(policy["personalization"]["sensitive_trait_inference"] is False,
                "sensitive trait inference must remain disabled")
        require(schedules["registry_mode"] == "single_project_registry",
                "schedules must be centralized")
        require(schedules["manual_plans_file"] == "config/plans.example.json"
                and schedules["manual_plans_file"] in allowed, "manual plans must use the central registry reference")
        manual = load_json("config/plans.example.json")
        require(manual["mode"] == "manual_only" and manual["dst_gap_policy"] == "skip"
                and manual["dst_fold_policy"] == "earlier", "plans must remain manual-only with explicit DST rules")
        require(all(plan["workflow_id"] in {"demo-news", "demo-open-source"} for plan in manual["plans"]),
                "public plan examples must use synthetic workflows only")
        require(runtime["workbench"] == {"implemented": True, "bind": "127.0.0.1", "foreground_only": True}
                and runtime["manual_planning"]["automatic_execution"] is False,
                "workbench and planner cannot enable background or remote execution")
        require(runtime["news_preview"] == {"implemented": True, "adapter": "synthetic", "network_enabled": False,
                                            "persisted": False, "fixture_file": "templates/news-feed.example.json"},
                "news preview must remain synthetic, offline and read-only")
        fixture = load_json("templates/news-feed.example.json")
        require(fixture["synthetic"] is True and fixture["schema_version"] == 1,
                "news fixture must be explicitly synthetic")
        require(all(item["title"].startswith("【合成】") and urlparse(item["url"]).hostname == "example.org"
                    for item in fixture["reports"]), "news reports must remain reserved-domain synthetic examples")
        require(all(urlparse(item["url"]).hostname == "example.org" for item in fixture["sources"]),
                "news preview sources cannot enable real endpoints")
        require(schedules["scheduler_implemented"] is False, "scheduler is not implemented")
        require(all(schedules[key] is None for key in ("backend", "timezone", "output_channel")),
                "public scheduler example cannot imply configured delivery")
        tasks = schedules["tasks"]
        require({task["id"] for task in tasks} == {"daily-news", "weekly-open-source-review"}
                and len(tasks) == 2, "expected two unique default task definitions")
        require([task["cadence"] for task in tasks] == ["daily", "weekly"],
                "default cadences must match the documented plan")
        for task in tasks:
            require(task["enabled"] is False, "draft schedules must be disabled")
            require(task["workflow_prompt"] in allowed, "schedule prompt must be allowlisted")
        require(policy["schedules_file"] in allowed and policy["sources_file"] in allowed,
                "policy references must be allowlisted")
        identifiers = [source["id"] for source in sources["sources"]]
        require(len(identifiers) == len(set(identifiers)), "source IDs must be unique")
        for source in sources["sources"]:
            url = urlparse(source["url"])
            require(url.scheme == "https" and bool(url.hostname) and not url.username
                    and not url.password and not url.query and not url.fragment,
                    "source must use a clean public HTTPS URL")
    except (KeyError, TypeError, ValueError):
        fail("configuration shape is invalid")


if __name__ == "__main__":
    try:
        check()
    except OSError as exc:
        fail(f"filesystem inspection failed ({type(exc).__name__})")
    for error in ERRORS:
        print(f"FAIL: {error}")
    if ERRORS:
        sys.exit(1)
    print("PASS: public working-tree allowlist, JSON, links, policy consistency and limited sensitive-pattern checks")
    print("Not checked: Git history, semantic privacy, complete secret detection, source availability or runtime behavior")
