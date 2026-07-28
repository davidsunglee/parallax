"""Freeze every corpus model's independent physical Table Layout projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reference_harness.case import load_model
from reference_harness.storage_layout import (
    AttributeContributor,
    ColumnContributor,
    InheritanceDiscriminator,
    ValueObjectContributor,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_MODELS_ROOT = _COMPATIBILITY_ROOT / "models"
_BASELINE_PATH = Path(__file__).parent / "fixtures" / "corpus-table-layout.json"

TableProjection = dict[str, Any]
ModelProjection = dict[str, TableProjection]
CorpusProjection = dict[str, ModelProjection]


def _model_paths() -> list[Path]:
    return sorted(set(_MODELS_ROOT.rglob("*.yaml")) | set(_MODELS_ROOT.rglob("*.yml")))


def _contributor(contributor: ColumnContributor) -> str:
    if isinstance(contributor, AttributeContributor):
        return f"attribute:{contributor.owner}.{contributor.name}"
    if isinstance(contributor, ValueObjectContributor):
        return f"valueObject:{contributor.owner}.{contributor.name}"
    if isinstance(contributor, InheritanceDiscriminator):
        return f"discriminator:{contributor.root}"
    raise AssertionError(f"unknown contributor {contributor!r}")


def _corpus_projection(model_paths: list[Path]) -> CorpusProjection:
    projection: CorpusProjection = {}
    for model_path in model_paths:
        relative_path = model_path.relative_to(_COMPATIBILITY_ROOT).as_posix()
        model = load_model(_COMPATIBILITY_ROOT, relative_path)
        tables: ModelProjection = {}
        for layout in model.storage_layout.tables:
            column_contributors = [_contributor(slot.contributor) for slot in layout.columns]
            primary_key_ordinals = [
                layout.columns.index(slot) for slot in layout.physical_primary_key
            ]
            assert len(column_contributors) == len(set(column_contributors))
            assert len(primary_key_ordinals) == len(set(primary_key_ordinals))
            assert all(0 <= ordinal < len(layout.columns) for ordinal in primary_key_ordinals)
            tables[layout.table] = {
                "columns": [
                    {
                        "column": slot.column,
                        "tier": slot.tier.value,
                        "contributor": _contributor(slot.contributor),
                        "declaringOwner": slot.declaring_owner,
                        "effectiveNullable": slot.effective_nullable,
                        "applicableEntities": sorted(slot.applicable_entities),
                    }
                    for slot in layout.columns
                ],
                "physicalPrimaryKey": primary_key_ordinals,
            }
        assert len(tables) == len(model.storage_layout.tables)
        projection[relative_path] = tables
    return projection


def _canonical_json(projection: CorpusProjection) -> str:
    return json.dumps(projection, indent=2, sort_keys=True) + "\n"


def test_corpus_table_layout_matches_independent_baseline() -> None:
    model_paths = _model_paths()
    assert model_paths, f"no corpus models found under {_MODELS_ROOT}"
    actual = _canonical_json(_corpus_projection(model_paths))
    expected = _BASELINE_PATH.read_text(encoding="utf-8")
    assert actual == expected
