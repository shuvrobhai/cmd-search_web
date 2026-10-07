"""
Unit tests for exporters module (Markdown, JSONL formatting and atomic write crash-safety).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.engine import ERR_FILE_EXISTS, SCHEMA_VERSION, SearchResult, Source
from scripts.exporters import (
    atomic_write,
    export_results,
    format_jsonl,
    format_markdown,
)


def _sample_result(index: int = 0) -> SearchResult:
    return SearchResult(
        schema_version=SCHEMA_VERSION,
        conversation_id="550e8400-e29b-41d4-a716-446655440000",
        surface="cli",
        index=index,
        tool_call_id="call-1",
        timestamp="2024-01-01T12:00:00Z",
        query="fastapi python",
        summary="FastAPI is a modern web framework.",
        sources=[
            Source(title="FastAPI Official", url="https://fastapi.tiangolo.com"),
            Source(title="GitHub", url="https://github.com/fastapi/fastapi"),
        ],
        is_truncated=False,
    )


class TestFormatMarkdown:
    def test_markdown_with_citations(self) -> None:
        result = _sample_result()
        md = format_markdown(result)

        assert "---" in md
        assert 'title: "Web Search: fastapi python"' in md
        assert "tool: search_web" in md
        assert "# fastapi python" in md
        assert "FastAPI is a modern web framework." in md
        assert "- [FastAPI Official](https://fastapi.tiangolo.com)" in md
        assert "- [GitHub](https://github.com/fastapi/fastapi)" in md

    def test_markdown_without_citations(self) -> None:
        result = SearchResult(
            schema_version=SCHEMA_VERSION,
            conversation_id="conv-1",
            surface="cli",
            index=0,
            tool_call_id=None,
            timestamp="",
            query="test",
            summary="",
            sources=[],
            is_truncated=False,
        )
        md = format_markdown(result)
        assert "_No summary extracted._" in md
        assert "_No citations found._" in md


class TestFormatJsonl:
    def test_jsonl_output(self) -> None:
        r1 = _sample_result(0)
        r2 = _sample_result(1)
        jsonl_str = format_jsonl([r1, r2])

        lines = [line for line in jsonl_str.strip().split("\n") if line]
        assert len(lines) == 2

        parsed_1 = json.loads(lines[0])
        assert parsed_1["index"] == 0
        assert parsed_1["query"] == "fastapi python"

        parsed_2 = json.loads(lines[1])
        assert parsed_2["index"] == 1


class TestWriteAtomic:
    def test_atomic_write_creates_file(self, tmp_path: Path) -> None:
        target = tmp_path / "notes" / "search.md"
        atomic_write(target, "hello world")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_atomic_write_file_exists_without_force_fails(self, tmp_path: Path) -> None:
        target = tmp_path / "search.md"
        target.write_text("initial")

        with pytest.raises(FileExistsError):
            atomic_write(target, "new content", force=False)

    def test_atomic_write_file_exists_with_force_succeeds(self, tmp_path: Path) -> None:
        target = tmp_path / "search.md"
        target.write_text("initial")

        atomic_write(target, "overwritten", force=True)
        assert target.read_text(encoding="utf-8") == "overwritten"


class TestExportResults:
    def test_export_results_markdown(self, tmp_path: Path) -> None:
        res = export_results(
            results=[_sample_result()],
            output_dir=tmp_path,
            fmt="md",
        )
        assert res.success is True
        assert res.total_exported == 1
        assert len(res.output_files) == 1
        assert Path(res.output_files[0]).exists()

    def test_export_results_jsonl(self, tmp_path: Path) -> None:
        res = export_results(
            results=[_sample_result(0), _sample_result(1)],
            output_dir=tmp_path,
            fmt="jsonl",
        )
        assert res.success is True
        assert res.total_exported == 1
        assert len(res.output_files) == 1
        assert Path(res.output_files[0]).name == "searches.jsonl"
