"""Freeze the compatibility corpus's effective entity-member storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reference_harness.case import Entity, load_model

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_MODELS_ROOT = _COMPATIBILITY_ROOT / "models"
_BASELINE_PATH = Path(__file__).parent / "fixtures" / "corpus-effective-storage.json"

MemberColumns = dict[str, str]
EntityProjection = dict[str, MemberColumns]
ModelProjection = dict[str, EntityProjection]
CorpusProjection = dict[str, ModelProjection]


def _model_paths() -> list[Path]:
    paths = set(_MODELS_ROOT.rglob("*.yaml")) | set(_MODELS_ROOT.rglob("*.yml"))
    return sorted(paths)


def _column(member: dict[str, Any]) -> str:
    column = member["column"]
    assert isinstance(column, str)
    return column


def _entity_projection(entity: Entity) -> EntityProjection:
    attributes: MemberColumns = {}
    declared_attributes = entity.definition.get("attributes", [])
    for declaration in declared_attributes:
        name = declaration["name"]
        assert isinstance(name, str)
        assert name not in attributes, f"duplicate Attribute {entity.canonical_name}.{name}"
        attributes[name] = _column(entity.attribute_by_name(name))

    value_objects: MemberColumns = {}
    declared_value_objects = entity.definition.get("valueObjects", [])
    for declaration in declared_value_objects:
        name = declaration["name"]
        assert isinstance(name, str)
        assert name not in value_objects, f"duplicate Value Object {entity.canonical_name}.{name}"
        value_objects[name] = _column(entity.value_object_by_name(name))

    assert len(attributes) == len(declared_attributes)
    assert len(value_objects) == len(declared_value_objects)
    return {"attribute": attributes, "valueObject": value_objects}


def _corpus_projection(model_paths: list[Path]) -> CorpusProjection:
    projection: CorpusProjection = {}
    for model_path in model_paths:
        relative_path = model_path.relative_to(_COMPATIBILITY_ROOT).as_posix()
        model = load_model(_COMPATIBILITY_ROOT, relative_path)
        entities = model.entities
        assert entities, f"{relative_path} declares no entities"

        projected_entities: ModelProjection = {}
        for entity in entities:
            identity = entity.canonical_name
            assert identity not in projected_entities, (
                f"{relative_path} declares duplicate Entity identity {identity}"
            )
            projected_entities[identity] = _entity_projection(entity)

        assert len(projected_entities) == len(model.entity_defs)
        projection[relative_path] = projected_entities

    expected_paths = {
        path.relative_to(_COMPATIBILITY_ROOT).as_posix() for path in model_paths
    }
    assert set(projection) == expected_paths
    return projection


def _canonical_json(projection: CorpusProjection) -> str:
    return json.dumps(projection, indent=2, sort_keys=True) + "\n"


def test_corpus_effective_storage_matches_historical_baseline() -> None:
    model_paths = _model_paths()
    assert model_paths, f"no corpus models found under {_MODELS_ROOT}"

    actual = _canonical_json(_corpus_projection(model_paths))
    expected = _BASELINE_PATH.read_text(encoding="utf-8")

    assert actual == expected
