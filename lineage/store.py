"""Run-file storage contract.

All run IO goes through this module. Each run writes exactly one JSON file at
runs/{run_id}.json, append-only: write_run refuses to overwrite an existing
file. Regenerating a run is an explicit delete-then-rerun. run_id is
{slug}-{YYYYMMDD}, so a same-day rerun targets the same filename and the guard
forces the deliberate delete.
"""
import json
import re
from datetime import date
from pathlib import Path

REQUIRED_KEYS = frozenset(
    {"schema_version", "run_id", "created_at", "seed", "depth", "nodes", "edges", "meta"}
)


def slugify(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")


def make_run_id(doi: str, when: date) -> str:
    return f"{slugify(doi)}-{when:%Y%m%d}"


def write_run(run: dict, runs_dir: Path = Path("runs")) -> Path:
    """Write a run dict to runs/{run_id}.json. Refuses to overwrite."""
    missing = REQUIRED_KEYS - run.keys()
    if missing:
        raise ValueError(f"run missing required keys: {sorted(missing)}")
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run['run_id']}.json"
    if path.exists():
        raise FileExistsError(f"run file already exists: {path}; delete to regenerate")
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_run(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
