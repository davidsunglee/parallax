"""Unit pins for the ``_where`` verb family's own build-time surface (COR-3
Phase 8 increment 5; python.md §5): the ``.set(...)`` assignment DSL
(``entity/expressions.py``) and the bare-statement guard
(``entity/statement.py``). The materializing/readless DISPATCH and the
rendered SQL are pinned in ``test_transact.py`` / ``test_write_lowering.py`` /
``test_engine.py``; these tests isolate the two build-time, entity-scoped
mechanisms every verb shares.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import cast

import pytest

import mirrored_models as mm
import snapshot_models as sm
import value_object_models as vom
from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field
from parallax.core.db_port import DbPort
from parallax.core.entity import ModelCopyError, metamodel
from parallax.core.entity.expressions import AttributeAssignment
from parallax.core.temporal_read import LATEST
from parallax.core.unit_work import FixedClock
from parallax.snapshot.handle import Database, Transaction

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
    address = vom.Address(street="1 Aurora Ave", city="Oslo")
    assignment = vom.Customer.address.set(address)
    assert assignment.value == {
        "street": "1 Aurora Ave",
        "city": "Oslo",
        "geo": None,
        "phones": [],
    }


def test_set_on_a_many_value_object_member_serializes_to_a_document_list() -> None:
    tags = (sm.Tag(label="a"), sm.Tag(label="b"))
    assignment = sm.SnapOrderStatus.tags.set(tags)
    assert assignment.value == [
        {"label": "a", "detail": None, "details": []},
        {"label": "b", "detail": None, "details": []},
    ]


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


# --------------------------------------------------------------------------- #
# The BEHAVIORAL bare-statement rejection, end to end (round-6 confirmation-   #
# pass strengthening): `is_bare()` returning `False` above is NECESSARY but    #
# not SUFFICIENT on its own — an actual `tx.update_where` / `tx.delete_where`  #
# call handed a `.distinct()` statement must itself raise the rejection        #
# (`Transaction._buffer_predicate`, python.md §5), never merely be provable    #
# through the predicate alone. A port that raises on any I/O proves the        #
# guard runs BEFORE the connection is ever touched.                            #
# --------------------------------------------------------------------------- #
class _NoIoPort:
    """A minimal ``DbPort`` that raises if the connection is ever touched."""

    def execute(self, sql: str, binds: Sequence[object]) -> list[dict[str, object]]:
        raise AssertionError("no read expected — the bare-statement guard runs first")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError("no write expected — the bare-statement guard runs first")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(cast("DbPort", self))


_PERSON_META = metamodel([mm.Person, mm.Passport])


def test_update_where_rejects_a_distinct_statement_end_to_end() -> None:
    statement = mm.Person.where(mm.Person.id == 1).distinct()

    def fn(tx: Transaction) -> None:
        tx.update_where(statement, mm.Person.name.set("Ada"))

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(_NoIoPort(), _PERSON_META, clock=FixedClock(_FIXED)).transact(fn)


def test_delete_where_rejects_a_distinct_statement_end_to_end() -> None:
    statement = mm.Person.where(mm.Person.id == 1).distinct()

    def fn(tx: Transaction) -> None:
        tx.delete_where(statement)

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(_NoIoPort(), _PERSON_META, clock=FixedClock(_FIXED)).transact(fn)
