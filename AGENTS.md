# cmd-search_web

High-efficiency CLI web research extraction toolkit for Antigravity surfaces.

## Verification & Tooling

Always use `uv` for environment management:

- **Run tests**: `uv run pytest tests/`
- **Run typecheck**: `uv run --with mypy mypy scripts/`

## Architecture Pointers

- **Parsing & Polling**: [`scripts/engine.py`](scripts/engine.py) — Core transcript parsing, search pairing, JSONL adapter, and stabilization polling.
- **Surface Detection**: [`scripts/surfaces.py`](scripts/surfaces.py) — Discovers active Antigravity session (App vs. CLI) and transcript directories.
- **Exporters**: [`scripts/exporters.py`](scripts/exporters.py) — Formats research extractions into Markdown notes and JSONL feeds.
- **CLI Entrypoints**:
  - [`scripts/export_search.py`](scripts/export_search.py) (`cmd-search-web-export`) — Extracts recent or specific search results.
  - [`scripts/list_searches.py`](scripts/list_searches.py) (`cmd-search-web-list`) — Lists past search calls across sessions.
- **Test Suite**: [`tests/test_engine.py`](tests/test_engine.py) — Unit tests for transcript ingestion, pairing, and extraction.
