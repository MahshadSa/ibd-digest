import logging

import numpy as np

from src.db import get_connection, set_meta
from src.ranking.embed import embed as embed_texts
from src.ranking.embed import load_model

logger = logging.getLogger(__name__)

# Fallback thresholds, used only when the corpus is too small to calibrate
# against itself. With a calibratable corpus the thresholds come from the
# leave-one-out similarity distribution each run, so they track corpus growth
# and source expansion without manual re-checks.
FALLBACK_MUST_READ = 0.958
FALLBACK_SKIM = 0.924

TOP_K_SIM = 3
MIN_CALIBRATION = 5
MUST_PERCENTILE = 90
SKIM_PERCENTILE = 50


def top_k_mean(sims: np.ndarray, k: int = TOP_K_SIM) -> float:
    """Mean of the k highest similarities (all of them if fewer than k)."""
    if sims.size <= k:
        return float(sims.mean())
    top = np.partition(sims, -k)[-k:]
    return float(top.mean())


def compute_thresholds(corpus_normed: np.ndarray) -> tuple[float, float]:
    """Percentile-anchored tier thresholds from the corpus leave-one-out distribution.

    Each corpus paper is scored against the rest with the same top-k mean
    statistic used for candidates, and the must-read/skim cuts are the 90th and
    50th percentiles of that distribution. Falls back to the fixed constants
    when the corpus is too small to calibrate.
    """
    n = corpus_normed.shape[0]
    if n < MIN_CALIBRATION:
        logger.warning(
            "Corpus too small to calibrate thresholds (%d < %d); using fallbacks",
            n,
            MIN_CALIBRATION,
        )
        return FALLBACK_MUST_READ, FALLBACK_SKIM
    all_sims = corpus_normed @ corpus_normed.T
    k = min(TOP_K_SIM, n - 1)
    dist = []
    for i in range(n):
        others = np.delete(all_sims[i], i)
        dist.append(top_k_mean(others, k))
    must = float(np.percentile(dist, MUST_PERCENTILE))
    skim = float(np.percentile(dist, SKIM_PERCENTILE))
    return must, skim


def assign_tier(score: float, must_threshold: float, skim_threshold: float) -> str:
    """Return 'must-read', 'skim', or 'archive' from the given thresholds."""
    if score >= must_threshold:
        return "must-read"
    if score >= skim_threshold:
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
    """Score papers as top-k mean cosine similarity vs corpus; store score, matching_corpus_doi, tier.

    Thresholds are recalibrated from the corpus each run and recorded in the
    meta table (tier_threshold_must, tier_threshold_skim) for telemetry.
    Returns count updated.
    """
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

    must_threshold, skim_threshold = compute_thresholds(corpus_normed)
    logger.info(
        "Tier thresholds this run: must-read >= %.4f, skim >= %.4f",
        must_threshold,
        skim_threshold,
    )
    with conn:
        set_meta(conn, "tier_threshold_must", f"{must_threshold:.6f}")
        set_meta(conn, "tier_threshold_skim", f"{skim_threshold:.6f}")

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
            score = top_k_mean(sims)
            conn.execute(
                """
                UPDATE papers
                SET similarity_score = ?, matching_corpus_doi = ?, tier = ?
                WHERE doi = ?
                """,
                (
                    score,
                    corpus_dois[best_idx],
                    assign_tier(score, must_threshold, skim_threshold),
                    row["doi"],
                ),
            )
            updated += 1

    conn.close()
    logger.info("Scored and tiered %d papers", updated)
    return updated
