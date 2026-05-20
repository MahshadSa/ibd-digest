import logging
import sys

from dotenv import load_dotenv

from src.db import migrate_embedding_columns
from src.ranking.score import embed_pending, score_and_tier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = "data/papers.db"
MODEL_NAME = "allenai/specter2_base"


def run(db_path: str, model_name: str) -> None:
    """Embed all pending papers and score against corpus."""
    migrate_embedding_columns(db_path)
    n_embedded = embed_pending(db_path, model_name)
    n_scored = score_and_tier(db_path)
    logger.info("Done. Embedded: %d, scored: %d.", n_embedded, n_scored)


if __name__ == "__main__":
    load_dotenv()
    _db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    run(_db, MODEL_NAME)
