"""Unit pins for the ``_where`` verb family's own build-time surface
(python.md §5): the ``.set(...)`` assignment DSL
(``entity/_expressions.py``) and the mutation-compatibility guard
(``entity/_query.py``). The materializing/readless DISPATCH and the
rendered SQL are pinned in ``test_transaction_predicate_writes.py`` /
``test_write_lowering.py`` /
``test_engine.py``; these tests isolate the two build-time, entity-scoped
mechanisms every verb shares.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest

from _support import mirrored_models as mm
from _support import snapshot_models as sm
from _support import value_object_models as vom
from parallax.core import (
    Attr,
    DomainModel,
    EditError,
    Entity,
    FindQuery,
    QueryDefinitionError,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity import AttributeAssignment, AttributeExpr
from parallax.core.entity._query import mutation_selection
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeLocation,
    EntityIdentity,
    EntityLocation,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeLocation,
    ValueObjectIdentity,
)
from parallax.core.predicate import All
from parallax.core.temporal_read import LATEST, TX_TIME

_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A small LOCAL Transaction-Time-Only entity, unregistered elsewhere — the
# `.as_of()` / `.history()` mutation-compatibility tests need a real temporal
# class, and no shared test-fixture entity mirror declares one (mirroring the
# same local-class pattern `test_snapshot_wrap_values.py`'s own `_WrapTemporalRoot`
# uses).
class _WhereTemporalLedger(
    TxTemporal,
    table="where_temporal_ledger",
    name="WhereTemporalLedger",
    namespace="parallax.compatibility",
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


class _WhereShipment(
    Entity, table="where_shipment", name="WhereShipment", namespace="parallax.compatibility"
):
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
    assert str(assignment.attr) == "parallax.compatibility.Customer.name"
    assert assignment.value == "Ada"


def test_set_string_matches_the_class_member_reference() -> None:
    assignment = vom.Customer.name.set("Ada")
    assert str(assignment) == "parallax.compatibility.Customer.name"


def test_set_on_a_nested_value_object_path_raises() -> None:
    # Only a TOP-LEVEL attribute or value-object member is assignable — a
    # value object always binds its WHOLE document, never a nested path. The
    # refusal carries the assignment family every other `.set(...)` refusal does,
    # so one `except` clause covers the whole surface.
    with pytest.raises(EditError, match="top-level attribute or value-object member") as caught:
        vom.Customer.address.city.set("Oslo")
    violation = caught.value.violations[0]
    assert violation.code == "edit-nested-path"
    assert violation.member_name == "address.city"


def test_a_nested_path_refusal_locates_the_scalar_inside_the_occurrence() -> None:
    # The one member position only this surface can name: a keyword edit cannot
    # spell a path, so `edit(...)` never produces this code or this location.
    customer = EntityIdentity("parallax.compatibility", "Customer")
    with pytest.raises(EditError) as caught:
        vom.Customer.address.geo.country.set("NO")
    assert caught.value.violations[0].location == ValueObjectAttributeLocation(
        ValueObjectAttributeIdentity(ValueObjectIdentity(customer, ("address", "geo")), "country")
    )


def test_a_path_hopped_off_a_scalar_locates_at_the_scalar_it_hopped_from() -> None:
    # A hop resolves dynamically, so a path off a SCALAR builds as readily as
    # one off an occurrence. There is no member below a scalar to locate at, so
    # the refusal names the scalar the caller started from.
    with pytest.raises(EditError) as caught:
        mm.Person.name.city.set("Oslo")
    assert caught.value.violations[0].location == AttributeLocation(
        AttributeIdentity(EntityIdentity("parallax.compatibility", "Person"), "name")
    )


def test_a_nested_path_refusal_on_a_directly_built_expression_names_its_bare_entity() -> None:
    # An expression built directly carries no member, so the only Entity it
    # names is the bare string it was constructed with — which is what an
    # ownerless Entity Identity means. The refusal still fires: the built
    # assignment would have dropped the path and bound the whole occurrence.
    address: AttributeExpr[Any, Any] = AttributeExpr("Customer", "address")
    with pytest.raises(EditError) as caught:
        address.city.set("Oslo")
    assert caught.value.violations[0].location == EntityLocation(EntityIdentity(None, "Customer"))


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
# reaches for a case-authored predicate-write assignment, and `edit(...)`       #
# reaches for an edited copy. Only the resolution in front of it differs        #
# (`test_write_instructions.py` and `test_model_free_authoring.py` are the      #
# other callers). The rejection is spelled `EditError` because §5's assignment  #
# rules are one family with `edit(**changes)`'s own rules (§3), and one call    #
# names one target, so it always carries exactly one violation.                 #
# --------------------------------------------------------------------------- #
def test_set_on_a_primary_key_attribute_raises() -> None:
    with pytest.raises(EditError, match="primary-key fields may not be assigned"):
        mm.Person.id.set(2)


def test_set_on_a_framework_owned_version_attribute_raises() -> None:
    with pytest.raises(EditError, match="framework-owned fields"):
        mm.Account.version.set(5)


def test_set_on_a_scalar_with_a_mismatched_type_raises() -> None:
    # An assignment's value is the member's own, so the parameter refuses this
    # before anything runs; the suppression is what lets the runtime rule be
    # exercised, and the two must agree.
    with pytest.raises(EditError, match="does not match the declared type"):
        mm.Person.name.set(42)  # pyright: ignore[reportArgumentType]


def test_set_states_its_rule_from_the_descriptors_member_alone() -> None:
    # A class no model composed still judges its own assignments: the descriptor
    # carries the member's declared Metadata, which is every fact the rule reads.
    class _Uncomposed(Entity, table="uncomposed", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str] = attr(max_length=8)

    assert _Uncomposed.label.set("x").value == "x"
    with pytest.raises(EditError, match="primary-key fields may not be assigned"):
        _Uncomposed.id.set(2)


def test_set_refuses_a_read_only_member() -> None:
    # The Python specification states the rule and the extracted judgement is
    # where it lands: read-only sits beside primary-key and framework-owned as an
    # unassignable target, on the typed path and the write boundary alike.
    class _Computed(Entity, table="computed", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)
        derived: Attr[str] = attr(max_length=8, read_only=True)

    with pytest.raises(EditError, match="read-only fields may not be assigned"):
        _Computed.derived.set("x")


# --------------------------------------------------------------------------- #
# A VALUE-OBJECT-targeted `.set(...)`'s value is validated against its declared #
# composite too: a non-document value is rejected with the scalar branch's own  #
# wording, while a well-formed document stays structurally accepted (assigning  #
# a value object is not itself a rejection).                                    #
# --------------------------------------------------------------------------- #
def test_set_on_a_value_object_with_a_non_document_value_raises() -> None:
    with pytest.raises(EditError, match="does not match the declared type"):
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
    with pytest.raises(EditError, match="required value object is absent"):
        _WhereShipment.destination.set(None)  # pyright: ignore[reportArgumentType]


def test_set_on_a_nullable_value_object_with_none_is_accepted() -> None:
    # `vom.Customer.address` is `nullable: true` -- an explicit `None` stays
    # a legal clearing assignment.
    assignment = vom.Customer.address.set(None)
    assert assignment.value is None


def test_set_on_a_non_nullable_scalar_with_none_raises() -> None:
    with pytest.raises(EditError, match="required attribute is absent"):
        _WhereShipment.name.set(None)  # pyright: ignore[reportArgumentType]


def test_set_on_a_nullable_scalar_with_none_is_accepted() -> None:
    assignment = _WhereShipment.note.set(None)
    assert assignment.value is None


# --------------------------------------------------------------------------- #
# `mutation_selection(query)` — the single write-target guard every `_where`   #
# verb shares (python.md §5). Each clause is tested independently, so the      #
# guard cannot be satisfied by an accidental combination, and the accepted     #
# case proves the seam answers the target and predicate a write is built from. #
# --------------------------------------------------------------------------- #
def test_a_plain_predicate_query_is_mutation_compatible() -> None:
    query = vom.Customer.where(vom.Customer.name == "Ada")
    selection = mutation_selection(query)
    assert selection.target == vom.Customer.identity
    assert selection.predicate == (vom.Customer.name == "Ada").node


def test_an_explicitly_unfiltered_query_is_mutation_compatible() -> None:
    assert mutation_selection(vom.Customer.where(vom.Customer.all)).predicate == All()


def _refused(query: FindQuery[Any, Any], clause: str) -> None:
    with pytest.raises(QueryDefinitionError, match=clause) as caught:
        mutation_selection(query)
    assert caught.value.code == "query-not-mutation-compatible"


def test_an_ordered_query_is_not_mutation_compatible() -> None:
    _refused(
        vom.Customer.where(vom.Customer.name == "Ada").order_by(vom.Customer.id.asc()), "order_by"
    )


def test_a_limited_query_is_not_mutation_compatible() -> None:
    _refused(vom.Customer.where(vom.Customer.name == "Ada").limit(1), "limit")


def test_a_pinned_query_is_not_mutation_compatible() -> None:
    _refused(
        _WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).as_of(tx_time=LATEST), "as_of"
    )


def test_a_milestone_set_query_is_not_mutation_compatible() -> None:
    _refused(_WhereTemporalLedger.where(_WhereTemporalLedger.id == 1).history(TX_TIME), "history")


def test_an_including_query_is_not_mutation_compatible() -> None:
    _refused(sm.SnapOrder.where(sm.SnapOrder.id == 1).include(sm.SnapOrder.items), "include")


def test_a_narrowed_query_is_not_mutation_compatible() -> None:
    _refused(sm.Animal.where(sm.Animal.name == "Rex").narrow(sm.Dog), "narrow")


def test_every_carried_clause_is_named_at_once() -> None:
    # The refusal names what the query actually carries rather than the first
    # clause it happens to find, so a caller fixes the query in one pass.
    query = vom.Customer.where(vom.Customer.name == "Ada").order_by(vom.Customer.id.asc()).limit(1)
    with pytest.raises(QueryDefinitionError, match="order_by, limit"):
        mutation_selection(query)
