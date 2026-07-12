"""m-descriptor serde: round-trip fidelity over the corpus and error handling."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
import yaml

from parallax.conformance import case_format
from parallax.core.descriptor import (
    UNSET,
    Attribute,
    DescriptorError,
    Entity,
    Metamodel,
    NestedValueObject,
    Relationship,
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
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
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


def test_pk_generator_string_spelling_is_preserved() -> None:
    document = {
        "entity": {
            "name": "A",
            "table": "a",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGenerator": "none",
                }
            ],
        }
    }
    assert canonicalize(document) == document


def test_pk_generator_object_spelling_is_preserved() -> None:
    document = {
        "entity": {
            "name": "B",
            "table": "b",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGenerator": {"strategy": "sequence", "sequenceName": "s", "batchSize": 2},
                }
            ],
        }
    }
    assert canonicalize(document) == document


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
            "mutability": "transactional",
            "attributes": [
                {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                {
                    "name": "on",
                    "type": "boolean",
                    "column": "on",
                    "readOnly": True,
                    "default": True,
                },
                {
                    "name": "note",
                    "type": "string",
                    "column": "note",
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


def test_temporal_disagreeing_with_axes_is_rejected() -> None:
    document = {
        "entity": {
            "name": "Bad",
            "table": "bad",
            "temporal": "bitemporal",
            "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
        }
    }
    with pytest.raises(DescriptorError, match="temporal"):
        deserialize(document)


@pytest.mark.parametrize(
    "attribute",
    [
        {"name": "id", "type": "int64"},  # missing column
        {"name": "id", "type": "int64", "column": "id", "nullable": "yes"},  # non-bool
        {"name": "id", "type": "int64", "column": "id", "maxLength": "x"},  # non-int
        {"name": "id", "type": "int64", "column": "id", "pkGenerator": "wild"},  # bad strategy
    ],
)
def test_malformed_attributes_are_rejected(attribute: dict[str, Any]) -> None:
    with pytest.raises(DescriptorError):
        deserialize({"entity": {"name": "A", "table": "a", "attributes": [attribute]}})


def test_bad_axis_default_infinity_and_direction_are_rejected() -> None:
    base = {"name": "id", "type": "int64", "column": "id", "primaryKey": True}
    with pytest.raises(DescriptorError, match="axis"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "asOfAttributes": [
                        {"name": "d", "fromColumn": "a", "toColumn": "b", "axis": "wall-clock"}
                    ],
                }
            }
        )
    with pytest.raises(DescriptorError, match="now"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "asOfAttributes": [
                        {
                            "name": "d",
                            "fromColumn": "a",
                            "toColumn": "b",
                            "axis": "processing",
                            "default": "later",
                        }
                    ],
                }
            }
        )
    with pytest.raises(DescriptorError, match="infinity"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "asOfAttributes": [
                        {
                            "name": "d",
                            "fromColumn": "a",
                            "toColumn": "b",
                            "axis": "processing",
                            "infinity": "max",
                        }
                    ],
                }
            }
        )
    with pytest.raises(DescriptorError, match="direction"):
        deserialize(
            {
                "entity": {
                    "name": "A",
                    "attributes": [base],
                    "relationships": [
                        {
                            "name": "r",
                            "relatedEntity": "B",
                            "cardinality": "one-to-many",
                            "join": "x",
                            "orderBy": [{"attr": "id", "direction": "sideways"}],
                        }
                    ],
                }
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
            Relationship(
                name="peer",
                related_entity="Other",
                cardinality="many-to-one",
                join="this.otherId = Other.id",
            ),  # no reverseName / foreignKey / orderBy
        ),
        value_objects=(
            ValueObject(name="tags", column="tags", cardinality="many"),  # many, no attributes
            ValueObject(
                name="addr",
                column="addr",
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
    document = serialize(Metamodel(entities=(entity,)))
    # Round-tripping proves both the optional-shape serialize branches and the
    # matching deserialize branches (no foreign key, many VO, empty nested VO).
    assert deserialize(document) == Metamodel(entities=(entity,))


def test_value_object_mapping_must_be_json() -> None:
    with pytest.raises(DescriptorError, match="json"):
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
