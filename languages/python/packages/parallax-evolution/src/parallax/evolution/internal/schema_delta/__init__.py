from __future__ import annotations

from typing import Final

from parallax.core.internal.base import InternalError
from parallax.core.internal.dialect import Dialect, Unsupported
from parallax.evolution.internal.model_evolution import UnilateralEvolution
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
    CollidingTemporalConstraint,
    CollisionGroup,
    CreatedIndex,
    PhysicalLocation,
    SchemaDelta,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)

__all__ = [
    "CreatedIndex",
    "PhysicalLocation",
    "SchemaDelta",
    "UnsupportedSchemaEvolutionError",
    "UnsupportedSchemaOperation",
    "schema_delta",
]


def schema_delta(evolution: UnilateralEvolution, dialect: Dialect) -> SchemaDelta:
    """The ordered ``dialect`` statements that apply ``evolution`` to a database.

    The complete plan is named, ordered, and rendered before any statement
    escapes, so a Dialect that cannot spell one operation yields no partial
    delta: :class:`UnsupportedSchemaEvolutionError` carries every refusal at once,
    in the order the statements would have run. A derived Physical Index Name
    clash raises the ``physical-index-name-collision``
    :class:`~parallax.core.internal.base.InternalError` naming every group rather than
    renaming either definition.

    The statements are prefix-safe in the returned order and deliberately not
    idempotent; creating a unique Index is the authoritative validation of the
    data already stored.
    """
    built = plan(evolution, dialect)
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
                physical_table=operation.definition.table,
                logical_index_identity=operation.definition.index,
                unique=operation.definition.unique,
            )
            for operation in ordered
            if isinstance(operation, CreateIndex)
        ),
    )


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
Physical Index Name: a defensive backstop for an unexpected 128-bit fingerprint
collision, not an ordinary control path, since a definition's name is derived
from its own facts alone."""


def _reject_collisions(built: Plan, dialect: Dialect) -> None:
    """Refuse a name two Index definitions the database holds at once both derived."""
    if built.collisions:
        raise _collision_refusal(dialect.name, built.collisions)


def _collision_refusal(dialect_identity: str, groups: tuple[CollisionGroup, ...]) -> InternalError:
    """The refusal naming the Dialect and every collision group, in Physical
    Index Name order, each with the shared name and its colliding definitions."""
    spelled = "; ".join(
        f"{group.name.value} is derived by "
        + ", ".join(
            [_spelled_index(definition) for definition in group.definitions]
            + [_spelled_constraint(constraint) for constraint in group.temporal_constraints]
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
        f"{definition.table.name} ({components}) [{definition.presence.value}]"
    )


def _spelled_constraint(constraint: CollidingTemporalConstraint) -> str:
    columns = ", ".join(column.name for column in constraint.columns)
    return (
        f"temporal {constraint.kind} on {constraint.table.name} ({columns}) "
        f"[{constraint.presence.value}]"
    )
