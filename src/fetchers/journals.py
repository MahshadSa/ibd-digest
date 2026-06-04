import html
import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import date

logger = logging.getLogger(__name__)

# (source_label, issn, display_name)
_CROSSREF_JOURNALS: list[tuple[str, str, str]] = [
    ("radiology",              "0033-8419", "Radiology"),
    ("radiology_ai",           "2638-6100", "Radiology: Artificial Intelligence"),
    ("european_radiology",     "1432-1084", "European Radiology"),
    ("investigative_radiology","1536-0210", "Investigative Radiology"),
    ("jmri",                   "1522-2586", "Journal of Magnetic Resonance Imaging"),
    ("insights_imaging",       "1869-4101", "Insights into Imaging"),
    ("ajr",                    "1546-3141", "American Journal of Roentgenology"),
    ("abdominal_radiology",    "2366-0058", "Abdominal Radiology"),
    ("jcc",                    "1876-4479", "Journal of Crohn's and Colitis"),
    ("ibd",                    "1536-4844", "Inflammatory Bowel Diseases"),
    ("medical_image_analysis", "1361-8415", "Medical Image Analysis"),
    ("nature_medicine",        "1546-170X", "Nature Medicine"),
    ("npj_digital_medicine",   "2398-6352", "npj Digital Medicine"),
    ("lancet_digital_health",  "2589-7500", "The Lancet Digital Health"),
    ("apt",                    "1365-2036", "Alimentary Pharmacology & Therapeutics"),
    ("lancet_gi",              "2468-1253", "The Lancet Gastroenterology & Hepatology"),
    ("cgh",                    "1542-3565", "Clinical Gastroenterology and Hepatology"),
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


def fetch_all_journals(email: str) -> list[dict]:
    """Fetch recent papers from all journals in _CROSSREF_JOURNALS via Crossref."""
    papers: list[dict] = []
    for source_label, issn, journal_name in _CROSSREF_JOURNALS:
        papers.extend(_fetch_crossref(issn, email, source_label, journal_name))
    return papers
