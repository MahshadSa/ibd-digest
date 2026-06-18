"""Stage 5: deterministic render of a pruned (v2) run to an Obsidian note.

Reads one pruned run and writes Inbox/Lineages/{slug}-{date}.md: a Mermaid
flowchart grouped into decade subgraphs (oldest to newest, seed styled) followed
by a bulleted trajectory. No network, no SPECTER2, no LLM (the narrative pass is
stage 6, out of scope here). stdlib plus lineage.store only.

LEGIBILITY (a finding, not a defect). Reframe 2 keeps every node by design, so
the chart renders all of them (190 and 217 on the two real seeds). At that scale
the single flowchart is NOT legible: a 90+ node 2000s decade plus ~200 mostly
tree edges is a hairball, and short labels make individual nodes readable, not
the chart. That unreadability is the exit-condition signal reframe 2 exists to
surface. We do not cap or drop here. The trajectory text is the readable
artifact. If the rendered note proves too busy, the cut to try is charting only
in_degree>=2 shared ancestors (7 to 10 nodes on the real graphs); not built now.
See the lineage section of CLAUDE.md.

mermaid() and trajectory() both consume group_by_phase() so their orderings
cannot drift.
"""
import logging
from datetime import date
from pathlib import Path

from lineage import store
from lineage.prune import prune

logger = logging.getLogger(__name__)


def _phase_label(phase: int | None) -> str:
    return "Undated" if phase is None else f"{phase}s"


def group_by_phase(run: dict) -> list[dict]:
    """Order kept nodes into decade groups, the single source of ordering.

    Returns a list of {"phase", "label", "nodes"}, decades oldest to newest with
    the Undated (no pub_year) group trailing. Nodes within a group are sorted by
    (pub_year, title). Both mermaid() and trajectory() iterate this so the chart
    and the text can never disagree on grouping or order.
    """
    groups: dict[int | None, list[dict]] = {}
    for n in run["nodes"]:
        if n.get("kept", True):
            groups.setdefault(n.get("phase"), []).append(n)
    order = sorted(p for p in groups if p is not None)
    if None in groups:
        order.append(None)
    result = []
    for phase in order:
        members = sorted(
            groups[phase], key=lambda n: (n.get("pub_year") or 0, n.get("title") or "")
        )
        result.append({"phase": phase, "label": _phase_label(phase), "nodes": members})
    return result


def _surname(author: str) -> str:
    parts = author.split()
    return parts[-1] if parts else author


def build_label(node: dict) -> str:
    """Short Mermaid node label: first-author surname + year.

    Full titles (median ~80, max ~250 chars) are unusable as node labels; the
    full title and author list live in the trajectory bullets instead. Falls
    back to the openalex_id when a node has no authors.
    """
    authors = node.get("authors") or []
    who = _surname(authors[0]) if authors else node["openalex_id"]
    year = node.get("pub_year") or "n.d."
    return f"{who} {year}"


def _mermaid_label(text: str) -> str:
    """Sanitize a label for a double-quoted Mermaid node."""
    return text.replace('"', "'").replace("\n", " ").strip()


def _era_id(phase: int | None) -> str:
    return "era_undated" if phase is None else f"era_{phase}"


def mermaid(run: dict) -> str:
    seed_id = run["seed"]["openalex_id"]
    groups = group_by_phase(run)
    lines = ["```mermaid", "flowchart TB"]
    for g in groups:
        lines.append(f'  subgraph {_era_id(g["phase"])}["{g["label"]}"]')
        for n in g["nodes"]:
            label = _mermaid_label(build_label(n))
            if n["openalex_id"] == seed_id:
                label = f"SEED: {label}"
            lines.append(f'    {n["openalex_id"]}["{label}"]')
        lines.append("  end")
    kept = {n["openalex_id"] for n in run["nodes"] if n.get("kept", True)}
    for citing, referenced in run["edges"]:
        if citing in kept and referenced in kept:
            lines.append(f"  {citing} --> {referenced}")
    lines.append("  classDef seed fill:#ffd54f,stroke:#333,stroke-width:3px;")
    lines.append(f"  class {seed_id} seed;")
    lines.append("```")
    return "\n".join(lines)


def _authors_text(node: dict) -> str:
    authors = node.get("authors") or []
    if not authors:
        return ""
    return authors[0] + (" et al." if len(authors) > 1 else "")


def trajectory(run: dict) -> str:
    seed_id = run["seed"]["openalex_id"]
    groups = group_by_phase(run)
    lines = ["## Trajectory", ""]
    for g in groups:
        lines.append(f"### {g['label']}")
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
            bits.append(f"in-degree {n.get('in_degree', 0)}")
            bits.append(f"cited by {n.get('citation_count', 0)}")
            meta = ", ".join(bits)
            doi = n.get("doi")
            link = f" [{doi}](https://doi.org/{doi})" if doi else ""
            lines.append(f"- **{title}** -- {meta}.{link}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_note(run: dict) -> str:
    seed = run["seed"]
    groups = group_by_phase(run)
    dated = [g["phase"] for g in groups if g["phase"] is not None]
    kept = sum(1 for n in run["nodes"] if n.get("kept", True))
    span = f"{dated[0]}s to {dated[-1]}s" if dated else "undated"
    header = [
        f"# Lineage: {seed.get('title') or seed['doi']}",
        "",
        f"Seed: [{seed['doi']}](https://doi.org/{seed['doi']})",
        f"Generated {date.today():%Y-%m-%d} from run `{run['run_id']}`.",
        f"{kept} nodes across {len(dated)} eras ({span}); {len(run['edges'])} edges.",
        "",
    ]
    return "\n".join(header) + mermaid(run) + "\n\n" + trajectory(run)


def write_note(run: dict, vault_root: Path = Path("."), force: bool = False) -> Path:
    """Write the rendered note to Inbox/Lineages/{slug}-{date}.md.

    Refuses to overwrite an existing note unless force is set (the note may carry
    hand annotations); regenerating is then explicit, like the digest writer.
    """
    slug = store.slugify(run["seed"]["doi"])
    path = Path(vault_root) / "Inbox" / "Lineages" / f"{slug}-{date.today():%Y-%m-%d}.md"
    if path.exists() and not force:
        raise FileExistsError(f"note already exists: {path}; pass --force to regenerate")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_note(run), encoding="utf-8")
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
        sys.exit("usage: python -m lineage.render <run_file> [vault_root] [--force]")
    run_file = args[0]
    vault_root = Path(args[1]) if len(args) > 1 else Path(".")
    run = store.read_run(run_file)
    if run.get("schema_version", 1) < 2:
        logger.info("Run %s is unpruned (v1); pruning in memory before render", run_file)
        prune(run)
    out = write_note(run, vault_root=vault_root, force=force)
    logger.info("Wrote %s", out)
