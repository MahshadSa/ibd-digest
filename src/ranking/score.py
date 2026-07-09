import logging

import numpy as np

from src.db import get_connection, set_meta
from src.ranking.embed import embed as embed_texts
from src.ranking.embed import load_model
from src.ranking.history import append_scores, load_score_history

logger = logging.getLogger(__name__)

# Fallback thresholds, used only when the corpus is too small to calibrate
# against itself. With a calibratable corpus the thresholds come from the
# leave-one-out similarity distribution each run, so they track corpus growth
# and source expansion without manual re-checks.
FALLBACK_MUST_READ = 0.958
FALLBACK_SKIM = 0.924

TOP_K_SIM = 3
MIN_CALIBRATION = 5
MUST_PERCENTILE = 85
SKIM_PERCENTILE = 40


def top_k_mean(sims: np.ndarray, k: int = TOP_K_SIM) -> float:
    """Mean of the k highest similarities (all of them if fewer than k)."""
    if sims.size <= k:
        return float(sims.mean())
    top = np.partition(sims, -k)[-k:]
    return float(top.mean())


def compute_thresholds(score_history: np.ndarray) -> tuple[float, float]:
    """Percentile-anchored tier thresholds from the candidate-score distribution.

    The thresholds are the MUST_PERCENTILE / SKIM_PERCENTILE percentiles of the
    scores candidates have actually produced (the persisted rolling window), so
    the cutoffs track where papers land rather than how self-similar the corpus
    is. Falls back to the fixed constants when the window is too small.
    """
    if score_history.size < MIN_CALIBRATION:
        logger.warning(
            "Score history too small to calibrate (%d < %d); using fallbacks",
            score_history.size,
            MIN_CALIBRATION,
        )
        return FALLBACK_MUST_READ, FALLBACK_SKIM
    must = float(np.percentile(score_history, MUST_PERCENTILE))
    skim = float(np.percentile(score_history, SKIM_PERCENTILE))
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


def _load_corpus(conn) -> tuple[list[str], np.ndarray]:
    """Return corpus DOIs and the L2-normalized corpus embedding matrix."""
    rows = conn.execute(
        "SELECT doi, embedding FROM corpus WHERE embedding IS NOT NULL"
    ).fetchall()
    dois = [r["doi"] for r in rows]
    matrix = np.vstack(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
    )
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return dois, matrix / np.maximum(norms, 1e-8)


def score_papers(
    corpus_dois: list[str], corpus_normed: np.ndarray, paper_rows
) -> list[tuple[str, float, str]]:
    """Score each paper as top-k mean cosine vs corpus.

    Returns (doi, score, matching_corpus_doi) per scorable paper; papers with a
    degenerate (zero-norm) embedding are skipped.
    """
    scored: list[tuple[str, float, str]] = []
    for row in paper_rows:
        emb = np.frombuffer(row["embedding"], dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm < 1e-8:
            continue
        sims = corpus_normed @ (emb / norm)
        best_idx = int(np.argmax(sims))
        scored.append((row["doi"], top_k_mean(sims), corpus_dois[best_idx]))
    return scored


def score_and_tier(
    db_path: str, score_history_path: str = "data/score_history.txt"
) -> int:
    """Score papers vs corpus, append scores to the history window, calibrate
    thresholds from that window, then tier. Returns count updated.

    Two-pass: scoring is independent of the thresholds, and the thresholds come
    from the accumulated candidate-score distribution (this run's scores
    included), so scoring must complete before tiering.
    """
    conn = get_connection(db_path)

    corpus_dois, corpus_normed = _load_corpus(conn)
    if not corpus_dois:
        logger.warning("Corpus is empty; cannot score papers")
        conn.close()
        return 0

    paper_rows = conn.execute(
        "SELECT doi, embedding FROM papers WHERE embedding IS NOT NULL"
    ).fetchall()
    if not paper_rows:
        logger.info("No papers with embeddings to score")
        conn.close()
        return 0

    scored = score_papers(corpus_dois, corpus_normed, paper_rows)

    append_scores(score_history_path, [s for _, s, _ in scored])
    window = load_score_history(score_history_path)
    must_threshold, skim_threshold = compute_thresholds(window)
    logger.info(
        "Tier thresholds this run: must-read >= %.4f, skim >= %.4f (window n=%d)",
        must_threshold,
        skim_threshold,
        window.size,
    )
    with conn:
        set_meta(conn, "tier_threshold_must", f"{must_threshold:.6f}")
        set_meta(conn, "tier_threshold_skim", f"{skim_threshold:.6f}")
        for doi, score, matching_doi in scored:
            conn.execute(
                """
                UPDATE papers
                SET similarity_score = ?, matching_corpus_doi = ?, tier = ?
                WHERE doi = ?
                """,
                (
                    score,
                    matching_doi,
                    assign_tier(score, must_threshold, skim_threshold),
                    doi,
                ),
            )

    conn.close()
    logger.info("Scored and tiered %d papers", len(scored))
    return len(scored)
