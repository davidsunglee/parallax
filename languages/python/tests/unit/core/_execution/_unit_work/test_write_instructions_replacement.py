"""A replacement states its object's complete writable state on both lanes.

Keyed, target, and predicate-selected replacements share one completion: an
omitted nullable member is written as null, an omitted ``many`` as its empty
collection, and an omitted required member refused, judged in declaration
order beside the key that addresses the object. Omitting a member and stating
it null are the same replacement.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

import pytest

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._unit_work import instructions as wi
from parallax.core.base import Int32
from parallax.core.entity._model import model_of
from parallax.core.unit_work import WriteRejectedError
from parallax.core.write_plan.managed_row import ManagedRow, named_members
from tests._support.write_preparation import write_preparation_of

_NS = "replacement.completion"


class _Spot(ValueObject):
    code: Attr[str]


class Ledger(Entity, table="ledger", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]
    note: Attr[str | None]
    tags: Attr[tuple[str, ...]]
    spot: Attr[_Spot | None]


class Ledgered(Entity, table="ledgered", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]
    note: Attr[str | None]
    tags: Attr[tuple[str, ...]]
    spot: Attr[_Spot | None]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Sealed(Entity, table="sealed", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]
    tags: Attr[tuple[str, ...]] = attr(read_only=True)


class Sealeded(Entity, table="sealeded", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]
    tags: Attr[tuple[str, ...]] = attr(read_only=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_MODEL: Final = model_of(DomainModel(Ledger, Ledgered, Sealed, Sealeded))
_COMPLETED: Final[Mapping[str, object]] = {
    "id": 1,
    "owner": "A",
    "note": None,
    "tags": (),
    "spot": None,
}


def _keyed(row: Mapping[str, object]) -> wi.WriteInstruction:
    return wi.KeyedWriteInstruction("replace", f"{_NS}.Ledger", (row,))


def _target(row: Mapping[str, object]) -> wi.WriteInstruction:
    return wi.TargetWriteInstruction("replace", f"{_NS}.Ledgered", row, if_version=3)


def _predicate(row: Mapping[str, object]) -> wi.WriteInstruction:
    node = predicate_algebra.deserialize({"eq": {"path": f"{_NS}.Ledger.id", "value": 1}})
    return wi.PredicateWriteInstruction(
        "replace", wi.PredicateSelection(f"{_NS}.Ledger", node), row=row
    )


def _row(prepared: object) -> ManagedRow:
    if isinstance(prepared, wi.PreparedKeyedInstruction):
        (row,) = prepared.rows
        return row
    assert isinstance(prepared, wi.PreparedTargetInstruction | wi.PreparedPredicateInstruction)
    return prepared.row


_FORMS: Final = pytest.mark.parametrize(
    ("form", "addressed"),
    [
        pytest.param(_keyed, True, id="keyed"),
        pytest.param(_target, True, id="target"),
        pytest.param(_predicate, False, id="predicate"),
    ],
)
_LANES: Final = pytest.mark.parametrize(
    ("prepare", "empty"),
    [
        pytest.param(wi.prepare_typed_write, (), id="typed"),
        pytest.param(wi.prepare_wire_write, [], id="wire"),
    ],
)

type _Form = Callable[[Mapping[str, object]], wi.WriteInstruction]
type _Prepare = Callable[..., Any]


def _expected(addressed: bool) -> Mapping[str, object]:
    # A predicate selects its rows, so the key it states is judged and dropped.
    if addressed:
        return _COMPLETED
    return {name: value for name, value in _COMPLETED.items() if name != "id"}


@_FORMS
@_LANES
def test_an_omitted_nullable_member_is_written_null_and_an_omitted_many_empty(
    form: _Form, addressed: bool, prepare: _Prepare, empty: object
) -> None:
    del empty
    prepared = prepare(form({"id": 1, "owner": "A"}), write_preparation_of(_MODEL))

    assert named_members(_row(prepared)) == _expected(addressed)


@_FORMS
@_LANES
def test_stating_a_member_null_or_empty_is_the_same_replacement_as_omitting_it(
    form: _Form, addressed: bool, prepare: _Prepare, empty: object
) -> None:
    stated = {"id": 1, "owner": "A", "note": None, "tags": empty, "spot": None}

    prepared = prepare(form(stated), write_preparation_of(_MODEL))

    assert named_members(_row(prepared)) == _expected(addressed)


@_FORMS
@_LANES
def test_an_omitted_required_member_is_refused(
    form: _Form, addressed: bool, prepare: _Prepare, empty: object
) -> None:
    del addressed, empty
    with pytest.raises(WriteRejectedError, match=r"owner: a replacement states every") as refused:
        prepare(form({"id": 1, "note": "n"}), write_preparation_of(_MODEL))

    assert refused.value.rule == "write-required-attribute-missing"


@_FORMS
@_LANES
def test_a_required_member_stated_null_is_refused_as_an_assignment(
    form: _Form, addressed: bool, prepare: _Prepare, empty: object
) -> None:
    del addressed, empty
    with pytest.raises(wi.WriteInstructionError, match=r"owner: required attribute is absent"):
        prepare(form({"id": 1, "owner": None}), write_preparation_of(_MODEL))


def _sealed_keyed(row: Mapping[str, object]) -> wi.WriteInstruction:
    return wi.KeyedWriteInstruction("replace", f"{_NS}.Sealed", (row,))


def _sealed_target(row: Mapping[str, object]) -> wi.WriteInstruction:
    return wi.TargetWriteInstruction("replace", f"{_NS}.Sealeded", row, if_version=3)


def _sealed_predicate(row: Mapping[str, object]) -> wi.WriteInstruction:
    node = predicate_algebra.deserialize({"eq": {"path": f"{_NS}.Sealed.id", "value": 1}})
    return wi.PredicateWriteInstruction(
        "replace", wi.PredicateSelection(f"{_NS}.Sealed", node), row=row
    )


_SEALED_FORMS: Final = pytest.mark.parametrize(
    ("form", "addressed"),
    [
        pytest.param(_sealed_keyed, True, id="keyed"),
        pytest.param(_sealed_target, True, id="target"),
        pytest.param(_sealed_predicate, False, id="predicate"),
    ],
)


@_SEALED_FORMS
@_LANES
def test_a_replacement_leaves_an_omitted_read_only_collection_unstated(
    form: _Form, addressed: bool, prepare: _Prepare, empty: object
) -> None:
    del empty
    prepared = prepare(form({"id": 1, "owner": "A"}), write_preparation_of(_MODEL))

    expected = {"id": 1, "owner": "A"} if addressed else {"owner": "A"}
    assert named_members(_row(prepared)) == expected


def test_a_typed_keyed_replacement_reads_a_held_read_only_collection_as_unstated() -> None:
    preparation = write_preparation_of(_MODEL)
    target = _MODEL.entity(Sealed.identity)
    assert target is not None
    entry = preparation.entity(target.identity)
    values = Sealed(id=1, owner="A", tags=("t",)).__parallax_row_values__(
        entry.selection.members.shape, target.identity
    )

    prepared = wi.prepare_typed_keyed_write(
        preparation, "replace", target, values=values, valid_from=None, until=None
    )

    assert named_members(_row(prepared)) == {"id": 1, "owner": "A"}


@_LANES
@pytest.mark.parametrize("mutation", ["replace", "amend"])
def test_an_earlier_rows_value_failure_wins_over_a_later_rows_name_failure(
    prepare: _Prepare, empty: object, mutation: wi.KeyedMutation
) -> None:
    del empty
    first = {"id": 1, "owner": 7}
    second = {"id": 2, "owner": "B", "bogus": 1}
    with pytest.raises(ValueError, match=r"Ledger\.owner: ") as refused:
        prepare(
            wi.KeyedWriteInstruction(mutation, f"{_NS}.Ledger", (first, second)),
            write_preparation_of(_MODEL),
        )

    assert "bogus" not in str(refused.value)


class Meter(
    Entity,
    table="meter",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]


class Gauge(Meter, namespace=_NS, inheritance=ConcreteSubtype(tag_value="gauge")):
    span: Attr[int | None]


_FAMILY: Final = model_of(DomainModel(Meter, Gauge))


def _gauge_target() -> Any:
    target = _FAMILY.entity(Gauge.identity)
    assert target is not None
    return target


def test_a_typed_keyed_replacement_of_a_subtype_states_its_whole_family_state() -> None:
    preparation = write_preparation_of(_FAMILY)
    target = _gauge_target()
    entry = preparation.entity(target.identity)
    values = Gauge(id=1, owner="A", span=2).__parallax_row_values__(
        entry.selection.members.shape, target.identity
    )

    prepared = wi.prepare_typed_keyed_write(
        preparation, "replace", target, values=values, valid_from=None, until=None
    )

    assert named_members(_row(prepared)) == {"id": 1, "owner": "A", "span": 2}


def test_a_typed_keyed_amendment_of_a_subtype_judges_its_explicit_assignments() -> None:
    preparation = write_preparation_of(_FAMILY)
    target = _gauge_target()
    key = preparation.entity(target.identity).key

    prepared = wi.prepare_typed_keyed_write(
        preparation,
        "amend",
        target,
        pairs=((key, 1),),
        members=lambda: {"span": 3},
        valid_from=None,
        until=None,
    )

    assert named_members(_row(prepared)) == {"id": 1, "span": 3}


def test_a_typed_keyed_write_of_an_existing_object_opens_no_row() -> None:
    with pytest.raises(ValueError, match="opens a row"):
        wi.prepare_typed_keyed_write(
            write_preparation_of(_FAMILY), "insert", _gauge_target(), valid_from=None, until=None
        )
