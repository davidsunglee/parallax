from __future__ import annotations

import argparse
import json
import types
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

import validate_wheel


def _wheel(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def test_driver_resolution_uses_the_candidate_metadata_constraint(tmp_path: Path) -> None:
    wheel = _wheel(
        tmp_path / "adapter.whl",
        {"adapter.dist-info/METADATA": b"Requires-Dist: psycopg[binary]>=3.3.8,<3.4\n"},
    )
    assert validate_wheel.driver_requirement(wheel, "c") == "psycopg[c]>=3.3.8,<3.4"


def test_validation_tool_versions_follow_authoritative_dev_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["pytest>=10", "filelock>=5", "sqlglot>=31", "ruff>=1"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_wheel, "PY_ROOT", tmp_path)
    assert validate_wheel.validation_dependencies() == ["pytest>=10", "filelock>=5", "sqlglot>=31"]


@pytest.mark.parametrize("change", ["replaced", "source-fallback", "namespace-fallback"])
def test_installed_identity_refuses_changed_bytes_and_source_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    relative = "parallax/postgres/__init__.py"
    wheel = _wheel(tmp_path / "adapter.whl", {relative: b"candidate = True\n"})
    site = tmp_path / "site-packages"
    installed = site / relative
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"candidate = True\n")
    module = types.ModuleType("parallax.postgres")
    module.__file__ = str(installed)
    namespace = types.ModuleType("parallax")
    namespace.__path__ = [str(site / "parallax")]
    monkeypatch.setattr(
        validate_wheel,
        "sys",
        types.SimpleNamespace(modules={"parallax.postgres": module, "parallax": namespace}),
    )

    def site_path(_name: str) -> str:
        return str(site)

    monkeypatch.setattr(validate_wheel.sysconfig, "get_path", site_path)
    assert validate_wheel.installed_origins([wheel]) == {"parallax.postgres": str(installed)}

    if change == "replaced":
        installed.write_text("candidate = False\n", encoding="utf-8")
    elif change == "source-fallback":
        module.__file__ = str(tmp_path / "checkout" / relative)
    else:
        namespace.__path__.append(str(tmp_path / "checkout" / "parallax"))

    with pytest.raises(RuntimeError, match=r"does not match|escaped installed"):
        validate_wheel.installed_origins([wheel])


def test_missing_database_fails_and_retains_candidate_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _wheel(tmp_path / "adapter.whl", {})
    companions = tmp_path / "companions"
    companions.mkdir()
    output = tmp_path / "validation"
    monkeypatch.delenv("PARALLAX_WHEEL_DSN", raising=False)
    assert (
        validate_wheel.main(
            [
                "--wheel",
                str(wheel),
                "--companions",
                str(companions),
                "--output",
                str(output),
                "--postgres-version",
                "18.6",
            ]
        )
        == 1
    )
    result = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["wheel"] == {"filename": wheel.name, "sha256": validate_wheel.digest(wheel)}
    assert "PARALLAX_WHEEL_DSN" in result["error"]
    assert result["drivers"] == {}


def test_junit_keeps_skips_errors_and_failures_distinct(tmp_path: Path) -> None:
    report = tmp_path / "tests.xml"
    report.write_text(
        "<testsuites><testsuite>"
        "<testcase/><testcase><skipped/></testcase><testcase><failure/></testcase>"
        "<testcase><error/></testcase></testsuite></testsuites>",
        encoding="utf-8",
    )
    assert validate_wheel.test_counts(report) == {
        "passed": 1,
        "skipped": 1,
        "failed": 1,
        "errors": 1,
    }


def test_windows_registers_system_libpq_until_the_installed_driver_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _wheel(tmp_path / "adapter.whl", {})
    companions = tmp_path / "companions"
    companions.mkdir()
    binary = tmp_path / "postgres" / "bin"
    events: list[str] = []

    @contextmanager
    def directory(path: str) -> Generator[None]:
        assert path == str(binary)
        events.append("registered")
        try:
            yield
        finally:
            events.append("closed")

    def exercise(args: argparse.Namespace) -> int:
        assert args.driver == "c"
        assert events == ["registered"]
        events.append("driver imported and tested")
        return 0

    def pg_config(_command: str) -> str:
        return str(binary / "pg_config.exe")

    monkeypatch.setattr(validate_wheel, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(validate_wheel.shutil, "which", pg_config)
    monkeypatch.setattr(validate_wheel.os, "add_dll_directory", directory, raising=False)
    monkeypatch.setattr(validate_wheel, "_exercise", exercise)

    assert (
        validate_wheel.main(
            [
                "--wheel",
                str(wheel),
                "--companions",
                str(companions),
                "--output",
                str(tmp_path / "out"),
                "--postgres-version",
                "18.6",
                "--driver",
                "c",
            ]
        )
        == 0
    )
    assert events == ["registered", "driver imported and tested", "closed"]
