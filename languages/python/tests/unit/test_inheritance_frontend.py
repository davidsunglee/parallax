"""D-7 inheritance class frontend (DQ2): unit-level no-drift proof against
``models/payment.yaml`` (table-per-hierarchy) and ``models/document.yaml``
(table-per-concrete-subtype, COR-3 Phase 7 increment 6a). This is the
build-time proof that ``parent`` / ``role`` derive from the Python class
hierarchy and ``strategy`` / ``tag`` / ``tagValue`` thread through
``EntityConfig(inheritance=...)`` exactly as an ingested descriptor would.

The API-conformance no-drift guard extension this docstring used to defer is
DONE: `read_stories.py`'s Dog/CardPayment/Invoice examples (COR-3 Phase 7
increment 6b / the Phase-7 implementation review remediation) already execute
inheritance-family reads through the shipped surface against real Postgres.
This file also proves the temporal composition's class-frontend spelling —
``models/rate.yaml`` (table-per-concrete-subtype BITEMPORAL, the root ALONE
declaring ``EntityConfig(as_of=...)``, COR-3 residual-finding remediation) —
against the SAME installed ``Rate`` family the ``m-inheritance-100`` `ReadStory`
(`parallax.conformance.read_stories`) queries, so its own definition never
drifts from the corpus descriptor either.
"""

from __future__ import annotations

from typing import cast

import pytest
import yaml

import inheritance_models as im
from parallax.conformance import case_format
from parallax.core.descriptor import canonicalize
from parallax.core.entity import descriptor_document, entity_record_of

pytestmark = pytest.mark.unit

_MODELS_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"


def _drop_indices(document: dict[str, object]) -> dict[str, object]:
    # The class frontend expresses the logical model only (D-8): physical
    # indices are a storage concern with no class-level declaration mechanism.
    import copy

    clone = copy.deepcopy(document)
    entities = clone["entities"] if "entities" in clone else [clone["entity"]]
    for entity in entities:  # type: ignore[union-attr]
        entity.pop("indices", None)  # type: ignore[attr-defined]
    return clone


def _corpus(stem: str) -> dict[str, object]:
    raw = yaml.safe_load((_MODELS_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))
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
    # The root ALONE declares `as_of` (the binding root-ownership decision); the
    # concrete subtypes declare none of their own — proving that spelling
    # (`EntityConfig(as_of=...)` on `Rate`, absent on `DepositRate`/`LoanRate`)
    # threads through exactly as the ingested descriptor's root-only
    # `asOfAttributes` does.
    corpus = _corpus("rate")
    mine = descriptor_document([im.Rate, im.DepositRate, im.LoanRate])
    assert mine == corpus


def test_root_is_tableless_and_the_shared_table_defaults_from_it() -> None:
    root = entity_record_of(im.Payment)
    assert root is not None
    assert root.table is None
    assert root.inheritance is not None
    assert root.inheritance.role == "root"
    assert root.inheritance.strategy == "table-per-hierarchy"
    assert root.inheritance.tag_column == "kind"

    card = entity_record_of(im.CardPayment)
    assert card is not None
    assert card.table == "payment"  # shared table, derived from the root
    assert card.inheritance is not None
    assert card.inheritance.role == "concrete-subtype"
    assert card.inheritance.parent == "Payment"
    assert card.inheritance.tag_value == "card"


def test_a_concrete_subtype_may_override_its_derived_table() -> None:
    wire = entity_record_of(im.WirePayment)
    assert wire is not None
    assert wire.table == "wire_payment"  # explicit override, not the shared "payment" table


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


def test_abstract_subtype_declaring_a_table_is_rejected() -> None:
    from parallax.core import Attr, EntityConfig, Field

    with pytest.raises(Exception, match="tableless and rowless"):

        class BadAbstract(im.Payment, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(table="nope")

            extra: Attr[int] = Field(type="int32", default=0)


def test_subclassing_a_non_family_entity_is_rejected() -> None:
    from parallax.core import Attr, Entity, EntityConfig, Field

    class Plain(Entity, frozen=True):
        __parallax__ = EntityConfig(table="plain")
        id: Attr[int] = Field(primary_key=True, type="int64")

    with pytest.raises(Exception, match="declares no inheritance family"):

        class NotAFamilyMember(Plain, frozen=True):  # pyright: ignore[reportUnusedClass]
            extra: Attr[int] = Field(type="int32", default=0)


# --------------------------------------------------------------------------- #
# Binding decision (COR-3 residual-finding remediation): temporal axes are     #
# family-wide; only the family ROOT may declare `EntityConfig(as_of=...)`.    #
# The class frontend rejects a subclass that declares its own, at class-      #
# definition time, consistently with `parallax.core.inheritance.validate`'s   #
# `inheritance-temporal-axes-not-root-owned` descriptor invariant.            #
# --------------------------------------------------------------------------- #
def test_concrete_subtype_declaring_its_own_as_of_is_rejected() -> None:
    from parallax.core import Attr, EntityConfig, Field
    from parallax.core.descriptor import AsOfAttribute
    from parallax.core.entity.base import Concrete

    with pytest.raises(Exception, match="family SUBCLASS cannot declare EntityConfig\\(as_of"):

        class BadConcrete(im.Rate, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(
                inheritance=Concrete(),
                as_of=(
                    AsOfAttribute(
                        name="businessDate",
                        from_column="from_z",
                        to_column="thru_z",
                        axis="business",
                    ),
                ),
            )

            extra: Attr[str | None] = Field(type="string", nullable=True, default=None)


def test_abstract_subtype_declaring_its_own_as_of_is_rejected() -> None:
    from parallax.core import Attr, EntityConfig, Field
    from parallax.core.descriptor import AsOfAttribute

    with pytest.raises(Exception, match="family SUBCLASS cannot declare EntityConfig\\(as_of"):

        class BadAbstract(im.Rate, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(
                as_of=(
                    AsOfAttribute(
                        name="businessDate",
                        from_column="from_z",
                        to_column="thru_z",
                        axis="business",
                    ),
                )
            )

            extra: Attr[str | None] = Field(type="string", nullable=True, default=None)


def test_concrete_subtype_declaring_an_optimistic_locking_attr_is_rejected() -> None:
    # D-25 / ADR 0027 (subsuming the old ADR-0026-era composition check): a
    # temporal-family CONCRETE subtype declares no `as_of` of its own (only the
    # root does, the test above), and the GENERAL root-ownership rule (D-25)
    # forbids it from carrying its own `optimisticLocking` attribute too — a
    # non-root may never declare its own version attribute at all, temporal or
    # not (`im.Rate` is bitemporal; the rule fires the same way for a
    # non-temporal family, the tests below).
    from parallax.core import Attr, EntityConfig, Field
    from parallax.core.entity.base import Concrete

    with pytest.raises(Exception, match="only the inheritance family root may declare"):

        class BadVersionedConcrete(im.Rate, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(inheritance=Concrete())

            version: Attr[int] = Field(type="int64", optimistic_locking=True)


# --------------------------------------------------------------------------- #
# D-25 / ADR 0027: optimistic locking is root-owned and family-uniform — the  #
# class-frontend gate (EntityMeta.__new__) rejects a family subclass          #
# declaring its own `optimisticLocking` attribute, regardless of what the     #
# root declares, mirroring `parallax.core.inheritance.validate`'s             #
# `inheritance-optimistic-locking-not-root-owned` descriptor invariant.       #
# --------------------------------------------------------------------------- #
def test_root_declared_optimistic_locking_is_accepted() -> None:
    from parallax.core import Attr, Entity, EntityConfig, Field
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
    from parallax.core import Attr, Entity, EntityConfig, Field
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
    from parallax.core import Attr, Entity, EntityConfig, Field
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
