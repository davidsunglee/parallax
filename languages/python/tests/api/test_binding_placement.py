"""Placing one model under explicit Database Bindings through the public verbs."""

from __future__ import annotations

import dataclasses
from contextlib import closing
from typing import Any, Final

import pytest

from parallax.core import (
    POSTGRES,
    PUBLICATION_RELOCATION_REFUSED,
    Attr,
    BindingError,
    DomainModel,
    Entity,
    Sequence,
    ServingModel,
    UsageError,
    attr,
    prepare_model,
)
from parallax.core.internal.entity import model_of
from parallax.evolution import (
    ABSENT,
    CoordinatedEvolution,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.evolution.operations import SequenceRelocated, TableRelocated
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresSequence, PostgresTable
from parallax.snapshot import connect
from tests._support.root_ownership import own_root


class PlacedLedger(Entity, table="bp_ledger", namespace="placement"):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=32)


class PlacedTicket(Entity, table="bp_ticket", namespace="placement"):
    id: Attr[int] = attr(primary_key=Sequence(name="ticketNumbers"))


class PlacedRefund(Entity, table="bp_refund", namespace="placement"):
    id: Attr[int] = attr(primary_key=True)


_LEDGERS: Final = DomainModel(PlacedLedger)
_TICKETS: Final = DomainModel(PlacedLedger, PlacedTicket)
_GROWN: Final = DomainModel(PlacedLedger, PlacedTicket, PlacedRefund)
_PX: Final = PostgresLocation(schema="px")
_DEFAULT: Final = PostgresBinding(default=_PX)
_LEDGER: Final = "placement.PlacedLedger"


def _selection(model: DomainModel, binding: PostgresBinding, edition: str = "r1") -> Any:
    return prepare_model(model, binding=binding, edition=edition)


# --------------------------------------------------------------------------- #
# Publication and evolution judge one binding change by the same relocations.  #
# --------------------------------------------------------------------------- #


def test_a_binding_only_table_move_is_refused_by_publication_and_coordinated_by_evolution() -> None:
    moved = PostgresBinding(default=_PX, entities={_LEDGER: PostgresTable(schema="px_archive")})
    current = _selection(_LEDGERS, _DEFAULT)
    serving = ServingModel(current)
    with pytest.raises(UsageError) as refused:
        serving.publish(_selection(_LEDGERS, moved, "r2"), expected=current)
    assert refused.value.code == PUBLICATION_RELOCATION_REFUSED
    assert "px.bp_ledger to px_archive.bp_ledger" in str(refused.value)
    assert serving.current() is current

    evolution = evolve(_LEDGERS, _LEDGERS, earlier_binding=_DEFAULT, later_binding=moved)
    assert isinstance(evolution, CoordinatedEvolution)
    (operation,) = evolution.operations
    assert isinstance(operation, TableRelocated)
    assert operation.mapping_owner.canonical == _LEDGER
    assert (operation.earlier.qualifier, operation.later.qualifier) == (("px",), ("px_archive",))
    (requirement,) = evolution.coordination_requirements
    assert requirement.operation == operation


def test_a_binding_only_sequence_move_is_refused_and_coordinated_alike() -> None:
    moved = PostgresBinding(
        default=_PX, sequences={"ticketNumbers": PostgresSequence(schema="px_keys")}
    )
    current = _selection(_TICKETS, _DEFAULT)
    with pytest.raises(UsageError) as refused:
        ServingModel(current).publish(_selection(_TICKETS, moved, "r2"), expected=current)
    assert refused.value.code == PUBLICATION_RELOCATION_REFUSED
    assert "sequence 'ticketNumbers' from px.ticketNumbers to px_keys.ticketNumbers" in str(
        refused.value
    )

    evolution = evolve(_TICKETS, _TICKETS, earlier_binding=_DEFAULT, later_binding=moved)
    assert isinstance(evolution, CoordinatedEvolution)
    (operation,) = evolution.operations
    assert isinstance(operation, SequenceRelocated)
    assert operation.allocator == "ticketNumbers"


def test_growth_and_a_default_change_that_pins_every_survivor_publish_hot() -> None:
    current = _selection(_TICKETS, _DEFAULT)
    serving = ServingModel(current)
    pinned = PostgresBinding(
        default=PostgresLocation(schema="px_next"),
        entities={
            _LEDGER: PostgresTable(schema="px"),
            "placement.PlacedTicket": PostgresTable(schema="px"),
        },
        sequences={"ticketNumbers": PostgresSequence(schema="px")},
    )
    candidate = _selection(_GROWN, pinned, "r2")
    serving.publish(candidate, expected=current)
    assert serving.current() is candidate
    evolution = evolve(_TICKETS, _GROWN, earlier_binding=_DEFAULT, later_binding=pinned)
    assert isinstance(evolution, UnilateralEvolution)
    assert schema_delta(evolution).statements[0].startswith("create table px_next.bp_refund")


# --------------------------------------------------------------------------- #
# Every door that prepares a model requires its binding, and refuses before I/O.
# --------------------------------------------------------------------------- #


_misused_connect: Any = connect
_misused_prepare: Any = prepare_model
_misused_evolve: Any = evolve
"""The doors called the ways their signatures refuse, to observe the runtime refusal."""


class _NeverOpened:
    """An adapter whose ``open`` fails the test: every refusal comes first."""

    dialect = POSTGRES

    def open(self) -> Any:
        raise AssertionError("the adapter was opened before the refusal")


def _code(refused: pytest.ExceptionInfo[UsageError]) -> str:
    return refused.value.code


def test_each_door_that_prepares_a_model_names_the_missing_binding() -> None:
    doors = (
        lambda: _misused_connect(_NeverOpened(), _LEDGERS),
        lambda: _misused_prepare(_LEDGERS, edition="r1"),
        lambda: _misused_evolve(ABSENT, _LEDGERS),
        lambda: _misused_evolve(_LEDGERS, _LEDGERS, later_binding=_DEFAULT),
    )
    for door in doors:
        with pytest.raises(UsageError) as refused:
            door()
        assert _code(refused) == "binding-required"
        assert "02-modeling.md#database-bindings" in str(refused.value)


def test_a_serving_model_connects_without_a_binding_and_refuses_one() -> None:
    serving = ServingModel(_selection(_LEDGERS, _DEFAULT))
    with pytest.raises(UsageError) as refused:
        _misused_connect(_NeverOpened(), serving, binding=_DEFAULT)
    assert _code(refused) == "connect-binding-unexpected"


def test_an_unplaceable_binding_is_refused_before_the_adapter_opens() -> None:
    collision = PostgresBinding(
        default=_PX, entities={"placement.PlacedTicket": PostgresTable(name="bp_ledger")}
    )
    with pytest.raises(BindingError) as refused:
        _misused_connect(_NeverOpened(), _TICKETS, binding=collision)
    assert [issue.code for issue in refused.value.issues] == ["binding-table-collision"]


class _OtherBackend(_NeverOpened):
    dialect = dataclasses.replace(POSTGRES, name="mariadb")


def test_a_binding_for_another_backend_than_the_adapter_is_refused_before_it_opens() -> None:
    with pytest.raises(UsageError) as refused:
        _misused_connect(_OtherBackend(), _LEDGERS, binding=_DEFAULT)
    assert _code(refused) == "connect-backend-mismatch"
    with pytest.raises(UsageError) as refused:
        _misused_connect(_OtherBackend(), ServingModel(_selection(_LEDGERS, _DEFAULT)))
    assert _code(refused) == "connect-backend-mismatch"


def test_evolving_from_absent_takes_no_earlier_binding() -> None:
    with pytest.raises(UsageError) as refused:
        _misused_evolve(ABSENT, _LEDGERS, earlier_binding=_DEFAULT, later_binding=_DEFAULT)
    assert _code(refused) == "evolution-binding-unexpected"


# --------------------------------------------------------------------------- #
# One model, two bindings, one PostgreSQL database: the data never merges.     #
# --------------------------------------------------------------------------- #

_TENANT_A: Final = PostgresBinding(default=PostgresLocation(schema="px"))
_TENANT_B: Final = PostgresBinding(default=PostgresLocation(schema="public"))


def _provision_both_tenants(profile_run: Any) -> None:
    """Provision tenant A through the provider's reset, then tenant B's tables
    beside it through the shipped generator under B's binding."""
    profile_run.reset(model_of(_LEDGERS), {}, _TENANT_A)
    with closing(profile_run.control()) as control:
        for statement in schema_delta(evolve(ABSENT, _LEDGERS, later_binding=_TENANT_B)).statements:
            control.execute_write(statement, [])
        control.execute_write(
            "grant select, insert, update, delete on all tables in schema public "
            f"to {POSTGRES.quote(profile_run.default_role.name)}",
            [],
        )


def test_one_model_under_two_bindings_keeps_each_tenants_rows_apart(profile_run: Any) -> None:
    _provision_both_tenants(profile_run)
    tenant_a, tenant_b = (
        own_root(
            connect(profile_run.port, ServingModel(_selection(_LEDGERS, binding, "release-1")))
        ).using_database_login()
        for binding in (_TENANT_A, _TENANT_B)
    )
    tenant_a.transact(lambda tx: tx.insert(PlacedLedger(id=1, owner="ada")))
    tenant_b.transact(lambda tx: tx.wire.insert("PlacedLedger", {"id": 1, "owner": "bob"}))

    everything: dict[str, object] = {"target": "PlacedLedger", "predicate": {"true": {}}}
    for db, owner in ((tenant_a, "ada"), (tenant_b, "bob")):
        assert db.find(PlacedLedger.where(PlacedLedger.id == 1)).result().owner == owner
        (node,) = db.wire.find(everything).results()
        assert node["owner"] == owner
    with closing(profile_run.control()) as control:
        assert control.execute("select owner from px.bp_ledger", []) == [("ada",)]
        assert control.execute("select owner from public.bp_ledger", []) == [("bob",)]
