"""Run-file storage contract.

All run IO goes through this module. Each run writes exactly one JSON file at
runs/{run_id}.json. write_run is append-only: it refuses to overwrite an
existing file, so regenerating a run is an explicit delete-then-rerun.
update_run is overwrite-permitted, for stages that re-annotate an existing run
(the pruner upgrading v1 to v2); it writes atomically so an interrupted write
cannot corrupt the run. run_id is {slug}-{YYYYMMDD}, so a same-day rerun
targets the same filename.
"""
import json
import os
import re
import tempfile
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


def update_run(run: dict, runs_dir: Path = Path("runs")) -> Path:
    """Write a run dict to runs/{run_id}.json, overwriting if present.

    Unlike write_run (append-only), update_run permits overwrite, for stages
    that re-annotate an existing run such as the pruner upgrading v1 to v2.
    Atomic: writes a temp file in the same directory and renames over the
    target, so an interrupted write leaves the existing run intact.
    """
    missing = REQUIRED_KEYS - run.keys()
    if missing:
        raise ValueError(f"run missing required keys: {sorted(missing)}")
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run['run_id']}.json"
    fd, tmp = tempfile.mkstemp(dir=runs_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read_run(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def selection_path(run_id: str, runs_dir: Path = Path("runs")) -> Path:
    """Sidecar path for a run's selection block: runs/{run_id}.selection.json.

    The selection is a model judgment kept separate from the deterministic crawl
    run file, which stays immutable; re-selecting overwrites only the sidecar.
    """
    return Path(runs_dir) / f"{run_id}.selection.json"


def write_selection(block: dict, run_id: str, runs_dir: Path = Path("runs")) -> Path:
    """Write a validated selection block to the sidecar, overwriting if present.

    Atomic (temp-file-plus-rename), like update_run: an interrupted re-select
    cannot corrupt an existing sidecar. The crawl run file is never touched.
    """
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = selection_path(run_id, runs_dir)
    fd, tmp = tempfile.mkstemp(dir=runs_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(block, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read_selection(run_id: str, runs_dir: Path = Path("runs")) -> dict:
    return json.loads(selection_path(run_id, runs_dir).read_text(encoding="utf-8"))
