"""Unit tests for the harness's live-database access guard.

The guard is what makes the derived scheduling class trustworthy, so the canary
matters more than usual: a guard that only ever returns 0 is indistinguishable
from no guard, and the state it exists to catch fails silently on a host with
Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

from reference_harness import check_database_access as access

_TESTS_ROOT = Path(__file__).resolve().parent


def _seams(source: str) -> list[str]:
    return [target for _line, target in access.seam_calls(ast.parse(source))]


def _minimal_tree(root: Path) -> None:
    """A tests root the guard finds clean: the designated fixture, acquiring the
    database, and a classifier designating exactly it."""
    (root / "conftest.py").write_text('_DATABASE_FIXTURES = frozenset({"provider"})\n')
    (root / "test_compatibility.py").write_text(
        "from reference_harness.providers import provider_for\n"
        "\n"
        "\n"
        "def provider(request):\n"
        "    with provider_for(request.param) as db:\n"
        "        yield db\n"
    )


# --------------------------------------------------------------------------
# Call resolution: a seam is what a call reaches, not what it is spelled
# --------------------------------------------------------------------------
def test_a_seam_imported_directly_is_found() -> None:
    assert _seams("from reference_harness.providers import provider_for\nprovider_for('pg')\n") == [
        "reference_harness.providers.provider_for"
    ]


def test_a_seam_reached_through_its_module_is_found() -> None:
    assert _seams("from reference_harness import providers\nproviders.provider_for('pg')\n") == [
        "reference_harness.providers.provider_for"
    ]


def test_a_seam_reached_under_an_alias_is_found() -> None:
    assert _seams("from reference_harness.providers import provider_for as boot\nboot('pg')\n") == [
        "reference_harness.providers.provider_for"
    ]


def test_the_container_classes_are_seams() -> None:
    assert _seams(
        "from testcontainers.mysql import MySqlContainer\n"
        "from testcontainers.postgres import PostgresContainer\n"
        "MySqlContainer('img')\n"
        "PostgresContainer('img')\n"
    ) == ["testcontainers.mysql.MySqlContainer", "testcontainers.postgres.PostgresContainer"]


def test_the_cli_entry_points_that_boot_providers_are_seams() -> None:
    assert _seams("from reference_harness import benchmark\nbenchmark.main([])\n") == [
        "reference_harness.benchmark.main"
    ]
    assert _seams("from reference_harness.matrix import main\nmain([])\n") == [
        "reference_harness.matrix.main"
    ]


def test_importing_a_provider_module_for_its_pure_functions_is_not_a_violation() -> None:
    assert (
        _seams("from reference_harness.providers.mariadb import normalize\nnormalize('select 1')\n")
        == []
    )


def test_a_local_name_that_merely_looks_like_a_seam_is_not_one() -> None:
    assert _seams("def fake_provider_for(dialect):\n    ...\n\n\nfake_provider_for('pg')\n") == []


# --------------------------------------------------------------------------
# Structural preconditions: the rule is vacuous without them
# --------------------------------------------------------------------------
def test_a_minimal_tree_is_clean(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    assert access.audit(tmp_path) == []


def test_a_seam_call_outside_the_designated_fixture_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    (tmp_path / "test_rogue.py").write_text(
        "from reference_harness.providers import provider_for\n"
        "\n"
        "\n"
        "def test_rogue():\n"
        "    with provider_for('postgres') as db:\n"
        "        assert db\n"
    )
    (finding,) = access.audit(tmp_path)
    assert finding.path == "test_rogue.py"
    assert finding.line == 5
    assert "provider" in finding.message


def test_a_seam_call_elsewhere_in_the_designated_module_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    entry = tmp_path / access.ENTRY_POINT_MODULE
    entry.write_text(
        entry.read_text() + "\n\ndef warm_up():\n    with provider_for('postgres'):\n        pass\n"
    )
    (finding,) = access.audit(tmp_path)
    assert finding.path == access.ENTRY_POINT_MODULE


def test_a_missing_designated_fixture_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    (tmp_path / access.ENTRY_POINT_MODULE).write_text("def other():\n    ...\n")
    (finding,) = access.audit(tmp_path)
    assert "is not defined here" in finding.message


def test_a_classifier_designating_a_different_fixture_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    classifier = tmp_path / access.CLASSIFIER_MODULE
    classifier.write_text(classifier.read_text().replace('"provider"', '"other"'))
    (finding,) = access.audit(tmp_path)
    assert access.CLASSIFIER_CONSTANT in finding.message


# --------------------------------------------------------------------------
# Canary: the real tree passes, a planted rogue acquisition blocks
# --------------------------------------------------------------------------
def test_the_real_test_tree_confines_database_access() -> None:
    assert access.main([]) == 0


def test_an_argument_is_a_usage_error() -> None:
    assert access.main(["tests"]) == 2


def test_a_planted_rogue_acquisition_fails() -> None:
    # Named `_canary_*` rather than `test_*` so it can never be collected.
    canary = _TESTS_ROOT / "_canary_database_access.py"
    canary.write_text(
        "from reference_harness.providers import provider_for\n"
        "\n"
        "\n"
        "def reach_a_database():\n"
        "    with provider_for('postgres') as db:\n"
        "        return db\n"
    )
    try:
        assert access.main([]) == 1
    finally:
        canary.unlink()
    assert access.main([]) == 0
