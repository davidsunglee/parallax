"""Corpus model ingestion through the m-descriptor deserializer."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from _sql_gen_support import corpus_records

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.descriptor._serde import canonicalize, serialize

_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"


def test_default_models_dir_points_at_the_corpus() -> None:
    assert corpus_models.default_models_dir() == _DIR


def test_every_corpus_model_ingests_and_round_trips() -> None:
    loaded = corpus_records()
    on_disk = {path.stem for path in _DIR.glob("*.yaml")}
    assert set(loaded) == on_disk
    assert loaded  # non-empty
    for stem, metamodel in loaded.items():
        # The ingested records re-serialize to the canonical form of the raw file.
        raw = case_format.safe_load_yaml((_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        assert serialize(metamodel) == canonicalize(cast("dict[str, object]", raw))


def test_load_model_rejects_a_non_mapping_document(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.yaml"
    bogus.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a mapping"):
        corpus_models.load_model(bogus)


def test_every_corpus_model_forms_through_the_public_door() -> None:
    formed = corpus_models.load_models(_DIR)
    assert set(formed) == {path.stem for path in _DIR.glob("*.yaml")}
    assert all(model.entities for model in formed.values())


def test_declared_entity_names_reads_the_documents_own_order() -> None:
    # The accepted model enumerates canonically, so the authoring order survives
    # only in the document — and `m-case-format`'s default-target convention for
    # a case naming no target is the document's own FIRST entity. Both top-level
    # forms answer, and a document declaring neither answers with nothing rather
    # than raising: this reads shape, and every defect is the door's to report.
    several = corpus_models.read_document(_DIR / "person.yaml")
    assert corpus_models.declared_entity_names(several) == ("Person", "Passport")
    assert [entity.identity.name for entity in corpus_models.accepted_model(several).entities] == [
        "Passport",
        "Person",
    ]
    assert corpus_models.declared_entity_names({"entity": {"name": "Solo"}}) == ("Solo",)
    assert corpus_models.declared_entity_names({"entities": "not a list"}) == ()
    assert corpus_models.declared_entity_names({}) == ()
