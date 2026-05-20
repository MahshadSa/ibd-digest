import html
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.db import get_connection, migrate_embedding_columns
from src.ranking.embed import embed, load_model

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _strip_markup(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def _fetch_pubmed_by_doi(doi: str, api_key: str, email: str) -> dict[str, str] | None:
    params = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "term": f"{doi}[DOI]",
            "retmode": "json",
            "retmax": 1,
            "api_key": api_key,
            "email": email,
        }
    )
    try:
        with urllib.request.urlopen(
            f"{EUTILS_BASE}/esearch.fcgi?{params}", timeout=30
        ) as resp:
            data = json.loads(resp.read())
        pmids = data["esearchresult"]["idlist"]
        if not pmids:
            return None

        params2 = urllib.parse.urlencode(
            {
                "db": "pubmed",
                "id": pmids[0],
                "rettype": "xml",
                "retmode": "xml",
                "api_key": api_key,
                "email": email,
            }
        )
        with urllib.request.urlopen(
            f"{EUTILS_BASE}/efetch.fcgi?{params2}", timeout=30
        ) as resp:
            root = ET.fromstring(resp.read())

        art = root.find(".//Article")
        if art is None:
            return None

        title_el = art.find("ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        abstract = ""
        abstract_el = art.find("Abstract")
        if abstract_el is not None:
            parts = []
            for text_el in abstract_el.findall("AbstractText"):
                label = text_el.get("Label")
                text = "".join(text_el.itertext()).strip()
                parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(parts)

        return {"title": title, "abstract": abstract}
    except Exception:
        return None


def _fetch_crossref_by_doi(doi: str, email: str) -> dict[str, str] | None:
    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.crossref.org/works/{encoded}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"IBD-Digest/1.0 (mailto:{email})"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        item = data.get("message", {})
        titles = item.get("title", [])
        title = _strip_markup(titles[0]) if titles else ""
        if not title:
            return None
        abstract = _strip_markup(item.get("abstract", ""))
        return {"title": title, "abstract": abstract}
    except Exception:
        return None


def fetch_doi_metadata(doi: str, api_key: str, email: str) -> dict[str, str] | None:
    """Return {title, abstract} for a DOI. PubMed first, Crossref fallback. None on failure."""
    result = _fetch_pubmed_by_doi(doi, api_key, email)
    if result is not None:
        return result
    logger.debug("PubMed lookup failed for %s, trying Crossref", doi)
    return _fetch_crossref_by_doi(doi, email)


def _write_note(doi: str, title: str, abstract: str, corpus_dir: str) -> None:
    slug = doi.replace("/", "_").replace(":", "_")
    path = Path(corpus_dir) / f"{slug}.md"
    body = abstract if abstract else "No abstract available."
    path.write_text(
        f"# {title}\n\nDOI: [{doi}](https://doi.org/{doi})\n\n## Abstract\n\n{body}\n",
        encoding="utf-8",
    )


def build_corpus(
    db_path: str,
    seed_file: str,
    corpus_dir: str,
    model_name: str,
    api_key: str,
    email: str,
) -> None:
    """Read seed DOIs, fetch metadata, embed, store in corpus table, write Markdown notes."""
    migrate_embedding_columns(db_path)

    raw_dois: list[str] = []
    with open(seed_file) as f:
        for line in f:
            doi = line.strip().lower()
            if doi:
                raw_dois.append(doi)
    seed_dois = list(dict.fromkeys(raw_dois))
    logger.info("Seed DOIs: %d unique from %d lines", len(seed_dois), len(raw_dois))

    conn = get_connection(db_path)
    done_dois = {
        row["doi"]
        for row in conn.execute(
            "SELECT doi FROM corpus WHERE embedding IS NOT NULL"
        ).fetchall()
    }
    pending = [d for d in seed_dois if d not in done_dois]
    logger.info(
        "Already embedded: %d, pending: %d", len(done_dois), len(pending)
    )

    if not pending:
        conn.close()
        return

    tokenizer, model = load_model(model_name)

    fetched: list[tuple[str, str, str]] = []
    failed: list[str] = []

    for doi in pending:
        meta = fetch_doi_metadata(doi, api_key, email)
        if meta is None:
            logger.warning("Failed to fetch metadata for DOI: %s", doi)
            failed.append(doi)
        else:
            fetched.append((doi, meta["title"], meta.get("abstract") or ""))

    if fetched:
        texts = [
            title + tokenizer.sep_token + abstract
            for _, title, abstract in fetched
        ]
        embeddings = embed(texts, tokenizer, model)
        Path(corpus_dir).mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()

        with conn:
            for (doi, title, abstract), emb in zip(fetched, embeddings):
                _write_note(doi, title, abstract, corpus_dir)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO corpus
                        (doi, title, abstract, embedding, added_date)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doi, title, abstract, emb.tobytes(), today),
                )

    conn.close()
    logger.info(
        "Corpus build complete. Fetched: %d, failed: %d.", len(fetched), len(failed)
    )
    if failed:
        logger.warning("Failed DOIs (%d): %s", len(failed), ", ".join(failed))


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    load_dotenv()
    build_corpus(
        db_path="data/papers.db",
        seed_file="Corpus/seed_dois.txt",
        corpus_dir="Corpus",
        model_name="allenai/specter2_base",
        api_key=os.environ["NCBI_API_KEY"].strip(),
        email=os.environ["NCBI_EMAIL"].strip(),
    )
