"""Stage 6 half 1: emit a selection payload, ingest the pasted response.

The transport is manual, not networked. build_payload renders a pasteable
prompt block listing the kept nodes; a human pastes it into a Claude session and
pastes the model's reply back. parse_selection and validate_selection turn that
reply into a validated selection block, written to the sidecar
runs/{run_id}.selection.json. The crawl run file is never mutated.

Anti-hallucination contract: the selection the renderer consumes is only
openalex_ids plus rationale sentences. validate_selection keeps only ids present
in the run, drops the rest with a logged warning, and fails loud if the reply is
prose instead of a JSON object or carries no usable id. narrative and
coverage_gaps are free prose passed through untouched; the renderer takes every
citation fact from the run file by id, never from the pasted text.
"""
import json
import logging
import re
from pathlib import Path

from lineage import store

logger = logging.getLogger(__name__)

ABSTRACT_CHARS = 500

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)

_INSTRUCTIONS = """You are selecting the foundational papers in a citation lineage.

Seed paper: {seed_title}
Seed DOI: {seed_doi}

From the candidate papers below, select the papers that form the groundwork this
seed's field built on. Pick only from the listed papers and use only their
openalex_id values. Do not invent papers, titles, DOIs, or years.

Select 15 to 20 papers at most. That range is a ceiling, not a target: if fewer
papers are genuinely foundational, select fewer. Do not pad the list toward 20.

Keep each rationale to one short sentence. Return only the fenced JSON object
below and nothing outside it.

Reply with one fenced JSON object in exactly this form, nothing outside it:

```json
{{
  "narrative": "one short paragraph on the overall arc",
  "coverage_gaps": ["a topic or era no listed paper covers"],
  "selections": [
    {{"openalex_id": "W...", "rationale": "one sentence on this paper's role"}}
  ]
}}
```

Candidates (groundwork-likely first; depth is a hint, not a rule):
"""


def _kept_nodes(run: dict) -> list[dict]:
    return [n for n in run["nodes"] if n.get("kept", True)]


def _payload_sort_key(node: dict):
    """Groundwork-likely first: oldest year, then deeper, then title.

    pub_year ascending puts old foundational work first; undated nodes sort last
    (an unknown year cannot be judged groundwork). depth descending is a
    tiebreaker only, never a cut.
    """
    year = node.get("pub_year")
    return (year is None, year or 0, -(node.get("depth") or 0), node.get("title") or "")


def _truncate(text: str | None, limit: int = ABSTRACT_CHARS) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "..."


def build_payload(run: dict) -> str:
    """Render the pasteable prompt block for the selection session."""
    seed = run["seed"]
    lines = [
        _INSTRUCTIONS.format(
            seed_title=seed.get("title") or seed["doi"], seed_doi=seed["doi"]
        )
    ]
    tree_total = len(run.get("meta", {}).get("seeds", []))
    for n in sorted(_kept_nodes(run), key=_payload_sort_key):
        year = n.get("pub_year") or "n.d."
        head = f"--- {n['openalex_id']} | {year} | depth {n.get('depth', '?')}"
        if tree_total > 1 and n.get("seed_count"):
            head += f" | in {n['seed_count']}/{tree_total} seed trees"
        lines.append(head)
        lines.append(f"Title: {n.get('title') or '(untitled)'}")
        lines.append(f"Abstract: {_truncate(n.get('abstract')) or '(none)'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_selection(text: str) -> dict:
    """Extract the response JSON object. Fails loud on prose.

    Accepts a fenced ```json block or a bare JSON object. Raises ValueError if
    no JSON object can be parsed (the reply was prose, not an id list).
    """
    match = _FENCE.search(text)
    candidate = match.group(1) if match else text.strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"expected a fenced JSON object, got prose: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def validate_selection(parsed: dict, run: dict) -> dict:
    """Keep only selections whose openalex_id is in the run; drop the rest.

    Returns a clean block {narrative, coverage_gaps, selections}. Unknown or
    duplicate ids are dropped with a logged warning. Raises ValueError if the
    reply has no selections list or none survive validation.
    """
    sels = parsed.get("selections")
    if not isinstance(sels, list) or not sels:
        raise ValueError("response has no 'selections' list")
    valid_ids = {n["openalex_id"] for n in run["nodes"]}
    kept: list[dict] = []
    seen: set[str] = set()
    for sel in sels:
        oid = sel.get("openalex_id") if isinstance(sel, dict) else None
        if oid not in valid_ids:
            logger.warning("Dropping selection not in run: %r", oid)
            continue
        if oid in seen:
            logger.warning("Dropping duplicate selection: %s", oid)
            continue
        seen.add(oid)
        kept.append({"openalex_id": oid, "rationale": (sel.get("rationale") or "").strip()})
    if not kept:
        raise ValueError("no selection survived validation (no id matched the run)")
    gaps = parsed.get("coverage_gaps") or []
    if not isinstance(gaps, list):
        gaps = []
    return {
        "narrative": (parsed.get("narrative") or "").strip(),
        "coverage_gaps": [str(g).strip() for g in gaps if str(g).strip()],
        "selections": kept,
    }


def ingest(run: dict, response_text: str, runs_dir: Path) -> Path:
    """Parse, validate, and persist a selection to the sidecar. No run mutation."""
    block = validate_selection(parse_selection(response_text), run)
    block["run_id"] = run["run_id"]
    path = store.write_selection(block, run["run_id"], runs_dir)
    logger.info("Wrote %s: %d selections", path, len(block["selections"]))
    return path


def _force_utf8(stream) -> None:
    """Force a text stream to UTF-8 so payloads survive non-cp1252 abstracts.

    The Windows console defaults to cp1252; writing a payload with characters
    outside it raises UnicodeEncodeError mid-write and truncates the output.
    Guarded for streams that predate io.TextIOWrapper.reconfigure.
    """
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = sys.argv[1:]
    if args and args[0] == "ingest":
        if len(args) < 2:
            sys.exit("usage: python -m lineage.select ingest <run_file> [response_file]")
        run = store.read_run(args[1])
        text = Path(args[2]).read_text(encoding="utf-8") if len(args) > 2 else sys.stdin.read()
        ingest(run, text, Path(args[1]).parent)
    elif args:
        run = store.read_run(args[0])
        _force_utf8(sys.stdout)
        sys.stdout.write(build_payload(run))
    else:
        sys.exit(
            "usage: python -m lineage.select <run_file>            (print payload)\n"
            "       python -m lineage.select ingest <run_file> [response_file]"
        )
