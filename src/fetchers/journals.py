import html
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

logger = logging.getLogger(__name__)

_RSS_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
}

# (source_label, issn, display_name)
_CROSSREF_JOURNALS: list[tuple[str, str, str]] = [
    ("radiology", "0033-8419", "Radiology"),
    ("radiology_ai", "2638-6100", "Radiology: Artificial Intelligence"),
]

_SPRINGER_FEEDS: list[tuple[str, str]] = [
    ("european_radiology", "https://link.springer.com/search.rss?facet-journal-id=330&channel=journals"),
]


def _strip_markup(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def _date_parts_to_iso(date_parts: list[list[int]]) -> str:
    parts = date_parts[0] if date_parts else []
    year = parts[0] if len(parts) >= 1 else date.today().year
    month = parts[1] if len(parts) >= 2 else 1
    day = parts[2] if len(parts) >= 3 else 1
    return date(year, month, day).isoformat()


def _parse_crossref_item(item: dict, source_label: str, journal_name: str) -> dict | None:
    doi = item.get("DOI", "").lower().strip()
    if not doi:
        return None

    titles = item.get("title", [])
    title = _strip_markup(titles[0]) if titles else ""

    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in item.get("author", [])
        if a.get("given") or a.get("family")
    ]

    container = item.get("container-title", [])
    journal = container[0] if container else journal_name

    pub_date = date.today().isoformat()
    for field in ("published-online", "published", "published-print"):
        if field in item:
            pub_date = _date_parts_to_iso(item[field].get("date-parts", []))
            break

    abstract_raw = item.get("abstract", "")
    abstract = _strip_markup(abstract_raw) if abstract_raw else None

    return {
        "doi": doi,
        "title": title,
        "authors": authors,
        "corresponding_author": authors[-1] if authors else None,
        "journal": journal,
        "pub_date": pub_date,
        "abstract": abstract,
        "source": source_label,
    }


def _fetch_crossref(issn: str, email: str, source_label: str, journal_name: str, rows: int = 50) -> list[dict]:
    params = urllib.parse.urlencode({"sort": "published", "order": "desc", "rows": rows, "mailto": email})
    url = f"https://api.crossref.org/journals/{issn}/works?{params}"
    logger.info("Fetching Crossref: %s", journal_name)
    req = urllib.request.Request(url, headers={"User-Agent": f"IBD-Digest/1.0 (mailto:{email})"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    items = data.get("message", {}).get("items", [])
    papers = [p for item in items if (p := _parse_crossref_item(item, source_label, journal_name))]
    logger.info("Parsed %d papers from %s", len(papers), journal_name)
    return papers


def _parse_rss_item(item: ET.Element, source_label: str) -> dict | None:
    doi: str | None = item.findtext("prism:doi", namespaces=_RSS_NS)

    if not doi:
        dc_id = item.findtext("dc:identifier", namespaces=_RSS_NS) or ""
        if dc_id.lower().startswith("doi:"):
            doi = dc_id[4:]

    if not doi:
        link = item.findtext("link") or ""
        m = re.search(r"10\.\d{4,}/\S+", link)
        if m:
            doi = m.group()

    if not doi:
        return None

    title = item.findtext("title", "").strip()
    creator = item.findtext("dc:creator", namespaces=_RSS_NS) or ""
    authors = [a.strip() for a in creator.split(";") if a.strip()]
    journal = item.findtext("prism:publicationName", namespaces=_RSS_NS) or source_label

    pub_date_str = item.findtext("pubDate") or ""
    pub_date = date.today().isoformat()
    if pub_date_str:
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                pub_date = datetime.strptime(pub_date_str.strip(), fmt).date().isoformat()
                break
            except ValueError:
                continue

    description = item.findtext("description") or ""
    abstract = _strip_markup(description) or None

    return {
        "doi": doi.lower().strip(),
        "title": title,
        "authors": authors,
        "corresponding_author": authors[-1] if authors else None,
        "journal": journal,
        "pub_date": pub_date,
        "abstract": abstract,
        "source": source_label,
    }


def _fetch_springer_rss(feed_url: str, source_label: str) -> list[dict]:
    logger.info("Fetching Springer RSS: %s", source_label)
    req = urllib.request.Request(feed_url, headers={"User-Agent": "IBD-Digest/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    papers = [p for item in root.findall(".//item") if (p := _parse_rss_item(item, source_label))]
    logger.info("Parsed %d papers from %s", len(papers), source_label)
    return papers


def fetch_all_journals(email: str) -> list[dict]:
    """Fetch from Radiology, Radiology AI (Crossref) and European Radiology (Springer RSS)."""
    papers: list[dict] = []
    for source_label, issn, journal_name in _CROSSREF_JOURNALS:
        papers.extend(_fetch_crossref(issn, email, source_label, journal_name))
    for source_label, feed_url in _SPRINGER_FEEDS:
        papers.extend(_fetch_springer_rss(feed_url, source_label))
    return papers
