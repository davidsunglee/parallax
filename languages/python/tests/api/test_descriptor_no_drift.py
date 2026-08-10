"""Descriptor no-drift guard (m-api-conformance).

Each idiomatic class family the suite authors must form the same accepted
Metamodel the corpus model it mirrors forms. The comparison is field for field
over the two accepted models rather than over exported documents, so it measures
what every behavioral module actually reads and needs no export round trip on
either side; the ``indices`` array is compared with everything else, because the
class grammar expresses local indices.

The metadata protocols prescribe no concrete class, so two implementations of one
member are never equal *values* where the protocol is what they satisfy — Value
Object occurrences and leaves are therefore compared by what they answer.

Pure, Docker-free, in-process behaviour, so it classifies ``dbfree`` and the
class frontend's corpus proof contributes to the database-free branch-coverage
gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from _support import mirrored_models as mm
from parallax.conformance import case_format, models

if TYPE_CHECKING:
    from parallax.core import DomainModel
    from parallax.core.metamodel import (
        EntityMetadata,
        Metamodel,
        NestedValueObjectMetadata,
        ValueObjectAttributeMetadata,
        ValueObjectMetadata,
    )

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"


def _corpus(stem: str) -> Metamodel:
    return models.load_model(Path(_MODELS / f"{stem}.yaml"))


def _leaf(left: ValueObjectAttributeMetadata, right: ValueObjectAttributeMetadata) -> None:
    assert left.identity == right.identity
    assert left.type == right.type
    assert left.nullable == right.nullable


def _occurrence(
    left: NestedValueObjectMetadata | ValueObjectMetadata,
    right: NestedValueObjectMetadata | ValueObjectMetadata,
) -> None:
    assert left.identity == right.identity
    assert left.multiplicity is right.multiplicity
    assert left.nullable == right.nullable
    for leaf, other in zip(left.attributes, right.attributes, strict=True):
        _leaf(leaf, other)
    for below, other_below in zip(left.value_objects, right.value_objects, strict=True):
        _occurrence(below, other_below)


def _entity(left: EntityMetadata, right: EntityMetadata) -> None:
    assert left.identity == right.identity
    assert left.declared_container == right.declared_container
    assert left.declared_persistence == right.declared_persistence
    assert list(left.declared_attributes) == list(right.declared_attributes)
    assert list(left.declared_relationships) == list(right.declared_relationships)
    assert list(left.declared_as_of_axes) == list(right.declared_as_of_axes)
    assert list(left.indices) == list(right.indices)
    assert left.inheritance == right.inheritance
    for occurrence, other in zip(
        left.declared_value_objects, right.declared_value_objects, strict=True
    ):
        assert occurrence.storage == other.storage
        _occurrence(occurrence, other)


def test_mirrored_and_reasoned_models_partition_the_corpus() -> None:
    stems = {path.stem for path in _MODELS.glob("*.yaml")}
    mirrored = {stem for stem, _ in mm.MIRRORED}
    assert mirrored.isdisjoint(mm.UNMIRRORED)
    assert mirrored | set(mm.UNMIRRORED) == stems
    assert [stem for stem in mm.UNMIRRORED if not mm.UNMIRRORED[stem].strip()] == []


@pytest.mark.parametrize("stem, model", mm.MIRRORED, ids=[stem for stem, _ in mm.MIRRORED])
def test_idiomatic_classes_form_the_corpus_model(stem: str, model: DomainModel) -> None:
    corpus = _corpus(stem)
    assert [entity.identity for entity in model.entities] == [
        entity.identity for entity in corpus.entities
    ]
    for left, right in zip(model.entities, corpus.entities, strict=True):
        _entity(left, right)
