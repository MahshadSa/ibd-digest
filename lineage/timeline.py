"""Stage 6 half 2: render the selected papers as a decade-grouped timeline.

Reads the immutable crawl run file plus the sidecar selection block and joins
them by openalex_id. No Mermaid: the real graph is a near-tree with no
meaningful branching, so a decade timeline is the honest artifact and converts
cleanly to a visual post. group_by_phase (from render.py) is reused as the
single ordering source so the timeline cannot drift from the stage-5 grouping.

Anti-hallucination contract: every citation fact (title, authors, year, DOI)
comes from the run node looked up by id; the sidecar contributes only ids,
rationale sentences, the narrative, and coverage gaps. A sidecar id absent from
the live run is dropped with a logged warning, because a sidecar can outlive a
re-crawl of its seed. stdlib plus lineage.store, lineage.prune, lineage.render.
"""
import logging
from datetime import date
from pathlib import Path

from lineage import store
from lineage.prune import prune
from lineage.render import group_by_phase

logger = logging.getLogger(__name__)


def _authors_text(node: dict) -> str:
    authors = node.get("authors") or []
    if not authors:
        return ""
    return authors[0] + (" et al." if len(authors) > 1 else "")


def selected_nodes(run: dict, selection: dict) -> tuple[list[dict], dict[str, str]]:
    """Resolve sidecar ids against the live run, dropping unknowns with a warning.

    Returns (nodes, rationales) where nodes are the run nodes for surviving ids
    and rationales maps openalex_id to its rationale sentence.
    """
    by_id = {n["openalex_id"]: n for n in run["nodes"]}
    nodes: list[dict] = []
    rationales: dict[str, str] = {}
    for sel in selection["selections"]:
        oid = sel["openalex_id"]
        node = by_id.get(oid)
        if node is None:
            logger.warning("Sidecar id %s not in run %s; dropping", oid, run["run_id"])
            continue
        nodes.append(node)
        rationales[oid] = sel.get("rationale", "")
    return nodes, rationales


def render_note(run: dict, selection: dict) -> str:
    seed_id = run["seed"]["openalex_id"]
    seed = run["seed"]
    nodes, rationales = selected_nodes(run, selection)
    if not nodes:
        raise ValueError("no selected id resolved against the run; nothing to render")
    groups = group_by_phase({"nodes": nodes})
    dated = [g["phase"] for g in groups if g["phase"] is not None]
    span = f"{dated[0]}s to {dated[-1]}s" if dated else "undated"
    shared = sum(
        1 for n in run["nodes"] if n.get("kept", True) and n.get("in_degree", 0) >= 2
    )

    out = [
        f"# Lineage (selected): {seed.get('title') or seed['doi']}",
        "",
        f"Seed: [{seed['doi']}](https://doi.org/{seed['doi']})",
        f"Generated {date.today():%Y-%m-%d} from run `{run['run_id']}` "
        f"and selection `{run['run_id']}.selection.json`.",
        f"{len(nodes)} selected papers across {len(dated)} eras ({span}).",
        "",
    ]
    if selection.get("narrative"):
        out += [selection["narrative"], ""]
    out.append("## Timeline")
    out.append("")
    for g in groups:
        out.append(f"### {g['label']}")
        for n in g["nodes"]:
            title = n.get("title") or "(untitled)"
            if n["openalex_id"] == seed_id:
                title = f"SEED: {title}"
            bits = []
            who = _authors_text(n)
            if who:
                bits.append(who)
            if n.get("pub_year"):
                bits.append(str(n["pub_year"]))
            meta = ", ".join(bits)
            role = rationales.get(n["openalex_id"], "")
            doi = n.get("doi")
            link = f" [{doi}](https://doi.org/{doi})" if doi else ""
            head = f"- **{title}**" + (f" -- {meta}" if meta else "")
            out.append(f"{head}. {role}{link}".rstrip())
        out.append("")
    if selection.get("coverage_gaps"):
        out.append("## Coverage gaps")
        out += [f"- {gap}" for gap in selection["coverage_gaps"]]
        out.append("")
    out.append("---")
    out.append(
        f"Exit lever (unused): {shared} kept nodes have in-degree >= 2 in the crawl; "
        "chart only those if a later timeline reads too busy."
    )
    return "\n".join(out).rstrip() + "\n"


def write_note(
    run: dict, selection: dict, vault_root: Path = Path("."), force: bool = False
) -> Path:
    """Write the selected timeline to Inbox/Lineages/{slug}-{date}-selected.md.

    A new note alongside the stage-5 chart render, which stays the raw record.
    Refuses to overwrite unless force (the note may carry hand annotations).
    """
    slug = store.slugify(run["seed"]["doi"])
    name = f"{slug}-{date.today():%Y-%m-%d}-selected.md"
    path = Path(vault_root) / "Inbox" / "Lineages" / name
    if path.exists() and not force:
        raise FileExistsError(f"note already exists: {path}; pass --force to regenerate")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_note(run, selection), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if not args:
        sys.exit("usage: python -m lineage.timeline <run_file> [vault_root] [--force]")
    run_file = args[0]
    vault_root = Path(args[1]) if len(args) > 1 else Path(".")
    run = store.read_run(run_file)
    if run.get("schema_version", 1) < 2:
        logger.info("Run %s is unpruned (v1); pruning in memory for phases", run_file)
        prune(run)
    selection = store.read_selection(run["run_id"], Path(run_file).parent)
    out = write_note(run, selection, vault_root=vault_root, force=force)
    logger.info("Wrote %s", out)
