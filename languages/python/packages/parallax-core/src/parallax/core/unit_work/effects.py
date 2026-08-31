"""Affected-row enforcement and the Write Effect Error family (m-unit-work).

The unit of work owns the authoritative interpretation of every non-insert
execution result. An executor reports the driver's affected-row count and asks
:func:`enforce_affected_rows` what it means; SQL lowering and database adapters
report counts and never reconstruct or reinterpret these semantics.

Every error in the family carries the same semantic payload — the Entity
Identity, the Write Target retained by reference, the expected count, and the
actual count — and nothing else, so the diagnostic is stable across dialects and
recognizing the canonical optimistic conflict needs no optional concurrency
module.
"""

from __future__ import annotations

from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work.planned import (
    AnyCount,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    MissingTarget,
    OptimisticConflict,
    PlannedInsert,
    PlannedWrite,
    StaleWrite,
)

__all__ = [
    "AddressedTarget",
    "CardinalityCorruptionError",
    "MissingTargetError",
    "OptimisticLockConflictError",
    "StaleWriteError",
    "WriteEffectError",
    "enforce_affected_rows",
]

type AddressedTarget = KeyTarget | MilestoneTarget
"""The Write Target kinds that carry an exact expectation, and therefore the
only kinds a Write Effect Error can name."""


class WriteEffectError(RuntimeError):
    """The closed family raised when a step's Affected Rows Policy is violated.

    The payload is the whole diagnostic: no SQL, statement index, driver
    exception, complete Planned Write, assignments, or observation is retained,
    and ``target`` is the step's own target by reference rather than a copy.
    """

    _summary = "affected an unexpected number of rows"

    def __init__(
        self,
        entity: EntityIdentity,
        target: AddressedTarget,
        expected: int,
        actual: int,
    ) -> None:
        self.entity = entity
        self.target = target
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"{entity.name}: {self._summary} — affected {actual} row(s), expected {expected} "
            f"({_address(target)})"
        )


class MissingTargetError(WriteEffectError):
    """An observation-free keyed write did not reach every row it addressed.

    The addressed rows are simply not there. Re-executing cannot change that, so
    this is never retriable.
    """

    _summary = "the addressed rows do not exist"


class StaleWriteError(WriteEffectError):
    """An ungated observation-requiring write reached fewer rows than it observed.

    The shared read lock that licensed the ungated write should have made the
    shortfall impossible, so it reports a consistency failure rather than a lost
    update, and is never retriable.
    """

    _summary = "an ungated observation-requiring write fell short"


class OptimisticLockConflictError(WriteEffectError):
    """A gated write's version condition no longer held.

    A concurrent write moved the row first. This is the one member of the family
    a re-read can resolve, and therefore the only one the unit of work's retry
    opt-in admits.
    """

    _summary = "a concurrent write changed the gated rows first"


class CardinalityCorruptionError(WriteEffectError):
    """A write affected more rows than its target could address.

    An excess over an exact count means an accepted identity, storage, or
    lowering invariant does not hold. It is an invariant failure rather than a
    concurrency outcome, and is never retriable.
    """

    _summary = "the write affected more rows than its target addresses"


def enforce_affected_rows(step: PlannedWrite, actual_count: int) -> None:
    """Interpret one step's execution result against its Affected Rows Policy.

    Inserts carry no policy, so they are accepted and return. An ``AnyCount``
    policy accepts every nonnegative result. Against an ``ExactCount`` a
    shortfall raises the error named by the step's own shortfall tag, and an
    excess always raises :class:`CardinalityCorruptionError` — the excess
    failure is invariant and is never carried in the policy.
    """
    if isinstance(step, PlannedInsert):
        return
    policy = step.affected_rows
    if isinstance(policy, AnyCount) or actual_count == policy.expected:
        return
    # A step carrying an exact count addresses rows by key: a Validated Mutation Selection
    # implies an unbounded effect and a Milestone Target belongs to a close,
    # both refused while the step is settled.
    target = step.target
    assert isinstance(target, KeyTarget | MilestoneTarget)
    if actual_count > policy.expected:
        raise CardinalityCorruptionError(step.entity, target, policy.expected, actual_count)
    raise _shortfall_error(policy)(step.entity, target, policy.expected, actual_count)


def _shortfall_error(policy: ExactCount) -> type[WriteEffectError]:
    match policy.on_shortfall:
        case MissingTarget():
            return MissingTargetError
        case StaleWrite():
            return StaleWriteError
        case OptimisticConflict():
            return OptimisticLockConflictError


def _address(target: AddressedTarget) -> str:
    if isinstance(target, KeyTarget):
        names = tuple(attribute.name for attribute in target.key_attributes)
        return f"keys={[dict(zip(names, row, strict=True)) for row in target.key_values]!r}"
    key = dict(zip((a.name for a in target.key_attributes), target.key_values, strict=True))
    ends = tuple(attribute.name for attribute in target.end_attributes)
    return f"key={key!r} ends={dict(zip(ends, target.end_values, strict=True))!r}"
