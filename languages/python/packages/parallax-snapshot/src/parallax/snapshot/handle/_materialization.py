"""The shared read-page and root-publication seam for every Snapshot lane."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, cast, overload

from parallax.core import deep_fetch
from parallax.core.db_port import DatabaseConnection, PipelineStatement, Row
from parallax.core.entity._layout import CatalogedModel
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
from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_template,
)
from parallax.core.temporal_read import Pin, scans_validated_axis, validated_query_pin
from parallax.core.unit_work import Concurrency, EntityStateRow
from parallax.snapshot._read_result import FindResult
from parallax.snapshot.handle._paging import At, PagePlan, PageRequest, TieFound, page_decision
from parallax.snapshot.handle._retention import ObservationLedger, ObservedRows, ReadSources
from parallax.snapshot.materialize import (
    Page,
    PageBuilder,
    RootView,
    UnwindTree,
    hydrates,
    page_rows,
)
from parallax.snapshot.materialize._page import ABSENT, exact_stored_equal
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

if TYPE_CHECKING:
    from parallax.core.base import NeutralType

__all__ = [
    "INERT",
    "CompiledRead",
    "CompiledTemplate",
    "DeliveryPage",
    "DeliveryPlan",
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
class _RootTemplate:
    plan: deep_fetch.ObjectQueryPlan
    compiled: CompiledRead
    positions: tuple[tuple[int, int], ...]

    def render(
        self, coordinate: ContinuationCoordinate, size: int
    ) -> tuple[deep_fetch.ObjectQueryPlan, CompiledRead]:
        binds = list(self.compiled.statement.binds)
        for bind_index, carrier in self.positions:
            binds[bind_index] = coordinate.carriers[carrier]
        binds[-1] = size
        statement = replace(self.compiled.statement, binds=tuple(binds))
        return self.plan, replace(self.compiled, statement=statement)


@dataclass(frozen=True, slots=True)
class DeliveryPlan:
    """Pure paging policy plus delivery-owned compiled statement templates."""

    paging: PagePlan
    root_after: dict[tuple[bool, ...], _RootTemplate] = field(
        default_factory=lambda: {}, compare=False, repr=False
    )
    children: dict[int, CompiledTemplate] = field(
        default_factory=lambda: {}, compare=False, repr=False
    )


@dataclass(frozen=True, slots=True)
class DeliveryPage:
    """One streamed Page and the minimal state needed to continue its delivery."""

    page: Page
    includes: UnwindTree
    sources: ReadSources
    delivered: int
    resume_from: ContinuationCoordinate | None
    exhausted: bool
    tie: TieFound | None


@dataclass(slots=True)
class _RootRead:
    plan: deep_fetch.ObjectQueryPlan
    prepared: PreparedRead
    rows: tuple[Row, ...]
    coordinates: tuple[ContinuationCoordinate | None, ...]
    temporal: tuple[ValidatedTemporalSelection, ...]
    observer: MaterializationObserver = INERT

    def take_rows(self) -> tuple[Row, ...]:
        rows = self.rows
        self.rows = ()
        return rows


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

        return self._read_delivery_page(request)

    def _read_root(
        self,
        query: ValidatedObjectQuery,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        preference: Concurrency | None = None,
        calls: DatabaseCallScope,
        plan: deep_fetch.ObjectQueryPlan | None = None,
        compiled: CompiledRead | None = None,
    ) -> _RootRead:
        """Plan and execute the root statement for one Page."""
        from parallax.snapshot.handle._read import entity_read_lock, execute_read

        meta = model.meta
        planned = (
            deep_fetch.plan(
                query,
                meta,
                projection=deep_fetch.ReadProjectionRequest("all", True),
            )
            if plan is None
            else plan
        )
        if compiled is None:
            compiled = compile_read(
                planned.root,
                meta,
                port.dialect,
                result_form="instance",
                lock=entity_read_lock(meta, query.root.identity, preference),
            )
        prepared = bind(model, compiled)
        self.observer.prepared(len(planned.levels) + 1)
        self.observer.statement_rendered(ROOT_LEVEL)
        driver_rows = execute_read(port, compiled, calls)
        self.observer.statement_executed(ROOT_LEVEL, len(driver_rows))
        return _RootRead(
            plan=planned,
            prepared=prepared,
            rows=tuple(driver_rows),
            coordinates=tuple(compiled.row_header(row)[3] for row in driver_rows),
            temporal=query.temporal,
            observer=self.observer,
        )

    @staticmethod
    def _coordinates(root_read: _RootRead) -> tuple[ContinuationCoordinate, ...]:
        coordinates = root_read.coordinates
        if any(coordinate is None for coordinate in coordinates):
            raise SqlGenError("a paging read returned a root carrying no evaluated coordinate")
        return cast("tuple[ContinuationCoordinate, ...]", coordinates)

    @staticmethod
    def _compiled_root(
        delivery: DeliveryPlan,
        query: ValidatedObjectQuery,
        coordinate: ContinuationCoordinate | None,
        request: PageRequest,
        model: CatalogedModel,
        port: DatabaseConnection,
        preference: Concurrency | None,
    ) -> tuple[deep_fetch.ObjectQueryPlan, CompiledRead]:
        from parallax.snapshot.handle._read import entity_read_lock

        page_plan = delivery.paging
        meta = model.meta
        if coordinate is None:
            planned = deep_fetch.plan(
                query,
                meta,
                projection=deep_fetch.ReadProjectionRequest("all", True),
            )
            return planned, compile_read(
                planned.root,
                meta,
                port.dialect,
                result_form="instance",
                lock=entity_read_lock(meta, query.root.identity, preference),
            )
        pattern = tuple(carrier is None for carrier in coordinate.carriers)
        template = delivery.root_after.get(pattern)
        if template is None:
            markers = tuple(None if missing else object() for missing in pattern)
            template_query = page_plan.plan.after(
                ContinuationCoordinate(markers), limit=request.size
            )
            planned = deep_fetch.plan(
                template_query,
                meta,
                projection=deep_fetch.ReadProjectionRequest("all", True),
            )
            compiled = compile_read(
                planned.root,
                meta,
                port.dialect,
                result_form="instance",
                lock=entity_read_lock(meta, template_query.root.identity, preference),
            )
            positions = tuple(
                (bind_index, carrier_index)
                for bind_index, bind_value in enumerate(compiled.statement.binds)
                for carrier_index, marker in enumerate(markers)
                if marker is not None and bind_value is marker
            )
            expected = {index for index, marker in enumerate(markers) if marker is not None}
            if {carrier for _bind, carrier in positions} != expected:
                raise SqlGenError("compiled continuation lost a non-null coordinate bind")
            template = _RootTemplate(planned, compiled, positions)
            delivery.root_after[pattern] = template
        return template.render(coordinate, request.size)

    def _build_page(
        self,
        root_read: _RootRead,
        model: CatalogedModel,
        port: DatabaseConnection,
        *,
        preference: Concurrency | None = None,
        ledger: ObservationLedger | None = None,
        calls: DatabaseCallScope,
        templates: dict[int, CompiledTemplate] | None = None,
    ) -> FindResult:
        """Convert roots and execute every reachable child level into one Page."""
        from parallax.snapshot.handle import _read

        meta = model.meta
        planned = root_read.plan
        builder = PageBuilder(ViewSchema(_read.slot_table(planned)), root_read.observer)
        observations = ObservedRows()
        correlations = _read.correlation_table(planned, meta)

        root_rows = root_read.take_rows()
        root_refs = _read.convert_rows(
            builder,
            ROOT_LEVEL,
            root_read.prepared,
            root_rows,
            observations,
            correlations[ROOT_LEVEL],
        )
        del root_rows

        level_refs: list[tuple[int, ...]] = [()] * len(planned.levels)
        completed: set[int] = set()
        while len(completed) < len(planned.levels):
            ready = [
                index
                for index, level in enumerate(planned.levels)
                if index not in completed
                and (
                    isinstance(level.parent, deep_fetch.RootRef) or level.parent.index in completed
                )
            ]
            pending: list[tuple[int, deep_fetch.FetchLevel, tuple[int, ...], CompiledRead]] = []
            for index in ready:
                level = planned.levels[index]
                parents = _read.guarded_parents(
                    builder,
                    level,
                    _read.parent_refs(level.parent, root_refs, level_refs),
                )
                if level.is_back_reference:
                    _read.attach_back_reference(builder, meta, level, parents)
                    completed.add(index)
                    continue
                keys = _read.gather_keys(
                    builder,
                    parents,
                    _read.correlation_member(meta, level.owner.identity),
                )
                if not keys:
                    _read.attach_empty(builder, level, parents)
                    completed.add(index)
                    continue
                child_query = level.query_template()
                template = None if templates is None else templates.get(index)
                if template is None:
                    template = compile_template(
                        child_query,
                        meta,
                        port.dialect,
                        result_form="instance",
                        lock=_read.entity_read_lock(meta, child_query.target, preference),
                    )
                    if templates is not None:
                        templates[index] = template
                root_read.observer.statement_rendered(index + 1)
                pending.append((index, level, parents, template.render(keys)))

            if len(pending) == 1:
                for index, level, parents, compiled in pending:
                    child_refs = _read.convert_level(
                        builder,
                        index + 1,
                        model,
                        port,
                        compiled,
                        calls,
                        observations,
                        root_read.observer,
                        correlations[index + 1],
                    )
                    _read.attach_children(builder, meta, level, parents, child_refs)
                    level_refs[index] = child_refs
                    completed.add(index)
            elif pending:
                with ExitStack() as stack:
                    call_contexts: list[DatabaseCallActivity] = []
                    for _index, _level, _parents, compiled in pending:
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
                            for _index, _level, _parents, compiled in pending
                        )
                    )
                    for call, rows in zip(call_contexts, batches, strict=True):
                        call.read_completed(rows)
                for (index, level, parents, compiled), rows in zip(pending, batches, strict=True):
                    root_read.observer.statement_executed(index + 1, len(rows))
                    child_refs = _read.convert_level_rows(
                        builder,
                        index + 1,
                        model,
                        compiled,
                        rows,
                        observations,
                        correlations[index + 1],
                    )
                    _read.attach_children(builder, meta, level, parents, child_refs)
                    level_refs[index] = child_refs
                    completed.add(index)

        pin = validated_query_pin(root_read.temporal)
        page = builder.finish(root_refs, pin)
        return FindResult(
            page=page,
            includes=_read.include_tree(planned.levels),
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
        from parallax.snapshot.handle._retention import deferred_evidence

        rows = page_rows(page)
        state_rows: dict[object, EntityStateRow] = {}

        def admitted(node: int) -> EntityStateRow | None:
            key = rows.keys[node]
            states = () if key is None else rows.judged_states.get(key, ())
            state = next(
                (
                    value
                    for witness, value in states
                    if exact_stored_equal(rows.witnesses[node], rows.witnesses[witness])
                ),
                None,
            )
            if key is None or state is None or not hydrates(state.findings):
                return None
            held = state_rows.get(key)
            if held is None:
                held = EntityStateRow.over_state(rows.layouts[node], state, absent=ABSENT)
                state_rows[key] = held
            return held

        return deferred_evidence(
            meta,
            observations,
            admitted,
            lambda node: rows.layouts[node].concrete,
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
        planned, compiled = self._compiled_root(
            delivery,
            query,
            request.at.coordinate,
            page_request,
            request.model,
            request.port,
            request.preference,
        )
        root_read = self._read_root(
            query,
            request.model,
            request.port,
            preference=request.preference,
            calls=request.calls,
            plan=planned,
            compiled=compiled,
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
            templates=delivery.children,
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
