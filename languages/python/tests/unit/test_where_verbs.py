"""Unit pins for the ``_where`` verb family's own build-time surface
(python.md §5): the ``.set(...)`` assignment DSL
(``entity/_expressions.py``) and the bare-statement guard
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

from _support import mirrored_models as mm
from _support import snapshot_models as sm
from _support import value_object_models as vom
from parallax.core import Attr, DomainModel, Entity, ModelCopyError, TxTemporal, ValueObject, attr
from parallax.core.entity import AttributeAssignment
from parallax.core.temporal_read import LATEST, TX_TIME

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


_WHERE_LEDGER = DomainModel(_WhereTemporalLedger)
_WHERE_SHIPMENT = DomainModel(_WhereShipment)


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
        vom.Customer.address.city.set("Oslo")


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
# Assignability and declared-type agreement are facts of the MEMBER, not of a   #
# whole model, and an Attribute Expression built from a class carries the       #
# member's own declared Metadata — so `.set(...)` reaches the SAME judgement    #
# (`~parallax.core.metamodel.judge_assignment`) the engine/serialized path      #
# reaches for a case-authored predicate-write assignment, and `model_copy`      #
# reaches for an edited copy. Only the resolution in front of it differs        #
# (`test_write_instructions.py` and `test_model_free_authoring.py` are the      #
# other callers). The rejection is spelled `ModelCopyError` because §5's        #
# assignment rules are one family with `model_copy`'s own `update=` rules (§3). #
# --------------------------------------------------------------------------- #
def test_set_on_a_primary_key_attribute_raises() -> None:
    with pytest.raises(ModelCopyError, match="primary-key fields may not be assigned"):
        mm.Person.id.set(2)


def test_set_on_a_framework_owned_version_attribute_raises() -> None:
    with pytest.raises(ModelCopyError, match="framework-owned fields"):
        mm.Account.version.set(5)


def test_set_on_a_scalar_with_a_mismatched_type_raises() -> None:
    # An assignment's value is the member's own, so the parameter refuses this
    # before anything runs; the suppression is what lets the runtime rule be
    # exercised, and the two must agree.
    with pytest.raises(ModelCopyError, match="does not match the declared type"):
        mm.Person.name.set(42)  # pyright: ignore[reportArgumentType]


def test_set_states_its_rule_from_the_descriptors_member_alone() -> None:
    # A class no model composed still judges its own assignments: the descriptor
    # carries the member's declared Metadata, which is every fact the rule reads.
    class _Uncomposed(Entity, table="uncomposed", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=8)

    assert _Uncomposed.label.set("x").value == "x"
    with pytest.raises(ModelCopyError, match="primary-key fields may not be assigned"):
        _Uncomposed.id.set(2)


def test_set_refuses_a_read_only_member() -> None:
    # The Python specification states the rule and the extracted judgement is
    # where it lands: read-only sits beside primary-key and framework-owned as an
    # unassignable target, on the typed path and the write boundary alike.
    class _Computed(Entity, table="computed", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        derived: Attr[str] = attr(max_length=8, read_only=True)

    with pytest.raises(ModelCopyError, match="read-only fields may not be assigned"):
        _Computed.derived.set("x")


# --------------------------------------------------------------------------- #
# A VALUE-OBJECT-targeted `.set(...)`'s value is validated against its declared #
# composite too: a non-document value is rejected with the scalar branch's own  #
# wording, while a well-formed document stays structurally accepted (assigning  #
# a value object is not itself a rejection).                                    #
# --------------------------------------------------------------------------- #
def test_set_on_a_value_object_with_a_non_document_value_raises() -> None:
    with pytest.raises(ModelCopyError, match="does not match the declared type"):
        vom.Customer.address.set(42)  # pyright: ignore[reportArgumentType]


def test_set_on_a_value_object_with_a_well_formed_document_is_accepted() -> None:
    # The one accepted spelling the value parameter costs: a Value Object member
    # equally takes its already-rendered document, which the rules still judge
    # and the member's declared type no longer admits.
    assignment = vom.Customer.address.set(
        {"street": "1 Aurora Ave", "city": "Oslo", "geo": None, "phones": []}  # pyright: ignore[reportArgumentType]
    )
    assert assignment.value == {
        "street": "1 Aurora Ave",
        "city": "Oslo",
        "geo": None,
        "phones": [],
    }


# --------------------------------------------------------------------------- #
# A `None` assignment is nullability-gated on both branches: it clears a        #
# nullable member and is refused for a required one, so neither branch lets a   #
# `None` bypass validation.                                                     #
# --------------------------------------------------------------------------- #
def test_set_on_a_non_nullable_value_object_with_none_raises() -> None:
    # A non-nullable member's declared type excludes `None`, so the parameter
    # refuses the clearing assignment the runtime rule refuses too.
    with pytest.raises(ModelCopyError, match="required value object is absent"):
        _WhereShipment.destination.set(None)  # pyright: ignore[reportArgumentType]


def test_set_on_a_nullable_value_object_with_none_is_accepted() -> None:
    # `vom.Customer.address` is `nullable: true` -- an explicit `None` stays
    # a legal clearing assignment.
    assignment = vom.Customer.address.set(None)
    assert assignment.value is None


def test_set_on_a_non_nullable_scalar_with_none_raises() -> None:
    with pytest.raises(ModelCopyError, match="required attribute is absent"):
        _WhereShipment.name.set(None)  # pyright: ignore[reportArgumentType]


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
