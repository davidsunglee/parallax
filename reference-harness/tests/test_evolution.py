"""Evolution-case tests (m-model-evolution, m-schema-delta).

An `evolution` case describes the difference between two accepted Metamodels,
which executes nothing, so it is graded once rather than once per dialect and
this module is its sole runner — the counterpart of `test_rejected.py` for the
other shape the dialect-parametrized collection excludes, and the selection the
harness-lane partition there names.

What runs DB-free is layer 1: `then.evolution` is an authored golden, so the
harness grades that it COULD be one — closed vocabularies, every identity
resolving in the endpoint that must hold it, every ordered sequence actually
ordered. A language implementation grades the value itself through the
conformance adapter, exactly as it grades golden SQL against a run.

`then.schema` and `then.migration` are the halves that are not pure. A `delta`
cell, and a `migration` cell whose manual steps leave the database to its
statements, claims statements that carry a real database from one endpoint to
the other, so it is EXECUTED against each backend and the schema it leaves —
sequences included — is compared against the later model's own provisioning
DDL, the same independent-oracle shape golden SQL is graded by.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import run_case
from reference_harness.ddl_builder import ddl_for
from reference_harness.evolution_validate import validate_evolution
from reference_harness.providers import DatabaseProvider

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def evolution_cases() -> list[Case]:
    """Every authored evolution case. Also the selection `test_rejected.py`'s
    harness-lane partition measures this runner by."""
    return [case for case in discover_cases(_COMPATIBILITY_ROOT) if case.is_evolution]


_CASES = evolution_cases()

# The cases carrying a `then.schema` or `then.migration` matrix, which is what a
# database run has anything to do. A cell naming an unsupported operation, or
# migrating through a manual step no database stands in for, still collects
# here, so a dialect is never dropped from the run by the cell it happens to
# carry.
_SCHEMA_CASES = [case for case in _CASES if case.then.get("schema") or case.then.get("migration")]


@pytest.mark.parametrize("case", _CASES, ids=[case.path.stem for case in _CASES])
def test_evolution_case_is_structurally_sound_db_free(case: Case) -> None:
    # `None` is a safe stand-in for the provider: describing the difference
    # between two accepted models reaches no dialect, provisioning, or execution.
    run_case(case, None)


@pytest.mark.parametrize("case", _SCHEMA_CASES, ids=[case.path.stem for case in _SCHEMA_CASES])
def test_evolution_delta_cell_lands_on_the_later_models_schema(case: Case, provider) -> None:
    run_case(case, provider)


def test_the_evolution_population_is_non_empty() -> None:
    assert _CASES, "no evolution cases discovered under core/compatibility/cases"
    assert _SCHEMA_CASES, "no evolution case carries a then.schema matrix to execute"


def test_an_operation_naming_an_identity_neither_endpoint_declares_fails() -> None:
    case = _CASES[0]
    injected = {
        "kind": "AttributeAdded",
        "attribute": "parallax.compatibility.Absent.member",
    }
    findings = validate_evolution(_with_operations(case, [injected]))
    assert any("is not declared by the later endpoint" in finding for finding in findings)


def test_operations_out_of_canonical_order_fail() -> None:
    case = next(case for case in _CASES if len(_operations(case)) > 1)
    reversed_operations = list(reversed(_operations(case)))
    findings = validate_evolution(_with_operations(case, reversed_operations))
    assert any("canonical Model Location order" in finding for finding in findings)


def test_the_runner_reports_a_structural_finding_as_a_case_failure() -> None:
    case = next(case for case in _CASES if len(_operations(case)) > 1)
    broken = _with_operations(case, list(reversed(_operations(case))))
    with pytest.raises(CaseFailure, match="canonical Model Location order"):
        run_case(broken, None)


def _case(stem: str) -> Case:
    return next(case for case in _CASES if case.path.stem.startswith(stem))


def test_a_relocation_the_endpoints_do_not_resolve_to_fails() -> None:
    case = _case("m-model-evolution-071")
    (relocated,) = _operations(case)
    elsewhere = {**relocated, "later": {"qualifier": ["px_elsewhere"], "name": "evolution_widget"}}
    findings = validate_evolution(_with_operations(case, [elsewhere]))
    assert any("resolved relocations" in finding for finding in findings)


def test_an_omitted_relocation_fails() -> None:
    findings = validate_evolution(_with_operations(_case("m-model-evolution-072"), []))
    assert any("resolved relocations" in finding for finding in findings)


def test_a_relocation_the_masking_binding_prevents_fails() -> None:
    case = _case("m-model-evolution-073")
    invented = {
        "kind": "TableRelocated",
        "entity": "parallax.compatibility.Escrow",
        "earlier": {"qualifier": ["px"], "name": "evolution_escrow"},
        "later": {"qualifier": ["px"], "name": "evolution_escrow_archive"},
    }
    findings = validate_evolution(_with_operations(case, [*_operations(case), invented]))
    assert any("resolved relocations" in finding for finding in findings)
    assert any("DatabaseMigrationRequired" in finding for finding in findings)


def _operations(case: Case) -> list[dict[str, object]]:
    evolution = case.expected_evolution or {}
    return list(evolution.get("operations") or [])


def _with_operations(case: Case, operations: list[dict[str, object]]) -> Case:
    """``case`` with its authored operations replaced, leaving the corpus alone."""
    evolution = dict(case.expected_evolution or {})
    evolution["operations"] = operations
    raw = dict(case.raw)
    raw["then"] = {**raw["then"], "evolution": evolution}
    return Case(path=case.path, raw=raw, model=case.model, earlier_model=case.earlier_model)


# --- Coordinated Migration cells ---------------------------------------------


def _with_migration(case: Case, dialect: str, steps: list[dict[str, Any]]) -> Case:
    """``case`` with one dialect's authored migration steps replaced."""
    raw = dict(case.raw)
    migration = {**raw["then"]["migration"], dialect: {"steps": steps}}
    raw["then"] = {**raw["then"], "migration": migration}
    return Case(path=case.path, raw=raw, model=case.model, earlier_model=case.earlier_model)


def _steps(case: Case, dialect: str) -> list[dict[str, Any]]:
    return [dict(step) for step in (case.migration_cell(dialect) or {})["steps"]]


def test_a_migration_step_naming_an_operation_the_evolution_does_not_report_fails() -> None:
    case = _case("m-model-evolution-084")
    steps = _steps(case, "postgres")
    steps[0] = {**steps[0], "causedBy": [{"kind": "EntityRemoved", "entity": "parallax.x.Absent"}]}
    findings = validate_evolution(_with_migration(case, "postgres", steps))
    assert any("does not report" in finding for finding in findings)


def test_a_drain_after_a_statement_fails() -> None:
    case = _case("m-model-evolution-084")
    drain, *rest = _steps(case, "mariadb")
    findings = validate_evolution(_with_migration(case, "mariadb", [*rest, drain]))
    assert any("one drain at most" in finding for finding in findings)


def test_a_database_requirement_only_an_authoring_update_names_fails() -> None:
    case = _case("m-model-evolution-084")
    authoring = [{**step, "manual": "UpdateAuthoringSurface"} for step in _steps(case, "postgres")]
    for step in authoring:
        step.pop("statement", None)
    findings = validate_evolution(_with_migration(case, "postgres", authoring[:1]))
    assert any("do not cover" in finding for finding in findings)


def test_an_authoring_requirement_transformed_as_data_fails() -> None:
    case = _case("m-model-evolution-087")
    (step,) = _steps(case, "postgres")
    transformed = {**step, "manual": "TransformStoredData"}
    findings = validate_evolution(_with_migration(case, "postgres", [transformed]))
    assert any("do not cover" in finding for finding in findings)


def test_a_relocation_without_its_drain_fails() -> None:
    case = _case("m-model-evolution-025")
    _, relocate = _steps(case, "postgres")
    findings = validate_evolution(_with_migration(case, "postgres", [relocate]))
    assert any("does not drain for and relocate" in finding for finding in findings)


def test_a_migration_that_keeps_a_sequence_the_later_model_drops_fails(provider) -> None:
    case = _case("m-model-evolution-088")
    kept = [step for step in _steps(case, provider.dialect) if "statement" not in step]
    with pytest.raises(CaseFailure, match="migration leaves a schema"):
        run_case(_with_migration(case, provider.dialect, kept), provider)


def test_a_migration_altering_a_sequence_to_other_settings_fails(provider) -> None:
    case = _case("m-model-evolution-084")
    steps = _steps(case, provider.dialect)
    steps[1] = {**steps[1], "statement": steps[1]["statement"].replace("by 20", "by 25")}
    with pytest.raises(CaseFailure, match="migration leaves a schema"):
        run_case(_with_migration(case, provider.dialect, steps), provider)


def test_a_delta_that_never_creates_its_new_sequence_fails(provider) -> None:
    case = _case("m-schema-delta-012")
    cell = case.schema_cell(provider.dialect) or {}
    _, *tables = cell["delta"]["statements"]
    raw = dict(case.raw)
    missing = {"delta": {**cell["delta"], "statements": tables}}
    raw["then"] = {**raw["then"], "schema": {**raw["then"]["schema"], provider.dialect: missing}}
    with pytest.raises(CaseFailure, match="delta leaves a schema"):
        run_case(
            Case(path=case.path, raw=raw, model=case.model, earlier_model=case.earlier_model),
            provider,
        )


# --- Positioning over stored keys and reserved blocks --------------------------
#
# A migration cell's catalog comparison cannot see a sequence's position, and
# an evolution case's earlier database holds no rows. These tests store keys
# and reserve blocks the case cannot author, apply the cell's own statements,
# and read the next value the sequence answers.


def _provision_earlier(case: Case, db: DatabaseProvider) -> None:
    later = case.placement(db.dialect, case.model, "laterBinding")
    assert case.earlier_model is not None
    earlier = case.placement(db.dialect, case.earlier_model, "earlierBinding")
    db.reset(later.qualifiers | earlier.qualifiers)
    db.apply_ddl(ddl_for(case.earlier_model, earlier))


def _migrate(case: Case, db: DatabaseProvider) -> None:
    db.apply_ddl([step["statement"] for step in _steps(case, db.dialect) if "statement" in step])


_NEXT = {
    "postgres": "select nextval('{name}') as next_key",
    "mariadb": "select nextval({name}) as next_key",
}
_NAMES = {
    "fleetIds": {"postgres": 'px."fleetIds"', "mariadb": "px.`fleetIds`"},
    "credentialIds": {"postgres": 'px."credentialIds"', "mariadb": "px.`credentialIds`"},
}


def _next_key(db: DatabaseProvider, allocator: str) -> int:
    (row,) = db.query(_NEXT[db.dialect].format(name=_NAMES[allocator][db.dialect]))
    return int(row["next_key"])


_TX = {
    "postgres": "'2026-01-01 00:00:00+00', '2026-02-01 00:00:00+00'",
    "mariadb": "'2026-01-01 00:00:00', '2026-02-01 00:00:00'",
}
_TX_OPEN = {
    "postgres": "'2026-02-01 00:00:00+00', 'infinity'",
    "mariadb": "'2026-02-01 00:00:00', '9999-12-31 23:59:59.999999'",
}


def test_a_populated_join_starts_past_every_leaf_and_history_key(provider) -> None:
    case = _case("m-model-evolution-085")
    _provision_earlier(case, provider)
    provider.execute("insert into px_eu.car (id, name) values (7, 'c')")
    provider.execute("insert into px_us.truck (id, name) values (40, 't')")
    # The garage's largest key survives only in a closed history row.
    garage = "insert into px.garage (id, label, in_z, out_z) values"
    provider.execute(f"{garage} (93, 'old', {_TX[provider.dialect]})")
    provider.execute(f"{garage} (12, 'g', {_TX_OPEN[provider.dialect]})")
    _migrate(case, provider)
    assert _next_key(provider, "fleetIds") == 94


def test_a_join_never_moves_a_surviving_sequence_backward(provider) -> None:
    case = _case("m-model-evolution-086")
    _provision_earlier(case, provider)
    for _ in range(3):
        _next_key(provider, "credentialIds")  # blocks 1, 51, 101 reserved, none stored
    provider.execute("insert into px.pass (id, holder) values (60, 'p')")
    _migrate(case, provider)
    assert _next_key(provider, "credentialIds") == 151


def test_a_join_moves_a_surviving_sequence_past_a_stored_key_ahead_of_it(provider) -> None:
    case = _case("m-model-evolution-086")
    _provision_earlier(case, provider)
    _next_key(provider, "credentialIds")
    provider.execute("insert into px.pass (id, holder) values (5000, 'p')")
    _migrate(case, provider)
    assert _next_key(provider, "credentialIds") == 5001


def test_a_shrunken_step_starts_past_the_last_block_reserved_under_the_earlier_one(
    provider,
) -> None:
    case = _case("m-model-evolution-084")
    _provision_earlier(case, provider)
    _next_key(provider, "credentialIds")
    _next_key(provider, "credentialIds")  # 51..100 reserved under the step of 50
    provider.execute("insert into px.badge (id, holder) values (51, 'b')")
    _migrate(case, provider)
    assert _next_key(provider, "credentialIds") == 101
    assert _next_key(provider, "credentialIds") == 121


def test_a_floor_past_the_key_range_exhausts_the_sequence_rather_than_wrapping(provider) -> None:
    case = _case("m-model-evolution-086")
    _provision_earlier(case, provider)
    high = {"postgres": 2**63 - 1, "mariadb": 2**63 - 2}[provider.dialect]
    provider.execute(f"insert into px.pass (id, holder) values ({high}, 'p')")
    _migrate(case, provider)
    with pytest.raises(Exception, match="(?i)maximum value|run out"):
        _next_key(provider, "credentialIds")
