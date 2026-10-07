#!/usr/bin/env python3
"""
CLI helper to list and inspect search_web calls in an Antigravity conversation.
"""

from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict

from .engine import (
    ERR_NO_TRANSCRIPT,
    SCHEMA_VERSION,
    SUCCESS,
    poll_and_extract_searches,
)
from .surfaces import SessionResolutionError, resolve_conversation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List search_web calls in an Antigravity conversation."
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
    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON array"
    )

    args = parser.parse_args()

    try:
        conv = resolve_conversation(
            conv_id=args.conv_id,
            auto=args.auto,
            surface=args.surface,
            brain_dir=args.brain_dir,
            verbose=False,
        )
    except SessionResolutionError as err:
        sys.stderr.write(f"[ERROR] {err.message}\n")
        sys.exit(err.error_code)

    searches, _ = poll_and_extract_searches(
        conv_dir=conv.dir,
        conversation_id=conv.id,
        surface=conv.surface,
        timeout=1.0,
    )

    if args.json:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "conversation_id": conv.id,
            "surface": conv.surface,
            "total": len(searches),
            "searches": [asdict(s) for s in searches],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        sys.exit(SUCCESS)

    if not searches:
        sys.stdout.write(f"No search_web calls found for session {conv.id}.\n")
        sys.exit(SUCCESS)

    sys.stdout.write(f"Found {len(searches)} search(es) in session {conv.id}:\n")
    sys.stdout.write(f"{'INDEX':<7} | {'TIMESTAMP':<20} | {'QUERY'}\n")
    sys.stdout.write("-" * 65 + "\n")
    for s in searches:
        trunc_flag = " [TRUNCATED]" if s.is_truncated else ""
        sys.stdout.write(
            f"{s.index:<7} | {s.timestamp[:19]:<20} | {s.query}{trunc_flag}\n"
        )

    sys.exit(SUCCESS)


if __name__ == "__main__":
    main()
