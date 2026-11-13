from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

import pytest

from parallax.core._execution._read_query import resolve_read_query
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.internal import read_planning
from parallax.core.internal.base import INFINITY, InternalError, StructuredDocument
from parallax.core.internal.db_port import Bind, DocumentReadOrdinals, Row
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.internal.object_query import deserialize
from parallax.core.internal.object_query._resolved import ResolvedObjectQuery
from parallax.core.internal.read_delivery import _acquired_rows, _page_reader
from parallax.core.internal.read_delivery._page import (
    InvalidDataError,
    Page,
    entity_state,
    page_rows,
)
from parallax.core.internal.read_delivery._page_reader import (
    PageReadContext,
    PageReader,
    PageResult,
)
from parallax.core.internal.read_delivery._paging import PagingParameters
from parallax.core.internal.read_delivery._read_plan import EmptyRead, ReadPlan, ReadPlanCache
from parallax.core.internal.read_delivery._row_converter import ReadRowConverter
from parallax.core.internal.sql_gen._compile import CompiledRead
from parallax.core.internal.sql_gen._context import SQL_GENERATION_FAILED
from parallax.core.internal.temporal_read import Pin, TimeInterval, ranked_axes, temporal_facet_of
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import Read, ReadCall, ScriptedAdapter
from tests._support.errors import raises_code
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target
from tests.unit.core import _shared_coverage_support as shared

_TEMPORAL = CatalogedModel(shared.MODEL, TEST_BINDING)
_DOCUMENT = CatalogedModel(corpus_model("document-layout"), TEST_BINDING)


@dataclass
class _Collector:
    label: str
    observed: list[tuple[int, EntityIdentity, object | None]] = field(
        default_factory=list[tuple[int, EntityIdentity, object | None]]
    )
    sealed: list[Page] = field(default_factory=list[Page])

    def observe_fetched_row(
        self, fetched_row: int, entity: EntityIdentity, document: object | None
    ) -> None:
        self.observed.append((fetched_row, entity, document))

    def origins_for(self, page: Page, /) -> Mapping[int, str]:
        self.sealed.append(page)
        return {index: self.label for index, _, _ in self.observed}


def _query(
    selection: Mapping[str, object], *, entity_name: str = "ShareCols"
) -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize(
            {
                "target": entity_name,
                "predicate": {"true": {}},
                "temporal": {
                    "valid-time": dict(selection),
                    "transaction-time": {"asOf": "latest"},
                },
            }
        ),
        model=shared.MODEL,
    )


def _plan(
    cache: ReadPlanCache,
    query: ResolvedObjectQuery,
    *,
    paging: PagingParameters | None = None,
) -> ReadPlan:
    return cache.plan(
        edition="edition-a",
        model=_TEMPORAL,
        dialect=ScriptedAdapter().dialect,
        query=query,
        preference="optimistic",
        paging=paging,
    )


def _root(plan: ReadPlan) -> tuple[CompiledRead, ReadRowConverter]:
    root = plan.root_read()
    assert not isinstance(root, EmptyRead)
    return root


def test_cached_single_instant_policy_uses_each_executions_pin_and_collector() -> None:
    cache = ReadPlanCache()
    plans = tuple(
        _plan(cache, _query({"asOf": shared.day(day).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}))
        for day in (0, 1)
    )
    collectors = (_Collector("first"), _Collector("second"))
    results: list[PageResult[str]] = []
    for plan, collector in zip(plans, collectors, strict=True):
        with ScriptedAdapter(
            Read(
                [
                    shared.physical_row(
                        shared.ShareCols, shared.rectangle(shared.ShareCols, 1, 0, None, 3)
                    )
                ]
            )
        ) as port:
            results.append(PageReader().read_page(plan, PageReadContext(port, INERT, collector)))

    assert all(plan.kind == "single_instant" for plan in plans)
    assert all(plan.purpose == "publication" and plan.collects_evidence for plan in plans)
    assert all(plan.milestones is None for plan in plans)
    assert [plan.pin.valid_time for plan in plans] == [shared.day(0), shared.day(1)]
    assert [result.page.pin for result in results] == [plan.pin for plan in plans]
    assert [result.origins for result in results] == [{0: "first"}, {0: "second"}]
    assert [collector.sealed for collector in collectors] == [[result.page] for result in results]
    assert _root(plans[0])[1] is _root(plans[1])[1]
    assert page_rows(results[0].page).schema is page_rows(results[1].page).schema
    with ScriptedAdapter(Read()) as port:
        without_context = PageReader().read_page(plans[1], PageReadContext[str](port, INERT))
    assert without_context.origins == {}


def test_an_unpaged_read_does_not_extract_per_row_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(ReadPlanCache(), _query({"asOf": "latest"}))
    rows = [
        shared.physical_row(shared.ShareCols, shared.rectangle(shared.ShareCols, key, 0, None, key))
        for key in (1, 2, 3)
    ]

    def refuse(*_args: object) -> None:
        raise AssertionError("unpaged execution extracted coordinates")

    monkeypatch.setattr(_page_reader, "row_coordinates", refuse)
    with ScriptedAdapter(Read(rows)) as port:
        context: PageReadContext[str] = PageReadContext(port, INERT)
        result = PageReader().read_page(plan, context)

    assert result.continuation is None
    assert result.page.root_count == 3
    recorded = page_rows(result.page)
    assert [entity_state(recorded, root).member_row[0] for root in recorded.roots] == [1, 2, 3]


def test_a_paging_root_without_an_evaluated_coordinate_is_refused() -> None:
    plan = _plan(ReadPlanCache(), _query({"asOf": "latest"}))
    collector = _Collector("must stay unused")
    row = shared.physical_row(shared.ShareCols, shared.rectangle(shared.ShareCols, 1, 0, None, 3))
    with (
        ScriptedAdapter(Read([row])) as port,
        raises_code(
            InternalError,
            SQL_GENERATION_FAILED,
            match="returned a root carrying no evaluated coordinate",
        ),
    ):
        PageReader().read_page(
            plan, PageReadContext(port, INERT, collector), PagingParameters(3, True, 0)
        )

    assert collector.observed == collector.sealed == []


@pytest.mark.parametrize(
    "selection",
    [
        {"history": {}},
        {
            "asOfRange": {
                "start": shared.day(0).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "end": shared.day(2).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            }
        },
    ],
    ids=["history", "range"],
)
def test_milestone_policy_supplies_shape_and_suppresses_a_supplied_collector(
    selection: Mapping[str, object],
) -> None:
    plan = _plan(ReadPlanCache(), _query(selection))
    collector = _Collector("must stay unused")
    row = shared.physical_row(shared.ShareCols, shared.rectangle(shared.ShareCols, 1, 0, None, 3))
    with ScriptedAdapter(Read([row])) as port:
        result = PageReader().read_page(plan, PageReadContext(port, INERT, collector))

    shape = temporal_facet_of(shared.MODEL).shape(shared.ShareCols.identity)
    assert shape is not None
    assert (plan.kind, plan.purpose, plan.collects_evidence) == (
        "milestone_set",
        "publication",
        False,
    )
    assert plan.milestones is shape
    expected_order = (
        AttributeIdentity(shared.ShareCols.identity, "id"),
        *(axis.start_attribute for axis in ranked_axes(shape)),
    )
    assert tuple(term.member.identity for term in plan.query.order_by) == expected_order
    streamed = _plan(
        ReadPlanCache(), _query(selection), paging=PagingParameters.for_page(2, None, 0)
    )
    assert streamed.continuation is not None
    assert tuple(term.member.identity for term in streamed.query.order_by) == expected_order
    assert (
        tuple(term.member.identity for term in streamed.continuation.first(limit=2).order_by)
        == expected_order
    )
    assert plan.pin == result.page.pin == Pin()
    assert collector.observed == collector.sealed == []
    assert result.origins == {} and result.documents is None and result.continuation is None


def test_warm_milestone_plans_reuse_ordering_with_current_ranges_and_independent_pages() -> None:
    def query(start: int, end: int) -> ResolvedObjectQuery:
        return _query(
            {
                "asOfRange": {
                    "start": shared.day(start).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "end": shared.day(end).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                }
            }
        )

    cache = ReadPlanCache()
    seed = _plan(cache, query(0, 2))
    current = query(1, 3)
    warm = _plan(cache, current)
    cold = _plan(ReadPlanCache(), current)
    disabled = _plan(ReadPlanCache(0), current)
    assert warm.query.order_by is seed.query.order_by
    assert isinstance(warm.query, ResolvedObjectQuery)
    assert warm.query.temporal is current.temporal
    assert _root(warm)[1] is _root(seed)[1]
    assert _root(seed)[0].statement.binds == (shared.day(2), shared.day(0), INFINITY)

    results: list[PageResult[str]] = []
    for plan in (warm, cold, disabled):
        row = shared.physical_row(
            shared.ShareCols, shared.rectangle(shared.ShareCols, 1, 1, None, 3)
        )
        with ScriptedAdapter(Read([row])) as port:
            context: PageReadContext[str] = PageReadContext(port, INERT)
            result = PageReader().read_page(plan, context)
            assert port.calls == [
                ReadCall(
                    "select t0.id, t0.amount, t0.label, t0.from_z, t0.thru_z, t0.in_z, t0.out_z "
                    "from px.share_cols t0 where t0.from_z < ? and t0.thru_z > ? and t0.out_z = ? "
                    "order by t0.id asc, t0.from_z asc, t0.in_z asc",
                    (shared.day(3), shared.day(1), INFINITY),
                    read_only=True,
                )
            ]
        assert result.page.root_count == 1
        rows = page_rows(result.page)
        state = entity_state(rows, rows.roots[0])
        assert state.member_row[:3] == (1, 3, "k1")
        assert state.findings == ()
        results.append(result)
    assert len({id(page_rows(result.page).schema) for result in results}) == 3


def test_milestone_cache_keeps_authored_order_distinct_from_appended_order() -> None:
    cache = ReadPlanCache()
    implicit = _plan(cache, _query({"history": {}}))
    authored = replace(_query({"history": {}}), order_by=implicit.query.order_by)
    explicit = _plan(cache, authored)
    repeated = _plan(cache, authored)

    assert explicit.query.order_by == implicit.query.order_by
    assert _root(explicit)[0].statement == _root(implicit)[0].statement
    assert _root(explicit)[1] is not _root(implicit)[1]
    assert _root(repeated)[1] is _root(explicit)[1]


def _target_plan(cache: ReadPlanCache, key: int, *, retain: bool) -> ReadPlan:
    entity = target(_DOCUMENT.meta, "Traveler")
    query = read_planning.plan_target_read(
        entity,
        model=_DOCUMENT.meta,
        key="id",
        key_value=key,
        retain_predecessor=retain,
    )
    return cache.plan_acquisition(
        edition="edition-a",
        model=_DOCUMENT,
        dialect=ScriptedAdapter().dialect,
        query=query,
        preference="optimistic",
    )


def _traveler_document(name: str) -> StructuredDocument:
    return StructuredDocument(
        {
            "displayName": name,
            "score": None,
            "joinedOn": None,
            "note": None,
            "address": {"city": 42},
            "tags": [],
        }
    )


def test_cached_write_support_keeps_page_schemas_documents_and_judgement_per_execution() -> None:
    cache = ReadPlanCache()
    plans = tuple(_target_plan(cache, key, retain=True) for key in (1, 2))
    documents = tuple(_traveler_document(name) for name in ("Ada", "Bo"))

    def execute(index: int) -> PageResult[str]:
        collector = _Collector("must stay unused")
        with ScriptedAdapter(Read([{"id": index + 1, "payload": documents[index]}])) as port:
            result = PageReader().read_page(plans[index], PageReadContext(port, INERT, collector))
        assert collector.observed == collector.sealed == []
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, (0, 1)))

    assert all(plan.purpose == "write_support" and not plan.collects_evidence for plan in plans)
    assert _root(plans[0])[1] is _root(plans[1])[1]
    rows = tuple(page_rows(result.page) for result in results)
    assert rows[0].schema is not rows[1].schema
    assert all(row.decoders.pending(0) for row in rows)
    for index, result in enumerate(results):
        assert result.documents is not None and len(result.documents) == 1
        assert result.documents[0] is documents[index].document
        admitted = list(_acquired_rows.admitted_member_rows(result.page))
        assert admitted[0][0] == index + 1
        layout = _DOCUMENT.layouts.entity(target(_DOCUMENT.meta, "Traveler").identity)
        with pytest.raises(InvalidDataError, match=r"address\.city"):
            list(_acquired_rows.completed_member_rows(layout, admitted))


def test_shared_document_acquisition_keeps_each_roots_document_in_fetched_order() -> None:
    entity = target(_DOCUMENT.meta, "Traveler")
    query = resolve_read_query(
        deserialize({"target": "Traveler", "predicate": {"true": {}}}), model=_DOCUMENT.meta
    )
    plan = ReadPlanCache().plan_acquisition(
        edition="edition-a",
        model=_DOCUMENT,
        dialect=ScriptedAdapter().dialect,
        query=read_planning.plan_root(
            query, _DOCUMENT.meta, projection=read_planning.ReadProjectionRequest("all", True)
        ),
        preference="optimistic",
    )
    first, second, repeated = (_traveler_document(name) for name in ("Bo", "Ada", "Bo"))
    collector = _Collector("must stay unused")
    with ScriptedAdapter(
        Read(
            [
                {"id": 2, "payload": first},
                {"id": 1, "payload": second},
                {"id": 2, "payload": repeated},
                {"id": 3, "payload": None},
            ]
        )
    ) as port:
        result = PageReader().read_page(plan, PageReadContext(port, INERT, collector))

    rows = page_rows(result.page)
    assert result.page.root_count == len(rows.roots) == 4
    assert all(rows.decoders.pending(root) for root in rows.roots)
    assert result.documents is not None and len(result.documents) == 4
    assert all(
        actual is expected
        for actual, expected in zip(
            result.documents,
            (first.document, second.document, repeated.document, None),
            strict=True,
        )
    )
    assert collector.observed == collector.sealed == [] and result.origins == {}
    retained = list(_acquired_rows.admitted_member_rows(result.page))
    assert [(row[0], row[1]) for row in retained] == [(2, "Bo"), (1, "Ada"), (2, "Bo"), (3, None)]
    layout = _DOCUMENT.layouts.entity(entity.identity)
    with pytest.raises(InvalidDataError, match=r"address\.city"):
        list(_acquired_rows.completed_member_rows(layout, retained))


@pytest.mark.parametrize("retain", [False, True], ids=["point", "retained-point"])
def test_target_plans_keep_their_lock_and_projection_when_keys_and_instants_change(
    retain: bool,
) -> None:
    cache = ReadPlanCache()
    entity = target(shared.MODEL, "ShareDoc")
    plans: list[ReadPlan] = []
    for key, day in ((1, 0), (2, 1)):
        query = read_planning.plan_target_read(
            entity,
            model=shared.MODEL,
            key="id",
            key_value=key,
            valid_from=shared.day(day),
            retain_predecessor=retain,
        )
        plans.append(
            cache.plan_acquisition(
                edition="edition-a",
                model=_TEMPORAL,
                dialect=ScriptedAdapter().dialect,
                query=query,
                preference="optimistic",
            )
        )
    compiled = [_root(plan)[0] for plan in plans]
    assert all(plan.kind == "single_instant" and plan.purpose == "write_support" for plan in plans)
    assert all("for share" in read.statement.sql for read in compiled)
    assert all(read.projection.observe_structured_document is retain for read in compiled)
    assert compiled[0].statement.sql == compiled[1].statement.sql
    assert compiled[0].statement.binds != compiled[1].statement.binds
    for read, key, day in zip(compiled, (1, 2), (0, 1), strict=True):
        assert key in read.statement.binds and shared.day(day) in read.statement.binds
    assert _root(plans[0])[1] is _root(plans[1])[1]


@pytest.mark.parametrize("shared_lock", [False, True], ids=["optimistic", "locking"])
def test_coverage_plans_render_each_keys_windows_and_keep_the_requested_lock(
    shared_lock: bool,
) -> None:
    cache = ReadPlanCache()
    entity = target(shared.MODEL, "ShareDoc")
    plans: list[ReadPlan] = []
    for key, start, end in ((1, 0, 2), (2, 3, 5)):
        query = read_planning.plan_coverage_read(
            entity,
            model=shared.MODEL,
            key="id",
            terms=((key, (TimeInterval(shared.day(start), shared.day(end)),)),),
        )
        plans.append(
            cache.plan_acquisition(
                edition="edition-a",
                model=_TEMPORAL,
                dialect=ScriptedAdapter().dialect,
                query=query,
                preference="optimistic",
                coverage_shared_lock=shared_lock,
            )
        )
    compiled = [_root(plan)[0] for plan in plans]
    assert all(plan.kind == "milestone_set" and plan.purpose == "write_support" for plan in plans)
    assert all(("for share" in read.statement.sql) is shared_lock for read in compiled)
    assert all(read.result_contract.shared_document is not None for read in compiled)
    assert compiled[0].statement.sql == compiled[1].statement.sql
    for read, key, start, end in zip(compiled, (1, 2), (0, 3), (2, 5), strict=True):
        assert key in read.statement.binds
        assert shared.day(start) in read.statement.binds and shared.day(end) in read.statement.binds
        assert INFINITY in read.statement.binds
    assert _root(plans[0])[1] is _root(plans[1])[1]


@pytest.mark.parametrize("keys, kept", [((1, 2, 3), 2), ((1, 2, 2), 1)], ids=["lookahead", "tie"])
def test_page_continuation_collects_only_the_retained_root_prefix(
    keys: tuple[int, ...],
    kept: int,
) -> None:
    paging = PagingParameters(size=3, lookahead=True, emitted=0)
    plan = ReadPlanCache().plan(
        edition="edition-a",
        model=_TEMPORAL,
        dialect=ScriptedAdapter().dialect,
        query=_query(
            {"asOf": shared.day(0).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}, entity_name="ShareDoc"
        ),
        preference="optimistic",
        paging=paging,
    )
    collector = _Collector("retained")
    rows = [
        shared.physical_row(shared.ShareDoc, shared.rectangle(shared.ShareDoc, key, 0, None, index))
        for index, key in enumerate(keys)
    ]
    for row in rows[kept:]:
        row["payload"] = StructuredDocument({"amount": "invalid", "label": "invalid"})
    with ScriptedAdapter(Read(rows)) as port:
        result = PageReader().read_page(plan, PageReadContext(port, INERT, collector), paging)

    continuation = result.continuation
    assert continuation is not None
    assert continuation.delivered == kept
    assert continuation.exhausted is (keys[-1] == keys[-2])
    assert (continuation.tie is not None) is (keys[-1] == keys[-2])
    assert len(page_rows(result.page).roots) == kept
    assert [index for index, _, _ in collector.observed] == list(range(kept))
    assert result.origins == {index: "retained" for index in range(kept)}
    assert continuation.resume_from is not None
    assert continuation.resume_from.carriers == (kept,)
    recorded = page_rows(result.page)
    assert all(entity_state(recorded, root).findings == () for root in recorded.roots)


@pytest.mark.parametrize("keys", [(1, 2, 3), (1, 2, 2)], ids=["lookahead", "tie"])
def test_a_malformed_discarded_root_is_refused_before_any_root_is_converted(
    keys: tuple[int, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    paging = PagingParameters(size=3, lookahead=True, emitted=0)
    plan = _plan(ReadPlanCache(), _query({"asOf": "latest"}), paging=paging)
    collector = _Collector("must stay unused")
    rows = [
        shared.physical_row(shared.ShareCols, shared.rectangle(shared.ShareCols, key, 0, None, key))
        for key in keys
    ]
    with ScriptedAdapter(Read(rows)) as port:
        execute = port.execute

        def malformed(
            sql: str,
            binds: Sequence[Bind],
            document_reads: Sequence[DocumentReadOrdinals] = (),
            *,
            read_only: bool = False,
        ) -> list[Row]:
            answer = execute(sql, binds, document_reads, read_only=read_only)
            answer[-1] = answer[-1][:-1]
            return answer

        monkeypatch.setattr(port, "execute", malformed)
        with pytest.raises(ValueError, match="does not match row arity"):
            PageReader().read_page(plan, PageReadContext(port, INERT, collector), paging)

    assert collector.observed == collector.sealed == []


def test_transaction_time_coverage_is_single_instant_write_support() -> None:
    model = CatalogedModel(corpus_model("balance"), TEST_BINDING)
    entity = target(model.meta, "Balance")
    query = read_planning.plan_coverage_read(entity, model=model.meta, key="id", terms=((1, ()),))
    plan = ReadPlanCache().plan_acquisition(
        edition="edition-a",
        model=model,
        dialect=ScriptedAdapter().dialect,
        query=query,
        preference="optimistic",
        coverage_shared_lock=False,
    )
    collector = _Collector("must stay unused")
    with ScriptedAdapter(Read()) as port:
        result = PageReader().read_page(plan, PageReadContext(port, INERT, collector))

    assert (plan.kind, plan.purpose, plan.collects_evidence) == (
        "single_instant",
        "write_support",
        False,
    )
    assert plan.milestones is None
    assert collector.observed == collector.sealed == []
    assert result.origins == {} and not page_rows(result.page).roots
