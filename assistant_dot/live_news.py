"""Manual fixed-source public RSS reader. No accounts, storage or article fetches."""

from datetime import timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from .plans import timestamp
from .process import bounded_process, ProcessFailure
from .news_sources import FEEDS, source_catalog
from concurrent.futures import ThreadPoolExecutor
from .storage import LocalError, now


MAX_BYTES = 524288
TOPICS = ("politics", "economics", "technology")
TAG_TOPICS = {"politics": "politics", "governance": "politics", "elections": "politics",
              "international relations": "politics", "war & conflict": "politics",
              "economics & business": "economics", "technology": "technology", "science": "technology"}


class PlainTitle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_title(value):
    parser = PlainTitle()
    parser.feed(value)
    title = " ".join("".join(parser.parts).split())
    title = "".join(c for c in title if ord(c) >= 32 and ord(c) != 127)
    if not title or len(title) > 500:
        raise ValueError("invalid title")
    return title


def article_url(value, feed):
    url = urlsplit(value)
    if (len(value) > 2000 or url.scheme != "https" or url.hostname not in feed["hosts"]
            or url.netloc != url.hostname or url.username or url.password or url.query or url.fragment
            or "\\" in value or any(ord(c) <= 32 for c in value)):
        raise ValueError("article URL is outside the source allowlist")
    return value


def parse_feed(payload, feed, as_of, retrieved_at):
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise LocalError("feed exceeds byte limit")
    try:
        document = payload.decode("utf-8-sig")
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", document, re.I):
            raise ValueError()
        root = ET.fromstring(document)
        if len(list(root.iter())) > 5000:
            raise ValueError()
        if root.tag == "rss":
            entries = root.findall("./channel/item")
            atom = False
        elif root.tag == "{http://www.w3.org/2005/Atom}feed":
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")
            atom = True
        else:
            raise ValueError()
    except (UnicodeError, ET.ParseError, ValueError):
        raise LocalError("feed is not supported safe UTF-8 RSS or Atom") from None
    result, filtered, seen = [], {"invalid": 0, "future": 0, "stale": 0, "duplicate": 0, "overflow": 0, "out_of_scope": 0}, set()
    for entry in entries:
        try:
            if atom:
                ns = "{http://www.w3.org/2005/Atom}"
                title = "".join(entry.find(ns + "title").itertext())
                link = next(e.get("href") for e in entry.findall(ns + "link") if e.get("rel", "alternate") == "alternate")
                pub, update = entry.findtext(ns + "published"), entry.findtext(ns + "updated")
                published = timestamp(pub) if pub else None
                updated = timestamp(update) if update else None
                reported = published or updated
                if reported is None:
                    raise ValueError()
                date_basis = "atom_published" if published else "atom_updated_only"
                author = entry.findtext(ns + "author/" + ns + "name")
            else:
                title, link = entry.findtext("title"), entry.findtext("link")
                raw_date = entry.findtext("pubDate")
                if isinstance(raw_date, str):
                    raw_date = re.sub(r" (CET|CEST)$", lambda match: " +0100" if match[1] == "CET" else " +0200", raw_date)
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None:
                    raise ValueError()
                published = timestamp(published.isoformat())
                reported, updated, date_basis = published, None, "rss_pubdate"
                author = entry.findtext("{http://purl.org/dc/elements/1.1/}creator") or entry.findtext("author")
            title, link = clean_title(title), article_url(link, feed)
            author = clean_title(author) if author else None
            if author and len(author) > 200:
                raise ValueError()
            topics = [feed["topic"]]
            if feed.get("topic_mode") == "publisher_tags":
                tags = [item.text.strip().casefold() for item in entry.findall("category") if item.text]
                topics = [topic for topic in TOPICS if topic in {TAG_TOPICS[tag] for tag in tags if tag in TAG_TOPICS}]
                if not topics:
                    filtered["out_of_scope"] += 1
                    continue
        except (ValueError, TypeError, AttributeError, StopIteration, LocalError, OverflowError):
            filtered["invalid"] += 1
            continue
        if reported > as_of:
            filtered["future"] += 1
        elif as_of - reported > timedelta(days=7):
            filtered["stale"] += 1
        elif link in seen:
            filtered["duplicate"] += 1
        else:
            seen.add(link)
            result.append({"id": sha256(link.encode()).hexdigest()[:24], "title": title, "url": link,
                           "topic": topics[0], "topics": topics, "topic_basis": "publisher_category_tags" if feed.get("topic_mode") else "source_registry",
                           "source_id": feed["id"], "source_name": feed["name"], "author": author,
                           "source_kind": feed["kind"], "publisher": feed["publisher"], "editorial_base": feed["editorial_base"],
                           "terms_url": feed["terms_url"], "usage": feed["usage"], "underlying_origin": "unverified",
                           "published_at": published.isoformat() if published else None,
                           "updated_at": updated.isoformat() if updated else None, "reported_at": reported.isoformat(), "date_basis": date_basis,
                           "event_time": None, "retrieved_at": retrieved_at, "verification": "source_headline_not_fact_checked",
                           "major_status": "not_assessed"})
    result.sort(key=lambda item: (item["reported_at"], item["id"]), reverse=True)
    filtered["overflow"] = max(0, len(result) - 10)
    return result[:10], filtered


def fetch_feed(feed):
    if feed not in FEEDS:
        raise LocalError("only the fixed reviewed public feed registry may be fetched")
    # System curl uses its maintained TLS trust store. No -k, cookies, auth,
    # proxies, curlrc, redirects, arbitrary URLs or automatic article retrieval.
    return bounded_process(["/usr/bin/curl", "--disable", "--proxy", "", "--noproxy", "*", "--proto", "=https",
                            "--fail", "--silent", "--show-error", "--max-time", "12", "--connect-timeout", "5",
                            "--max-redirs", "0", "--max-filesize", str(MAX_BYTES),
                            "--header", "Accept-Encoding: identity", "--user-agent", "personal-assistant-dot/manual-reader",
                            "--url", feed["url"]], timeout=14, limit=MAX_BYTES)


def collect_source(feed, transport, clock, as_of):
    info = {key: feed[key] for key in ("id", "name", "topic", "topics", "publisher", "kind", "editorial_base", "language", "url", "reference", "terms_url", "usage")}
    try:
        payload = transport(feed)
    except Exception as error:
        reason = "transport_failed"
        if isinstance(error, ProcessFailure):
            reason = {22: "http_error", 28: "timeout", 60: "tls_verification_failed", 63: "response_too_large",
                      6: "dns_failed", 7: "connection_failed"}.get(error.returncode, error.category)
        info.update(status="unavailable", candidates=0, error=reason, retrieved_at=None)
        return [], info
    retrieved = timestamp(clock()).isoformat()
    try:
        items, filtered = parse_feed(payload, feed, as_of, retrieved)
        info.update(status="fetched", candidates=len(items), filtered=filtered, retrieved_at=retrieved)
        return items, info
    except (LocalError, ValueError, TypeError):
        info.update(status="unavailable", candidates=0, error="unsupported_or_unsafe_feed", retrieved_at=retrieved)
        return [], info


def coverage_summary(articles, sources):
    coverage = {}
    for topic in TOPICS:
        items = [item for item in articles if topic in item["topics"]]
        selected = [source for source in sources if topic in source["topics"]]
        primary = {item["publisher"] for item in items if item["source_kind"] == "institutional_primary"}
        reporting = {item["publisher"] for item in items if item["source_kind"] == "editorial_reporting"}
        gaps = []
        if not selected:
            gaps.append("no_source_selected")
        if any(source["status"] != "fetched" for source in selected):
            gaps.append("source_unavailable")
        if not items:
            gaps.append("no_recent_candidates")
        if not primary:
            gaps.append("no_primary_candidates")
        if not reporting:
            gaps.append("no_editorial_candidates")
        if len(reporting) < 2:
            gaps.append("fewer_than_two_editorial_publishers")
        coverage[topic] = {"candidates": len(items), "primary_publishers": len(primary), "editorial_publishers": len(reporting),
                           "selected_sources": len(selected), "fetched_sources": sum(s["status"] == "fetched" for s in selected),
                           "gaps": gaps, "major_status": "not_assessed", "coverage_verified": False, "independence_verified": False}
    return coverage


def fetch_public_news(source_ids=None, transport=fetch_feed, clock=now):
    chosen = [feed["id"] for feed in FEEDS] if source_ids is None else source_ids
    if (not isinstance(chosen, list) or not 1 <= len(chosen) <= len(FEEDS)
            or any(not isinstance(item, str) or item not in {f["id"] for f in FEEDS} for item in chosen)
            or len(set(chosen)) != len(chosen)):
        raise LocalError("select unique source IDs from the fixed public registry")
    as_of = timestamp(clock())
    articles, sources, groups = [], [], {}
    for feed in FEEDS:
        if feed["id"] not in chosen:
            continue
        groups.setdefault(feed["publisher"], []).append(feed)
    def collect_group(feeds):
        return [collect_source(feed, transport, clock, as_of) for feed in feeds]
    # At most three publishers concurrently; feeds from one publisher are serial.
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(collect_group, groups.values()))
    by_id = {info["id"]: (items, info) for group in results for items, info in group}
    for feed in FEEDS:
        if feed["id"] in by_id:
            items, info = by_id[feed["id"]]
            articles.extend(items)
            sources.append(info)
    coverage = coverage_summary(articles, sources)
    return {"mode": "manual_public_feeds", "as_of": as_of.isoformat(), "window_days": 7, "articles": articles,
            "sources": sources, "coverage": coverage, "network_scope": "fixed_public_feeds_only",
            "catalog": source_catalog(), "persisted": False, "delivery_enabled": False, "personalization_applied": False,
            "limitations": ["limited_editorial_publishers", "english_only", "regional_primary_gaps", "no_independent_fact_check",
                            "major_news_not_assessed", "event_dates_not_extracted", "no_cross_source_event_clustering"]}
