"""The inheritance class frontend: how ``inheritance=`` and Python subclassing
compose into the declared family position, and where each family rule fires.

The corpus no-drift proof lives in ``test_descriptor_no_drift.py``, which
compares the accepted Metamodel a class family forms against the one its corpus
model forms. What is pinned here is the frontend's own half: that the parent and
the role variant derive from the class hierarchy, that a temporal base selects
the family's axes on the root alone, and that a family-semantic violation which
stays *spellable* reaches ``DomainModel`` construction as the shared
formation-time ``inheritance-*`` issue rather than through a Python-only rule.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import BaseModel, PydanticUserError, ValidationError
from pydantic_core import PydanticUndefined

from _support import inheritance_models as im
from parallax.core import (
    MANY_TO_ONE,
    READ_ONLY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    EntityDefinitionError,
    Int32,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    inheritance,
    rel,
)
from parallax.core import AbstractSubtype as AbstractSubtypeRole
from parallax.core.entity import AttributeExpr, RelationshipPath
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AbstractSubtype,
    Column,
    EntityIdentity,
    EntityLocation,
    ExactEntityReference,
    PersistenceMode,
    Table,
    TemporalDimension,
)
from parallax.core.metamodel import ConcreteSubtype as AcceptedConcreteSubtype
from parallax.core.model_formation import MetamodelValidationError

_NS = "parallax.compatibility"


def _identity(name: str) -> EntityIdentity:
    return EntityIdentity(_NS, name)


def _issue_codes(error: MetamodelValidationError) -> list[str]:
    return [issue.code for issue in error.issues]


# --------------------------------------------------------------------------- #
# The declared family position: the variant is the role, and Python            #
# subclassing supplies the parent.                                             #
# --------------------------------------------------------------------------- #
def test_tph_root_owns_the_shared_table_and_the_tag_column() -> None:
    assert im.Payment.container == Table("payment")
    assert im.Payment.inheritance == AbstractRoot(TablePerHierarchy(tag_column="kind"))


def test_a_tph_concrete_subtype_is_tableless_and_carries_its_tag_value() -> None:
    assert im.CardPayment.container is None
    assert im.CardPayment.inheritance == AcceptedConcreteSubtype(
        ExactEntityReference(_identity("Payment")), "card"
    )


def test_a_tpcs_abstract_subtype_is_tableless_and_concretes_own_their_table() -> None:
    assert im.FinancialDocument.container is None
    assert im.FinancialDocument.inheritance == AbstractSubtype(
        ExactEntityReference(_identity("Document"))
    )
    assert im.Invoice.container == Table("invoice")
    assert im.Invoice.inheritance == AcceptedConcreteSubtype(
        ExactEntityReference(_identity("FinancialDocument")), None
    )


def test_a_temporal_base_on_a_family_root_supplies_the_axes_on_the_root_alone() -> None:
    # The root ALONE selects the temporal shape (the binding root-ownership
    # decision): its declaration carries both axes in canonical order plus the
    # reserved interval attributes, while a concrete subtype declares none of
    # its own — its family-effective temporality resolves through the root.
    assert [axis.dimension for axis in im.Rate.as_of_axes] == [
        TemporalDimension.VALID_TIME,
        TemporalDimension.TRANSACTION_TIME,
    ]
    assert [attribute.identity.name for attribute in im.Rate.attributes] == [
        "id",
        "amount",
        "validStart",
        "validEnd",
        "txStart",
        "txEnd",
    ]
    assert im.Rate.attributes[-1].storage == Column("out_z")
    assert im.DepositRate.as_of_axes == ()


# --------------------------------------------------------------------------- #
# What the grammar itself refuses, at class creation.                          #
# --------------------------------------------------------------------------- #
def test_a_domain_subclass_declaring_no_role_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError) as caught:

        class NoRole(im.Payment, namespace=_NS):  # pyright: ignore[reportUnusedClass] - class body must run to trigger the declaration-time rejection
            reference: Attr[str | None] = attr(max_length=32)

    assert caught.value.code == "entity-base-invalid"


def test_a_subclass_extending_a_temporal_base_beside_its_parent_is_rejected() -> None:
    # Temporal shape is family-wide and root-owned, so a family member never
    # names a second Parallax base — the grammar allows exactly one.
    with pytest.raises(EntityDefinitionError) as caught:

        class TwoBases(  # pyright: ignore[reportUnusedClass] - class body must run to trigger the declaration-time rejection
            im.Rate, Bitemporal, namespace=_NS, inheritance=ConcreteSubtype
        ):
            extra: Attr[str | None]

    assert caught.value.code == "entity-base-invalid"


def test_a_subtype_role_without_a_domain_parent_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError) as caught:

        class Orphan(  # pyright: ignore[reportUnusedClass] - class body must run to trigger the declaration-time rejection
            Entity, table="orphan", namespace=_NS, inheritance=ConcreteSubtype
        ):
            id: Attr[int] = attr(primary_key=True)

    assert caught.value.code == "entity-header-invalid-value"


# --------------------------------------------------------------------------- #
# What stays spellable and is therefore a formation-time family rule: the two  #
# frontends enforce the same accepted-model invariants, so these reach          #
# `DomainModel` construction as `inheritance-*` issues rather than a            #
# Python-only rejection.                                                        #
# --------------------------------------------------------------------------- #
def test_a_tph_descendant_declaring_a_table_is_a_formation_issue() -> None:
    class TphRoot(
        Entity,
        table="tph_root",
        namespace=_NS,
        inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
    ):
        id: Attr[int] = attr(primary_key=True)

    class TphLeaf(
        TphRoot, table="tph_leaf", namespace=_NS, inheritance=ConcreteSubtype(tag_value="leaf")
    ):
        note: Attr[str | None] = attr(max_length=32)

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(TphRoot, TphLeaf)
    assert _issue_codes(caught.value) == [inheritance.TPH_DESCENDANT_TABLE_FORBIDDEN]


def test_a_tpcs_root_declaring_a_table_is_a_formation_issue() -> None:
    class TpcsRoot(
        Entity,
        table="tpcs_root",
        namespace=_NS,
        inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
    ):
        id: Attr[int] = attr(primary_key=True)

    class TpcsLeaf(TpcsRoot, table="tpcs_leaf", namespace=_NS, inheritance=ConcreteSubtype):
        note: Attr[str | None] = attr(max_length=32)

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(TpcsRoot, TpcsLeaf)
    assert _issue_codes(caught.value) == [inheritance.TPCS_ABSTRACT_TABLE_FORBIDDEN]


def test_a_descendant_declaring_its_own_version_attribute_is_a_formation_issue() -> None:
    # Optimistic locking is root-owned and family-uniform (ADR 0027).
    class OvenRoot(Entity, namespace=_NS, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
        id: Attr[int] = attr(primary_key=True)

    class OvenLeaf(OvenRoot, table="oven_leaf", namespace=_NS, inheritance=ConcreteSubtype):
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(OvenRoot, OvenLeaf)
    assert _issue_codes(caught.value) == [inheritance.OPTIMISTIC_LOCKING_NOT_ROOT_OWNED]


def test_a_root_declaring_the_version_attribute_is_accepted() -> None:
    class ApplianceRoot(
        Entity, namespace=_NS, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)
    ):
        id: Attr[int] = attr(primary_key=True)
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)

    class ApplianceLeaf(
        ApplianceRoot, table="appliance_leaf", namespace=_NS, inheritance=ConcreteSubtype
    ):
        capacity: Attr[int | None] = attr(type=Int32)

    view = inheritance.view(model_of(DomainModel(ApplianceRoot, ApplianceLeaf)))
    position = view.entity(_identity("ApplianceLeaf"))
    assert position is not None
    assert position.applicable_attribute("version") is not None


# --------------------------------------------------------------------------- #
# Persistence is root-owned (m-inheritance "Persistence is root-owned"), which #
# makes what a class DECLARES the evidence that rule needs: a descendant that  #
# spells a mode at all is invalid, and absence on a descendant means inherit.  #
# --------------------------------------------------------------------------- #
class _Ledger(
    Entity,
    table="ledger",
    name="Ledger",
    namespace=_NS,
    persistence=READ_ONLY,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)


class _AuditLedger(
    _Ledger,
    name="AuditLedger",
    namespace=_NS,
    persistence=READ_ONLY,
    inheritance=ConcreteSubtype(tag_value="audit"),
):
    note: Attr[str | None] = attr(max_length=32)


class _SilentLedger(
    _Ledger, name="SilentLedger", namespace=_NS, inheritance=ConcreteSubtype(tag_value="silent")
):
    label: Attr[str | None] = attr(max_length=32)


def test_a_descendant_declares_exactly_the_mode_it_authored() -> None:
    assert _Ledger.persistence is PersistenceMode.READ_ONLY
    assert _AuditLedger.persistence is PersistenceMode.READ_ONLY
    assert _SilentLedger.persistence is None


def test_a_descendant_authored_persistence_makes_the_family_an_invalid_model() -> None:
    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(_Ledger, _AuditLedger)
    (issue,) = caught.value.issues
    assert issue.code == inheritance.PERSISTENCE_NOT_ROOT_OWNED
    assert issue.location == EntityLocation(_identity("AuditLedger"))
    assert issue.related == (EntityLocation(_identity("Ledger")),)


def test_a_descendant_that_declares_no_mode_inherits_the_root_owned_one() -> None:
    view = inheritance.view(model_of(DomainModel(_Ledger, _SilentLedger)))
    silent = view.entity(_identity("SilentLedger"))
    assert silent is not None
    assert silent.persistence is PersistenceMode.READ_ONLY


# --------------------------------------------------------------------------- #
# What a descendant inherits as a Pydantic field. Class access to a member      #
# yields its query-authoring seed, so the descriptor a base installs is a       #
# class attribute answering for every member name a descendant does not         #
# redeclare — and Pydantic reads a field's default off the class. What is       #
# pinned here is that a descendant's inherited field is the declaring class's   #
# own, for every member kind a family can contribute and at every depth.        #
# --------------------------------------------------------------------------- #
class _Badge(ValueObject):
    code: Attr[str | None]
    rank: Attr[int | None]


class _Fleet(Entity, table="fleet", name="Fleet", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)


class _Craft(
    Bitemporal,
    table="craft",
    name="Craft",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """Every member kind a family can contribute, declared on the root: a
    required Attribute, a nullable one, a required and a nullable Value Object
    occurrence, a many occurrence, a relationship, and — through the temporal
    base — four framework-owned endpoints."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    fleet_id: Attr[int | None]
    hull: Attr[_Badge]
    badge: Attr[_Badge | None]
    badges: Attr[tuple[_Badge, ...]]
    fleet: Rel[_Fleet | None] = rel(cardinality=MANY_TO_ONE, join=("fleet_id", "id"))


class _Winged(_Craft, name="Winged", namespace=_NS, inheritance=AbstractSubtypeRole):
    span: Attr[float | None]


class _Glider(_Winged, name="Glider", namespace=_NS, inheritance=ConcreteSubtype(tag_value="g")):
    tow_hook: Attr[bool | None]


def _collected(cls: type[BaseModel]) -> dict[str, tuple[object, bool]]:
    return {
        py_name: (field.default, field.is_required())
        for py_name, field in cls.__pydantic_fields__.items()
    }


_REQUIRED: tuple[object, bool] = (PydanticUndefined, True)
_CRAFT_FIELDS: dict[str, tuple[object, bool]] = {
    "id": _REQUIRED,
    "name": _REQUIRED,
    "fleet_id": (None, False),
    "hull": _REQUIRED,
    "badge": (None, False),
    "badges": ((), False),
    "valid_start": (None, False),
    "valid_end": (None, False),
    "tx_start": (None, False),
    "tx_end": (None, False),
}


def test_a_descendant_inherits_every_member_kind_as_the_declaring_classs_field() -> None:
    assert _collected(_Craft) == _CRAFT_FIELDS
    assert _collected(_Winged) == {**_CRAFT_FIELDS, "span": (None, False)}
    assert _collected(_Glider) == {
        **_CRAFT_FIELDS,
        "span": (None, False),
        "tow_hook": (None, False),
    }
    # A relationship is never a stored field, at any depth.
    assert "fleet" not in _Glider.__pydantic_fields__


def test_class_access_to_an_inherited_member_still_seeds_a_predicate() -> None:
    # Nothing the engine puts in the way of Pydantic's field collection outlives
    # class creation: every inherited member name resolves through the MRO to the
    # descriptor the declaring class installed.
    assert isinstance(_Glider.name, AttributeExpr)
    assert isinstance(_Glider.badges, AttributeExpr)
    assert isinstance(_Glider.tx_start, AttributeExpr)
    assert isinstance(_Glider.fleet, RelationshipPath)


def test_hydrating_a_descendant_fills_every_uncarried_inherited_member() -> None:
    # A member no read carried takes its declared default rather than whatever
    # class access to that member answers. Graded through the validation-free
    # constructor, which is where a declared default is applied at all: it is the
    # same default publication's own template row is prebuilt from.
    hydrated = _Glider.model_construct()
    assert hydrated.fleet_id is None
    assert hydrated.badge is None
    assert hydrated.badges == ()
    assert hydrated.span is None
    assert hydrated.tx_start is None
    assert hydrated.tow_hook is None


def test_an_inherited_required_member_is_still_required_of_a_descendant() -> None:
    with pytest.raises(ValidationError) as caught:
        _Glider(tow_hook=True)
    assert {error["loc"][0] for error in caught.value.errors()} == {"id", "name", "hull"}


def test_an_inherited_framework_owned_member_is_still_refused_of_a_descendant() -> None:
    # The refusal is a validator the root's class body installs; a descendant
    # inherits the member and the refusal together.
    with pytest.raises(ValidationError) as caught:
        _Glider(
            id=1,
            name="g",
            hull=_Badge(code="h", rank=1),
            tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
    assert {error["loc"][0] for error in caught.value.errors()} == {"tx_start"}


def test_a_descendant_binding_an_inherited_member_without_annotating_it_is_refused() -> None:
    # Nothing the engine puts in the way of Pydantic's field collection reaches a
    # name the class body bound: an unannotated override of an inherited member
    # stays Pydantic's own refusal rather than being quietly discarded.
    with pytest.raises(PydanticUserError) as caught:

        class Kite(  # pyright: ignore[reportUnusedClass] - class body must run to trigger the declaration-time rejection
            _Winged, name="Kite", namespace=_NS, inheritance=ConcreteSubtype(tag_value="k")
        ):
            fleet_id = 5  # pyright: ignore[reportAssignmentType] - an unannotated override is the subject

    assert caught.value.code == "model-field-overridden"
