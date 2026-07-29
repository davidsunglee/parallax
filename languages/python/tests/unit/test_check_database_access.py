"""Unit tests for the live-database access guard.

The guard is what makes the derived scheduling class trustworthy, so the canary
matters more than usual: a guard that only ever returns 0 is indistinguishable
from no guard, and the state it exists to catch fails silently on a host with
Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import check_database_access as access

PY_ROOT = Path(__file__).resolve().parents[2]


def _seams(source: str) -> list[str]:
    return [target for _line, target in access.seam_calls(ast.parse(source))]


def _minimal_tree(root: Path) -> None:
    """A tests root the guard finds clean: the designated fixture, acquiring the
    database, and a classifier designating exactly it."""
    (root / "conftest.py").write_text(
        "_DATABASE_FIXTURES = frozenset({'provisioner'})\n"
        "\n"
        "\n"
        "def provisioner():\n"
        "    from parallax.conformance.provision import Provisioner\n"
        "\n"
        "    yield Provisioner()\n"
    )


# --------------------------------------------------------------------------
# Call resolution: a seam is what a call reaches, not what it is spelled
# --------------------------------------------------------------------------
def test_a_seam_imported_directly_is_found() -> None:
    assert _seams("from parallax.conformance.provision import Provisioner\nProvisioner()\n") == [
        "parallax.conformance.provision.Provisioner"
    ]


def test_a_seam_reached_through_its_module_is_found() -> None:
    assert _seams("from parallax.conformance import provision\nprovision.Provisioner()\n") == [
        "parallax.conformance.provision.Provisioner"
    ]


def test_a_seam_reached_under_an_alias_is_found() -> None:
    assert _seams("from parallax.conformance.provision import Provisioner as P\nP()\n") == [
        "parallax.conformance.provision.Provisioner"
    ]


def test_the_container_and_driver_seams_are_found() -> None:
    assert _seams(
        "import psycopg\n"
        "from testcontainers.postgres import PostgresContainer\n"
        "psycopg.connect('')\n"
        "PostgresContainer('img')\n"
    ) == ["psycopg.connect", "testcontainers.postgres.PostgresContainer"]


def test_the_adapter_connect_classmethod_is_a_seam_but_its_constructor_is_not() -> None:
    assert _seams(
        "from parallax.postgres import PostgresAdapter\nPostgresAdapter.connect('')\n"
    ) == ["parallax.postgres.PostgresAdapter.connect"]
    # The internal-behavior surface wraps fake connections with the adapter; that
    # opens nothing.
    assert _seams("from parallax.postgres import PostgresAdapter\nPostgresAdapter(fake)\n") == []


def test_a_local_name_that_merely_looks_like_a_seam_is_not_one() -> None:
    assert _seams("class _RaisingProvisioner:\n    pass\n\n\n_RaisingProvisioner()\n") == []
    assert (
        _seams("from parallax.snapshot.handle import Database\nDatabase.connect(port, meta)\n")
        == []
    )


def test_naming_a_seam_without_calling_it_is_not_a_violation() -> None:
    assert (
        _seams(
            "from parallax.conformance import provision\n"
            "monkeypatch.setattr(provision, 'Provisioner', _Raising)\n"
        )
        == []
    )


# --------------------------------------------------------------------------
# Structural preconditions: the rule is vacuous without them
# --------------------------------------------------------------------------
def test_a_minimal_tree_is_clean(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    assert access.audit(tmp_path) == []


def test_a_seam_call_outside_the_designated_fixture_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    (tmp_path / "test_rogue.py").write_text(
        "from parallax.conformance.provision import Provisioner\n"
        "\n"
        "\n"
        "def test_rogue():\n"
        "    Provisioner()\n"
    )
    (finding,) = access.audit(tmp_path)
    assert finding.path == "test_rogue.py"
    assert finding.line == 5
    assert "provisioner" in finding.message


def test_a_seam_call_elsewhere_in_the_designated_module_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        conftest.read_text() + "\n"
        "\n"
        "def other():\n"
        "    from parallax.conformance.provision import Provisioner\n"
        "\n"
        "    return Provisioner()\n"
    )
    (finding,) = access.audit(tmp_path)
    assert finding.path == "conftest.py"


def test_a_missing_designated_fixture_is_a_violation(tmp_path: Path) -> None:
    (tmp_path / "conftest.py").write_text("_DATABASE_FIXTURES = frozenset({'provisioner'})\n")
    (finding,) = access.audit(tmp_path)
    assert "is not defined here" in finding.message


def test_a_classifier_designating_a_different_fixture_is_a_violation(tmp_path: Path) -> None:
    _minimal_tree(tmp_path)
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        conftest.read_text().replace("frozenset({'provisioner'})", "frozenset({'other'})")
    )
    (finding,) = access.audit(tmp_path)
    assert access.CLASSIFIER_CONSTANT in finding.message


# --------------------------------------------------------------------------
# Canary: the real tree passes, a planted rogue acquisition blocks
# --------------------------------------------------------------------------
def test_the_real_test_tree_confines_database_access() -> None:
    assert access.main([]) == 0
    assert access.main(["--check"]) == 0


def test_a_planted_rogue_acquisition_fails() -> None:
    # Named `_canary_*` rather than `test_*` so it can never be collected.
    canary = PY_ROOT / "tests/unit/_canary_database_access.py"
    canary.write_text(
        "from parallax.conformance.provision import Provisioner\n"
        "\n"
        "\n"
        "def reach_a_database():\n"
        "    return Provisioner()\n"
    )
    try:
        assert access.main([]) == 1
    finally:
        canary.unlink()
    assert access.main([]) == 0
