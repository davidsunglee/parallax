"""Corpus model ingestion through the m-descriptor deserializer."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core.descriptor import canonicalize, serialize

pytestmark = pytest.mark.unit

_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"


def test_default_models_dir_points_at_the_corpus() -> None:
    assert corpus_models.default_models_dir() == _DIR


def test_every_corpus_model_ingests_and_round_trips() -> None:
    loaded = corpus_models.load_models(_DIR)
    on_disk = {path.stem for path in _DIR.glob("*.yaml")}
    assert set(loaded) == on_disk
    assert loaded  # non-empty
    for stem, metamodel in loaded.items():
        # The ingested records re-serialize to the canonical form of the raw file.
        import yaml

        raw = yaml.safe_load((_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))
        assert serialize(metamodel) == canonicalize(raw)


def test_load_model_rejects_a_non_mapping_document(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.yaml"
    bogus.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a mapping"):
        corpus_models.load_model(bogus)
