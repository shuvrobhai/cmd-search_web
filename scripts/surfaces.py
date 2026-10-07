"""
Surface-aware brain path resolution for Antigravity surfaces.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

SURFACE_PATHS = {
    "cli": Path.home() / ".gemini" / "antigravity-cli" / "brain",
    "app": Path.home() / ".gemini" / "antigravity" / "brain",
    "ide": Path.home() / ".gemini" / "antigravity-ide" / "brain",
}


def auto_detect_surface() -> Tuple[str, Path]:
    """Detect surface based on available directories.

    Falls back to 'cli'.
    """
    detected = []
    for name, path in SURFACE_PATHS.items():
        if path.exists() and path.is_dir():
            detected.append((name, path))

    if len(detected) == 1:
        return detected[0]
    if len(detected) > 1:
        # Ambiguous check: return cli if present, else first
        for name, path in detected:
            if name == "cli":
                return name, path
        return detected[0]

    return "cli", SURFACE_PATHS["cli"]


def resolve_brain_dir(
    explicit_path: Optional[str | Path] = None,
    surface: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[str, Path]:
    """Resolve the brain root directory using precedence rules.

    Priority:
    1. explicit_path (--brain-dir)
    2. surface (--surface)
    3. ANTIGRAVITY_BRAIN_DIR env var
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
            raise ValueError(
                f"Unknown surface '{surface}'. Allowed: {list(SURFACE_PATHS.keys())}"
            )
        resolved = SURFACE_PATHS[surface_key]
        if verbose:
            sys.stderr.write(
                f"[INFO] Resolved brain-dir for surface '{surface_key}': {resolved}\n"
            )
        return surface_key, resolved

    env_brain = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env_brain:
        resolved = Path(env_brain).expanduser().resolve()
        if verbose:
            sys.stderr.write(
                f"[INFO] Using ANTIGRAVITY_BRAIN_DIR env: {resolved}\n"
            )
        return "custom", resolved

    detected_surface, detected_path = auto_detect_surface()
    if verbose:
        sys.stderr.write(
            f"[INFO] Auto-detected surface '{detected_surface}': {detected_path}\n"
        )
    return detected_surface, detected_path
