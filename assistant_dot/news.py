"""Bounded, read-only news preview over explicitly supplied source adapters.

Only bundled synthetic sources are registered. Adapters are trusted Python code,
not a sandbox; source payloads are untrusted data and cannot select adapters.
"""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import re
from typing import Protocol
from urllib.parse import urlsplit

from .plans import timestamp
from .storage import LocalError


TOPICS = ("politics", "economics", "technology")
REFERENCE_AT = "2026-01-15T12:00:00Z"
POLICY_VERSION = "synthetic-preview-1"
MAX_REPORTS = 50


class NewsSource(Protocol):
    """A trusted adapter returns at most 50 normalized synthetic reports.

    Any future network implementation needs separate permission, timeout,
    byte limits, license review and endpoint validation before registration.
    """

    id: str

    def collect(self) -> list:
        ...


def text(value, limit=600):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise LocalError("invalid news text")
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise LocalError("invalid news identifier")
    return value


def interests(value):
    if (not isinstance(value, list) or len(value) > 3 or any(item not in TOPICS for item in value)
            or len(set(value)) != len(value)):
        raise LocalError("interests must be unique explicit politics, economics or technology topics")
    return sorted(value)


def reserved_url(value):
    url = urlsplit(text(value, 300))
    # This preview accepts reserved example domains only; never fetches them.
    if (url.scheme != "https" or url.hostname != "example.org" or url.netloc != "example.org"
            or url.username or url.password or url.query or url.fragment or "\\" in value):
        raise LocalError("synthetic sources require clean reserved example.org URLs")
    return value


def source_info(value):
    if not isinstance(value, dict) or set(value) != {"id", "name", "url", "origin_chain_id", "kind"}:
        raise LocalError("invalid source descriptor")
    identifier(value["id"])
    identifier(value["origin_chain_id"])
    text(value["name"], 120)
    reserved_url(value["url"])
    if value["kind"] not in ("primary_statement", "reporting", "syndicated"):
        raise LocalError("unsupported source kind")
    return deepcopy(value)


def report(value, source_ids):
    keys = {"id", "event_id", "topic", "title", "url", "event_time", "published_at", "source_id",
            "major", "statements", "uncertainties", "correction_of"}
    if not isinstance(value, dict) or set(value) != keys:
        raise LocalError("invalid news report fields")
    for key in ("id", "event_id", "source_id"):
        identifier(value[key])
    if value["source_id"] not in source_ids or value["topic"] not in TOPICS or type(value["major"]) is not bool:
        raise LocalError("unsupported news topic or source")
    text(value["title"], 180)
    reserved_url(value["url"])
    published = timestamp(value["published_at"])
    if value["event_time"] is not None:
        timestamp(value["event_time"])
    if value["correction_of"] is not None:
        identifier(value["correction_of"])
    statements = value["statements"]
    if not isinstance(statements, list) or not 1 <= len(statements) <= 6:
        raise LocalError("news statements must be bounded")
    for item in statements:
        if (not isinstance(item, dict) or set(item) != {"kind", "text"}
                or item["kind"] not in ("reported_fact", "commentary")):
            raise LocalError("statements require explicit reported_fact or commentary attribution")
        text(item["text"])
    if not isinstance(value["uncertainties"], list) or len(value["uncertainties"]) > 6:
        raise LocalError("news uncertainty list must be bounded")
    for item in value["uncertainties"]:
        text(item)
    result = deepcopy(value)
    result["retrieved_at"] = None  # No network retrieval occurred; do not invent a timestamp.
    result["published_at"] = published.isoformat()
    if value["event_time"] is not None:
        result["event_time"] = timestamp(value["event_time"]).isoformat()
    return result


class SyntheticSource:
    def __init__(self, source_id, rows):
        self.id = source_id
        self._rows = deepcopy(rows)

    def collect(self):
        return deepcopy(self._rows)


def bundled_sources(project):
    path = Path(project) / "templates/news-feed.example.json"
    if path.is_symlink() or path.stat().st_size > 100_000:
        raise LocalError("invalid bundled news fixture")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or set(value) != {"schema_version", "synthetic", "sources", "reports"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["synthetic"] is not True or not isinstance(value["sources"], list)
            or not isinstance(value["reports"], list) or len(value["reports"]) > MAX_REPORTS):
        raise LocalError("only bounded bundled synthetic feeds are supported")
    descriptors = [source_info(item) for item in value["sources"]]
    if not 1 <= len(descriptors) <= 8 or len({item["id"] for item in descriptors}) != len(descriptors):
        raise LocalError("source IDs must be unique and bounded")
    if any(not isinstance(row, dict) or row.get("source_id") not in {item["id"] for item in descriptors}
           for row in value["reports"]):
        raise LocalError("bundled report has no registered source")
    return descriptors, [SyntheticSource(item["id"], [r for r in value["reports"] if r["source_id"] == item["id"]])
                         for item in descriptors]


def preview_news(descriptors, adapters, at=REFERENCE_AT, explicit_interests=None):
    """No storage, network, account access, inferred profile or policy mutation."""
    at = timestamp(at)
    chosen = interests([] if explicit_interests is None else explicit_interests)
    if not isinstance(descriptors, list) or not 1 <= len(descriptors) <= 8:
        raise LocalError("news requires one to eight source descriptors")
    sources = [source_info(item) for item in descriptors]
    by_id = {item["id"]: item for item in sources}
    if len(by_id) != len(sources) or not isinstance(adapters, list) or not 1 <= len(adapters) <= 8:
        raise LocalError("news sources must be unique and bounded")
    adapter_ids = [identifier(adapter.id) for adapter in adapters]
    if len(set(adapter_ids)) != len(adapter_ids) or set(adapter_ids) != set(by_id):
        raise LocalError("adapter IDs must match the explicit source registry")
    reports, diagnostics, counts = [], [], {"invalid": 0, "future": 0, "stale": 0, "duplicate": 0, "conflict": 0}
    for adapter in adapters:
        try:
            rows = adapter.collect()
            if not isinstance(rows, list) or len(rows) > MAX_REPORTS:
                raise LocalError("source output exceeds bounds")
        except Exception:
            diagnostics.append({"source_id": adapter.id, "status": "unavailable"})
            continue  # Never echo exception messages or untrusted payloads.
        diagnostics.append({"source_id": adapter.id, "status": "loaded_synthetic", "received": len(rows)})
        for row in rows:
            try:
                item = report(row, by_id)
                if item["source_id"] != adapter.id:
                    raise LocalError("source attribution mismatch")
            except (LocalError, ValueError, TypeError):
                counts["invalid"] += 1
                continue
            published = timestamp(item["published_at"])
            if published > at:
                counts["future"] += 1
            elif at - published > timedelta(days=7):
                counts["stale"] += 1
            else:
                reports.append(item)
    # IDs are local to a source. Conflicting repeated IDs are all withheld.
    unique, conflicted = {}, set()
    for item in reports:
        key = (item["source_id"], item["id"])
        if key in conflicted:
            counts["conflict"] += 1
        elif key in unique:
            if unique[key] == item:
                counts["duplicate"] += 1
            else:
                del unique[key]
                conflicted.add(key)
                counts["conflict"] += 2
        else:
            unique[key] = item
    grouped = {}
    for item in unique.values():
        grouped.setdefault(item["event_id"], []).append(item)
    lanes = {"major_public": [], "personal_relevant": [], "exploration": []}
    for event_id, items in grouped.items():
        if len({item["topic"] for item in items}) != 1:
            counts["conflict"] += len(items)
            continue
        items.sort(key=lambda x: (x["published_at"], x["source_id"], x["id"]), reverse=True)
        topic = items[0]["topic"]
        lane = "major_public" if any(item["major"] for item in items) else "personal_relevant" if topic in chosen else "exploration"
        chains = {by_id[item["source_id"]]["origin_chain_id"] for item in items}
        warnings = ["synthetic_only_not_fact_checked"]
        if len(chains) < 2:
            warnings.append("single_origin_chain")
        if any(item["event_time"] is None for item in items):
            warnings.append("event_time_unknown")
        if any(item["event_time"] and timestamp(item["event_time"]) > at for item in items):
            warnings.append("future_event_not_yet_occurred")
        if any(item["event_time"] and at - timestamp(item["event_time"]) > timedelta(days=7) for item in items):
            warnings.append("old_event_recent_reporting")
        if len({item["event_time"] for item in items if item["event_time"]}) > 1:
            warnings.append("event_time_disagreement")
        lanes[lane].append({"event_id": event_id, "topic": topic, "title": items[0]["title"],
                            "lane": lane, "why": {"major_public": "major_flag_independent_of_interests",
                            "personal_relevant": "explicit_topic_for_this_preview", "exploration": "outside_explicit_topics"}[lane],
                            "confidence": "unassessed_synthetic", "origin_chain_count": len(chains),
                            "warnings": warnings, "reports": items})
    for values in lanes.values():
        values.sort(key=lambda x: (x["reports"][0]["published_at"], x["event_id"]), reverse=True)
    omitted = {"personal_relevant": max(0, len(lanes["personal_relevant"]) - 3),
               "exploration": max(0, len(lanes["exploration"]) - 2)}
    lanes["personal_relevant"] = lanes["personal_relevant"][:3]
    lanes["exploration"] = lanes["exploration"][:2]
    coverage = {topic: {"major_events": sum(item["topic"] == topic for item in lanes["major_public"]),
                        "status": "synthetic_candidates_only" if any(item["topic"] == topic for item in lanes["major_public"])
                        else "no_eligible_major_candidate"} for topic in TOPICS}
    return {"mode": "synthetic_preview", "policy_version": POLICY_VERSION, "as_of": at.isoformat(),
            "reference_at": REFERENCE_AT, "window_days": 7, "sources": sources, "source_status": diagnostics,
            "coverage": coverage, "lanes": lanes, "filtered_reports": counts, "omitted_events": omitted,
            "explicit_interests": chosen, "profile_saved": False, "network_enabled": False,
            "persisted": False, "delivery_enabled": False, "live_coverage_verified": False}


def bundled_preview(project, at=REFERENCE_AT, explicit_interests=None):
    return preview_news(*bundled_sources(project), at=at, explicit_interests=explicit_interests)
