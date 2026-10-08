"""A recording Audit Strategy for the audit hooks' unit seams.

It records every row, update, and close each hook is handed, in order, with the
Actor Identity it came with, and stamps the Attributes it is given onto each one
that holds them — as executed assignments, the only way a hook may add a value.
With nothing to stamp it answers each input itself, like the neutral strategy,
while still not being the neutral strategy settlement recognizes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from parallax.core.metamodel import AttributeIdentity
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.strategy import ActorIdentity
from parallax.core.write_plan.steps import (
    PlannedAssignments,
    PlannedClose,
    PlannedUpdate,
    PlannedValue,
    WriteRow,
    adopt_planned_assignments,
    adopt_planned_row,
)

__all__ = ["RecordingAudit"]


@dataclass(slots=True)
class RecordingAudit:
    stamps: Mapping[AttributeIdentity, PlannedValue] = field(
        default_factory=dict[AttributeIdentity, PlannedValue]
    )
    rows: list[WriteRow] = field(default_factory=list[WriteRow])
    updates: list[PlannedUpdate] = field(default_factory=list[PlannedUpdate])
    closes: list[PlannedClose] = field(default_factory=list[PlannedClose])
    actors: list[ActorIdentity] = field(default_factory=list[ActorIdentity])

    def finalize_row(
        self,
        write_row: WriteRow,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> WriteRow:
        del transaction_instant
        self.rows.append(write_row)
        self.actors.append(actor_identity)
        stamped = self._stamped(write_row.row.attributes)
        if not stamped:
            return write_row
        row = write_row.row
        return WriteRow(
            row=adopt_planned_row({**row.attributes, **stamped}, dict(row.value_objects)),
            origin=write_row.origin,
            executed=(
                *write_row.executed,
                *(member for member in stamped if member not in write_row.executed),
            ),
        )

    def decorate_update(
        self,
        update: PlannedUpdate,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedUpdate:
        del transaction_instant
        self.updates.append(update)
        self.actors.append(actor_identity)
        extended = self._extended(update.assignments)
        return update if extended is update.assignments else replace(update, assignments=extended)

    def decorate_close(
        self,
        close: PlannedClose,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedClose:
        del transaction_instant
        self.closes.append(close)
        self.actors.append(actor_identity)
        extended = self._extended(close.assignments)
        return close if extended is close.assignments else replace(close, assignments=extended)

    def _stamped(
        self, attributes: Mapping[AttributeIdentity, PlannedValue]
    ) -> dict[AttributeIdentity, PlannedValue]:
        return {
            identity: value for identity, value in self.stamps.items() if identity in attributes
        }

    def _extended(self, assignments: PlannedAssignments) -> PlannedAssignments:
        stamped = {
            identity: value
            for identity, value in self.stamps.items()
            if identity.entity in {member.entity for member in assignments.attributes}
        }
        if not stamped:
            return assignments
        return adopt_planned_assignments(
            {**assignments.attributes, **stamped}, dict(assignments.value_objects)
        )
