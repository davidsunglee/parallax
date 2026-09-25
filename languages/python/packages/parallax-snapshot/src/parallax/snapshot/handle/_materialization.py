from __future__ import annotations

from array import array
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, cast, overload

from parallax.core import deep_fetch, opt_lock
from parallax.core.db_port import DatabaseConnection, PipelineStatement, Row
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.execution_lifecycle._activity import (
    DatabaseCallActivity,
    DatabaseCallScope,
)
from parallax.core.metamodel import Metamodel
from parallax.core.object_query._validated import (
    ContinuationCoordinate,
    ValidatedObjectQuery,
    ValidatedTemporalSelection,
)
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin, scans_validated_axis, validated_query_pin
from parallax.core.unit_work import Concurrency
from parallax.snapshot._read_result import FindResult
from parallax.snapshot.handle._paging import At, PagePlan, TieFound, page_decision
from parallax.snapshot.handle._read_plan import ReadPlan, ReadPlanner
from parallax.snapshot.handle._retention import ObservationLedger, ObservedRows, ReadSources
from parallax.snapshot.materialize import (
    Page,
    PageBuilder,
    RootView,
    hydrates,
    page_rows,
    root_last_uses,
)
from parallax.snapshot.materialize._page import judged_state, release_page_rows
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

if TYPE_CHECKING:
    from parallax.core.base import NeutralType

__all__ = [
    "INERT",
    "DeliveryPage",
    "DeliveryPlan",
    "EagerPageRead",
    "FlatPageRead",
    "MaterializationObserver",
    "Materializer",
    "RowPublication",
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
    planner: ReadPlanner
    edition: str = ""


@dataclass(frozen=True, slots=True)
class FlatPageRead:
    """Inputs for one statement whose rows form a root-only Page."""

    model: CatalogedModel
    compiled: CompiledRead
    read: Callable[[], Sequence[Row]]
    pin: Pin
    prepared: PreparedRead | None = None


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


@dataclass(slots=True)
class DeliveryPlan:
    """Pure paging policy for one streamed delivery."""

    paging: PagePlan


@dataclass(frozen=True, slots=True)
class DeliveryPage:
    """One streamed Page and the minimal state needed to continue its delivery."""

    page: Page
    includes: deep_fetch.IncludeTree
    sources: ReadSources
    delivered: int
    resume_from: ContinuationCoordinate | None
    exhausted: bool
    tie: TieFound | None


@dataclass(slots=True)
class _RootRead:
    plan: ReadPlan
    prepared: PreparedRead
    rows: list[Row]
    coordinates: tuple[ContinuationCoordinate | None, ...]
    temporal: tuple[ValidatedTemporalSelection, ...]
    observer: MaterializationObserver = INERT

    def take_rows(self) -> list[Row]:
        rows = self.rows
        self.rows = []
        return rows


def _drain_rows(rows: list[Row]) -> Iterator[Row]:
    """Yield transferred driver rows while releasing each consumed tuple."""
    for index in range(len(rows)):
        row = rows[index]
        rows[index] = cast("Row", ())
        yield row


@dataclass(frozen=True, slots=True)
class StreamPageRead:
    """Inputs for one bounded Page in an already prepared delivery."""

    plan: DeliveryPlan
    at: At
    model: CatalogedModel
    port: DatabaseConnection
    preference: Concurrency | None
    ledger: ObservationLedger | None
    calls: DatabaseCallScope
    planner: ReadPlanner
    edition: str = ""


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
            roots = self._read_root(
                request.query,
                request.model,
                request.port,
                preference=request.preference,
                calls=request.calls,
                edition=request.edition,
                planner=request.planner,
            )
            return self._build_page(
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
            prepared = request.prepared or bind(request.model, request.compiled)
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

        return self._read_delivery_page(request)

    def _read_root(
        self,
        query: ValidatedObjectQuery,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        preference: Concurrency | None = None,
        calls: DatabaseCallScope,
        edition: str = "",
        planner: ReadPlanner,
        plan: ReadPlan | None = None,
    ) -> _RootRead:
        """Plan and execute the root statement for one Page."""
        from parallax.snapshot.handle._read import execute_read

        if plan is None:
            plan = planner.plan(
                edition=edition,
                model=model,
                dialect=port.dialect,
                query=query,
                result_form="instance",
                preference=preference,
            )
        compiled_read, prepared_rows = plan.root_read()
        self.observer.prepared(plan.fetch_count + 1)
        self.observer.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(port, compiled_read, calls)
        self.observer.statement_executed(ROOT_LEVEL, len(driver_rows))
        return _RootRead(
            plan=plan,
            prepared=prepared_rows,
            rows=list(driver_rows),
            coordinates=compiled_read.row_coordinates(driver_rows),
            temporal=query.temporal,
            observer=self.observer,
        )

    @staticmethod
    def _coordinates(root_read: _RootRead) -> tuple[ContinuationCoordinate, ...]:
        coordinates = root_read.coordinates
        if any(coordinate is None for coordinate in coordinates):
            raise SqlGenError("a paging read returned a root carrying no evaluated coordinate")
        return cast("tuple[ContinuationCoordinate, ...]", coordinates)

    def _build_page(
        self,
        root_read: _RootRead,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        preference: Concurrency | None = None,
        ledger: ObservationLedger | None = None,
        calls: DatabaseCallScope,
    ) -> FindResult:
        """Convert roots and execute every reachable fetch step into one Page."""
        from parallax.snapshot.handle import _read

        meta = model.meta
        plan = root_read.plan
        includes = plan.include_tree()
        builder = plan.page_builder(None if root_read.observer is INERT else root_read.observer)
        observations = ObservedRows()
        root_rows = root_read.take_rows()
        root_refs = _read.convert_rows(
            builder,
            ROOT_LEVEL,
            root_read.prepared,
            _drain_rows(root_rows),
            observations,
            plan.correlation_members(ROOT_LEVEL),
        )
        del root_rows

        fetch_refs: list[tuple[int, ...]] = [()] * plan.fetch_count
        completed: set[int] = set()
        while len(completed) < plan.fetch_count:
            ready = plan.ready_fetches(completed)
            pending: list[
                tuple[
                    int,
                    deep_fetch.QueryFetchStep,
                    tuple[int, ...],
                    CompiledRead,
                    PreparedRead,
                ]
            ] = []
            for index in ready:
                step = plan.fetch_step(index)
                parents = _read.guarded_parents(
                    builder,
                    includes,
                    step,
                    _read.parent_refs(step.parent, root_refs, fetch_refs),
                )
                if isinstance(step, deep_fetch.BackReferenceFetchStep):
                    _read.attach_back_reference(builder, meta, includes, step, parents)
                    completed.add(index)
                    continue
                keys = _read.gather_keys(
                    builder,
                    parents,
                    _read.correlation_member(meta, step.owner.identity),
                )
                if not keys:
                    _read.attach_empty(builder, includes, step, parents)
                    completed.add(index)
                    continue
                compiled, prepared = plan.fetch_read(index, keys)
                root_read.observer.statement_rendered(index + 1)
                pending.append((index, step, parents, compiled, prepared))

            if len(pending) == 1:
                for index, step, parents, compiled, prepared in pending:
                    rows = _read.execute_read(port, compiled, calls)
                    root_read.observer.statement_executed(index + 1, len(rows))
                    child_refs = _read.convert_rows(
                        builder,
                        index + 1,
                        prepared,
                        rows,
                        observations,
                        plan.correlation_members(index + 1),
                    )
                    _read.attach_children(builder, meta, includes, step, parents, child_refs)
                    fetch_refs[index] = child_refs
                    completed.add(index)
            elif pending:
                with ExitStack() as stack:
                    call_contexts: list[DatabaseCallActivity] = []
                    for _index, _step, _parents, compiled, _prepared in pending:
                        context = calls.database_call(compiled.statement, "read", compiled.target)
                        call_contexts.append(context.__enter__())
                        stack.push(context.__exit__)
                    batches = port.execute_pipeline(
                        tuple(
                            PipelineStatement(
                                port.dialect.to_driver_sql(compiled.statement.sql),
                                compiled.statement.binds,
                                compiled.document_reads,
                            )
                            for _index, _step, _parents, compiled, _prepared in pending
                        )
                    )
                    for call, rows in zip(call_contexts, batches, strict=True):
                        call.read_completed(rows)
                for (index, step, parents, _compiled, prepared), rows in zip(
                    pending, batches, strict=True
                ):
                    root_read.observer.statement_executed(index + 1, len(rows))
                    child_refs = _read.convert_rows(
                        builder,
                        index + 1,
                        prepared,
                        rows,
                        observations,
                        plan.correlation_members(index + 1),
                    )
                    _read.attach_children(builder, meta, includes, step, parents, child_refs)
                    fetch_refs[index] = child_refs
                    completed.add(index)

        pin = validated_query_pin(root_read.temporal)
        page = builder.finish(root_refs, pin)
        return FindResult(
            page=page,
            includes=plan.include_tree(),
            sources=self._retained(
                meta,
                root_read.temporal,
                observations,
                page=page,
                ledger=ledger,
                pin=pin,
            ),
        )

    @staticmethod
    def _retained(
        meta: Metamodel,
        temporal: tuple[ValidatedTemporalSelection, ...],
        observations: ObservedRows,
        *,
        page: Page,
        ledger: ObservationLedger | None,
        pin: Pin,
    ) -> ReadSources:
        if scans_validated_axis(temporal):
            return MappingProxyType({})
        from parallax.snapshot.handle._retention import deferred_read_sources

        rows = page_rows(page)

        def admitted(node: int) -> tuple[EntityLayout, tuple[object, ...]] | None:
            state = None if rows.keys[node] is None else judged_state(rows, node)
            # Invalid roots suppress their complete origin map before this callback.
            if state is None or not hydrates(state.findings):  # pragma: no cover
                return None
            return rows.layouts[node], state.member_row

        def primary_key(node: int) -> object | None:
            key = rows.keys[node]
            return None if key is None else key.primary_key

        return deferred_read_sources(
            meta,
            observations,
            admitted,
            lambda node: rows.layouts[node].concrete,
            primary_key,
            ledger=ledger,
            pin=pin,
        )

    def _read_delivery_page(self, request: StreamPageRead) -> DeliveryPage:
        """Execute one streamed Page and retain only its continuation boundary."""
        delivery = request.plan
        page_plan = delivery.paging
        page_request = page_plan.page_request(request.at.emitted)
        query = (
            page_plan.plan.first(limit=page_request.size)
            if request.at.coordinate is None
            else page_plan.plan.after(request.at.coordinate, limit=page_request.size)
        )
        root_read = self._read_root(
            query,
            request.model,
            request.port,
            preference=request.preference,
            calls=request.calls,
            edition=request.edition,
            planner=request.planner,
        )
        coordinates = self._coordinates(root_read)
        terms = tuple(term.member.identity for term in query.order_by)
        verdict = page_decision(page_request, terms, coordinates)
        kept = replace(
            root_read,
            rows=root_read.rows[: verdict.keep],
            coordinates=root_read.coordinates[: verdict.keep],
        )
        discarded_rows = root_read.take_rows()
        del discarded_rows, root_read
        result = self._build_page(
            kept,
            request.model,
            request.port,
            preference=request.preference,
            ledger=request.ledger,
            calls=request.calls,
        )
        return DeliveryPage(
            page=result.page,
            includes=result.includes,
            sources=result.sources,
            delivered=verdict.keep,
            resume_from=coordinates[verdict.keep - 1] if verdict.keep else None,
            exhausted=verdict.exhausted,
            tie=verdict.tie,
        )

    def roots[T](
        self,
        page: Page,
        publish: Callable[[RootView, int], Iterator[T]],
        *,
        atomic: bool = False,
        model: Metamodel | None = None,
        ordinal_offset: int = 0,
        pins: Sequence[Pin | None] | None = None,
        prepare: Callable[[RootView], None] | None = None,
    ) -> Iterator[T]:
        """Judge and publish one Page root at a time through one shared seam.

        An ``atomic`` publication defers judging every root's state when each
        root's family carries write evidence, which ``model``'s Optimistic Lock
        Facet answers; it is required exactly then.
        """
        if pins is not None and len(pins) != page.root_count:
            raise ValueError("root pin count must match the Page root count")
        if atomic:
            if model is None:
                raise ValueError("an atomic publication decides state deferral against its model")
            keys = opt_lock.view(model)
            rows = page_rows(page)
            deferred_states = all(
                isinstance(
                    keys.key(rows.layouts[root].concrete),
                    opt_lock.ExplicitVersion | opt_lock.TransactionTimeDerived,
                )
                for root in rows.roots
            )
            last_uses = (
                root_last_uses(page)
                if deferred_states or any(not isinstance(claim, int) for claim in rows.claims)
                else None
            )
            prepared: list[T] = []
            published_counts = array("I")
            for position in range(page.root_count):
                pin = None if pins is None else pins[position]
                root = RootView(page, position, pin=pin, defer_states=deferred_states)
                root.complete()
                if prepare is not None:
                    prepare(root)
                if last_uses is None:
                    root.release_raw_rows()
                else:
                    root.release_finished_page_rows(position, last_uses)
                before = len(prepared)
                prepared.extend(publish(root, position))
                published_counts.append(len(prepared) - before)
            release_page_rows(page)
            prepared_position = 0
            for position, count in enumerate(published_counts):
                for root in prepared[prepared_position : prepared_position + count]:
                    yield root
                prepared_position += count
                self.observer.root_published(ordinal_offset + position)
            return
        for position in range(page.root_count):
            pin = None if pins is None else pins[position]
            root = RootView(page, position, pin=pin)
            root.release_raw_rows()
            yield from publish(root, position)
            self.observer.root_published(ordinal_offset + position)
