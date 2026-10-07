"""
Core parsing, extraction engine, and data models for cmd-search_web.
"""

from __future__ import annotations
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol

SCHEMA_VERSION = "2.1.0"

# Exit codes
SUCCESS = 0
ERR_GENERAL = 1
ERR_INVALID_ARGS = 2
ERR_DATA_TRUNCATED = 10
ERR_AMBIGUOUS_SESSION = 11
ERR_POLL_TIMEOUT = 12
ERR_INDEX_OUT_OF_BOUNDS = 13
ERR_FILE_EXISTS = 14
ERR_NO_SESSION = 15
ERR_PERMISSION = 16
ERR_PARSE = 17
ERR_WRITE = 18
ERR_NO_TRANSCRIPT = 19

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    snippet: Optional[str] = None


@dataclass(frozen=True)
class SearchResult:
    schema_version: str
    conversation_id: str
    surface: str
    index: int
    tool_call_id: Optional[str]
    timestamp: str
    query: str
    summary: str
    sources: List[Source]
    is_truncated: bool


@dataclass
class ExportResult:
    success: bool
    output_files: List[str] = field(default_factory=list)
    total_exported: int = 0
    error: Optional[str] = None
    error_code: int = SUCCESS


class TranscriptSource(Protocol):
    def read_records(self) -> Iterator[Dict[str, Any]]: ...
    def has_truncation(self) -> bool: ...
    def source_path(self) -> Path: ...


class JsonlAdapter:
    def __init__(self, file_path: Path):
        self.path = file_path
        self._truncated = False

    def source_path(self) -> Path:
        return self.path

    def has_truncation(self) -> bool:
        return self._truncated

    def read_records(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return

        with open(self.path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                clean_line = line.strip()
                if not clean_line:
                    continue
                try:
                    record = json.loads(clean_line)
                    if bool(record.get("truncated_fields")):
                        self._truncated = True
                    yield record
                except json.JSONDecodeError:
                    # Ignore trailing/partial lines
                    continue


def resolve_transcript_source(conv_dir: Path) -> TranscriptSource:
    logs_dir = conv_dir / ".system_generated" / "logs"
    full_path = logs_dir / "transcript_full.jsonl"
    std_path = logs_dir / "transcript.jsonl"

    if full_path.exists():
        return JsonlAdapter(full_path)
    if std_path.exists():
        return JsonlAdapter(std_path)
    raise FileNotFoundError(f"No transcript found under {logs_dir}")


def clean_summary_and_citations(
    raw_content: str,
) -> tuple[str, List[Source]]:
    """Separates summary markdown from citations and parses URLs."""
    if not raw_content:
        return "", []

    lines = raw_content.splitlines()
    summary_lines: List[str] = []
    sources: List[Source] = []

    # Markdown link pattern: [title](url)
    link_regex = re.compile(r"\[(.*?)\]\((https?://[^\s\)]+)\)")
    raw_url_regex = re.compile(r"(https?://[^\s\)]+)")

    parsing_citations = False
    for line in lines:
        stripped = line.strip()
        if re.match(
            r"^#{1,3}\s+(Sources|Citations|References)", stripped, re.IGNORECASE
        ):
            parsing_citations = True
            continue

        if parsing_citations:
            match = link_regex.search(stripped)
            if match:
                sources.append(
                    Source(title=match.group(1), url=match.group(2))
                )
            else:
                raw_match = raw_url_regex.search(stripped)
                if raw_match:
                    url = raw_match.group(1)
                    sources.append(Source(title=url, url=url))
        else:
            summary_lines.append(line)

    summary_text = "\n".join(summary_lines).strip()
    return summary_text, sources


def pair_search_calls(
    records: Iterator[Dict[str, Any]],
    conversation_id: str,
    surface: str,
) -> List[SearchResult]:
    """Hybrid pairing algorithm: handles explicit ID pairing or step_index sequence."""
    pending_by_id: Dict[str, Dict[str, Any]] = {}
    pending_sequential: List[Dict[str, Any]] = []
    paired_results: List[SearchResult] = []

    for rec in records:
        rec_type = rec.get("type")
        step_index = rec.get("step_index", 0)
        timestamp = rec.get("created_at", "")

        # 1. Detect tool calls in PLANNER_RESPONSE
        if rec_type == "PLANNER_RESPONSE":
            tool_calls = rec.get("tool_calls", [])
            for tc in tool_calls:
                tc_name = (
                    tc.get("name")
                    or tc.get("tool_name")
                    or tc.get("tool")
                )
                if tc_name == "search_web":
                    args = tc.get("args") or tc.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"query": args}
                    query = args.get("query", "")
                    call_id = tc.get("id") or tc.get("tool_call_id")

                    call_meta = {
                        "call_id": call_id,
                        "query": query,
                        "timestamp": timestamp,
                        "step_index": step_index,
                    }

                    if call_id:
                        pending_by_id[call_id] = call_meta
                    else:
                        pending_sequential.append(call_meta)

        # 2. Detect search execution outputs
        elif rec_type in ("SEARCH_WEB", "GENERIC"):
            call_id = rec.get("tool_call_id")
            content = rec.get("content", "")
            is_truncated = bool(rec.get("truncated_fields"))

            matched_call = None
            if call_id and call_id in pending_by_id:
                matched_call = pending_by_id.pop(call_id)
            elif pending_sequential:
                last_call = pending_sequential[0]
                # Match sequential if step_index is adjacent or content matches search signature
                if (
                    step_index == last_call["step_index"] + 1
                    or "The search for" in content
                    or "Created At:" in content
                ):
                    matched_call = pending_sequential.pop(0)

            if matched_call and matched_call["query"]:
                summary, sources = clean_summary_and_citations(content)
                result = SearchResult(
                    schema_version=SCHEMA_VERSION,
                    conversation_id=conversation_id,
                    surface=surface,
                    index=len(paired_results),
                    tool_call_id=matched_call["call_id"],
                    timestamp=matched_call["timestamp"],
                    query=matched_call["query"],
                    summary=summary,
                    sources=sources,
                    is_truncated=is_truncated,
                )
                paired_results.append(result)

    return paired_results


def poll_and_extract_searches(
    conv_dir: Path,
    conversation_id: str,
    surface: str,
    expected_index: Optional[int] = None,
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    verbose: bool = False,
) -> tuple[List[SearchResult], bool]:
    """Polls the transcript file until records stabilize and expectations are met."""
    start_time = time.time()
    last_size = -1
    last_results: List[SearchResult] = []
    has_truncated_record = False

    while True:
        try:
            source = resolve_transcript_source(conv_dir)
            curr_size = source.source_path().stat().st_size
        except FileNotFoundError:
            curr_size = -1
            source = None

        if source and curr_size == last_size and curr_size > 0:
            records = list(source.read_records())
            last_results = pair_search_calls(
                iter(records), conversation_id, surface
            )
            has_truncated_record = source.has_truncation()

            if expected_index is not None:
                if expected_index == -1 and len(last_results) >= 1:
                    return last_results, has_truncated_record
                if (
                    expected_index >= 0
                    and len(last_results) >= expected_index + 1
                ):
                    return last_results, has_truncated_record
            elif len(last_results) > 0:
                return last_results, has_truncated_record

        last_size = curr_size
        if time.time() - start_time >= timeout:
            break
        time.sleep(poll_interval)

    return last_results, has_truncated_record
