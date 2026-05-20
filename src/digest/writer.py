import json
import logging
import pathlib
import sqlite3
import sys
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = "data/papers.db"


def fetch_papers(conn: sqlite3.Connection, target_date: date) -> list[sqlite3.Row]:
    """Return all rows from papers where seen_date == target_date, ordered by source, title."""
    return conn.execute(
        "SELECT * FROM papers WHERE seen_date = ? ORDER BY source, title",
        (target_date.isoformat(),),
    ).fetchall()


def format_authors(authors_json: str, corresponding_author: str | None) -> str:
    """Build display string: first two authors + corresponding author if not already included."""
    authors: list[str] = json.loads(authors_json)
    display = authors[:2]
    if corresponding_author and corresponding_author not in display:
        display.append(corresponding_author)
    return ", ".join(display)


def render_paper(paper: sqlite3.Row) -> str:
    """Render one paper as a Markdown block."""
    doi_url = f"https://doi.org/{paper['doi']}"
    authors_str = format_authors(paper["authors"], paper["corresponding_author"])
    abstract = paper["abstract"] or ""

    callout_body = abstract if abstract else "No abstract available."
    callout_lines = "\n".join(f"> {line}" for line in callout_body.splitlines())

    return (
        f"### {paper['title']}\n"
        f"\n"
        f"[{paper['doi']}]({doi_url})  \n"
        f"**Authors:** {authors_str}  \n"
        f"**Journal:** {paper['journal']} | **Date:** {paper['pub_date']}\n"
        f"\n"
        f"> [!abstract]-\n"
        f"{callout_lines}\n"
        f"\n"
        f"- [ ] Relevant\n"
    )


def render_digest(papers: list[sqlite3.Row], target_date: date) -> str:
    """Render the complete digest: header, paper blocks, footer with per-source counts."""
    date_str = target_date.isoformat()

    header = (
        f"# IBD Imaging Digest - {date_str}\n"
        f"\n"
        f"**Date:** {date_str}  \n"
        f"**New papers:** {len(papers)}\n"
        f"\n"
        f"---\n"
        f"\n"
    )

    if not papers:
        return header + "No new papers today, pipeline ran successfully.\n"

    paper_blocks = []
    for i, paper in enumerate(papers):
        paper_blocks.append(render_paper(paper))
        if i < len(papers) - 1:
            paper_blocks.append("---\n\n")

    source_counts: dict[str, int] = {}
    for p in papers:
        source_counts[p["source"]] = source_counts.get(p["source"], 0) + 1
    source_str = " | ".join(
        f"{src}: {count}" for src, count in sorted(source_counts.items())
    )

    footer = f"\n---\n\n**Sources:** {source_str}\n"

    return header + "".join(paper_blocks) + footer


def write_digest(vault_root: str, content: str, target_date: date) -> pathlib.Path:
    """Write to Inbox/Papers/YYYY-MM-DD.md, overwriting if exists. Returns path."""
    out_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date.isoformat()}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def run(db_path: str, vault_root: str, target_date: date | None = None) -> None:
    """Fetch papers, render digest, write file. target_date defaults to today UTC."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        papers = fetch_papers(conn, target_date)
        logger.info("Found %d papers for %s", len(papers), target_date.isoformat())
        content = render_digest(papers, target_date)
        out_path = write_digest(vault_root, content, target_date)
        logger.info("Digest written to %s", out_path)
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _vault_root = sys.argv[1] if len(sys.argv) > 1 else "."
    run(DB_PATH, _vault_root)
