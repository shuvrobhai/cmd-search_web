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
    is_success: bool
    output_files: List[str] = field(default_factory=list)
    total_exported: int = 0
    error: Optional[str] = None
    error_code: int = SUCCESS


class TranscriptSource(Protocol):
    def read_records(self) -> Iterator[Dict[str, Any]]: ...
    def has_truncation(self) -> bool: ...
    def source_path(self) -> Path: ...


@dataclass(frozen=True)
class ProviderConfig:
    """Configures Provider-specific transcript schema contracts and naming conventions."""

    name: str = "antigravity"
    tool_name: str = "search_web"
    planner_record_types: tuple[str, ...] = ("PLANNER_RESPONSE",)
    execution_record_types: tuple[str, ...] = ("SEARCH_WEB", "GENERIC")
    search_signatures: tuple[str, ...] = ("The search for", "Created At:")
    env_brain_var: str = "ANTIGRAVITY_BRAIN_DIR"
    env_conv_var: str = "ANTIGRAVITY_CONV_ID"


ANTIGRAVITY_PROVIDER = ProviderConfig()


class MemoryTranscriptSource:
    """In-memory TranscriptSource adapter for fast, zero-I/O testing."""

    def __init__(
        self,
        records: List[Dict[str, Any]],
        has_truncation: bool = False,
        path: Optional[Path] = None,
    ) -> None:
        self._records = records
        self._has_truncation = has_truncation
        self._path = path or Path("/memory/transcript.jsonl")

    def source_path(self) -> Path:
        return self._path

    def has_truncation(self) -> bool:
        return self._has_truncation

    def read_records(self) -> Iterator[Dict[str, Any]]:
        yield from self._records


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


def parse_summary_and_citations(
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


def match_and_consume_sequential_call(
    step_index: int,
    content: str,
    pending_sequential: List[Dict[str, Any]],
    signatures: tuple[str, ...] = ("The search for", "Created At:"),
) -> Optional[Dict[str, Any]]:
    """Evaluates whether an execution record matches a pending search call sequentially.

    Checks step_index adjacency first (step_index == last_call['step_index'] + 1).
    Falls back to content signature presence ('The search for', 'Created At:').
    Returns the matched call (removing it from pending_sequential) or None.
    """
    if not pending_sequential:
        return None

    last_call = pending_sequential[0]
    is_adjacent = step_index == last_call["step_index"] + 1
    has_signature = any(sig in content for sig in signatures)

    if is_adjacent or has_signature:
        return pending_sequential.pop(0)

    return None


def pair_search_calls(
    records: Iterator[Dict[str, Any]],
    conversation_id: str,
    surface: str,
    provider: ProviderConfig = ANTIGRAVITY_PROVIDER,
) -> List[SearchResult]:
    """Hybrid pairing algorithm: handles explicit ID pairing or step_index sequence."""
    pending_by_id: Dict[str, Dict[str, Any]] = {}
    pending_sequential: List[Dict[str, Any]] = []
    paired_results: List[SearchResult] = []

    for record in records:
        rec_type = record.get("type")
        step_index = record.get("step_index", 0)
        timestamp = record.get("created_at", "")

        # 1. Detect tool calls in planner records
        if rec_type in provider.planner_record_types:
            tool_calls = record.get("tool_calls", [])
            for tool_call in tool_calls:
                tc_name = (
                    tool_call.get("name")
                    or tool_call.get("tool_name")
                    or tool_call.get("tool")
                )
                if tc_name == provider.tool_name:
                    args = tool_call.get("args") or tool_call.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"query": args}
                    query = args.get("query", "")
                    call_id = tool_call.get("id") or tool_call.get("tool_call_id")

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
        elif rec_type in provider.execution_record_types:
            call_id = record.get("tool_call_id")
            content = record.get("content", "")
            is_truncated = bool(record.get("truncated_fields"))

            matched_call = None
            if call_id and call_id in pending_by_id:
                matched_call = pending_by_id.pop(call_id)
            elif pending_sequential:
                matched_call = match_and_consume_sequential_call(
                    step_index, content, pending_sequential, provider.search_signatures
                )

            if matched_call and matched_call["query"]:
                summary, sources = parse_summary_and_citations(content)
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


def extract_searches(
    source: TranscriptSource,
    conversation_id: str,
    surface: str,
    provider: ProviderConfig = ANTIGRAVITY_PROVIDER,
) -> tuple[List[SearchResult], bool]:
    """Pure extraction: pairs search calls from a TranscriptSource without polling."""
    records = list(source.read_records())
    results = pair_search_calls(iter(records), conversation_id, surface, provider=provider)
    return results, source.has_truncation()


def poll_and_extract_searches(
    source_or_conv_dir: Path | TranscriptSource,
    conversation_id: str,
    surface: str,
    expected_index: Optional[int] = None,
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    verbose: bool = False,
    provider: ProviderConfig = ANTIGRAVITY_PROVIDER,
) -> tuple[List[SearchResult], bool]:
    """Polls a transcript source until records stabilize and expectations are met."""
    start_time = time.time()
    last_size = -1
    last_results: List[SearchResult] = []
    has_truncated_record = False

    while True:
        source: Optional[TranscriptSource] = None
        if isinstance(source_or_conv_dir, Path):
            try:
                source = resolve_transcript_source(source_or_conv_dir)
                current_size = source.source_path().stat().st_size
            except (FileNotFoundError, OSError):
                current_size = -1
                source = None
        else:
            source = source_or_conv_dir
            try:
                current_size = source.source_path().stat().st_size
            except (FileNotFoundError, OSError):
                current_size = 1

        is_memory_source = not isinstance(source_or_conv_dir, Path)
        is_stable_file = current_size == last_size and current_size > 0

        if source and (is_stable_file or is_memory_source):
            last_results, has_truncated_record = extract_searches(
                source, conversation_id, surface, provider=provider
            )

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

            if is_memory_source:
                return last_results, has_truncated_record

        last_size = current_size
        if time.time() - start_time >= timeout:
            break
        time.sleep(poll_interval)

    return last_results, has_truncated_record
