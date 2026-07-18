"""Descriptor no-drift guard (m-api-conformance).

Each idiomatic entity family the suite authors must export a descriptor that is
structurally equal to the corpus model it mirrors. The comparison is over the
logical model — physical ``indices`` are a storage concern the class frontend
does not express — so both sides drop the ``indices`` array before comparing.
"""

from __future__ import annotations

from typing import cast

import pytest

import mirrored_models as mm
from parallax.conformance import case_format
from parallax.core.descriptor import canonicalize
from parallax.core.entity import descriptor_document

pytestmark = pytest.mark.api_conformance

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"


@pytest.mark.parametrize("stem, classes", mm.MIRRORED, ids=[stem for stem, _ in mm.MIRRORED])
def test_idiomatic_class_export_has_no_drift_from_corpus(stem: str, classes: list[type]) -> None:
    raw = case_format.safe_load_yaml((_MODELS / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    corpus = mm.drop_indices(canonicalize(cast("dict[str, object]", raw)))
    assert descriptor_document(classes) == corpus
