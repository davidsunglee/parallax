from __future__ import annotations

from typing import Final, cast

from parallax.core.internal.base import InternalError
from parallax.core.internal.database_binding import PhysicalSequence, PhysicalTable
from parallax.core.internal.dialect import Dialect, Unsupported
from parallax.evolution.internal.model_evolution import CoordinatedEvolution, UnilateralEvolution
from parallax.evolution.internal.schema_delta._coordinated import migration_plan, migration_steps
from parallax.evolution.internal.schema_delta._order import order
from parallax.evolution.internal.schema_delta._physical import (
    CreateIndex,
    PhysicalOperation,
    location_of,
)
from parallax.evolution.internal.schema_delta._plan import Plan, plan
from parallax.evolution.internal.schema_delta._render import render
from parallax.evolution.internal.schema_delta._values import (
    CollidingIndex,
    CollidingRelation,
    CollidingTemporalConstraint,
    CollisionGroup,
    CoordinatedMigration,
    CreatedIndex,
    ManualAction,
    ManualStep,
    MigrationStatement,
    SchemaDelta,
    SchemaTarget,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)

__all__ = [
    "CoordinatedMigration",
    "CreatedIndex",
    "ManualAction",
    "ManualStep",
    "MigrationStatement",
    "SchemaDelta",
    "SchemaTarget",
    "UnsupportedSchemaEvolutionError",
    "UnsupportedSchemaOperation",
    "coordinated_migration",
    "schema_delta",
]


def schema_delta(evolution: UnilateralEvolution) -> SchemaDelta:
    """Render a `UnilateralEvolution` as SQL statements for its later binding's backend.

    The ordered statements that apply ``evolution`` to a database, naming every
    table as the later binding places it and dropping every index where the
    earlier binding placed it. Nothing here moves, renames, or provisions a
    table or schema, or moves, alters, or repositions a sequence.

    The complete plan is named, ordered, and rendered before any statement
    escapes, so a Dialect that cannot spell one operation yields no partial
    delta: :class:`UnsupportedSchemaEvolutionError` carries every refusal at once,
    in the order the statements would have run. A derived Physical Index Name
    clash, with another Index or with a table or sequence holding that name in
    the Index's scope, raises the ``physical-index-name-collision``
    :class:`~parallax.core.internal.base.InternalError` naming every group rather than
    renaming any definition.

    The statements are prefix-safe in the returned order and deliberately not
    idempotent; creating a unique Index is the authoritative validation of the
    data already stored. A sequence is created exactly for each native allocator
    the later binding resolves and the earlier one does not.

    A :class:`~parallax.evolution.internal.model_evolution.CoordinatedEvolution`
    raises :class:`TypeError` before anything is planned:
    :func:`coordinated_migration` generates its steps.
    """
    if not isinstance(cast("object", evolution), UnilateralEvolution):
        raise TypeError(
            f"schema_delta takes a UnilateralEvolution, not a {type(evolution).__name__}; "
            "use coordinated_migration for a coordinated evolution"
        )
    dialect = evolution.later.dialect
    built = plan(evolution)
    _reject_collisions(built, dialect)
    ordered = order(built.operations)
    rendered = tuple((operation, render(operation, dialect)) for operation in ordered)
    refusals = tuple(
        _refusal(operation, result)
        for operation, result in rendered
        if isinstance(result, Unsupported)
    )
    if refusals:
        raise UnsupportedSchemaEvolutionError(dialect.name, refusals)
    return SchemaDelta(
        statements=tuple(result for _, result in rendered if isinstance(result, str)),
        created_indices=tuple(
            CreatedIndex(
                physical_index_name=operation.name,
                physical_table=operation.definition.table.physical,
                logical_index_identity=operation.definition.index,
                unique=operation.definition.unique,
            )
            for operation in ordered
            if isinstance(operation, CreateIndex)
        ),
    )


def coordinated_migration(evolution: CoordinatedEvolution) -> CoordinatedMigration:
    """The ordered steps carrying a `CoordinatedEvolution`'s database and roots onward.

    Each step is a generated :class:`MigrationStatement` for the later binding's
    backend or a :class:`ManualStep` the deployment performs, and each names
    the operations that asked for it: every operation a coordination
    requirement names appears in some step. Every drain the migration needs
    precedes every relocation, transformation, and statement. Nothing here moves
    a table or sequence or transforms stored data; those are manual steps.

    Statements are generated for the ordinary physical changes the evolution's
    other operations ask for, exactly as :func:`schema_delta` generates them,
    and for native sequences: creating one, altering a surviving one's
    settings, moving one forward past every key its consumers store and every
    block already reserved from it, and dropping one no model references.
    Refusals and Physical Index Name collisions are raised exactly as
    :func:`schema_delta` raises them, before any step escapes.

    A :class:`~parallax.evolution.internal.model_evolution.UnilateralEvolution`
    raises :class:`TypeError`: :func:`schema_delta` generates its statements.
    """
    if not isinstance(cast("object", evolution), CoordinatedEvolution):
        raise TypeError(
            f"coordinated_migration takes a CoordinatedEvolution, not a "
            f"{type(evolution).__name__}; use schema_delta for a unilateral evolution"
        )
    dialect = evolution.later.dialect
    built, steps = migration_plan(evolution)
    _reject_collisions(built, dialect)
    return CoordinatedMigration(steps=migration_steps(steps, dialect))


def _refusal(operation: PhysicalOperation, result: Unsupported) -> UnsupportedSchemaOperation:
    return UnsupportedSchemaOperation(
        kind=type(operation).__name__,
        location=location_of(operation),
        reason=result.reason,
        caused_by=operation.caused_by,
    )


PHYSICAL_INDEX_NAME_COLLISION: Final = "physical-index-name-collision"
"""The code of the :class:`~parallax.core.internal.base.InternalError` a delta is refused
by where distinct Index definitions the database would hold at once derive one
Physical Index Name, or a table or sequence a binding places holds one in its
scope: a defensive backstop, not an ordinary control path, since a definition's
name is derived from its own facts alone."""


def _reject_collisions(built: Plan, dialect: Dialect) -> None:
    """Refuse a name two objects the database holds at once both claim."""
    if built.collisions:
        raise _collision_refusal(dialect.name, built.collisions)


def _collision_refusal(dialect_identity: str, groups: tuple[CollisionGroup, ...]) -> InternalError:
    """The refusal naming the Dialect and every collision group, in Physical
    Index Name order, each with the shared name, its colliding definitions, and
    the relations holding it."""
    spelled = "; ".join(
        f"{group.name.value} is derived by "
        + ", ".join(
            [_spelled_index(definition) for definition in group.definitions]
            + [_spelled_constraint(constraint) for constraint in group.temporal_constraints]
        )
        + (
            " and held by " + ", ".join(_spelled_relation(held) for held in group.relations)
            if group.relations
            else ""
        )
        for group in groups
    )
    return InternalError(
        PHYSICAL_INDEX_NAME_COLLISION,
        f"{dialect_identity} derived colliding Physical Index Names: {spelled}",
    )


def _spelled_index(definition: CollidingIndex) -> str:
    components = ", ".join(component.name for component in definition.components)
    unique = "unique " if definition.unique else ""
    return (
        f"{unique}Index {definition.index.entity.canonical}.{definition.index.name} on "
        f"{_spelled_table(definition.table)} ({components}) [{definition.presence.value}]"
    )


def _spelled_constraint(constraint: CollidingTemporalConstraint) -> str:
    columns = ", ".join(column.name for column in constraint.columns)
    return (
        f"temporal {constraint.kind} on {_spelled_table(constraint.table)} ({columns}) "
        f"[{constraint.presence.value}]"
    )


def _spelled_relation(held: CollidingRelation) -> str:
    kind = "table" if isinstance(held.relation, PhysicalTable) else "sequence"
    return f"{kind} {_spelled_table(held.relation)} [{held.presence.value}]"


def _spelled_table(table: PhysicalTable | PhysicalSequence) -> str:
    return ".".join((*table.qualifier, table.name))
