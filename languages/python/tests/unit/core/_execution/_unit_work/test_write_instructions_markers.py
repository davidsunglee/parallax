"""DB-computed markers are judged at admission (`m-pk-gen`, `m-value-object`
"Writing"): a marker at a top-level scalar Attribute plans the generated value
its write's context allows, or is refused before anything is buffered."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.conformance import models
from parallax.core import Attr, DomainModel, TxTemporal, attr
from parallax.core._execution._unit_work.instructions import (
    KeyedWriteInstruction,
    PreparedKeyedInstruction,
    prepare_typed_insert,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.internal.base import UsageError
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.write_plan.managed_row import ManagedRow
from parallax.core.internal.write_plan.steps import MAX_PLUS_ONE, SelfIncrement
from tests._support.errors import raises_code
from tests._support.write_preparation import write_preparation_of

_MODELS = models.load_models()
_PK_MAX = _MODELS["pk-max"]
_PK_SEQUENCE = _MODELS["pk-sequence"]
_CUSTOMER = _MODELS["customer"]

_PREPARERS = (prepare_typed_write, prepare_wire_write)
_LANES = ("typed", "wire")


class Counter(TxTemporal, table="counter", namespace="insert.markers"):
    id: Attr[int] = attr(primary_key=True)
    level: Attr[int]


_COUNTER = model_of(DomainModel(Counter))


def _row(
    prepare: Callable[..., object], instruction: KeyedWriteInstruction, model: Metamodel
) -> dict[str, object]:
    prepared = prepare(instruction, write_preparation_of(model))
    assert isinstance(prepared, PreparedKeyedInstruction)
    (row,) = prepared.rows
    return _named(row)


def _named(row: ManagedRow) -> dict[str, object]:
    members = row.selection.members.shape.members
    return {members[position].name: cell for position, cell in row.stated_cells()}


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_max_plus_one_marker_plans_the_key_an_opening_allocates(
    prepare: Callable[..., object],
) -> None:
    insert = KeyedWriteInstruction(
        "insert", "Attendee", ({"id": {"computed": "maxPlusOne"}, "name": "Ada"},)
    )
    assert _row(prepare, insert, _PK_MAX) == {"id": MAX_PLUS_ONE, "name": "Ada"}


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_an_increment_marker_plans_the_registry_advance_an_update_reads(
    prepare: Callable[..., object],
) -> None:
    update = KeyedWriteInstruction(
        "amend", "PkSequence", ({"name": "badge_seq", "nextVal": {"increment": 2}},)
    )
    assert _row(prepare, update, _PK_SEQUENCE)["nextVal"] == SelfIncrement(amount=2)


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_temporal_assignment_plans_in_the_successor_rows_insert_context(
    prepare: Callable[..., object],
) -> None:
    preparation = write_preparation_of(_COUNTER)
    canonical = "insert.markers.Counter"
    computed = KeyedWriteInstruction(
        "amend", canonical, ({"id": 1, "level": {"computed": "maxPlusOne"}},)
    )
    assert _row(prepare, computed, _COUNTER)["level"] is MAX_PLUS_ONE
    increment = KeyedWriteInstruction("amend", canonical, ({"id": 1, "level": {"increment": 1}},))
    with raises_code(
        UsageError,
        "write-instruction-invalid",
        match=r"unsupported DB-computed marker on 'Counter'\.level: a 'increment' marker is "
        r"not recognized for insert planning$",
    ):
        prepare(increment, preparation)


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_marker_shaped_value_object_is_a_document(prepare: Callable[..., object]) -> None:
    # Judged as the address document it is, which states none of its members.
    insert = KeyedWriteInstruction(
        "insert", "Customer", ({"id": 9, "name": "Ada", "address": {"computed": "maxPlusOne"}},)
    )
    with pytest.raises(
        UsageError,
        match=r"Customer\.address\.street: required attribute is absent \(or null\)$",
    ):
        prepare(insert, write_preparation_of(_CUSTOMER))


@pytest.mark.parametrize(
    ("prepare", "code"),
    [
        (prepare_typed_write, "write-value-type-mismatch"),
        (prepare_wire_write, "neutral-literal-type-mismatch"),
    ],
    ids=_LANES,
)
@pytest.mark.parametrize("mutation", ["delete", "amend"])
def test_a_key_an_existing_object_is_addressed_by_is_never_a_marker(
    prepare: Callable[..., object], code: str, mutation: str
) -> None:
    row: dict[str, object] = {"id": {"computed": "maxPlusOne"}}
    if mutation == "amend":
        row["name"] = "Ada"
    instruction = KeyedWriteInstruction(
        mutation,  # pyright: ignore[reportArgumentType]
        "Attendee",
        (row,),
    )
    with raises_code(UsageError, code, match=r"Attendee\.id: "):
        prepare(instruction, write_preparation_of(_PK_MAX))


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_replacement_and_an_explicit_assignment_plan_where_each_member_is_judged(
    prepare: Callable[..., object],
) -> None:
    preparation = write_preparation_of(_PK_SEQUENCE)
    row = {"name": "badge_seq", "nextVal": {"increment": 3}}
    replaced = prepare(KeyedWriteInstruction("replace", "PkSequence", (row,)), preparation)
    assigned = prepare(
        KeyedWriteInstruction("amend", "PkSequence", (row,)),
        preparation,
        authored_members={"nextVal"},
    )
    for prepared in (replaced, assigned):
        assert isinstance(prepared, PreparedKeyedInstruction)
        (planned,) = prepared.rows
        assert _named(planned)["nextVal"] == SelfIncrement(amount=3)


def test_only_an_opening_is_prepared_as_one() -> None:
    entity = _PK_MAX.entities[0]
    with pytest.raises(ValueError, match=r"^'amend' opens no row$"):
        prepare_typed_insert(
            write_preparation_of(_PK_MAX), "amend", entity, (), valid_from=None, until=None
        )
