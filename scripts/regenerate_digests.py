"""One-off: regenerate the all-archive July digests under the fixed calibration.

Reads the DOIs from each broken digest, re-fetches metadata by DOI, inserts each
paper with seen_date pinned to its digest date, then runs corpus/rank/writer/
metrics per date. Runs on the laptop (Crossref/PubMed unreachable in CI). Not
part of the daily pipeline.
"""
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src import metrics
from src.corpus import rebuild_corpus_from_notes
from src.db import get_connection, insert_paper, migrate, migrate_embedding_columns
from src.digest import writer
from src.fetchers.by_doi import fetch_by_doi
from src.ranking.score import embed_pending, score_and_tier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATES = ["2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07", "2026-07-08"]
MODEL_NAME = "allenai/specter2_base"
CORPUS_DIR = "Corpus"
METRICS_PATH = "data/metrics.txt"

_DOI_LINK_RE = re.compile(r"\[([^\]]+)\]\(https://doi\.org/[^)]+\)")


def dois_from_digest(path: str) -> list[str]:
    """Ordered, de-duplicated DOIs linked in one digest file."""
    seen: dict[str, None] = {}
    for m in _DOI_LINK_RE.finditer(Path(path).read_text(encoding="utf-8")):
        doi = m.group(1).strip().lower()
        if doi.startswith("10."):
            seen.setdefault(doi, None)
    return list(seen)


def run(vault_root: str, db_path: str, email: str, api_key: str | None) -> None:
    if Path(db_path).exists():
        Path(db_path).unlink()  # start from a clean DB; the snapshot is expendable
    migrate(db_path)
    migrate_embedding_columns(db_path)
    rebuild_corpus_from_notes(db_path, CORPUS_DIR, MODEL_NAME)

    conn = get_connection(db_path)
    for d in DATES:
        digest = Path(vault_root) / "Inbox" / "Papers" / f"{d}.md"
        dois = dois_from_digest(str(digest))
        logger.info("%s: %d DOIs", d, len(dois))
        for doi in dois:
            paper = fetch_by_doi(doi, email, api_key)
            if paper is None:
                logger.warning("Unresolved DOI, skipping: %s", doi)
                continue
            with conn:
                insert_paper(conn, paper, seen_date=d)
    conn.close()

    embed_pending(db_path, MODEL_NAME)
    score_and_tier(db_path)

    for d in DATES:
        target = date.fromisoformat(d)
        writer.run(db_path, vault_root, target_date=target, force=True)
        metrics.run(db_path, METRICS_PATH, target_date=target)
    logger.info("Regenerated %d digests", len(DATES))


if __name__ == "__main__":
    load_dotenv()
    _vault = sys.argv[1] if len(sys.argv) > 1 else "."
    _db = sys.argv[2] if len(sys.argv) > 2 else "data/papers.db"
    run(_vault, _db, os.environ["NCBI_EMAIL"], os.environ.get("NCBI_API_KEY"))
