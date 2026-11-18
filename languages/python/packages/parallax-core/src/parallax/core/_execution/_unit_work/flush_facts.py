from __future__ import annotations

from dataclasses import dataclass, field

from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.row_acquisition import CoverageReadKey
from parallax.core._execution._unit_work.strategy import AuditDecoration
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.inheritance import InheritanceEntityView
from parallax.core.internal.metamodel import CompiledEntity, EntityIdentity
from parallax.core.internal.planned_step.write_effects import TemporalWriteOwnership

__all__ = ["FlushFacts"]

type _ReadKeys = dict[tuple[EntityIdentity, bool], CoverageReadKey]


def _no_read_keys() -> _ReadKeys:
    return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class FlushFacts:
    """What every write one flush settles shares: the unit of work's
    Concurrency Preference, the attempt's Transaction Instant, captured only
    once a surviving temporal write needs it, the ownership planning reads,
    the configured audit, and whether a guard can prove a milestone a write
    leaves unchanged (``guards``).

    It lives for one finalization, and nothing a plan holds reaches it.
    """

    preference: ConcurrencyPreference
    instant: TransactionInstant
    ownership: TemporalWriteOwnership
    audit: AuditDecoration
    guards: bool
    _read_keys: _ReadKeys = field(
        init=False, default_factory=_no_read_keys, repr=False, compare=False
    )

    def coverage_read_key(
        self, entity: CompiledEntity, view: InheritanceEntityView, *, gated: bool
    ) -> CoverageReadKey:
        """The read ``entity``'s ranges read their coverage by, whose writes
        gate where ``gated`` and whose reads take the shared row lock
        otherwise: one instance for every range of one Entity and lock
        decision this flush settles."""
        shared_lock = not gated
        read_keys = self._read_keys
        held = read_keys.get((entity.identity, shared_lock))
        if held is None:
            held = read_keys[entity.identity, shared_lock] = CoverageReadKey(
                entity, view.primary_key.identity, shared_lock
            )
        return held
