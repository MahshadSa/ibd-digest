import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SCORE_HISTORY_CAP = 2000


def load_score_history(path: str) -> np.ndarray:
    """Return the persisted rolling window of candidate scores. Empty if absent.

    The papers table is rebuilt empty each scheduled run, so tier calibration
    cannot rely on it; this committed text file is the durable candidate-score
    distribution the thresholds are drawn from.
    """
    p = Path(path)
    if not p.exists():
        return np.array([], dtype=np.float64)
    values = [
        float(line.strip())
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return np.array(values, dtype=np.float64)


def append_scores(
    path: str, scores: list[float], cap: int = SCORE_HISTORY_CAP
) -> None:
    """Append scores in order, then keep only the last `cap` (FIFO from front)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = [
        line.strip()
        for line in (
            p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        )
        if line.strip()
    ]
    combined = existing + [f"{s:.6f}" for s in scores]
    combined = combined[-cap:]
    p.write_text("\n".join(combined) + "\n", encoding="utf-8")
