"""The authored-corpus proof that Storage Layout preserves logical behavior."""

from __future__ import annotations

from pathlib import Path

import yaml

from reference_harness.twin_layout_check import twin_layout_errors

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _model(*, document_layout: bool) -> dict:
    entity: dict[str, object] = {
        "name": "TwinItem",
        "namespace": "example",
        "table": "twin_item",
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True},
            {"name": "label", "type": "string"},
        ],
    }
    if document_layout:
        entity["layout"] = {"document": {"column": "payload"}}
    return {"entities": [entity]}


def _case(arm: str, *, rows: list[dict[str, object]] | None = None) -> dict:
    return {
        "model": f"models/item-layout-twin-{arm}.yaml",
        "tags": ["m-storage-layout", "layout-twin"],
        "shape": "read",
        "when": {"objectQuery": {"target": "example.TwinItem", "predicate": {"all": {}}}},
        "then": {
            "statements": [
                {
                    "sql": {
                        "postgres": (
                            "select t0.id, t0.label from twin_item t0"
                            if arm == "columns"
                            else "select t0.id, t0.payload from twin_item t0"
                        )
                    }
                }
            ],
            "rows": rows if rows is not None else [{"id": 1, "label": "Ada"}],
            "roundTrips": 1,
        },
    }


def _complete_corpus(root: Path) -> None:
    fixtures = {"example.TwinItem": [{"id": 1, "label": "Ada"}]}
    for number, arm in ((900, "columns"), (901, "document")):
        _write(
            root / "models" / f"item-layout-twin-{arm}.yaml",
            _model(document_layout=arm == "document"),
        )
        _write(root / "fixtures" / f"item-layout-twin-{arm}.yaml", fixtures)
        _write(
            root / "cases" / f"m-storage-layout-{number:03d}-valid-read-layout-twin-{arm}.yaml",
            _case(arm),
        )


def test_real_corpus_twin_layout_proofs_are_complete() -> None:
    assert twin_layout_errors(_COMPATIBILITY_ROOT) == []


def test_equal_logical_descriptors_and_observations_pass(tmp_path: Path) -> None:
    _complete_corpus(tmp_path)
    assert twin_layout_errors(tmp_path) == []


def test_descriptor_comparison_strips_only_layout_blocks(tmp_path: Path) -> None:
    _complete_corpus(tmp_path)
    path = tmp_path / "models" / "item-layout-twin-document.yaml"
    changed = _model(document_layout=True)
    entities = changed["entities"]
    assert isinstance(entities, list)
    entity = entities[0]
    assert isinstance(entity, dict)
    attributes = entity["attributes"]
    assert isinstance(attributes, list)
    attribute = attributes[1]
    assert isinstance(attribute, dict)
    attribute["type"] = "int64"
    _write(path, changed)

    errors = twin_layout_errors(tmp_path)
    assert any("differs after root-owned layout blocks are removed" in error for error in errors)


def test_layout_invariant_observations_must_match(tmp_path: Path) -> None:
    _complete_corpus(tmp_path)
    path = tmp_path / "cases" / "m-storage-layout-901-valid-read-layout-twin-document.yaml"
    _write(path, _case("document", rows=[{"id": 1, "label": "Linus"}]))

    errors = twin_layout_errors(tmp_path)
    assert any("differs in layout-invariant authored behavior" in error for error in errors)


def test_unpaired_case_is_refused(tmp_path: Path) -> None:
    _complete_corpus(tmp_path)
    (tmp_path / "cases" / "m-storage-layout-901-valid-read-layout-twin-document.yaml").unlink()

    errors = twin_layout_errors(tmp_path)
    assert any("case twin" in error and "missing document" in error for error in errors)
