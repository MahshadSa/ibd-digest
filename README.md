# IBD Imaging Digest

Automated daily digest of new IBD imaging papers, ranked by semantic relevance, delivered to an Obsidian vault.

## Log

### 2026-05-21 - Step 3 complete: embedding layer and ranking

- Added `src/ranking/embed.py`: loads SPECTER2 (`allenai/specter2_base`) from local HuggingFace cache (`local_files_only=True`), CPU inference only. Input format: `title + [SEP] + abstract`, max 512 tokens, truncated. Embedding is the CLS token (index 0 of last hidden state), float32, shape (N, 768). Batched to 16 texts at a time.
- Added `src/corpus.py`: reads `Corpus/seed_dois.txt`, deduplicates, fetches title and abstract for each DOI via PubMed E-utilities first with Crossref as fallback. Failures are logged per-DOI with a summary count at the end. Each fetched paper is embedded, stored in the `corpus` table, and written as a Markdown note in `Corpus/` (title, DOI link, abstract). Idempotent: skips DOIs already in `corpus` with a non-null embedding. Entry point: `python -m src.corpus`.
- Added `src/ranking/score.py`: `embed_pending` embeds all papers in `papers` with `embedding IS NULL` and stores the vector as a BLOB. `score_and_tier` loads all corpus embeddings, normalizes them, and computes max cosine similarity for each embedded paper; stores `similarity_score`, `matching_corpus_doi`, and `tier`. Tiers: must-read >= 0.75, skim 0.60-0.75, archive < 0.60.
- Added `src/rank.py`: single daily entry point that runs `migrate_embedding_columns`, `embed_pending`, and `score_and_tier` in sequence. Run with `python -m src.rank [db_path]`.
- Updated `src/db.py`: SCHEMA extended with `matching_corpus_doi TEXT` and `tier TEXT` on `papers`, and `abstract TEXT` on `corpus`. New `migrate_embedding_columns` handles existing databases idempotently using `PRAGMA table_info` and `sqlite_master` checks (no try/except).
- Updated `pyproject.toml`: declared `numpy`, `torch`, `transformers` as dependencies.

### 2026-05-20 - Step 2 complete: digest writer

- Built `src/digest/writer.py`; entry point is `python -m src.digest.writer [vault_root]`.
- Reads papers from SQLite where `seen_date` equals today (UTC), writes `Inbox/Papers/YYYY-MM-DD.md`, overwriting if the file already exists.
- Per-paper block: title, DOI link, authors (first two + corresponding author deduplicated), journal and date, abstract in a collapsible Obsidian callout (`> [!abstract]-`), and a `- [ ] Relevant` checkbox.
- Header carries date and total paper count; footer lists per-source counts.
- Empty days produce a note with "no new papers today, pipeline ran successfully."
- Fixed European Radiology fetcher: migrated from Springer RSS (missing authors and truncated abstracts) to Crossref API (ISSN 1432-1084), consistent with the other two journal sources.

### 2026-05-20 - Step 1 complete: source layer

- Built PubMed fetcher (`src/fetchers/pubmed.py`) using NCBI E-utilities API with an API key; query covers IBD imaging, treatment response monitoring, and high-level IBD reviews/guidelines; parameterized lookback window (`days_back`).
- Replaced planned RSNA RSS feeds (inaccessible) with three working sources:
  - Radiology via Crossref API (ISSN 0033-8419)
  - Radiology: Artificial Intelligence via Crossref API (ISSN 2638-6100)
  - European Radiology via Springer RSS (journal ID 330)
- Crossref fetcher handles JSON response, strips JATS/HTML markup from abstracts, and resolves publication date from `published-online`, `published`, or `published-print` fields in that priority order.
- Springer RSS fetcher reuses the same RSS parsing logic (prism/dc namespaces, RFC 2822 date parsing, DOI extraction from link as fallback).
- All four sources normalize to the same schema: DOI, title, authors, corresponding author, journal, date, abstract, source.
- Deduplication by DOI across the full batch before writing to SQLite; existing DOIs in the DB are also excluded.
- Pipeline entry point is `src/fetch.py`; run with `python -m src.fetch` or pass `days_back` as a positional argument.
- Confirmed pipeline runs end-to-end and writes new papers to `data/papers.db`.
