import argparse
import logging
import pathlib
import re
import subprocess
import sys
from datetime import date, datetime, timezone

from src.digest.blocks import DOI_RE, find_recent_digests, parse_block, split_into_blocks

logger = logging.getLogger(__name__)

_TO_READ_PATH = "Inbox/To Read.md"
_QUEUED_PATH = "data/queued_dois.txt"
_CATEGORIES = ("IBD", "AI")
# Ticks from digests before this date were dropped by the old 7-digest window
# and land in their own section when the all-digest sweep first picks them up.
# A fixed date, not an age rule, because ticks are routinely pushed >7 days late.
BACKFILL_CUTOFF = date(2026, 11, 2)
BACKFILL_HEADING = "# Backfilled late ticks"
_BACKFILL_HEADER_RE = re.compile(r"(?m)^# Backfilled late ticks\s*$")
_CATEGORY_START_RE = re.compile(r"(?m)^# (?:IBD|AI)\s*$")
_IBD_RE = re.compile(
    r"\b(?:inflammatory bowel diseases?|IBD|Crohn|ulcerative colitis|pouchitis|colitis)\b",
    re.IGNORECASE,
)
_AI_RE = re.compile(
    r"\b(?:artificial intelligence|machine learning|deep learning|neural networks?|"
    r"large language models?|foundation models?|radiomics|vision transformers?|"
    r"agentic|computer-aided)\b",
    re.IGNORECASE,
)
_AI_ACRONYM_RE = re.compile(r"\b(?:AI|LLMs?|GenAI)\b")
_CATEGORY_HEADER_RE = re.compile(r"(?m)^# (?:IBD|AI)\s*$\n?")
_ENTRY_START_RE = re.compile(r"(?m)^#{2,3} ")


def load_queued_dois(path: str) -> set[str]:
    """Return every DOI ever queued into To Read.md. Raises if the file is missing.

    A missing file must not read as empty: that would re-queue every ticked
    paper, including ones removed from To Read.md by hand.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing; restore it from git or regenerate it with "
            "`python -m src.digest.to_read seed-queued` on a full (non-shallow) clone"
        )
    return {
        line.strip().lower()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def save_queued_dois(path: str, dois: set[str]) -> None:
    """Write the queued-DOI set sorted and deduplicated, one DOI per line."""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    normalized = sorted({d.strip().lower() for d in dois if d.strip()})
    p.write_text("\n".join(normalized) + "\n", encoding="utf-8")


def dois_from_history(vault_root: str) -> set[str]:
    """Return every DOI that has ever appeared in To Read.md across git history."""
    shallow = subprocess.run(
        ["git", "-C", vault_root, "rev-parse", "--is-shallow-repository"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if shallow == "true":
        raise RuntimeError("shallow clone: history is incomplete, run seed-queued locally")
    log = subprocess.run(
        ["git", "-C", vault_root, "log", "-p", "--follow", "--format=", "--", _TO_READ_PATH],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return {m.group(2).lower() for m in DOI_RE.finditer(log)}


def categorize_paper(title: str, abstract: str) -> str:
    """Return IBD or AI, giving IBD precedence when a paper matches both."""
    text = f"{title}\n{abstract}"
    if _IBD_RE.search(text):
        return "IBD"
    if _AI_RE.search(text) or _AI_ACRONYM_RE.search(text):
        return "AI"
    return "IBD"


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
            "category": categorize_paper(parsed["title"], parsed["abstract"]),
        })

    return entries


def _format_entry(entry: dict) -> str:
    doi_url = f"https://doi.org/{entry['doi']}"
    date_str = entry["digest_date"].isoformat()
    digest_note = f"Inbox/Papers/{date_str}"
    lines = [
        f"### {entry['title']}",
        "",
        f"Added: {date_str} | Source: [[{digest_note}]]",
        f"{entry['authors']} | {entry['journal']} | {entry['pub_date']}",
        f"[{entry['doi']}]({doi_url})",
    ]
    if entry["abstract"]:
        lines.append("")
        lines.append("> [!abstract]- Abstract")
        for abstract_line in entry["abstract"].splitlines():
            stripped = abstract_line.strip()
            lines.append(f"> {stripped}" if stripped else ">")
    lines.append("")
    lines.append("---")
    return "\n".join(lines)


def _entry_blocks(text: str) -> list[str]:
    """Return entry blocks from either the legacy flat note or categorized note."""
    without_headers = _CATEGORY_HEADER_RE.sub("", text).strip()
    starts = [match.start() for match in _ENTRY_START_RE.finditer(without_headers)]
    return [
        without_headers[start:end].strip()
        for start, end in zip(starts, starts[1:] + [len(without_headers)])
    ]


def _block_title_abstract(block: str) -> tuple[str, str]:
    """Read classification text from a rendered entry, excluding its metadata."""
    lines = block.splitlines()
    title = re.sub(r"^#{2,3} ", "", lines[0]) if lines else ""
    doi_index = next(
        (index for index, line in enumerate(lines) if "https://doi.org/" in line),
        len(lines),
    )
    abstract = "\n".join(
        line.strip()
        for line in lines[doi_index + 1 :]
        if line.strip() and line.strip() != "---"
    )
    return title, abstract


def _normalize_entry_block(block: str) -> str:
    """Render a legacy or current entry with an H3 title and abstract callout."""
    lines = block.splitlines()
    if not lines:
        return block
    lines[0] = re.sub(r"^#{2,3} ", "### ", lines[0])
    doi_index = next(
        (index for index, line in enumerate(lines) if "https://doi.org/" in line),
        len(lines),
    )
    if doi_index == len(lines):
        return "\n".join(lines)

    tail = [line for line in lines[doi_index + 1 :] if line.strip() != "---"]
    while tail and not tail[0].strip():
        tail.pop(0)
    while tail and not tail[-1].strip():
        tail.pop()

    if tail and tail[0].strip().startswith("> [!abstract]"):
        abstract_callout = tail
    elif tail:
        abstract_callout = ["> [!abstract]- Abstract"] + [
            f"> {line.strip()}" if line.strip() else ">" for line in tail
        ]
    else:
        abstract_callout = []

    normalized = lines[: doi_index + 1]
    if abstract_callout:
        normalized.extend(["", *abstract_callout])
    normalized.extend(["", "---"])
    return "\n".join(normalized)


def _split_backfill(text: str) -> tuple[str, str]:
    """Split the note into (backfill section body, everything else)."""
    header = _BACKFILL_HEADER_RE.search(text)
    if not header:
        return "", text
    next_category = _CATEGORY_START_RE.search(text, header.end())
    end = next_category.start() if next_category else len(text)
    return text[header.end():end], text[:header.start()] + text[end:]


def _render_note(backfill: list[str], blocks: dict[str, list[str]]) -> str:
    sections: list[str] = []
    if backfill:
        sections.append(BACKFILL_HEADING + "\n\n" + "\n\n".join(backfill))
    for category in _CATEGORIES:
        entries = "\n\n".join(blocks[category])
        sections.append(f"# {category}" + (f"\n\n{entries}" if entries else ""))
    return "\n\n".join(sections) + "\n"


def append_entries(
    to_read_path: pathlib.Path,
    entries: list[dict],
    queued: set[str],
) -> list[str]:
    """Categorize the note and prepend entries whose DOI was never queued. Returns the added DOIs."""
    existing = to_read_path.read_text(encoding="utf-8") if to_read_path.exists() else ""

    added: list[str] = []
    new_backfill: list[str] = []
    new_blocks = {category: [] for category in _CATEGORIES}
    for entry in entries:
        if not entry["doi"]:
            logger.warning("Skipping entry with no DOI: %s", entry["title"])
            continue
        doi = entry["doi"].lower()
        if doi in queued or doi in added:
            logger.debug("Already queued, skipping: %s", doi)
            continue
        added.append(doi)
        if entry["digest_date"] < BACKFILL_CUTOFF:
            new_backfill.append(_format_entry(entry))
            continue
        category = entry.get("category")
        if category not in _CATEGORIES:
            category = categorize_paper(entry["title"], entry["abstract"])
        new_blocks[category].append(_format_entry(entry))

    backfill_text, rest = _split_backfill(existing)
    existing_backfill = [_normalize_entry_block(b) for b in _entry_blocks(backfill_text)]
    existing_blocks = {category: [] for category in _CATEGORIES}
    for block in _entry_blocks(rest):
        block = _normalize_entry_block(block)
        title, abstract = _block_title_abstract(block)
        category = categorize_paper(title, abstract)
        existing_blocks[category].append(block)

    categorized = {
        category: new_blocks[category] + existing_blocks[category]
        for category in _CATEGORIES
    }
    rendered = _render_note(new_backfill + existing_backfill, categorized)
    if rendered != existing:
        to_read_path.write_text(rendered, encoding="utf-8")
    return added


def run(vault_root: str, window: int | None = None, digest_date: date | None = None) -> None:
    """Scan digest files and prepend never-queued Read later entries to the rolling note."""
    papers_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"
    queued_path = str(pathlib.Path(vault_root) / _QUEUED_PATH)
    queued = load_queued_dois(queued_path)

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
        logger.info("Scanning %d digest file(s) (window=%s)", len(targets), window)

    all_entries: list[dict] = []
    for digest_path, d in targets:
        entries = extract_read_later_entries(digest_path, d)
        logger.info("Found %d checked Read later entries in %s", len(entries), d.isoformat())
        all_entries.extend(entries)

    if not all_entries:
        return

    to_read_path = pathlib.Path(vault_root) / _TO_READ_PATH
    to_read_path.parent.mkdir(parents=True, exist_ok=True)
    added = append_entries(to_read_path, all_entries, queued)
    if added:
        save_queued_dois(queued_path, queued | set(added))
    backfilled = sum(
        1 for e in all_entries
        if e["doi"].lower() in added and e["digest_date"] < BACKFILL_CUTOFF
    )
    logger.info(
        "Added %d new entries to %s (%d backfilled, %d normal)",
        len(added), to_read_path, backfilled, len(added) - backfilled,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    if len(sys.argv) > 1 and sys.argv[1] == "seed-queued":
        _root = sys.argv[2] if len(sys.argv) > 2 else "."
        _dois = dois_from_history(_root)
        save_queued_dois(str(pathlib.Path(_root) / _QUEUED_PATH), _dois)
        logger.info("Seeded %s from To Read.md history: %d DOIs", _QUEUED_PATH, len(_dois))
        sys.exit(0)
    _parser = argparse.ArgumentParser()
    _parser.add_argument("vault_root", nargs="?", default=".")
    _parser.add_argument("--date", dest="digest_date", default=None)
    _parser.add_argument("--window", type=int, default=None)
    _args = _parser.parse_args()
    _date = date.fromisoformat(_args.digest_date) if _args.digest_date else None
    run(_args.vault_root, window=_args.window, digest_date=_date)
