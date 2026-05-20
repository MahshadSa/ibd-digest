import argparse
import json
import logging
import pathlib
import sqlite3
import sys
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = "data/papers.db"

_TIER_CALLOUT = {
    "must-read": "> [!important]",
    "skim": "> [!note]",
    "archive": "> [!abstract]-",
}
_TIER_LABEL = {
    "must-read": "Must-read",
    "skim": "Skim",
    "archive": "Archive",
}


def fetch_papers(conn: sqlite3.Connection, target_date: date) -> list[sqlite3.Row]:
    """Return all rows for target_date, ordered by similarity_score descending."""
    return conn.execute(
        "SELECT * FROM papers WHERE seen_date = ? ORDER BY similarity_score DESC NULLS LAST, title",
        (target_date.isoformat(),),
    ).fetchall()


def format_authors(authors_json: str, corresponding_author: str | None) -> str:
    """Build display string: first two authors + corresponding author if not already included."""
    authors: list[str] = json.loads(authors_json)
    display = authors[:2]
    if corresponding_author and corresponding_author not in display:
        display.append(corresponding_author)
    return ", ".join(display)


def tier_papers(
    papers: list[sqlite3.Row],
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], list[sqlite3.Row]]:
    """Split papers into (must_read, skim, archive) using the stored tier column."""
    must_read: list[sqlite3.Row] = []
    skim: list[sqlite3.Row] = []
    archive: list[sqlite3.Row] = []
    for p in papers:
        t = p["tier"]
        if t == "must-read":
            must_read.append(p)
        elif t == "skim":
            skim.append(p)
        else:
            archive.append(p)
    return must_read, skim, archive


def render_paper_full(paper: sqlite3.Row) -> str:
    """Render a must-read or skim paper: task checkbox, metadata, collapsed abstract callout."""
    doi_url = f"https://doi.org/{paper['doi']}"
    authors_str = format_authors(paper["authors"], paper["corresponding_author"])
    score = paper["similarity_score"]
    score_str = f"{score:.2f}" if score is not None else "N/A"
    abstract = paper["abstract"] or ""

    lines = [
        f"- [ ] **{paper['title']}**",
        f"  {authors_str}",
        f"  {paper['journal']} | {paper['pub_date']}",
        f"  [{paper['doi']}]({doi_url}) | Score: {score_str}",
    ]
    if abstract:
        lines.append("")
        lines.append("  > [!abstract]-")
        lines.append(f"  > {abstract}")

    return "\n".join(lines)


def render_paper_archive(paper: sqlite3.Row) -> str:
    """Render an archive paper for inside a callout body: title, authors, DOI link only."""
    doi_url = f"https://doi.org/{paper['doi']}"
    authors_str = format_authors(paper["authors"], paper["corresponding_author"])
    return "\n".join([
        f"> - **{paper['title']}**",
        f">   {authors_str}",
        f">   [{paper['doi']}]({doi_url})",
    ])


def render_tier(papers: list[sqlite3.Row], tier: str) -> str:
    """Render one tier section. Must-read/skim: callout banner + papers outside. Archive: papers inside callout so it collapses."""
    n = len(papers)
    header = f"{_TIER_CALLOUT[tier]} {_TIER_LABEL[tier]} ({n})"

    if tier == "archive":
        body = "\n>\n".join(render_paper_archive(p) for p in papers)
        return f"{header}\n>\n{body}"

    paper_blocks = "\n\n".join(render_paper_full(p) for p in papers)
    return f"{header}\n\n{paper_blocks}"


def render_digest(papers: list[sqlite3.Row], target_date: date) -> str:
    """Render the complete digest: header with tier counts, tiered sections, source footer."""
    date_str = target_date.isoformat()
    must_read, skim, archive = tier_papers(papers)

    header_counts = (
        f"**Date:** {date_str}\n"
        f"**New papers:** {len(papers)}"
        f" | Must-read: {len(must_read)}"
        f" | Skim: {len(skim)}"
        f" | Archive: {len(archive)}"
    )
    header = f"# IBD Imaging Digest - {date_str}\n\n{header_counts}\n\n---\n\n"

    if not papers:
        return header + "No new papers today, pipeline ran successfully.\n"

    tier_sections = []
    for tier_name, tier_list in [("must-read", must_read), ("skim", skim), ("archive", archive)]:
        if tier_list:
            tier_sections.append(render_tier(tier_list, tier_name))

    body = "\n\n---\n\n".join(tier_sections)

    source_counts: dict[str, int] = {}
    for p in papers:
        source_counts[p["source"]] = source_counts.get(p["source"], 0) + 1
    source_str = " | ".join(f"{src}: {count}" for src, count in sorted(source_counts.items()))
    footer = f"\n\n---\n\n**Sources:** {source_str}\n"

    return header + body + footer


def write_digest(vault_root: str, content: str, target_date: date, force: bool = False) -> pathlib.Path:
    """Write to Inbox/Papers/YYYY-MM-DD.md. Raises FileExistsError if file exists and force is False."""
    out_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date.isoformat()}.md"
    if out_path.exists() and not force:
        raise FileExistsError(f"Digest already exists: {out_path}")
    out_path.write_text(content, encoding="utf-8")
    return out_path


def run(db_path: str, vault_root: str, target_date: date | None = None, force: bool = False) -> None:
    """Fetch papers, render digest, write file. target_date defaults to today UTC."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        papers = fetch_papers(conn, target_date)
        logger.info("Found %d papers for %s", len(papers), target_date.isoformat())
        content = render_digest(papers, target_date)
        out_path = write_digest(vault_root, content, target_date, force=force)
        logger.info("Digest written to %s", out_path)
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _parser = argparse.ArgumentParser()
    _parser.add_argument("vault_root", nargs="?", default=".")
    _parser.add_argument("--force", action="store_true")
    _args = _parser.parse_args()
    run(DB_PATH, _args.vault_root, force=_args.force)
