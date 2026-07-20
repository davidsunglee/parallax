"""Unit pins for the ``_where`` verb family's own build-time surface (COR-3
Phase 8 increment 5; python.md §5): the ``.set(...)`` assignment DSL
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

import mirrored_models as mm
import snapshot_models as sm
import value_object_models as vom
from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field
from parallax.core.entity import ModelCopyError
from parallax.core.entity.expressions import AttributeAssignment
from parallax.core.entity.value_object import ValueObject, VoField
from parallax.core.temporal_read import LATEST

pytestmark = pytest.mark.unit

_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A small LOCAL temporal (audit-only) entity, unregistered elsewhere — the
# `.as_of()` / `.history()` bare-statement-guard tests need a real temporal
# class, and no shared test-fixture entity mirror declares one (mirroring the
# same local-class pattern `test_snapshot_wrap.py`'s own `_WrapTemporalRoot`
# uses).
class _WhereTemporalLedger(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_temporal_ledger",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    amount: Attr[Decimal] = Field(type="decimal(18,2)")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


# A small LOCAL non-temporal entity mirroring `models/shipment.yaml`'s own
# shape — the "required top-level value object missing" exemplar
# (`destination` is `nullable: false`, unlike every other value-object owner
# in the corpus) — confirmation-pass residual B's own typed-path fixture
# (round 2, `inheritance/__init__.py:667`). D-21 has since installed
# `vo_models.Shipment`, which carries that same non-nullable `destination`; this
# fixture stays local because it ALSO pairs it with the nullable scalar `note`,
# giving one fixture both the refusal and the scalar-None accept counterpart.
class _WhereShipmentDestination(ValueObject, frozen=True):
    street: Attr[str] = VoField(type="string")
    city: Attr[str] = VoField(type="string")


class _WhereShipment(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_shipment", namespace="parallax.compatibility", mutability="transactional"
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    note: Attr[str | None] = Field(type="string", max_length=64, nullable=True, default=None)
    destination: Attr[_WhereShipmentDestination] = Field()


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
    # D-33: `geo`/`phones` stay unset (relying on their own declared
    # defaults), so `to_document` omits them entirely rather than binding an
    # explicit `null`/`[]`.
    address = vom.Address(street="1 Aurora Ave", city="Oslo")
    assignment = vom.Customer.address.set(address)
    assert assignment.value == {"street": "1 Aurora Ave", "city": "Oslo"}


def test_set_on_a_many_value_object_member_serializes_to_a_document_list() -> None:
    # D-33: neither `Tag` sets its own optional `detail`/`details`.
    tags = (sm.Tag(label="a"), sm.Tag(label="b"))
    assignment = sm.SnapOrderStatus.tags.set(tags)
    assert assignment.value == [{"label": "a"}, {"label": "b"}]


def test_set_on_a_scalar_passes_a_plain_literal_through_unchanged() -> None:
    assignment = sm.SnapOrderStatus.code.set("X-1")
    assert assignment.value == "X-1"


def test_set_on_a_primary_key_attribute_raises() -> None:
    # Finding 3's own repro: `Person.id.set(2)` must be rejected at `.set()`
    # BUILD time (`python.md:667-676`), the SAME classification `model_copy`'s
    # own assignability guard raises for a primary-key `update=` key.
    with pytest.raises(ModelCopyError, match="primary-key fields may not be assigned"):
        mm.Person.id.set(2)


def test_set_on_a_framework_owned_version_attribute_raises() -> None:
    with pytest.raises(ModelCopyError, match="framework-owned fields"):
        mm.Account.version.set(5)


def test_set_on_a_scalar_with_a_mismatched_type_raises() -> None:
    with pytest.raises(ModelCopyError, match="does not match the declared type"):
        mm.Person.name.set(42)


# --------------------------------------------------------------------------- #
# Confirmation-pass residual P3 -- a VALUE-OBJECT-targeted `.set(...)`'s VALUE  #
# is validated against its declared composite too (the prior round's check     #
# validated only scalar targets, silently accepting `Customer.address.set(42)` #
# and binding `42` as the document): a non-document value is rejected with the #
# SAME wording style the scalar branch above uses; a well-formed document      #
# stays structurally accepted (D-26 -- a value-object target is not itself     #
# rejected; `test_set_on_a_top_level_value_object_serializes_to_its_document`  #
# above already pins the well-formed-`ValueObject`-instance shape of this SAME #
# accept branch). `test_write_instructions.py`'s own `test_member_name_       #
# honesty_...value_object_assignment` pins are the serialized/engine-path      #
# half of this SAME shared check.                                              #
# --------------------------------------------------------------------------- #
def test_set_on_a_value_object_with_a_non_document_value_raises() -> None:
    with pytest.raises(ModelCopyError, match="does not match the declared type"):
        vom.Customer.address.set(42)  # type: ignore[arg-type]


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


# --------------------------------------------------------------------------- #
# Confirmation-pass residual B (round 2, `inheritance/__init__.py:667`): a     #
# `None` assignment's nullability-aware handling through the TYPED `.set(...)` #
# path -- `test_write_instructions.py`'s own `test_member_name_honesty_       #
# ..._of_none` pins are the serialized/engine-path half of this SAME shared    #
# check.                                                                       #
# --------------------------------------------------------------------------- #
def test_set_on_a_non_nullable_value_object_with_none_raises() -> None:
    # `_WhereShipment.destination` is `nullable: false` (`models/
    # shipment.yaml`'s own "required top-level value object missing"
    # exemplar) -- before the fix, the VO branch's `if value is not None:`
    # guard skipped validation entirely for a `None` assignment, regardless
    # of nullability.
    with pytest.raises(ModelCopyError, match="required value object is absent"):
        _WhereShipment.destination.set(None)


def test_set_on_a_nullable_value_object_with_none_is_accepted() -> None:
    # `vom.Customer.address` is `nullable: true` -- an explicit `None` stays
    # a legal clearing assignment.
    assignment = vom.Customer.address.set(None)
    assert assignment.value is None


def test_set_on_a_non_nullable_scalar_with_none_raises() -> None:
    # The scalar branch's own extension of residual B: a non-nullable
    # scalar assigned `None` must be rejected too -- before the fix,
    # `value is not None and not _type_matches(...)` let a `None` value
    # bypass validation entirely, the SAME class of bug as the VO branch.
    with pytest.raises(ModelCopyError, match="required attribute is absent"):
        _WhereShipment.name.set(None)


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
    statement = _WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).as_of(processing=LATEST)
    assert statement.is_bare() is False


def test_is_bare_false_with_history() -> None:
    statement = _WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).history("processing")
    assert statement.is_bare() is False


def test_is_bare_false_with_include() -> None:
    statement = sm.SnapOrder.where(sm.SnapOrder.id == 1).include(sm.SnapOrder.items)
    assert statement.is_bare() is False


def test_is_bare_false_with_narrow() -> None:
    statement = sm.Animal.where(sm.Animal.name == "Rex").narrow(sm.Dog)
    assert statement.is_bare() is False
