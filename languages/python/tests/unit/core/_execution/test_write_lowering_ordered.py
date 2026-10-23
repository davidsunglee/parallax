"""Which steps ordered write transport may carry, decided before payload demand
(execution's lowering seam, `m-execution`, `m-dialect`).

A count-only effect on one row — a temporal close, guard, revision, or removal,
or a Non-Temporal update or delete of one key expecting an exact count —
promises a conservative ceiling on its statement's SQL parameters from the step
alone, and qualifies only where that ceiling fits the dialect's configured
limit. The promise is checked against what lowering actually produced, so a
statement exceeding it is refused as a lowering failure rather than presented.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance import adapter, case_format
from parallax.core import predicate as predicate_algebra
from parallax.core._execution import _write_lowering
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    PreparedPredicateWrite,
    PreparedTargetWrite,
    prepare_typed_write,
)
from parallax.core._execution._write_lowering import (
    lowered,
    lowered_within,
    ordered_parameter_ceiling,
)
from parallax.core.base import INFINITY as OPEN
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import (
    StepPayload,
    compile_write_step,
    non_insert_parameter_ceiling,
)
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    WritePlanningRequest,
)
from parallax.core.write_plan import SUPERSEDED
from parallax.core.write_plan.steps import (
    INFINITY,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    SelfIncrement,
    TemporalGate,
    Versioned,
    VersionGate,
    WriteRow,
)
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, plan_steps
from tests._support.sweep_goldens import WRITE_EXERCISED
from tests.unit._corpus_model_support import model
from tests.unit._corpus_model_support import target as entity_of

_T0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_T1: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _effects(
    entity: EntityIdentity, owner: EntityIdentity, revised: dict[AttributeIdentity, object]
) -> list[PlannedStep]:
    """Every count-only temporal effect on ``entity``, whose key and temporal
    members ``owner`` declares; its revision assigns ``revised``."""

    def attr(name: str) -> AttributeIdentity:
        return AttributeIdentity(owner, name)

    slot = MilestoneTarget(
        key_attributes=(attr("id"),),
        key_values=(1,),
        end_attributes=(attr("validEnd"), attr("txEnd")),
        end_values=(INFINITY, INFINITY),
    )
    gate = TemporalGate(start_attribute=attr("txStart"), observed_start=_T0)
    return [
        PlannedClose(
            entity=entity,
            target=slot,
            assignments=PlannedAssignments(attributes={attr("txEnd"): _T1}),
            cause=SUPERSEDED,
            concurrency=UNGATED,
            affected_rows=ExactCount(1, STALE_WRITE),
        ),
        PlannedTemporalGuard(
            entity=entity,
            target=slot,
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
        PlannedTemporalRemoval(
            entity=entity,
            target=slot,
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
        PlannedTemporalRevision(
            entity=entity,
            target=slot,
            assignments=PlannedAssignments(attributes=revised),
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
            predecessor_document_is_object=True,
        ),
    ]


def _cases() -> list[tuple[str, Metamodel, PlannedStep]]:
    position = model("position")
    columns = entity_of(position, "Position").identity
    tags = model("scalar-collection-lifecycle-layout-twin-document")
    document = entity_of(tags, "TagSpan").identity
    instrument = model("instrument")
    bond = entity_of(instrument, "Bond").identity
    root = entity_of(instrument, "Instrument").identity
    cases: list[tuple[str, Metamodel, PlannedStep]] = []
    revisions: tuple[tuple[str, Metamodel, EntityIdentity, EntityIdentity, dict[str, object]], ...]
    revisions = (
        ("columns", position, columns, columns, {"value": Decimal("2.50")}),
        (
            "document",
            tags,
            document,
            document,
            {"amount": 5, "marks": (1, 2, 3), "validStart": _T0},
        ),
        ("table-per-hierarchy", instrument, bond, root, {"price": Decimal("1.00")}),
    )
    for label, meta, entity, owner, revised in revisions:
        assigned: dict[AttributeIdentity, object] = {
            AttributeIdentity(owner, name): value for name, value in revised.items()
        }
        if entity == bond:
            assigned[AttributeIdentity(bond, "coupon")] = Decimal("2.00")
        effects = _effects(entity, owner, assigned)
        cases.extend((f"{label}-{type(step).__name__}", meta, step) for step in effects)
    return cases


@pytest.mark.parametrize(
    ("label", "meta", "step"), _cases(), ids=[label for label, _meta, _step in _cases()]
)
def test_every_temporal_effect_promises_a_parameter_ceiling_its_statement_keeps(
    label: str, meta: Metamodel, step: PlannedStep
) -> None:
    del label
    ceiling = ordered_parameter_ceiling(step, POSTGRES)
    assert ceiling is not None
    statement = lowered_within(step, ceiling, build_write_planner(meta).payloads, meta, POSTGRES)
    assert len(statement.binds) <= ceiling
    assert statement == lowered(step, build_write_planner(meta).payloads, meta, POSTGRES)


def test_an_insert_never_qualifies_for_ordered_transport() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity

    def attr(name: str) -> AttributeIdentity:
        return AttributeIdentity(entity, name)

    row = PlannedRow(
        attributes={
            attr("id"): 1,
            attr("acctNum"): "A-1",
            attr("value"): Decimal("1.00"),
            attr("validStart"): _T0,
            attr("validEnd"): OPEN,
            attr("txStart"): _T1,
            attr("txEnd"): OPEN,
        }
    )
    insert = PlannedInsert(entity=entity, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))
    assert ordered_parameter_ceiling(insert, POSTGRES) is None


def test_an_effect_whose_ceiling_exceeds_the_dialect_limit_runs_alone() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity
    close, guard, *_ = _effects(entity, entity, {AttributeIdentity(entity, "value"): Decimal("1")})
    # A close's ceiling is six parameters and a guard's five.
    narrow = replace(POSTGRES, max_bind_parameters=5)
    assert ordered_parameter_ceiling(close, narrow) is None
    assert ordered_parameter_ceiling(guard, narrow) == 5


def test_a_statement_exceeding_the_ceiling_it_promised_is_a_lowering_failure() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity
    close, *_ = _effects(entity, entity, {AttributeIdentity(entity, "value"): Decimal("1")})
    payloads = build_write_planner(meta).payloads
    with pytest.raises(SqlGenError, match="carrying 4 binds exceeds the 3 its shape promised"):
        lowered_within(close, 3, payloads, meta, POSTGRES)


def _wallet_effects(*keys: int) -> tuple[PlannedUpdate, PlannedDelete]:
    wallet = entity_of(model("wallet"), "Wallet").identity
    target = KeyTarget(
        key_attributes=(AttributeIdentity(wallet, "id"),),
        key_values=tuple((key,) for key in keys),
    )
    affected = ExactCount(len(keys), MISSING_TARGET)
    return (
        PlannedUpdate(
            entity=wallet,
            target=target,
            assignments=PlannedAssignments(
                attributes={AttributeIdentity(wallet, "balance"): Decimal("1.00")}
            ),
            concurrency=UNVERSIONED,
            affected_rows=affected,
        ),
        PlannedDelete(
            entity=wallet, target=target, concurrency=UNVERSIONED, affected_rows=affected
        ),
    )


def _planned(
    meta: Metamodel, instruction: KeyedWriteInstruction | PredicateWriteInstruction
) -> PlannedStep:
    prepared = prepare_typed_write(instruction, meta)
    assert not isinstance(prepared, PreparedTargetWrite)
    planner = build_write_planner(meta)
    if isinstance(prepared, PreparedPredicateWrite):
        return planner.predicate_step(
            prepared, actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=inert_instant()
        )
    (step,) = plan_steps(
        planner.finalize(
            WritePlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="locking",
                buffered_writes=[prepared],
            )
        )
    )
    return step


def test_a_single_key_non_temporal_effect_promises_the_ceiling_its_statement_keeps() -> None:
    meta = model("wallet")
    update, delete = _wallet_effects(1)
    # Key and tag guard, plus an assigned member's two.
    assert ordered_parameter_ceiling(update, POSTGRES) == 4
    assert ordered_parameter_ceiling(delete, POSTGRES) == 2
    payloads = build_write_planner(meta).payloads
    for step in (update, delete):
        ceiling = ordered_parameter_ceiling(step, POSTGRES)
        assert ceiling is not None
        assert lowered_within(step, ceiling, payloads, meta, POSTGRES) == lowered(
            step, payloads, meta, POSTGRES
        )


def test_a_version_gate_and_a_registry_increment_each_fit_the_ceiling() -> None:
    account = entity_of(model("account"), "Account").identity
    gated = PlannedUpdate(
        entity=account,
        target=KeyTarget(key_attributes=(AttributeIdentity(account, "id"),), key_values=((1,),)),
        assignments=PlannedAssignments(
            attributes={
                AttributeIdentity(account, "balance"): Decimal("1.00"),
                AttributeIdentity(account, "version"): 2,
            }
        ),
        concurrency=Versioned(
            attribute=AttributeIdentity(account, "version"), gate=VersionGate(observed_version=1)
        ),
        affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
    )
    assert ordered_parameter_ceiling(gated, POSTGRES) == 7
    registry_model = model("pk-sequence")
    registry = _planned(
        registry_model,
        KeyedWriteInstruction(
            "amend", "PkSequence", ({"name": "pass_seq", "nextVal": {"increment": 3}},)
        ),
    )
    assert isinstance(registry, PlannedUpdate)
    assert any(
        isinstance(value, SelfIncrement) for value in registry.assignments.attributes.values()
    )
    ceiling = ordered_parameter_ceiling(registry, POSTGRES)
    assert ceiling == 4
    payloads = build_write_planner(registry_model).payloads
    statement = lowered_within(registry, ceiling, payloads, registry_model, POSTGRES)
    assert statement.binds == (3, "pass_seq")


def test_a_multi_key_or_predicate_selected_effect_runs_alone() -> None:
    meta = model("wallet")
    for step in _wallet_effects(1, 2):
        assert ordered_parameter_ceiling(step, POSTGRES) is None
    predicate = _planned(
        meta,
        PredicateWriteInstruction(
            "delete",
            PredicateSelection(
                "Wallet",
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Wallet.id"), 1),
            ),
        ),
    )
    assert isinstance(predicate, PlannedDelete)
    assert ordered_parameter_ceiling(predicate, POSTGRES) is None
    with pytest.raises(SqlGenError, match="not bounded by its shape"):
        non_insert_parameter_ceiling(predicate)


def test_a_non_temporal_effect_whose_ceiling_exceeds_the_dialect_limit_runs_alone() -> None:
    update, delete = _wallet_effects(1)
    narrow = replace(POSTGRES, max_bind_parameters=3)
    assert ordered_parameter_ceiling(update, narrow) is None
    assert ordered_parameter_ceiling(delete, narrow) == 2


def test_every_single_key_non_temporal_effect_the_corpus_lowers_keeps_its_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every keyed write case the compile lane grades, under every layout,
    # inheritance strategy, and concurrency its models declare.
    kept: list[PlannedUpdate | PlannedDelete] = []
    compiling = compile_write_step

    def checked(
        step: PlannedStep, payload: StepPayload, meta: Metamodel, dialect: Dialect
    ) -> LoweredStatement:
        statement = compiling(step, payload, meta, dialect)
        if isinstance(step, PlannedUpdate | PlannedDelete):
            ceiling = ordered_parameter_ceiling(step, dialect)
            if ceiling is not None:
                assert len(statement.binds) <= ceiling, (step, statement.sql)
                kept.append(step)
        return statement

    monkeypatch.setattr(_write_lowering, "compile_write_step", checked)
    cases = case_format.default_cases_dir()
    for case_id in sorted(WRITE_EXERCISED):
        (path,) = cases.glob(f"{case_id}-*.yaml")
        assert adapter.compile_case(path, "postgres")["status"] == "ok", case_id
    gated = [
        step
        for step in kept
        if isinstance(step.concurrency, Versioned)
        and isinstance(step.concurrency.gate, VersionGate)
    ]
    documents = [
        step for step in kept if isinstance(step, PlannedUpdate) and step.assignments.value_objects
    ]
    assert gated and documents
    assert {type(step) for step in kept} == {PlannedUpdate, PlannedDelete}
