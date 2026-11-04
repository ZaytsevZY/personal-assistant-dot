"""No-network acceptance for the real-feed parser and bounded transport."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from assistant_dot.live_news import FEEDS, MAX_BYTES, fetch_feed, fetch_public_news, parse_feed
from assistant_dot.plans import timestamp
from assistant_dot.process import bounded_process
from assistant_dot.storage import LocalError

AT = "2026-01-15T12:00:00Z"


def rss(feed, title="Synthetic headline", date="Thu, 15 Jan 2026 09:00:00 GMT", link=None):
    link = link or "https://" + feed["hosts"][0] + "/synthetic-test"
    return ("<rss><channel><item><title>" + title + "</title><link>" + link + "</link><pubDate>" + date + "</pubDate></item></channel></rss>").encode()


def rejected(call):
    try:
        call()
    except LocalError:
        return
    raise AssertionError("unsafe input accepted")


def main():
    feed = FEEDS[0]
    articles, counts = parse_feed(rss(feed, "&lt;b&gt;Synthetic&lt;/b&gt; headline"), feed, timestamp(AT), AT)
    assert articles[0]["title"] == "Synthetic headline" and articles[0]["event_time"] is None
    assert articles[0]["major_status"] == "not_assessed" and articles[0]["retrieved_at"] == AT
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Synthetic atom</title><link href="https://' + feed["hosts"][0] + '/synthetic-atom"/><published>2026-01-15T09:00:00Z</published></entry></feed>').encode()
    assert len(parse_feed(atom, feed, timestamp(AT), AT)[0]) == 1
    for bad in [b'<!DOCTYPE rss [<!ENTITY a "unsafe">]><rss/>', b'<rss>'.decode().encode('utf-16'), b'<html/>', b'x'*(MAX_BYTES+1)]:
        rejected(lambda: parse_feed(bad, feed, timestamp(AT), AT))
    print("PASS: safe bounded RSS/Atom parsing, attributed headline and distinct unknown event date")

    userinfo_attack = "https://www.ungeneva.org" + chr(64) + "untrusted.invalid/x"
    for link in ["http://127.0.0.1/x", "https://untrusted.invalid/x", userinfo_attack, "javascript:unsafe()", "https://www.ungeneva.org:444/x"]:
        assert parse_feed(rss(feed, link=link), feed, timestamp(AT), AT)[1]["invalid"] == 1
    assert parse_feed(rss(feed, date="Thu, 22 Jan 2026 09:00:00 GMT"), feed, timestamp(AT), AT)[1]["future"] == 1
    assert parse_feed(rss(feed, date="Thu, 01 Jan 2026 09:00:00 GMT"), feed, timestamp(AT), AT)[1]["stale"] == 1
    assert parse_feed(rss(feed, date="unknown"), feed, timestamp(AT), AT)[1]["invalid"] == 1
    assert len(parse_feed(rss(feed, date="Thu, 15 Jan 2026 10:00:00 CET"), feed, timestamp(AT), AT)[0]) == 1
    assert len(parse_feed(rss(feed, date="Thu, 15 Jan 2026 10:00:00 CEST"), feed, timestamp(AT), AT)[0]) == 1
    duplicate=rss(feed).replace(b'</channel>',rss(feed).split(b'<channel>')[1].split(b'</channel>')[0]+b'</channel>')
    assert parse_feed(duplicate, feed, timestamp(AT), AT)[1]["duplicate"] == 1
    print("PASS: article URL boundaries, date failures, freshness and duplicate links")

    calls=[]
    def transport(source):
        calls.append(source["id"])
        if source["id"] == "fed":
            raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")
        return rss(source)
    result=fetch_public_news(transport=transport,clock=lambda:AT)
    assert len(result["articles"]) == 2 and len(calls) == 3
    assert result["sources"][1]["status"] == "unavailable"
    assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(result)
    assert all(c["coverage_verified"] is False and c["major_status"] == "not_assessed" for c in result["coverage"].values())
    rejected(lambda:fetch_public_news(["https://untrusted.invalid/"]))
    rejected(lambda:fetch_public_news([["fed"]]))
    with patch("assistant_dot.live_news.bounded_process",return_value=b"synthetic") as mocked:
        fetch_feed(FEEDS[0])
        argv=mocked.call_args.args[0]
        assert "--disable" in argv and "--max-filesize" in argv and "--max-time" in argv
        assert "--insecure" not in argv and "-k" not in argv and "--location" not in argv
        assert argv[-1] == FEEDS[0]["url"]
        rejected(lambda:fetch_feed(dict(FEEDS[0],url="https://untrusted.invalid/")))
    print("PASS: source isolation, truthful partial coverage and fixed verified-TLS transport arguments")

    assert bounded_process([sys.executable,"-c","print('synthetic')"],limit=100).strip() == b"synthetic"
    rejected(lambda:bounded_process([sys.executable,"-c","print('x'*1000)"],limit=50))
    rejected(lambda:bounded_process([sys.executable,"-c","import time; time.sleep(2)"],timeout=.05))
    rejected(lambda:bounded_process([sys.executable,"-c","raise RuntimeError('SYNTHETIC_PRIVATE_ERROR')"]))
    print("PASS: trusted process timeout, output cap, cleanup and sanitized failures")
    print("PASS: 4 public-feed acceptance groups; no real network or accounts")


if __name__ == "__main__":
    main()
