"""``parallax.snapshot._read_result`` enforcement scope (m-snapshot-read).

What a snapshot read HANDS BACK: a Snapshot Graph Input paired with the Read
Trace of the calls that produced it. `m-snapshot-read --> m-execution-log`
(`core/spec/modules.md`) exists for exactly this pairing — a read's round-trip
ceiling is observed through the record its result carries — so the edge is
declared where the record is actually named, and nowhere else.

This scope alone carries the module tag's full grant. The row-to-graph work sits
in the separate, narrower ``parallax.snapshot.materialize`` scope, which turns
driver rows into graph inputs and never names execution provenance. The split is
what keeps `m-sql` outside the closure of the grant every consumer of the
row-to-graph surface holds: a forbidden contract is the complement of a closure,
so a scope that must stay clear of SQL generation has to be granted a scope that
does not reach it.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.execution_log import ReadTrace
from parallax.snapshot.materialize import SnapshotGraphInput

__all__ = [
    "FindResult",
    "HistoryFindResult",
]


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's Snapshot Graph Input plus its Read Trace."""

    graph: SnapshotGraphInput
    execution: ReadTrace


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's ordered per-milestone graph inputs plus its
    (single-call) Read Trace.

    Each entry is a root-only graph pinned at its own milestone's from-instant
    (m-snapshot-read "The whole-graph pin"); a v1 milestone-set graph carries no
    includes (m-case-format).
    """

    graphs: tuple[SnapshotGraphInput, ...]
    execution: ReadTrace
