from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import batch_write, bitemp_write, txtime_write
from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.unit_work import (
    NO_AUDIT,
    Concurrency,
    MilestoneTopology,
    PlannedClose,
    TransactionInstant,
    WritePlanner,
)
from parallax.core.unit_work import plan_temporal_close as _plan_temporal_close
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._keyed_sql import collapse_group_key

__all__ = ["build_write_planner", "plan_temporal_close"]


@dataclass(frozen=True, slots=True)
class _BatchingAdapter:
    """``m-batch-write``'s collapse-eligibility policy plus the layout-derived
    physical grouping key, structurally satisfying ``BatchingStrategy``."""

    def collapses(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        mutation: str,
        rows: Sequence[Mapping[str, object]],
    ) -> bool:
        return batch_write.collapses(model, entity, mutation, rows)

    def group_key(
        self, model: Metamodel, entity: EntityMetadata, mutation: str, row: Mapping[str, object]
    ) -> object:
        return collapse_group_key(model, entity, mutation, row)


@dataclass(frozen=True, slots=True)
class _TemporalAdapter:
    """Dispatch between the Transaction-Time-Only and Bitemporal facets,
    structurally satisfying ``TemporalStrategy``.

    Which facet answers is itself part of "how a temporal facet describes a
    mutation" — the planner cannot import either facet module, so this
    composition-root adapter selects between them from the declaring entity's
    own declared As-Of Axes, a plain Metamodel fact the planner already reads
    directly.
    """

    def topology(self, entity: EntityMetadata, mutation: str) -> MilestoneTopology:
        strategy = (
            bitemp_write.RECTANGLE_SPLIT
            if entity.as_of_axis(TemporalDimension.VALID_TIME) is not None
            else txtime_write.MILESTONE_CHAIN
        )
        return strategy.topology(mutation)


def build_write_planner(model: Metamodel) -> WritePlanner:
    """One ``WritePlanner`` for ``model``, wired with production strategies.

    Called once at the composition root (:mod:`~parallax.snapshot.handle.
    _database`) and identically by the conformance engine's compile lane, so
    the two lanes plan through the same deterministic computation.
    """
    return WritePlanner(
        model,
        batching=_BatchingAdapter(),
        concurrency=CONCURRENCY,
        temporal=_TemporalAdapter(),
        audit=NO_AUDIT,
    )


def plan_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    model: Metamodel,
    concurrency: Concurrency,
    tx_instant: TransactionInstant,
    observed_tx_start: object | None,
    observed_valid_end: object | None = None,
) -> PlannedClose:
    """The `m-opt-lock` conflict lane's standalone close probe, wired with the
    same concurrency adapter :func:`build_write_planner` injects — see
    :func:`parallax.core.unit_work.plan_temporal_close`."""
    return _plan_temporal_close(
        identity,
        entity_name,
        model,
        concurrency,
        CONCURRENCY,
        tx_instant,
        observed_tx_start,
        observed_valid_end,
    )
