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
    ANTIGRAVITY_PROVIDER,
    ERR_AMBIGUOUS_SESSION,
    ERR_DATA_TRUNCATED,
    ERR_INDEX_OUT_OF_BOUNDS,
    ERR_NO_TRANSCRIPT,
    ERR_POLL_TIMEOUT,
    MemoryTranscriptSource,
    ProviderConfig,
    SCHEMA_VERSION,
    SUCCESS,
    UUID_REGEX,
    SearchResult,
    Source,
    clean_summary_and_citations,
    extract_searches,
    match_sequential_call,
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


class TestMatchSequentialCall:
    def test_adjacent_step_index_matches(self) -> None:
        pending = [{"call_id": None, "query": "pytest", "step_index": 2}]
        matched = match_sequential_call(
            step_index=3,
            content="Some search output",
            pending_sequential=pending,
        )
        assert matched is not None
        assert matched["query"] == "pytest"
        assert len(pending) == 0

    def test_content_signature_matches_even_if_not_adjacent(self) -> None:
        pending = [{"call_id": None, "query": "antigravity", "step_index": 1}]
        matched = match_sequential_call(
            step_index=5,
            content="Created At: 2024-01-01\nFound results",
            pending_sequential=pending,
        )
        assert matched is not None
        assert matched["query"] == "antigravity"
        assert len(pending) == 0

    def test_content_signature_the_search_for(self) -> None:
        pending = [{"call_id": None, "query": "search query", "step_index": 1}]
        matched = match_sequential_call(
            step_index=4,
            content="The search for 'search query' returned 3 results.",
            pending_sequential=pending,
        )
        assert matched is not None
        assert matched["query"] == "search query"
        assert len(pending) == 0

    def test_non_adjacent_without_signature_does_not_match(self) -> None:
        pending = [{"call_id": None, "query": "python", "step_index": 1}]
        matched = match_sequential_call(
            step_index=6,
            content="Output from bash command without search signature",
            pending_sequential=pending,
        )
        assert matched is None
        assert len(pending) == 1

    def test_empty_pending_returns_none(self) -> None:
        assert match_sequential_call(2, "content", []) is None


class TestSequentialPairingIntegration:
    def test_sequential_pairing_without_ids(self) -> None:
        records = [
            {
                "type": "PLANNER_RESPONSE",
                "step_index": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "tool_calls": [{"name": "search_web", "args": {"query": "sequential test"}}],
            },
            {
                "type": "SEARCH_WEB",
                "step_index": 1,
                "content": "Sequential result content.",
            },
        ]
        results = pair_search_calls(iter(records), "conv-1", "cli")
        assert len(results) == 1
        assert results[0].query == "sequential test"
        assert results[0].summary == "Sequential result content."

    def test_interleaved_explicit_and_sequential(self) -> None:
        records = [
            {
                "type": "PLANNER_RESPONSE",
                "step_index": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "tool_calls": [
                    {"name": "search_web", "id": "id-1", "args": {"query": "explicit"}},
                    {"name": "search_web", "args": {"query": "sequential"}},
                ],
            },
            {
                "type": "GENERIC",
                "step_index": 1,
                "content": "The search for sequential.",
            },
            {
                "type": "SEARCH_WEB",
                "step_index": 2,
                "tool_call_id": "id-1",
                "content": "Explicit result.",
            },
        ]
        results = pair_search_calls(iter(records), "conv-1", "cli")
        assert len(results) == 2
        queries = [r.query for r in results]
        assert "sequential" in queries
        assert "explicit" in queries


class TestProviderConfigCustomization:
    def test_custom_provider_config(self) -> None:
        custom_provider = ProviderConfig(
            name="custom",
            tool_name="web_research",
            planner_record_types=("AGENT_PLAN",),
            execution_record_types=("TOOL_EXEC",),
        )
        records = [
            {
                "type": "AGENT_PLAN",
                "step_index": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "tool_calls": [{"name": "web_research", "id": "call-x", "args": {"query": "custom"}}],
            },
            {
                "type": "TOOL_EXEC",
                "step_index": 1,
                "tool_call_id": "call-x",
                "content": "Custom result.",
            },
        ]
        results = pair_search_calls(iter(records), "conv-1", "cli", provider=custom_provider)
        assert len(results) == 1
        assert results[0].query == "custom"


class TestMemoryTranscriptSourceAndExtraction:
    def test_extract_searches_with_memory_source(self) -> None:
        records = [
            {
                "type": "PLANNER_RESPONSE",
                "step_index": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "tool_calls": [{"name": "search_web", "id": "mem-1", "args": {"query": "in memory"}}],
            },
            {
                "type": "SEARCH_WEB",
                "step_index": 1,
                "tool_call_id": "mem-1",
                "content": "In-memory content.",
            },
        ]
        source = MemoryTranscriptSource(records=records, has_truncation=False)
        results, truncated = extract_searches(source, "conv-1", "cli")
        assert len(results) == 1
        assert results[0].query == "in memory"
        assert truncated is False

    def test_poll_and_extract_searches_with_memory_source(self) -> None:
        records = [
            {
                "type": "PLANNER_RESPONSE",
                "step_index": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "tool_calls": [{"name": "search_web", "id": "mem-2", "args": {"query": "polled in memory"}}],
            },
            {
                "type": "SEARCH_WEB",
                "step_index": 1,
                "tool_call_id": "mem-2",
                "content": "Polled in-memory content.",
            },
        ]
        source = MemoryTranscriptSource(records=records, has_truncation=True)
        results, truncated = poll_and_extract_searches(
            conv_dir=source,
            conversation_id="conv-1",
            surface="cli",
            timeout=0.1,
        )
        assert len(results) == 1
        assert results[0].query == "polled in memory"
        assert truncated is True
