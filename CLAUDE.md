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
- Radiology (Crossref API, ISSN 0033-8419)
- Radiology: Artificial Intelligence (Crossref API, ISSN 2638-6100)
- European Radiology (Crossref API, ISSN 1432-1084)
- Deduplication by DOI across all four sources

### Storage
- Single SQLite database
- `papers` table: DOI (primary key), title, authors, corresponding author, journal, date, abstract, source, embedding vector, similarity score, seen date, relevance status
- `corpus` table: relevance seed set with embeddings of papers marked relevant

### Ranking
- Embedding model: SPECTER2 (local, biomedical/scientific)
- Initial corpus: 20 to 50 papers selected manually from Zotero
- Score: max cosine similarity between candidate and corpus
- Tiers:
  - Must-read: score ≥ 0.75
  - Skim: 0.60 to 0.75
  - Archive: score < 0.60
- Thresholds adjustable after seeing real numbers

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
- Relevance checkbox: `- [ ] Relevant`

Archive tier: collapsed section, title + DOI link + authors only, no checkboxes.

Footer: source breakdown (papers per source, duplicates merged).

Empty days: note still generated, says "no new papers today, pipeline ran successfully."

### Feedback loop
- User ticks `- [x] Relevant` on papers in the digest
- Weekly job scans past week's digest notes for checked boxes
- Extracts those DOIs, pulls embeddings, adds to corpus table
- Ranker sharpens over time

### Infrastructure
- Python project in a GitHub repo
- GitHub Actions runs the fetcher daily on a cron schedule
- Daily digest committed to the repo
- Repo syncs to Obsidian vault via git

## Build order

- [ ] Step 1: Source layer (PubMed + Crossref + Springer RSS fetchers, dedup by DOI, write to SQLite)
- [ ] Step 2: Digest writer (Markdown output from SQLite, no ranking yet)
- [ ] Step 3: Embedding layer (SPECTER2, corpus from Zotero selection, scoring and tiering)
- [ ] Step 4: Obsidian integration (file paths, callouts, checkbox convention)
- [ ] Step 5: GitHub Actions scheduling and git sync
- [ ] Step 6: Feedback loop (weekly job parses checkboxes, updates corpus)

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
)
AND English[Language]
NOT "Case Reports"[Publication Type]
AND "last 30 days"[PDat]

Scope includes adult and pediatric IBD imaging, treatment response and monitoring, plus high-level IBD reviews and guidelines (consensus papers, position statements, practice guidelines).

## Deferred (not in v1)

- LLM-generated abstract summaries
- Citation counts and altmetrics
- Author override filters (always surface specific authors regardless of score)
- Europe PMC, bioRxiv, medRxiv, arXiv sources
- Telegram or email notification for top-tier hits

## Step 4: Obsidian integration (done)

Digest writer renders papers grouped by tier with Obsidian callouts.

### Rendering conventions
- Must-read tier: `> [!important]` banner, papers rendered outside the callout with `- [ ]` at column 0.
- Skim tier: `> [!note]` banner, same pattern.
- Archive tier: `> [!abstract]-` container (collapsed), papers rendered inside with `> ` prefix on every line.
- Empty tiers are skipped entirely. Header counts still show zeros.
- Each paper: `- [ ] **Title**` followed by 2-space-indented metadata (authors, journal, date, DOI, score), then a nested `> [!abstract]-` callout for the abstract.
- DOI format is always `[10.xxxx/yyyy](https://doi.org/10.xxxx/yyyy)`.

### Step 6 parsing contract (do not break)
- Checked papers match `^>?\s*- \[[xX]\] \*\*` (handles both column-0 must-read/skim and `> `-prefixed archive).
- DOI extraction on the same paper block: `\[([^\]]+)\]\(https://doi\.org/[^\)]+\)`.
- Score extraction if needed: `Score: (\d+\.\d+)`.

Any change to the writer must preserve these patterns or update Step 6 in lockstep.

## Step 5: GitHub Actions scheduling — complete (2026-05-21)

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

## Next steps — do not start before 2026-06-01

System is at a natural rest point. Step 6 (feedback loop) is the planned next
step per the project handoff, but the order is a hypothesis. Use the system
daily for ~2 weeks first, then decide whether Step 6 is still the right
priority or whether friction observed in actual use points elsewhere.

While running, keep a friction log (in Obsidian, freeform) of things that
felt awkward, missing, or wrong during reading sessions. That log is the
real spec for what comes next.

Failure monitoring: GitHub notifies on workflow failure via email. If
notifications stop arriving for several days with no commits to `main`,
check the Actions tab.