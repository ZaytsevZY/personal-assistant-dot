"""Reviewed public reader registry, not a license for downstream redistribution."""
from copy import deepcopy

REVIEWED_AT = "2026-11-04"
FEEDS = (
    {"id": "un-geneva", "name": "UN Geneva", "topic": "politics", "topics": ["politics"],
     "url": "https://www.ungeneva.org/en/news-media/press-releases-list/rss.xml",
     "hosts": ("www.ungeneva.org",), "reference": "https://www.ungeneva.org/en/news-media/rss",
     "publisher": "un", "kind": "institutional_primary", "editorial_base": "international_institution",
     "language": "en", "terms_url": "https://www.un.org/en/about-us/terms-of-use",
     "usage": "personal_reader_no_redistribution", "perspective": "UN institutional statements"},
    {"id": "fed", "name": "Federal Reserve Board", "topic": "economics", "topics": ["economics"],
     "url": "https://www.federalreserve.gov/feeds/press_all.xml",
     "hosts": ("www.federalreserve.gov", "federalreserve.gov"), "reference": "https://www.federalreserve.gov/feeds/feeds.htm",
     "publisher": "fed", "kind": "institutional_primary", "editorial_base": "united_states",
     "language": "en", "terms_url": "https://www.federalreserve.gov/website-linking-policies.htm",
     "usage": "official_rss_reader_attribution", "perspective": "US central bank statements"},
    {"id": "nasa", "name": "NASA", "topic": "technology", "topics": ["technology"],
     "url": "https://www.nasa.gov/news-release/feed/",
     "hosts": ("www.nasa.gov", "science.nasa.gov"), "reference": "https://www.nasa.gov/rss-feeds/",
     "publisher": "nasa", "kind": "institutional_primary", "editorial_base": "united_states",
     "language": "en", "terms_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
     "usage": "official_rss_reader_no_images", "perspective": "US space agency statements"},
    {"id": "ecb", "name": "European Central Bank", "topic": "economics", "topics": ["economics"],
     "url": "https://www.ecb.europa.eu/rss/press.html", "hosts": ("www.ecb.europa.eu",),
     "reference": "https://www.ecb.europa.eu/home/html/rss.en.html",
     "publisher": "ecb", "kind": "institutional_primary", "editorial_base": "european_union",
     "language": "en", "terms_url": "https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html",
     "usage": "attribution_no_authored_paper_republication", "perspective": "Euro area central bank statements"},
    {"id": "global-voices", "name": "Global Voices", "topic": "politics", "topics": ["politics", "economics", "technology"],
     "url": "https://globalvoices.org/feed/", "hosts": ("globalvoices.org",),
     "reference": "https://globalvoices.org/feeds/", "publisher": "global-voices",
     "kind": "editorial_reporting", "editorial_base": "global_contributor_network",
     "language": "en", "terms_url": "https://globalvoices.org/about/global-voices-attribution-policy/",
     "usage": "cc_by_attribution_original_author_link_exceptions_apply",
     "perspective": "Nonprofit citizen-media reporting and commentary; origin chains unverified",
     "topic_mode": "publisher_tags"},
)

# Not executable sources: endpoint/terms review does not imply local availability.
DEFERRED = (
    {"id": "le-monde", "reason": "local_fetch_unavailable", "reference": "https://www.lemonde.fr/en/about-us/article/2026/03/27/le-monde-rss-feeds_6751860_115.html",
     "terms_note": "personal_nonprofessional_noncollective_reader_only"},
    {"id": "cna", "reason": "local_fetch_unavailable", "reference": "https://www.channelnewsasia.com/rss/rssterms",
     "terms_note": "personal_noncommercial_no_modification_or_redistribution_direct_links"},
    {"id": "cna-taiwan", "reason": "local_fetch_timeout", "reference": "https://www.cna.com.tw/about/rss.aspx",
     "terms_note": "personal_noncommercial_credit_central_news_agency_keep_dispatch_attribution_no_full_text"},
    {"id": "the-register", "reason": "human_verification_page", "reference": "https://www.theregister.com/design/page/feeds",
     "terms_note": "personal_noncommercial_reader_only"},
    {"id": "aljazeera", "reason": "automated_access_terms_need_clarification", "reference": "https://terms.aljazeera.net/",
     "terms_note": "do_not_assume_rss_overrides_automation_restrictions"},
    {"id": "arxiv", "reason": "cross_process_rate_control_not_implemented", "reference": "https://info.arxiv.org/help/api/tou.html",
     "terms_note": "metadata_cc0_papers_separate_one_connection_one_request_per_three_seconds"},
)


def source_catalog():
    fields = ("id", "name", "topics", "publisher", "kind", "editorial_base", "language", "reference", "terms_url", "usage", "perspective")
    return deepcopy({"reviewed_at": REVIEWED_AT, "sources": [{key: feed[key] for key in fields} for feed in FEEDS],
                     "deferred": list(DEFERRED), "usage_scope": "personal_local_reader", "review_is_not_availability_guarantee": True})
