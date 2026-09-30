import argparse
import logging
import pathlib
import re
from datetime import date, datetime, timezone

from src.digest.blocks import find_recent_digests, parse_block, split_into_blocks

logger = logging.getLogger(__name__)

_TO_READ_PATH = "Inbox/To Read.md"
_CATEGORIES = ("IBD", "AI")
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


def _render_categories(blocks: dict[str, list[str]]) -> str:
    sections: list[str] = []
    for category in _CATEGORIES:
        entries = "\n\n".join(blocks[category])
        sections.append(f"# {category}" + (f"\n\n{entries}" if entries else ""))
    return "\n\n".join(sections) + "\n"


def append_entries(
    to_read_path: pathlib.Path,
    entries: list[dict],
) -> int:
    """Categorize the note and prepend entries whose DOI is not already present."""
    existing = to_read_path.read_text(encoding="utf-8") if to_read_path.exists() else ""

    seen: set[str] = set()
    new_blocks = {category: [] for category in _CATEGORIES}
    for entry in entries:
        if not entry["doi"]:
            logger.warning("Skipping entry with no DOI: %s", entry["title"])
            continue
        doi_url = f"https://doi.org/{entry['doi']}"
        if doi_url in existing or entry["doi"] in seen:
            logger.debug("Already present, skipping: %s", entry["doi"])
            continue
        seen.add(entry["doi"])
        category = entry.get("category")
        if category not in _CATEGORIES:
            category = categorize_paper(entry["title"], entry["abstract"])
        new_blocks[category].append(_format_entry(entry))

    existing_blocks = {category: [] for category in _CATEGORIES}
    for block in _entry_blocks(existing):
        block = _normalize_entry_block(block)
        title, abstract = _block_title_abstract(block)
        category = categorize_paper(title, abstract)
        existing_blocks[category].append(block)

    categorized = {
        category: new_blocks[category] + existing_blocks[category]
        for category in _CATEGORIES
    }
    rendered = _render_categories(categorized)
    if rendered != existing:
        to_read_path.write_text(rendered, encoding="utf-8")
    return sum(len(blocks) for blocks in new_blocks.values())


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
