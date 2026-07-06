"""Filesystem anchors for the monorepo.

The harness is invoked with an explicit path to ``core/compatibility`` (or
``core/spec/...``) on the command line, so it does not hard-code a repo layout.
This module only provides the schemas directory, which is found relative to the
``core/`` ancestor of whatever compatibility/spec path was supplied.
"""

from __future__ import annotations

from pathlib import Path


def find_core_root(start: Path) -> Path:
    """Walk up from *start* to the ``core/`` directory that contains it.

    Works whether the caller passes ``core``, ``core/compatibility``,
    ``core/spec/modules.md``, or any descendant.
    """
    start = start.resolve()
    candidates = [start, *start.parents]
    for candidate in candidates:
        if candidate.name == "core" and (candidate / "schemas").is_dir():
            return candidate
    # Fall back to a sibling ``core`` if *start* lives next to it (e.g. the repo
    # root was passed). This keeps error messages actionable.
    for candidate in candidates:
        sibling = candidate / "core"
        if (sibling / "schemas").is_dir():
            return sibling
    raise FileNotFoundError(
        f"could not locate the core/ directory (with a schemas/ child) from {start}"
    )


def schemas_dir(start: Path) -> Path:
    """Return the ``core/schemas`` directory for the given compatibility/spec path."""
    return find_core_root(start) / "schemas"
