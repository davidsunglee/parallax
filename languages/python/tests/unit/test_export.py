"""Canonical export over the accepted Metamodel (m-descriptor).

Export is the inverse adapter: an accepted Metamodel becomes the canonical
minimal descriptor document ``_serde.canonicalize`` produces from a parsed one.
These pin the canonicalization law (export equals canonicalize, the omission set,
idempotence, a canonical fixpoint) over the corpus and over an alternate model
implementation, and the error path (an induced defect surfaces as
``DescriptorExportError`` with no partial output and no ``DescriptorError``).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from _support import fake_metamodel
from parallax.conformance import case_format, models
from parallax.core.base import STRING, TIMESTAMP
from parallax.core.metamodel import (
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    Document,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    Table,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.descriptor._errors import DescriptorError
from parallax.descriptor._export import DescriptorExportError, export_document
from parallax.descriptor._serde import canonicalize


def _corpus_paths() -> list[Path]:
    root = case_format.find_repo_root() / "core" / "compatibility" / "models"
    return sorted(root.glob("*.yaml"))


def _by_identity(document: dict[str, object]) -> dict[tuple[object, object], dict[str, object]]:
    """A document's entities keyed by ``(namespace, name)``.

    An accepted Metamodel enumerates in canonical identity order while a corpus
    document preserves its authored order, so entities are compared as an
    identity-keyed mapping rather than positionally.
    """
    if "entity" in document:
        entities = [cast("dict[str, object]", document["entity"])]
    else:
        entities = cast("list[dict[str, object]]", document["entities"])
    return {(entity.get("namespace"), entity["name"]): entity for entity in entities}


@pytest.mark.parametrize("path", _corpus_paths(), ids=lambda path: path.stem)
def test_export_equals_canonicalize_over_the_corpus(path: Path) -> None:
    raw = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    model = models.accepted_model(models.load_model(path))
    exported = export_document(model)
    corpus = canonicalize(cast("dict[str, object]", raw))
    assert ("entity" in exported) == ("entity" in corpus)
    assert _by_identity(exported) == _by_identity(corpus)


def test_export_over_an_alternate_implementation_matches_the_canonical_form() -> None:
    # `parity_model` builds no descriptor record, so export reads only the
    # metamodel protocols; `PARITY_DESCRIPTOR` is the same model as text.
    raw = case_format.safe_load_yaml(fake_metamodel.PARITY_DESCRIPTOR)
    assert isinstance(raw, dict)
    exported = export_document(fake_metamodel.parity_model())
    corpus = canonicalize(cast("dict[str, object]", raw))
    assert _by_identity(exported) == _by_identity(corpus)


def test_export_applies_the_omission_set() -> None:
    exported = _by_identity(export_document(fake_metamodel.parity_model()))
    ledger = exported[(None, "Ledger")]
    account = exported[("parallax.fake", "Account")]
    ledger_attributes = {
        a["name"]: a for a in cast("list[dict[str, object]]", ledger["attributes"])
    }
    account_attributes = {
        a["name"]: a for a in cast("list[dict[str, object]]", account["attributes"])
    }
    # Application-assigned generation is the default a bare declared key
    # re-derives, so `pkGeneration` is omitted; `max` is the bare strategy token.
    assert ledger_attributes["id"]["primaryKey"] is True
    assert "pkGeneration" not in ledger_attributes["id"]
    assert account_attributes["id"]["pkGeneration"] == "max"
    # A column equal to the portable derived default is omitted; an override is written.
    assert "column" not in account_attributes["balance"]
    assert "column" not in account_attributes["ledgerLabel"]
    value_objects = {
        value_object["name"]: value_object
        for value_object in cast("list[dict[str, object]]", account["valueObjects"])
    }
    assert value_objects["contact"]["column"] == "contact_doc"
    # Read Write is the default, so only the read-only Audit spells persistence.
    assert "persistence" not in account
    assert exported[("parallax.fake", "Audit")]["persistence"] == "read-only"


def test_export_retains_acronym_domain_and_old_camel_case_overrides() -> None:
    identity = EntityIdentity(None, "Contact")
    postal = ValueObjectIdentity(identity, ("postalAddress",))
    legacy = ValueObjectIdentity(identity, ("legacyAddress",))
    entity = fake_metamodel.FakeEntity(
        identity,
        declared_container=Table("contact"),
        declared_attributes=(
            AttributeMetadata(AttributeIdentity(identity, "personId"), STRING, Column("person_id")),
            AttributeMetadata(AttributeIdentity(identity, "taxID"), STRING, Column("tax_id")),
            AttributeMetadata(
                AttributeIdentity(identity, "legacyName"), STRING, Column("legacyName")
            ),
            AttributeMetadata(
                AttributeIdentity(identity, "displayName"), STRING, Column("display_label")
            ),
        ),
        declared_value_objects=(
            fake_metamodel.FakeValueObject(
                postal,
                Column("postal_address"),
                attributes=(
                    fake_metamodel.FakeValueObjectAttribute(
                        ValueObjectAttributeIdentity(postal, "city"), STRING
                    ),
                ),
            ),
            fake_metamodel.FakeValueObject(
                legacy,
                Column("legacyAddress"),
                attributes=(
                    fake_metamodel.FakeValueObjectAttribute(
                        ValueObjectAttributeIdentity(legacy, "city"), STRING
                    ),
                ),
            ),
        ),
    )

    exported = cast(
        "dict[str, object]",
        export_document(fake_metamodel.FakeMetamodel((entity,)))["entity"],
    )
    attributes = {
        attribute["name"]: attribute
        for attribute in cast("list[dict[str, object]]", exported["attributes"])
    }
    assert "column" not in attributes["personId"]
    assert attributes["taxID"]["column"] == "tax_id"
    assert attributes["legacyName"]["column"] == "legacyName"
    assert attributes["displayName"]["column"] == "display_label"
    value_objects = {
        value_object["name"]: value_object
        for value_object in cast("list[dict[str, object]]", exported["valueObjects"])
    }
    assert "column" not in value_objects["postalAddress"]
    assert value_objects["legacyAddress"]["column"] == "legacyAddress"


def test_export_writes_the_resolved_structured_column_only_where_the_root_owns_it() -> None:
    # Omission is the only wire form of Columns storage, and Storage Layout is
    # root-owned, so the property appears exactly where a root selects the
    # Document layout. A descendant record that nonetheless carries one keeps it
    # as the evidence family validation is stated over, and canonical form drops
    # it — the same rule persistence follows.
    root = EntityIdentity(None, "Record")
    child = EntityIdentity(None, "CardRecord")
    entities = (
        fake_metamodel.FakeEntity(
            root,
            declared_container=Table("record"),
            declared_layout=Document(Column("payload")),
            declared_attributes=(
                AttributeMetadata(AttributeIdentity(root, "note"), STRING, Column("note")),
            ),
        ),
        fake_metamodel.FakeEntity(
            child,
            declared_layout=Document(Column("payload")),
            inheritance=ConcreteSubtype(root, "card"),
        ),
    )
    exported = _by_identity(export_document(fake_metamodel.FakeMetamodel(entities)))
    assert exported[(None, "Record")]["layout"] == {"document": {"column": "payload"}}
    assert "layout" not in exported[(None, "CardRecord")]


def test_export_qualifies_a_same_namespace_parent_and_bares_an_ownerless_one() -> None:
    # An inheritance parent exports as exact Entity Identity wherever the child
    # sits, so a parent sharing the child's namespace is qualified exactly like a
    # cross-namespace one — the asymmetry canonical form used to carry. An
    # ownerless parent has no namespace to spell, so its canonical form is the
    # local name itself; that is the identity degenerating, not a second rule.
    owned = EntityIdentity("family.ns", "Child")
    ownerless = EntityIdentity(None, "Child")
    exported = _by_identity(
        export_document(
            fake_metamodel.FakeMetamodel(
                (
                    fake_metamodel.FakeEntity(
                        owned,
                        declared_container=Table("child"),
                        inheritance=AbstractSubtype(EntityIdentity("family.ns", "Parent")),
                    ),
                    fake_metamodel.FakeEntity(
                        ownerless,
                        declared_container=Table("orphan"),
                        inheritance=AbstractSubtype(EntityIdentity(None, "Parent")),
                    ),
                )
            )
        )
    )
    assert exported[("family.ns", "Child")]["inheritance"] == {
        "role": "abstract-subtype",
        "parent": "family.ns.Parent",
    }
    assert exported[(None, "Child")]["inheritance"] == {
        "role": "abstract-subtype",
        "parent": "Parent",
    }


def test_export_spells_read_only_cross_namespace_parent_and_a_many_value_object() -> None:
    # Three formatting branches no corpus model exercises: a read-only attribute,
    # a cross-namespace inheritance parent, and a top-level cardinality-many Value
    # Object. Export renews no validation, so a lone position with an out-of-model
    # parent still formats.
    child = EntityIdentity("child.ns", "Child")
    tags = ValueObjectIdentity(child, ("tags",))
    entity = fake_metamodel.FakeEntity(
        child,
        declared_container=Table("child"),
        declared_attributes=(
            AttributeMetadata(
                identity=AttributeIdentity(child, "note"),
                type=STRING,
                storage=Column("note"),
                read_only=True,
            ),
        ),
        declared_value_objects=(
            fake_metamodel.FakeValueObject(
                tags,
                Column("tags"),
                multiplicity=Multiplicity.MANY,
                attributes=(
                    fake_metamodel.FakeValueObjectAttribute(
                        ValueObjectAttributeIdentity(tags, "label"), STRING
                    ),
                ),
            ),
        ),
        inheritance=AbstractSubtype(EntityIdentity("other.ns", "Parent")),
    )
    exported = cast(
        "dict[str, object]", export_document(fake_metamodel.FakeMetamodel((entity,)))["entity"]
    )
    attributes = cast("list[dict[str, object]]", exported["attributes"])
    assert attributes[0]["readOnly"] is True
    assert exported["inheritance"] == {"role": "abstract-subtype", "parent": "other.ns.Parent"}
    value_objects = cast("list[dict[str, object]]", exported["valueObjects"])
    assert value_objects[0]["multiplicity"] == "many"


def test_export_drops_the_endpoints_the_axes_point_at_not_the_conventional_names() -> None:
    # The `m-metamodel` seam accepts an As-Of Axis over any distinct pair of local
    # Timestamp Attributes, so an axis can run over endpoints the convention table
    # does not name. The Temporality Profile is the axis's whole wire form, so
    # those endpoints leave the document with it: emitting them would produce a
    # `transaction-time` Entity whose re-import derives `txStart`/`txEnd` beside
    # them. What the round trip does not preserve is the endpoints' own names and
    # Columns, which come back canonical.
    identity = EntityIdentity(None, "Session")
    entity = fake_metamodel.FakeEntity(
        identity,
        declared_container=Table("session"),
        declared_attributes=(
            AttributeMetadata(AttributeIdentity(identity, "label"), STRING, Column("label")),
            AttributeMetadata(AttributeIdentity(identity, "openedAt"), TIMESTAMP, Column("in_z")),
            AttributeMetadata(AttributeIdentity(identity, "closedAt"), TIMESTAMP, Column("out_z")),
        ),
        declared_as_of_axes=(
            AsOfAxisMetadata(
                dimension=TemporalDimension.TRANSACTION_TIME,
                start_attribute=AttributeIdentity(identity, "openedAt"),
                end_attribute=AttributeIdentity(identity, "closedAt"),
            ),
        ),
    )
    exported = cast(
        "dict[str, object]", export_document(fake_metamodel.FakeMetamodel((entity,)))["entity"]
    )
    assert exported["temporality"] == "transaction-time"
    names = [
        attribute["name"] for attribute in cast("list[dict[str, object]]", exported["attributes"])
    ]
    assert names == ["label"]


def test_export_is_deterministic_and_a_canonical_fixpoint() -> None:
    model = fake_metamodel.parity_model()
    first = export_document(model)
    second = export_document(model)
    assert first == second
    # Re-canonicalizing an export changes nothing: export already emits the
    # canonical minimal form.
    assert canonicalize(first) == first


class _ExplodingEntity:
    """An Entity view that raises the moment export reads it."""

    @property
    def identity(self) -> EntityIdentity:
        raise RuntimeError("induced export defect")


class _ExplodingMetamodel:
    """A valid model with one Entity that raises during export."""

    def __init__(self, model: Metamodel) -> None:
        self._model = model

    @property
    def entities(self) -> tuple[EntityMetadata, ...]:
        return (*self._model.entities, cast("EntityMetadata", _ExplodingEntity()))

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self._model.entity(identity)

    def facet(self, key: object) -> object:  # pragma: no cover - unused by export
        raise KeyError(key)


def test_export_wraps_an_induced_defect_with_no_partial_output() -> None:
    model = fake_metamodel.parity_model()
    with pytest.raises(DescriptorExportError) as caught:
        export_document(cast("Metamodel", _ExplodingMetamodel(model)))
    error = caught.value
    assert error.code == "descriptor-export-failed"
    assert error.target == "document"
    assert isinstance(error.cause, RuntimeError)
    # An export defect is an adapter boundary, never an ingestion DescriptorError.
    assert not isinstance(error, DescriptorError)
    # No partial document escaped, and the underlying model is untouched: it still
    # exports its complete canonical form.
    assert export_document(model) == export_document(model)
