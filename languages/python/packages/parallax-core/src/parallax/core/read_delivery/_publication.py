from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Protocol

from parallax.core import deep_fetch
from parallax.core.execution_lifecycle import ReadInterface
from parallax.core.read_delivery._page import Page
from parallax.core.read_delivery._page_reader import EagerPageResult, HistoryPageResult
from parallax.core.temporal_read import TemporalShape

__all__ = ["Publication", "RootsOf"]


class RootsOf[Origin](Protocol):
    """One lifecycle's publication of the roots one sealed Page carries.

    ``includes`` is the requested Include Path tree. ``ordinal_offset`` is where
    this Page's roots start in the ordered result being published, which is
    nonzero wherever one result spans several Pages. ``sources`` is the origin
    each observed projection's value carries, keyed by projection index.
    ``milestones`` is the target family's Temporal Shape for a milestone-set
    read, whose roots each stand at their own edge. An ``atomic`` publication
    publishes nothing until every root of the Page has been published.
    """

    def __call__(
        self,
        page: Page,
        includes: deep_fetch.IncludeTree,
        /,
        *,
        atomic: bool = False,
        ordinal_offset: int = 0,
        sources: Mapping[int, Origin] = ...,
        milestones: TemporalShape | None = None,
    ) -> Iterator[object]: ...


class Publication[Origin, Eager](Protocol):
    """How one delivery turns its Pages' judged states into lifecycle values.

    Delivery-scoped: an eager read uses it once and a stream reuses it across
    every bounded Page, then :attr:`release` drops any representation-specific
    reuse state. Delivery invokes it inside the read or stream activity that
    owns the Page, so no Page outlives the operation that read it.
    :meth:`from_find` and :meth:`from_history` compose :attr:`roots_of` into an
    eager envelope, so neither is a conversion that could drift from the
    streamed one. ``interface`` names the read interface the activity reports,
    and ``edition`` the Model Edition every published envelope is stamped with.
    """

    @property
    def interface(self) -> ReadInterface: ...

    @property
    def roots_of(self) -> RootsOf[Origin]: ...

    @property
    def edition(self) -> str: ...

    @property
    def release(self) -> Callable[[], None]: ...

    def from_find(self, result: EagerPageResult[Origin], /) -> Eager: ...

    def from_history(self, result: HistoryPageResult, /) -> Eager: ...
