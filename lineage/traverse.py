"""Stage 2: backward reference walk from a seed node.

The seed is depth 0; its referenced works are depth 1; theirs are depth 2.
Depth-2 nodes are fetched for metadata but not expanded further. Each unique
work is fetched once; on re-encounter the first (lowest) depth is kept and the
edge is still recorded. build_run assembles the run dict; only the __main__
guard performs live IO and persistence via store.
"""
import logging
from datetime import date, datetime

from lineage import store
from lineage.resolve import Fetch, WorkNotFound, resolve, to_node

logger = logging.getLogger(__name__)


def traverse(seed_node: dict, fetch: Fetch, depth: int = 2) -> dict:
    """Walk references breadth-first to the given depth.

    Returns {nodes, edges, unresolved_ids}. nodes are in-memory (still carry
    referenced_works); edges are [citing_id, referenced_id] pairs for every
    depth-0 and depth-1 parent. A reference that 404s (WorkNotFound) is skipped
    and recorded in unresolved_ids: no node, no edge, so the graph stays
    consistent. Other fetch errors propagate and abort the walk.
    """
    nodes: dict[str, dict] = {seed_node["openalex_id"]: seed_node}
    edges: list[list[str]] = []
    unresolved: dict[str, None] = {}
    frontier = [seed_node]

    for d in range(1, depth + 1):
        next_frontier: list[dict] = []
        for parent in frontier:
            for ref_id in parent["referenced_works"]:
                if ref_id in nodes:
                    edges.append([parent["openalex_id"], ref_id])
                    continue
                if ref_id in unresolved:
                    continue
                try:
                    work = fetch(ref_id)
                except WorkNotFound:
                    logger.warning(
                        "Skipping unresolved reference %s (cited by %s)",
                        ref_id,
                        parent["openalex_id"],
                    )
                    unresolved[ref_id] = None
                    continue
                child = to_node(work, depth=d)
                nodes[ref_id] = child
                edges.append([parent["openalex_id"], ref_id])
                next_frontier.append(child)
        logger.info("Depth %d: %d new nodes", d, len(next_frontier))
        frontier = next_frontier

    return {"nodes": list(nodes.values()), "edges": edges, "unresolved_ids": list(unresolved)}


def _strip(node: dict) -> dict:
    """Drop the in-memory-only referenced_works field before persistence."""
    return {k: v for k, v in node.items() if k != "referenced_works"}


def build_run(seed_doi: str, fetch: Fetch, depth: int = 2) -> dict:
    """Resolve, traverse, and assemble the run dict. Does not write."""
    seed = resolve(seed_doi, fetch)
    graph = traverse(seed, fetch, depth=depth)
    nodes = [_strip(n) for n in graph["nodes"]]
    sparse_ids = [n["openalex_id"] for n in nodes if not n["ref_complete"]]
    return {
        "schema_version": 1,
        "run_id": store.make_run_id(seed["doi"] or seed_doi, date.today()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "seed": {
            "doi": seed["doi"],
            "openalex_id": seed["openalex_id"],
            "title": seed["title"],
        },
        "depth": depth,
        "nodes": nodes,
        "edges": graph["edges"],
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(graph["edges"]),
            "sparse_ids": sparse_ids,
            "unresolved_ids": graph["unresolved_ids"],
            "unresolved_count": len(graph["unresolved_ids"]),
        },
    }


if __name__ == "__main__":
    import sys

    from lineage import openalex

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _seed_doi = sys.argv[1]
    _depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    _run = build_run(_seed_doi, openalex.http_fetch, depth=_depth)
    _path = store.write_run(_run)
    logger.info(
        "Wrote %s: %d nodes, %d edges, %d sparse, %d unresolved",
        _path,
        _run["meta"]["node_count"],
        _run["meta"]["edge_count"],
        len(_run["meta"]["sparse_ids"]),
        _run["meta"]["unresolved_count"],
    )
