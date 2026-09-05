"""``parallax.evolution.schema_delta`` enforcement scope (m-schema-delta).

The ordered dialect statements that carry a database from one accepted Metamodel
to another. :func:`schema_delta` accepts a Unilateral Evolution and nothing else:
a Coordinated Evolution is a complete description whose application needs
authoring, data, or rollout coordination, so it is not an input to schema
generation at all — the type says so rather than a runtime check.

Generation is pure and applies nothing. It makes no provider or database call,
runs no preflight query, and returns statements the APPLICATION executes; the
later Model Edition is published only after every one of them succeeds.

``m-schema-delta`` depends on ``m-model-evolution`` for the description it
lowers, on ``m-metamodel`` for the declarations an operation names, on
``m-storage-layout`` for every physical fact, and on ``m-dialect`` for the
spellings. It branches on no dialect name: a Dialect value determines the whole
output.
"""

from __future__ import annotations

from parallax.core.dialect import Dialect, Unsupported
from parallax.evolution.model_evolution import UnilateralEvolution
from parallax.evolution.schema_delta._naming import collision_groups
from parallax.evolution.schema_delta._order import order
from parallax.evolution.schema_delta._physical import (
    CreateIndex,
    PhysicalOperation,
    location_of,
)
from parallax.evolution.schema_delta._plan import Plan, plan
from parallax.evolution.schema_delta._render import render
from parallax.evolution.schema_delta._values import (
    CollidingIndex,
    CollisionGroup,
    CreatedIndex,
    IndexPresence,
    PhysicalIndexNameCollisionError,
    PhysicalLocation,
    SchemaDelta,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)

__all__ = [
    "CollidingIndex",
    "CollisionGroup",
    "CreatedIndex",
    "IndexPresence",
    "PhysicalIndexNameCollisionError",
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
    clash raises :class:`PhysicalIndexNameCollisionError` with every group rather
    than renaming either definition.

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


def _reject_collisions(built: Plan, dialect: Dialect) -> None:
    """Refuse a name two distinct Index definitions both derived.

    The check spans every Index of both endpoints, not only the ones this delta
    creates or drops: an Index it never mentions is still an object in the
    database while a new one is created beside it, so the two coexist during some
    prefix of the statements.
    """
    groups = collision_groups(built.indices)
    if groups:
        raise PhysicalIndexNameCollisionError(dialect.name, groups)
