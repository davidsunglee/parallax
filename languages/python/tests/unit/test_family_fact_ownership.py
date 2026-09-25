"""Family facts reach a prepared write flow from the facets that formed them.

Formation settles each family's version source and Temporal Shape once. A flow
that later asks a declared Attribute whether it is the version, or asks an
Entity's declarations for its As-Of Axes, re-derives that answer, and a correct
answer hides the duplicate work. These tests record every such declaration read
while production seams admit, plan, and lower writes, so a re-derivation fails
even when it agrees with the owner. They grade the flows they drive, not every
spelling in the tree.
"""

from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance.read_models import DepositRate
from parallax.core import opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    BufferItem,
    ChunkedColumnBuilder,
    Concurrency,
    FixedClock,
    KeyedWrite,
    MaterializedWriteGroup,
    ObjectKey,
    PlanningRequest,
    PredecessorRow,
    PredicateSelection,
    PredicateWrite,
    TemporalObservation,
    VersionColumns,
    VersionObservation,
    WriteAssignment,
    WriteObservation,
    object_key,
    whole,
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
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle import (
    Database,
    Transaction,
    build_write_planner,
    plan_temporal_close,
    stream_lowered,
)
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer
from tests._support.root_ownership import own_root
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._temporal_group_support import temporal_group
from tests.unit._transact_support import RATE

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
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for key_value, version in ((20, 1), (21, 4)):
        keys.append(key_value)
        versions.append(version)
    return MaterializedWriteGroup(
        mutation=prepared,
        key_attributes=("id",),
        key_columns=(whole(keys.build()),),
        observations=VersionColumns(versions=whole(versions.build())),
    )


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
