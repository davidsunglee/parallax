"""Unit tests for the harness's live-database access guard.

The guard is what makes the derived scheduling class trustworthy, so the canary
matters more than usual: a guard that only ever returns 0 is indistinguishable
from no guard, and the state it exists to catch fails silently on a host with
Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from reference_harness import check_database_access as access


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
        "from testcontainers.community.mysql import MySqlContainer\n"
        "from testcontainers.community.postgres import PostgresContainer\n"
        "MySqlContainer('img')\n"
        "PostgresContainer('img')\n"
    ) == [
        "testcontainers.community.mysql.MySqlContainer",
        "testcontainers.community.postgres.PostgresContainer",
    ]


def test_the_cli_entry_points_that_boot_providers_are_seams() -> None:
    assert _seams("from reference_harness import benchmark\nbenchmark.main([])\n") == [
        "reference_harness.benchmark.main"
    ]
    assert _seams("from reference_harness.matrix import main\nmain([])\n") == [
        "reference_harness.matrix.main"
    ]


def test_a_seam_bound_to_a_local_name_and_called_through_it_is_found() -> None:
    # Binding first and calling second is the same acquisition, spelled so that the
    # dotted resolution sees only a plain name at the call. The three ways a name is
    # bound are one rule, so adding a type or an `if` does not escape it.
    assert _seams(
        "from reference_harness.providers import provider_for\nboot = provider_for\nboot('pg')\n"
    ) == ["reference_harness.providers.provider_for"]
    assert _seams(
        "from reference_harness.providers import provider_for\n"
        "boot: object = provider_for\n"
        "boot('pg')\n"
    ) == ["reference_harness.providers.provider_for"]
    assert _seams(
        "from reference_harness.providers import provider_for\n"
        "if (boot := provider_for):\n"
        "    boot('pg')\n"
    ) == ["reference_harness.providers.provider_for"]


def test_a_seam_reached_through_a_chain_of_local_names_is_found() -> None:
    # Rebinding costs one line, so a rule reading one hop only is escaped by adding
    # another; the bindings are followed until they stop growing instead, in whatever
    # order the module happens to write them.
    assert _seams(
        "from reference_harness.providers import provider_for\n"
        "boot = provider_for\n"
        "again = boot\n"
        "again('pg')\n"
    ) == ["reference_harness.providers.provider_for"]
    assert _seams(
        "from reference_harness.providers import provider_for\n"
        "def rogue():\n"
        "    return again('pg')\n"
        "again = boot\n"
        "boot = provider_for\n"
    ) == ["reference_harness.providers.provider_for"]


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
def test_every_declared_seam_names_a_callable() -> None:
    assert access.unresolved_seams() == ()


def test_a_seam_whose_attribute_was_renamed_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    renamed = "reference_harness.providers.provider_for_dialect"
    monkeypatch.setattr(access, "DATABASE_SEAMS", access.DATABASE_SEAMS | {renamed})
    assert access.unresolved_seams() == (renamed,)


def test_a_seam_whose_module_disappeared_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access, "DATABASE_SEAMS", frozenset({"reference_harness.pools.acquire"}))
    assert access.unresolved_seams() == ("reference_harness.pools.acquire",)


def test_a_seam_naming_something_uncallable_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        access, "DATABASE_SEAMS", frozenset({"reference_harness.providers.__doc__"})
    )
    assert access.unresolved_seams() == ("reference_harness.providers.__doc__",)


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


def test_a_planted_rogue_acquisition_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant goes into a scratch tree the audited root is pointed at, never
    into the real one: a canary interrupted mid-run would otherwise leave an
    untracked module behind and fail a sibling gate."""
    _minimal_tree(tmp_path)
    monkeypatch.setattr(access, "TESTS_ROOT", tmp_path)
    assert access.main([]) == 0

    (tmp_path / "test_rogue.py").write_text(
        "from reference_harness.providers import provider_for\n"
        "\n"
        "\n"
        "def test_rogue():\n"
        "    with provider_for('postgres') as db:\n"
        "        assert db\n"
    )
    assert access.main([]) == 1


def test_an_unresolved_seam_fails_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        access, "DATABASE_SEAMS", access.DATABASE_SEAMS | {"reference_harness.providers.acquire"}
    )
    assert access.main([]) == 1
