# IBD Imaging Digest

Automated daily digest of new IBD imaging papers, ranked by semantic relevance, delivered to an Obsidian vault.

## Log

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
