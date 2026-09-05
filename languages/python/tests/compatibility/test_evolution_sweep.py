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


def test_an_evolution_case_compiles_as_run_only() -> None:
    # No golden SQL exists to compile, so `compile` answers the shape-intrinsic
    # run-only envelope rather than deriving emissions from nothing.
    envelope = adapter.compile_case(_REACHABLE_EVOLUTION[0].path, "postgres")
    jsonschema.validate(envelope, _SCHEMA)
    assert envelope["status"] == "run-only"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"
