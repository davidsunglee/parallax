"""An insert's one admission: Typed and Wire openings judged in member order
through the model's authoring plan, buffered as the positional Managed Row the
flush writes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import cast

import pytest

from parallax.core import (
    Attr,
    DomainModel,
    Entity,
    Int32,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core._execution._unit_work import instructions
from parallax.core._execution._unit_work.instructions import (
    InstructionRejectedError,
    KeyedWriteInstruction,
    PreparedKeyedInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.read_delivery._page import ABSENT
from parallax.core.unit_work import WriteRejectedError
from parallax.core.write_plan.managed_row import ManagedRow
from parallax.snapshot import TxnContext
from parallax.snapshot._publication._wire import WireEntity
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests._support.write_preparation import write_preparation_of
from tests.unit._transact_support import FIXED, db_for
from tests.unit.snapshot._handle._vessel_model import VESSEL, Ferry

_NS = "insert.admission"


class Mark(ValueObject):
    code: Attr[str]
    note: Attr[str | None]
    tags: Attr[tuple[str, ...]]


class Parcel(Entity, table="parcel", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    weight: Attr[Decimal] = attr(precision=6, scale=2)
    label: Attr[str]
    count: Attr[int] = attr(type=Int32)
    memo: Attr[str | None]
    sizes: Attr[tuple[int, ...]]
    mark: Attr[Mark | None]
    marks: Attr[tuple[Mark, ...]]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Reading(TxTemporal, table="reading", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    level: Attr[int]


_MODEL = DomainModel(Parcel, Reading)
_META = model_of(_MODEL)
_PARCEL = "insert.admission.Parcel"
# Member order: the Attributes in declaration order, then the Value Objects.
_MEMBERS = ("id", "weight", "label", "count", "memo", "sizes", "version", "mark", "marks")


def _parcel(**overrides: object) -> Parcel:
    values: dict[str, object] = {"id": 1, "weight": Decimal("2.50"), "label": "L", "count": 3}
    values.update(overrides)
    return Parcel(**values)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"id": 1, "weight": "2.50", "label": "L", "count": 3}
    payload.update(overrides)
    return payload


def _buffered(write: Callable[[TxnContext], object], model: DomainModel = _MODEL) -> ManagedRow:
    """The one row the opening ``write`` prepares, as its verb buffers it."""
    prepared: list[PreparedKeyedInstruction] = []

    def recorded[**P](
        prepare: Callable[P, PreparedKeyedInstruction],
    ) -> Callable[P, PreparedKeyedInstruction]:
        def record(*args: P.args, **kwargs: P.kwargs) -> PreparedKeyedInstruction:
            prepared.append(prepare(*args, **kwargs))
            return prepared[-1]

        return record

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            instructions, "prepare_typed_insert", recorded(instructions.prepare_typed_insert)
        )
        patch.setattr(
            instructions, "prepare_wire_insert", recorded(instructions.prepare_wire_insert)
        )
        db_for(model, ScriptedAdapter(Transact(Write()))).transact(write)
    ((row,),) = (instruction.rows for instruction in prepared)
    return row


def _stated(row: ManagedRow) -> dict[str, object]:
    return {_MEMBERS[position]: cell for position, cell in row.stated_cells()}


def _constructed(values: Mapping[str, object]) -> Parcel:
    """A ``Parcel`` holding exactly ``values``, admitted by nothing."""
    return Parcel.model_construct(None, **values)


type _Opening = Callable[[dict[str, object]], Callable[[TxnContext], object]]

# Each public opening verb beside its spelling of `Parcel.weight`.
_LANES: tuple[tuple[_Opening, object], ...] = (
    (lambda values: lambda tx: tx.insert(_constructed(values)), Decimal("2.50")),
    (lambda values: lambda tx: tx.wire.insert("Parcel", values), "2.50"),
)
_LANE_IDS = ("typed", "wire")


# --------------------------------------------------------------------------- #
# The positional row an opening buffers.                                       #
# --------------------------------------------------------------------------- #
def test_a_typed_opening_packs_its_stated_members_in_member_order() -> None:
    row = _buffered(lambda tx: tx.insert(_parcel()))
    # The nullable members it never set stay unstated; each omitted `many` is
    # its empty collection; the framework-owned version is the framework's.
    assert _stated(row) == {
        "id": 1,
        "weight": Decimal("2.50"),
        "label": "L",
        "count": 3,
        "sizes": (),
        "marks": (),
    }
    assert len(row.cells) == row.presence.bit_count() == 6


def test_a_wire_opening_reads_its_payload_in_member_order_whatever_its_key_order() -> None:
    payload = dict(reversed(list(_payload(memo=None).items())))
    row = _buffered(lambda tx: tx.wire.insert("Parcel", payload))
    assert list(_stated(row)) == ["id", "weight", "label", "count", "memo", "sizes", "marks"]
    assert _stated(row)["weight"] == Decimal("2.50")


@pytest.mark.parametrize(("write", "weight"), _LANES, ids=_LANE_IDS)
def test_an_omitted_nullable_member_is_unstated_and_a_null_one_is_stated(
    write: _Opening, weight: object
) -> None:
    base: dict[str, object] = {"id": 1, "weight": weight, "label": "L", "count": 3}
    omitted = _buffered(write(base))
    stated = _buffered(write({**base, "memo": None, "mark": None}))
    assert "memo" not in _stated(omitted) and "mark" not in _stated(omitted)
    assert _stated(stated)["memo"] is None and _stated(stated)["mark"] is None
    assert stated.presence == omitted.presence | (1 << 4) | (1 << 7)


def test_a_wide_opening_stating_every_member_holds_one_cell_per_member() -> None:
    row = _buffered(
        lambda tx: tx.wire.insert(
            "Parcel",
            _payload(memo="m", sizes=[1, 2], mark={"code": "A", "tags": []}, marks=[]),
        )
    )
    # Every member but the framework's own version.
    assert row.presence == row.selection.full_presence & ~(1 << 6)
    assert len(row.cells) == 8


def test_a_nested_occurrence_is_owned_in_its_full_width_positional_form() -> None:
    mark: dict[str, object] = {"code": "A", "tags": ["x"]}
    tags = cast("list[object]", mark["tags"])
    row = _buffered(lambda tx: tx.wire.insert("Parcel", _payload(mark=mark)))
    tags.append("y")
    mark["code"] = "B"
    # The omitted nullable `note` keeps the Entity State absence marker; the
    # authored containers are detached.
    assert _stated(row)["mark"] == ("A", ABSENT, ("x",))


def test_a_typed_value_object_is_read_into_the_same_positional_form() -> None:
    row = _buffered(lambda tx: tx.insert(_parcel(mark=Mark(code="A", tags=("x",)))))
    assert _stated(row)["mark"] == ("A", ABSENT, ("x",))


def test_an_inherited_family_member_order_is_read_positionally() -> None:
    row = _buffered(lambda tx: tx.insert(Ferry(id=4, name="Ada", berths=12)), VESSEL)
    shape = row.selection.members.shape.members
    assert [shape[position].name for position in row.positions()] == ["id", "name", "berths"]
    assert row.cells == (4, "Ada", 12)


def test_an_instance_of_another_models_class_is_read_by_name() -> None:
    # Same Entity Identity, its own declaration ordering the members otherwise:
    # its class is no class this model proved positional, so its row is read
    # through the codec by name, into the same positional row.
    class Parcel(Entity, table="parcel", namespace=_NS):
        label: Attr[str]
        id: Attr[int] = attr(primary_key=True)
        count: Attr[int] = attr(type=Int32)
        weight: Attr[Decimal] = attr(precision=6, scale=2)
        memo: Attr[str | None]
        sizes: Attr[tuple[int, ...]]
        mark: Attr[Mark | None]
        marks: Attr[tuple[Mark, ...]]
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)

    foreign = _buffered(
        lambda tx: tx.insert(Parcel(id=1, weight=Decimal("2.50"), label="L", count=3))
    )
    assert foreign == _buffered(lambda tx: tx.insert(_parcel()))


# --------------------------------------------------------------------------- #
# What the flush writes from that row.                                         #
# --------------------------------------------------------------------------- #
def _flushed(write: Callable[[TxnContext], object]) -> dict[str, object]:
    port = ScriptedAdapter(Transact(Write()))
    db_for(_MODEL, port).transact(write)
    (call,) = [call for call in port.calls if isinstance(call, WriteCall)]
    columns = call.sql.split("(", 1)[1].split(")", 1)[0].split(", ")
    return dict(zip(columns, call.binds, strict=True))


def test_an_opening_stamps_the_initial_version_over_any_carried_one() -> None:
    hydrated = Parcel.model_construct(
        id=1, weight=Decimal("2.50"), label="L", count=3, sizes=(), marks=(), version=9
    )
    assert _flushed(lambda tx: tx.insert(hydrated))["version"] == 1


def test_a_temporal_opening_stamps_its_milestone_endpoints() -> None:
    binds = _flushed(lambda tx: tx.insert(Reading(id=5, level=2)))
    assert binds == {"id": 5, "level": 2, "in_z": FIXED, "out_z": INFINITY}


def test_a_wire_opening_answers_its_node_in_member_order() -> None:
    nodes: list[WireEntity] = []

    def fn(tx: TxnContext) -> None:
        nodes.append(tx.wire.insert("Parcel", dict(reversed(list(_payload().items())))))

    db_for(_MODEL, ScriptedAdapter(Transact(Write()))).transact(fn)
    (node,) = nodes
    assert list(node) == ["id", "weight", "label", "count", "sizes", "marks"]
    assert list(cast("list[object]", node["sizes"])) == []
    assert list(cast("list[object]", node["marks"])) == []


# --------------------------------------------------------------------------- #
# U1: a complete row is judged in member order, names before values, one row  #
# at a time.                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("write", "weight"), _LANES, ids=_LANE_IDS)
def test_an_earlier_missing_required_member_wins_over_a_later_invalid_value(
    write: _Opening, weight: object
) -> None:
    del weight
    values: dict[str, object] = {"id": 1, "label": "L", "count": 2**40}

    def fn(tx: TxnContext) -> None:
        with pytest.raises(
            WriteRejectedError, match=r"^Parcel\.weight: required attribute is absent \(or null\)$"
        ) as refused:
            write(values)(tx)
        assert refused.value.rule == "write-required-attribute-missing"

    port = ScriptedAdapter(Transact())
    db_for(_MODEL, port).transact(fn)
    assert not [call for call in port.calls if isinstance(call, WriteCall)]


def test_a_typed_earlier_invalid_value_wins_over_a_later_missing_required_member() -> None:
    def fn(tx: TxnContext) -> None:
        with pytest.raises(
            WriteRejectedError,
            match=r"^Parcel\.weight: value Decimal\('2\.505'\) does not match the declared "
            r"type Decimal\(precision=6, scale=2\)$",
        ):
            tx.insert(Parcel.model_construct(id=1, weight=Decimal("2.505"), count=3))

    db_for(_MODEL, ScriptedAdapter(Transact())).transact(fn)


def test_a_wire_payload_is_judged_in_member_order_not_its_key_order() -> None:
    # The payload states `count` first; `weight` comes first in member order.
    payload = {"count": 2**40, "label": "L", "weight": "2.505", "id": 1}

    def fn(tx: TxnContext) -> None:
        with pytest.raises(InstructionRejectedError, match=r"\.Parcel\.weight: ") as refused:
            tx.wire.insert("Parcel", payload)
        assert refused.value.rule.startswith("neutral-literal-")

    db_for(_MODEL, ScriptedAdapter(Transact())).transact(fn)


# Each preparation lane beside its spelling of a Decimal.
_PREPARERS: tuple[tuple[Callable[..., object], Callable[[str], object]], ...] = (
    (prepare_typed_write, Decimal),
    (prepare_wire_write, str),
)


@pytest.mark.parametrize(("prepare", "decimal"), _PREPARERS, ids=_LANE_IDS)
def test_a_rows_names_are_judged_before_its_values(
    prepare: Callable[..., object], decimal: Callable[[str], object]
) -> None:
    row = {"id": 1, "weight": decimal("2.505"), "label": "L", "count": 3, "bogus": 1}
    with pytest.raises(
        instructions.WriteInstructionError,
        match=r"Parcel: keyed write row names undeclared member\(s\) \['bogus'\]",
    ):
        prepare(KeyedWriteInstruction("insert", _PARCEL, (row,)), write_preparation_of(_META))


@pytest.mark.parametrize(("prepare", "decimal"), _PREPARERS, ids=_LANE_IDS)
def test_a_rows_declaration_order_decides_whatever_its_key_order(
    prepare: Callable[..., object], decimal: Callable[[str], object]
) -> None:
    row = {"count": 2**40, "id": 1, "label": "L", "weight": decimal("2.505")}
    with pytest.raises(ValueError, match=r"Parcel\.weight: ") as refused:
        prepare(KeyedWriteInstruction("insert", _PARCEL, (row,)), write_preparation_of(_META))
    assert "count" not in str(refused.value)


@pytest.mark.parametrize(("prepare", "decimal"), _PREPARERS, ids=_LANE_IDS)
@pytest.mark.parametrize(
    ("first", "refusal"),
    [
        ({"id": 1, "label": "L", "count": 2**40}, r"Parcel\.count: "),
        (
            {"id": 1, "label": "L", "count": 3, "weight": None},
            r"^Parcel\.weight: required attribute is absent \(or null\)$",
        ),
    ],
    ids=["invalid-value", "missing-required"],
)
def test_an_earlier_rows_value_failure_wins_over_a_later_rows_name_failure(
    prepare: Callable[..., object],
    decimal: Callable[[str], object],
    first: dict[str, object],
    refusal: str,
) -> None:
    first = {"weight": decimal("2.50"), **first}
    second = {"id": 2, "weight": decimal("2.50"), "label": "L", "count": 3, "bogus": 1}
    with pytest.raises(ValueError, match=refusal) as refused:
        prepare(
            KeyedWriteInstruction("insert", _PARCEL, (first, second)),
            write_preparation_of(_META),
        )
    assert "bogus" not in str(refused.value)


@pytest.mark.parametrize(("prepare", "decimal"), _PREPARERS, ids=_LANE_IDS)
def test_a_later_rows_failure_is_heard_once_every_earlier_row_is_admitted(
    prepare: Callable[..., object], decimal: Callable[[str], object]
) -> None:
    first = {"id": 1, "weight": decimal("2.50"), "label": "L", "count": 3}
    second = {"id": 2, "weight": decimal("2.50"), "count": 3}
    with pytest.raises(WriteRejectedError, match=r"^Parcel\.label: required attribute"):
        prepare(
            KeyedWriteInstruction("insert", _PARCEL, (first, second)),
            write_preparation_of(_META),
        )


# --------------------------------------------------------------------------- #
# What the buffered opening composes with, and what it never buffers.          #
# --------------------------------------------------------------------------- #
def test_an_amendment_of_a_pending_opening_folds_into_the_one_insert() -> None:
    def typed(tx: TxnContext) -> None:
        opened = _parcel()
        tx.insert(opened)
        tx.amend(opened.edit(label="M", memo="m"))

    def wire(tx: TxnContext) -> None:
        tx.wire.amend(tx.wire.insert("Parcel", _payload()), {"label": "M", "memo": "m"})

    for write in (typed, wire):
        binds = _flushed(write)
        assert (binds["label"], binds["memo"], binds["version"]) == ("M", "m", 1)


@pytest.mark.parametrize(
    ("marker", "refusal"),
    [
        ({"increment": 1}, r"a 'increment' marker is not recognized for insert planning$"),
        ({"computed": "next"}, r"'next' is not a recognized `computed` strategy \(m-pk-gen\)$"),
    ],
    ids=["wrong-context", "unknown-strategy"],
)
def test_a_wire_opening_refuses_an_unplannable_marker_before_buffering(
    marker: dict[str, object], refusal: str
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(
            instructions.WriteInstructionError,
            match=rf"^unsupported DB-computed marker on 'Parcel'\.count: {refusal}",
        ):
            tx.wire.insert("Parcel", _payload(count=marker))

    db_for(_MODEL, port).transact(fn)
    assert not [call for call in port.calls if isinstance(call, WriteCall)]


def test_a_registry_advance_cannot_fold_into_a_pending_opening() -> None:
    # The amendment plans an `increment` for the row it revises, and folding
    # it would make that the row the insert opens; the refusal leaves the
    # pending insert as it was.
    def fn(tx: TxnContext) -> None:
        opened = tx.wire.insert("Parcel", _payload())
        with pytest.raises(
            instructions.WriteInstructionError,
            match=r"^unsupported DB-computed marker on 'Parcel'\.count: a 'increment' marker is "
            r"not recognized for insert planning$",
        ):
            tx.wire.amend(opened, {"count": {"increment": 1}})

    assert _flushed(fn)["count"] == 3
