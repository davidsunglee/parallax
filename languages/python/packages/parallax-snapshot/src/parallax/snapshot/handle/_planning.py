"""``parallax.snapshot.handle._planning`` — the Write Planner composition root.

:func:`build_write_planner` is the one place the optional policy modules
(``batch_write``, ``opt_lock``, ``txtime_write``, ``bitemp_write``) are wired
into a :class:`~parallax.core.unit_work.WritePlanner` as its strategy ports —
`parallax.snapshot.handle` is the sole module cleared to import both
``batch_write`` and ``unit_work``. Both the developer transaction path
(:mod:`~parallax.snapshot.handle._database`) and the conformance engine's
compile lane call this same factory, so lane equivalence is structural rather
than parallel wiring that could drift.

:func:`plan_temporal_close` re-wires the SAME concurrency adapter into
:func:`~parallax.core.unit_work.plan_temporal_close`, the `m-opt-lock`
conflict-probe's standalone close settlement — preserving its existing
signature so every caller of the pre-Phase-8 seam is unaffected.

The three adapter classes translate this scope's own optional-policy calls
into the neutral vocabulary the planner's strategy Protocols declare;
nothing here inherits a Protocol, matching the ``Clock`` / ``DbPort``
convention every other strategy shape in the tree follows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import batch_write, bitemp_write, opt_lock, txtime_write
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
)
from parallax.core.unit_work import (
    NO_AUDIT,
    Concurrency,
    MilestoneTopology,
    PlannedClose,
    TransactionInstant,
    TransactionTimeBasis,
    WriteObservation,
    WritePlanner,
)
from parallax.core.unit_work import plan_temporal_close as _plan_temporal_close
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
class _ConcurrencyAdapter:
    """``m-opt-lock``'s version arithmetic and observation-licensing policy,
    structurally satisfying ``ConcurrencyStrategy``."""

    model: Metamodel

    def version_attribute(self, entity: EntityMetadata) -> AttributeIdentity | None:
        key = opt_lock.view(self.model).key(entity.identity)
        return key.attribute if isinstance(key, opt_lock.ExplicitVersion) else None

    def gates(self, concurrency: Concurrency) -> bool:
        return opt_lock.gates(concurrency)

    def initial_version(self) -> int:
        return opt_lock.INITIAL_VERSION

    def advance(self, observed_version: int) -> int:
        return opt_lock.advance(observed_version)

    def require_version(self, entity: EntityIdentity, observation: WriteObservation | None) -> int:
        return opt_lock.require_observed(entity.name, observation)

    def reject_authored_version(self, entity: EntityIdentity, attribute: AttributeIdentity) -> None:
        opt_lock.reject_caller_authored_version(entity.name, attribute.name)

    def check_locking_license(self, concurrency: Concurrency, basis: TransactionTimeBasis) -> None:
        opt_lock.check_locking_license(concurrency, basis)


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
        concurrency=_ConcurrencyAdapter(model),
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
    SAME concurrency adapter :func:`build_write_planner` injects — see
    :func:`parallax.core.unit_work.plan_temporal_close`."""
    return _plan_temporal_close(
        identity,
        entity_name,
        model,
        concurrency,
        _ConcurrencyAdapter(model),
        tx_instant,
        observed_tx_start,
        observed_valid_end,
    )
