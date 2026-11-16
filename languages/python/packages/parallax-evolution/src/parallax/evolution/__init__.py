"""Compare two Domain Models and produce the schema change between them."""

from __future__ import annotations

from parallax.evolution._domain_models import evolve
from parallax.evolution.internal.model_evolution import (
    ABSENT,
    Absent,
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    Evolution,
    UnilateralEvolution,
)
from parallax.evolution.internal.schema_delta import (
    CoordinatedMigration,
    CreatedIndex,
    ManualAction,
    ManualStep,
    MigrationStatement,
    SchemaDelta,
    SchemaTarget,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
    coordinated_migration,
    schema_delta,
)

__all__ = [
    "ABSENT",
    "Absent",
    "CoordinatedEvolution",
    "CoordinatedMigration",
    "CoordinationReason",
    "CoordinationRequirement",
    "CreatedIndex",
    "Evolution",
    "ManualAction",
    "ManualStep",
    "MigrationStatement",
    "SchemaDelta",
    "SchemaTarget",
    "UnilateralEvolution",
    "UnsupportedSchemaEvolutionError",
    "UnsupportedSchemaOperation",
    "coordinated_migration",
    "evolve",
    "schema_delta",
]
