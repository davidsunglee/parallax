"""The authored-corpus proof that a streamed read's page size changes nothing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from reference_harness.batch_size_twin_check import batch_size_twin_errors

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _case(
    batch_size: int,
    *,
    pages: int,
    graph: list[dict[str, Any]] | None = None,
    values: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "model": "models/item.yaml",
        "tags": ["m-snapshot-read", "stream"],
        "shape": "read",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
        "when": {
            "objectQuery": {
                "target": "example.StreamItem",
                "predicate": {"in": {"attr": "example.StreamItem.id", "values": values or [1, 2]}},
            },
            "stream": {"batchSize": batch_size},
        },
        "then": {
            "statements": [
                {"sql": {"postgres": f"select t0.id from stream_item t0 -- page {page}"}}
                for page in range(pages)
            ],
            "graph": {"StreamItem": graph if graph is not None else [{"id": 1}, {"id": 2}]},
            "roundTrips": pages,
        },
    }


def _corpus(root: Path) -> None:
    modules = """# Modules

## The module catalog

| Module | Summary | Status | Coverage |
| --- | --- | --- | --- |
| `m-snapshot-read` | Snapshot read | active | cases |
"""
    spec = root.parent / "spec"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "modules.md").write_text(modules, encoding="utf-8")
    _write(
        root / "cases" / "m-snapshot-read-900-page-invariance-batch-size-twin-1.yaml",
        _case(1, pages=3),
    )
    _write(
        root / "cases" / "m-snapshot-read-901-page-invariance-batch-size-twin-2.yaml",
        _case(2, pages=2),
    )


def test_real_corpus_batch_size_twins_are_complete() -> None:
    assert batch_size_twin_errors(_COMPATIBILITY_ROOT) == []


def test_arms_differing_only_in_page_size_and_its_goldens_pass(tmp_path: Path) -> None:
    _corpus(tmp_path)
    assert batch_size_twin_errors(tmp_path) == []


def test_a_coherent_edit_to_one_arm_is_refused(tmp_path: Path) -> None:
    """The failure mode the gate exists for: a query and graph moved together.

    Each arm still passes its own end-to-end sweep afterwards, so nothing else in
    the corpus notices that the two no longer describe one read.
    """
    _corpus(tmp_path)
    _write(
        tmp_path / "cases" / "m-snapshot-read-901-page-invariance-batch-size-twin-2.yaml",
        _case(2, pages=2, values=[1], graph=[{"id": 1}]),
    )

    errors = batch_size_twin_errors(tmp_path)
    assert any("differ in page-size-invariant authored behavior" in error for error in errors)


def test_a_lone_arm_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path)
    (tmp_path / "cases" / "m-snapshot-read-901-page-invariance-batch-size-twin-2.yaml").unlink()

    errors = batch_size_twin_errors(tmp_path)
    assert any("has one member" in error for error in errors)


def test_the_declared_page_size_must_match_the_filename(tmp_path: Path) -> None:
    _corpus(tmp_path)
    _write(
        tmp_path / "cases" / "m-snapshot-read-901-page-invariance-batch-size-twin-2.yaml",
        _case(3, pages=2),
    )

    errors = batch_size_twin_errors(tmp_path)
    assert any("filename declares batch size 2" in error for error in errors)


def test_a_name_outside_the_module_catalog_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path)
    _write(
        tmp_path / "cases" / "not-a-module-900-page-invariance-batch-size-twin-4.yaml",
        _case(4, pages=1),
    )

    errors = batch_size_twin_errors(tmp_path)
    assert any("must begin with a catalog module" in error for error in errors)


def test_a_missing_corpus_directory_is_reported(tmp_path: Path) -> None:
    assert batch_size_twin_errors(tmp_path / "absent") == [
        f"not a directory: {tmp_path / 'absent'}"
    ]
