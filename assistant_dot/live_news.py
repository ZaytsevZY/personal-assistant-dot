"""Manual fixed-source public RSS reader. No accounts, storage or article fetches."""

from datetime import timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from .plans import timestamp
from .process import bounded_process
from .storage import LocalError, now


FEEDS = (
    {"id": "un-geneva", "name": "UN Geneva", "topic": "politics",
     "url": "https://www.ungeneva.org/en/news-media/press-releases-list/rss.xml",
     "hosts": ("www.ungeneva.org",), "reference": "https://www.ungeneva.org/en/news-media/rss"},
    {"id": "fed", "name": "Federal Reserve Board", "topic": "economics",
     "url": "https://www.federalreserve.gov/feeds/press_all.xml",
     "hosts": ("www.federalreserve.gov", "federalreserve.gov"), "reference": "https://www.federalreserve.gov/feeds/feeds.htm"},
    {"id": "nasa", "name": "NASA", "topic": "technology",
     "url": "https://www.nasa.gov/news-release/feed/",
     "hosts": ("www.nasa.gov", "science.nasa.gov"), "reference": "https://www.nasa.gov/rss-feeds/"},
)
MAX_BYTES = 524288


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
    result, filtered, seen = [], {"invalid": 0, "future": 0, "stale": 0, "duplicate": 0, "overflow": 0}, set()
    for entry in entries:
        try:
            if atom:
                ns = "{http://www.w3.org/2005/Atom}"
                title = "".join(entry.find(ns + "title").itertext())
                link = next(e.get("href") for e in entry.findall(ns + "link") if e.get("rel", "alternate") == "alternate")
                raw_date = entry.findtext(ns + "published") or entry.findtext(ns + "updated")
                published = timestamp(raw_date)
            else:
                title, link = entry.findtext("title"), entry.findtext("link")
                raw_date = entry.findtext("pubDate")
                if isinstance(raw_date, str):
                    raw_date = re.sub(r" (CET|CEST)$", lambda match: " +0100" if match[1] == "CET" else " +0200", raw_date)
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None:
                    raise ValueError()
                published = timestamp(published.isoformat())
            title, link = clean_title(title), article_url(link, feed)
        except (ValueError, TypeError, AttributeError, StopIteration, LocalError, OverflowError):
            filtered["invalid"] += 1
            continue
        if published > as_of:
            filtered["future"] += 1
        elif as_of - published > timedelta(days=7):
            filtered["stale"] += 1
        elif link in seen:
            filtered["duplicate"] += 1
        else:
            seen.add(link)
            result.append({"id": sha256(link.encode()).hexdigest()[:24], "title": title, "url": link,
                           "topic": feed["topic"], "source_id": feed["id"], "source_name": feed["name"],
                           "source_kind": "institutional_primary", "published_at": published.isoformat(),
                           "event_time": None, "retrieved_at": retrieved_at, "verification": "source_headline_not_fact_checked",
                           "major_status": "not_assessed"})
    result.sort(key=lambda item: (item["published_at"], item["id"]), reverse=True)
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


def fetch_public_news(source_ids=None, transport=fetch_feed, clock=now):
    chosen = [feed["id"] for feed in FEEDS] if source_ids is None else source_ids
    if (not isinstance(chosen, list) or not 1 <= len(chosen) <= 3
            or any(not isinstance(item, str) or item not in {f["id"] for f in FEEDS} for item in chosen)
            or len(set(chosen)) != len(chosen)):
        raise LocalError("select one to three unique fixed public source IDs")
    as_of = timestamp(clock())
    articles, sources = [], []
    for feed in FEEDS:
        if feed["id"] not in chosen:
            continue
        info = {key: feed[key] for key in ("id", "name", "topic", "url", "reference")}
        try:
            payload = transport(feed)
            retrieved = timestamp(clock()).isoformat()
            items, filtered = parse_feed(payload, feed, as_of, retrieved)
            articles.extend(items)
            info.update(status="fetched", candidates=len(items), filtered=filtered, retrieved_at=retrieved)
        except Exception:
            info.update(status="unavailable", candidates=0, error="fetch_or_parse_failed", retrieved_at=None)
        sources.append(info)
    coverage = {topic: {"candidates": sum(a["topic"] == topic for a in articles), "major_status": "not_assessed",
                        "coverage_verified": False} for topic in ("politics", "economics", "technology")}
    return {"mode": "manual_public_feeds", "as_of": as_of.isoformat(), "window_days": 7, "articles": articles,
            "sources": sources, "coverage": coverage, "network_scope": "fixed_public_feeds_only",
            "persisted": False, "delivery_enabled": False, "personalization_applied": False,
            "limitations": ["institutional_sources_only", "no_independent_fact_check", "major_news_not_assessed",
                            "event_dates_not_extracted", "no_cross_source_event_clustering"]}
