"""The Materialized Write Group (`m-unit-work` "Materialized Write Groups").

A predicate-selected write whose target requires per-row observation cannot be
planned from buffered data alone. Its resolving read happens before the pure
planning call, in Unit Work's write-input preparation, and settles into
exactly one compact private group per authored predicate: one shared
primary-key shape, one immutable value column per key attribute, and either an
aligned version column or complete Predecessor Columns under one group-wide
Transaction-Time Basis. The group is an input to planning, never a member of a
Write Plan; it stays indivisible through batching and dependency ordering and
disappears during finalization.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.unit_work.columns import ColumnSlice, PredecessorColumns
from parallax.core.unit_work.instructions import PredicateWrite
from parallax.core.unit_work.observe import TransactionTimeBasis

__all__ = ["GroupObservations", "MaterializedWriteGroup", "TemporalColumns", "VersionColumns"]


@dataclass(frozen=True, slots=True)
class VersionColumns:
    """One aligned optimistic-lock version value per resolved row."""

    versions: ColumnSlice[int]


@dataclass(frozen=True, slots=True)
class TemporalColumns:
    """Complete predecessor state per resolved row, under one group-wide basis.

    The one Transaction-Time pin the resolving read used determines this basis
    for every row; a resolving read can never mix latest- and historical-pinned
    rows, so there is no per-row basis column.
    """

    predecessors: PredecessorColumns
    transaction_time_basis: TransactionTimeBasis


type GroupObservations = VersionColumns | TemporalColumns
"""One authored predicate's aligned observation evidence, one member per
resolved row and one basis (if temporal) for the whole group."""


@dataclass(frozen=True, slots=True)
class MaterializedWriteGroup:
    """One authored predicate's compact, private, indivisible planning input.

    ``key_attributes`` names the canonical primary-key shape once (by declared
    member name, matching the write-instruction row convention); ``key_columns``
    carries one aligned value column per key attribute, in database resolution
    order. Every key and observation column shares the same positive row count.
    The group holds no managed Entity object, no per-row keyed-write wrapper,
    and no per-row Predecessor Row object.
    """

    mutation: PredicateWrite
    key_attributes: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    observations: GroupObservations

    def __post_init__(self) -> None:
        if not self.key_attributes:
            raise ValueError("a Materialized Write Group names at least one key Attribute")
        if len(self.key_columns) != len(self.key_attributes):
            raise ValueError(
                "a Materialized Write Group carries one key column per key Attribute: "
                f"expected {len(self.key_attributes)}, got {len(self.key_columns)}"
            )
        length = len(self.key_columns[0])
        if length == 0:
            raise ValueError("a Materialized Write Group addresses at least one row")
        if any(len(column) != length for column in self.key_columns):
            raise ValueError(
                "a Materialized Write Group's key columns share one positive row count"
            )
        if _observation_length(self.observations) != length:
            raise ValueError(
                "a Materialized Write Group's observation column carries the same row count as "
                f"its key columns: expected {length}, got {_observation_length(self.observations)}"
            )

    def __len__(self) -> int:
        return len(self.key_columns[0])


def _observation_length(observations: GroupObservations) -> int:
    if isinstance(observations, VersionColumns):
        return len(observations.versions)
    return observations.predecessors.length
