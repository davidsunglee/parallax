from __future__ import annotations

from collections.abc import Sequence

from parallax.core._execution._unit_work.evidence import ReadEvidence
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedWrite,
    InsertBatch,
    KeyedInsert,
    ObjectLockedBatch,
    ObjectLockedWrite,
    OrderedWrite,
    PostRemovalInsert,
)
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.metamodel import AttributeMetadata, Metamodel
from parallax.core.internal.write_plan.keys import ObjectKey
from parallax.core.internal.write_plan.managed_row import ManagedRow

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
    candidates: list[KeyedInsert | ObjectLockedWrite] = []
    group: object = None

    def close_run() -> None:
        collapsed = _collapsed(model, candidates) if len(candidates) > 1 else None
        if collapsed is None:
            result.extend(candidates)
        else:
            result.append(collapsed)
        candidates.clear()

    for item in writes:
        if isinstance(item, KeyedInsert | ObjectLockedWrite):
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
    model: Metamodel, run: Sequence[KeyedInsert | ObjectLockedWrite]
) -> InsertBatch | ObjectLockedBatch | None:
    first = run[0]
    instruction = first.instruction
    if isinstance(first, KeyedInsert):
        shape = temporal_read.temporal_facet_of(model).shape(instruction.target.identity)
        if isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal):
            return None
        if _primary_key(model, instruction).generated_key:
            return None
    elif instruction.mutation != "delete" and not _uniform_assignments(model, run):
        return None

    rows: list[ManagedRow] = []
    assigns = False
    insert_keys: list[ObjectKey | None] = []
    locked_keys: list[ObjectKey] = []
    retained: dict[int, ReadEvidence] = {}
    for item in run:
        rows.extend(item.instruction.rows)
        assigns = assigns or item.instruction.assigns
        if isinstance(item, KeyedInsert):
            insert_keys.append(item.object_key)
        else:
            locked_keys.append(item.object_key)
            for held in item.source_evidence:
                retained.setdefault(id(held), held)
    merged = derive_keyed_instruction(instruction, tuple(rows), assigns=assigns)
    if isinstance(first, KeyedInsert):
        return InsertBatch(instruction=merged, object_keys=tuple(insert_keys))
    return ObjectLockedBatch(
        instruction=merged,
        object_keys=tuple(locked_keys),
        source_evidence=tuple(retained.values()),
    )


def _primary_key(model: Metamodel, instruction: PreparedKeyedInstruction) -> AttributeMetadata:
    position = inheritance.inheritance_facet_of(model).entity(instruction.target.identity)
    assert position is not None
    return position.primary_key


def _uniform_assignments(model: Metamodel, run: Sequence[KeyedInsert | ObjectLockedWrite]) -> bool:
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
