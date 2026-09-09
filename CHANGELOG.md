# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
