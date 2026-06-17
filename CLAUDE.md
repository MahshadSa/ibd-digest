# IBD Imaging Digest

Automated daily digest of new IBD imaging papers, ranked by semantic relevance to my work, delivered to my Obsidian vault, with a feedback loop that sharpens the ranker over time.

## Environment

- Python 3.11+
- 8GB RAM laptop, regional network constraints (proxy may be needed for some endpoints; set HTTPS_PROXY and HTTP_PROXY in shell before running)
- NCBI API key stored in .env, not committed
- Runs locally for development, GitHub Actions for production

## Code style

- No em dashes anywhere (code, comments, docs, commit messages)
- No emojis
- No decorative comments. Comment only when the "why" is non-obvious. Never restate what the code does.
- No verbose explanations between code blocks when responding. Show the change, brief rationale only if needed.
- Avoid typical AI-generated patterns: no excessive try/except wrapping, no defensive checks for impossible conditions, no "helper" functions that wrap one line, no over-abstraction.
- Plain, direct Python. Type hints throughout. Docstrings only on public functions, one line where possible.
- Prefer standard library over dependencies. Justify each third-party package.
- Use the logging module from the start. No print statements for logging.

## Project plan

### Goal
Daily Markdown digest of new IBD imaging papers in my Obsidian vault, with semantic ranking and a checkbox-driven feedback loop.

### Sources (v1)
- PubMed E-utilities API, using NCBI API key
- Crossref API, 17 journals (unfiltered 50-paper pull per journal):
  - Focused radiology: Radiology (0033-8419), Radiology: Artificial Intelligence (2638-6100), European Radiology (1432-1084), Investigative Radiology (1536-0210), JMRI (1522-2586), Insights into Imaging (1869-4101), AJR (1546-3141), Abdominal Radiology (2366-0058)
  - Focused IBD: Journal of Crohn's and Colitis (1876-4479), Inflammatory Bowel Diseases (1536-4844)
  - Focused imaging AI: Medical Image Analysis (1361-8415)
  - Broad (noise accepted until keyword prefilter is built): Nature Medicine (1546-170X), npj Digital Medicine (2398-6352), The Lancet Digital Health (2589-7500), Alimentary Pharmacology & Therapeutics (1365-2036), The Lancet Gastroenterology & Hepatology (2468-1253), Clinical Gastroenterology and Hepatology (1542-3565)
- Deduplication by DOI across all sources

Crossref journal policy: focused journals fetched unfiltered because hit rate is high. Broad journals included at the same 50-paper pull; a keyword prefilter is planned once observation data informs the term list (see Deferred). ISSNs are electronic except Medical Image Analysis (1361-8415) and CGH (1542-3565), whose electronic ISSNs are absent from Crossref.

### Storage
- Single SQLite database
- `papers` table: DOI (primary key), title, authors, corresponding author, journal, date, abstract, source, embedding vector, similarity score, seen date, relevance status
- `corpus` table: relevance seed set with embeddings of papers marked relevant

### Ranking
- Embedding model: SPECTER2 (local, biomedical/scientific)
- Initial corpus: 20 to 50 papers selected manually from Zotero
- Score: max cosine similarity between candidate and corpus
- Tiers (percentile-anchored to the corpus; SPECTER2 cosine sims run high for
  in-domain biomedical text, so fixed round-number thresholds do not generalize):
  - Must-read: score >= 0.958
  - Skim: 0.924 to 0.958
  - Archive: score < 0.924
- Re-check monthly as the corpus grows, and off-cycle after any source expansion

### Daily digest format
One Markdown note per day at `Inbox/Papers/YYYY-MM-DD.md` in the Obsidian vault.

Header: date, total new papers, count per tier.

For each paper in must-read and skim tiers:
- Title
- DOI as link
- Authors: first two plus corresponding author
- Journal and date
- Similarity score (numeric)
- Full abstract inside a collapsible Markdown callout
- Two independent checkboxes: `- [ ] Relevant` (feeds the corpus feedback loop)
  and `- [ ] Read later` (queues the paper into Inbox/To Read.md)

Archive tier: collapsed section, title + DOI link + authors only, no checkboxes.

Footer: source breakdown (papers per source, duplicates merged).

Empty days: note still generated, says "no new papers today, pipeline ran successfully."

### Feedback loop (NOT BUILT)
- User ticks `- [x] Relevant` on papers in the digest
- A job scans recent digest notes for checked Relevant boxes only (must not pick
  up Read later ticks; see the checkbox parsing contract)
- Extracts those DOIs, pulls embeddings, adds to corpus table
- Ranker sharpens over time
- Filter-bubble risk: corpus growth from own reading narrows scope. Mitigate by
  manually adding outside papers to the seed set periodically.

### Infrastructure
- Python project in a GitHub repo
- GitHub Actions runs the fetcher daily on a cron schedule
- Daily digest committed to the repo
- Repo syncs to Obsidian vault via git

## Build order

- [x] Step 1: Source layer (PubMed + Crossref fetchers, dedup by DOI, write to SQLite)
- [x] Step 2: Digest writer (Markdown output from SQLite, no ranking yet)
- [x] Step 3: Embedding layer (SPECTER2, corpus from Zotero selection, scoring and tiering)
- [x] Step 4: Obsidian integration (file paths, callouts, checkbox convention)
- [x] Step 5: GitHub Actions scheduling and git sync
- [ ] Step 6: Feedback loop (job parses checked Relevant boxes, updates corpus) -- NOT BUILT
- [x] Read later layer (to_read.py: parses checked Read later boxes into Inbox/To Read.md, windowed + automated)

## PubMed query (v1)

(
  (
    (
"Inflammatory Bowel Diseases"[Mesh]
OR "Crohn Disease"[Mesh]
OR "Colitis, Ulcerative"[Mesh]
OR inflammatory bowel disease[tiab]
OR Crohn[tiab]
OR "ulcerative colitis"[tiab]
OR IBD[tiab]
)
AND
(
"Magnetic Resonance Imaging"[Mesh]
OR "Diffusion Magnetic Resonance Imaging"[Mesh]
OR "Tomography, X-Ray Computed"[Mesh]
OR "Ultrasonography"[Mesh]
OR MRI[tiab]
OR MRE[tiab]
OR "magnetic resonance enterography"[tiab]
OR "MR enterography"[tiab]
OR "CT enterography"[tiab]
OR CTE[tiab]
OR "intestinal ultrasound"[tiab]
OR IUS[tiab]
OR radiomics[tiab]
OR "deep learning"[tiab]
OR "artificial intelligence"[tiab]
OR "treatment response"[tiab]
OR monitoring[tiab]
OR "disease activity"[tiab]
OR "mucosal healing"[tiab]
OR "transmural healing"[tiab]
)
)
OR
(
  (
    "Inflammatory Bowel Diseases"[Mesh]
    OR "Crohn Disease"[Mesh]
    OR "Colitis, Ulcerative"[Mesh]
  )
  AND
  (
    "Review"[Publication Type]
    OR "Practice Guideline"[Publication Type]
    OR "Guideline"[Publication Type]
    OR consensus[tiab]
    OR "position paper"[tiab]
  )
)
OR
(
  (
    "Radiology"[Journal]
    OR "Radiol Artif Intell"[Journal]
    OR "Eur Radiol"[Journal]
    OR "AJR Am J Roentgenol"[Journal]
    OR "Abdom Radiol (NY)"[Journal]
    OR "Invest Radiol"[Journal]
    OR "J Magn Reson Imaging"[Journal]
    OR "Insights Imaging"[Journal]
  )
  AND
  (
    "deep learning"[tiab]
    OR "artificial intelligence"[tiab]
    OR radiomics[tiab]
    OR "machine learning"[tiab]
    OR "large language model"[tiab]
    OR "foundation model"[tiab]
    OR "convolutional neural network"[tiab]
  )
  AND
  (
    abdomin*[tiab]
    OR gastrointestin*[tiab]
    OR bowel[tiab]
    OR intestin*[tiab]
    OR colorect*[tiab]
    OR colon*[tiab]
    OR liver[tiab]
    OR hepat*[tiab]
    OR pancrea*[tiab]
    OR pelvi*[tiab]
  )
)
OR
(
  (
    "agentic AI"[tiab]
    OR "AI agent"[tiab]
    OR "autonomous AI agent"[tiab]
    OR "agentic workflow"[tiab]
  )
  AND
  (
    radiology[tiab]
    OR "medical imaging"[tiab]
    OR diagnosis[tiab]
    OR clinical[tiab]
  )
)
)
AND English[Language]
NOT "Case Reports"[Publication Type]
AND "last 30 days"[PDat]

Scope includes adult and pediatric IBD imaging, treatment response and monitoring, plus high-level IBD reviews and guidelines. Non-IBD-gated branch added 2026-06-04: abdominal radiology AI/DL/radiomics (journal-gated to 8 radiology journals, ~32 papers/month) and agentic AI in radiology/medicine (~11 papers/month). Combined new branch: ~43 papers/month observed over last 30 days.

## Deferred (not in v1)

- LLM-generated abstract summaries
- Citation counts and altmetrics
- Author override filters (always surface specific authors regardless of score)
- Europe PMC, bioRxiv, medRxiv, arXiv sources
- Telegram or email notification for top-tier hits
- Crossref keyword prefilter for broad journals (Nature Medicine, npj Digital Medicine, Lancet Digital Health, AP&T, Lancet GI, CGH): defer until 2-4 weeks of data at expanded volume shows which terms anchor relevant papers

## Step 4: Obsidian integration (done)

Digest writer renders papers grouped by tier with Obsidian callouts.

### Rendering conventions
- Must-read tier: `> [!important]` banner, papers rendered outside the callout with `- [ ]` at column 0.
- Skim tier: `> [!note]` banner, same pattern.
- Archive tier: `> [!abstract]-` container (collapsed), papers rendered inside with `> ` prefix on every line.
- Empty tiers are skipped entirely. Header counts still show zeros.
- Each paper: `- [ ] **Title**` followed by 2-space-indented metadata (authors, journal, date, DOI, score), then a nested `> [!abstract]-` callout for the abstract.
- Abstract callout body: every line (including blank separator lines between paragraphs) must carry its own `  > ` prefix. Blank lines use `  >` with no trailing space. The writer splits the abstract on `\n` and prefixes each line individually; structured abstracts (Introduction/Methods/Results) from Crossref have leading whitespace that is stripped per line.
- DOI format is always `[10.xxxx/yyyy](https://doi.org/10.xxxx/yyyy)`.

### Checkbox parsing contract (do not break)

Two independent checkboxes per paper, parsed by two separate consumers. They
must never be confused: a `Read later` tick must never reach the corpus, and a
`Relevant` tick must never be treated as a Read later queue entry.

- `Relevant` (feeds the corpus, consumed by the feedback loop, NOT YET BUILT):
  match the checked Relevant box specifically, e.g. `^>?\s*- \[[xX]\] Relevant`.
- `Read later` (feeds Inbox/To Read.md, consumed by `to_read.py`, BUILT):
  match the checked Read later box specifically, e.g. `^>?\s*- \[[xX]\] Read later`.
- DOI extraction on the same paper block: `\[([^\]]+)\]\(https://doi\.org/[^\)]+\)`.
- Score extraction if needed: `Score: (\d+\.\d+)`.
- Both patterns must handle column-0 (must-read/skim) and `> `-prefixed (archive)
  rendering.

Any change to the writer must preserve these patterns or update both consumers
in lockstep. When the feedback loop is built, its parser must match ONLY the
Relevant box and must not pick up Read later ticks.

## Step 5: GitHub Actions scheduling, complete (2026-05-21)

Workflow: `.github/workflows/daily-digest.yml`
Schedule: `0 2 * * *` UTC (5:30 AM Tehran)
Manual trigger: `workflow_dispatch` available in Actions tab

Pipeline order: `src.fetch` -> `src.corpus from-notes` -> `src.rank` ->
`src.digest.writer . --force`. The `src.corpus from-notes` step rebuilds the
corpus embeddings from the committed `Corpus/*.md` notes on every run because
the DB is ephemeral (see DB persistence); without it the corpus table is empty
and ranking is silently skipped. The `--force` flag is required in the scheduled
run because the writer guard (added pre-Step 5) refuses to overwrite existing
daily digests by default. Local manual runs should omit `--force` to preserve
any notes added to today's file.

State persistence: `Inbox/Papers/*.md`, `Inbox/To Read.md`, and
`data/seen_dois.txt` committed back to `main` by `github-actions[bot]` with
`[skip ci]` in the commit message. Commit step is a no-op if nothing changed.
`data/papers.db` is intentionally not committed to `main` (gitignored via
`data/*.db`); it is rebuilt empty every run -- see DB persistence (2026-06-15).

Caches:
- pip cache via `actions/setup-python` keyed on `pyproject.toml`
- SPECTER2 model cache at `~/.cache/huggingface/hub`, key
  `specter2-allenai-specter2_base`. Download step gated on cache miss,
  runs without `local_files_only=True` to populate the cache; runtime
  embedding uses `local_files_only=True` as before.

Secrets: `NCBI_API_KEY`, `NCBI_EMAIL` set in repo settings.

Local sync: workflow does not auto-update the local vault. `git pull` from
vault root before opening Obsidian to read the day's digest.

Dry run: passed on 2026-05-21.

## DB persistence (2026-06-15)

`data/papers.db` was untracked from `main` (git rm --cached, removed from
history). This broke the scheduled run: `migrate()` called
`sqlite3.connect("data/papers.db")` on a fresh checkout where `data/` does
not exist, and sqlite3 does not create missing parent directories. Fixed by
adding `Path(db_path).parent.mkdir(parents=True, exist_ok=True)` to
`migrate()` in src/db.py.

The workflow's commit step no longer does `git add data/papers.db` (it would
have re-tracked the DB on the next run, undoing the untrack). It now commits
only `Inbox/Papers/` and `Inbox/To Read.md`.

Persistence decision: a bot-owned `data` branch, separate from `main`,
holding `data/papers.db`. NOT `actions/cache`. Reason: cache eviction
(~7 days unused, or storage pressure) is silent -- the pipeline would just
run as if the DB were empty, with no failure signal, degrading to the open
items below without anyone noticing. A bot-owned branch gives a push step
that can fail loudly and a history that's inspectable. Considered but NOT
chosen: superseded by the lighter committed-text approach built 2026-06-15
(corpus rebuilt from notes + a committed seen-DOI list), which keeps no binary
in git at all. The DB still starts empty every run, by design; the two open
items below are the built solution that makes that safe.

Open items from the untrack, status updated:
- Corpus-empty: FIXED (2026-06-15). The corpus seed metadata (DOI, title,
  abstract) lives as committed text in `Corpus/seed_dois.txt` and the 42
  `Corpus/*.md` notes; only the SPECTER2 embedding BLOBs were lost with the
  DB. `rebuild_corpus_from_notes()` (src/corpus.py) parses those notes and
  re-embeds them into the fresh DB's `corpus` table with no network, run as
  the workflow step `python -m src.corpus from-notes` before `src.rank`.
  Rebuilding at runtime (rather than committing pre-baked vectors) also keeps
  the corpus and candidate papers embedded by the same runtime model, so
  cosine scores stay consistent. Re-embeds 42 papers per run, seconds with
  the cached model. Ranking is restored without persisting the binary DB.
  Note: the corpus is rebuilt from the notes, which are the
  successfully-built subset; `seed_dois.txt` is the DOI list, the notes are
  the source of truth for corpus content.
- Empty-DB dedup: FIXED (2026-06-15) with a committed seen-DOI list, the
  lighter alternative to the bot-owned `data` branch. `data/seen_dois.txt`
  (tracked; only `data/*.db` is gitignored) is the durable record of every
  DOI ever surfaced. `src/seen.py` loads/saves it (lowercased, sorted,
  one per line for small line-merge-friendly diffs). `src.fetch` now dedups
  against `load_seen_dois() | get_existing_dois()` (file for CI where the DB
  is ephemeral, DB union for laptop where it persists), then writes the
  updated set back; the workflow commits it alongside `Inbox/`. Because the
  writer selects `WHERE seen_date = today` (src/digest/writer.py), only the
  genuinely-new papers inserted this run reach the digest. Seeded once from
  the 1103 DOIs already present in committed `Inbox/Papers/*.md`, so the
  first post-fix run does not replay the back catalogue.
  Failure consistency: a run that dies before the commit step persists
  nothing (Actions stops on step failure, so seen file and digests commit
  together or not at all), so the seen set never gets ahead of the digests.
  Recovery: `python -m src.seen rebuild-from-notes` regenerates
  `data/seen_dois.txt` from the DOIs linked in `Inbox/Papers/*.md` (the notes
  are the source of truth), for use after editing or regenerating digests by
  hand. Used 2026-06-16 when the 2026-06-15 and 2026-06-16 digests were
  regenerated with ranking after the corpus and dedup fixes landed.

## Next steps (updated 2026-06-04)

Observation period is over. Source expansion is done. The current decision,
deliberately taken: write the first weekly column (post zero) before building
any new feature, including the feedback loop. Rationale: writing reveals whether
ranking quality is actually the bottleneck (which the feedback loop would
address) or whether something else is. Do not build the feedback loop on the
assumption that better ranking is needed until the writing demonstrates it.

Step 6 (feedback loop) remains the one unbuilt pipeline step. It is next in the
pipeline's logic but NOT next in priority. Build only if post zero shows ranking
is the limiting factor. Note: the Relevant checkbox is already
rendered and the corpus table exists; the loop is the missing consumer that
reads checked Relevant boxes and appends their embeddings to the corpus.

Friction log (freeform in Obsidian) continues to be the real spec for what comes
next. Candidate features, unordered until the writing ranks them: top-k nearest
corpus DOIs per paper, in-context note capture during reading, Crossref keyword
prefilter for broad journals, feedback loop.

Failure monitoring: GitHub notifies on workflow failure via email. If
notifications stop arriving for several days with no commits to `main`,
check the Actions tab.

## Source expansion 2026-06-04

Crossref expanded from 3 to 17 journals. PubMed query extended with a
non-IBD-gated branch (abdominal radiology AI + agentic AI, ~43 papers/month).

Off-cycle threshold re-check: this expansion increases total papers scored
against the same corpus, which shifts the tier distribution. After one week
of digests at the new volume, check whether the must-read/skim/archive splits
(0.958/0.924) still produce useful groupings, and adjust if needed.


## Lineage module (separate from the digest)

The lineage module reconstructs the citation trajectory of a single
paper: given a seed DOI, it walks backward through references, prunes
to the relevant subgraph, clusters into phases, and renders a visual
Mermaid chart plus a bulleted trajectory into the Obsidian vault.

It is fully independent of the digest. It does not import digest code,
does not open data/papers.db, and does not write to Inbox/Papers/.
The digest could be deleted and this module would still run. Keep it
that way.

Status: building the deterministic pipeline first. The agentic backfill
loop is deferred until the deterministic version has run on real papers
and actual coverage gaps are visible. Do not build the agent yet.

Storage: per-run JSON files in runs/{run_id}.json, append-only, written
once per run. No database, no binary, no shared mutable state. This is
deliberate, to avoid the binary-merge push/pull problems papers.db has.
All run IO goes through store.py. See the store.py contract.

Output: rendered notes to Inbox/Lineages/{slug}-{date}.md, containing a
Mermaid flowchart grouped by phase followed by the bulleted trajectory.
Parallel to the digest's Inbox/Papers/, never overlapping it.

Pipeline stages (deterministic):
  1 resolve.py   DOI to OpenAlex work id
  2 traverse.py  backward reference walk, depth 2, flag sparse nodes
  3 prune.py     top-k per depth on relevance, non-destructive (hub weighting
                  deferred, see Stage 3 status)
  4 cluster.py   SPECTER2 embeddings, cluster into phases, date-order
  5 render.py    Mermaid chart plus trajectory Markdown
  6 render.py    LLM narrative pass, structured input only, writes prose

Conventions (same as digest): plain Python, stdlib first, type hints,
no em dashes, no emojis, no decorative comments, no new dependencies
without discussion, no over-abstraction. SPECTER2 helper is copied into
embed.py, not imported from the digest, to keep zero coupling.

Network note: OpenAlex, Crossref, and PubMed are not reachable from the
Claude Code container. The module runs on the laptop during deep-dive
sessions. Build and unit-test logic in the container against fixtures;
run end-to-end on the laptop.

Open verification items (do before relying on them):
  - confirm two-machine round trip: two runs writing different filenames
    must merge with no git conflict. Test with throwaway files first.
  - confirm OpenAlex reference coverage on a few known papers before
    trusting depth-2 traversal completeness.

### Built so far: stages 1, 2, and storage

resolve.py, traverse.py, store.py, plus openalex.py (live HTTP) and a
fixture-backed test suite (lineage/tests, stdlib unittest, run with
`python -m unittest discover -s lineage/tests -t .`). resolve and traverse
take an injectable fetch callable (`fetch(ref) -> dict`, ref is a DOI or a
`Wxxxx` work id); the live implementation is `openalex.http_fetch`, the test
implementation reads lineage/fixtures/openalex_sample.json. resolve and
traverse never touch the network themselves.

Live entry point: `python -m lineage.traverse <seed_doi> [depth] [top_k]`
resolves, traverses, and persists via store.write_run.

Fan-out cap (top_k): a per-node cap on how many referenced_works are
followed, applied as a cheap first-N slice (NOT quality selection, that is
stage 3). Bounds the walk to roughly top_k + top_k^2 fetches at depth 2,
before dedup. DEFAULT_TOP_K=15 (~240 worst case) is the safe default so a
run reliably completes; the raw depth-2 fan-out is hundreds of sequential
OpenAlex requests, which triggers connection drops and is wasted work
since stage 3 prunes anyway. Pass a larger top_k explicitly for a deeper
walk: light by default, deep on request. Recorded in the run dict.

Node schema (normalized; persisted on every node):
  - openalex_id   short id, URL prefix stripped (W123)
  - doi           lowercased, https://doi.org/ stripped, or null
  - title         from display_name
  - abstract      decoded from abstract_inverted_index, or null (see Abstract
                  enrichment); added 2026-06-17
  - pub_year      publication_year
  - authors       list of author display names
  - citation_count  from cited_by_count
  - ref_complete  bool; false flags a sparse node (fewer than
                  SPARSE_THRESHOLD=5 referenced_works), candidate for the
                  deferred agentic backfill
  - depth         min depth at which the node was reached (seed=0)
  - in_degree     reserved, 0 this session, filled by stage 3
  - phase         reserved, null this session, filled by stage 4

referenced_works is kept on the in-memory node during traversal to build
edges, then stripped before write_run (edges carry the same information).

Run dict (one JSON object per run file):
  schema_version (1), run_id, created_at (ISO), seed {doi, openalex_id,
  title}, depth, top_k, nodes [...], edges [[citing_id, referenced_id], ...],
  meta {node_count, edge_count, sparse_ids, unresolved_ids,
  unresolved_count, failed_ids, failed_count}.

Two skip buckets, distinct on purpose because they mean different things
to future-you reading a run:
  - unresolved_ids/unresolved_count: references that returned HTTP 404.
    PERMANENT coverage gap, OpenAlex does not have the work; a re-run will
    not recover them.
  - failed_ids/failed_count: references that exhausted bounded retries on a
    TRANSIENT error (connection drop, timeout, 5xx, rate limit that did not
    clear). NOT permanent; a re-run might recover them.
Both are skipped the same way (no node, no edge, walk continues) and each
skip logs a WARNING carrying the work id AND its citing parent, so a real
failure traces back to which paper referenced it. unresolved_count is the
coverage-gap signal feeding the deferred backfill.

Failure classification lives at the openalex.http_fetch boundary:
  - HTTP 404 -> WorkNotFound (permanent skip).
  - HTTP 429 / 5xx / URLError / connection drop / timeout -> retried
    MAX_RETRIES=3 times with exponential backoff (1, 2, 4 s, cap 8 s; 429
    honors Retry-After), then raised as FetchFailed (transient skip).
  - HTTP 401 / 403 / other 4xx -> propagate and abort the run (config or
    auth problem, not transient).
POLITE_DELAY=0.2 s spaces out requests (OpenAlex polite pool allows ~10/s)
to stop triggering the drops in the first place. These are constants in
openalex.py, not CLI args.

Consistency note for later (do NOT do now): sparse_ids should gain a
sparse_count sibling so meta's *_ids/*_count shape is uniform.

run_id format: `{slug}-{YYYYMMDD}` where slug is the seed DOI with
non-alphanumerics collapsed to hyphens. No uuid suffix: a same-day rerun of
the same paper targets the same filename so it overwrites-by-intent, but
write_run refuses to overwrite an existing file, so regenerating is an
explicit delete-then-rerun. If same-day collisions ever bite, add HHMMSS,
not a uuid.

Traversal edges run citing -> referenced for every depth-0 and depth-1
parent. Depth-2 nodes are fetched for metadata but not expanded. Nodes are
deduplicated by openalex_id (first/lowest depth kept); a work referenced by
multiple parents yields one node and multiple edges.

### Stage 3 (pruner): similarity-floor approach ABANDONED (2026-06-17)

RESOLVED. The abstract re-run (see Re-run verdict, 2026-06-17) closed the open
question with positive evidence: content similarity to the seed is the wrong
axis for lineage relevance, so there is no floor to validate and seed-anchored
cosine is not the primary prune measure. The decision taken: coarse prune to
deliverable (reframe #2). The pruner is now structural, not similarity-based.
The analysis preserved here records why three similarity attempts (hub
weighting, title-only floor, title+abstract floor) all failed validation, so a
future session does not re-litigate the axis. SETTLED: no floor, no revisiting
seed-anchored cosine as the primary measure. The coarse-prune spec is being
written this session and recorded once approved.

The pruner was specced as similarity-floor but not built. It was blocked on a
validated relevance floor, and the floor could not be validated on the data we
have. What was decided and why, so the next session does not re-litigate it:

Relevance measure: seed-anchored cosine. relevance = cosine(node, seed). The
tool is the trajectory of one paper, so similarity to that seed is the axis.
Not corpus-anchored (that is the digest's job and drags in its filter-bubble
concerns), not seed-plus-depth-1-average (smears the anchor toward whatever the
first ring happened to contain).

Hub weighting by in_degree: DROPPED from v1. An empirical pass
(analyze_floor.py, throwaway, uncommitted, kept in the repo root for re-running)
showed in_degree is degenerate on depth-2/top_k=15 graphs: ~95% of nodes have
in_degree exactly 1, a handful 2, exactly one node 3, on both real run files.
These graphs are essentially trees (217 nodes/224 edges, 190/200); depth-2
sinks under top_k=15 barely overlap, so there are no real foundational hubs to
weight on, and the in_degree-2/3 nodes are incidental cross-references, not the
shared-ancestor signal hub weighting was meant to catch. Relevance is on 0.77
to 1.00; in_degree is 0 to 3 and near-constant. Any relevance + alpha*in_degree
formula would either do nothing or inject noise; there is nothing to calibrate
alpha against. So v1 cuts on relevance alone. in_degree is still computed and
stored as a structural field per the schema (two-pass: it is not used in the
keep decision, so the only meaningful value is the kept-subgraph recompute,
stored on every node). Revisit hub weighting ONLY if a later deep walk (higher
top_k or depth 3) produces a graph with real overlap, and only after such a
graph exists to calibrate against.

Floor NOT hardcoded. analyze_floor.py reported a clean +0.115 margin between
the named off-topic nodes (rat sexual receptivity, mother-infant-peer
interaction, at 0.776 to 0.790) and the lowest labeled-relevant node (0.905).
That clean margin is misleading: those off-topic nodes are semantically miles
from IBD imaging, so title-only SPECTER2 separates them trivially. At the real
boundary there is NO gap. On-topic-adjacent but off-thread papers (IBD
complications, transplant lymphoma, rheumatoid-arthritis cancer risk, primary
sclerosing cholangitis, infectious enteritis, oncology) form a continuous band
from ~0.79 to ~0.90 that interleaves with both foundational keepers and genuine
imaging papers. Concretely: a paper we would keep ("The Results of Surgical
Treatment of Chronic Regional Enteritis," 1961) sits at 0.853, BELOW on-thread
imaging-method papers like "SonoVue contrast agent" (0.873) and "MR imaging of
the small bowel HASTE" (0.898). No single floor separates on-thread from
off-thread on title-only data.

Next step: abstract enrichment (its own build step, next session). Decode
OpenAlex abstract_inverted_index into an abstract field on each node, re-embed
title + abstract to match the digest, re-run analyze_floor.py unchanged on
freshly fetched runs, look at the margin again. http_fetch already returns the
full work object (no select= narrowing), so abstract_inverted_index is already
in every payload traverse downloads; enrichment is decode-only, zero extra
HTTP. Must re-fetch on the laptop (OpenAlex unreachable in the container); the
existing 0614 run files predate the field and cannot be backfilled from disk.

OPEN QUESTION, unresolved: whether title + abstract actually opens a gap is
unknown. This is a commitment to RE-TEST, not a commitment to the pruner
working once abstracts exist. If the margin is still thin with abstracts, the
next conversation is about whether seed-anchored cosine is the right relevance
measure at all, NOT about tuning the floor. Do not hardcode any floor until the
abstract re-run shows a real, defensible gap at the on-thread/off-thread
boundary.

What the abstract re-run actually tests is bigger than its framing. It is not
"do abstracts fix the floor," it is "is content similarity to the seed the
right axis for lineage relevance at all." Lineage is a structural and temporal
relationship (what built on what, in what order), not purely a topical one. A
1961 surgery paper is part of the imaging lineage because the field built on
it, not because its text is close to a 2023 MRI paper. The off-thread papers
(lymphoma, sclerosing cholangitis, methotrexate toxicity) have abstracts
genuinely about IBD, so richer text may pull them CLOSER to the seed rather
than separating them. If that happens it is not a failure of enrichment, it is
evidence the measure is wrong, and the next move is rethinking the axis, not
fetching more text.

Two reframes to have on the table before the re-run, not after, in case the
margin is still thin. Note: hub weighting and the title-only floor have already
failed validation; abstracts are the third attempt at a similarity-based prune,
so go in knowing the axis itself is what is on trial.
  1. Structure over similarity. Lineage may be better served by graph structure
     than by embedding similarity. Phases could come from depth and citation-era
     rather than embedding clusters. Relevance could be "does a path connect
     this node back to the seed through the kept subgraph" rather than "is this
     node topically close to the seed," using similarity only to break ties or
     label phases. This treats it as the graph problem it is and may be the real
     fix the floor failures are pointing at.
  2. A looser prune may be enough. The deliverable is a human-readable note with
     an LLM narrative pass, not a precise classifier. A 40-node trajectory that
     includes a few off-thread papers is still useful, and the narrative stage
     can say "this branch goes off toward lymphoma risk and is not central." The
     goal may need only a rough filter with the narrative doing the interpretive
     work, a much easier bar than the precision we defaulted to building. Decide
     this deliberately rather than by default.

### Abstract enrichment (built 2026-06-17)

Decode-only, zero extra HTTP: http_fetch returns the full work object (no
select= narrowing), so abstract_inverted_index is already in every payload
traverse downloads. `decode_abstract` (resolve.py) reconstructs the text by
expanding every (position, word) pair (a word can occupy multiple positions),
sorting by position, and joining; missing/empty index returns None. `to_node`
now emits an `abstract` field. lineage/embed.py is the copied SPECTER2 helper
(load_model, embed) plus `build_input(title, abstract, tokenizer)` =
title + tokenizer.sep_token + (abstract or ""), matching the digest's
src/ranking contract exactly, copied not imported for zero coupling. A node
with no abstract degrades to title-only. Tested in lineage/tests against the
fixture (word order, repeated word landing in all positions, missing -> None,
to_node population).

schema_version is NOT bumped for enrichment. Deliberate, not an oversight: the
node gains a field but the run dict shape is unchanged, and an old abstract-less
run is not migrated, it is simply re-fetched. analyze_floor.py and to_node both
read abstract with .get/null-tolerance, so old and new runs coexist. The
schema_version 2 bump is reserved for the pruner's structural additions (kept,
kept_count/pruned_count), which do change the run shape.

Re-test procedure (laptop, OpenAlex unreachable in container): re-run
`python -m lineage.traverse <doi>` for both seeds to produce fresh run files
carrying abstracts (new date, no overwrite collision with the -0614 pair),
delete the -0614 pair so analyze_floor.py (globs runs/*.json) sees only the
enriched runs, then re-run analyze_floor.py unchanged and read the boundary
margin. Hold the pruner until that margin is real.

### Abstract re-run verdict (2026-06-17): axis is wrong, similarity prune dropped

Ran on the laptop. Both seeds re-fetched with abstracts (-0617 run files,
139/217 and 113/190 nodes carrying an abstract; the rest have no OpenAlex
abstract, mostly older works, and degrade to title-only). Re-ran
analyze_floor.py unchanged. Result: abstracts did NOT open a gap. They made it
slightly worse, the exact failure mode that was flagged before the re-run.

  - rg run margin NARROWED: title-only +0.115 (off-topic max 0.790, lowest
    relevant 0.905) to abstract +0.095 (off-topic max 0.815, lowest relevant
    0.909). The labeled margin is nominally "clean" but that was always the easy
    case (rat/observation papers are semantically distant). The real boundary,
    off-thread-IBD vs on-thread-imaging, has NO gap, and abstracts pushed the
    off-thread band UP toward the seed: granulomatous hepatitis/sulfasalazine
    0.802 to 0.840, primary sclerosing cholangitis 0.843 to 0.866, and the whole
    lymphoma / transplant / RA-cancer-risk / methotrexate cluster now sits 0.81
    to 0.87, climbing under the keepers.
  - diagnostics run is the clean proof: off-thread differential-diagnosis papers
    now OUTSCORE a genuine on-thread imaging paper. "SonoVue contrast agent"
    (imaging) is 0.874, but "Malignant Tumors of Small Intestine" (0.880), "GI
    amyloidosis" (0.887), "abdominal actinomycosis" (0.882) all score higher. The
    1961 surgery paper we would keep is 0.862, below infectious-disease noise.
    There is no monotone relationship between similarity-to-seed and on-lineage
    membership.

Interpretation: this is positive evidence the AXIS is wrong, not that enrichment
was too weak. SPECTER2 is working correctly. Off-lineage papers (lymphoma risk
in IBD, PSC, methotrexate toxicity, EBV in Crohn's) have abstracts genuinely,
richly about IBD, so SPECTER2 correctly judges them topically close to an
IBD-imaging seed. Topical similarity cannot separate "IBD imaging-methods
lineage" from "IBD clinical-complications literature" because both are about IBD.
That distinction is structural (what the field's imaging methods built on), not
topical. The open question is closed. SETTLED: no floor, seed-anchored cosine is
not the primary prune measure, do not re-litigate either.

Decision (reframe #2, coarse prune to deliverable): chosen over reframe #1
(structure over similarity) deliberately. The deciding caveat: pure structure
will not rescue these graphs either. They are capped trees (217 nodes/224 edges,
190/200) with degenerate in_degree (~everything is 1) because top_k=15 first-N
slicing admitted off-thread papers for tangential reasons and there is no
co-citation signal at this depth/width. So reframe #1 (bibliographic coupling,
deeper/wider walk, depth-2 reference fetching) is a whole graph-enrichment
project with real cost and a deferred deliverable. Reframe #2 gets a real
lineage note into the vault end-to-end and produces the one thing three sessions
of floor-chasing could not: evidence about whether prune precision matters to a
reader at all. If the rendered note reads fine with a few off-thread papers, the
entire structural build is saved. If it is confusing, we then invest in reframe
#1 with a concrete artifact telling us it is needed. analyze_floor.py stays
uncommitted in the repo root for re-running if a later deep walk is attempted.

Stage 3 schema (when the pruner is finally built, not yet applied):
  - add kept (bool) to every node; pruner sets it, never deletes.
  - fill in_degree (kept-subgraph value, two-pass).
  - bump schema_version to 2.
  - add kept_count / pruned_count to meta (mirrors the *_count convention).
  - leave the deferred sparse_count item alone.
  - v1-to-v2 migration: a schema_version 1 run is simply an unpruned run;
    prune upgrades it in place to v2 when it writes. No separate migration. A
    mixed-version runs/ directory just means some runs are pruned and some are
    not.
  - write path: store.update_run(), overwrite-permitted (unlike write_run,
    which is append-only), atomic via temp-file-plus-rename so an interrupted
    write cannot corrupt an existing run. Keeps all run IO in store.py.