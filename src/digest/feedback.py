"""Feedback loop consumer: checked Relevant boxes become corpus seed notes.

Scans a trailing window of digest files for papers whose Relevant box is
checked and writes each as a Corpus/{slug}.md note in the same format
src.corpus emits and parses. The next `src.corpus from-notes` rebuild embeds
the new notes into the corpus table, so the ranker sharpens with no further
step. Fully offline: the digest block already carries title and abstract.

Contract: matches ONLY the Relevant checkbox. A Read later tick must never
reach the corpus (see the checkbox parsing contract in CLAUDE.md).
"""
import argparse
import logging
import pathlib

from src.corpus import _write_note
from src.digest.blocks import find_recent_digests, parse_block, split_into_blocks

logger = logging.getLogger(__name__)


def extract_relevant_entries(digest_path: pathlib.Path) -> list[dict]:
    """Return {doi, title, abstract} for each paper with a checked Relevant box."""
    text = digest_path.read_text(encoding="utf-8")
    entries: list[dict] = []
    for block in split_into_blocks(text.splitlines()):
        parsed = parse_block(block)
        if not parsed["relevant_checked"]:
            continue
        if not parsed["doi"]:
            logger.warning("Relevant tick with no DOI, skipping: %s", parsed["title"])
            continue
        entries.append({
            "doi": parsed["doi"].lower(),
            "title": parsed["title"],
            "abstract": parsed["abstract"],
        })
    return entries


def run(vault_root: str, window: int = 7) -> int:
    """Scan recent digests for Relevant ticks and write missing corpus notes. Returns count added."""
    papers_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"
    corpus_dir = pathlib.Path(vault_root) / "Corpus"
    targets = find_recent_digests(papers_dir, window)
    if not targets:
        logger.info("No digest files found in %s", papers_dir)
        return 0

    added = 0
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for digest_path, d in targets:
        for entry in extract_relevant_entries(digest_path):
            slug = entry["doi"].replace("/", "_").replace(":", "_")
            note_path = corpus_dir / f"{slug}.md"
            if note_path.exists():
                continue
            _write_note(entry["doi"], entry["title"], entry["abstract"], str(corpus_dir))
            logger.info("Added corpus note %s (from digest %s)", note_path.name, d)
            added += 1

    logger.info("Feedback sweep done: %d corpus note(s) added", added)
    return added


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _parser = argparse.ArgumentParser()
    _parser.add_argument("vault_root", nargs="?", default=".")
    _parser.add_argument("--window", type=int, default=7)
    _args = _parser.parse_args()
    run(_args.vault_root, window=_args.window)
