import argparse
import logging
import pathlib
from datetime import date, datetime, timezone

from src.digest.blocks import find_recent_digests, parse_block, split_into_blocks

logger = logging.getLogger(__name__)

_TO_READ_PATH = "Inbox/To Read.md"


def extract_read_later_entries(
    digest_path: pathlib.Path,
    digest_date: date,
) -> list[dict]:
    """Parse a digest file; return one dict per paper with a checked Read later box."""
    text = digest_path.read_text(encoding="utf-8")
    entries: list[dict] = []
    for block in split_into_blocks(text.splitlines()):
        parsed = parse_block(block)
        if not parsed["read_later_checked"] or not parsed["title"]:
            continue
        abstract = parsed["abstract"].splitlines()
        entries.append({
            "title": parsed["title"],
            "authors": parsed["authors"],
            "journal": parsed["journal"],
            "pub_date": parsed["pub_date"],
            "doi": parsed["doi"],
            "abstract": abstract[0] if abstract else "",
            "digest_date": digest_date,
        })

    return entries


def _format_entry(entry: dict) -> str:
    doi_url = f"https://doi.org/{entry['doi']}"
    date_str = entry["digest_date"].isoformat()
    digest_note = f"Inbox/Papers/{date_str}"
    lines = [
        f"## {entry['title']}",
        "",
        f"Added: {date_str} | Source: [[{digest_note}]]",
        f"{entry['authors']} | {entry['journal']} | {entry['pub_date']}",
        f"[{entry['doi']}]({doi_url})",
    ]
    if entry["abstract"]:
        lines.append("")
        lines.append(entry["abstract"])
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def append_entries(
    to_read_path: pathlib.Path,
    entries: list[dict],
) -> int:
    """Prepend entries whose DOI is not already present. Returns count added."""
    existing = to_read_path.read_text(encoding="utf-8") if to_read_path.exists() else ""

    seen: set[str] = set()
    new_blocks: list[str] = []
    for entry in entries:
        if not entry["doi"]:
            logger.warning("Skipping entry with no DOI: %s", entry["title"])
            continue
        doi_url = f"https://doi.org/{entry['doi']}"
        if doi_url in existing or entry["doi"] in seen:
            logger.debug("Already present, skipping: %s", entry["doi"])
            continue
        seen.add(entry["doi"])
        new_blocks.append(_format_entry(entry))

    if not new_blocks:
        return 0

    prepend = "\n\n".join(new_blocks) + ("\n\n" if existing else "\n")
    to_read_path.write_text(prepend + existing, encoding="utf-8")
    return len(new_blocks)


def run(vault_root: str, window: int = 7, digest_date: date | None = None) -> None:
    """Scan a trailing window of digest files and append new Read later entries to the rolling note."""
    papers_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"

    if digest_date is not None:
        digest_path = papers_dir / f"{digest_date.isoformat()}.md"
        if not digest_path.exists():
            logger.error("Digest not found: %s", digest_path)
            return
        targets = [(digest_path, digest_date)]
    else:
        targets = find_recent_digests(papers_dir, window)
        if not targets:
            logger.info("No digest files found in %s", papers_dir)
            return
        logger.info("Scanning %d digest file(s) (window=%d)", len(targets), window)

    all_entries: list[dict] = []
    for digest_path, d in targets:
        entries = extract_read_later_entries(digest_path, d)
        logger.info("Found %d checked Read later entries in %s", len(entries), d.isoformat())
        all_entries.extend(entries)

    if not all_entries:
        return

    to_read_path = pathlib.Path(vault_root) / _TO_READ_PATH
    to_read_path.parent.mkdir(parents=True, exist_ok=True)
    added = append_entries(to_read_path, all_entries)
    logger.info("Appended %d new entries to %s", added, to_read_path)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _parser = argparse.ArgumentParser()
    _parser.add_argument("vault_root", nargs="?", default=".")
    _parser.add_argument("--date", dest="digest_date", default=None)
    _parser.add_argument("--window", type=int, default=7)
    _args = _parser.parse_args()
    _date = date.fromisoformat(_args.digest_date) if _args.digest_date else None
    run(_args.vault_root, window=_args.window, digest_date=_date)
