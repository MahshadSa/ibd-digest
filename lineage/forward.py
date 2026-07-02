"""Forward walk: works citing the seed and the selected groundwork papers.

The backward walk cannot see past the seed (a 2025 review cites nothing newer
than ~2019), so the trajectory has no frontier. This stage fetches the works
CITING the seed and each selected groundwork paper, giving the "where is it
heading" half of the big picture. Far cheaper than the backward walk: one
paginated request per target instead of one request per reference.

Same injectable-fetch pattern as resolve/traverse: build_forward takes a
fetch_citing callable (work_id -> list of raw work dicts); the live
implementation is openalex.http_fetch_citing. Results are written to the
runs/{run_id}.forward.json sidecar; the crawl run file is never mutated.
"""
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from lineage import store
from lineage.resolve import to_node

logger = logging.getLogger(__name__)

FetchCiting = Callable[[str], list[dict]]

# Fields meaningless on a citer node (they describe the backward walk).
_BACKWARD_ONLY = ("referenced_works", "depth", "in_degree", "phase")


def forward_targets(run: dict, selection: dict | None) -> list[str]:
    """Seed plus the selection's groundwork ids (ids not in the run are dropped)."""
    seed_id = run["seed"]["openalex_id"]
    targets = [seed_id]
    if selection:
        run_ids = {n["openalex_id"] for n in run["nodes"]}
        for sel in selection.get("selections", []):
            oid = sel.get("openalex_id")
            if oid == seed_id or oid in targets:
                continue
            if oid not in run_ids:
                logger.warning("Selection id %s not in run; dropping from targets", oid)
                continue
            targets.append(oid)
    return targets


def _citer_node(work: dict) -> dict:
    node = to_node(work, depth=0)
    for field in _BACKWARD_ONLY:
        node.pop(field, None)
    return node


def build_forward(run: dict, target_ids: list[str], fetch_citing: FetchCiting) -> dict:
    """Fetch citing works per target and assemble the forward block. Does not write."""
    citers: dict[str, dict] = {}
    targets: list[dict] = []
    for tid in target_ids:
        works = fetch_citing(tid)
        ids: list[str] = []
        for work in works:
            node = _citer_node(work)
            oid = node["openalex_id"]
            citers.setdefault(oid, node)
            if oid not in ids:
                ids.append(oid)
        targets.append({"openalex_id": tid, "citer_ids": ids})
        logger.info("Target %s: %d citing works", tid, len(ids))
    return {
        "schema_version": 1,
        "run_id": run["run_id"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "targets": targets,
        "citers": list(citers.values()),
        "meta": {"target_count": len(targets), "citer_count": len(citers)},
    }


if __name__ == "__main__":
    import sys

    from lineage import openalex

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    if len(sys.argv) < 2:
        sys.exit("usage: python -m lineage.forward <run_file>")
    _run_file = Path(sys.argv[1])
    _run = store.read_run(_run_file)
    try:
        _selection = store.read_selection(_run["run_id"], _run_file.parent)
    except FileNotFoundError:
        logger.info("No selection sidecar; forward walk covers the seed only")
        _selection = None
    _targets = forward_targets(_run, _selection)
    _fwd = build_forward(_run, _targets, openalex.http_fetch_citing)
    _path = store.write_forward(_fwd, _run["run_id"], _run_file.parent)
    logger.info(
        "Wrote %s: %d targets, %d citing works",
        _path,
        _fwd["meta"]["target_count"],
        _fwd["meta"]["citer_count"],
    )
