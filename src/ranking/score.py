import logging

import numpy as np

from src.db import get_connection
from src.ranking.embed import embed as embed_texts
from src.ranking.embed import load_model

logger = logging.getLogger(__name__)

TIER_MUST_READ = 0.75
TIER_SKIM = 0.60


def assign_tier(score: float) -> str:
    """Return 'must-read', 'skim', or 'archive' from score thresholds."""
    if score >= TIER_MUST_READ:
        return "must-read"
    if score >= TIER_SKIM:
        return "skim"
    return "archive"


def embed_pending(db_path: str, model_name: str) -> int:
    """Embed papers with NULL embedding. Return count embedded."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT doi, title, abstract FROM papers WHERE embedding IS NULL"
    ).fetchall()
    if not rows:
        logger.info("No papers pending embedding")
        conn.close()
        return 0

    logger.info("Embedding %d papers", len(rows))
    tokenizer, model = load_model(model_name)
    texts = [
        row["title"] + tokenizer.sep_token + (row["abstract"] or "")
        for row in rows
    ]
    embeddings = embed_texts(texts, tokenizer, model)

    with conn:
        for row, emb in zip(rows, embeddings):
            conn.execute(
                "UPDATE papers SET embedding = ? WHERE doi = ?",
                (emb.tobytes(), row["doi"]),
            )

    conn.close()
    logger.info("Embedded %d papers", len(rows))
    return len(rows)


def score_and_tier(db_path: str) -> int:
    """Compute max cosine similarity vs corpus; store score, matching_corpus_doi, tier. Return count updated."""
    conn = get_connection(db_path)

    corpus_rows = conn.execute(
        "SELECT doi, embedding FROM corpus WHERE embedding IS NOT NULL"
    ).fetchall()
    if not corpus_rows:
        logger.warning("Corpus is empty; cannot score papers")
        conn.close()
        return 0

    corpus_dois = [r["doi"] for r in corpus_rows]
    corpus_matrix = np.vstack(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in corpus_rows]
    )
    norms = np.linalg.norm(corpus_matrix, axis=1, keepdims=True)
    corpus_normed = corpus_matrix / np.maximum(norms, 1e-8)

    paper_rows = conn.execute(
        "SELECT doi, embedding FROM papers WHERE embedding IS NOT NULL"
    ).fetchall()
    if not paper_rows:
        logger.info("No papers with embeddings to score")
        conn.close()
        return 0

    updated = 0
    with conn:
        for row in paper_rows:
            paper_emb = np.frombuffer(row["embedding"], dtype=np.float32)
            norm = np.linalg.norm(paper_emb)
            if norm < 1e-8:
                continue
            sims = corpus_normed @ (paper_emb / norm)
            best_idx = int(np.argmax(sims))
            score = float(sims[best_idx])
            conn.execute(
                """
                UPDATE papers
                SET similarity_score = ?, matching_corpus_doi = ?, tier = ?
                WHERE doi = ?
                """,
                (score, corpus_dois[best_idx], assign_tier(score), row["doi"]),
            )
            updated += 1

    conn.close()
    logger.info("Scored and tiered %d papers", updated)
    return updated
