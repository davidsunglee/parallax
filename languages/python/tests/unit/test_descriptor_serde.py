"""m-descriptor serde: round-trip fidelity over the corpus and error handling."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
import yaml

from parallax.conformance import case_format
from parallax.core.descriptor import (
    UNSET,
    AsOfAxisMetadata,
    Attribute,
    DefiningRelationship,
    DescriptorError,
    Entity,
    Metamodel,
    NestedValueObject,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ValueObject,
    ValueObjectAttribute,
    canonicalize,
    deserialize,
    serialize,
)

pytestmark = pytest.mark.unit

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
def test_every_corpus_descriptor_round_trips_deterministically(path: Path) -> None:
    canonical = canonicalize(_raw(path))
    # Idempotence: the canonical form is a fixpoint of serialize ∘ deserialize.
    assert canonicalize(canonical) == canonical
    # Records survive the round-trip identically.
    assert deserialize(canonical) == deserialize(_raw(path))


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_canonical_form_survives_json_and_yaml(path: Path) -> None:
    canonical = canonicalize(_raw(path))
    assert json.loads(json.dumps(canonical)) == canonical
    assert yaml.safe_load(yaml.safe_dump(canonical)) == canonical


_validate = cast("Callable[[object, object], None]", jsonschema.validate)


@pytest.mark.parametrize("path", _MODELS, ids=lambda p: p.stem)
def test_canonical_form_validates_against_metamodel_schema(path: Path) -> None:
    _validate(canonicalize(_raw(path)), _SCHEMA)


def test_pk_generation_application_assigned_is_canonicalized() -> None:
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
    assert canonicalize(document) == document


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


def test_read_only_and_default_survive_round_trip() -> None:
    entity = Entity(
        name="Flag",
        table="flag",
        mutability="transactional",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
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
                {
                    "name": "on",
                    "type": "boolean",
                    "readOnly": True,
                    "default": True,
                },
                {
                    "name": "note",
                    "type": "string",
                    "nullable": True,
                    "default": None,
                },
            ],
        }
    }
    assert deserialize(document) == Metamodel(entities=(entity,))
    assert deserialize(document).entity("Flag").attributes[0].default is UNSET


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
                            "dimension": "transactionTime",
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
        mutability="transactional",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
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
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
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
                                dimension="transactionTime",
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
