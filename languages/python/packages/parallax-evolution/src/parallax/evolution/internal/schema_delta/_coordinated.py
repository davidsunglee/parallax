from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from parallax.core.internal.database_binding import (
    AllocatorSettingsChanged,
    ResolvedBinding,
    ResolvedSequence,
    SequenceRelocated,
    TableRelocated,
    sequence_ddl,
)
from parallax.core.internal.dialect import Dialect, Unsupported
from parallax.core.internal.metamodel import PrimaryKey
from parallax.evolution.internal.model_evolution import (
    AttributeAltered,
    CoordinatedEvolution,
    CoordinationReason,
    EvolutionOperation,
    PrimaryKeyChanged,
)
from parallax.evolution.internal.schema_delta._order import table_operations
from parallax.evolution.internal.schema_delta._physical import (
    AlterSequence,
    CreateExtension,
    CreateSequence,
    DropIndex,
    DropSequence,
    PhysicalOperation,
    PositionSequence,
    location_of,
)
from parallax.evolution.internal.schema_delta._plan import (
    Plan,
    abandoned_by,
    joined_allocators,
    plan,
)
from parallax.evolution.internal.schema_delta._render import render
from parallax.evolution.internal.schema_delta._values import (
    ManualAction,
    ManualStep,
    MigrationStatement,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)

__all__ = ["migration_plan", "migration_steps"]

type _Step = ManualStep | PhysicalOperation


def migration_plan(evolution: CoordinatedEvolution) -> tuple[Plan, tuple[_Step, ...]]:
    """The ordinary plan ``evolution`` lowers to, beside every migration step in
    executable order, the generated ones still physical operations.

    The order is prerequisite-first: one drain of the earlier roots precedes
    everything it is required for, then each relocation, each stored-data
    transformation no statement generates, each authoring-only change, the
    ordinary statements, and the sequence statements last — creations, then
    alterations, then positionings, which read keys every earlier step has
    stored, then drops.
    """
    later = evolution.later
    database = frozenset(
        requirement.operation
        for requirement in evolution.coordination_requirements
        if CoordinationReason.DATABASE_MIGRATION_REQUIRED in requirement.reasons
    )
    built = plan(evolution)
    relocations = tuple(
        operation
        for operation in evolution.operations
        if isinstance(operation, TableRelocated | SequenceRelocated)
    )
    settings = tuple(
        operation
        for operation in evolution.operations
        if isinstance(operation, AllocatorSettingsChanged)
    )
    joins = joined_allocators(evolution)
    joining = {operation for causes in joins.values() for operation in causes}
    sequences: list[PhysicalOperation] = [
        operation for operation in built.operations if isinstance(operation, CreateSequence)
    ]
    sequences.extend(
        AlterSequence(earlier=change.earlier, later=change.later, caused_by=(change,))
        for change in settings
        if sequence_ddl(change.earlier) != sequence_ddl(change.later)
    )
    sequences.extend(_positions(later, evolution.operations, joins, settings))
    drops = _drops(evolution)
    sequences.extend(drops)
    covered = {
        *relocations,
        *settings,
        *(operation for operation in joining if _only_moves_generation(operation)),
    }
    drained = {
        *relocations,
        *settings,
        *joining,
        *(cause for drop in drops for cause in drop.caused_by),
    }
    steps: list[_Step] = []
    if drained:
        steps.append(
            ManualStep(ManualAction.DRAIN_EARLIER_ROOTS, _in_order(evolution.operations, drained))
        )
    steps.extend(ManualStep(ManualAction.RELOCATE, (operation,)) for operation in relocations)
    steps.extend(
        ManualStep(ManualAction.TRANSFORM_STORED_DATA, (operation,))
        for operation in evolution.operations
        if operation in database and operation not in covered
    )
    steps.extend(
        ManualStep(ManualAction.UPDATE_AUTHORING_SURFACE, (requirement.operation,))
        for requirement in evolution.coordination_requirements
        if requirement.operation not in database
    )
    steps.extend(
        operation for operation in built.operations if isinstance(operation, CreateExtension)
    )
    steps.extend(_after_relocation(table_operations(built.operations), later))
    steps.extend(sequences)
    return built, tuple(steps)


def migration_steps(
    steps: Sequence[_Step], dialect: Dialect
) -> tuple[MigrationStatement | ManualStep, ...]:
    """``steps`` with every physical operation rendered, or the atomic refusal
    naming every one ``dialect`` cannot spell."""
    rendered = tuple(
        (step, step if isinstance(step, ManualStep) else render(step, dialect)) for step in steps
    )
    refusals = tuple(
        UnsupportedSchemaOperation(
            kind=type(step).__name__,
            location=location_of(step),
            reason=result.reason,
            caused_by=step.caused_by,
        )
        for step, result in rendered
        if isinstance(result, Unsupported) and not isinstance(step, ManualStep)
    )
    if refusals:
        raise UnsupportedSchemaEvolutionError(dialect.name, refusals)
    return tuple(
        result
        if isinstance(result, ManualStep)
        else MigrationStatement(sql=result, caused_by=step.caused_by)
        for step, result in rendered
        if not isinstance(result, Unsupported)
    )


def _positions(
    later: ResolvedBinding,
    operations: Sequence[EvolutionOperation],
    joins: Mapping[str, Sequence[EvolutionOperation]],
    settings: Sequence[AllocatorSettingsChanged],
) -> Iterable[PositionSequence]:
    """One positioning per sequence a surviving Entity joins or whose physical step
    shrinks, caused by every operation asking for it.

    A sequence whose step shrinks is positioned past the block its latest
    reservation took under the earlier step, which a reading of its position
    under the later step alone would overlap; one whose step grows already
    starts its next block past that one.
    """
    causes: dict[str, set[EvolutionOperation]] = {}
    reserved: dict[str, int] = {}
    for change in settings:
        before, after = sequence_ddl(change.earlier).increment, sequence_ddl(change.later).increment
        if before > after:
            causes.setdefault(change.allocator, set()).add(change)
            reserved[change.allocator] = before
    for allocator, joining in joins.items():
        causes.setdefault(allocator, set()).update(joining)
    for allocator in sorted(causes, key=lambda key: _physical_order(later.sequences[key])):
        sequence = later.sequences[allocator]
        yield PositionSequence(
            sequence=sequence,
            reserved_increment=reserved.get(allocator, sequence_ddl(sequence).increment),
            caused_by=_in_order(operations, causes[allocator]),
        )


def _drops(evolution: CoordinatedEvolution) -> tuple[DropSequence, ...]:
    """One drop per native allocator the earlier binding resolves and the later
    one does not, caused by the operations that took its last consumer away."""
    gone = sorted(
        (
            sequence
            for allocator, sequence in evolution.earlier.sequences.items()
            if allocator not in evolution.later.sequences
        ),
        key=_physical_order,
    )
    return tuple(
        DropSequence(sequence=sequence, caused_by=abandoned_by(evolution, sequence.allocator))
        for sequence in gone
    )


def _only_moves_generation(operation: EvolutionOperation) -> bool:
    """Whether every field ``operation`` changes is a key's generation, so the
    sequence statements carry the whole of its database change."""
    return isinstance(operation, AttributeAltered) and all(
        isinstance(delta, PrimaryKeyChanged)
        and isinstance(delta.earlier, PrimaryKey)
        and isinstance(delta.later, PrimaryKey)
        for delta in operation.deltas
    )


def _after_relocation(
    operations: Sequence[PhysicalOperation], later: ResolvedBinding
) -> Iterable[PhysicalOperation]:
    """Table operations as they run once every relocation is done: an Index
    dropped from a surviving Table is dropped where the relocation moved the
    Table, under the name it held there."""
    for operation in operations:
        if isinstance(operation, DropIndex):
            moved = later.table(operation.definition.mapping_owner)
            if moved != operation.definition.table:
                yield replace(operation, definition=replace(operation.definition, table=moved))
                continue
        yield operation


def _in_order(
    operations: Sequence[EvolutionOperation], chosen: set[EvolutionOperation]
) -> tuple[EvolutionOperation, ...]:
    return tuple(operation for operation in operations if operation in chosen)


def _physical_order(sequence: ResolvedSequence) -> tuple[str, tuple[str, ...]]:
    return (sequence.physical.name, sequence.physical.qualifier)
