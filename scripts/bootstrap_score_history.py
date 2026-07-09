"""One-off: seed data/score_history.txt from the local DB snapshot.

Re-scores every embedded paper in data/papers.db against the current corpus and
writes the scores as the initial calibration window. Not part of the daily
pipeline. Run once, locally, then commit data/score_history.txt.
"""
import logging
import sys

from src.db import get_connection
from src.ranking.history import append_scores
from src.ranking.score import _load_corpus, score_papers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run(db_path: str, history_path: str) -> int:
    conn = get_connection(db_path)
    corpus_dois, corpus_normed = _load_corpus(conn)
    if not corpus_dois:
        conn.close()
        sys.exit("corpus table is empty; run: python -m src.corpus from-notes " + db_path)
    paper_rows = conn.execute(
        "SELECT doi, embedding FROM papers WHERE embedding IS NOT NULL"
    ).fetchall()
    conn.close()
    scored = score_papers(corpus_dois, corpus_normed, paper_rows)
    append_scores(history_path, [s for _, s, _ in scored])
    logger.info("Seeded %s with %d scores", history_path, len(scored))
    return len(scored)


if __name__ == "__main__":
    _db = sys.argv[1] if len(sys.argv) > 1 else "data/papers.db"
    _hist = sys.argv[2] if len(sys.argv) > 2 else "data/score_history.txt"
    run(_db, _hist)
