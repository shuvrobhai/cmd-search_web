"""
Tests for cmd-search_web engine module.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.engine import (
    ERR_AMBIGUOUS_SESSION,
    ERR_DATA_TRUNCATED,
    ERR_INDEX_OUT_OF_BOUNDS,
    ERR_NO_TRANSCRIPT,
    ERR_POLL_TIMEOUT,
    SCHEMA_VERSION,
    SUCCESS,
    UUID_REGEX,
    SearchResult,
    Source,
    clean_summary_and_citations,
    pair_search_calls,
    poll_and_extract_searches,
)


class TestUuidRegex:
    def test_valid_uuid(self) -> None:
        assert UUID_REGEX.match("550e8400-e29b-41d4-a716-446655440000")

    def test_invalid_uuid(self) -> None:
        assert not UUID_REGEX.match("not-a-uuid")
        assert not UUID_REGEX.match("12345")


class TestCleanSummaryAndCitations:
    def test_empty_content(self) -> None:
        summary, sources = clean_summary_and_citations("")
        assert summary == ""
        assert sources == []

    def test_summary_only(self) -> None:
        raw = "Python is a programming language."
        summary, sources = clean_summary_and_citations(raw)
        assert summary == raw
        assert sources == []

    def test_citations_section(self) -> None:
        raw = (
            "Python is great.\n"
            "\n"
            "## Sources\n"
            "- [Python Docs](https://docs.python.org)\n"
            "- [PEP 8](https://peps.python.org/pep-0008/)\n"
        )
        summary, sources = clean_summary_and_citations(raw)
        assert "Python is great." in summary
        assert len(sources) == 2
        assert sources[0].title == "Python Docs"
        assert sources[0].url == "https://docs.python.org"
        assert sources[1].title == "PEP 8"
        assert sources[1].url == "https://peps.python.org/pep-0008/"

    def test_case_insensitive_citations_header(self) -> None:
        raw = "Summary text.\n### REFERENCES\n- [Title](https://example.com)"
        summary, sources = clean_summary_and_citations(raw)
        assert "Summary text." in summary
        assert len(sources) == 1
        assert sources[0].url == "https://example.com"


class TestPairSearchCalls:
    def _make_record(self, **overrides: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "type": "PLANNER_RESPONSE",
            "step_index": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "tool_calls": [],
        }
        base.update(overrides)
        return base

    def test_pairs_call_by_id(self) -> None:
        call = {
            "name": "search_web",
            "id": "call-123",
            "args": {"query": "python async"},
        }
        output = {
            "type": "SEARCH_WEB",
            "step_index": 1,
            "tool_call_id": "call-123",
            "content": "Async results.\n## Sources\n- [Real Python](https://realpython.com)",
            "truncated_fields": [],
        }
        records = [
            self._make_record(tool_calls=[call]),
            output,
        ]
        results = pair_search_calls(iter(records), "conv-1", "cli")
        assert len(results) == 1
        assert results[0].query == "python async"
        assert results[0].summary == "Async results."
        assert len(results[0].sources) == 1

    def test_truncation_flag(self) -> None:
        call = {
            "name": "search_web",
            "id": "call-1",
            "args": {"query": "test"},
        }
        output = {
            "type": "SEARCH_WEB",
            "step_index": 1,
            "tool_call_id": "call-1",
            "content": "Truncated.",
            "truncated_fields": ["content"],
        }
        records = [
            self._make_record(tool_calls=[call]),
            output,
        ]
        results = pair_search_calls(iter(records), "conv-1", "cli")
        assert results[0].is_truncated is True


class TestPollAndExtractSearches:
    def test_no_transcript(self, tmp_path: Path) -> None:
        conv_dir = tmp_path / "conv"
        conv_dir.mkdir()
        results, truncated = poll_and_extract_searches(
            conv_dir=conv_dir,
            conversation_id="00000000-0000-0000-0000-000000000000",
            surface="cli",
            timeout=0.1,
        )
        assert results == []
        assert truncated is False

    def test_transcript_with_results(self, tmp_path: Path) -> None:
        conv_dir = tmp_path / "conv"
        logs_dir = conv_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)
        transcript = logs_dir / "transcript.jsonl"
        call = {
            "type": "PLANNER_RESPONSE",
            "step_index": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "tool_calls": [
                {
                    "name": "search_web",
                    "id": "call-1",
                    "args": {"query": "fastapi"},
                }
            ],
        }
        output = {
            "type": "SEARCH_WEB",
            "step_index": 1,
            "tool_call_id": "call-1",
            "content": "FastAPI results.\n## Sources\n- [FastAPI](https://fastapi.tiangolo.com)",
            "truncated_fields": [],
        }
        with transcript.open("w") as f:
            f.write(json.dumps(call) + "\n")
            f.write(json.dumps(output) + "\n")
        results, truncated = poll_and_extract_searches(
            conv_dir=conv_dir,
            conversation_id="conv-1",
            surface="cli",
            timeout=1.0,
        )
        assert len(results) == 1
        assert results[0].query == "fastapi"
        assert truncated is False
        assert results[0].is_truncated is False

    def test_transcript_with_non_empty_truncated_fields(self, tmp_path: Path) -> None:
        conv_dir = tmp_path / "conv"
        logs_dir = conv_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)
        transcript = logs_dir / "transcript.jsonl"
        call = {
            "type": "PLANNER_RESPONSE",
            "step_index": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "tool_calls": [
                {
                    "name": "search_web",
                    "id": "call-1",
                    "args": {"query": "fastapi"},
                }
            ],
        }
        output = {
            "type": "SEARCH_WEB",
            "step_index": 1,
            "tool_call_id": "call-1",
            "content": "FastAPI results.\n## Sources\n- [FastAPI](https://fastapi.tiangolo.com)",
            "truncated_fields": ["content"],
        }
        with transcript.open("w") as f:
            f.write(json.dumps(call) + "\n")
            f.write(json.dumps(output) + "\n")
        results, truncated = poll_and_extract_searches(
            conv_dir=conv_dir,
            conversation_id="conv-1",
            surface="cli",
            timeout=1.0,
        )
        assert len(results) == 1
        assert results[0].query == "fastapi"
        assert truncated is True
        assert results[0].is_truncated is True

    def test_transcript_without_truncated_fields_key(self, tmp_path: Path) -> None:
        conv_dir = tmp_path / "conv"
        logs_dir = conv_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)
        transcript = logs_dir / "transcript.jsonl"
        call = {
            "type": "PLANNER_RESPONSE",
            "step_index": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "tool_calls": [
                {
                    "name": "search_web",
                    "id": "call-1",
                    "args": {"query": "fastapi"},
                }
            ],
        }
        output = {
            "type": "SEARCH_WEB",
            "step_index": 1,
            "tool_call_id": "call-1",
            "content": "FastAPI results.\n## Sources\n- [FastAPI](https://fastapi.tiangolo.com)",
        }
        with transcript.open("w") as f:
            f.write(json.dumps(call) + "\n")
            f.write(json.dumps(output) + "\n")
        results, truncated = poll_and_extract_searches(
            conv_dir=conv_dir,
            conversation_id="conv-1",
            surface="cli",
            timeout=1.0,
        )
        assert len(results) == 1
        assert results[0].query == "fastapi"
        assert truncated is False
        assert results[0].is_truncated is False
