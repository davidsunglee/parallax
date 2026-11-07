"""The authored-corpus proof that a Sharing Scope changes no observation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from reference_harness.sharing_scope_twin_check import main, sharing_scope_twin_errors

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_ROOT_ARM = "m-snapshot-read-900-repeated-sharing-scope-twin-root.yaml"
_PAGE_ARM = "m-snapshot-read-901-repeated-sharing-scope-twin-page.yaml"


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _case(
    scope: str | None,
    *,
    sql: str = "select t0.id from item t0",
    values: list[int] | None = None,
    graph: list[dict[str, Any]] | None = None,
    database_calls: int = 1,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    when: dict[str, Any] = {
        "objectQuery": {
            "target": "example.Item",
            "predicate": {"in": {"path": "example.Item.id", "values": values or [1, 2]}},
        }
    }
    if scope is not None:
        when["sharingScope"] = scope
    return {
        "model": "models/item.yaml",
        "tags": tags or ["m-snapshot-read"],
        "shape": "read",
        "when": when,
        "then": {
            "statements": [{"sql": {"postgres": sql}}],
            "graph": {"Item": graph if graph is not None else [{"id": 1}, {"id": 2}]},
            "databaseCalls": database_calls,
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
    _write(root / "cases" / _ROOT_ARM, _case("root"))
    _write(root / "cases" / _PAGE_ARM, _case("page"))


def test_real_corpus_sharing_scope_twins_are_complete() -> None:
    assert sharing_scope_twin_errors(_COMPATIBILITY_ROOT) == []


def test_arms_differing_only_in_scope_pass(tmp_path: Path) -> None:
    _corpus(tmp_path)
    assert sharing_scope_twin_errors(tmp_path) == []


@pytest.mark.parametrize(
    "drifted",
    [
        _case("page", values=[1], graph=[{"id": 1}]),
        _case("page", sql="select t0.id from item t0 -- page"),
        _case("page", database_calls=2),
        _case("page", tags=["m-snapshot-read", "extra"]),
    ],
    ids=["query-and-graph", "statements", "database-calls", "tags"],
)
def test_an_arm_differing_anywhere_else_is_refused(tmp_path: Path, drifted: dict[str, Any]) -> None:
    _corpus(tmp_path)
    _write(tmp_path / "cases" / _PAGE_ARM, drifted)

    assert any(
        "differ in more than when.sharingScope" in error
        for error in sharing_scope_twin_errors(tmp_path)
    )


def test_a_lone_arm_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path)
    (tmp_path / "cases" / _PAGE_ARM).unlink()

    assert any("has arms ['root']" in error for error in sharing_scope_twin_errors(tmp_path))


def test_an_arm_naming_no_scope_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path)
    (tmp_path / "cases" / _PAGE_ARM).unlink()
    _write(
        tmp_path / "cases" / "m-snapshot-read-901-repeated-sharing-scope-twin-global.yaml",
        _case("page"),
    )

    assert any(
        "has arms ['global', 'root']" in error for error in sharing_scope_twin_errors(tmp_path)
    )


@pytest.mark.parametrize("declared", ["root", None], ids=["the-other-scope", "none"])
def test_the_declared_scope_must_match_the_filename(tmp_path: Path, declared: str | None) -> None:
    _corpus(tmp_path)
    _write(tmp_path / "cases" / _PAGE_ARM, _case(declared))

    assert any(
        "filename declares sharing scope page" in error
        for error in sharing_scope_twin_errors(tmp_path)
    )


def test_a_name_outside_the_module_catalog_is_refused(tmp_path: Path) -> None:
    _corpus(tmp_path)
    _write(
        tmp_path / "cases" / "not-a-module-900-repeated-sharing-scope-twin-root.yaml",
        _case("root"),
    )

    assert any(
        "must begin with a catalog module" in error for error in sharing_scope_twin_errors(tmp_path)
    )


@pytest.mark.parametrize(
    ("root_name", "page_name"),
    [
        ("m-snapshot-read-900-repeated.yaml", "m-snapshot-read-901-repeated.yaml"),
        (
            "m-snapshot-read-900-repeated-sharing-scope-twin-root.v2.yaml",
            "m-snapshot-read-901-repeated-sharing-scope-twin-page.v2.yaml",
        ),
    ],
    ids=["ordinary-names", "dotted-arm-suffixes"],
)
def test_a_scope_declared_outside_the_twin_grammar_is_refused(
    tmp_path: Path, root_name: str, page_name: str
) -> None:
    _corpus(tmp_path)
    (tmp_path / "cases" / _ROOT_ARM).rename(tmp_path / "cases" / root_name)
    (tmp_path / "cases" / _PAGE_ARM).rename(tmp_path / "cases" / page_name)

    errors = sharing_scope_twin_errors(tmp_path)

    assert len(errors) == 2
    assert all("only a sharing-scope twin may declare" in error for error in errors)
    assert {error.split(":")[0] for error in errors} == {root_name, page_name}


def test_a_case_declaring_no_scope_needs_no_twin(tmp_path: Path) -> None:
    _corpus(tmp_path)
    _write(tmp_path / "cases" / "m-snapshot-read-902-plain.yaml", _case(None))

    assert sharing_scope_twin_errors(tmp_path) == []


def test_an_unreadable_case_outside_the_twin_grammar_is_reported(tmp_path: Path) -> None:
    _corpus(tmp_path)
    unreadable = "m-snapshot-read-902-plain.yaml"
    (tmp_path / "cases" / unreadable).write_text("- a list\n", encoding="utf-8")

    assert sharing_scope_twin_errors(tmp_path) == [
        f"{unreadable}: compatibility case is not a mapping"
    ]


def test_an_unreadable_arm_is_reported_and_not_compared(tmp_path: Path) -> None:
    _corpus(tmp_path)
    (tmp_path / "cases" / _PAGE_ARM).write_text("- a list\n", encoding="utf-8")

    assert sharing_scope_twin_errors(tmp_path) == [
        f"{_PAGE_ARM}: compatibility case is not a mapping"
    ]


def test_a_missing_corpus_directory_is_reported(tmp_path: Path) -> None:
    assert sharing_scope_twin_errors(tmp_path / "absent") == [
        f"not a directory: {tmp_path / 'absent'}"
    ]


def test_the_gate_answers_through_its_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path)
    assert main([str(tmp_path)]) == 0
    assert "gate OK" in capsys.readouterr().out

    (tmp_path / "cases" / _PAGE_ARM).unlink()
    assert main([str(tmp_path)]) == 1
    assert "gate FAILED" in capsys.readouterr().err

    assert main([]) == 2
