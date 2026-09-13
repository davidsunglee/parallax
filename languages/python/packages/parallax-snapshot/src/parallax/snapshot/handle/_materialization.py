"""The shared read-page and root-publication seam for every Snapshot lane."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, overload

from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import Page, RootView

if TYPE_CHECKING:
    from parallax.core.db_port import DatabaseConnection, Row
    from parallax.core.entity._layout import CatalogedModel
    from parallax.core.execution_lifecycle._activity import DatabaseCallScope
    from parallax.core.object_query._validated import ValidatedObjectQuery
    from parallax.core.sql_gen._compile import CompiledRead
    from parallax.core.unit_work import Concurrency
    from parallax.snapshot._read_result import FindResult
    from parallax.snapshot.handle._paging import At, DeliveryPage, PagePlan
    from parallax.snapshot.handle._read import RowPublication
    from parallax.snapshot.handle._retention import ObservationLedger

__all__ = [
    "INERT",
    "EagerPageRead",
    "FlatPageRead",
    "MaterializationObserver",
    "Materializer",
    "StreamPageRead",
]


class MaterializationObserver(Protocol):
    """Aggregate cadence events emitted by the shared materialization path."""

    def prepared(self, levels: int) -> None: ...

    def statement_rendered(self, level: int) -> None: ...

    def statement_executed(self, level: int, rows: int) -> None: ...

    def occurrences_reached(self, count: int) -> None: ...

    def witnesses_compared(self, count: int) -> None: ...

    def states_decoded(self) -> None: ...

    def states_shared(self) -> None: ...

    def root_published(self, ordinal: int) -> None: ...


@dataclass(frozen=True, slots=True)
class _InertObserver:
    def prepared(self, levels: int) -> None:
        del levels

    def statement_rendered(self, level: int) -> None:
        del level

    def statement_executed(self, level: int, rows: int) -> None:
        del level, rows

    def occurrences_reached(self, count: int) -> None:
        del count

    def witnesses_compared(self, count: int) -> None:
        del count

    def states_decoded(self) -> None:
        pass

    def states_shared(self) -> None:
        pass

    def root_published(self, ordinal: int) -> None:
        del ordinal


INERT: MaterializationObserver = _InertObserver()


@dataclass(frozen=True, slots=True)
class EagerPageRead:
    """Inputs for one eager Page read."""

    query: ValidatedObjectQuery
    model: CatalogedModel
    port: DatabaseConnection
    preference: Concurrency | None
    ledger: ObservationLedger | None
    calls: DatabaseCallScope


@dataclass(frozen=True, slots=True)
class FlatPageRead:
    """Inputs for one statement whose rows form a root-only Page."""

    model: CatalogedModel
    compiled: CompiledRead
    read: Callable[[], Sequence[Row]]
    pin: Pin


@dataclass(frozen=True, slots=True)
class StreamPageRead:
    """Inputs for one bounded Page in an already prepared delivery."""

    plan: PagePlan
    at: At
    model: CatalogedModel
    port: DatabaseConnection
    preference: Concurrency | None
    ledger: ObservationLedger | None
    calls: DatabaseCallScope


@dataclass(frozen=True, slots=True)
class Materializer:
    """The two delivery operations: build a Page, then publish its roots."""

    observer: MaterializationObserver = INERT

    @overload
    def read_page(self, request: EagerPageRead) -> FindResult: ...

    @overload
    def read_page(self, request: FlatPageRead) -> RowPublication: ...

    @overload
    def read_page(self, request: StreamPageRead) -> DeliveryPage: ...

    def read_page(
        self, request: EagerPageRead | FlatPageRead | StreamPageRead
    ) -> FindResult | RowPublication | DeliveryPage:
        """Prepare, execute, and assemble one lane Page from typed inputs."""
        if isinstance(request, EagerPageRead):
            from parallax.snapshot.handle._read import build_page, read_roots

            roots = read_roots(
                request.query,
                request.model,
                request.port,
                preference=request.preference,
                calls=request.calls,
                observer=self.observer,
            )
            return build_page(
                roots,
                request.model,
                request.port,
                preference=request.preference,
                ledger=request.ledger,
                calls=request.calls,
            )
        if isinstance(request, FlatPageRead):
            from parallax.snapshot.handle._read import judge_rows
            from parallax.snapshot.materialize._views import ROOT_LEVEL

            self.observer.prepared(1)
            self.observer.statement_rendered(ROOT_LEVEL)
            rows = request.read()
            self.observer.statement_executed(ROOT_LEVEL, len(rows))
            return judge_rows(
                request.model,
                request.compiled,
                rows,
                pin=request.pin,
                observer=self.observer,
            )

        from parallax.snapshot.handle._paging import read_delivery_page

        return read_delivery_page(
            request.plan,
            request.at,
            request.model,
            request.port,
            preference=request.preference,
            ledger=request.ledger,
            calls=request.calls,
            observer=self.observer,
        )

    def roots[T](
        self,
        page: Page,
        publish: Callable[[RootView, int], Iterator[T]],
        *,
        ordinal_offset: int = 0,
        pins: Sequence[Pin | None] | None = None,
    ) -> Iterator[T]:
        """Judge and publish one Page root at a time through one shared seam."""
        if pins is not None and len(pins) != page.root_count:
            raise ValueError("root pin count must match the Page root count")
        for position in range(page.root_count):
            pin = None if pins is None else pins[position]
            root = RootView(page, position, pin=pin)
            yield from publish(root, position)
            self.observer.root_published(ordinal_offset + position)
