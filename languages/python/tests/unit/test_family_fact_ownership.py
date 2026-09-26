"""Family facts reach prepared write and read flows from the facets that formed them.

Formation settles each family's version source and Temporal Shape once. A flow
that later asks a declared Attribute whether it is the version, or asks an
Entity's declarations for its As-Of Axes, re-derives that answer, and a correct
answer hides the duplicate work. These tests record every such declaration read
while production seams admit, plan, and lower writes, plan and run queries,
materialize Pages, and retain their evidence, so a re-derivation fails even when
it agrees with the owner. Object Query validation alone may read a root's
declared axes, because its module cannot reach the Temporal Facet. The tests
grade the flows they drive, not every spelling in the tree.
"""

from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Final, cast

import pytest

from parallax.conformance.graph_models import POLICY_MODEL, Coverage, Policy
from parallax.conformance.read_models import DepositRate
from parallax.core import (
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    attr,
    opt_lock,
    temporal_read,
)
from parallax.core import predicate as predicate_algebra
from parallax.core.deep_fetch._include_tree import build_include_tree
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, Metamodel
from parallax.core.object_query import LATEST, TX_TIME
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.sql_gen import LoweredStatement
from parallax.core.temporal_read import Edge, Pin
from parallax.core.unit_work import (
    BufferItem,
    Concurrency,
    FixedClock,
    KeyedWrite,
    MaterializedWriteGroup,
    ObjectKey,
    PlanningRequest,
    PredecessorRow,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    TemporalObservation,
    TransactionSettings,
    UnitOfWork,
    VersionedEvidenceBuilder,
    VersionObservation,
    WriteAssignment,
    WriteBatchTrigger,
    WriteObservation,
    WritePlan,
    object_key,
    run_unit_of_work,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write
from parallax.core.unit_work.planned import (
    PlannedClose,
    PlannedDelete,
    PlannedUpdate,
    PlannedWrite,
    TemporalGate,
    Versioned,
)
from parallax.core.unit_work.planner import TemporalStateKey, VersionedStateKey
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot import edge_of, pin_of
from parallax.snapshot.handle import (
    Database,
    ScopedDatabase,
    Transaction,
    build_write_planner,
    plan_temporal_close,
    stream_lowered,
)
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._read import typed_publication, wire_publication
from parallax.snapshot.materialize import ClassifiedRoot, InvalidData, RootView, classify_roots
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.db_port import (
    Read,
    ReadCall,
    ScriptedAdapter,
    ScriptEntry,
    Transact,
    Write,
    WriteCall,
)
from tests._support.model_capabilities import graph_construction_for
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer
from tests._support.root_ownership import own_root
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._judged_evidence_support import judged_rows, retained_sources
from tests.unit._temporal_group_support import temporal_group
from tests.unit._transact_support import INFINITY_INSTANT, RATE, db_for
from tests.unit.snapshot._snapshot_page_support import PageFixture, identity_of

_RECORDS = corpus_records()
_MODEL: Final[Metamodel] = formed(
    DescriptorMetamodel(
        entities=(
            *_RECORDS["account"].entities,
            *_RECORDS["appliance"].entities,
            *_RECORDS["wallet"].entities,
        )
    )
)
_TEMPORAL_MODEL: Final[Metamodel] = formed(
    DescriptorMetamodel(
        entities=(
            *_RECORDS["balance"].entities,
            *_RECORDS["position"].entities,
            *_RECORDS["quote"].entities,
            *_RECORDS["rate"].entities,
        )
    )
)


_GRANT_BOUND: Final = frozenset(
    {
        "parallax.core.object_query.validate:_validate_temporal_selections",
        "parallax.core.object_query._validated:latest_temporal_selections",
    }
)


def _trace_declarations(monkeypatch: pytest.MonkeyPatch, model: Metamodel) -> list[str]:
    """Every caller that asks a declared Attribute whether it is the version,
    or an Entity's declarations for its As-Of Axes, from now on; each read
    still answers."""
    callers: list[str] = []

    def record() -> None:
        frame = inspect.currentframe()
        caller = None if frame is None else frame.f_back
        caller = None if caller is None else caller.f_back
        assert caller is not None
        callers.append(f"{caller.f_globals['__name__']}:{caller.f_code.co_qualname}")

    def traced_property(owner: type, name: str) -> None:
        declared = owner.__dict__[name]

        def traced(instance: object) -> object:
            record()
            return declared.__get__(instance, owner)

        monkeypatch.setattr(owner, name, property(traced))

    entity_type = type(model.entities[0])
    as_of_axis: Callable[..., object] = entity_type.__dict__["as_of_axis"]

    def traced_axis(entity: object, *args: object) -> object:
        record()
        return as_of_axis(entity, *args)

    traced_property(AttributeMetadata, "optimistic_locking")
    traced_property(entity_type, "declared_as_of_axes")
    monkeypatch.setattr(entity_type, "as_of_axis", traced_axis)
    return callers


def _version_group() -> MaterializedWriteGroup:
    prepared = prepare_typed_write(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Account",
                predicate_algebra.Comparison("lessThan", "Account.balance", "1000000.00"),
            ),
            assignments=(WriteAssignment("Account.balance", Decimal("5.00")),),
        ),
        _MODEL,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    evidence = VersionedEvidenceBuilder(key_position=0, version_position=1)
    for key_value, version in ((20, 1), (21, 4)):
        evidence.append((key_value, version))
    sealed = evidence.seal()
    assert sealed is not None
    return MaterializedWriteGroup(mutation=prepared, evidence=sealed)


def _prepared_writes() -> list[BufferItem]:
    """Every non-temporal arm version settlement forks on: a versioned insert,
    observed updates and deletes of a standalone Entity and of an inherited
    position, a collapsing unversioned run, a readless predicate write, and a
    Materialized Write Group."""
    fridge_update = KeyedWrite("update", "Fridge", ({"id": 1, "name": "Chill"},))
    account_delete = KeyedWrite("delete", "Account", ({"id": 3},))
    fridge_key = object_key(fridge_update, _MODEL)
    account_key = object_key(account_delete, _MODEL)
    assert fridge_key is not None and account_key is not None
    return [
        *observed_buffer(
            [
                KeyedWrite(
                    "insert",
                    "Account",
                    ({"id": 9, "owner": "Ada", "balance": Decimal("1.00")},),
                ),
                fridge_update,
                account_delete,
                KeyedWrite("update", "Wallet", ({"id": 1, "balance": Decimal("2.00")},)),
                KeyedWrite("update", "Wallet", ({"id": 2, "balance": Decimal("2.00")},)),
                PredicateWrite(
                    "delete",
                    PredicateSelection(
                        "Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 7)
                    ),
                ),
            ],
            _MODEL,
            {
                fridge_key: VersionObservation(observed_version=5),
                account_key: VersionObservation(observed_version=2),
            },
        ),
        _version_group(),
    ]


def _settled_versions(steps: list[PlannedWrite]) -> list[tuple[EntityIdentity, object]]:
    """Each versioned step's Entity beside the version Attribute planning settled."""
    return [
        (step.entity, step.concurrency.attribute)
        for step in steps
        if isinstance(step, PlannedUpdate | PlannedDelete)
        and isinstance(step.concurrency, Versioned)
    ]


def _owner_version(entity: EntityIdentity) -> object:
    key = opt_lock.view(_MODEL).key(entity)
    assert isinstance(key, opt_lock.ExplicitVersion)
    return key.attribute


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_planning_and_lowering_prepared_writes_take_the_version_from_its_owner(
    monkeypatch: pytest.MonkeyPatch, concurrency: Concurrency
) -> None:
    prepared = _prepared_writes()
    planner = build_write_planner(_MODEL)
    callers = _trace_declarations(monkeypatch, _MODEL)

    plan = planner.finalize(
        PlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency=concurrency,
            buffered_writes=prepared,
        )
    ).plan
    lowered: list[tuple[PlannedWrite, LoweredStatement]] = list(
        stream_lowered(plan, _MODEL, POSTGRES)
    )

    assert callers == []
    settled = _settled_versions([step for step, _statement in lowered])
    assert {entity.name for entity, _version in settled} == {"Account", "Fridge"}
    assert all(version is _owner_version(entity) for entity, version in settled)
    assert "update wallet set balance = ? where id in (?, ?)" in [
        statement.sql for _step, statement in lowered
    ]


_OPENED: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_TRANSACTION_TIME: Final[Mapping[str, object]] = {"txStart": _OPENED, "txEnd": "infinity"}
_BITEMPORAL: Final[Mapping[str, object]] = {
    "validStart": _OPENED,
    "validEnd": "infinity",
    **_TRANSACTION_TIME,
}
_VALID_FROM: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _value_update(entity: str, *, valid_from: dt.datetime | None = None) -> PredicateWrite:
    return PredicateWrite(
        "update",
        PredicateSelection(
            entity, predicate_algebra.Comparison("lessThan", f"{entity}.value", "1000000.00")
        ),
        assignments=(WriteAssignment(f"{entity}.value", Decimal("7.00")),),
        valid_from=valid_from,
    )


def _temporal_writes() -> list[BufferItem]:
    """Observed updates of an inherited position in a Transaction-Time-Only and
    a Bitemporal family, an observed standalone terminate, and a packed
    Materialized Write Group of each temporal shape."""
    quote_update = KeyedWrite("update", "SpotQuote", ({"id": 1, "price": Decimal("2.00")},))
    rate_update = KeyedWrite(
        "update", "DepositRate", ({"id": 2, "amount": Decimal("3.00")},), valid_from=_VALID_FROM
    )
    balance_terminate = KeyedWrite("terminate", "Balance", ({"id": 3},))
    predecessors: list[tuple[KeyedWrite, Mapping[str, object]]] = [
        (quote_update, {"id": 1, "price": Decimal("1"), "symbol": "Q", **_TRANSACTION_TIME}),
        (rate_update, {"id": 2, "amount": Decimal("1"), "grade": "A", **_BITEMPORAL}),
        (balance_terminate, {"id": 3, "acctNum": "B", "value": Decimal("1"), **_TRANSACTION_TIME}),
    ]
    observations: dict[ObjectKey, WriteObservation] = {}
    for write, members in predecessors:
        key = object_key(write, _TEMPORAL_MODEL)
        assert key is not None
        observations[key] = TemporalObservation(predecessor=PredecessorRow(members=members))
    return [
        *observed_buffer(
            [write for write, _members in predecessors], _TEMPORAL_MODEL, observations
        ),
        temporal_group(
            _value_update("Balance"),
            _TEMPORAL_MODEL,
            [
                {"id": row, "acctNum": "B", "value": Decimal("1"), **_TRANSACTION_TIME}
                for row in (10, 11, 12)
            ],
        ),
        temporal_group(
            _value_update("Position", valid_from=_VALID_FROM),
            _TEMPORAL_MODEL,
            [
                {"id": row, "acctNum": "P", "value": Decimal("1"), **_BITEMPORAL}
                for row in (20, 21, 22)
            ],
        ),
    ]


def _close_probes(concurrency: Concurrency) -> list[PlannedClose]:
    return [
        plan_temporal_close(
            {"id": 4},
            name,
            _TEMPORAL_MODEL,
            concurrency,
            instant_at("2024-06-01T00:00:00+00:00"),
            _OPENED,
            valid_end,
        )
        for name, valid_end in (("SpotQuote", None), ("DepositRate", "infinity"))
    ]


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_admitting_planning_and_lowering_temporal_writes_take_axes_from_the_family_shape(
    monkeypatch: pytest.MonkeyPatch, concurrency: Concurrency
) -> None:
    planner = build_write_planner(_TEMPORAL_MODEL)
    callers = _trace_declarations(monkeypatch, _TEMPORAL_MODEL)

    plan = planner.finalize(
        PlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-06-01T00:00:00+00:00"),
            concurrency=concurrency,
            buffered_writes=_temporal_writes(),
        )
    ).plan
    steps = list(plan.steps)
    assert list(plan.steps) == steps
    lowered = list(stream_lowered(plan, _TEMPORAL_MODEL, POSTGRES))
    probes = _close_probes(concurrency)

    assert callers == []
    assert len(lowered) == len(steps)
    closes = [step for step in (*steps, *probes) if isinstance(step, PlannedClose)]
    # Three addressed writes, three rows of each packed group, and two probes.
    assert len(closes) == 11
    for close in closes:
        shape = temporal_read.view(_TEMPORAL_MODEL).shape(close.entity)
        assert isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)
        transaction_time = shape.transaction_time
        assert close.target.end_attributes[-1] is transaction_time.end_attribute
        assert close.target.key_attributes[0].name == "id"
        if concurrency == "optimistic":
            assert isinstance(close.concurrency, TemporalGate)
            assert close.concurrency.start_attribute is transaction_time.start_attribute
        else:
            assert not isinstance(close.concurrency, TemporalGate)


def test_a_typed_temporal_insert_admits_and_flushes_from_the_family_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = ScriptedAdapter(Transact(Write(times=1)))
    database = own_root(
        Database.connect(port, RATE, clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)))
    )
    callers = _trace_declarations(monkeypatch, _TEMPORAL_MODEL)

    def insert(tx: Transaction) -> None:
        tx.insert(DepositRate(id=1, amount=Decimal("1.00"), grade="A"), valid_from=_VALID_FROM)

    database.using_database_login().transact(insert)

    assert callers == []
    (write,) = [call for call in port.calls if isinstance(call, WriteCall)]
    assert write.sql.startswith("insert into deposit_rate")


def _deposit_rate_row(id_: int) -> Mapping[str, object]:
    return {
        "id": id_,
        "amount": Decimal("1.00"),
        "grade": "A",
        "from_z": _OPENED,
        "thru_z": INFINITY_INSTANT,
        "in_z": _OPENED,
        "out_z": INFINITY_INSTANT,
    }


def test_keyed_temporal_writes_settle_standalone_evidence_from_the_family_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = ScriptedAdapter(
        Read(rows=[_deposit_rate_row(1)]),
        Read(rows=[_deposit_rate_row(2)]),
        Transact(Write(times=5)),
    )
    database = db_for(RATE, port)

    def latest(id_: int) -> DepositRate:
        return database.find(
            DepositRate.where(DepositRate.id == id_).as_of(valid_time=LATEST)
        ).result()

    callers = _trace_declarations(monkeypatch, _TEMPORAL_MODEL)
    updated, terminated = latest(1), latest(2)

    def write(tx: Transaction) -> None:
        tx.update(updated.edit(amount=Decimal("2.00")), valid_from=_VALID_FROM)
        tx.terminate(terminated, valid_from=_VALID_FROM)

    database.transact(write)

    assert set(callers) <= _GRANT_BOUND
    closes = [
        call.sql for call in port.calls if isinstance(call, WriteCall) and "set out_z" in call.sql
    ]
    assert len(closes) == 2
    assert all("in_z = " in close for close in closes)


class OwnedAppliance(
    Entity,
    namespace="parallax.ownership",
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class OwnedFridge(
    OwnedAppliance,
    table="owned_fridge",
    namespace="parallax.ownership",
    inheritance=ConcreteSubtype,
):
    litres: Attr[int | None] = attr(type=Int32)


_APPLIANCE: Final = DomainModel(OwnedAppliance, OwnedFridge)
_PUBLICATIONS: Final = ("typed", "wire", "rows")


class _PreparedPage:
    """One conforming and one issue-carrying root of ``entity``, sealed into a
    Page with everything publication needs formed before any trace starts."""

    def __init__(
        self,
        domain: DomainModel,
        entity: str,
        conforming: Mapping[str, object],
        invalid: Mapping[str, object],
        *,
        history: bool,
    ) -> None:
        meta = model_of(domain)
        fixture = PageFixture(domain, model=meta)
        self.page = fixture.page(fixture.node(entity, conforming), fixture.node(entity, invalid))
        self.cataloged = CatalogedModel(meta)
        self.construction = graph_construction_for(domain)
        self.identity = identity_of(meta, entity)
        self.includes = build_include_tree(
            queried=self.identity, root=(self.identity,), positions=()
        )
        self.milestones = temporal_read.view(meta).shape(self.identity) if history else None

    def published(self, publication: str) -> tuple[object, ...]:
        if publication == "rows":
            return classify_roots(RootView(self.page), self.cataloged.meta, CONCURRENCY).roots
        selected = (
            typed_publication(self.cataloged, self.construction, "owned")
            if publication == "typed"
            else wire_publication(self.cataloged, "owned")
        )
        return tuple(
            selected.roots_of(self.page, self.includes, atomic=True, milestones=self.milestones)
        )


def _record(published: object) -> ClassifiedRoot | InvalidData[object]:
    assert isinstance(published, ClassifiedRoot | InvalidData)
    return cast("ClassifiedRoot | InvalidData[object]", published)


@pytest.mark.parametrize("publication", _PUBLICATIONS)
def test_materializing_an_inherited_versioned_page_reads_the_version_from_its_owner(
    monkeypatch: pytest.MonkeyPatch, publication: str
) -> None:
    row = {"id": 1, "name": "Chill", "version": 3, "litres": 40}
    prepared = _PreparedPage(
        _APPLIANCE, "OwnedFridge", row, {**row, "id": 2, "name": None}, history=False
    )
    callers = _trace_declarations(monkeypatch, prepared.cataloged.meta)

    _conforming, invalid = prepared.published(publication)

    assert callers == []
    record = _record(invalid)
    assert record.version == 3
    assert record.object_key == ObjectKey(prepared.identity, (("id", 2),))


@pytest.mark.parametrize("publication", _PUBLICATIONS)
def test_materializing_an_inherited_milestone_page_reads_axes_from_the_family_shape(
    monkeypatch: pytest.MonkeyPatch, publication: str
) -> None:
    row = {
        "id": 1,
        "amount": Decimal("1.00"),
        "grade": "A",
        "from_z": _VALID_FROM,
        "thru_z": INFINITY_INSTANT,
        "in_z": _OPENED,
        "out_z": INFINITY_INSTANT,
    }
    prepared = _PreparedPage(
        RATE, "DepositRate", row, {**row, "id": 2, "amount": None}, history=True
    )
    callers = _trace_declarations(monkeypatch, prepared.cataloged.meta)

    conforming, invalid = prepared.published(publication)

    assert callers == []
    edge = Edge(tx_time=_OPENED, valid_time=_VALID_FROM)
    assert _record(invalid).edge == edge
    if publication == "typed":
        assert edge_of(conforming) == edge
        assert pin_of(conforming) == Pin(tx_time=_OPENED, valid_time=_VALID_FROM)


def _no_flush(_plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
    return None


_EVIDENCE: Final = {
    "DepositRate": (
        RATE,
        {
            "id": 1,
            "amount": Decimal("1.00"),
            "grade": "A",
            "from_z": _VALID_FROM,
            "thru_z": INFINITY_INSTANT,
            "in_z": _OPENED,
            "out_z": INFINITY_INSTANT,
        },
    ),
    "OwnedFridge": (_APPLIANCE, {"id": 1, "name": "Chill", "version": 3, "litres": 40}),
}


@pytest.mark.parametrize("participating", [False, True], ids=["standalone", "participating"])
@pytest.mark.parametrize("entity", sorted(_EVIDENCE))
def test_retaining_read_evidence_reads_each_familys_locator_from_its_owner(
    monkeypatch: pytest.MonkeyPatch, entity: str, participating: bool
) -> None:
    domain, columns = _EVIDENCE[entity]
    meta = model_of(domain)
    identity = identity_of(meta, entity)
    judged = judged_rows(meta, identity, columns)
    planner = build_write_planner(meta)
    callers = _trace_declarations(monkeypatch, meta)

    def retain(ledger: UnitOfWork | None) -> RetainedObservation | None:
        return retained_sources(meta, judged, ledger=ledger)[0].observation

    retained = (
        run_unit_of_work(
            retain,
            settings=TransactionSettings(),
            clock=FixedClock(_OPENED),
            meta=meta,
            flush_executor=_no_flush,
            planner=planner,
            actor_identity=TEST_ACTOR_IDENTITY,
        )
        if participating
        else retain(None)
    )

    assert callers == []
    assert retained is not None
    observed = ObjectKey(identity, (("id", 1),))
    assert retained.key == (
        TemporalStateKey(observed, Edge(tx_time=_OPENED, valid_time=_VALID_FROM))
        if entity == "DepositRate"
        else VersionedStateKey(observed, 3)
    )


_LATER: Final = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_POLICY_ROW: Final[Mapping[str, object]] = {
    "id": 1,
    "name": "P-1",
    "from_z": _OPENED,
    "thru_z": INFINITY_INSTANT,
    "in_z": _OPENED,
    "out_z": INFINITY_INSTANT,
}
_COVERAGE_ROW: Final[Mapping[str, object]] = {
    "id": 10,
    "policy_id": 1,
    "amount": Decimal("250.00"),
    "from_z": _OPENED,
    "thru_z": INFINITY_INSTANT,
    "in_z": _OPENED,
    "out_z": INFINITY_INSTANT,
}
_RATE_MILESTONES: Final = (
    {**_deposit_rate_row(1), "out_z": _LATER},
    {**_deposit_rate_row(1), "amount": Decimal("2.00"), "in_z": _LATER},
)


def _rate_history() -> ObjectQuery[DepositRate, DepositRate]:
    return DepositRate.where(DepositRate.id == 1).history(TX_TIME).as_of(valid_time=LATEST)


def _navigated_policies(database: ScopedDatabase) -> None:
    query = (
        Policy.where(Policy.coverages.exists(Coverage.amount > Decimal("0")))
        .as_of(valid_time=LATEST)
        .include(Policy.coverages)
    )
    assert [policy.id for policy in database.find(query).results()] == [1]


def _latest_rate(database: ScopedDatabase) -> None:
    query = DepositRate.where(DepositRate.id == 1).as_of(valid_time=LATEST)
    assert database.find(query).result().amount == Decimal("1.00")


def _eager_rate_history(database: ScopedDatabase) -> None:
    milestones = database.find(_rate_history()).results()
    assert [edge_of(root).tx_time for root in milestones] == [_OPENED, _LATER]


def _streamed_rate_history(database: ScopedDatabase) -> None:
    with database.stream(_rate_history(), batch_size=len(_RATE_MILESTONES) + 1) as stream:
        assert [edge_of(root).tx_time for root in stream] == [_OPENED, _LATER]


def _materialized_policy_update(database: ScopedDatabase) -> None:
    def update(tx: Transaction) -> None:
        tx.update_where(
            Policy.where(Policy.id == 1), Policy.name.set("P-2"), valid_from=_VALID_FROM
        )

    database.transact(update)


_QUERIES: Final[
    Mapping[str, tuple[DomainModel, tuple[ScriptEntry, ...], Callable[[ScopedDatabase], None]]]
] = {
    "navigated-include": (
        POLICY_MODEL,
        (Read(rows=[_POLICY_ROW]), Read(rows=[_COVERAGE_ROW])),
        _navigated_policies,
    ),
    "inherited-latest": (RATE, (Read(rows=[_deposit_rate_row(1)]),), _latest_rate),
    "inherited-history": (RATE, (Read(rows=list(_RATE_MILESTONES)),), _eager_rate_history),
    "inherited-stream": (RATE, (Read(rows=list(_RATE_MILESTONES)),), _streamed_rate_history),
    "materialized-update": (
        POLICY_MODEL,
        (Transact(Read(rows=[_POLICY_ROW]), Write(times=3)),),
        _materialized_policy_update,
    ),
}


@pytest.mark.parametrize("flow", sorted(_QUERIES))
def test_planning_and_running_queries_take_family_facts_from_their_owners(
    monkeypatch: pytest.MonkeyPatch, flow: str
) -> None:
    domain, answers, run = _QUERIES[flow]
    port = ScriptedAdapter(*answers)
    database = db_for(domain, port)
    callers = _trace_declarations(monkeypatch, model_of(domain))

    run(database)

    assert callers
    assert set(callers) <= _GRANT_BOUND
    assert any(isinstance(call, ReadCall) for call in port.calls)
