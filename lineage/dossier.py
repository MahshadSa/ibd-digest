"""Topic dossier: the full-big-picture note for one topic.

Combines the (usually merged) crawl run, its selection sidecar, and the
optional forward sidecar into one note under Inbox/Lineages/: narrative arc,
decade-grouped main studies, a small consensus chart (seeds plus in_degree>=2
shared ancestors, the exit-lever cut made principled by multi-seed merging), a
frontier section from the forward walk, and coverage gaps. Origins, pillars,
present, and gaps in one artifact.

Anti-hallucination contract, same as timeline: every citation fact (title,
authors, year, DOI) comes from the run or forward node looked up by id; the
selection contributes only ids, rationale sentences, narrative, and gaps.
"""
import logging
from datetime import date
from pathlib import Path

from lineage import store
from lineage.render import build_label, group_by_phase, seed_slug, _mermaid_label
from lineage.timeline import selected_nodes

logger = logging.getLogger(__name__)

FRONTIER_MAX = 20


def _authors_text(node: dict) -> str:
    authors = node.get("authors") or []
    if not authors:
        return ""
    return authors[0] + (" et al." if len(authors) > 1 else "")


def _seed_ids(run: dict) -> list[str]:
    seeds = run.get("meta", {}).get("seeds") or [run["seed"]]
    return [s["openalex_id"] for s in seeds]


def _tree_total(run: dict) -> int:
    return len(run.get("meta", {}).get("seeds") or [run["seed"]])


def consensus_chart(run: dict) -> str | None:
    """Mermaid chart of seeds plus in_degree>=2 kept nodes; None if no shared node."""
    seed_ids = set(_seed_ids(run))
    include = {
        n["openalex_id"]: n
        for n in run["nodes"]
        if n.get("kept", True)
        and (n["openalex_id"] in seed_ids or n.get("in_degree", 0) >= 2)
    }
    if not (set(include) - seed_ids):
        return None
    lines = ["```mermaid", "flowchart TB"]
    for oid, node in include.items():
        label = _mermaid_label(build_label(node))
        if oid in seed_ids:
            label = f"SEED: {label}"
        lines.append(f'  {oid}["{label}"]')
    for citing, referenced in run["edges"]:
        if citing in include and referenced in include:
            lines.append(f"  {citing} --> {referenced}")
    lines.append("  classDef seed fill:#ffd54f,stroke:#333,stroke-width:3px;")
    lines.append(f"  class {','.join(sorted(seed_ids & set(include)))} seed;")
    lines.append("```")
    return "\n".join(lines)


def frontier_nodes(run: dict, forward: dict) -> list[dict]:
    """Citing works not already inside the crawl, most recent first, capped."""
    run_ids = {n["openalex_id"] for n in run["nodes"]}
    fresh = [c for c in forward["citers"] if c["openalex_id"] not in run_ids]
    fresh.sort(
        key=lambda n: (n.get("pub_year") or 0, n.get("citation_count") or 0),
        reverse=True,
    )
    return fresh[:FRONTIER_MAX]


def _study_line(node: dict, rationale: str, seed_ids: set[str], total: int) -> str:
    title = node.get("title") or "(untitled)"
    if node["openalex_id"] in seed_ids:
        title = f"SEED: {title}"
    bits = []
    who = _authors_text(node)
    if who:
        bits.append(who)
    if node.get("pub_year"):
        bits.append(str(node["pub_year"]))
    if total > 1 and node.get("seed_count", 0) >= 2:
        bits.append(f"(in {node['seed_count']}/{total} seed trees)")
    meta = ", ".join(bits)
    doi = node.get("doi")
    link = f" [{doi}](https://doi.org/{doi})" if doi else ""
    head = f"- **{title}**" + (f" -- {meta}" if meta else "")
    return f"{head}. {rationale}{link}".rstrip()


def render_dossier(run: dict, selection: dict, forward: dict | None = None) -> str:
    seeds = run.get("meta", {}).get("seeds") or [run["seed"]]
    seed_ids = set(_seed_ids(run))
    total = _tree_total(run)
    nodes, rationales = selected_nodes(run, selection)
    if not nodes:
        raise ValueError("no selected id resolved against the run; nothing to render")
    groups = group_by_phase({"nodes": nodes})

    out = [
        f"# Topic dossier: {run['run_id']}",
        "",
        f"Generated {date.today():%Y-%m-%d} from run `{run['run_id']}`"
        f" ({run['meta'].get('node_count', len(run['nodes']))} crawled nodes,"
        f" {len(seeds)} seed tree(s)).",
        "",
        "Seeds:",
    ]
    out += [
        f"- {s.get('title') or s['doi']} [{s['doi']}](https://doi.org/{s['doi']})"
        for s in seeds
    ]
    out.append("")
    if selection.get("narrative"):
        out += [selection["narrative"], ""]

    out += ["## Main studies", ""]
    for g in groups:
        out.append(f"### {g['label']}")
        for n in g["nodes"]:
            out.append(
                _study_line(n, rationales.get(n["openalex_id"], ""), seed_ids, total)
            )
        out.append("")

    chart = consensus_chart(run)
    if chart:
        out += [
            "## Consensus chart",
            "",
            "Seeds plus the ancestors shared across trees (in-degree >= 2).",
            "",
            chart,
            "",
        ]

    if forward:
        frontier = frontier_nodes(run, forward)
        if frontier:
            out += [
                "## Frontier",
                "",
                "Recent works citing the seed or the groundwork, newest first.",
                "",
            ]
            for n in frontier:
                bits = [b for b in [
                    _authors_text(n),
                    str(n["pub_year"]) if n.get("pub_year") else "",
                    f"cited by {n.get('citation_count', 0)}",
                ] if b]
                doi = n.get("doi")
                link = f" [{doi}](https://doi.org/{doi})" if doi else ""
                out.append(f"- **{n.get('title') or '(untitled)'}** -- {', '.join(bits)}.{link}")
            out.append("")

    out += ["## Coverage gaps", ""]
    out += [f"- {gap}" for gap in selection.get("coverage_gaps", [])]
    unresolved = run["meta"].get("unresolved_count", 0)
    out.append(
        f"- Mechanical: {unresolved} unresolved reference(s) (OpenAlex 404s)"
        " across the crawl(s); these cannot appear above."
    )
    return "\n".join(out).rstrip() + "\n"


def write_note(
    run: dict,
    selection: dict,
    forward: dict | None = None,
    vault_root: Path = Path("."),
    force: bool = False,
) -> Path:
    """Write the dossier to Inbox/Lineages/{name}-dossier.md. Refuses overwrite unless force.

    A merged (multi-seed) run already has a readable topic-based run_id
    (see merge.py); a single-seed run's run_id is DOI-based (see
    store.make_run_id) and unreadable, so it is swapped for an author-year slug.
    """
    is_merged = bool(run.get("meta", {}).get("seeds"))
    name = run["run_id"] if is_merged else f"{seed_slug(run)}-{date.today():%Y-%m-%d}"
    path = Path(vault_root) / "Inbox" / "Lineages" / f"{name}-dossier.md"
    if path.exists() and not force:
        raise FileExistsError(f"note already exists: {path}; pass --force to regenerate")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dossier(run, selection, forward), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys

    from lineage.prune import prune

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if not args:
        sys.exit("usage: python -m lineage.dossier <run_file> [vault_root] [--force]")
    run_file = Path(args[0])
    vault_root = Path(args[1]) if len(args) > 1 else Path(".")
    run = store.read_run(run_file)
    if run.get("schema_version", 1) < 2:
        logger.info("Run %s is unpruned (v1); pruning in memory for phases", run_file)
        prune(run)
    selection = store.read_selection(run["run_id"], run_file.parent)
    try:
        forward = store.read_forward(run["run_id"], run_file.parent)
    except FileNotFoundError:
        logger.info("No forward sidecar; dossier renders without a frontier section")
        forward = None
    out = write_note(run, selection, forward, vault_root=vault_root, force=force)
    logger.info("Wrote %s", out)
