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

Pipeline order: `src.fetch` -> `src.rank` -> `src.digest.writer . --force`
The `--force` flag is required in the scheduled run because the writer guard
(added pre-Step 5) refuses to overwrite existing daily digests by default.
Local manual runs should omit `--force` to preserve any notes added to today's
file.

State persistence: `data/papers.db` and `Inbox/Papers/*.md` committed back to
`main` by `github-actions[bot]` with `[skip ci]` in the commit message.
Commit step is a no-op if nothing changed.

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
  3 prune.py     top-k per depth, hub weighting by in-degree, non-destructive
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

Live entry point: `python -m lineage.traverse <seed_doi> [depth]` resolves,
traverses, and persists via store.write_run.

Node schema (normalized; persisted on every node):
  - openalex_id   short id, URL prefix stripped (W123)
  - doi           lowercased, https://doi.org/ stripped, or null
  - title         from display_name
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
  title}, depth, nodes [...], edges [[citing_id, referenced_id], ...],
  meta {node_count, edge_count, sparse_ids}.

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