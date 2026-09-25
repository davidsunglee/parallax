"""Family facts reach a prepared write flow from the facets that formed them.

Formation settles each family's version source once. A flow that later asks a
declared Attribute whether it is the version re-derives that answer, and a
correct answer hides the duplicate work. These tests record every such
declaration read while production seams plan and lower prepared writes, so a
re-derivation fails even when it agrees with the owner. They grade the flows
they drive, not every spelling in the tree.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Final

import pytest

from parallax.core import opt_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    BufferItem,
    ChunkedColumnBuilder,
    Concurrency,
    KeyedWrite,
    MaterializedWriteGroup,
    PlanningRequest,
    PredicateSelection,
    PredicateWrite,
    VersionColumns,
    VersionObservation,
    WriteAssignment,
    object_key,
    whole,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write
from parallax.core.unit_work.planned import (
    PlannedDelete,
    PlannedUpdate,
    PlannedWrite,
    Versioned,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot.handle import build_write_planner, stream_lowered
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer
from tests.unit._corpus_model_support import corpus_records, formed

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


def _trace_version_declarations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every caller that asks a declared Attribute whether it is the version,
    from now on; each read still answers."""
    declared = AttributeMetadata.__dict__["optimistic_locking"]
    callers: list[str] = []

    def traced(attribute: AttributeMetadata) -> bool:
        frame = inspect.currentframe()
        caller = None if frame is None else frame.f_back
        assert caller is not None
        callers.append(f"{caller.f_globals['__name__']}:{caller.f_code.co_qualname}")
        return declared.__get__(attribute, AttributeMetadata)

    monkeypatch.setattr(AttributeMetadata, "optimistic_locking", property(traced))
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
    callers = _trace_version_declarations(monkeypatch)

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
