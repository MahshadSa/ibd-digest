import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DOI_LINK_RE = re.compile(r"\[([^\]]+)\]\(https://doi\.org/[^)]+\)")


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


def dois_from_notes(notes_dir: str) -> set[str]:
    """Extract every DOI linked in the digest notes under notes_dir.

    The committed digest notes are the source of truth for what has been
    surfaced; this resyncs the seen list to them (recovery / after editing notes).
    """
    dois: set[str] = set()
    for path in Path(notes_dir).glob("*.md"):
        for m in _DOI_LINK_RE.finditer(path.read_text(encoding="utf-8")):
            d = m.group(1).strip().lower()
            if d.startswith("10."):
                dois.add(d)
    return dois


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    if len(sys.argv) < 2 or sys.argv[1] != "rebuild-from-notes":
        sys.exit("usage: python -m src.seen rebuild-from-notes [notes_dir] [seen_path]")
    _notes_dir = sys.argv[2] if len(sys.argv) > 2 else "Inbox/Papers"
    _seen_path = sys.argv[3] if len(sys.argv) > 3 else "data/seen_dois.txt"
    _dois = dois_from_notes(_notes_dir)
    save_seen_dois(_seen_path, _dois)
    logger.info("Rebuilt %s from %s: %d DOIs", _seen_path, _notes_dir, len(_dois))
