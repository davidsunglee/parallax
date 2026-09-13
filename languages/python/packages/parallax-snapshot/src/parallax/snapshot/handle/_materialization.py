"""The shared read-page and root-publication seam for every Snapshot lane."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, overload

from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import Page, PageBuilder, RootView
from parallax.snapshot.materialize._prepared import bind
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

if TYPE_CHECKING:
    from parallax.core.base import NeutralType
    from parallax.core.db_port import DatabaseConnection, Row
    from parallax.core.entity._layout import CatalogedModel
    from parallax.core.execution_lifecycle._activity import DatabaseCallScope
    from parallax.core.object_query._validated import ValidatedObjectQuery
    from parallax.core.unit_work import Concurrency
    from parallax.snapshot._read_result import FindResult
    from parallax.snapshot.handle._paging import At, DeliveryPage, PagePlan
    from parallax.snapshot.handle._retention import ObservationLedger

__all__ = [
    "INERT",
    "CompiledRead",
    "CompiledTemplate",
    "EagerPageRead",
    "FlatPageRead",
    "MaterializationObserver",
    "Materializer",
    "RowPublication",
    "StreamPageRead",
    "compile_read",
    "compile_template",
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
class RowPublication:
    """One flat batch and the Page-owned Entity States that judged it.

    Header metadata needed by row publication and predecessor evidence is retained
    beside the Page. Provider rows end at Page assembly.
    """

    variants: tuple[str | None, ...]
    documents: tuple[object | None, ...]
    publication_keys: tuple[tuple[str, ...], ...]
    publication_renames: tuple[tuple[tuple[str, str], ...], ...]
    publication_encodings: tuple[tuple[tuple[str, NeutralType], ...], ...]
    page: Page


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
            self.observer.prepared(1)
            self.observer.statement_rendered(ROOT_LEVEL)
            rows = request.read()
            self.observer.statement_executed(ROOT_LEVEL, len(rows))
            prepared = bind(request.model, request.compiled)
            builder = PageBuilder(ViewSchema.of(), self.observer)
            converted = tuple(
                prepared.convert_driver(row, builder, source=ROOT_LEVEL) for row in rows
            )
            page = builder.finish(tuple(item[0] for item in converted), request.pin)
            publication_keys = tuple(
                request.compiled.publication_keys(item[1], item[3]) for item in converted
            )
            publication_renames: list[tuple[tuple[str, str], ...]] = []
            for item, keys in zip(converted, publication_keys, strict=True):
                layout = request.model.layouts.entity(item[1])
                reads = request.compiled.attribute_reads(item[1])
                publication_renames.append(
                    tuple(
                        (attribute.storage.name, read.result_key)
                        for attribute, read in zip(layout.attributes, reads, strict=True)
                        if attribute.storage.name not in keys and read.result_key in keys
                    )
                    if reads
                    else ()
                )
            publication_encodings: list[tuple[tuple[str, NeutralType], ...]] = []
            for item, keys in zip(converted, publication_keys, strict=True):
                layout = request.model.layouts.entity(item[1])
                reads = request.compiled.attribute_reads(item[1])
                publication_encodings.append(
                    tuple(
                        (
                            read.result_key if read.result_key in keys else attribute.storage.name,
                            attribute.type,
                        )
                        for attribute, read in zip(layout.attributes, reads, strict=True)
                        if read.encoded
                        and (read.result_key in keys or attribute.storage.name in keys)
                    )
                    if reads
                    else ()
                )
            return RowPublication(
                tuple(item[3] for item in converted),
                tuple(item[2] for item in converted),
                publication_keys,
                tuple(publication_renames),
                tuple(publication_encodings),
                page,
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
