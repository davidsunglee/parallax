"""One vocabulary for a diagnostic and one shape for reporting a run of them.

A checker's output is part of its contract: a reader who has learned to read one
command's failures should not have to learn a second spelling to read another's.
This module is deliberately neutral — it knows nothing about the compatibility
corpus, the command graph, or a language spec — so tooling on either side of
those boundaries can share it without importing the other's subject.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["Diagnostic", "report_failures"]


@dataclass(frozen=True)
class Diagnostic:
    """One problem, named by a stable code and described by a message.

    The code names the rule that was broken and is what a reader looks up or
    greps for; the message names the instance and is what tells them where to
    go. Codes are stable across runs, so a caller may treat one as an identifier
    rather than as prose.
    """

    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def report_failures(subject: str, detail: str, diagnostics: Sequence[Diagnostic]) -> None:
    """Print *diagnostics* as a failure of *subject*, one per line, on stderr.

    *detail* completes the summary line — what was examined, or where the
    problem is anchored — so the count is never the whole story.
    """
    print(f"{subject} FAILED ({len(diagnostics)} problem(s)): {detail}", file=sys.stderr)
    for diagnostic in diagnostics:
        print(f"  - {diagnostic}", file=sys.stderr)
