"""Shared digest-block parsing for the checkbox consumers.

One parser, three consumers (to_read, feedback, column), so the checkbox
contract cannot drift between them. Parsing is pattern-based, not positional:
metadata is read from the indented lines and the checkbox lines are matched by
their literal labels, so old-format digests (no Relevant line, no Nearest seed
line) and new-format digests parse identically.
"""
import pathlib
import re
from datetime import date

TITLE_RE = re.compile(r"^>?\s?- \[.\] \*\*(.+)\*\*$")
RELEVANT_RE = re.compile(r"^>?\s*- \[[xX]\] Relevant\s*$")
READ_LATER_RE = re.compile(r"^>?\s*- \[[xX]\] Read later\s*$")
DOI_RE = re.compile(r"\[([^\]]+)\]\(https://doi\.org/([^\)]+)\)")
SCORE_RE = re.compile(r"Score: (\d+\.\d+)")
_ABSTRACT_MARKER = "> [!abstract]-"


def split_into_blocks(lines: list[str]) -> list[list[str]]:
    """Group digest lines into per-paper blocks, one per title line."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if TITLE_RE.match(line):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _abstract_text(block: list[str]) -> str:
    """Reassemble the abstract from its callout, joining paragraphs with blank lines."""
    out: list[str] = []
    in_callout = False
    for line in block:
        if line.strip() == _ABSTRACT_MARKER:
            in_callout = True
            continue
        if not in_callout:
            continue
        stripped = line.strip()
        if stripped.startswith(">"):
            out.append(stripped[1:].strip())
        elif stripped:
            break
    return "\n".join(out).strip()


def parse_block(block: list[str]) -> dict:
    """Parse one paper block into its fields and checkbox states."""
    title_match = TITLE_RE.match(block[0])
    title = title_match.group(1) if title_match else ""

    meta = [
        line.strip()
        for line in block
        if line.startswith("  ") and not line.lstrip().startswith(">")
    ]
    authors = meta[0] if meta else ""
    journal_date = meta[1] if len(meta) > 1 else ""
    parts = journal_date.split(" | ", 1)
    journal = parts[0] if parts else ""
    pub_date = parts[1] if len(parts) > 1 else ""

    doi = ""
    score = ""
    for line in meta:
        if not doi:
            m = DOI_RE.search(line)
            if m:
                doi = m.group(2)
        if not score:
            m = SCORE_RE.search(line)
            if m:
                score = m.group(1)

    return {
        "title": title,
        "relevant_checked": any(RELEVANT_RE.match(line) for line in block),
        "read_later_checked": any(READ_LATER_RE.match(line) for line in block),
        "authors": authors,
        "journal": journal,
        "pub_date": pub_date,
        "doi": doi,
        "score": score,
        "abstract": _abstract_text(block),
    }


def find_recent_digests(
    papers_dir: pathlib.Path, window: int
) -> list[tuple[pathlib.Path, date]]:
    """Return up to window most-recent digest files, newest first."""
    results: list[tuple[pathlib.Path, date]] = []
    for p in papers_dir.glob("*.md"):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        results.append((p, d))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:window]
