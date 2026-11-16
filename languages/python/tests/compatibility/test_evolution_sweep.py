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

import pytest

from parallax.conformance import adapter, case_format, models
from parallax.conformance._mechanism.model_facts import model_path
from parallax.conformance.bindings import binding_document
from parallax.conformance.profile import profile_for
from parallax.core.internal.database_binding import (
    AllocatorSettingsChanged,
    ResolvedBinding,
    SequenceRelocated,
    TableRelocated,
)
from parallax.core.internal.db_port import DatabaseConnection, Row, TransactionOutcome
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.evolution import (
    CoordinatedEvolution,
    CoordinationReason,
    ManualAction,
    ManualStep,
    coordinated_migration,
    schema_delta,
)
from parallax.evolution.internal.model_evolution import evolve_resolved
from parallax.postgres import PostgresBinding
from tests._support.case_corpus import reachable_cases
from tests._support.corpus import case_document
from tests._support.db_port import ConnectsAsItself
from tests._support.repo import validate_adapter_envelope

# The declared profile an evolution `run` is requested under, read off the one
# roster. Nothing here provisions it: the refusing port below stands in for the
# container the shape never needs, and the envelope still names the profile the
# request was made against.
_PROFILE = profile_for("pg-full")
_REACHABLE_EVOLUTION = [c for c in reachable_cases() if c.shape == "evolution"]


class _RefusingPort(ConnectsAsItself):
    """An `m-db-port` that fails loudly if the evolution lane ever touches it."""

    dialect: Dialect = POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        raise AssertionError(f"an evolution-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise AssertionError(f"an evolution-case run must not execute SQL: {sql!r}")

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        raise AssertionError("an evolution-case run must not open a transaction")


def _expected(case: case_format.Case) -> dict[str, Any]:
    return cast("dict[str, Any]", case_document(case)["then"]["evolution"])


def _expected_matrix(case: case_format.Case, member: str) -> dict[str, Any] | None:
    then = cast("dict[str, Any]", case_document(case)["then"])
    matrix = then.get(member)
    return cast("dict[str, Any]", matrix) if matrix is not None else None


def _graded(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    # A cell this implementation has no Dialect for is authored as the answer
    # some implementation must produce; the run reports it as an explicit
    # exclusion instead, which is a counted gap rather than a match.
    graded = {name: cell for name, cell in observed.items() if "excluded" not in cell}
    assert graded == {name: cell for name, cell in expected.items() if name in graded}


@pytest.mark.parametrize(
    "case", _REACHABLE_EVOLUTION, ids=[c.case_id for c in _REACHABLE_EVOLUTION]
)
def test_evolution_sweep(case: case_format.Case) -> None:
    envelope = adapter.run_case(case.path, _PROFILE.on_stand_in(_RefusingPort()))
    validate_adapter_envelope(envelope)

    assert envelope["status"] == "ok", envelope
    assert envelope["emissions"] == []
    observations = envelope["observations"]
    assert observations["databaseCalls"] == 0
    assert observations["evolution"] == _expected(case)
    for member in ("schema", "migration"):
        expected = _expected_matrix(case, member)
        if expected is not None:
            _graded(observations[member], expected)


def test_reachable_evolution_population_is_non_empty() -> None:
    assert _REACHABLE_EVOLUTION, "the reachable intersection lost its evolution-shape cases"


def test_the_reachable_population_covers_both_earlier_endpoint_forms() -> None:
    # `when.evolve.earlier` is either a model descriptor path or the explicit
    # fresh-provisioning sentinel, and the two reach `evolve` as different
    # arguments — a model, and `ABSENT`. Both dispatch cases need a witness.
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


def test_each_description_reports_the_one_matrix_its_kind_generates() -> None:
    # A Coordinated Evolution is not an input to schema generation at all, nor a
    # Unilateral one to coordinated migration, so each reports the other's
    # matrix not as an empty or excluded cell but not at all.
    by_kind = {
        kind: [
            case
            for case in _REACHABLE_EVOLUTION
            if case_document(case)["then"]["evolution"]["kind"] == kind
        ]
        for kind in ("unilateral", "coordinated")
    }
    for kind, reported, absent in (
        ("unilateral", "schema", "migration"),
        ("coordinated", "migration", "schema"),
    ):
        assert by_kind[kind], f"the reachable population lost its {kind} cases"
        envelope = adapter.run_case(by_kind[kind][0].path, _PROFILE.on_stand_in(_RefusingPort()))
        assert reported in envelope["observations"]
        assert absent not in envelope["observations"]


_COORDINATED_EVOLUTION = [
    case
    for case in _REACHABLE_EVOLUTION
    if case_document(case)["then"]["evolution"]["kind"] == "coordinated"
]


def _evolution_of(case: case_format.Case) -> CoordinatedEvolution:
    document = case_document(case)
    named = document["when"]["evolve"]
    inherited = document.get("binding")

    def endpoint(model: str, binding: object) -> ResolvedBinding:
        return ResolvedBinding(
            models.load_model(model_path(model)),
            PostgresBinding.from_document(
                binding_document(binding, "postgres", inherited=inherited)
            ),
        )

    evolution = evolve_resolved(
        endpoint(named["earlier"], named.get("earlierBinding")),
        endpoint(named["later"], named.get("laterBinding")),
    )
    assert isinstance(evolution, CoordinatedEvolution), case.case_id
    return evolution


@pytest.mark.parametrize(
    "case", _COORDINATED_EVOLUTION, ids=[c.case_id for c in _COORDINATED_EVOLUTION]
)
def test_every_coordinated_fixture_migrates_completely(case: case_format.Case) -> None:
    evolution = _evolution_of(case)
    with pytest.raises(TypeError, match="use coordinated_migration"):
        schema_delta(evolution)  # pyright: ignore[reportArgumentType] - the refused input
    steps = coordinated_migration(evolution).steps

    def actions_naming(operation: object) -> set[ManualAction | None]:
        return {
            step.action if isinstance(step, ManualStep) else None
            for step in steps
            if operation in step.caused_by
        }

    for requirement in evolution.coordination_requirements:
        named = actions_naming(requirement.operation)
        if CoordinationReason.DATABASE_MIGRATION_REQUIRED in requirement.reasons:
            assert named - {ManualAction.UPDATE_AUTHORING_SURFACE}, requirement
        else:
            assert ManualAction.UPDATE_AUTHORING_SURFACE in named, requirement
            assert ManualAction.TRANSFORM_STORED_DATA not in named, requirement
    drains = [
        index
        for index, step in enumerate(steps)
        if isinstance(step, ManualStep) and step.action is ManualAction.DRAIN_EARLIER_ROOTS
    ]
    assert len(drains) <= 1
    if drains:
        assert drains == [0]
    for operation in evolution.operations:
        if isinstance(operation, TableRelocated | SequenceRelocated):
            assert {ManualAction.DRAIN_EARLIER_ROOTS, ManualAction.RELOCATE} <= actions_naming(
                operation
            )


def test_the_coordinated_population_covers_every_breaking_change_and_manual_action() -> None:
    evolutions = [_evolution_of(case) for case in _COORDINATED_EVOLUTION]
    assert {
        type(operation).__name__
        for evolution in evolutions
        for operation in evolution.operations
        if isinstance(operation, TableRelocated | SequenceRelocated | AllocatorSettingsChanged)
    } == {"TableRelocated", "SequenceRelocated", "AllocatorSettingsChanged"}
    assert {
        step.action
        for evolution in evolutions
        for step in coordinated_migration(evolution).steps
        if isinstance(step, ManualStep)
    } == set(ManualAction)


def test_an_evolution_case_compiles_as_run_only() -> None:
    # No golden SQL exists to compile, so `compile` answers the shape-intrinsic
    # run-only envelope rather than deriving emissions from nothing.
    envelope = adapter.compile_case(_REACHABLE_EVOLUTION[0].path, "postgres")
    validate_adapter_envelope(envelope)
    assert envelope["status"] == "run-only"
    assert envelope["diagnostics"][0]["code"] == "compile-run-only"
