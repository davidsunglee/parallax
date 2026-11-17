from __future__ import annotations

from collections.abc import Sequence

from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedWrite,
    InsertBatch,
    KeyedInsert,
    LicensedWrite,
    OrderedWrite,
    PostRemovalInsert,
    UnversionedLocked,
    UnversionedWriteBatch,
    distinct_evidence,
    is_licensed_by,
)
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.metamodel import AttributeMetadata, Metamodel
from parallax.core.internal.planned_step.keys import ObjectKey
from parallax.core.internal.planned_step.managed_row import ManagedRow

__all__ = ["collapse_writes"]


def collapse_writes(
    model: Metamodel, writes: Sequence[ComposedWrite]
) -> list[OrderedWrite | PostRemovalInsert]:
    """Collapse adjacent compatible admitted writes, after no-op removal.

    A same-shape update run collapses only when every assigned value is uniform
    across the whole run. Ineligible writes, including removal-dependent
    inserts, remain barriers. Row order and distinct source evidence survive.
    """
    result: list[OrderedWrite | PostRemovalInsert] = []
    candidates: list[KeyedInsert | LicensedWrite[UnversionedLocked]] = []
    group: object = None

    def close_run() -> None:
        collapsed = _collapsed(model, candidates) if len(candidates) > 1 else None
        if collapsed is None:
            result.extend(candidates)
        else:
            result.append(collapsed)
        candidates.clear()

    for item in writes:
        if isinstance(item, KeyedInsert) or is_licensed_by(item, UnversionedLocked):
            arriving = _group_key(item.instruction)
            if candidates and arriving == group:
                candidates.append(item)
                continue
            close_run()
            candidates.append(item)
            group = arriving
        else:
            close_run()
            result.append(item)
    close_run()
    return result


def _group_key(instruction: PreparedKeyedInstruction) -> object:
    # Deletes address only keys; payload members cannot split their statement.
    return (
        instruction.target,
        instruction.mutation,
        instruction.valid_time_window,
        0 if instruction.mutation == "delete" else instruction.rows[0].presence,
    )


def _collapsed(
    model: Metamodel, run: Sequence[KeyedInsert | LicensedWrite[UnversionedLocked]]
) -> InsertBatch | UnversionedWriteBatch | None:
    first = run[0]
    instruction = first.instruction
    if isinstance(first, KeyedInsert):
        shape = temporal_read.temporal_facet_of(model).shape(instruction.target.identity)
        if isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal):
            return None
    elif instruction.mutation != "delete" and not _uniform_assignments(model, run):
        return None

    rows: list[ManagedRow] = []
    assigns = False
    keys: list[ObjectKey] = []
    for item in run:
        rows.extend(item.instruction.rows)
        assigns = assigns or item.instruction.assigns
        keys.append(item.object_key)
    merged = derive_keyed_instruction(instruction, tuple(rows), assigns=assigns)
    if isinstance(first, KeyedInsert):
        return InsertBatch(instruction=merged, object_keys=tuple(keys))
    return UnversionedWriteBatch(
        instruction=merged,
        object_keys=tuple(keys),
        source_evidence=distinct_evidence(item.source_evidence for item in run),
    )


def _primary_key(model: Metamodel, instruction: PreparedKeyedInstruction) -> AttributeMetadata:
    position = inheritance.inheritance_facet_of(model).entity(instruction.target.identity)
    assert position is not None
    return position.primary_key


def _uniform_assignments(
    model: Metamodel, run: Sequence[KeyedInsert | LicensedWrite[UnversionedLocked]]
) -> bool:
    first = run[0].instruction
    row = first.rows[0]
    key = row.selection.members.index[_primary_key(model, first).identity]
    return all(
        value is candidate or value == candidate
        for item in run[1:]
        for (position, value), candidate in zip(
            row.stated_cells(), item.instruction.rows[0].cells, strict=True
        )
        if position != key
    )
