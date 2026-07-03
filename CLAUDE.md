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
- Initial corpus: 20 to 50 papers selected manually from Zotero, grown by the
  feedback loop (checked Relevant boxes) since 2026-07-02
- Score: mean of the top 3 cosine similarities between candidate and corpus
  (top-3 mean, replaced single max 2026-07-02: with a ~40-paper corpus one
  atypical seed note could pull an off-topic paper into must-read)
- Tiers are SELF-CALIBRATING per run (2026-07-02): thresholds come from the
  corpus leave-one-out distribution, each seed scored against the rest with the
  same top-3 mean statistic; must-read = 90th percentile, skim = 50th.
  compute_thresholds in src/ranking/score.py; values recorded in the DB meta
  table (tier_threshold_must/skim) and data/metrics.txt. Fixed fallbacks
  (0.958/0.924) apply only when the corpus is under 5 papers. The monthly
  manual threshold re-check is obsolete; watch data/metrics.txt for drift.
  Measured on the real 42-note corpus at build time: must >= 0.9750,
  skim >= 0.9674 (higher than the old fixed pair; the statistic changed with
  the calibration, so tier composition shifts on the first ranked run).

### Daily digest format
One Markdown note per day at `Inbox/Papers/YYYY-MM-DD.md` in the Obsidian vault.

Header: date, total new papers, count per tier.

For each paper in must-read and skim tiers:
- Title
- DOI as link
- Authors: first two plus corresponding author
- Journal and date
- Similarity score (numeric)
- Nearest seed line (`Nearest seed: {corpus title}`, from matching_corpus_doi):
  shows WHY the paper ranked, which makes Relevant judgments faster and better
  informed
- Full abstract inside a collapsible Markdown callout
- Two independent checkboxes: `- [ ] Relevant` (feeds the corpus feedback loop)
  and `- [ ] Read later` (queues the paper into Inbox/To Read.md)

Wildcard tier (2026-07-02, filter-bubble mitigation): up to 2 archive papers,
sampled seeded by the digest date, promoted to a full-rendered section
(`> [!question]` banner) with both checkboxes, so the corpus has a path to
papers the ranker scores low. Promoted papers are excluded from the archive
listing below.

Archive tier: collapsed section, title + DOI link + authors only, no checkboxes.

Footer: source breakdown (papers per source, duplicates merged).

Empty days: note still generated, says "no new papers today, pipeline ran successfully."

### Feedback loop (BUILT 2026-07-02)
- User ticks `- [x] Relevant` on papers in the digest and pushes
- src/digest/feedback.py scans a trailing window of digests (workflow: 7 days)
  for checked Relevant boxes ONLY (a Read later tick never reaches the corpus;
  see the checkbox parsing contract) and writes each as a Corpus/{slug}.md note
  in the exact format src.corpus emits and parses
- Fully offline: the digest block already carries title and abstract, so no
  refetch is needed. The next `src.corpus from-notes` step embeds the new notes;
  ranking sharpens with no further action. The complete human loop is: tick the
  box in Obsidian, git push.
- Idempotent: an existing Corpus/{slug}.md is never rewritten
- Old-format digests (pre 2026-07-02, no literal Relevant line) contribute
  nothing; the loop starts with new-format digests
- Filter-bubble mitigation: the Wildcard digest section surfaces low-scoring
  papers with checkboxes, plus periodically add outside papers to Corpus/ by
  hand as before

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
- [x] Step 6: Feedback loop (feedback.py parses checked Relevant boxes into Corpus/ notes, windowed + automated) -- BUILT 2026-07-02
- [x] Read later layer (to_read.py: parses checked Read later boxes into Inbox/To Read.md, windowed + automated)
- [x] Weekly column packet (column.py: one prep note per completed ISO week at Inbox/Column/YYYY-Www.md) -- 2026-07-02
- [x] Run telemetry (metrics.py: one committed line per run in data/metrics.txt) -- 2026-07-02

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
- Crossref keyword prefilter for broad journals (Nature Medicine, npj Digital

## Step 4: Obsidian integration (done)

Digest writer renders papers grouped by tier with Obsidian callouts.

### Rendering conventions
- Must-read tier: `> [!important]` banner, papers rendered outside the callout with `- [ ]` at column 0.
- Skim tier: `> [!note]` banner, same pattern.
- Archive tier: `> [!abstract]-` container (collapsed), papers rendered inside with `> ` prefix on every line.
- Wildcard tier (2026-07-02): `> [!question]` banner, papers rendered full like
  must-read/skim (seeded-random archive promotions, see Daily digest format).
- Empty tiers are skipped entirely. Header counts still show zeros.
- Each paper (2026-07-02 layout): `- [ ] **Title**`, then `- [ ] Relevant`, then
  `- [ ] Read later`, followed by 2-space-indented metadata (authors, journal,
  date, DOI + score, optional `Nearest seed: {corpus title}` line), then a
  nested `> [!abstract]-` callout for the abstract. Pre-2026-07-02 digests lack
  the Relevant and Nearest seed lines; the parser handles both formats.
- Abstract callout body: every line (including blank separator lines between paragraphs) must carry its own `  > ` prefix. Blank lines use `  >` with no trailing space. The writer splits the abstract on `\n` and prefixes each line individually; structured abstracts (Introduction/Methods/Results) from Crossref have leading whitespace that is stripped per line.
- DOI format is always `[10.xxxx/yyyy](https://doi.org/10.xxxx/yyyy)`.

### Checkbox parsing contract (do not break)

Two independent checkboxes per paper, parsed by separate consumers. They must
never be confused: a `Read later` tick must never reach the corpus, and a
`Relevant` tick must never be treated as a Read later queue entry.

Since 2026-07-02 all block parsing lives in ONE shared module,
src/digest/blocks.py, consumed by to_read.py (Read later), feedback.py
(Relevant), and column.py (weekly packet), so the contract cannot drift between
consumers. Parsing is pattern-based, not positional: metadata comes from the
indented lines, checkboxes are matched by literal label, so old-format digests
(no Relevant line, no Nearest seed line) and new-format digests parse
identically.

- `Relevant` (feeds Corpus/, consumed by feedback.py, BUILT 2026-07-02):
  `^>?\s*- \[[xX]\] Relevant$` (RELEVANT_RE in blocks.py).
- `Read later` (feeds Inbox/To Read.md, consumed by to_read.py, BUILT):
  `^>?\s*- \[[xX]\] Read later$` (READ_LATER_RE).
- DOI extraction: `\[([^\]]+)\]\(https://doi\.org/([^\)]+)\)` (DOI_RE), searched
  on the metadata lines only, so a DOI link inside an abstract cannot match.
- Score extraction: `Score: (\d+\.\d+)` (SCORE_RE).
- Both patterns tolerate a `> ` prefix.

Any change to the writer's block layout must keep blocks.py parsing both the
old and the new format (tests/test_blocks.py and tests/test_to_read.py pin
this). The feedback parser matches ONLY the Relevant box; tests pin that a Read
later tick never reaches the corpus.

## Step 5: GitHub Actions scheduling, complete (2026-05-21)

Workflow: `.github/workflows/daily-digest.yml`
Schedule: `0 2 * * *` UTC (5:30 AM Tehran)
Manual trigger: `workflow_dispatch` available in Actions tab

Pipeline order (since 2026-07-02): `src.fetch 3` -> `src.digest.feedback .
--window 7` -> `src.corpus from-notes` -> `src.rank` -> `src.digest.writer .
--force` -> `src.digest.to_read . --window 7` -> `src.digest.column .` ->
`src.metrics`. Fetch runs with days_back=3 so a failed run self-heals on the
next one (the seen-DOI list makes the overlap free). The feedback sweep runs
BEFORE the corpus rebuild so new Relevant notes are embedded the same run. The
commit step adds `Inbox/Papers/`, `Inbox/To Read.md`, `Inbox/Column/`,
`Corpus/`, `data/seen_dois.txt`, `data/metrics.txt`.
The `src.corpus from-notes` step rebuilds the
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

Step 6 (feedback loop) was BUILT 2026-07-02 as part of the whole-approach
overhaul (see the 2026-07-02 section), on explicit instruction, superseding the
post-zero gating above. The loop is deliberately tiny (a windowed scanner
mirroring to_read.py) so building it did not compete with the writing. Post
zero remains the priority; the column packet (also 2026-07-02) exists to serve
it directly.

Friction log (freeform in Obsidian) continues to be the real spec for what comes
next. Candidate features, unordered until the writing ranks them: in-context
note capture during reading, Crossref keyword prefilter for broad journals
(now derivable from accumulated tier labels instead of a hand-written term
list; see Deferred).

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
  3 prune.py     annotation pass: kept on every node, kept-subgraph in_degree,
                  era phase; non-destructive, v1 keeps everything (no cut, no
                  similarity, no centrality), see Stage 3 status
  4 prune.py     era phases from pub_year decade (folded into stage 3; replaces
                  the planned SPECTER2 clustering, axis settled wrong)
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

### Stage 3 (pruner): coarse prune BUILT (2026-06-17)

prune.py is an annotation pass, not a reducer. It sets kept on every node,
recomputes in_degree over the kept subgraph, assigns era phases from pub_year,
records kept_count/pruned_count, and bumps schema_version to 2. `prune(run)` is
a pure in-place function; `python -m lineage.prune <run_file>...` prunes files
in place via store.update_run. Idempotent. Tested fixture-based for the logic
(keep-all, kept-subgraph in_degree including the pruned-node-exclusion seam,
decade phase mapping, schema bump, counts, idempotency, update_run overwrite +
atomic temp cleanup) and against the real -0617 run files for the foundational
keepers (CDAI 1976, "Lesions of the ileum" 1956 survive) and the presence of
in_degree>=2 shared ancestors. The real-run tests skipUnless the files exist
(they are not committed), so the suite stays green elsewhere.

WHY THERE IS NO DEPTH-2 CAP (a decision, not a missing feature). Do not add one
without new evidence; a future session that sees "the pruner does not prune" and
adds a cap walks straight back into the trap this records. No honest per-node
ordering exists for the cut. All three candidates failed validation:
  - in_degree: degenerate on depth-2/top_k=15 graphs (~everything is 1), no
    continuous signal to rank on.
  - seed-anchored cosine: wrong axis, settled by the abstract re-run (off-thread
    IBD papers are genuinely about IBD and score high; off-thread
    differential-diagnosis papers outscore a real on-thread imaging paper).
  - citation_count: actively harmful. It keeps famous off-thread classics
    (rg run #1 most-cited depth-2 reference is Kaplan-Meier, "Nonparametric
    Estimation from Incomplete Observations," cc=45545; then "Cancer Incidence
    in Five Continents," cc=8537) and DROPS low-cited on-thread imaging papers
    (diagnostics: "Crohn's disease evaluated with MR enteroclysis" cc=8,
    "Doppler US of the SMA for Crohn's activity" cc=3). The cut direction is
    the fatal one: a kept off-thread node can be flagged by the narrative, an
    absent on-thread node cannot.
Depth-2 is already bounded once, honestly, at traversal by top_k=15 (first-N per
parent). A second stage-3 cap would re-order an already-bounded set with an
ordering shown to fail every way. So v1 keeps the full top_k set: seed, all
depth-1, all depth-2. pruned_count=0 is a real result. Keeping everything and
letting era-grouping plus the narrative carry it is the purest version of the
experiment this reframe exists to run.

EXIT CONDITION (when to add a real cut). This reframe is a test; its pass/fail
is the rendered note, not the pruner. Add a cut only if the rendered note is too
busy to read. The cut to try then is charting only in_degree>=2 shared ancestors
(keep all depth-1, chart depth-2 only where in_degree>=2, list the rest in the
trajectory text). That is the point where reframe #1's graph-enrichment cost
(bibliographic coupling, deeper/wider walk, depth-2 reference fetching) becomes
justified. Recording the trigger now makes the later call "did the note hit the
trigger," not a fresh argument. With prune settled as annotation-only, the real
uncertainty has moved to render and narrative: whether the narrative can carry
the off-thread flagging convincingly is the next hard question, not the graph.

Schema v2 (applied):
  - kept (bool) on every node; pruner sets it, never deletes.
  - in_degree filled (kept-subgraph value; single post-hoc pass, not used in any
    keep decision, stored for a future reframe #1 without pretending to carry
    signal now).
  - schema_version bumped to 2.
  - phase (int decade start, e.g. 1970, or null if pub_year missing).
  - meta gains kept_count / pruned_count (mirrors the *_count convention).
  - sparse_count still deferred, left alone.
  - v1-to-v2 migration: a schema_version 1 run is simply an unpruned run;
    prune upgrades it in place to v2 when it writes. No separate migration. A
    mixed-version runs/ directory just means some runs are pruned and some are
    not.
  - write path: store.update_run(), overwrite-permitted (unlike write_run,
    which is append-only), atomic via temp-file-plus-rename so an interrupted
    write cannot corrupt an existing run. Keeps all run IO in store.py.

### Stage 5 (render): deterministic note BUILT (2026-06-18)

render.py reads a pruned v2 run and writes `Inbox/Lineages/{slug}-{date}.md`: a
Mermaid flowchart of decade subgraphs (oldest to newest, seed styled) followed
by a bulleted trajectory. Deterministic, no network, no SPECTER2, no LLM (the
narrative pass is stage 6, deferred). stdlib plus lineage.store only; zero
coupling to the digest. Entry point: `python -m lineage.render <run_file>
[vault_root] [--force]`.

Single grouping source. `group_by_phase(run)` returns the ordered structure
(decades oldest to newest, Undated trailing, nodes sorted by (pub_year, title))
and BOTH `mermaid()` and `trajectory()` consume it, so the chart and the text
can never disagree on grouping or order. Decided deliberately: do not let the
two renderers each group independently.

Decisions, made against the real -0617 runs (190 and 217 nodes), not defaults:
  - Labels: first-author surname + year (`Bousvaros 2007`). Full titles are
    unusable as node labels (median ~80, max ~250 chars); truncated titles are
    worse (40-char boxes x 190 = denser hairball, ambiguous). The full title and
    author list live in the trajectory bullets. Node id = openalex_id. No
    authors -> fall back to the id. Labels are double-quoted and sanitized
    (strip `"`, collapse newlines).
  - Phase grouping: one subgraph per decade from the `phase` field, oldest to
    newest, titled `1960s` etc.
  - Null phase (no pub_year): a trailing `Undated` subgraph after the newest
    decade (cannot be temporally ordered). BOTH real runs have zero null-phase
    nodes (every node carries a pub_year), so this bucket is empty on them; it is
    built and unit-tested against a synthetic run because the schema permits
    phase=null.
  - Seed distinction: Mermaid `classDef seed` (fill + bold border) on the seed
    node (identified by run["seed"]["openalex_id"]) plus a `SEED:` label prefix,
    in both the chart and the trajectory. Seed sits in its own decade subgraph.
  - Edges: all citation edges among kept nodes, rendered faithfully. The main
    hairball source; rendered anyway (reframe 2 keeps everything).

v1 input: render auto-prunes in memory (calls prune(run)) if schema_version < 2,
then renders; it does NOT write the pruned run back (that is `python -m
lineage.prune`'s job). The runs/ files on disk are still v1; render upgrades a
copy in memory. Overwrite: write_note refuses to overwrite an existing note
unless --force, mirroring the digest writer guard, because a note may carry hand
annotations. Tested fixture/synthetic-based (group order, Undated trailing,
within-group sort, kept-only, label format, all nodes charted, seed styled, all
edges rendered, et-al rule, doi present/absent, path + overwrite guard) plus a
render of the pruned fixture run.

LEGIBILITY FINDING (the thing this reframe exists to surface). At reframe-2
scale the single Mermaid chart is NOT legible, and short labels do not fix it.
Rendering the diagnostics -0617 run produces a 408-line Mermaid block: 190 nodes
and 200 edges, with a single 2000s decade subgraph of 93 nodes (rg: 95) and a
mostly-tree edge set that crosses eras into a hairball. Short labels make
individual nodes readable, not the chart. The trajectory text is the genuinely
readable artifact. This is recorded as evidence, not fixed: per the exit
condition, the cut to try IF the rendered note reads too busy is charting only
in_degree>=2 shared ancestors. The trigger numbers are now measured: in_degree>=2
is 10 nodes on diagnostics, 7 on rg, so that cut would reduce the chart from
~190-217 charted nodes to ~25 (seed + 15 depth-1 + the 7-10 shared ancestors).
Not built now; the decision is whether the rendered note in the vault reads
acceptably with everything in it. Per-decade sizes (diagnostics):
1960s 2, 1970s 5, 1980s 20, 1990s 35, 2000s 93, 2010s 34, 2020s 1.

STATUS (2026-06-18): stage 5 built, tested, committed. 69 tests passing
(`python -m unittest discover -s lineage/tests -t .`). render.py and
test_render.py are the only stage-5 files.

### Empty 2020s decade: TRUE ABSENCE, not a top_k artifact (2026-06-18)

The diagnostics seed (a 2025 review) renders with exactly one node in the 2020s
decade: itself. Investigated whether that is a real property of backward
traversal or an artifact of the top_k=15 first-N slice truncating recent
references. Confirmed TRUE ABSENCE by a one-off top_k=60 re-run on the laptop
(`python -m lineage.traverse 10.3390/diagnostics15192457 2 60`, scratch run
deleted after). Following the seed's references at 4x the window: all 60 depth-1
nodes resolved (0 missing a year), newest reference is 2019, ZERO depth-1 nodes
>= 2020. Widening 15 -> 60 added 2015-2019 papers (20 nodes >= 2015) but no
2020s papers; the ceiling moved only 2015 -> 2019. A 2025 review citing
established literature with a ~6-year lag is expected (recent papers have not yet
entered the cited canon). NO traversal fix needed; the empty 2020s reflects what
the seed actually cites. Caveat: depth-1 came back as exactly 60 = top_k, so the
seed has >= 60 references and the full list is still capped, but a 4x widening
moving the ceiling only to 2019 is strongly one-directional evidence.

### Stage 6 (LLM selection + narrative): SCOPED (now BUILT, see below)

Recording the intended reframe so it is not lost. The stage-5 legibility finding
(190-node hairball, trajectory text is the readable artifact) reframes stage 6:
it should SELECT the small set of groundwork papers (~15) from the crawl pool and
narrate ONLY those, NOT narrate all 190. The chart-everything render stays as the
raw record; stage 6 is the curated layer on top.

Anti-hallucination contract (strict, the core of the design):
  - The LLM receives the run-file nodes (id, title, year, abstract) and returns
    ONLY openalex_ids drawn from the run file, plus one rationale line per
    selected id. It never emits its own titles, DOIs, or years.
  - The renderer looks up every citation fact (title, year, authors, DOI) from
    the run file by id, never from the LLM output.
  - Coverage gaps are described as topics ("no node here covers X"), never as
    fabricated citations. An id not in the run file is rejected, not rendered.

Target output: a structured, visual-ready record, timeline-friendly (per paper:
label, year, one-line role, DOI), so the note can convert to an infographic.
This is scope only; do not build until the stage-5 note is read in the vault and
shows whether the curated layer is actually needed (the reframe-2 experiment).

### Stage 6 (LLM selection + timeline): BUILT (2026-06-18)

Built as two halves around a MANUAL paste, not a network call. This module still
makes zero API calls and adds no network client; the transport is the human
copying a prompt into a Claude session and pasting the reply back. Two new files,
lineage/select.py and lineage/timeline.py, plus sidecar IO in store.py. render.py
(stage 5) is untouched: the chart-everything note stays the raw record, this is
the curated layer alongside it. 95 tests passing.

Half 1, lineage/select.py (the human-in-the-loop boundary):
  - `build_payload(run)` renders a pasteable prompt block: an instruction
    preamble (select ~15-20 groundwork papers, pick ids from the list only, do
    not invent) and the exact required response format, then one entry per kept
    node (openalex_id, pub_year, depth, title, abstract truncated to 500 chars).
    Ordered groundwork-likely first: `(pub_year asc, depth desc, title)`, undated
    nodes last (an unknown year cannot be judged groundwork). Depth is a sort
    TIEBREAKER only, never a cut. Full kept set, no pre-filter. SPECTER2,
    in_degree, citation_count are NOT used in the ordering, per the stage-3
    findings.
  - `parse_selection(text)` extracts the response JSON. Accepts a fenced ```json
    block or a bare object; raises ValueError on prose or non-object (the
    "id list, not prose" guard).
  - `validate_selection(parsed, run)` is the anti-hallucination validator: keeps
    only selections whose openalex_id is in the run, drops unknown and duplicate
    ids with a logged WARNING, raises if there is no selections list or none
    survive. narrative (str) and coverage_gaps (list[str]) are free prose passed
    through untouched.
  - CLI: `python -m lineage.select <run_file>` prints the payload;
    `python -m lineage.select ingest <run_file> [response_file]` (stdin if no
    file) validates and writes the sidecar.

Handoff format: a single fenced ```json object
`{narrative, coverage_gaps, selections:[{openalex_id, rationale}]}` so the arc
and gaps travel with the picks in one paste.

Caching, SIDECAR not in-place (decided against mutating the run file): the
validated block is written to `runs/{run_id}.selection.json` via
store.write_selection (atomic temp-rename, overwrite-permitted). The crawl run
file is NEVER mutated. Reasons: the crawl files are the immutable validation
fixtures the skipUnless tests read against; the selection is a model judgment
re-run as picks improve, a different artifact kind than the deterministic crawl;
and it removes any in-place prune-and-write-back coupling. Re-render is free
(re-read the sidecar); re-select is an explicit re-ingest (overwrites the
sidecar). Sidecar carries run_id to bind it to its crawl.

Half 2, lineage/timeline.py (the curated render):
  - Reads the immutable crawl run plus the sidecar and joins by openalex_id. No
    Mermaid: the graph is a near-tree with no meaningful branching, so a
    decade-grouped timeline is the honest artifact and converts cleanly to a
    visual post. Reuses render.group_by_phase as the single ordering source, so
    the timeline cannot drift from stage-5 grouping (it prunes the v1 crawl in
    memory first to populate phase, like render does; the on-disk crawl stays
    v1).
  - Every citation fact (title, authors, year, DOI) comes from the run node by
    id; the sidecar contributes only ids, rationale sentences, narrative, gaps.
  - DROP-UNKNOWN-ID GUARD AT RENDER TIME TOO, not only at ingest: a sidecar can
    outlive a re-crawl of its seed, so an id valid at ingest can be absent at
    render. `selected_nodes` drops any sidecar id not in the live run with a
    logged WARNING; render raises if none survive. This keeps every fact sourced
    from the live crawl.
  - Output `Inbox/Lineages/{slug}-{date}-selected.md`: header + narrative arc,
    `## Timeline` with decade headings (SEED prefixed, full title, authors, year,
    one-line role from the rationale, DOI), `## Coverage gaps` (topics/eras
    only), and a footer recording the in_degree>=2 count as the UNUSED exit lever
    (10 on diagnostics) for if the timeline ever reads busy. write_note refuses
    to overwrite without --force, mirroring the stage-5 guard.
  - CLI: `python -m lineage.timeline <run_file> [vault_root] [--force]`.

Tested (stdlib unittest, fixture/synthetic plus real-run skipUnless on the -0617
files): payload lists every kept node, format spec present, abstract truncation,
groundwork-first ordering, depth-tiebreaker; parse (fenced, bare, prose raises,
non-object raises); validate (unknown dropped+warned, dedupe, no-list raises,
none-survive raises, narrative/gaps passthrough); ingest writes sidecar only and
does not touch the run; timeline (no Mermaid, only-selected, phase-order reuse,
facts-from-run/role-from-sidecar, seed marked, narrative+gaps rendered, exit
footer count, empty-after-drop raises, path + overwrite guard).

VALIDATION DONE (2026-06-23): the human read was run on the diagnostics seed in
the vault (select payload -> Claude session -> ingest -> timeline ->
read the -selected.md note). The picks were judged relevant and the curated
timeline reads better than the stage-5 hairball: reframe-2 is answered, the
curated layer is worth keeping.

WHAT IS NOT TESTED HERE: selection QUALITY. The module guarantees the renderer
cannot hallucinate citations and cannot drift from the crawl; it does not and
cannot judge whether the model picked the right ~15 papers. That is the human
read.

### Stage 6 closeout (2026-06-23)

Stage 6 is finalized. What shipped, for the record (the section above is the
design; this is the as-built summary plus the two closing fixes):

  - select.py: `build_payload` (pasteable prompt, kept nodes groundwork-first by
    pub_year then depth tiebreaker, abstracts truncated to 500 chars),
    `parse_selection` (fenced or bare JSON, fails loud on prose),
    `validate_selection` (anti-hallucination: keeps only ids in the run, drops
    unknown/duplicate with a WARNING, fails loud on no-list/none-survive),
    `ingest` and the `ingest` CLI subcommand. The print-payload CLI path
    reconfigures stdout to UTF-8 (see Fix below).
  - store.py sidecar IO: `selection_path`, `write_selection` (atomic temp-rename,
    overwrite-permitted), `read_selection`. The crawl run file is NEVER mutated;
    the selection lives at runs/{run_id}.selection.json.
  - timeline.py: joins the immutable crawl run plus the sidecar by openalex_id,
    renders a decade-grouped timeline (no Mermaid; the graph is a near-tree with
    no meaningful branching). Every citation fact comes from the run node by id;
    the sidecar contributes only ids, rationales, narrative, gaps. The
    drop-unknown-id guard runs at render time too (a sidecar can outlive a
    re-crawl). in_degree>=2 count recorded in a footer as the UNUSED exit lever.
  - render.py (stage 5) untouched: the chart-everything note stays the raw
    record, the timeline is the curated layer alongside it.

Manual-paste transport is a deliberate choice, not a stopgap: the module makes
zero API calls and adds no network client or dependency. The human copies the
payload into a Claude session and pastes the reply back. This keeps the module
stdlib-only and decoupled, and the anti-hallucination validation runs on ingest
regardless of where the reply came from.

Fix 1 (UTF-8 output): the print-payload CLI path now forces stdout to UTF-8
(`_force_utf8`, guarded for streams without `reconfigure`) before writing.
Without it, a payload carrying a non-cp1252 abstract character crashed the
Windows console with UnicodeEncodeError mid-write, truncating the payload.
Payload output is now platform-independent; PYTHONUTF8 no longer needs setting
by hand. The pure functions are untouched; only the CLI entry path reconfigures.

Fix 2 (preamble conciseness): the build_payload instruction preamble now tells
the model to keep each rationale to one short sentence, return only the fenced
JSON object with nothing outside it, and treat 15 to 20 as a ceiling not a
target (select fewer if fewer are genuinely foundational, do not pad toward 20).
The response-format spec and the no-inventing rule are unchanged;
parse_selection and validate_selection are unchanged.

OPEN, not a defect: selection recall across seeds is uncalibrated. The
diagnostics read was good, but whether the model reliably surfaces the same
groundwork set across different seeds (and across re-runs of one seed) is
unmeasured. Re-selecting is cheap (re-ingest overwrites the sidecar; the crawl
is untouched), so this is a calibration question to revisit when more seeds have
been run, not a blocker. Multi-seed merge (2026-07-02) gives a deterministic
cross-check for free: seed_count in the payload lets picks be compared against
the consensus set.

### Forward walk, multi-seed merge, topic dossier: BUILT (2026-07-02)

Reframes the module from "lineage of one paper" to "topic dossier": origins
(backward walk), pillars (multi-seed consensus), present (forward walk), and
gaps, in one artifact. Motivated by two findings already on record: the
backward walk cannot see past the seed (empty-2020s, TRUE ABSENCE), and a
single capped tree has degenerate in_degree so no honest "main study" signal
exists within one crawl. Three new modules, all fixture-tested, zero coupling
to the digest, no new dependencies. 118 lineage tests passing.

forward.py (the frontier): fetches works CITING the seed and each selected
groundwork paper via openalex.http_fetch_citing (two sorted pages per target,
most-cited plus most-recent, per-page 25, deduped; one paginated request per
sort instead of one request per reference, so it is far cheaper than the
backward walk). Same injectable-fetch pattern as traverse. Targets = seed plus
selection sidecar ids (seed only if no sidecar). Output is a sidecar
runs/{run_id}.forward.json (store.forward_path/write_forward/read_forward,
atomic, overwrite-permitted); the crawl run file is never mutated. Citer nodes
are normalized with to_node minus the backward-only fields (referenced_works,
depth, in_degree, phase). CLI: `python -m lineage.forward <run_file>`.

merge.py (the pillars): unions independent crawls of sibling seeds into one v2
run dict. Nodes union by openalex_id (lowest depth kept) with a new seed_count
field (how many source trees contain the node); edges union deduped; in_degree
recomputed across the merged graph; phases assigned. This is the honest
structural "main studies" signal the stage-3 analysis could not get from one
tree: independent trees overlapping is real co-citation evidence, obtained
without the deferred graph-enrichment project. The merged dict conforms to the
run schema, so select, timeline, forward, and dossier work on it unchanged.
run_id = {topic-slug}-merged-{YYYYMMDD}, written via store.write_run
(append-only); source runs never mutated. meta carries seeds, merged_from,
shared_node_count, summed unresolved/failed counts. select.build_payload shows
`in N/M seed trees` per node on merged runs, giving the LLM a real signal and
the human a deterministic cross-check on its picks. CLI: `python -m
lineage.merge <topic> <run_file>...`.

dossier.py (the artifact): renders Inbox/Lineages/{run_id}-dossier.md from the
(usually merged) run plus its selection sidecar plus the optional forward
sidecar. Sections: header with all seeds, narrative, Main studies
(decade-grouped selected nodes, rationale from the sidecar, seed_count
annotation), Consensus chart (Mermaid of seeds plus in_degree>=2 nodes only,
the exit-lever cut made principled by merging; section omitted when no shared
ancestor exists), Frontier (forward citers not already in the crawl, newest
first, capped at 20), Coverage gaps (selection gaps plus the mechanical
unresolved count). Anti-hallucination contract unchanged: every citation fact
comes from run/forward nodes by id; the drop-unknown-id guard runs at render
time (reuses timeline.selected_nodes). Overwrite guard mirrors the other
renderers. CLI: `python -m lineage.dossier <run_file> [vault_root] [--force]`.

End-to-end topic flow (laptop for the crawls, offline after):
  1. `python -m lineage.traverse <seed_doi>` per sibling seed (2 or 3 reviews)
  2. `python -m lineage.merge "<topic>" runs/<a>.json runs/<b>.json ...`
  3. `python -m lineage.select runs/<merged>.json` -> Claude session -> ingest
  4. `python -m lineage.forward runs/<merged>.json`
  5. `python -m lineage.dossier runs/<merged>.json .`
Single-seed runs still work at every step (merge is optional; forward and
dossier accept any v1/v2 run).

VALIDATION PENDING (laptop, OpenAlex unreachable from the container): crawl 1
or 2 sibling seeds for the diagnostics topic, merge, and look at the in_degree
distribution. If real overlap appears, the consensus chart earns its place; if
the trees barely intersect, that is important negative evidence recorded
cheaply. Then read a rendered dossier in the vault, same as the stage-6 human
read. Until that read, the dossier is built and tested but its VALUE is
unproven, per the run-the-experiment doctrine.

### Single-seed flow wrapper (BUILT 2026-07-02)

lineage/flow.py chains the single-seed crawl-to-dossier flow into ONE
interactive command with a single pause for the manual Claude paste, so the run
sequence (traverse -> select payload -> [paste] -> ingest -> forward -> dossier)
is no longer typed one line at a time. It adds NO new logic to any stage: it
imports and orchestrates the existing stage functions, so the anti-hallucination
validation and the overwrite guards keep working unchanged. Zero coupling to the
digest, stdlib-only, no new dependency. Entry point: `python -m lineage.flow
[seed_doi] [--force]` (prompts for the DOI if omitted).

run_flow is the testable core, taking injectable fetch/fetch_citing/prompt/
confirm/clipboard callables; __main__ wires openalex.http_fetch,
openalex.http_fetch_citing, and stdin prompts. Sequence:
  - clear_scratch: at the START of the run, if payload.txt/reply.json from a
    previous run exist, prompt to delete them (guards against ingesting a stale
    reply). This is the only cleanup; there is no end-of-run delete.
  - crawl_or_reuse: run_id is computed internally via store.make_run_id on the
    normalized input DOI, so no filename is typed. If today's run file already
    exists it is reused (no re-fetch); a FileExistsError from write_run (resolved
    DOI slugifies differently) falls back to reusing the on-disk run.
  - build_payload written to payload.txt AND copied to the clipboard
    (copy_to_clipboard, best-effort via PowerShell Set-Clipboard reading the
    UTF-8 file; a failure only warns, payload.txt is the reliable path).
  - ingest_reply: blocks on the paste, reads reply.json, and RETRIES on a
    ValueError from parse/validate (prose instead of JSON, no id matched) so a
    fumbled paste never discards the crawl. Returns the validated selection block
    (calls select.ingest to persist the sidecar, then store.read_selection).
  - forward walk, then prune-in-memory-if-v1, then dossier.write_note to
    Inbox/Lineages/{run_id}-dossier.md.

This produces the forward + dossier output (the topic-dossier artifact), NOT the
curated timeline; run lineage.timeline separately for that. The two network
stages (crawl, forward walk) still require the laptop (OpenAlex unreachable in
the container). Tested in lineage/tests/test_flow.py (fixture/injected-fetch):
scratch cleanup (delete on confirm, keep on decline, no prompt when nothing
stale), crawl-then-reuse without re-fetching, the bad-then-good ingest retry, and
a full end-to-end run asserting the dossier and both sidecars are written. The
multi-seed merge flow (Option B) is unchanged and still run stage by stage;
flow.py is single-seed only.

Fixed in passing: lineage/tests/test_prune.py REAL_RUNS globbed runs/*-2026*.json
and excluded .selection.json but not .forward.json, so a forward sidecar in runs/
(from a real dossier run) made the skipUnless prune tests crash with
KeyError: 'nodes'. The glob now excludes both sidecar suffixes. Pre-existing, not
caused by flow.py; surfaced when the suite ran with a forward sidecar present.

## 2026-07-02 overhaul (digest arm)

Applied as one batch on explicit instruction. All changes TDD-tested (30 tests
in tests/, new suite; run `python -m unittest discover -s tests -t .`).

- Scoring: top-3 mean replaces max cosine; self-calibrating thresholds from the
  corpus leave-one-out distribution (see Ranking). Thresholds recorded in the
  DB meta table (new, src/db.py ensure_meta_table/set_meta/get_meta) and in
  data/metrics.txt.
- Writer: explicit `- [ ] Relevant` line (the contract's literal box was never
  actually rendered before; the title checkbox was the only tick target),
  `Nearest seed:` line from matching_corpus_doi, Wildcard section (2
  seeded-random archive promotions with full checkboxes).
- blocks.py: single shared block parser for all checkbox consumers,
  pattern-based so old and new digest formats both parse. to_read.py rewritten
  on top of it in lockstep with the writer change (output format of
  Inbox/To Read.md unchanged).
- feedback.py: Step 6 feedback loop, offline, windowed, idempotent (see the
  Feedback loop section).
- column.py: weekly column packet at Inbox/Column/{year}-W{week}.md, from the
  last completed ISO week's digests: must-read section papers plus every
  ticked paper, deduplicated by DOI, grouped as Must-read this week / Marked
  relevant / Queued to read, each entry backlinked to its digest. Write-once
  (never overwritten; may carry hand notes); the daily workflow writes it the
  first run after a week completes. Self-check generated the real 2026-W26
  packet (15 papers) at build time.
- metrics.py: one line per run in committed data/metrics.txt (date, new, per
  tier counts, thresholds); re-running a date replaces its line. Tier drift and
  silent degradations become a plottable file.
- Workflow: fetch overlap days_back=3 (failed runs self-heal), feedback sweep
  before corpus rebuild, column and metrics steps, expanded commit list.

Self-checks run at build time: both suites green (30 digest, 118 lineage); real
digest for 2026-06-16 rendered to a temp dir (64 papers, all full blocks
carrying both checkboxes and nearest-seed lines, wildcard section present);
calibrated thresholds computed on the real 42-note corpus (0.9750/0.9674).
Known follow-up: watch the first ranked runs in data/metrics.txt; if the 90/50
percentile anchors prove too strict at the new statistic, adjust the anchors in
src/ranking/score.py (MUST_PERCENTILE/SKIM_PERCENTILE), not the thresholds.