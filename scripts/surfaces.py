"""
Provider and session resolution for Antigravity surfaces.

Deep module encapsulating surface detection, brain directory discovery,
and conversation session resolution as defined in GLOSSARY.md.
"""

from __future__ import annotations
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .engine import (
    ANTIGRAVITY_PROVIDER,
    ERR_AMBIGUOUS_SESSION,
    ERR_GENERAL,
    ERR_INVALID_ARGS,
    ERR_NO_SESSION,
    ERR_NO_TRANSCRIPT,
    ProviderConfig,
    UUID_REGEX,
)

ProviderPaths = Dict[str, Path]

SURFACE_PATHS: ProviderPaths = {
    "cli": Path.home() / ".gemini" / "antigravity-cli" / "brain",
    "app": Path.home() / ".gemini" / "antigravity" / "brain",
    "ide": Path.home() / ".gemini" / "antigravity-ide" / "brain",
}


class SessionResolutionError(Exception):
    """Raised when conversation or brain directory resolution fails."""

    def __init__(self, message: str, error_code: int = ERR_GENERAL) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


@dataclass(frozen=True)
class Conversation:
    """A resolved conversation session within a Provider surface.

    Represents a single Provider conversational session identified by a UUID,
    containing transcripts, search results, and scratch outputs.
    """

    id: str
    surface: str
    conversation_dir: Path
    brain_dir: Path

    @property
    def transcript_dir(self) -> Path:
        return self.conversation_dir / ".system_generated" / "logs"

    @property
    def transcript_path(self) -> Optional[Path]:
        full = self.transcript_dir / "transcript_full.jsonl"
        if full.exists():
            return full
        std = self.transcript_dir / "transcript.jsonl"
        if std.exists():
            return std
        return None


def auto_detect_surface() -> Tuple[str, Path]:
    """Detect surface based on available directories.

    Falls back to 'cli'.
    """
    detected: List[Tuple[str, Path]] = []
    for name, path in SURFACE_PATHS.items():
        if path.exists() and path.is_dir():
            detected.append((name, path))

    if len(detected) == 1:
        return detected[0]
    if len(detected) > 1:
        for name, path in detected:
            if name == "cli":
                return name, path
        return detected[0]

    return "cli", SURFACE_PATHS["cli"]


def resolve_brain_dir(
    explicit_path: Optional[str | Path] = None,
    surface: Optional[str] = None,
    verbose: bool = False,
    provider: ProviderConfig = ANTIGRAVITY_PROVIDER,
) -> Tuple[str, Path]:
    """Resolve the brain root directory using precedence rules.

    Priority:
    1. explicit_path (--brain-dir)
    2. surface (--surface)
    3. Provider env brain var (e.g. ANTIGRAVITY_BRAIN_DIR)
    4. Auto-detected default
    """
    if explicit_path:
        resolved = Path(explicit_path).expanduser().resolve()
        if verbose:
            sys.stderr.write(f"[INFO] Using explicit brain-dir: {resolved}\n")
        return "custom", resolved

    if surface:
        surface_key = surface.lower()
        if surface_key not in SURFACE_PATHS:
            raise SessionResolutionError(
                f"Unknown surface '{surface}'. Allowed: {list(SURFACE_PATHS.keys())}",
                ERR_INVALID_ARGS,
            )
        resolved = SURFACE_PATHS[surface_key]
        if verbose:
            sys.stderr.write(
                f"[INFO] Resolved brain-dir for surface '{surface_key}': {resolved}\n"
            )
        return surface_key, resolved

    env_brain = os.environ.get(provider.env_brain_var)
    if env_brain:
        resolved = Path(env_brain).expanduser().resolve()
        if verbose:
            sys.stderr.write(
                f"[INFO] Using {provider.env_brain_var} env: {resolved}\n"
            )
        return "custom", resolved

    detected_surface, detected_path = auto_detect_surface()
    if verbose:
        sys.stderr.write(
            f"[INFO] Auto-detected surface '{detected_surface}': {detected_path}\n"
        )
    return detected_surface, detected_path


def resolve_conversation(
    conv_id: Optional[str] = None,
    auto: bool = False,
    surface: Optional[str] = None,
    brain_dir: Optional[str | Path] = None,
    verbose: bool = False,
    provider: ProviderConfig = ANTIGRAVITY_PROVIDER,
) -> Conversation:
    """Resolves and validates an active or explicit Conversation session.

    Encapsulates brain root resolution, surface detection, active session marker checks,
    10-minute recency filtering, UUID validation, and directory validation behind a single seam.

    Raises:
        SessionResolutionError: with domain error_code if validation fails.
    """
    if surface == "ide":
        raise SessionResolutionError(
            "IDE surface does not maintain JSONL transcripts.",
            ERR_NO_TRANSCRIPT,
        )

    surface_name, resolved_brain = resolve_brain_dir(brain_dir, surface, verbose, provider=provider)

    if not resolved_brain.exists():
        raise SessionResolutionError(
            f"Brain directory not found: {resolved_brain}",
            ERR_NO_SESSION,
        )

    # Priority 1: Explicit conv_id argument or provider env var (e.g. ANTIGRAVITY_CONV_ID)
    target_id = conv_id or os.environ.get(provider.env_conv_var)
    if target_id:
        if not UUID_REGEX.match(target_id):
            raise SessionResolutionError(
                f"Invalid UUID format for conv-id: {target_id}",
                ERR_INVALID_ARGS,
            )
        target_path = resolved_brain / target_id
        if not target_path.exists():
            raise SessionResolutionError(
                f"Conversation session directory not found: {target_path}",
                ERR_NO_SESSION,
            )
        return Conversation(
            id=target_id,
            surface=surface_name,
            conversation_dir=target_path,
            brain_dir=resolved_brain,
        )

    # Priority 2: Auto-detection
    if auto:
        active_marker = resolved_brain / ".active_session"
        if active_marker.exists():
            candidate = active_marker.read_text().strip()
            candidate_path = resolved_brain / candidate
            if UUID_REGEX.match(candidate) and candidate_path.exists():
                return Conversation(
                    id=candidate,
                    surface=surface_name,
                    conversation_dir=candidate_path,
                    brain_dir=resolved_brain,
                )

        now = time.time()
        recent_sessions: List[Tuple[float, Path]] = []
        for d in resolved_brain.iterdir():
            if d.is_dir() and UUID_REGEX.match(d.name):
                mtime = d.stat().st_mtime
                if now - mtime <= 600:  # 10 minutes window
                    recent_sessions.append((mtime, d))

        if len(recent_sessions) > 1:
            candidates_msg = "\n".join(f"  - {p.name}" for _, p in recent_sessions)
            raise SessionResolutionError(
                f"Multiple active sessions detected in the last 10 minutes:\n{candidates_msg}\n"
                "Specify --conv-id <UUID> to resolve ambiguity.",
                ERR_AMBIGUOUS_SESSION,
            )

        if len(recent_sessions) == 1:
            candidate_id = recent_sessions[0][1].name
            return Conversation(
                id=candidate_id,
                surface=surface_name,
                conversation_dir=recent_sessions[0][1],
                brain_dir=resolved_brain,
            )

        # Fallback to latest modified session directory
        all_sessions = [
            d
            for d in resolved_brain.iterdir()
            if d.is_dir() and UUID_REGEX.match(d.name)
        ]
        if all_sessions:
            all_sessions.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            latest = all_sessions[0]
            return Conversation(
                id=latest.name,
                surface=surface_name,
                conversation_dir=latest,
                brain_dir=resolved_brain,
            )

        raise SessionResolutionError(
            f"No sessions found under {resolved_brain}",
            ERR_NO_SESSION,
        )

    raise SessionResolutionError(
        "Either --conv-id <UUID> or --auto must be specified.",
        ERR_INVALID_ARGS,
    )


def resolve_session_dir(
    brain_dir: Path,
    conv_id: Optional[str],
    auto: bool,
    verbose: bool = False,
) -> Tuple[str, Path]:
    """Compatibility adapter for legacy callers."""
    conv = resolve_conversation(
        conv_id=conv_id,
        auto=auto,
        brain_dir=brain_dir,
        verbose=verbose,
    )
    return conv.id, conv.conversation_dir
