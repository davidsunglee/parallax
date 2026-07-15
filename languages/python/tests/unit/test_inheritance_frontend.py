"""D-7 inheritance class frontend (DQ2): unit-level no-drift proof against
``models/payment.yaml`` (table-per-hierarchy) and ``models/document.yaml``
(table-per-concrete-subtype, COR-3 Phase 7 increment 6a). The full
API-conformance no-drift guard extension is the next agent's job; this is the
build-time proof that ``parent`` / ``role`` derive from the Python class
hierarchy and ``strategy`` / ``tag`` / ``tagValue`` thread through
``EntityConfig(inheritance=...)`` exactly as an ingested descriptor would.
"""

from __future__ import annotations

from typing import cast

import inheritance_models as im
import pytest
import yaml

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
