"""Interactive wrapper for the single-seed lineage flow.

Chains the single-paper flow into one command with a single pause for the
manual Claude paste: crawl (traverse) -> select payload -> [paste into a Claude
session, save the JSON reply to reply.json] -> ingest -> forward walk ->
dossier. run_id is computed internally so no run filename is ever typed. The two
network stages (crawl, forward walk) run on the laptop; everything else is
offline. Zero coupling to the digest.

The core is run_flow, which takes injectable fetch/fetch_citing/prompt/confirm
callables so it is testable against fixtures; __main__ wires the live OpenAlex
fetchers and real stdin prompts.
"""
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

from lineage import openalex, store
from lineage.dossier import write_note
from lineage.forward import build_forward, forward_targets
from lineage.prune import prune
from lineage.resolve import _norm_doi
from lineage.select import build_payload, ingest
from lineage.traverse import DEFAULT_TOP_K, build_run

logger = logging.getLogger(__name__)

DEFAULT_PAYLOAD = Path("payload.txt")
DEFAULT_REPLY = Path("reply.json")


def clear_scratch(paths, confirm) -> list[Path]:
    """Prompt to delete leftover scratch files from a previous run.

    Guards against ingesting a stale reply.json left over from an earlier flow.
    confirm(message) returns truthy to delete. Returns the paths deleted.
    """
    stale = [p for p in paths if p.exists()]
    if not stale:
        return []
    names = ", ".join(p.name for p in stale)
    if not confirm(f"Delete leftover scratch from a previous run ({names})? [y/N] "):
        return []
    for p in stale:
        p.unlink()
    logger.info("Deleted leftover scratch: %s", names)
    return stale


def crawl_or_reuse(doi: str, fetch, runs_dir: Path, depth: int = 2, top_k: int = DEFAULT_TOP_K):
    """Return (run, reused). Reuse today's crawl if it exists; else crawl and write.

    A same-day rerun of the same seed targets the same run file (write_run is
    append-only), so reusing it skips a redundant network walk. The run_id is
    computed from the normalized input DOI; the FileExistsError fallback covers
    the rare case where OpenAlex's canonical DOI slugifies differently.
    """
    run_id = store.make_run_id(_norm_doi(doi) or doi, date.today())
    path = Path(runs_dir) / f"{run_id}.json"
    if path.exists():
        logger.info("Reusing existing crawl %s", path)
        return store.read_run(path), True
    run = build_run(doi, fetch, depth=depth, top_k=top_k)
    try:
        store.write_run(run, runs_dir)
    except FileExistsError:
        logger.info("Crawl already on disk under resolved id; reusing")
        return store.read_run(Path(runs_dir) / f"{run['run_id']}.json"), True
    return run, False


def copy_to_clipboard(path: Path) -> bool:
    """Best-effort copy of a UTF-8 file's contents to the Windows clipboard.

    A convenience so the payload can be pasted straight into Claude; payload.txt
    is the reliable fallback, so a clipboard failure only warns.
    """
    try:
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 -LiteralPath '{path}')",
            ],
            check=True,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not copy payload to clipboard: %s", exc)
        return False


def ingest_reply(run: dict, reply_path: Path, runs_dir: Path, prompt) -> dict:
    """Block for the manual paste, then validate reply_path, retrying on bad input.

    prompt() waits for the user (a bare Enter). Loops until reply_path parses and
    validates so a fumbled paste never discards the crawl. Returns the validated
    selection block.
    """
    while True:
        prompt()
        if not reply_path.exists():
            logger.warning("%s not found; save the Claude reply there first", reply_path)
            continue
        text = reply_path.read_text(encoding="utf-8")
        try:
            ingest(run, text, runs_dir)
        except ValueError as exc:
            logger.warning("Reply not usable (%s); fix %s and press Enter", exc, reply_path)
            continue
        return store.read_selection(run["run_id"], runs_dir)


def run_flow(
    doi: str,
    *,
    fetch,
    fetch_citing,
    prompt,
    confirm,
    runs_dir: Path = Path("runs"),
    vault_root: Path = Path("."),
    payload_path: Path = DEFAULT_PAYLOAD,
    reply_path: Path = DEFAULT_REPLY,
    clipboard=copy_to_clipboard,
    force: bool = False,
) -> Path:
    """Run the whole single-seed flow, returning the dossier note path."""
    runs_dir = Path(runs_dir)
    clear_scratch([payload_path, reply_path], confirm)

    run, reused = crawl_or_reuse(doi, fetch, runs_dir)
    logger.info(
        "%s crawl %s (%d nodes)",
        "Reused" if reused else "Wrote",
        run["run_id"],
        run["meta"]["node_count"],
    )

    payload_path.write_text(build_payload(run), encoding="utf-8")
    clipboard(payload_path)
    print(
        f"\nPayload written to {payload_path} (and copied to the clipboard).\n"
        f"Paste it into a Claude session, save the JSON reply to {reply_path},\n"
        f"then press Enter here.\n",
        file=sys.stderr,
    )

    selection = ingest_reply(run, reply_path, runs_dir, prompt)

    targets = forward_targets(run, selection)
    forward = build_forward(run, targets, fetch_citing)
    store.write_forward(forward, run["run_id"], runs_dir)

    if run.get("schema_version", 1) < 2:
        prune(run)
    note = write_note(run, selection, forward, vault_root=vault_root, force=force)
    logger.info("Wrote %s", note)
    return note


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    seed_doi = args[0] if args else input("Seed DOI: ").strip()
    out = run_flow(
        seed_doi,
        fetch=openalex.http_fetch,
        fetch_citing=openalex.http_fetch_citing,
        prompt=lambda: input("Press Enter once reply.json is saved (or fixed): "),
        confirm=lambda msg: input(msg).strip().lower().startswith("y"),
        force=force,
    )
    print(out)
