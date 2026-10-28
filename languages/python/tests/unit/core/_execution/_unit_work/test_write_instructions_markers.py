"""DB-computed markers are judged at admission (`m-pk-gen`, `m-value-object`
"Writing"): a marker at a top-level scalar Attribute plans the generated value
its write's context allows, or is refused before anything is buffered."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.conformance import models
from parallax.core import Attr, DomainModel, TxTemporal, attr
from parallax.core._execution._unit_work.instructions import (
    InstructionRejectedError,
    KeyedWriteInstruction,
    PreparedKeyedInstruction,
    WriteInstructionError,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import JSON
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel, Table
from parallax.core.unit_work import WriteRejectedError
from parallax.core.write_plan.managed_row import ManagedRow
from parallax.core.write_plan.steps import MAX_PLUS_ONE, SelfIncrement
from tests._support.write_preparation import write_preparation_of
from tests.unit._metamodel_support import Declaration, attribute, identity, key, source

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

_DOCUMENT = identity("MarkedDocument")
_JSON_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_DOCUMENT,
            container=Table("marked_document"),
            attributes=(key(_DOCUMENT), attribute(_DOCUMENT, "payload", type=JSON)),
        )
    )
)


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
    with pytest.raises(
        WriteInstructionError,
        match=r"^unsupported DB-computed marker on 'Counter'\.level: a 'increment' marker is "
        r"not recognized for insert planning$",
    ):
        prepare(increment, preparation)


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_scalar_json_attribute_keeps_its_root_marker_reading(
    prepare: Callable[..., object],
) -> None:
    canonical = _DOCUMENT.canonical
    marked = KeyedWriteInstruction(
        "insert", canonical, ({"id": 1, "payload": {"computed": "maxPlusOne"}},)
    )
    assert _row(prepare, marked, _JSON_MODEL)["payload"] is MAX_PLUS_ONE
    # A mapping of another shape is a Json document like any other.
    shaped = KeyedWriteInstruction(
        "insert", canonical, ({"id": 1, "payload": {"computed": "maxPlusOne", "x": 1}},)
    )
    assert dict(_row(prepare, shaped, _JSON_MODEL)["payload"]) == {  # pyright: ignore[reportArgumentType, reportCallIssue]
        "computed": "maxPlusOne",
        "x": 1,
    }


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_marker_shaped_value_object_is_a_document(prepare: Callable[..., object]) -> None:
    # Judged as the address document it is, which states none of its members.
    insert = KeyedWriteInstruction(
        "insert", "Customer", ({"id": 9, "name": "Ada", "address": {"computed": "maxPlusOne"}},)
    )
    with pytest.raises(
        WriteRejectedError,
        match=r"^Customer\.address\.street: required attribute is absent \(or null\)$",
    ):
        prepare(insert, write_preparation_of(_CUSTOMER))


@pytest.mark.parametrize(
    ("prepare", "refusal"),
    [
        (prepare_typed_write, WriteRejectedError),
        (prepare_wire_write, InstructionRejectedError),
    ],
    ids=_LANES,
)
@pytest.mark.parametrize("mutation", ["delete", "amend"])
def test_a_key_an_existing_object_is_addressed_by_is_never_a_marker(
    prepare: Callable[..., object], refusal: type[Exception], mutation: str
) -> None:
    row: dict[str, object] = {"id": {"computed": "maxPlusOne"}}
    if mutation == "amend":
        row["name"] = "Ada"
    instruction = KeyedWriteInstruction(
        mutation,  # pyright: ignore[reportArgumentType]
        "Attendee",
        (row,),
    )
    with pytest.raises(refusal, match=r"Attendee\.id: ") as refused:
        prepare(instruction, write_preparation_of(_PK_MAX))
    assert "type-mismatch" in getattr(refused.value, "rule", "")
