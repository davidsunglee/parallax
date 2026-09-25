from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core import opt_lock
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.unit_work import Concurrency, VersionArithmetic, WriteObservation

__all__ = ["CONCURRENCY"]

# `m-opt-lock` owns both numbers, so the step is read as the difference one
# advance makes rather than restated here. The arithmetic varies with nothing —
# not the model, not the Entity, not the transaction's Concurrency Preference.
_VERSION_ARITHMETIC: Final[VersionArithmetic] = VersionArithmetic(
    initial=opt_lock.INITIAL_VERSION,
    increment=opt_lock.advance(opt_lock.INITIAL_VERSION) - opt_lock.INITIAL_VERSION,
)


@dataclass(frozen=True, slots=True)
class _ConcurrencyAdapter:
    """``m-opt-lock``'s per-Entity version source, gate eligibility, version
    arithmetic, and observation-licensing policy, structurally satisfying
    ``ConcurrencyStrategy``.

    Every entity-scoped answer reads the Optimistic Lock Facet of the model the
    caller passes, so one stateless instance serves every model.
    """

    def version_attribute(
        self, model: Metamodel, entity: EntityIdentity
    ) -> AttributeIdentity | None:
        key = opt_lock.view(model).key(entity)
        return key.attribute if isinstance(key, opt_lock.ExplicitVersion) else None

    def gates(self, concurrency: Concurrency, model: Metamodel, entity: EntityIdentity) -> bool:
        return opt_lock.effective_strategy(concurrency, opt_lock.view(model).key(entity)) == (
            "optimistic"
        )

    def version_arithmetic(self) -> VersionArithmetic:
        return _VERSION_ARITHMETIC

    def require_version(self, entity: EntityIdentity, observation: WriteObservation | None) -> int:
        return opt_lock.require_observed(entity.name, observation)

    def reject_authored_version(self, entity: EntityIdentity, attribute: AttributeIdentity) -> None:
        opt_lock.reject_caller_authored_version(entity.name, attribute.name)


CONCURRENCY: Final[_ConcurrencyAdapter] = _ConcurrencyAdapter()
