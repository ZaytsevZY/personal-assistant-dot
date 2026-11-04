"""Synthetic news pipeline acceptance: coverage, provenance and safe failures."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.news import bundled_preview, bundled_sources, preview_news, REFERENCE_AT, SyntheticSource
from assistant_dot.storage import LocalError


def rejected(call):
    try:
        call()
    except LocalError:
        return
    raise AssertionError("unsafe news input was accepted")


def main():
    descriptors, adapters = bundled_sources(PROJECT)
    fixture = json.loads((PROJECT / "templates/news-feed.example.json").read_text())

    def run(rows, **kwargs):
        return preview_news(descriptors, [SyntheticSource(s["id"], [r for r in rows if r["source_id"] == s["id"]])
                                          for s in descriptors], **kwargs)

    plain = bundled_preview(PROJECT)
    focused = bundled_preview(PROJECT, explicit_interests=["technology"])
    assert plain["lanes"]["major_public"] == focused["lanes"]["major_public"]
    assert all(value["major_events"] == 1 for value in plain["coverage"].values())
    assert plain["lanes"]["personal_relevant"] == []
    assert focused["lanes"]["personal_relevant"][0]["topic"] == "technology"
    assert focused["lanes"]["exploration"][0]["topic"] == "economics"
    assert focused["profile_saved"] is focused["persisted"] is focused["network_enabled"] is False
    assert focused["live_coverage_verified"] is False
    rejected(lambda: bundled_preview(PROJECT, explicit_interests=["technology", "technology"]))
    rejected(lambda: bundled_preview(PROJECT, explicit_interests=["inferred-political-identity"]))
    rejected(lambda: bundled_preview(PROJECT, explicit_interests="technology"))
    print("PASS: protected major coverage, explicit ephemeral interests and no inferred profile")

    technology = next(e for e in plain["lanes"]["major_public"] if e["topic"] == "technology")
    politics = next(e for e in plain["lanes"]["major_public"] if e["topic"] == "politics")
    assert len(technology["reports"]) == 2 and technology["origin_chain_count"] == 1
    assert politics["origin_chain_count"] == 2
    assert "single_origin_chain" in technology["warnings"] and "event_time_unknown" in technology["warnings"]
    assert technology["confidence"] == "unassessed_synthetic"
    assert technology["reports"][0]["event_time"] is None
    assert {s["kind"] for r in politics["reports"] for s in r["statements"]} == {"reported_fact", "commentary"}
    duplicate = run(fixture["reports"] + [fixture["reports"][0]])
    assert duplicate["filtered_reports"]["duplicate"] == 1
    assert duplicate["lanes"] == plain["lanes"]
    conflicting = deepcopy(fixture["reports"][0]); conflicting["title"] = "Synthetic conflict"
    result = run(fixture["reports"] + [conflicting])
    assert result["filtered_reports"]["conflict"] == 2
    assert next(e for e in result["lanes"]["major_public"] if e["topic"] == "politics")["origin_chain_count"] == 1
    print("PASS: event grouping, syndicated origin chains, statement attribution and conflicting IDs")

    old = bundled_preview(PROJECT, at="2026-02-15T12:00:00Z")
    future = bundled_preview(PROJECT, at="2026-01-14T12:00:00Z")
    assert all(c["status"] == "no_eligible_major_candidate" for c in old["coverage"].values())
    assert old["filtered_reports"]["stale"] == 7 and future["filtered_reports"]["future"] == 7
    rows = deepcopy(fixture["reports"])
    rows[0]["event_time"] = "2026-01-16T08:00:00Z"
    rows[0]["correction_of"] = "synthetic-prior-report"
    event = next(e for e in run(rows)["lanes"]["major_public"] if e["topic"] == "politics")
    assert "future_event_not_yet_occurred" in event["warnings"] and "event_time_disagreement" in event["warnings"]
    assert any(r["correction_of"] == "synthetic-prior-report" for r in event["reports"])
    rows[0]["event_time"] = "2025-12-01T08:00:00Z"
    event = next(e for e in run(rows)["lanes"]["major_public"] if e["topic"] == "politics")
    assert "old_event_recent_reporting" in event["warnings"]
    assert all(r["retrieved_at"] is None for r in event["reports"])
    rejected(lambda: bundled_preview(PROJECT, at="2026-01-15T12:00:00"))
    print("PASS: event/publication separation, bounded freshness, missing dates, future events and correction references")

    class Broken:
        id = "synthetic-bulletin"

        def collect(self):
            raise RuntimeError("SYNTHETIC_PRIVATE_ERROR_DO_NOT_ECHO")

    broken = preview_news(descriptors, [Broken(), *adapters[1:]])
    assert broken["coverage"]["economics"]["major_events"] == 0
    assert broken["source_status"][0]["status"] == "unavailable"
    assert "SYNTHETIC_PRIVATE_ERROR_DO_NOT_ECHO" not in json.dumps(broken)
    invalid = deepcopy(fixture["reports"])
    invalid[0]["statements"][0]["kind"] = "verified_fact"
    invalid[2]["permissions"] = {"enable_network": True}
    result = run(invalid)
    assert result["filtered_reports"]["invalid"] == 2
    spoofed = preview_news(descriptors, [SyntheticSource("synthetic-bulletin", [fixture["reports"][1]]), *adapters[1:]])
    assert spoofed["filtered_reports"]["invalid"] == 1
    source = deepcopy(descriptors); source[0]["url"] = "http://127.0.0.1/private"
    rejected(lambda: preview_news(source, adapters))
    rejected(lambda: preview_news(descriptors, adapters + [adapters[0]]))
    oversized = preview_news(descriptors, [SyntheticSource(descriptors[0]["id"], [fixture["reports"][0]] * 51), *adapters[1:]])
    assert oversized["source_status"][0]["status"] == "unavailable"
    assert oversized["coverage"]["economics"]["major_events"] == 0
    print("PASS: source failure isolation, strict bounded payloads, URL boundaries and truthful coverage gaps")

    rows = deepcopy(fixture["reports"])
    base = deepcopy(rows[-2])
    for n in range(7):
        item = deepcopy(base); item["id"] = "synthetic-extra-" + str(n); item["event_id"] = item["id"]
        rows.append(item)
    capped = run(rows, explicit_interests=["technology"])
    assert len(capped["lanes"]["personal_relevant"]) == 3
    assert capped["omitted_events"]["personal_relevant"] == 5
    assert capped["lanes"]["major_public"] == plain["lanes"]["major_public"]
    command = subprocess.run([sys.executable, "-B", "-m", "assistant_dot", "/news-preview", "--interests", "technology"],
                             cwd=PROJECT, text=True, capture_output=True, check=True)
    assert json.loads(command.stdout) == focused
    assert REFERENCE_AT in json.loads(command.stdout)["reference_at"]
    print("PASS: bounded optional recommendations, major lane protection and CLI parity without private storage")
    print("PASS: 5 news acceptance groups; synthetic fixtures only")


if __name__ == "__main__":
    main()
