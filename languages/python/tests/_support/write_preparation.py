from __future__ import annotations

from typing import Final, overload

import pytest

from parallax.core._execution._planning import build_write_preparation
from parallax.core._execution._unit_work.instructions import (
    INSERT_MUTATIONS,
    REPLACE_MUTATIONS,
    KeyedWriteInstruction,
    PredicateWriteInstruction,
    TargetWriteInstruction,
    WriteInstruction,
)
from parallax.core._execution._unit_work.preparation import (
    TYPED,
    WIRE,
    CompletePayload,
    PartialPayload,
    PreparedKeyedInstruction,
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
    TargetRevisionArguments,
    WritePreparation,
    WriteRepresentation,
    prepare_insert,
    prepare_keyed_write,
    prepare_predicate_write,
    prepare_target_write,
    resolve_target,
)
from parallax.core.internal.metamodel import Metamodel

__all__ = ["REPRESENTATIONS", "prepare_instruction", "write_preparation_of"]

REPRESENTATIONS: Final = pytest.mark.parametrize(
    "representation", (TYPED, WIRE), ids=("typed", "wire")
)
"""Parametrize a test over both write representations as ``representation``."""

_PREPARED: dict[int, tuple[Metamodel, WritePreparation]] = {}


def write_preparation_of(model: Metamodel) -> WritePreparation:
    """The write preparation production derives for ``model``, derived once per
    model object, so every write a test prepares against one model shares its
    row selections as production's do."""
    held = _PREPARED.get(id(model))
    if held is not None and held[0] is model:
        return held[1]
    preparation = build_write_preparation(model)
    _PREPARED[id(model)] = (model, preparation)
    return preparation


@overload
def prepare_instruction(
    instruction: KeyedWriteInstruction,
    preparation: WritePreparation,
    representation: WriteRepresentation = TYPED,
) -> PreparedKeyedInstruction: ...
@overload
def prepare_instruction(
    instruction: TargetWriteInstruction,
    preparation: WritePreparation,
    representation: WriteRepresentation = TYPED,
) -> PreparedTargetInstruction: ...
@overload
def prepare_instruction(
    instruction: PredicateWriteInstruction,
    preparation: WritePreparation,
    representation: WriteRepresentation = TYPED,
) -> PreparedPredicateInstruction: ...
@overload
def prepare_instruction(
    instruction: WriteInstruction,
    preparation: WritePreparation,
    representation: WriteRepresentation = TYPED,
) -> PreparedKeyedInstruction | PreparedPredicateInstruction | PreparedTargetInstruction: ...
def prepare_instruction(
    instruction: WriteInstruction,
    preparation: WritePreparation,
    representation: WriteRepresentation = TYPED,
) -> PreparedKeyedInstruction | PreparedPredicateInstruction | PreparedTargetInstruction:
    """``instruction``, a test's readable spelling of one write, prepared
    through its family's entry in ``representation``, its row built into a
    payload by the production name builders."""
    meta = preparation.meta
    if isinstance(instruction, PredicateWriteInstruction):
        target = resolve_target(meta, instruction.target.entity)
        row = instruction.row
        return prepare_predicate_write(
            preparation,
            representation,
            instruction.mutation,
            target,
            instruction.target.predicate,
            None
            if row is None
            else preparation.entity(target.identity).complete_payload_from_names(row),
            assignments=instruction.assignments,
        )
    target = resolve_target(meta, instruction.entity)
    prepared = preparation.entity(target.identity)
    whole = instruction.mutation in INSERT_MUTATIONS or instruction.mutation in REPLACE_MUTATIONS
    payload: CompletePayload | PartialPayload = (
        prepared.complete_payload_from_names(instruction.row)
        if whole
        else prepared.partial_payload_from_names(instruction.row)
    )
    if isinstance(instruction, TargetWriteInstruction):
        stated = tuple(
            name
            for name, value in (
                ("version", instruction.if_version),
                ("tx_start", instruction.if_tx_start),
            )
            if value is not None
        )
        return prepare_target_write(
            preparation,
            representation,
            instruction.mutation,
            target,
            payload,
            revision=TargetRevisionArguments(
                instruction.if_version, instruction.if_tx_start, stated
            ),
            valid_from=instruction.valid_from,
            until=instruction.until,
        )
    if isinstance(payload, CompletePayload) and instruction.mutation in INSERT_MUTATIONS:
        return prepare_insert(
            preparation,
            representation,
            instruction.mutation,
            target,
            payload,
            valid_from=instruction.valid_from,
            until=instruction.until,
        )
    return prepare_keyed_write(
        preparation,
        representation,
        instruction.mutation,
        target,
        payload,
        valid_from=instruction.valid_from,
        until=instruction.until,
    )
