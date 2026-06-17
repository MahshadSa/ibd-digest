"""Stage 3: coarse prune (annotation pass) plus stage-4 era phases.

v1 does not reduce the graph. There is no honest per-node ordering for a
depth-2 cut: in_degree is degenerate on these top_k-bounded tree-like graphs,
seed-anchored cosine is the wrong axis (the abstract re-run settled that), and
citation_count keeps famous off-thread classics (Kaplan-Meier, cancer-incidence
reference works) while dropping low-cited on-thread imaging papers, which is the
fatal direction since an absent node cannot be narrated. Depth-2 is already
bounded at traversal by top_k, so v1 keeps everything: seed, all depth-1, all
depth-2. The pruner annotates (kept, in_degree, phase) and never deletes;
pruned_count=0 is a real result, not a stub. A real cut waits until a rendered
note proves too busy to read; the structural cut to try then is charting only
in_degree>=2 shared ancestors (reframe #1), at which point the graph-enrichment
cost is justified. See the lineage section of CLAUDE.md for the full reasoning.
"""
import logging

from lineage import store

logger = logging.getLogger(__name__)


def _kept_subgraph_in_degree(nodes: list[dict], edges: list[list[str]]) -> dict[str, int]:
    """In-degree counting only edges whose endpoints are both kept.

    v1 keeps every node so this equals the full-graph in-degree, but the
    kept-only filter is what makes it correct once a future cut sets some
    nodes kept=False. Stored as a structural field, not used in any keep
    decision.
    """
    kept = {n["openalex_id"] for n in nodes if n["kept"]}
    counts = {n["openalex_id"]: 0 for n in nodes}
    for citing, referenced in edges:
        if citing in kept and referenced in kept:
            counts[referenced] += 1
    return counts


def _phase(pub_year: int | None) -> int | None:
    """Era phase as the decade start year (1976 -> 1970), or None if undated."""
    if not pub_year:
        return None
    return (pub_year // 10) * 10


def prune(run: dict) -> dict:
    """Annotate a run in place and upgrade it to schema_version 2.

    Sets kept on every node (v1 keep-rule: seed, all depth-1, all depth-2, no
    cut), recomputes in_degree over the kept subgraph, assigns era phases from
    pub_year, and records kept_count/pruned_count in meta. Idempotent.
    """
    nodes = run["nodes"]
    for n in nodes:
        n["kept"] = True
    in_deg = _kept_subgraph_in_degree(nodes, run["edges"])
    for n in nodes:
        n["in_degree"] = in_deg[n["openalex_id"]]
        n["phase"] = _phase(n.get("pub_year"))
    kept_count = sum(1 for n in nodes if n["kept"])
    run["meta"]["kept_count"] = kept_count
    run["meta"]["pruned_count"] = len(nodes) - kept_count
    run["schema_version"] = 2
    return run


if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for arg in sys.argv[1:]:
        run = store.read_run(arg)
        prune(run)
        out = store.update_run(run, runs_dir=Path(arg).parent)
        logger.info(
            "Pruned %s: %d kept, %d pruned, schema_version %d",
            out,
            run["meta"]["kept_count"],
            run["meta"]["pruned_count"],
            run["schema_version"],
        )
