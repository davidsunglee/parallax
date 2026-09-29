"""The committed cost evidence as a scheduling resource: which files it is, and
the fixture an item requests to read them.

A test whose verdict depends on the committed captures, or on the memory gates
derived from one, is true only while that evidence is current, and only a
recapture makes it current again, so requesting :data:`FIXTURE` schedules the
item in the cost class exactly as requesting ``profile_run`` schedules it with a
database. The runner refuses any other open of the evidence in the test process.

The refusal is an audit hook, so it stops at the process boundary: a child the
test spawns inherits no hook and can read the evidence while the item stays
``dbfree``. Carrying the hook into children would add it to the interpreters
whose whole-heap readings the memory gates grade.
"""

from __future__ import annotations

import os
from pathlib import PurePath
from typing import Final

from tests._support.repo import PY_ROOT

__all__ = ["CAPTURES", "FIXTURE", "GATES", "EvidenceRefused", "is_committed"]

FIXTURE: Final = "committed_cost_evidence"
"""The fixture an item requests to read the committed cost evidence."""

CAPTURES: Final = "docs/*-envelope/**/*.json"
"""Every capture record retained under an envelope directory, relative to the
Python root: the canonical capture and every comparison base beside it."""

GATES: Final = "spec/memory-gates.yaml"
"""The memory gates derived from the canonical capture, relative to the Python root."""

_ROOT: Final = f"{PY_ROOT}{os.sep}"
_GATES_PATH: Final = str(PY_ROOT / GATES)


class EvidenceRefused(BaseException):
    """An item that did not request the committed cost evidence opened it.

    Not an :class:`Exception`, so an opener that handles its own errors cannot
    turn the refusal into a pass.
    """


def is_committed(path: str) -> bool:
    """Whether the absolute *path* is committed cost evidence."""
    if not path.startswith(_ROOT):
        return False
    return path == _GATES_PATH or PurePath(path[len(_ROOT) :]).full_match(CAPTURES)
