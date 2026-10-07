#!/usr/bin/env python3
"""
CLI entrypoint to extract and export search_web results from Antigravity session logs.
"""

from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

from .engine import (
    ERR_AMBIGUOUS_SESSION,
    ERR_DATA_TRUNCATED,
    ERR_GENERAL,
    ERR_INDEX_OUT_OF_BOUNDS,
    ERR_INVALID_ARGS,
    ERR_NO_SESSION,
    ERR_NO_TRANSCRIPT,
    ERR_PERMISSION,
    ERR_POLL_TIMEOUT,
    SUCCESS,
    UUID_REGEX,
    poll_and_extract_searches,
)
from .exporters import export_results
from .surfaces import (
    Conversation,
    SessionResolutionError,
    resolve_brain_dir,
    resolve_conversation,
    resolve_session_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and export search_web results from Antigravity session logs."
    )

    identity_group = parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--conv-id", help="Conversation UUID")
    identity_group.add_argument(
        "--auto", action="store_true", help="Auto-detect current active session"
    )

    parser.add_argument(
        "--surface",
        choices=["app", "cli", "ide"],
        default="cli",
        help="Antigravity surface",
    )
    parser.add_argument("--brain-dir", help="Explicit brain root directory")

    index_group = parser.add_mutually_exclusive_group()
    index_group.add_argument(
        "--index",
        type=int,
        default=-1,
        help="Search index (-1 for latest, 0 for first)",
    )
    index_group.add_argument(
        "--all", action="store_true", help="Export all searches in session"
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output-dir", help="Output directory path (defaults to scratch/)"
    )
    output_group.add_argument(
        "--stdout", action="store_true", help="Print directly to standard out"
    )

    parser.add_argument(
        "--format",
        choices=["md", "json", "jsonl"],
        default="md",
        help="Export format",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    parser.add_argument(
        "--allow-truncated",
        action="store_true",
        help="Allow truncated search logs without failing",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Log buffer poll timeout in seconds",
    )

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--verbose", action="store_true", help="Show execution details"
    )
    verbosity_group.add_argument(
        "--quiet", action="store_true", help="Suppress non-error logs"
    )

    args = parser.parse_args()

    try:
        conv = resolve_conversation(
            conv_id=args.conv_id,
            auto=args.auto,
            surface=args.surface,
            brain_dir=args.brain_dir,
            verbose=args.verbose,
        )
    except SessionResolutionError as err:
        sys.stderr.write(f"[ERROR] {err.message}\n")
        sys.exit(err.error_code)

    expected_index = None if args.all else args.index
    searches, is_truncated = poll_and_extract_searches(
        source_or_conv_dir=conv.conversation_dir,
        conversation_id=conv.id,
        surface=conv.surface,
        expected_index=expected_index,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    if not searches:
        sys.stderr.write("[ERROR] No search_web records found.\n")
        sys.exit(ERR_INDEX_OUT_OF_BOUNDS)

    # Truncation Guard
    if is_truncated and not args.allow_truncated:
        sys.stderr.write(
            "[ERROR] Search record is truncated in logs. Pass --allow-truncated to permit lossy export.\n"
        )
        sys.exit(ERR_DATA_TRUNCATED)

    # Slice results
    if args.all:
        selected_searches = searches
    else:
        try:
            selected_searches = [searches[args.index]]
        except IndexError:
            sys.stderr.write(
                f"[ERROR] Index {args.index} out of bounds (found {len(searches)} search records).\n"
            )
            sys.exit(ERR_INDEX_OUT_OF_BOUNDS)

    # Resolve output directory
    resolved_output_dir: Path | None = None
    if not args.stdout:
        if args.output_dir:
            resolved_output_dir = Path(args.output_dir).expanduser().resolve()
        else:
            resolved_output_dir = conv.conversation_dir / "scratch" / "search_web"
        try:
            resolved_output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            sys.stderr.write(
                f"[ERROR] Permission denied writing to: {resolved_output_dir}\n"
            )
            sys.exit(ERR_PERMISSION)

    res = export_results(
        results=selected_searches,
        output_dir=resolved_output_dir,
        output_format=args.format,
        stdout=args.stdout,
        force=args.force,
        verbose=args.verbose,
    )

    if not res.is_success:
        sys.stderr.write(f"[ERROR] {res.error}\n")
        sys.exit(res.error_code)

    if not args.stdout and not args.quiet:
        for file_path in res.output_files:
            sys.stdout.write(f"Exported: {file_path}\n")

    sys.exit(SUCCESS)


if __name__ == "__main__":
    main()
