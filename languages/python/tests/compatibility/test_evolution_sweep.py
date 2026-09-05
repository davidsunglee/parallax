"""Docker-free evolution-case run sweep (m-conformance-adapter `run`,
m-case-format `evolution` cases).

An evolution case describes the difference between two accepted models and
executes nothing (m-case-format "Evolution cases"): grading its `run` envelope
needs no provisioning, so — unlike `test_run_sweep.py`, whose every test function
threads the Testcontainers `profile_run` fixture — this sweep runs entirely
in-process. The described `evolution` observation is compared against the case's
own `then.evolution` WHOLE, because the returned Evolution is one internally
consistent value, and a :class:`_RefusingPort` proves the "no database" contract
structurally, the same way the rejected and compile lanes prove theirs.

Pure, Docker-free, in-process behaviour, so it classifies `dbfree` and
contributes to the database-free branch-coverage gate even though the rest of
`tests/compatibility/` needs a database.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import jsonschema
import pytest

from _support.corpus import case_document
from _support.repo import adapter_schema
from parallax.conformance import adapter, case_format, sweep
from parallax.conformance.profile import profile_for
from parallax.core.db_port import DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect

_SCHEMA = adapter_schema()
# The declared profile an evolution `run` is requested under, read off the one
# roster. Nothing here provisions it: the refusing port below stands in for the
# container the shape never needs, and the envelope still names the profile the
# request was made against.
_PROFILE = profile_for("pg-full")
_REACHABLE_EVOLUTION = [c for c in sweep.reachable_cases() if c.shape == "evolution"]


class _RefusingPort:
    """An `m-db-port` that fails loudly if the evolution lane ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        raise AssertionError(f"an evolution-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"an evolution-case run must not execute SQL: {sql!r}")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise AssertionError("an evolution-case run must not open a transaction")


def _expected(case: case_format.Case) -> dict[str, Any]:
    return cast("dict[str, Any]", case_document(case)["then"]["evolution"])


def _expected_schema(case: case_format.Case) -> dict[str, Any] | None:
    then = cast("dict[str, Any]", case_document(case)["then"])
    matrix = then.get("schema")
    return cast("dict[str, Any]", matrix) if matrix is not None else None


@pytest.mark.parametrize(
    "case", _REACHABLE_EVOLUTION, ids=[c.case_id for c in _REACHABLE_EVOLUTION]
)
def test_evolution_sweep(case: case_format.Case) -> None:
    envelope = adapter.run_case(case.path, _PROFILE.on_stand_in(_RefusingPort()))
    jsonschema.validate(envelope, _SCHEMA)

    assert envelope["status"] == "ok", envelope
    assert envelope["emissions"] == []
    observations = envelope["observations"]
    assert observations["roundTrips"] == 0
    assert observations["evolution"] == _expected(case)
    expected_schema = _expected_schema(case)
    if expected_schema is not None:
        # A cell this implementation has no Dialect for is authored as the delta
        # some implementation must produce; the run reports it as an explicit
        # exclusion instead, which is a counted gap rather than a match.
        graded = {
            name: cell for name, cell in observations["schema"].items() if "excluded" not in cell
        }
        assert graded == {name: cell for name, cell in expected_schema.items() if name in graded}


def test_reachable_evolution_population_is_non_empty() -> None:
    assert _REACHABLE_EVOLUTION, "the reachable intersection lost its evolution-shape cases"


def test_the_reachable_population_covers_both_earlier_endpoint_forms() -> None:
    # `when.evolve.earlier` is either a model descriptor path or the explicit
    # fresh-provisioning sentinel, and the two reach `evolve` as different
    # arguments — a model, and `ABSENT`. Both dispatch arms need a witness.
    endpoints = {
        case_document(case)["when"]["evolve"]["earlier"] is None for case in _REACHABLE_EVOLUTION
    }
    assert endpoints == {True, False}, endpoints


def test_the_matrix_reports_every_catalog_dialect_and_excludes_the_missing_one() -> None:
    # The supported Dialect catalog is the SPEC's, so the envelope answers for
    # `mariadb` even though this implementation ships no strategy for it: the
    # gap is named with its reason rather than left out of the matrix.
    provisioning = [
        case for case in _REACHABLE_EVOLUTION if "provisioning" in case_document(case)["tags"]
    ]
    assert provisioning, "the reachable population lost its provisioning cases"
    for case in provisioning:
        envelope = adapter.run_case(case.path, _PROFILE.on_stand_in(_RefusingPort()))
        matrix = envelope["observations"]["schema"]
        assert sorted(matrix) == ["mariadb", "postgres"], case.path.name
        assert matrix["mariadb"] == {"excluded": {"reason": "no-dialect"}}, case.path.name
        assert "delta" in matrix["postgres"], case.path.name


def test_a_coordinated_description_reports_no_schema_matrix() -> None:
    # A Coordinated Evolution is not an input to schema generation at all, so
    # there is no cell to report — not an empty one, and not an excluded one.
    coordinated = [
        case
        for case in _REACHABLE_EVOLUTION
        if case_document(case)["then"]["evolution"]["kind"] == "coordinated"
    ]
    assert coordinated, "the reachable population lost its coordinated cases"
    envelope = adapter.run_case(coordinated[0].path, _PROFILE.on_stand_in(_RefusingPort()))
    assert "schema" not in envelope["observations"]


def test_an_evolution_case_compiles_as_run_only() -> None:
    # No golden SQL exists to compile, so `compile` answers the shape-intrinsic
    # run-only envelope rather than deriving emissions from nothing.
    envelope = adapter.compile_case(_REACHABLE_EVOLUTION[0].path, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "run-only"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"
