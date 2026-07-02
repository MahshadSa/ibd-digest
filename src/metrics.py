"""Per-run telemetry: one committed text line per scheduled run.

Appends a line to data/metrics.txt with the day's new-paper count, per-tier
counts, and the tier thresholds this run calibrated. Threshold drift and
source-expansion effects become a plottable file instead of ad-hoc archaeology,
and a silent degradation (empty corpus, empty fetch) shows up as an anomalous
line. Re-running for a date replaces that date's line, so the file stays one
line per day.
"""
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from src.db import get_connection, get_meta

logger = logging.getLogger(__name__)

DB_PATH = "data/papers.db"
METRICS_PATH = "data/metrics.txt"


def run(db_path: str, out_path: str, target_date: date | None = None) -> str:
    """Record the day's metrics line. Returns the line written."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()
    day = target_date.isoformat()

    conn = get_connection(db_path)
    counts = {"must-read": 0, "skim": 0, "archive": 0}
    total = 0
    for row in conn.execute(
        "SELECT tier, COUNT(*) AS n FROM papers WHERE seen_date = ? GROUP BY tier",
        (day,),
    ):
        total += row["n"]
        if row["tier"] in counts:
            counts[row["tier"]] += row["n"]
    thr_must = get_meta(conn, "tier_threshold_must") or "n/a"
    thr_skim = get_meta(conn, "tier_threshold_skim") or "n/a"
    conn.close()

    line = (
        f"{day} new={total} must={counts['must-read']} skim={counts['skim']}"
        f" archive={counts['archive']} thr_must={thr_must} thr_skim={thr_skim}"
    )

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [l for l in existing if l.strip() and not l.startswith(day)]
    path.write_text("\n".join(kept + [line]) + "\n", encoding="utf-8")
    logger.info("Metrics recorded: %s", line)
    return line


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    _out = sys.argv[2] if len(sys.argv) > 2 else METRICS_PATH
    run(_db, _out)
