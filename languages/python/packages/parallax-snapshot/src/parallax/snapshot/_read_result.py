from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.deep_fetch import IncludeTree
from parallax.core.temporal_read import TemporalShape
from parallax.core.unit_work import ReadOrigin
from parallax.snapshot.materialize import InvalidData, Page

__all__ = [
    "FindResult",
    "HistoryFindResult",
    "PublishedRow",
    "RowsResult",
]


@dataclass(frozen=True, slots=True)
class FindResult:
    """A find's sealed delivery Page.

    ``includes`` is the query's own Include Paths as the relationship views a
    wire unwind follows. The Root View alone cannot supply them: it keeps
    every view any level loaded onto a node, so a back-reference would revisit
    its target forever. The executor knows the plan, so it hands the tree on.

    ``sources`` is the private Read Origin each observed projection's value will
    carry, keyed by that projection's own index in the Page. It travels
    with the Page because only the executor holds the row and the
    projection at once: a materializer builds the value, but the row it came from
    is gone by then.
    """

    page: Page
    includes: IncludeTree
    sources: Mapping[int, ReadOrigin] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's one database-ordered page of flat roots.

    ``milestones`` is the target family's Temporal Shape, whose axis starts are
    each root's own edge.
    """

    page: Page
    milestones: TemporalShape
    includes: IncludeTree


type PublishedRow = Mapping[str, object] | InvalidData[Mapping[str, object]]
"""One row-form result position: the transformed row itself, or the record a row
whose stored state contradicted the model publishes in its place.

The values lane's element type is the same union both public materializers
publish, one result position at a time — a row-form read has no graph, so its
own root IS the row."""


@dataclass(frozen=True, slots=True)
class RowsResult:
    """A row-form read's published rows.

    ``rows`` is every result position in result order, already eager, detached,
    and immutable, keyed as the read PROJECTED it — physical columns plus the
    synthetic ``familyVariant`` where the compiled read materializes one.
    ``edition`` is the Model Edition the read was served under, retained for
    later access exactly as the graph-form envelopes retain theirs.
    """

    rows: tuple[PublishedRow, ...]
    edition: str
