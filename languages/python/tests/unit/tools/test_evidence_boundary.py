from __future__ import annotations

from pathlib import Path

import pytest

from evidence_boundary import digest, local_module, measurement_source, measurement_sources

_MEASURING = '''"""A report."""

import json

from tests.unit import support


def measure() -> int:
    return len(json.dumps(support.WORK))
'''

_DIAGNOSING = """

def _marks(work: object) -> object:
    return work


@_marks
def chosen() -> str:
    return "a subset"


def main() -> int:
    print(measure())
    return 0
"""


def _workspace(root: Path) -> Path:
    (root / "tools").mkdir()
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "tests" / "unit" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "unit" / "support.py").write_text(
        "from tests.unit import reused\nfrom tests.unit.reused import WORK\n", encoding="utf-8"
    )
    (root / "tests" / "unit" / "reused.py").write_text("WORK = {'a': 1}\n", encoding="utf-8")
    return root


def _report(workspace: Path, source: str = _MEASURING + _DIAGNOSING) -> Path:
    module = workspace / "tools" / "report.py"
    module.write_text(source, encoding="utf-8")
    return module


def test_a_name_this_workspace_does_not_own_resolves_to_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    assert local_module("json", workspace) is None
    assert local_module("tests.unit.support", workspace) == workspace / "tests/unit/support.py"
    assert local_module("tests.unit", workspace) == workspace / "tests/unit/__init__.py"


def test_the_closure_reaches_every_workspace_module_a_root_imports(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = _report(workspace)

    assert measurement_sources((report,), workspace) == (
        workspace / "tests/unit/__init__.py",
        workspace / "tests/unit/reused.py",
        workspace / "tests/unit/support.py",
        report,
    )


def test_an_instrument_that_imports_relatively_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = _report(workspace, "from . import sibling\n")

    with pytest.raises(ValueError, match="absolute name only"):
        measurement_sources((report,), workspace)


def test_only_the_named_declarations_leave_the_digested_source(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    report = _report(workspace)
    excluded = ("chosen", "main")

    kept = measurement_source(report, excluded)

    assert b"def measure" in kept
    assert b"def chosen" not in kept and b"@_marks" not in kept and b"def main" not in kept
    assert measurement_source(report) == report.read_bytes()
    assert measurement_source(_report(workspace, _MEASURING + _DIAGNOSING + "\n\n"), excluded) != (
        kept
    )


def test_editing_an_excluded_declaration_leaves_the_digested_source_unchanged(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    excluded = ("chosen", "main")
    kept = measurement_source(_report(workspace), excluded)

    edited = _report(workspace, _MEASURING + _DIAGNOSING.replace("a subset", "another subset"))

    assert measurement_source(edited, excluded) == kept
    assert measurement_source(_report(workspace, _MEASURING.replace("len", "id")), ()) != kept


def test_an_exclusion_naming_no_declaration_is_refused(tmp_path: Path) -> None:
    report = _report(_workspace(tmp_path))

    with pytest.raises(ValueError, match=r"report\.py declares no absent, missing"):
        measurement_source(report, ("main", "missing", "absent"))


def test_the_digest_covers_the_workloads_and_every_source_but_what_each_excludes(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    report = _report(workspace)
    sources = measurement_sources((report,), workspace)
    excluded = {report: ("chosen", "main")}
    original = digest("workloads", sources, excluded)

    assert digest("other workloads", sources, excluded) != original
    assert digest("workloads", sources, {}) != original
    _report(workspace, _MEASURING + _DIAGNOSING.replace("a subset", "another subset"))
    assert digest("workloads", sources, excluded) == original
    (workspace / "tests/unit/reused.py").write_text("WORK = {'a': 2}\n", encoding="utf-8")
    assert digest("workloads", sources, excluded) != original
