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
        source_or_conv_dir=conv.conversation_dir,
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
    for search in searches:
        trunc_flag = " [TRUNCATED]" if search.is_truncated else ""
        sys.stdout.write(
            f"{search.index:<7} | {search.timestamp[:19]:<20} | {search.query}{trunc_flag}\n"
        )

    sys.exit(SUCCESS)


if __name__ == "__main__":
    main()
