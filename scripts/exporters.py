"""
Formatters and atomic writers for cmd-search_web results.
"""

from __future__ import annotations
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .engine import (
    ERR_FILE_EXISTS,
    ERR_WRITE,
    SCHEMA_VERSION,
    ExportResult,
    SearchResult,
)


def format_markdown(result: SearchResult) -> str:
    """Formats a single SearchResult into frontmatter-enabled Markdown."""
    clean_query = result.query.replace('"', '\\"')

    lines = [
        "---",
        f'title: "Web Search: {clean_query}"',
        f'date: {result.timestamp or datetime.now().isoformat()}',
        f'query: "{clean_query}"',
        "tool: search_web",
        f'tool_call_id: "{result.tool_call_id or ""}"',
        f"index: {result.index}",
        f'conversation_id: "{result.conversation_id}"',
        f'surface: "{result.surface}"',
        f'schema_version: "{result.schema_version}"',
        "tags:",
        "  - research",
        "  - web-search",
        "---",
        "",
        f"# {result.query}",
        "",
        "## Summary & Findings",
        result.summary if result.summary else "_No summary extracted._",
        "",
        "## Citations & Sources",
    ]

    if result.sources:
        for src in result.sources:
            lines.append(f"- [{src.title}]({src.url})")
    else:
        lines.append("_No citations found._")

    lines.append("")
    return "\n".join(lines)


def format_jsonl(results: List[SearchResult]) -> str:
    """Formats a list of SearchResult objects into JSON Lines."""
    return "".join(json.dumps(asdict(r)) + "\n" for r in results)


def atomic_write(target_path: Path, content: str, force: bool = False) -> None:
    """Performs crash-safe atomic write with 0600 permissions."""
    if target_path.exists() and not force:
        raise FileExistsError(f"Target file already exists: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.tmp_{os.getpid()}")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Set strict permissions on POSIX
        try:
            os.chmod(temp_path, 0o600)
        except Exception:
            pass  # Windows no-op

        os.replace(temp_path, target_path)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise OSError(f"Atomic write failed: {e}") from e


def export_results(
    results: List[SearchResult],
    output_dir: Optional[Path],
    fmt: str = "md",
    stdout: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> ExportResult:
    """Writes search results to stdout or target directory."""
    if not results:
        return ExportResult(success=True, output_files=[], total_exported=0)

    # 1. Handle STDOUT Mode
    if stdout:
        if fmt == "json":
            payload = {
                "schema_version": SCHEMA_VERSION,
                "conversation_id": results[0].conversation_id,
                "surface": results[0].surface,
                "results": [asdict(r) for r in results],
            }
            sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        elif fmt == "jsonl":
            for r in results:
                sys.stdout.write(json.dumps(asdict(r)) + "\n")
        else:  # md
            outputs = [format_markdown(r) for r in results]
            sys.stdout.write("\n---\n".join(outputs) + "\n")
        return ExportResult(
            success=True, output_files=["<stdout>"], total_exported=len(results)
        )

    # 2. Handle File Output Mode
    assert output_dir is not None
    written_files: List[str] = []

    try:
        if fmt == "json":
            target = output_dir / "searches.json"
            payload = {
                "schema_version": SCHEMA_VERSION,
                "conversation_id": results[0].conversation_id,
                "surface": results[0].surface,
                "results": [asdict(r) for r in results],
            }
            atomic_write(
                target, json.dumps(payload, indent=2) + "\n", force=force
            )
            written_files.append(str(target))

        elif fmt == "jsonl":
            target = output_dir / "searches.jsonl"
            atomic_write(target, format_jsonl(results), force=force)
            written_files.append(str(target))

        else:  # md
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            for r in results:
                target = output_dir / f"search_{r.index}_{ts}.md"
                content = format_markdown(r)
                atomic_write(target, content, force=force)
                written_files.append(str(target))

            if len(results) > 1:
                index_target = output_dir / "index.md"
                index_lines = [
                    f"# Search Results Index ({len(results)} queries)\n"
                ]
                for r in results:
                    index_lines.append(
                        f"- `[Index {r.index}]` **{r.query}** ({r.timestamp})"
                    )
                atomic_write(
                    index_target, "\n".join(index_lines) + "\n", force=force
                )
                written_files.append(str(index_target))

    except FileExistsError as e:
        return ExportResult(
            success=False, error=str(e), error_code=ERR_FILE_EXISTS
        )
    except Exception as e:
        return ExportResult(success=False, error=str(e), error_code=ERR_WRITE)

    return ExportResult(
        success=True,
        output_files=written_files,
        total_exported=len(written_files),
    )
