"""The inheritance class frontend: how ``inheritance=`` and Python subclassing
compose into the declared family position, and where each family rule fires.

The corpus no-drift proof lives in ``test_descriptor_no_drift.py``, which
compares the accepted Metamodel a class family forms against the one its corpus
model forms. What is pinned here is the frontend's own half: that the parent and
the role variant derive from the class hierarchy, that a temporal base selects
the family's axes on the root alone, and that a family-semantic violation which
stays *spellable* reaches hub construction as the shared formation-time
``inheritance-*`` issue rather than through a Python-only rule.
"""

from __future__ import annotations

import pytest

import inheritance_models as im
from parallax.core import (
    READ_ONLY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Entity,
    EntityDefinitionError,
    Int32,
    MetamodelHub,
    TablePerHierarchy,
    attr,
    inheritance,
)
from parallax.core.entity import sealed_model
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

pytestmark = pytest.mark.unit

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
        "valid_start",
        "valid_end",
        "tx_start",
        "tx_end",
    ]
    assert im.Rate.attributes[-1].storage == Column("out_z")
    assert im.DepositRate.as_of_axes == ()


# --------------------------------------------------------------------------- #
# What the grammar itself refuses, at class creation.                          #
# --------------------------------------------------------------------------- #
def test_a_domain_subclass_declaring_no_role_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError) as caught:

        class NoRole(im.Payment, namespace=_NS):  # pyright: ignore[reportUnusedClass]
            reference: Attr[str | None] = attr(max_length=32)

    assert caught.value.code == "entity-base-invalid"


def test_a_subclass_extending_a_temporal_base_beside_its_parent_is_rejected() -> None:
    # Temporal shape is family-wide and root-owned, so a family member never
    # names a second Parallax base — the grammar allows exactly one.
    with pytest.raises(EntityDefinitionError) as caught:

        class TwoBases(  # pyright: ignore[reportUnusedClass]
            im.Rate, Bitemporal, namespace=_NS, inheritance=ConcreteSubtype
        ):
            extra: Attr[str | None]

    assert caught.value.code == "entity-base-invalid"


def test_a_subtype_role_without_a_domain_parent_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError) as caught:

        class Orphan(  # pyright: ignore[reportUnusedClass]
            Entity, table="orphan", namespace=_NS, inheritance=ConcreteSubtype
        ):
            id: Attr[int] = attr(primary_key=True)

    assert caught.value.code == "entity-header-invalid-value"


# --------------------------------------------------------------------------- #
# What stays spellable and is therefore a formation-time family rule: the two  #
# frontends enforce the same accepted-model invariants, so these reach hub     #
# construction as `inheritance-*` issues rather than a Python-only rejection.  #
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
        MetamodelHub(TphRoot, TphLeaf)
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
        MetamodelHub(TpcsRoot, TpcsLeaf)
    assert _issue_codes(caught.value) == [inheritance.TPCS_ABSTRACT_TABLE_FORBIDDEN]


def test_a_descendant_declaring_its_own_version_attribute_is_a_formation_issue() -> None:
    # Optimistic locking is root-owned and family-uniform (ADR 0027).
    class OvenRoot(Entity, namespace=_NS, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
        id: Attr[int] = attr(primary_key=True)

    class OvenLeaf(OvenRoot, table="oven_leaf", namespace=_NS, inheritance=ConcreteSubtype):
        version: Attr[int] = attr(type=Int32, optimistic_locking=True)

    with pytest.raises(MetamodelValidationError) as caught:
        MetamodelHub(OvenRoot, OvenLeaf)
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

    view = inheritance.view(sealed_model(MetamodelHub(ApplianceRoot, ApplianceLeaf)).model)
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
    namespace=_NS,
    persistence=READ_ONLY,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)


class _AuditLedger(
    _Ledger, namespace=_NS, persistence=READ_ONLY, inheritance=ConcreteSubtype(tag_value="audit")
):
    note: Attr[str | None] = attr(max_length=32)


class _SilentLedger(_Ledger, namespace=_NS, inheritance=ConcreteSubtype(tag_value="silent")):
    label: Attr[str | None] = attr(max_length=32)


def test_a_descendant_declares_exactly_the_mode_it_authored() -> None:
    assert _Ledger.persistence is PersistenceMode.READ_ONLY
    assert _AuditLedger.persistence is PersistenceMode.READ_ONLY
    assert _SilentLedger.persistence is None


def test_a_descendant_authored_persistence_makes_the_family_an_invalid_model() -> None:
    with pytest.raises(MetamodelValidationError) as caught:
        MetamodelHub(_Ledger, _AuditLedger)
    (issue,) = caught.value.issues
    assert issue.code == inheritance.PERSISTENCE_NOT_ROOT_OWNED
    assert issue.location == EntityLocation(_identity("_AuditLedger"))
    assert issue.related == (EntityLocation(_identity("_Ledger")),)


def test_a_descendant_that_declares_no_mode_inherits_the_root_owned_one() -> None:
    view = inheritance.view(sealed_model(MetamodelHub(_Ledger, _SilentLedger)).model)
    silent = view.entity(_identity("_SilentLedger"))
    assert silent is not None
    assert silent.persistence is PersistenceMode.READ_ONLY
