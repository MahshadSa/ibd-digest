import logging
import os
import sys

from dotenv import load_dotenv

from src.db import get_connection, get_existing_dois, insert_paper, migrate
from src.fetchers.journals import fetch_all_journals
from src.fetchers.pubmed import fetch_pubmed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = "data/papers.db"


def run(db_path: str, api_key: str, email: str, days_back: int = 1) -> None:
    """Run all fetchers, dedup by DOI against existing DB rows, write new papers."""
    migrate(db_path)
    conn = get_connection(db_path)

    existing_dois = get_existing_dois(conn)
    logger.info("Existing papers in DB: %d", len(existing_dois))

    all_papers: list[dict] = []
    all_papers.extend(fetch_pubmed(api_key, email, days_back))
    all_papers.extend(fetch_all_journals(email))

    # Dedup within batch by DOI, keeping first occurrence
    seen: set[str] = set()
    deduped: list[dict] = []
    for paper in all_papers:
        if paper["doi"] not in seen:
            seen.add(paper["doi"])
            deduped.append(paper)

    new_papers = [p for p in deduped if p["doi"] not in existing_dois]

    logger.info(
        "Fetched %d total, %d batch duplicates, %d already in DB, %d new",
        len(all_papers),
        len(all_papers) - len(deduped),
        len(deduped) - len(new_papers),
        len(new_papers),
    )

    with conn:
        for paper in new_papers:
            insert_paper(conn, paper)

    conn.close()
    logger.info("Done. %d papers written to DB.", len(new_papers))


if __name__ == "__main__":
    load_dotenv()
    _api_key = os.environ["NCBI_API_KEY"].strip()
    _email = os.environ["NCBI_EMAIL"].strip()
    _days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run(DB_PATH, _api_key, _email, _days_back)
