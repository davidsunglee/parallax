"""The inheritance class frontend: unit-level no-drift proof against
``models/payment.yaml`` (table-per-hierarchy) and ``models/document.yaml``
(table-per-concrete-subtype). This is the
build-time proof that ``parent`` / ``role`` derive from the Python class
hierarchy and ``strategy`` / ``tag`` / ``tagValue`` thread through
``EntityConfig(inheritance=...)`` exactly as an ingested descriptor would.

`read_stories.py`'s Dog/CardPayment/Invoice examples execute
inheritance-family reads through the shipped surface against real Postgres.
This file also proves the temporal composition's class-frontend spelling —
``models/rate.yaml`` (table-per-concrete-subtype BITEMPORAL, the root ALONE
extending the ``Bitemporal`` framework base) — against the SAME installed
``Rate`` family the ``m-inheritance-100`` `ReadStory`
(`parallax.conformance.read_stories`) queries, so its own definition never
drifts from the corpus descriptor either.
"""

from __future__ import annotations

from typing import cast

import pytest

import inheritance_models as im
from parallax.conformance import case_format
from parallax.core import Attr, Entity, EntityConfig, Field, descriptor, inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.descriptor import canonicalize, unresolved_metamodel
from parallax.core.entity import descriptor_document, entity_record_of, metamodel
from parallax.core.entity.base import Concrete, FamilyRoot
from parallax.core.metamodel import EntityIdentity, EntityLocation, PersistenceMode
from parallax.core.model_formation import MetamodelValidationError

pytestmark = pytest.mark.unit

_MODELS_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"


def _drop_indices(document: dict[str, object]) -> dict[str, object]:
    # The class frontend expresses the logical model only: physical
    # indices are a storage concern with no class-level declaration mechanism.
    import copy

    clone = copy.deepcopy(document)
    entities = clone["entities"] if "entities" in clone else [clone["entity"]]
    for entity in entities:  # type: ignore[union-attr]
        entity.pop("indices", None)  # type: ignore[attr-defined]
    return clone


def _corpus(stem: str) -> dict[str, object]:
    raw = case_format.safe_load_yaml((_MODELS_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return _drop_indices(canonicalize(cast("dict[str, object]", raw)))


def test_table_per_hierarchy_class_export_has_no_drift_from_payment_yaml() -> None:
    corpus = _corpus("payment")
    mine = descriptor_document([im.Payment, im.CardPayment, im.CashPayment])
    assert mine == corpus


def test_table_per_concrete_subtype_class_export_has_no_drift_from_document_yaml() -> None:
    corpus = _corpus("document")
    mine = descriptor_document(
        [im.Document, im.FinancialDocument, im.Invoice, im.Receipt, im.Memo, im.Folder]
    )
    assert mine == corpus


def test_temporal_tpcs_class_export_has_no_drift_from_rate_yaml() -> None:
    # The root ALONE selects the temporal shape (the binding root-ownership
    # decision); the concrete subtypes declare none of their own — proving
    # that spelling (the `Bitemporal` base on `Rate`, plain parent extension
    # on `DepositRate`/`LoanRate`) threads through exactly as the ingested
    # descriptor's root-only axis declarations do.
    corpus = _corpus("rate")
    mine = descriptor_document([im.Rate, im.DepositRate, im.LoanRate])
    assert mine == corpus


def test_temporal_base_on_a_family_root_injects_the_axes_on_the_root_alone() -> None:
    # The family-root base selection: the root's own compiled record carries
    # both injected axes (Valid Time first) and the injected standard interval
    # attributes; a concrete subtype's own record carries NO axes of its own —
    # its family-effective temporality resolves through the root.
    root = entity_record_of(im.Rate)
    assert root is not None
    assert root.temporal == "bitemporal"
    assert [
        (axis.dimension, axis.start_attribute, axis.end_attribute) for axis in root.as_of_axes
    ] == [
        ("validTime", "valid_start", "valid_end"),
        ("transactionTime", "tx_start", "tx_end"),
    ]
    assert [attr.name for attr in root.attributes] == [
        "id",
        "amount",
        "valid_start",
        "valid_end",
        "tx_start",
        "tx_end",
    ]
    concrete = entity_record_of(im.DepositRate)
    assert concrete is not None
    assert concrete.as_of_axes == ()


def test_tph_root_owns_the_shared_table() -> None:
    root = entity_record_of(im.Payment)
    assert root is not None
    assert root.table == "payment"
    assert root.inheritance is not None
    assert root.inheritance.role == "root"
    assert root.inheritance.strategy == "table-per-hierarchy"
    assert root.inheritance.tag_column == "kind"

    card = entity_record_of(im.CardPayment)
    assert card is not None
    assert card.table is None
    assert card.inheritance is not None
    assert card.inheritance.role == "concrete-subtype"
    assert card.inheritance.parent == "Payment"
    assert card.inheritance.tag_value == "card"


def test_tph_concrete_subtype_cannot_override_the_root_table() -> None:
    from parallax.core import EntityConfig, Field
    from parallax.core.entity.base import Concrete

    with pytest.raises(Exception, match="family root owns the shared table"):

        class WirePayment(im.Payment, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(
                table="wire_payment",
                inheritance=Concrete(tag_value="wire"),
            )

            reference: Attr[str | None] = Field(type="string", max_length=32, nullable=True)


def test_tpcs_abstract_subtype_is_tableless_and_concretes_own_their_table() -> None:
    fin_doc = entity_record_of(im.FinancialDocument)
    assert fin_doc is not None
    assert fin_doc.table is None
    assert fin_doc.inheritance is not None
    assert fin_doc.inheritance.role == "abstract-subtype"
    assert fin_doc.inheritance.parent == "Document"

    invoice = entity_record_of(im.Invoice)
    assert invoice is not None
    assert invoice.table == "invoice"
    assert invoice.inheritance is not None
    assert invoice.inheritance.role == "concrete-subtype"
    assert invoice.inheritance.parent == "FinancialDocument"
    assert invoice.inheritance.tag_value is None  # TPCS carries no tag at all


def test_tpcs_root_cannot_declare_a_table() -> None:
    from parallax.core import Entity, EntityConfig, Field
    from parallax.core.entity.base import FamilyRoot

    with pytest.raises(Exception, match="family root is tableless"):

        class BadRoot(Entity, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(
                table="bad_root",
                inheritance=FamilyRoot(strategy="table-per-concrete-subtype"),
            )

            id: Attr[int] = Field(primary_key=True, type="int64")


def test_abstract_subtype_declaring_a_table_is_rejected() -> None:
    from parallax.core import EntityConfig, Field

    with pytest.raises(Exception, match="tableless and rowless"):

        class BadAbstract(im.Payment, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(table="nope")

            extra: Attr[int] = Field(type="int32", default=0)


def test_subclassing_a_non_family_entity_is_rejected() -> None:
    from parallax.core import Entity, EntityConfig, Field

    class Plain(Entity, frozen=True):
        __parallax__ = EntityConfig(table="plain")
        id: Attr[int] = Field(primary_key=True, type="int64")

    with pytest.raises(Exception, match="declares no inheritance family"):

        class NotAFamilyMember(Plain, frozen=True):  # pyright: ignore[reportUnusedClass]
            extra: Attr[int] = Field(type="int32", default=0)


# --------------------------------------------------------------------------- #
# Binding decision: temporal axes are family-wide; only the family ROOT may    #
# select a temporal shape (by extending `TxTemporal`/`Bitemporal`). The class  #
# frontend rejects a subclass that lists a temporal base of its own, at        #
# class-definition time, consistently with                                     #
# `parallax.core.inheritance.validate`'s                                       #
# `inheritance-temporal-axes-not-root-owned` descriptor invariant.             #
# --------------------------------------------------------------------------- #
def test_concrete_subtype_extending_a_temporal_base_is_rejected() -> None:
    from parallax.core import Bitemporal, EntityConfig, Field
    from parallax.core.entity.base import Concrete

    with pytest.raises(Exception, match="family SUBCLASS cannot extend the temporal base"):

        class BadConcrete(im.Rate, Bitemporal, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(inheritance=Concrete())

            extra: Attr[str | None] = Field(type="string", nullable=True, default=None)


def test_abstract_subtype_extending_a_temporal_base_is_rejected() -> None:
    from parallax.core import Bitemporal, EntityConfig, Field

    with pytest.raises(Exception, match="family SUBCLASS cannot extend the temporal base"):

        class BadAbstract(im.Rate, Bitemporal, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig()

            extra: Attr[str | None] = Field(type="string", nullable=True, default=None)


def test_concrete_subtype_declaring_an_optimistic_locking_attr_is_rejected() -> None:
    # The family-uniform version rule (ADR 0027): a
    # temporal-family CONCRETE subtype declares no `as_of` of its own (only the
    # root does, the test above), and the GENERAL root-ownership rule
    # forbids it from carrying its own `optimisticLocking` attribute too — a
    # non-root may never declare its own version attribute at all, temporal or
    # not (`im.Rate` is bitemporal; the rule fires the same way for a
    # non-temporal family, the tests below).
    from parallax.core import EntityConfig, Field
    from parallax.core.entity.base import Concrete

    with pytest.raises(Exception, match="only the inheritance family root may declare"):

        class BadVersionedConcrete(im.Rate, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(inheritance=Concrete())

            version: Attr[int] = Field(type="int64", optimistic_locking=True)


# --------------------------------------------------------------------------- #
# ADR 0027: optimistic locking is root-owned and family-uniform — the         #
# class-frontend gate (EntityMeta.__new__) rejects a family subclass          #
# declaring its own `optimisticLocking` attribute, regardless of what the     #
# root declares, mirroring `parallax.core.inheritance.validate`'s             #
# `inheritance-optimistic-locking-not-root-owned` descriptor invariant.       #
# --------------------------------------------------------------------------- #
def test_root_declared_optimistic_locking_is_accepted() -> None:
    from parallax.core import Entity, EntityConfig, Field
    from parallax.core.entity.base import Concrete, FamilyRoot

    class _VersionedApplianceRoot(Entity, frozen=True):
        __parallax__ = EntityConfig(inheritance=FamilyRoot(strategy="table-per-concrete-subtype"))
        id: Attr[int] = Field(primary_key=True, type="int64")
        version: Attr[int] = Field(type="int64", optimistic_locking=True)

    class _VersionedApplianceLeaf(  # pyright: ignore[reportUnusedClass]
        _VersionedApplianceRoot, frozen=True
    ):
        __parallax__ = EntityConfig(inheritance=Concrete())
        capacity: Attr[int | None] = Field(type="int32", nullable=True, default=None)

    # no raise — the root alone declares the version column


def test_descendant_only_optimistic_locking_is_rejected() -> None:
    from parallax.core import Entity, EntityConfig, Field
    from parallax.core.entity.base import Concrete, FamilyRoot

    class _UnversionedApplianceRoot(Entity, frozen=True):
        __parallax__ = EntityConfig(inheritance=FamilyRoot(strategy="table-per-concrete-subtype"))
        id: Attr[int] = Field(primary_key=True, type="int64")

    with pytest.raises(Exception, match="only the inheritance family root may declare"):

        class _BadUnversionedLeaf(  # pyright: ignore[reportUnusedClass]
            _UnversionedApplianceRoot, frozen=True
        ):
            __parallax__ = EntityConfig(inheritance=Concrete())
            version: Attr[int] = Field(type="int64", optimistic_locking=True)


def test_root_and_different_descendant_attribute_is_rejected() -> None:
    from parallax.core import Entity, EntityConfig, Field
    from parallax.core.entity.base import Concrete, FamilyRoot

    class _VersionedOvenRoot(Entity, frozen=True):
        __parallax__ = EntityConfig(inheritance=FamilyRoot(strategy="table-per-concrete-subtype"))
        id: Attr[int] = Field(primary_key=True, type="int64")
        version: Attr[int] = Field(type="int64", optimistic_locking=True)

    with pytest.raises(Exception, match="only the inheritance family root may declare"):

        class _BadSecondVersionLeaf(  # pyright: ignore[reportUnusedClass]
            _VersionedOvenRoot, frozen=True
        ):
            __parallax__ = EntityConfig(inheritance=Concrete())
            revision: Attr[int] = Field(type="int64", optimistic_locking=True)


# --------------------------------------------------------------------------- #
# Persistence is root-owned (m-inheritance "Persistence is root-owned"), which  #
# makes what a class DECLARES the evidence that rule needs: a descendant that   #
# spells a mode at all is invalid, and absence on a descendant means inherit.   #
# The class frontend therefore records the mode a class authored and nothing    #
# else, while the canonical descriptor still spells `persistence` only where    #
# m-descriptor's omission set allows it.                                        #
#                                                                               #
# `_AuditLedger` is deliberately that invalid shape, so this family is a        #
# NEGATIVE fixture on two levels at once: assembly and canonical export are     #
# pinned below exactly as they behave for any descendant, and the family        #
# formation the same declarations feed is pinned as rejected. The two are one   #
# statement -- authorship survives assembly PRECISELY so the family rule has    #
# something to reject -- so neither half may be read alone.                     #
# --------------------------------------------------------------------------- #


class _Ledger(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="ledger",
        mutability="read-only",
        inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
    )
    id: Attr[int] = Field(primary_key=True, type="int64")


class _AuditLedger(_Ledger, frozen=True):
    __parallax__ = EntityConfig(mutability="read-only", inheritance=Concrete(tag_value="audit"))
    note: Attr[str | None] = Field(type="string", max_length=32, nullable=True)


class _SilentLedger(_Ledger, frozen=True):
    __parallax__ = EntityConfig(inheritance=Concrete(tag_value="silent"))
    label: Attr[str | None] = Field(type="string", max_length=32, nullable=True)


def _assembled(classes: list[type], name: str) -> descriptor.Entity:
    (record,) = [entity for entity in metamodel(classes).entities if entity.name == name]
    return record


def test_a_descendant_declares_the_same_persistence_with_or_without_its_root() -> None:
    assert _assembled([_AuditLedger], "_AuditLedger").persistence == "read-only"
    assert _assembled([_Ledger, _AuditLedger], "_AuditLedger").persistence == "read-only"
    assert _assembled([_SilentLedger], "_SilentLedger").persistence is None
    assert _assembled([_Ledger, _SilentLedger], "_SilentLedger").persistence is None


def test_an_authored_descendant_persistence_survives_assembly_and_is_never_exported() -> None:
    family = [_Ledger, _AuditLedger]
    assert _assembled(family, "_Ledger").persistence == "read-only"
    assert _assembled(family, "_AuditLedger").persistence == "read-only"

    root, descendant = cast("list[dict[str, object]]", descriptor_document(family)["entities"])
    assert root["persistence"] == "read-only"
    assert "persistence" not in descendant


def test_a_descendant_authored_persistence_makes_the_family_an_invalid_model() -> None:
    with pytest.raises(MetamodelValidationError) as caught:
        form_metamodel(unresolved_metamodel(metamodel([_Ledger, _AuditLedger])))
    (issue,) = caught.value.issues
    assert issue.code == inheritance.PERSISTENCE_NOT_ROOT_OWNED
    assert issue.location == EntityLocation(EntityIdentity(None, "_AuditLedger"))
    assert issue.related == (EntityLocation(EntityIdentity(None, "_Ledger")),)


def test_a_descendant_that_declares_no_mode_inherits_the_root_owned_one() -> None:
    model = form_metamodel(unresolved_metamodel(metamodel([_Ledger, _SilentLedger])))
    facet = inheritance.view(model)
    silent = facet.entity(EntityIdentity(None, "_SilentLedger"))
    assert silent is not None
    assert silent.persistence is PersistenceMode.READ_ONLY
