"""Freeze the compatibility corpus's effective entity-member storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reference_harness.case import Entity, Model, load_model
from reference_harness.storage_layout import (
    AttributeContributor,
    DirectColumn,
    DocumentPath,
    MemberAddress,
    TableLayout,
    ValueObjectContributor,
)

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


def _contained_paths(occurrence: dict[str, Any]) -> list[tuple[str, ...]]:
    """Every member path inside ``occurrence``, relative to the occurrence itself."""
    paths: list[tuple[str, ...]] = []
    for leaf in occurrence.get("attributes", []) or []:
        paths.append((leaf["name"],))
    for nested in occurrence.get("valueObjects", []) or []:
        paths.append((nested["name"],))
        paths.extend((nested["name"], *deeper) for deeper in _contained_paths(nested))
    return paths


def _document_paths(entity: Entity, layout: TableLayout | None) -> MemberColumns:
    """Every member the layout stores inside a document, as its Member Placement.

    The rendering is ``<structured column>:<dotted Document Path>``, taken from
    ``TableLayout.placement`` rather than re-derived, so the derivation this
    baseline freezes is the one consumers actually read.

    A member inside a top-level occurrence is always here, under either layout.
    A TOP-LEVEL member is here only where the Entity declares a Relational
    Document Layout that moved it, and that entry is the authority: the
    ``attribute`` / ``valueObject`` maps beside it freeze the DESCRIPTOR's derived
    column name for every declared member, which such a member does not occupy.
    """
    if layout is None:
        return {}
    placements: MemberColumns = {}

    def record(path: tuple[str, ...], *, contained: bool) -> None:
        address = MemberAddress(entity.canonical_name, path)
        placement = layout.placement(address)
        if placement is None and not contained:
            return  # a member of an ancestor's table this Entity does not own
        assert not contained or isinstance(placement, DocumentPath), (
            f"{entity.canonical_name}.{'.'.join(path)} is not document-resident"
        )
        if isinstance(placement, DocumentPath):
            placements[".".join(path)] = f"{placement.slot.column}:{'.'.join(placement.path)}"

    for attribute in entity.definition.get("attributes", []) or []:
        record((attribute["name"],), contained=False)
    for occurrence in entity.definition.get("valueObjects", []) or []:
        name = occurrence["name"]
        record((name,), contained=False)
        for relative in _contained_paths(occurrence):
            record((name, *relative), contained=True)
    return placements


def _entity_projection(entity: Entity, layout: TableLayout | None) -> EntityProjection:
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
    return {
        "attribute": attributes,
        "valueObject": value_objects,
        "documentPath": _document_paths(entity, layout),
    }


def _entity_layout(model: Model, entity: Entity) -> TableLayout | None:
    """The Table Layout carrying ``entity``'s rows, or absent for a tableless node."""
    return model.storage_layout.table(entity.table) if entity.table else None


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
            projected_entities[identity] = _entity_projection(entity, _entity_layout(model, entity))

        assert len(projected_entities) == len(model.entity_defs)
        projection[relative_path] = projected_entities

    expected_paths = {path.relative_to(_COMPATIBILITY_ROOT).as_posix() for path in model_paths}
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


def test_every_corpus_contributor_is_placed_over_the_slot_it_owns() -> None:
    """Placement agrees with contribution for every contributor in the corpus.

    Wherever a top-level member holds a Column of its own the two lookups answer
    the same question about it, so a table where they disagree is a
    consumer-visible defect rather than a layout choice. This walks slots, so a
    Relational Document Layout's document-resident members are outside it by
    construction: they contribute no slot at all, and `documentPath` in the frozen
    baseline is what states where they went instead.
    """
    for model_path in _model_paths():
        relative_path = model_path.relative_to(_COMPATIBILITY_ROOT).as_posix()
        model = load_model(_COMPATIBILITY_ROOT, relative_path)
        for layout in model.storage_layout.tables:
            for slot in layout.columns:
                contributor = slot.contributor
                if not isinstance(contributor, (AttributeContributor, ValueObjectContributor)):
                    continue
                address = MemberAddress(contributor.owner, (contributor.name,))
                assert layout.placement(address) == DirectColumn(slot), (
                    f"{relative_path}: {layout.table}.{slot.column} disagrees"
                )
