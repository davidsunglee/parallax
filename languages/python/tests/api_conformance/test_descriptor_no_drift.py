"""Descriptor no-drift guard (m-api-conformance).

Each idiomatic entity family the suite authors must export a descriptor that is
structurally equal to the corpus model it mirrors, now exercising full formation
on both sides. The comparison is over the logical model — physical ``indices``
are a storage concern the class frontend does not express — so both sides drop
the ``indices`` array before comparing. An accepted Metamodel enumerates entities
in canonical identity order while the corpus preserves its authored order, so a
multi-entity document is compared with its entities sorted by identity.
"""

from __future__ import annotations

from typing import cast

import pytest

import mirrored_models as mm
from parallax.conformance import case_format
from parallax.core.descriptor import canonicalize, export_document
from parallax.core.entity import metamodel

pytestmark = pytest.mark.api_conformance

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"


def _by_identity(document: dict[str, object]) -> dict[str, object]:
    """``document`` with its entities in canonical identity order.

    A single-``entity`` document is already canonical; a multi-entity one is
    sorted by ``(namespace, name)`` so an accepted model's canonical enumeration
    compares equal to the corpus's authored order.
    """
    if "entity" in document:
        return document
    entities = cast("list[dict[str, object]]", document["entities"])
    ordered = sorted(entities, key=lambda entity: (entity.get("namespace", ""), entity["name"]))
    return {**document, "entities": ordered}


@pytest.mark.parametrize("stem, classes", mm.MIRRORED, ids=[stem for stem, _ in mm.MIRRORED])
def test_idiomatic_class_export_has_no_drift_from_corpus(stem: str, classes: list[type]) -> None:
    raw = case_format.safe_load_yaml((_MODELS / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    corpus = mm.drop_indices(canonicalize(cast("dict[str, object]", raw)))
    assert _by_identity(export_document(metamodel(classes))) == _by_identity(corpus)
