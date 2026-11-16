"""What every pooled primary-key diagnostic shares with the launcher that captures it.

``tools/pooled_primary_key_diagnostic.py`` names a mode and an output directory
through the environment; a diagnostic test reads them here and writes each of
its cells there as one file. Unset, the test runs its check protocol and writes
nothing, so the same test grades its readings in an ordinary run and captures
them when launched.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal

__all__ = [
    "MODES",
    "MODE_VARIABLE",
    "OUT_VARIABLE",
    "DiagnosticRefused",
    "Mode",
    "requested",
    "write_readings",
]

OUT_VARIABLE: Final = "PARALLAX_POOLED_KEY_DIAGNOSTIC_OUT"
MODE_VARIABLE: Final = "PARALLAX_POOLED_KEY_DIAGNOSTIC_MODE"

type Mode = Literal["assigned", "generated"]
MODES: Final[tuple[Mode, ...]] = ("assigned", "generated")


class DiagnosticRefused(AssertionError):
    """A reading that cannot be trusted, or a request no diagnostic can answer."""


def requested() -> tuple[Mode, Path | None]:
    """The mode and output directory the launcher asked for, or ``assigned``
    and no output for a check run, which grades every mode it supports."""
    out = os.environ.get(OUT_VARIABLE)
    mode = os.environ.get(MODE_VARIABLE, "assigned")
    if mode not in MODES:
        raise DiagnosticRefused(f"mode {mode!r} is not one of {MODES}")
    if out is not None and not Path(out).is_dir():
        raise DiagnosticRefused(f"the output directory {out} does not exist")
    return mode, None if out is None else Path(out)


def write_readings(out: Path, cell: str, document: Mapping[str, object]) -> None:
    """Write ``cell``'s readings into the output directory ``out``."""
    (out / f"{cell}.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
