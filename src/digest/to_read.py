import argparse
import logging
import pathlib
import re
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

_TO_READ_PATH = "Inbox/To Read.md"

_TITLE_RE = re.compile(r"^- \[.\] \*\*(.+)\*\*$")
_READ_LATER_RE = re.compile(r"^- \[[xX]\] Read later$")
_DOI_RE = re.compile(r"\[([^\]]+)\]\(https://doi\.org/([^\)]+)\)")


def _split_into_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _TITLE_RE.match(line) and current:
            blocks.append(current)
            current = [line]
        elif _TITLE_RE.match(line):
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def extract_read_later_entries(
    digest_path: pathlib.Path,
    digest_date: date,
) -> list[dict]:
    """Parse a digest file; return one dict per paper with a checked Read later box."""
    text = digest_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = _split_into_blocks(lines)

    entries: list[dict] = []
    for block in blocks:
        if len(block) < 2:
            continue
        if not _READ_LATER_RE.match(block[1]):
            continue

        title_match = _TITLE_RE.match(block[0])
        if not title_match:
            continue
        title = title_match.group(1)

        authors = block[2].strip() if len(block) > 2 else ""
        journal_date = block[3].strip() if len(block) > 3 else ""
        parts = journal_date.split(" | ", 1)
        journal = parts[0] if parts else ""
        pub_date = parts[1] if len(parts) > 1 else ""

        doi = ""
        if len(block) > 4:
            doi_match = _DOI_RE.search(block[4])
            if doi_match:
                doi = doi_match.group(2)

        abstract = ""
        for i, line in enumerate(block):
            if line.strip() == "> [!abstract]-":
                if i + 1 < len(block):
                    raw = block[i + 1]
                    abstract = raw[4:] if raw.startswith("  > ") else raw.strip()
                break

        entries.append({
            "title": title,
            "authors": authors,
            "journal": journal,
            "pub_date": pub_date,
            "doi": doi,
            "abstract": abstract,
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

    new_blocks: list[str] = []
    for entry in entries:
        if not entry["doi"]:
            logger.warning("Skipping entry with no DOI: %s", entry["title"])
            continue
        if f"https://doi.org/{entry['doi']}" in existing:
            logger.debug("Already present, skipping: %s", entry["doi"])
            continue
        new_blocks.append(_format_entry(entry))

    if not new_blocks:
        return 0

    prepend = "\n\n".join(new_blocks) + ("\n\n" if existing else "\n")
    to_read_path.write_text(prepend + existing, encoding="utf-8")
    return len(new_blocks)


def run(vault_root: str, digest_date: date | None = None) -> None:
    """Scan one day's digest and append new Read later entries to the rolling note."""
    if digest_date is None:
        digest_date = datetime.now(timezone.utc).date()

    digest_path = pathlib.Path(vault_root) / "Inbox" / "Papers" / f"{digest_date.isoformat()}.md"
    if not digest_path.exists():
        logger.error("Digest not found: %s", digest_path)
        return

    entries = extract_read_later_entries(digest_path, digest_date)
    logger.info("Found %d checked Read later entries in %s", len(entries), digest_date.isoformat())

    if not entries:
        return

    to_read_path = pathlib.Path(vault_root) / _TO_READ_PATH
    to_read_path.parent.mkdir(parents=True, exist_ok=True)
    added = append_entries(to_read_path, entries)
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
    _args = _parser.parse_args()
    _date = date.fromisoformat(_args.digest_date) if _args.digest_date else None
    run(_args.vault_root, _date)
