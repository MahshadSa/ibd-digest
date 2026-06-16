import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_seen_dois(path: str) -> set[str]:
    """Return the persisted set of DOIs already surfaced in a digest. Empty if absent.

    This is the run-to-run dedup baseline. The papers table is rebuilt empty
    each scheduled run, so dedup cannot rely on it; this committed text file is
    the durable record of what has already been shown.
    """
    p = Path(path)
    if not p.exists():
        return set()
    return {
        line.strip().lower()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def save_seen_dois(path: str, dois: set[str]) -> None:
    """Write the seen-DOI set sorted and deduplicated, one DOI per line.

    Sorted output keeps the committed diff small and line-merge friendly.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({d.strip().lower() for d in dois if d.strip()})
    p.write_text("\n".join(normalized) + "\n", encoding="utf-8")
