"""Multi-seed merge: union independent crawls of the same topic into one run.

A single capped crawl has degenerate in_degree (everything is 1), so "which of
these papers are the pillars" has no structural signal. Independent trees
overlapping is real co-citation evidence: a paper cited by multiple seeds'
reference trees is a shared ancestor, an honest structural definition of "main
study on this topic". The merge unions nodes by openalex_id (keeping the
lowest depth), unions edges, recomputes in_degree across the merged graph, and
stamps each node with seed_count (how many source runs contain it).

The merged dict conforms to the run schema (v2, pre-annotated), so select,
timeline, forward, and dossier all work on it unchanged. Written via
store.write_run like any crawl; the source runs are never mutated.
"""
import logging
from datetime import date, datetime

from lineage import store
from lineage.prune import _kept_subgraph_in_degree, _phase

logger = logging.getLogger(__name__)


def merge_runs(runs: list[dict], topic: str) -> dict:
    """Merge crawl runs of sibling seeds into one v2 run dict. Does not write."""
    if not runs:
        raise ValueError("no runs to merge")

    nodes: dict[str, dict] = {}
    seed_counts: dict[str, int] = {}
    edges: list[list[str]] = []
    seen_edges: set[tuple[str, str]] = set()

    for run in runs:
        for node in run["nodes"]:
            oid = node["openalex_id"]
            seed_counts[oid] = seed_counts.get(oid, 0) + 1
            existing = nodes.get(oid)
            if existing is None or node["depth"] < existing["depth"]:
                nodes[oid] = dict(node)
        for citing, referenced in run["edges"]:
            if (citing, referenced) not in seen_edges:
                seen_edges.add((citing, referenced))
                edges.append([citing, referenced])

    merged_nodes = list(nodes.values())
    for node in merged_nodes:
        node["kept"] = True
        node["seed_count"] = seed_counts[node["openalex_id"]]
        node["phase"] = _phase(node.get("pub_year"))
    in_deg = _kept_subgraph_in_degree(merged_nodes, edges)
    for node in merged_nodes:
        node["in_degree"] = in_deg[node["openalex_id"]]

    shared = sum(1 for n in merged_nodes if n["seed_count"] >= 2)
    logger.info(
        "Merged %d runs: %d nodes (%d shared across trees), %d edges",
        len(runs),
        len(merged_nodes),
        shared,
        len(edges),
    )

    return {
        "schema_version": 2,
        "run_id": f"{store.slugify(topic)}-merged-{date.today():%Y%m%d}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "seed": dict(runs[0]["seed"]),
        "depth": max(run["depth"] for run in runs),
        "top_k": max(run.get("top_k", 0) for run in runs),
        "nodes": merged_nodes,
        "edges": edges,
        "meta": {
            "node_count": len(merged_nodes),
            "edge_count": len(edges),
            "kept_count": len(merged_nodes),
            "pruned_count": 0,
            "shared_node_count": shared,
            "seeds": [dict(run["seed"]) for run in runs],
            "merged_from": [run["run_id"] for run in runs],
            "unresolved_count": sum(
                run["meta"].get("unresolved_count", 0) for run in runs
            ),
            "failed_count": sum(run["meta"].get("failed_count", 0) for run in runs),
        },
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    if len(sys.argv) < 3:
        sys.exit("usage: python -m lineage.merge <topic> <run_file> [<run_file>...]")
    _topic = sys.argv[1]
    _runs = [store.read_run(p) for p in sys.argv[2:]]
    _merged = merge_runs(_runs, _topic)
    _path = store.write_run(_merged)
    logger.info("Wrote %s", _path)
