# cmd-search_web

High-efficiency CLI web research extraction toolkit for Antigravity.

## Overview

A script-driven, token-conserving research pipeline for Antigravity surfaces (App, CLI). It executes native `search_web`, delegates result extraction and note generation directly to local Python scripts, and returns minimal summaries without polluting the LLM conversation context.

## Requirements

- Python >= 3.10
- Antigravity CLI/App/IDE with JSONL transcript logs

## Installation

```bash
uv sync --extra dev
```

## CLI Commands

| Task | Command |
|------|---------|
| List past searches | `uv run python -m scripts.list_searches --auto` |
| Export latest search | `uv run python -m scripts.export_search --auto --index -1` |
| Export all as JSONL | `uv run python -m scripts.export_search --auto --all --format jsonl` |
| Custom destination | `uv run python -m scripts.export_search --auto --output-dir docs/research/` |

## Error Codes

| Code | Cause | Action |
|------|-------|--------|
| 10 | Log truncated on disk | Re-run with `--allow-truncated` |
| 11 | Multiple active sessions | Run `list_searches.py` or pass `--conv-id` |
| 12 | I/O buffer flush delayed | Retry with `--timeout 10.0` |
| 13 | Search index not found | Run `list_searches.py --auto` |
| 14 | Target note already exists | Pass `--force` |
| 19 | Invoked from IDE surface | Run via App or CLI (agy) |

## Development

```bash
# Run tests
uv run pytest tests/

# Type check
uv run mypy scripts/ tests/
```

## License

MIT
