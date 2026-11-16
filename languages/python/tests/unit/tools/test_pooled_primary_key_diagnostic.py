"""The pooled primary-key diagnostic launcher: where it writes, what it runs,
and what it requires of the suite it runs."""

from __future__ import annotations

from pathlib import Path

import pytest

import pooled_primary_key_diagnostic as launcher


def test_the_output_must_be_a_new_or_empty_directory_under_an_existing_parent(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit, match="does not exist"):
        launcher.prepared_output(tmp_path / "absent" / "capture")
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "live.json").write_text("{}")
    with pytest.raises(SystemExit, match="already holds a capture"):
        launcher.prepared_output(taken)
    assert launcher.prepared_output(tmp_path / "fresh").is_dir()


def test_every_suite_names_sources_that_exist() -> None:
    for suite in launcher.SUITES.values():
        for source in (suite.target.split("::")[0], *suite.sources):
            assert (launcher.WORKSPACE / source).is_file(), source


def test_only_a_database_suite_requires_its_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PARALLAX_REQUIRE_DB", raising=False)
    live = launcher.environment(launcher.SUITES["live"], "assigned", tmp_path)
    memory = launcher.environment(launcher.SUITES["pool-memory"], "assigned", tmp_path)
    assert live["PARALLAX_REQUIRE_DB"] == "1"
    assert "PARALLAX_REQUIRE_DB" not in memory
    assert live[launcher.OUT_VARIABLE] == str(tmp_path)
    assert live[launcher.MODE_VARIABLE] == "assigned"
