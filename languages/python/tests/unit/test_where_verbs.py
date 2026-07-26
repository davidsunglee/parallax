"""Unit pins for the ``_where`` verb family's own build-time surface
(python.md §5): the ``.set(...)`` assignment DSL
(``entity/expressions.py``) and the bare-statement guard
(``entity/statement.py``). The materializing/readless DISPATCH and the
rendered SQL are pinned in ``test_transaction_predicate_writes.py`` /
``test_write_lowering.py`` /
``test_engine.py``; these tests isolate the two build-time, entity-scoped
mechanisms every verb shares.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

import snapshot_models as sm
import value_object_models as vom
from parallax.core import Attr, Entity, MetamodelHub, TxTemporal, ValueObject, attr
from parallax.core.entity import AttributeAssignment
from parallax.core.temporal_read import LATEST, TX_TIME

pytestmark = pytest.mark.unit

_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A small LOCAL Transaction-Time-Only entity, unregistered elsewhere — the
# `.as_of()` / `.history()` bare-statement-guard tests need a real temporal
# class, and no shared test-fixture entity mirror declares one (mirroring the
# same local-class pattern `test_snapshot_wrap_values.py`'s own `_WrapTemporalRoot`
# uses).
class _WhereTemporalLedger(
    TxTemporal, table="where_temporal_ledger", namespace="parallax.compatibility"
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


# A small LOCAL non-temporal entity mirroring `models/shipment.yaml`'s own
# shape — the "required top-level value object missing" exemplar
# (`destination` is `nullable: false`, unlike every other value-object owner
# in the corpus) — the non-nullable value-object write fixture.
# `vo_models.Shipment` (installed separately) carries that same non-nullable
# `destination`; this
# fixture stays local because it ALSO pairs it with the nullable scalar `note`,
# giving one fixture both the refusal and the scalar-None accept counterpart.
class _WhereShipmentDestination(ValueObject):
    street: Attr[str]
    city: Attr[str]


class _WhereShipment(Entity, table="where_shipment", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    note: Attr[str | None] = attr(max_length=64)
    destination: Attr[_WhereShipmentDestination]


_WHERE_LEDGER = MetamodelHub(_WhereTemporalLedger)
_WHERE_SHIPMENT = MetamodelHub(_WhereShipment)


# --------------------------------------------------------------------------- #
# `.set(...)` — the typed assignment DSL.                                      #
# --------------------------------------------------------------------------- #
def test_set_on_a_scalar_attribute_builds_an_attribute_assignment() -> None:
    assignment = vom.Customer.name.set("Ada")
    assert isinstance(assignment, AttributeAssignment)
    assert str(assignment.attr) == "Customer.name"
    assert assignment.value == "Ada"


def test_set_string_matches_the_class_member_reference() -> None:
    assignment = vom.Customer.name.set("Ada")
    assert str(assignment) == "Customer.name"


def test_set_on_a_nested_value_object_path_raises() -> None:
    # Only a TOP-LEVEL attribute or value-object member is assignable — a
    # value object always binds its WHOLE document, never a nested path.
    with pytest.raises(TypeError, match="top-level attribute or value-object member"):
        vom.Customer.address.city.set("Oslo")  # type: ignore[attr-defined]


def test_set_on_a_top_level_value_object_serializes_to_its_document() -> None:
    # `geo` stays unset and omitted; multiplicity-many `phones` uses its empty
    # tuple default, serialized as the sole zero-element representation `[]`.
    address = vom.Address(street="1 Aurora Ave", city="Oslo")
    assignment = vom.Customer.address.set(address)
    assert assignment.value == {"street": "1 Aurora Ave", "city": "Oslo", "phones": []}


def test_set_on_a_many_value_object_member_serializes_to_a_document_list() -> None:
    # The optional one `detail` stays omitted; required-many `details` defaults empty.
    tags = (sm.Tag(label="a"), sm.Tag(label="b"))
    assignment = sm.SnapOrderStatus.tags.set(tags)
    assert assignment.value == [
        {"label": "a", "details": []},
        {"label": "b", "details": []},
    ]


def test_set_on_a_scalar_passes_a_plain_literal_through_unchanged() -> None:
    assignment = sm.SnapOrderStatus.code.set("X-1")
    assert assignment.value == "X-1"


# --------------------------------------------------------------------------- #
# A VALUE-OBJECT-targeted `.set(...)` renders its own value to a document and  #
# nothing more. Assignability, declared-type agreement, and required-member    #
# presence are model facts, and an Attribute Expression reaches no model: it   #
# carries structured member identities and performs no class lookup, so those  #
# rules are enforced where the model is, on the write path                     #
# (`test_write_instructions.py`).                                              #
# --------------------------------------------------------------------------- #
def test_set_on_a_value_object_with_a_well_formed_document_is_accepted() -> None:
    assignment = vom.Customer.address.set(
        {"street": "1 Aurora Ave", "city": "Oslo", "geo": None, "phones": []}
    )
    assert assignment.value == {
        "street": "1 Aurora Ave",
        "city": "Oslo",
        "geo": None,
        "phones": [],
    }


def test_set_on_a_nullable_value_object_with_none_is_accepted() -> None:
    # `vom.Customer.address` is `nullable: true` -- an explicit `None` stays
    # a legal clearing assignment.
    assignment = vom.Customer.address.set(None)
    assert assignment.value is None


def test_set_on_a_nullable_scalar_with_none_is_accepted() -> None:
    assignment = _WhereShipment.note.set(None)
    assert assignment.value is None


# --------------------------------------------------------------------------- #
# `Statement.is_bare()` — the single write-target guard every `_where` verb    #
# shares (python.md §5). Each non-default clause is tested independently, so  #
# the guard cannot be satisfied by an accidental combination.                  #
# --------------------------------------------------------------------------- #
def test_is_bare_true_for_a_plain_predicate_statement() -> None:
    statement = vom.Customer.where(vom.Customer.name == "Ada")
    assert statement.is_bare() is True


def test_is_bare_true_for_a_zero_predicate_find_all_statement() -> None:
    assert vom.Customer.where().is_bare() is True


def test_is_bare_false_with_order_by() -> None:
    statement = vom.Customer.where(vom.Customer.name == "Ada").order_by(vom.Customer.id.asc())
    assert statement.is_bare() is False


def test_is_bare_false_with_limit() -> None:
    statement = vom.Customer.where(vom.Customer.name == "Ada").limit(1)
    assert statement.is_bare() is False


def test_is_bare_false_with_distinct() -> None:
    # The spec's own enumeration omits `.distinct()`; the guard checks it
    # anyway (any non-default field), resolving that prose gap by
    # construction rather than a special case.
    statement = vom.Customer.where(vom.Customer.name == "Ada").distinct()
    assert statement.is_bare() is False


def test_is_bare_false_with_as_of() -> None:
    statement = _WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).as_of(tx_time=LATEST)
    assert statement.is_bare() is False


def test_is_bare_false_with_history() -> None:
    statement = _WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).history(TX_TIME)
    assert statement.is_bare() is False


def test_is_bare_false_with_include() -> None:
    statement = sm.SnapOrder.where(sm.SnapOrder.id == 1).include(sm.SnapOrder.items)
    assert statement.is_bare() is False


def test_is_bare_false_with_narrow() -> None:
    statement = sm.Animal.where(sm.Animal.name == "Rex").narrow(sm.Dog)
    assert statement.is_bare() is False
