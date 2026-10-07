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
from .surfaces import resolve_brain_dir


def resolve_session_dir(
    brain_dir: Path, conv_id: str | None, auto: bool, verbose: bool
) -> Tuple[str, Path]:
    if not brain_dir.exists():
        sys.stderr.write(f"[ERROR] Brain directory not found: {brain_dir}\n")
        sys.exit(ERR_NO_SESSION)

    # Priority 1: Explicit --conv-id
    target_id = conv_id or os.environ.get("ANTIGRAVITY_CONV_ID")
    if target_id:
        if not UUID_REGEX.match(target_id):
            sys.stderr.write(
                f"[ERROR] Invalid UUID format for conv-id: {target_id}\n"
            )
            sys.exit(ERR_INVALID_ARGS)
        target_path = brain_dir / target_id
        if not target_path.exists():
            sys.stderr.write(
                f"[ERROR] Conversation session directory not found: {target_path}\n"
            )
            sys.exit(ERR_NO_SESSION)
        return target_id, target_path

    # Priority 2: --auto flag
    if auto:
        active_marker = brain_dir / ".active_session"
        if active_marker.exists():
            candidate = active_marker.read_text().strip()
            if UUID_REGEX.match(candidate) and (brain_dir / candidate).exists():
                return candidate, brain_dir / candidate

        now = time.time()
        recent_sessions: List[Tuple[float, Path]] = []
        for d in brain_dir.iterdir():
            if d.is_dir() and UUID_REGEX.match(d.name):
                mtime = d.stat().st_mtime
                if now - mtime <= 600:  # 10 minutes window
                    recent_sessions.append((mtime, d))

        if len(recent_sessions) > 1:
            sys.stderr.write(
                "[ERROR] Multiple active sessions detected in the last 10 minutes:\n"
            )
            for _, p in recent_sessions:
                sys.stderr.write(f"  - {p.name}\n")
            sys.stderr.write("Specify --conv-id <UUID> to resolve ambiguity.\n")
            sys.exit(ERR_AMBIGUOUS_SESSION)

        if len(recent_sessions) == 1:
            return recent_sessions[0][1].name, recent_sessions[0][1]

        # Fallback to latest modified
        all_sessions = [
            d
            for d in brain_dir.iterdir()
            if d.is_dir() and UUID_REGEX.match(d.name)
        ]
        if all_sessions:
            all_sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            return all_sessions[0].name, all_sessions[0]

        sys.stderr.write(f"[ERROR] No sessions found under {brain_dir}\n")
        sys.exit(ERR_NO_SESSION)

    sys.stderr.write(
        "[ERROR] Either --conv-id <UUID> or --auto must be specified.\n"
    )
    sys.exit(ERR_INVALID_ARGS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract and export search_web results from Antigravity session logs."
    )

    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--conv-id", help="Conversation UUID")
    id_group.add_argument(
        "--auto", action="store_true", help="Auto-detect current active session"
    )

    parser.add_argument(
        "--surface",
        choices=["app", "cli", "ide"],
        default="cli",
        help="Antigravity surface",
    )
    parser.add_argument("--brain-dir", help="Explicit brain root directory")

    idx_group = parser.add_mutually_exclusive_group()
    idx_group.add_argument(
        "--index",
        type=int,
        default=-1,
        help="Search index (-1 for latest, 0 for first)",
    )
    idx_group.add_argument(
        "--all", action="store_true", help="Export all searches in session"
    )

    out_group = parser.add_mutually_exclusive_group()
    out_group.add_argument(
        "--output-dir", help="Output directory path (defaults to scratch/)"
    )
    out_group.add_argument(
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

    verb_group = parser.add_mutually_exclusive_group()
    verb_group.add_argument(
        "--verbose", action="store_true", help="Show execution details"
    )
    verb_group.add_argument(
        "--quiet", action="store_true", help="Suppress non-error logs"
    )

    args = parser.parse_args()

    # IDE limitations
    if args.surface == "ide":
        sys.stderr.write(
            "[ERROR] IDE surface does not maintain JSONL transcripts for search_web.\n"
        )
        sys.exit(ERR_NO_TRANSCRIPT)

    surface_name, brain_dir = resolve_brain_dir(
        args.brain_dir, args.surface, args.verbose
    )
    conv_id, conv_dir = resolve_session_dir(
        brain_dir, args.conv_id, args.auto, args.verbose
    )

    expected_idx = None if args.all else args.index
    searches, is_truncated = poll_and_extract_searches(
        conv_dir=conv_dir,
        conversation_id=conv_id,
        surface=surface_name,
        expected_index=expected_idx,
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
    target_out: Path | None = None
    if not args.stdout:
        if args.output_dir:
            target_out = Path(args.output_dir).expanduser().resolve()
        else:
            target_out = conv_dir / "scratch" / "search_web"
        try:
            target_out.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            sys.stderr.write(
                f"[ERROR] Permission denied writing to: {target_out}\n"
            )
            sys.exit(ERR_PERMISSION)

    res = export_results(
        results=selected_searches,
        output_dir=target_out,
        fmt=args.format,
        stdout=args.stdout,
        force=args.force,
        verbose=args.verbose,
    )

    if not res.success:
        sys.stderr.write(f"[ERROR] {res.error}\n")
        sys.exit(res.error_code)

    if not args.stdout and not args.quiet:
        for f in res.output_files:
            sys.stdout.write(f"Exported: {f}\n")

    sys.exit(SUCCESS)


if __name__ == "__main__":
    main()
