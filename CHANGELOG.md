# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Full-text PDF download (`core/fulltext.py`): `POST /api/download` and CLI `--download` / `--download-csv` write open-access PDFs to `out/pdf/`
- Download robustness: resume (skip files ≥ `min_bytes`, default 20KB), `%PDF` magic-number validation, per-run batch limit and polite delay; reuses `core/fetcher` retry/proxy/rate-limit handling
- PDF source registry: `arxiv` / `openreview` (direct link), `semanticscholar` / `europepmc` / `doaj` (conditional on open access)
- Universal DOI fallback: any article with a DOI is looked up via **Unpaywall → OpenAlex** for a legally open-access version, so `crossref` (metadata only) can still download when an OA copy exists; `openaire` returns an explicit reason
- Adapters enriched with `doi` / `url` (`openreview`, `doaj`, `semanticscholar`, `crossref`, `europepmc`) so results carry the identifiers needed for resolution (also restores the missing "原文" links)
- `GET /api/download/supported` exposes per-source download capability (with `mode`: direct / api / oa_lookup / none)
- Web UI: per-result `⬇ PDF` button and a `📄 下载 PDF` action-bar button for selected results

### Changed
- PDF download UX: multi-select downloads are chunked in the browser with live `n/N` progress, and results open a detail modal showing each item's status, size, channel (`via`), save directory and failure reason
- Test suites expanded: frontend↔backend field contract + static template checks, data persistence (history / operation log / CSV / export archive / PDF resume), a real-server HTTP smoke pass, and doc-asset consistency checks (240 tests total)

### Docs
- Project overview dashboard (both `project_overview/` and the `docs/` copy) refreshed: new "开放全文下载" section with per-source capability table, updated hero stats (20 endpoints), inline architecture SVG (Full-text node + `pdf/` output), source download badges, API table, structure tree, quickstart, config sample and roadmap
- Asset generators updated and re-run: `generate_architecture.py` (full-text download pipeline + 6 outputs), `generate_banner.py` (7 sources / 20 endpoints / 226 tests / 3.2k lines)
- In-app `/sources` page now shows each source's full-text download capability (badge + reason) plus a "只走正规渠道" note

## [1.1.0] - 2026-09-09

### Added
- Cross-database deduplication: DOI primary key + normalized title/year fallback, keeps the most complete record and merges hit sources into `sources`
- Result sorting: `relevance` / `citations` / `year` (CLI `--sort-by`, API `sort_by`, config `query.sort_by`)
- Multi-select export: Markdown / BibTeX / EndNote(RIS) / CSV / plain text via `POST /api/export`, archived under `out/exports/`
- In-page article preview: `GET /api/article/detail` fetches full abstract, authors, PDF link with 30-min cache (arxiv, crossref, semanticscholar, openreview, europepmc, doaj)
- Web UI: per-result checkbox, floating action bar (select all / export / copy), quick-preview modal, dedup toggle, sort selector, duplicate count badge, toast notifications

### Fixed
- Page routes crashed on Starlette 1.x (deprecated `TemplateResponse` signature)
- Search blocked the event loop; 429 rate-limit and retry events were swallowed (now streamed via SSE and executed in a thread pool)
- Nav version badge showed v0.1 while the project was at v1.0.0
- EventSource reconnected automatically after the server closed the stream, causing the search to repeat; the client now closes the connection on `complete`
- `X-Export-Path` response header used raw bytes, throwing `UnicodeEncodeError` (HTTP 500) for any keyword containing non-latin-1 characters; now URL-encoded
- `core/article_detail` returned source-specific fields under `extra`; the frontend could not read them. The unified `get_detail` flattens `extra` to the top level
- Europe PMC author list returned raw dicts (`[object Object]` in the UI); now returns plain strings
- Version strings drifted across `pyproject.toml` / `FastAPI` / `config.yaml` / `README` / `base.html`; aligned to v1.1.0
- Frontend progress log inserted raw server messages into HTML; now escaped to prevent DOM breakage
- `navigator.clipboard.writeText` failed outside HTTPS; added a `textarea + execCommand` fallback

### Changed
- `Article` gained an optional `sources` field; CSV output includes it

[Unreleased]: https://github.com/LPK3215/LitScan/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/LPK3215/LitScan/compare/v1.0.0...v1.1.0

### Added
- Multi-database search: arXiv, Semantic Scholar, Crossref, OpenReview, OpenAIRE, DOAJ, Europe PMC
- CLI entry (`litscan.py`) with keywords/year/limit overrides, proxy control, history commands
- FastAPI web server: search, history, sources, and logs pages
- SSE streaming search endpoint (`/api/search/stream`) with real-time progress
- Search history: list, search, retry, delete, per-record detail and stats
- Operation logger (`core/logger.py`) with `/logs` page and stats API
- Output pipeline: raw responses, unified CSV, retrieval log (`out/`)
- Proxy support: config file, environment variables, `--no-proxy` override
- Rate-limit handling with automatic retry and backoff

[Unreleased]: https://github.com/LPK3215/LitScan/compare/v1.1.0...HEAD
[1.0.0]: https://github.com/LPK3215/LitScan/releases/tag/v1.0.0
