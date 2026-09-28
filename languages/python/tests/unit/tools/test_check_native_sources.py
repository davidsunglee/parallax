"""Unit tests for the Cython source confinement and exemption check.

The real tree must pass, and a scratch checkout carrying each planted fault must
fail naming it: a check that only ever passes cannot be told apart from no
check at all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import check_native_sources as native

_PACKAGE = "packages/parallax-postgres/src/parallax/postgres"


def _exclude(*paths: str) -> str:
    entries = ", ".join(f'"*/{path}"' for path in paths)
    return f"[tool.diff_cover]\nexclude = [{entries}]\n"


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch repository whose Python root holds one exempted Cython source."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    python = tmp_path / "languages" / "python"
    (python / _PACKAGE).mkdir(parents=True)
    (python / _PACKAGE / "_loaders.pyx").write_text("")
    (python / "pyproject.toml").write_text(_exclude(f"{_PACKAGE}/_loaders.pyx"))
    monkeypatch.setattr(native, "PY_ROOT", python)
    return python


def test_the_real_tree_is_confined_and_exempted() -> None:
    assert native.main([]) == 0


def test_a_confined_and_exempted_source_passes(checkout: Path) -> None:
    assert native.main([]) == 0


def test_sources_are_found_tracked_or_not_but_never_ignored(checkout: Path) -> None:
    (checkout / "tools").mkdir()
    (checkout / "tools" / "tracked.pxd").write_text("")
    subprocess.run(["git", "add", "tools/tracked.pxd"], cwd=checkout, check=True)
    (checkout / ".venv").mkdir()
    (checkout / ".venv" / "cython.pxd").write_text("")
    (checkout.parents[1] / ".gitignore").write_text(".venv/\n")

    assert native.cython_sources(checkout) == [
        f"languages/python/{_PACKAGE}/_loaders.pyx",
        "languages/python/tools/tracked.pxd",
    ]


def test_a_source_outside_the_adapter_package_fails(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    escaped = "packages/parallax-core/src/parallax/core/_fast.pyx"
    (checkout / escaped).parent.mkdir(parents=True)
    (checkout / escaped).write_text("")
    (checkout / "pyproject.toml").write_text(_exclude(f"{_PACKAGE}/_loaders.pyx", escaped))

    assert native.main([]) == 1
    assert f"languages/python/{escaped}" in capsys.readouterr().err


def test_an_unexempted_source_and_a_stale_exemption_both_fail(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (checkout / _PACKAGE / "_body.pxi").write_text("")
    (checkout / "pyproject.toml").write_text(
        _exclude(f"{_PACKAGE}/_loaders.pyx", f"{_PACKAGE}/_retired.pyx")
    )

    assert native.main([]) == 1
    report = capsys.readouterr().err
    assert f"does not name:\n    languages/python/{_PACKAGE}/_body.pxi" in report
    assert f"naming no Cython source:\n    languages/python/{_PACKAGE}/_retired.pyx" in report


def test_a_missing_exemption_table_exempts_nothing(checkout: Path) -> None:
    (checkout / "pyproject.toml").write_text("")

    assert native.main([]) == 1


def test_an_unreadable_checkout_raises_rather_than_passing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="git ls-files"):
        native.cython_sources(tmp_path)
