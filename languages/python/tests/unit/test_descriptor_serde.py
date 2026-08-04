"""m-descriptor serde: round-trip fidelity over the corpus and error handling."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
import yaml

from parallax.conformance import case_format
from parallax.descriptor._errors import DescriptorError
from parallax.descriptor._records import (
    UNSET,
    AsOfAxisMetadata,
    Attribute,
    DefiningRelationship,
    Entity,
    Metamodel,
    NestedValueObject,
    PkGenerator,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._serde import canonicalize, deserialize, serialize

_REPO = case_format.find_repo_root()
_MODELS = sorted((_REPO / "core" / "compatibility" / "models").glob("*.yaml"))
_SCHEMA = cast(
    "dict[str, Any]", json.loads((_REPO / "core" / "schemas" / "metamodel.schema.json").read_text())
)


def _raw(path: Path) -> dict[str, Any]:
    loaded = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_every_corpus_descriptor_is_authored_in_canonical_form(path: Path) -> None:
    authored = _raw(path)
    assert canonicalize(authored) == authored


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_every_corpus_descriptor_canonicalization_is_idempotent(path: Path) -> None:
    canonical = canonicalize(_raw(path))
    assert canonicalize(canonical) == canonical


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_every_corpus_descriptor_records_round_trip(path: Path) -> None:
    records = deserialize(_raw(path))
    assert deserialize(serialize(records)) == records


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_canonical_form_survives_json_and_yaml(path: Path) -> None:
    canonical = canonicalize(_raw(path))
    assert json.loads(json.dumps(canonical)) == canonical
    assert yaml.safe_load(yaml.safe_dump(canonical)) == canonical


_validate = cast("Callable[[object, object], None]", jsonschema.validate)


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_canonical_form_validates_against_metamodel_schema(path: Path) -> None:
    _validate(canonicalize(_raw(path)), _SCHEMA)


def test_pk_generation_application_assigned_is_omitted() -> None:
    document = {
        "entity": {
            "name": "A",
            "table": "a",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "primaryKey": True,
                    "pkGeneration": "application-assigned",
                }
            ],
        }
    }
    canonical = {
        "entity": {
            "name": "A",
            "table": "a",
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        }
    }
    assert canonicalize(document) == canonical
    assert canonicalize(canonical) == canonical


def test_pk_generation_sequence_object_is_preserved() -> None:
    document = {
        "entity": {
            "name": "B",
            "table": "b",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "primaryKey": True,
                    "pkGeneration": {"strategy": "sequence", "name": "s", "batchSize": 2},
                }
            ],
        }
    }
    assert canonicalize(document) == document


def test_member_columns_normalize_and_serialize_against_the_derived_default() -> None:
    document = {
        "entity": {
            "name": "Contact",
            "table": "contact",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "personId", "type": "string"},
                {"name": "lineItem", "type": "string", "column": "line_item"},
                {"name": "taxID", "type": "string", "column": "tax_id"},
                {"name": "legacyName", "type": "string", "column": "legacyName"},
            ],
            "valueObjects": [
                {
                    "name": "postalAddress",
                    "attributes": [{"name": "city", "type": "string"}],
                },
                {
                    "name": "billingAddress",
                    "column": "billing_address",
                    "attributes": [{"name": "city", "type": "string"}],
                },
                {
                    "name": "legacyAddress",
                    "column": "legacyAddress",
                    "attributes": [{"name": "city", "type": "string"}],
                },
            ],
        }
    }

    entity = deserialize(document).entity("Contact")
    assert {attribute.name: attribute.column for attribute in entity.attributes} == {
        "id": "id",
        "personId": "person_id",
        "lineItem": "line_item",
        "taxID": "tax_id",
        "legacyName": "legacyName",
    }
    assert [
        (value_object.name, value_object.column, value_object.storage_column)
        for value_object in entity.value_objects
    ] == [
        ("postalAddress", None, "postal_address"),
        ("billingAddress", None, "billing_address"),
        ("legacyAddress", "legacyAddress", "legacyAddress"),
    ]

    canonical = canonicalize(document)
    canonical_entity = cast("dict[str, Any]", canonical["entity"])
    attributes = {
        attribute["name"]: attribute
        for attribute in cast("list[dict[str, Any]]", canonical_entity["attributes"])
    }
    assert "column" not in attributes["personId"]
    assert "column" not in attributes["lineItem"]
    assert attributes["taxID"]["column"] == "tax_id"
    assert attributes["legacyName"]["column"] == "legacyName"
    value_objects = {
        value_object["name"]: value_object
        for value_object in cast("list[dict[str, Any]]", canonical_entity["valueObjects"])
    }
    assert "column" not in value_objects["postalAddress"]
    assert "column" not in value_objects["billingAddress"]
    assert value_objects["legacyAddress"]["column"] == "legacyAddress"


@pytest.mark.parametrize("member_kind", ["attribute", "valueObject"])
def test_person_id_old_camel_case_override_survives_round_trip(member_kind: str) -> None:
    entity_document: dict[str, Any] = {
        "name": "Legacy",
        "table": "legacy",
        "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
    }
    if member_kind == "attribute":
        cast("list[dict[str, Any]]", entity_document["attributes"]).append(
            {"name": "personId", "type": "string", "column": "personId"}
        )
    else:
        entity_document["valueObjects"] = [
            {
                "name": "personId",
                "column": "personId",
                "attributes": [{"name": "value", "type": "string"}],
            }
        ]
    document: dict[str, object] = {"entity": entity_document}

    canonical = canonicalize(document)
    canonical_entity = cast("dict[str, Any]", canonical["entity"])
    members = cast(
        "list[dict[str, Any]]",
        canonical_entity["valueObjects" if member_kind == "valueObject" else "attributes"],
    )
    exported = members[0] if member_kind == "valueObject" else members[1]
    assert exported["column"] == "personId"

    entity = deserialize(document).entity("Legacy")
    if member_kind == "attribute":
        assert entity.attributes[1].column == "personId"
    else:
        assert entity.value_objects[0].column == "personId"
        assert entity.value_objects[0].storage_column == "personId"


def test_pk_generation_object_requires_sequence_strategy() -> None:
    document = {
        "entity": {
            "name": "Bad",
            "table": "bad",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "primaryKey": True,
                    "pkGeneration": {"strategy": "max"},
                }
            ],
        }
    }
    with pytest.raises(DescriptorError, match="requires `strategy: sequence`"):
        deserialize(document)


def test_read_only_survives_round_trip_and_default_is_not_wire_vocabulary() -> None:
    entity = Entity(
        name="Flag",
        table="flag",
        attributes=(
            Attribute(
                name="id",
                type="int64",
                column="id",
                primary_key=True,
                pk_generator=PkGenerator(strategy="none"),
            ),
            Attribute(name="on", type="boolean", column="on", read_only=True, default=True),
            Attribute(name="note", type="string", column="note", nullable=True, default=None),
        ),
    )
    document = serialize(Metamodel(entities=(entity,)))
    assert document == {
        "entity": {
            "name": "Flag",
            "table": "flag",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "on", "type": "boolean", "readOnly": True},
                {"name": "note", "type": "string", "nullable": True},
            ],
        }
    }
    assert all(attr.default is UNSET for attr in deserialize(document).entity("Flag").attributes)


def test_authored_default_key_is_rejected() -> None:
    document = {
        "entity": {
            "name": "Flag",
            "table": "flag",
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True, "default": 1}],
        }
    }
    with pytest.raises(DescriptorError, match="default"):
        deserialize(document)


def test_multi_entity_uses_entities_array_and_single_uses_entity() -> None:
    single = serialize(
        Metamodel(
            entities=(
                Entity(
                    name="One",
                    table="one",
                    attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
                ),
            )
        )
    )
    assert set(single) == {"entity"}
    multi = serialize(
        Metamodel(
            entities=(
                Entity(
                    name="A",
                    table="a",
                    attributes=(Attribute(name="id", type="int64", column="id"),),
                ),
                Entity(
                    name="B",
                    table="b",
                    attributes=(Attribute(name="id", type="int64", column="id"),),
                ),
            )
        )
    )
    assert set(multi) == {"entities"}


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"entity": {"name": "A"}, "entities": []},
        {"entities": []},
    ],
)
def test_missing_or_conflicting_entity_form_is_rejected(document: dict[str, Any]) -> None:
    with pytest.raises(DescriptorError):
        deserialize(document)


def test_retired_temporal_spelling_is_rejected() -> None:
    document = {
        "entity": {
            "name": "Bad",
            "table": "bad",
            "temporal": "bitemporal",
            "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
        }
    }
    with pytest.raises(DescriptorError, match="unknown properties: `temporal`"):
        deserialize(document)


def _layout_document(layout: object) -> dict[str, object]:
    return {
        "entity": {
            "name": "Bad",
            "table": "bad",
            "layout": layout,
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        }
    }


@pytest.mark.parametrize(
    ("layout", "message"),
    [
        ({"columns": {}}, "unknown properties: `columns`"),
        ({}, "`document` is required"),
        ({"document": {"column": 1}}, "`column` must be a string"),
        ({"document": {"column": "payload", "format": "bson"}}, "unknown properties: `format`"),
    ],
    ids=["columns-has-no-spelling", "document-required", "column-not-a-string", "closed-document"],
)
def test_a_malformed_layout_is_rejected_at_ingestion(layout: object, message: str) -> None:
    with pytest.raises(DescriptorError, match=re.escape(message)):
        deserialize(_layout_document(layout))


def test_a_document_layout_survives_the_canonical_round_trip() -> None:
    document = _layout_document({"document": {"column": "payload"}})
    assert canonicalize(document) == document


def test_non_string_persistence_is_rejected() -> None:
    document = {
        "entity": {
            "name": "Bad",
            "table": "bad",
            "persistence": True,
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        }
    }
    with pytest.raises(DescriptorError, match="`persistence` must be a string"):
        deserialize(document)


@pytest.mark.parametrize(
    "relationship",
    [
        {"name": "peer", "reverseOf": "B.other", "cardinality": "one-to-one"},
        {"name": "peer", "reverseOf": "other"},
    ],
)
def test_malformed_reverse_relationship_is_rejected(relationship: dict[str, object]) -> None:
    document = {
        "entity": {
            "name": "A",
            "table": "a",
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            "relationships": [relationship],
        }
    }
    with pytest.raises(DescriptorError):
        deserialize(document)


def test_non_string_value_object_multiplicity_is_rejected() -> None:
    document = {
        "entity": {
            "name": "A",
            "table": "a",
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            "valueObjects": [{"name": "tags", "multiplicity": 2}],
        }
    }
    with pytest.raises(DescriptorError, match="`multiplicity` must be a string"):
        deserialize(document)


@pytest.mark.parametrize(
    "attribute",
    [
        {"name": "id", "type": "int64", "column": 7},  # non-string override
        {"name": "id", "type": "int64", "nullable": "yes"},  # non-bool
        {"name": "id", "type": "int64", "maxLength": "x"},  # non-int
        {"name": "id", "type": "int64", "pkGeneration": "wild"},  # bad strategy
        {"name": "id", "type": "int64", "pkGenerator": "none"},  # retired key
    ],
)
def test_malformed_attributes_are_rejected(attribute: dict[str, Any]) -> None:
    with pytest.raises(DescriptorError):
        deserialize({"entity": {"name": "A", "table": "a", "attributes": [attribute]}})


def test_pk_generation_requires_a_primary_key() -> None:
    with pytest.raises(DescriptorError, match="requires `primaryKey: true`"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "table": "a",
                    "attributes": [{"name": "value", "type": "int64", "pkGeneration": "max"}],
                }
            }
        )


def test_cross_namespace_relationship_identity_round_trips_exactly() -> None:
    document = {
        "entities": [
            {
                "name": "Source",
                "namespace": "alpha",
                "table": "source",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                "relationships": [
                    {
                        "name": "targets",
                        "cardinality": "one-to-many",
                        "join": {
                            "source": "id",
                            "target": {"entity": "beta.Target", "attribute": "sourceId"},
                        },
                    }
                ],
            },
            {
                "name": "Target",
                "namespace": "beta",
                "table": "target",
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "sourceId", "type": "int64"},
                ],
                "relationships": [{"name": "source", "reverseOf": "alpha.Source.targets"}],
            },
            {
                "name": "Target",
                "namespace": "alpha",
                "table": "other_target",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            },
        ]
    }

    metamodel = deserialize(document)
    declaration = metamodel.entity("alpha.Source").relationships[0]
    assert isinstance(declaration, DefiningRelationship)
    assert declaration.join.target.entity == "beta.Target"
    assert metamodel.entity(declaration.join.target.entity).namespace == "beta"
    relationship = metamodel.relationship("alpha.Source", "targets")
    assert relationship.join.target.entity == "beta.Target"
    assert {field.name for field in fields(Relationship)} == {
        "name",
        "cardinality",
        "join",
        "reverse",
        "dependent",
        "order_by",
    }
    with pytest.raises(KeyError):
        metamodel.entity("Target")

    serialized = serialize(metamodel)
    source, target, _collision = cast("list[dict[str, Any]]", serialized["entities"])
    source_relationships = cast("list[dict[str, Any]]", source["relationships"])
    source_join = cast("dict[str, Any]", source_relationships[0]["join"])
    source_target = cast("dict[str, Any]", source_join["target"])
    target_relationships = cast("list[dict[str, Any]]", target["relationships"])
    assert source_target["entity"] == "beta.Target"
    assert target_relationships[0]["reverseOf"] == "alpha.Source.targets"


def test_bad_axis_reference_and_direction_are_rejected() -> None:
    base = {"name": "id", "type": "int64", "primaryKey": True}
    with pytest.raises(DescriptorError, match="dimension"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "asOfAxes": [
                        {
                            "dimension": "wallClock",
                            "startAttribute": "id",
                            "endAttribute": "id",
                        }
                    ],
                }
            }
        )
    with pytest.raises(DescriptorError, match="applicable attribute"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "asOfAxes": [
                        {
                            "dimension": "transaction-time",
                            "startAttribute": "missing",
                            "endAttribute": "id",
                        }
                    ],
                }
            }
        )
    with pytest.raises(DescriptorError, match="direction"):
        deserialize(
            {
                "entities": [
                    {
                        "name": "A",
                        "attributes": [base],
                        "relationships": [
                            {
                                "name": "rs",
                                "cardinality": "one-to-many",
                                "join": {
                                    "source": "id",
                                    "target": {"entity": "B", "attribute": "aId"},
                                },
                                "orderBy": [{"attribute": "id", "direction": "sideways"}],
                            }
                        ],
                    },
                    {
                        "name": "B",
                        "attributes": [
                            {"name": "id", "type": "int64"},
                            {"name": "aId", "type": "int64"},
                        ],
                    },
                ]
            }
        )


def test_bad_order_by_null_placement_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="nulls"):
        deserialize(
            {
                "entities": [
                    {
                        "name": "A",
                        "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                        "relationships": [
                            {
                                "name": "rs",
                                "cardinality": "one-to-many",
                                "join": {
                                    "source": "id",
                                    "target": {"entity": "B", "attribute": "aId"},
                                },
                                "orderBy": [{"attribute": "id", "nulls": "middle"}],
                            }
                        ],
                    },
                    {
                        "name": "B",
                        "attributes": [
                            {"name": "id", "type": "int64"},
                            {"name": "aId", "type": "int64"},
                        ],
                    },
                ]
            }
        )


def test_an_order_by_null_placement_round_trips_and_canonicalizes_its_default() -> None:
    def document(term: dict[str, Any]) -> dict[str, Any]:
        return {
            "entities": [
                {
                    "name": "A",
                    "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                    "relationships": [
                        {
                            "name": "rs",
                            "cardinality": "one-to-many",
                            "join": {
                                "source": "id",
                                "target": {"entity": "B", "attribute": "aId"},
                            },
                            "orderBy": [term],
                        }
                    ],
                },
                {
                    "name": "B",
                    "attributes": [
                        {"name": "id", "type": "int64"},
                        {"name": "aId", "type": "int64"},
                    ],
                },
            ]
        }

    first = document({"attribute": "id", "direction": "desc", "nulls": "first"})
    assert serialize(deserialize(first)) == first
    authored_last = document({"attribute": "id", "nulls": "last"})
    assert serialize(deserialize(authored_last)) == document({"attribute": "id"})


def test_non_mapping_and_non_list_shapes_are_rejected() -> None:
    with pytest.raises(DescriptorError):
        deserialize({"entity": "not a mapping"})
    with pytest.raises(DescriptorError):
        deserialize({"entities": "not a list"})
    with pytest.raises(DescriptorError):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [{"name": "id", "type": "int64", "column": "id"}],
                    "indices": [{"name": "i", "attributes": "id"}],
                }
            }
        )


def test_non_string_optional_field_is_rejected() -> None:
    with pytest.raises(DescriptorError):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "namespace": 123,
                    "table": "a",
                    "attributes": [{"name": "id", "type": "int64", "column": "id"}],
                }
            }
        )


def test_serialize_covers_optional_relationship_and_value_object_shapes() -> None:
    entity = Entity(
        name="Rich",
        table="rich",
        attributes=(
            Attribute(
                name="id",
                type="int64",
                column="id",
                primary_key=True,
                pk_generator=PkGenerator(strategy="none"),
            ),
        ),
        relationships=(
            DefiningRelationship(
                name="peer",
                cardinality="many-to-one",
                join=RelationshipJoin(
                    source="id", target=RelationshipTarget(entity="Other", attribute="id")
                ),
            ),  # no reverse / orderBy
        ),
        value_objects=(
            ValueObject(name="tags", multiplicity="many"),  # many, no attributes
            ValueObject(
                name="addr",
                column="legacy_addr",
                attributes=(ValueObjectAttribute(name="city", type="string"),),
                value_objects=(
                    NestedValueObject(
                        name="geo",
                        value_objects=(
                            NestedValueObject(name="point"),  # nested VO with no attributes
                        ),
                    ),
                ),
            ),
        ),
    )
    other = Entity(
        name="Other",
        table="other",
        attributes=(
            Attribute(
                name="id",
                type="int64",
                column="id",
                primary_key=True,
                pk_generator=PkGenerator(strategy="none"),
            ),
        ),
    )
    metamodel = Metamodel(entities=(entity, other))
    document = serialize(metamodel)
    # Round-tripping proves both the optional-shape serialize branches and the
    # matching deserialize branches (no foreign key, many VO, empty nested VO).
    assert deserialize(document) == metamodel


def test_serialize_rejects_unresolved_transition_records() -> None:
    attribute = Attribute(name="id", type="int64", column="id", primary_key=True)
    with pytest.raises(DescriptorError, match="has an invalid structured join"):
        serialize(
            Metamodel(
                entities=(
                    Entity(
                        name="A",
                        table="a",
                        attributes=(attribute,),
                        relationships=(
                            DefiningRelationship(
                                name="peer",
                                cardinality="one-to-one",
                                join=RelationshipJoin(
                                    source="",
                                    target=RelationshipTarget(entity="B", attribute="id"),
                                ),
                            ),
                        ),
                    ),
                )
            )
        )
    with pytest.raises(DescriptorError, match="has no Attribute references"):
        serialize(
            Metamodel(
                entities=(
                    Entity(
                        name="A",
                        table="a",
                        attributes=(attribute,),
                        as_of_axes=(
                            AsOfAxisMetadata(
                                dimension="transaction-time",
                                start_attribute="tx_start",
                                end_attribute="tx_end",
                            ),
                        ),
                    ),
                )
            )
        )


def test_retired_value_object_mapping_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="unknown properties: `mapping`"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "table": "a",
                    "attributes": [{"name": "id", "type": "int64", "column": "id"}],
                    "valueObjects": [{"name": "vo", "column": "vo", "mapping": "xml"}],
                }
            }
        )
