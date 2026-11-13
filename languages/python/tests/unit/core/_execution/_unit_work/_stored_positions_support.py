"""WherePosition's current rows as a database holds them, changing as simulated
step execution runs each step a flush hands it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.acquisition import RowConsumer, RowRequest
from parallax.core.internal.base import INFINITY
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.metamodel import AttributeIdentity, Metamodel
from parallax.core.internal.write_plan import PredecessorRow
from parallax.core.internal.write_plan.payload import PatchedDocument
from parallax.core.internal.write_plan.plan import EffectSpan
from parallax.core.internal.write_plan.steps import (
    Finite,
    MilestoneTarget,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    WriteRow,
)
from tests._support.bindings import bound_model
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

__all__ = ["StoredPositions"]


@dataclass(slots=True)
class StoredPositions:
    """``rows``, each WherePosition row current on Transaction Time by member
    name, and the flush's step execution over them.

    Each step sequence runs through ``simulated``, and only once it lowered do
    its steps change the rows: an insert stores what it opens, a close or a
    removal retires the row its target addresses, and a revision assigns its
    members. :meth:`acquire` answers reads from the rows standing then.
    """

    model: Metamodel
    rows: list[dict[str, object]]
    simulated: SimulatedWriteSteps = field(init=False)

    def __post_init__(self) -> None:
        self.rows = [dict(row) for row in self.rows]
        payloads = build_write_planner(bound_model(self.model)).payloads
        self.simulated = SimulatedWriteSteps(payloads, bound_model(self.model), POSTGRES)

    def __call__(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        effect_spans: tuple[EffectSpan, ...] = (),
        allocates: bool,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        answered = self.simulated(
            steps,
            effect_spans=effect_spans,
            allocates=allocates,
            capture_insert=capture_insert,
            capture_revision=capture_revision,
        )
        for step in steps:
            self._apply(step)
        return answered

    def acquire[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        stored = [PredecessorRow(members=row) for row in self.rows]
        return HeldRows(self.model, stored, overlapping=True)(request, consumer)

    def _apply(self, step: PlannedStep) -> None:
        match step:
            case PlannedInsert():
                self.rows.extend(_by_name(entry.row.attributes) for entry in step.entries)
            case PlannedClose() | PlannedTemporalRemoval():
                self.rows.remove(self._addressed(step.target))
            case PlannedTemporalRevision():
                self._addressed(step.target).update(_by_name(step.assignments.attributes))
            case _:
                raise AssertionError(f"a stored position takes no {type(step).__name__}")

    def _addressed(self, target: MilestoneTarget) -> dict[str, object]:
        (key,) = target.key_values
        ends = [end.instant if isinstance(end, Finite) else INFINITY for end in target.end_values]
        (row,) = [
            row for row in self.rows if [row["id"], row["validEnd"], row["txEnd"]] == [key, *ends]
        ]
        return row


def _by_name(attributes: Mapping[AttributeIdentity, object]) -> dict[str, object]:
    return {identity.name: value for identity, value in attributes.items()}
