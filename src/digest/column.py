"""Weekly column packet: one prep note per completed week.

Collects the week's must-read papers plus every paper with a checked box
(Relevant or Read later) from the seven daily digests of the last completed
ISO week into Inbox/Column/{year}-W{week}.md, deduplicated by DOI. Turns
"gather material for the column" from a manual sweep of seven notes into
reading one generated note. Write-once: the packet is written the first run
after the week completes and never overwritten (it may carry hand notes).
"""
import argparse
import logging
import pathlib
from datetime import date, datetime, timedelta, timezone

from src.digest.blocks import TITLE_RE, parse_block

logger = logging.getLogger(__name__)

_SECTION_BANNERS = [
    ("> [!important]", "must-read"),
    ("> [!note]", "skim"),
    ("> [!question]", "wildcard"),
    ("> [!abstract]-", "archive"),
]


def last_completed_week(today: date) -> date:
    """Monday of the most recent fully completed ISO week."""
    return today - timedelta(days=today.weekday() + 7)


def _blocks_with_sections(lines: list[str]) -> list[tuple[list[str], str | None]]:
    result: list[tuple[list[str], str | None]] = []
    section: str | None = None
    current: list[str] | None = None
    for line in lines:
        for banner, name in _SECTION_BANNERS:
            if line.startswith(banner):
                section = name
                break
        if TITLE_RE.match(line):
            if current is not None:
                result.append((current, result_section))
            current = [line]
            result_section = section
        elif current is not None:
            current.append(line)
    if current is not None:
        result.append((current, result_section))
    return result


def collect_week(vault_root: str, monday: date) -> list[dict]:
    """Aggregate the week's must-read and ticked papers, deduplicated by DOI."""
    papers_dir = pathlib.Path(vault_root) / "Inbox" / "Papers"
    by_doi: dict[str, dict] = {}
    for offset in range(7):
        d = monday + timedelta(days=offset)
        digest_path = papers_dir / f"{d.isoformat()}.md"
        if not digest_path.exists():
            continue
        lines = digest_path.read_text(encoding="utf-8").splitlines()
        for block, section in _blocks_with_sections(lines):
            parsed = parse_block(block)
            if not parsed["doi"]:
                continue
            flags = {
                "must_read": section == "must-read",
                "relevant": parsed["relevant_checked"],
                "read_later": parsed["read_later_checked"],
            }
            if not any(flags.values()):
                continue
            entry = by_doi.setdefault(
                parsed["doi"],
                {**parsed, **flags, "digest_date": d},
            )
            for key, value in flags.items():
                entry[key] = entry[key] or value
    return list(by_doi.values())


def _entry_line(entry: dict) -> str:
    doi_url = f"https://doi.org/{entry['doi']}"
    bits = [f"- **{entry['title']}**"]
    if entry["authors"]:
        bits.append(f" -- {entry['authors']}.")
    if entry["journal"]:
        bits.append(f" {entry['journal']} | {entry['pub_date']}.")
    bits.append(f" [{entry['doi']}]({doi_url})")
    if entry["score"]:
        bits.append(f" | Score: {entry['score']}")
    bits.append(f" (from [[Inbox/Papers/{entry['digest_date'].isoformat()}]])")
    return "".join(bits)


def render_packet(entries: list[dict], monday: date) -> str:
    iso = monday.isocalendar()
    sunday = monday + timedelta(days=6)
    lines = [
        f"# Column packet - {iso.year}-W{iso.week:02d}",
        "",
        f"Week {monday.isoformat()} to {sunday.isoformat()}. "
        f"{len(entries)} paper(s) collected.",
        "",
    ]
    sections = [
        ("Must-read this week", "must_read"),
        ("Marked relevant", "relevant"),
        ("Queued to read", "read_later"),
    ]
    any_section = False
    for heading, flag in sections:
        members = [e for e in entries if e[flag]]
        if not members:
            continue
        any_section = True
        lines.append(f"## {heading}")
        lines.append("")
        lines.extend(_entry_line(e) for e in members)
        lines.append("")
    if not any_section:
        lines.append("No must-read or ticked papers this week.")
        lines.append("")
    return "\n".join(lines)


def run(vault_root: str, today: date | None = None, force: bool = False) -> pathlib.Path | None:
    """Write the last completed week's packet if missing. Returns the path, or None if skipped."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    monday = last_completed_week(today)
    iso = monday.isocalendar()
    out_dir = pathlib.Path(vault_root) / "Inbox" / "Column"
    out_path = out_dir / f"{iso.year}-W{iso.week:02d}.md"
    if out_path.exists() and not force:
        logger.info("Packet already exists, skipping: %s", out_path)
        return None
    entries = collect_week(vault_root, monday)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_packet(entries, monday), encoding="utf-8")
    logger.info("Column packet written: %s (%d papers)", out_path, len(entries))
    return out_path


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
    run(_args.vault_root, force=_args.force)
