from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TypeGuard

from parallax.core.metamodel import EntityIdentity
from parallax.core.write_plan.steps import (
    AnyCount,
    FailedPrecondition,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    MissingTarget,
    NonTemporalConcurrency,
    OptimisticConflict,
    PlannedInsert,
    PlannedWrite,
    StaleWrite,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
)

__all__ = [
    "CardinalityCorruptionError",
    "MissingTargetError",
    "OptimisticLockConflictError",
    "StaleWriteError",
    "WriteEffectError",
    "WritePreconditionError",
    "WriteResultError",
    "allocated_keys",
    "enforce_affected_rows",
    "returns_rows",
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


class WritePreconditionError(RuntimeError):
    """A target write's caller-stated starting condition does not hold: the
    state it addresses is gone, or a revision other than ``expected`` replaced
    it.

    ``key`` names the object by its primary key and ``expected`` is the revision
    the caller stated, unchanged. Re-running the transaction re-states the same
    condition, so this is never retriable; nothing reads the row again to say
    which of the two happened.
    """

    def __init__(self, entity: EntityIdentity, key: Mapping[str, object], expected: object) -> None:
        self.entity = entity
        self.key = MappingProxyType(dict(key))
        self.expected = expected
        super().__init__(
            f"{entity.name}: the state this write starts from no longer matches its "
            f"precondition — key={dict(key)!r}, expected revision {expected!r}"
        )


class WriteResultError(RuntimeError):
    """A row-producing write answered rows its statement cannot produce: a row
    missing or in excess of the rows it opened, a row of another width, a cell
    of another type, or one key answered twice.

    Like an excess count, this is an invariant failure rather than a
    concurrency outcome, and it is never retriable. ``expected`` and ``actual``
    count rows; the rows themselves are not retained.
    """

    def __init__(self, entity: EntityIdentity, expected: int, actual: int, reason: str) -> None:
        self.entity = entity
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"{entity.name}: the write answered {actual} row(s) for {expected} it opened — {reason}"
        )


def returns_rows(step: PlannedWrite) -> TypeGuard[PlannedInsert]:
    """Whether ``step``'s statement answers rows: an insert whose key the
    database allocates and returns. Every entry of one Planned Insert carries
    the same generated-value shape, so the first answers for all."""
    if not isinstance(step, PlannedInsert):
        return False
    for value in step.entries[0].row.attributes.values():
        if isinstance(value, MaxPlusOne) and value.returned:
            return True
    return False


def allocated_keys(step: PlannedInsert, rows: Sequence[Sequence[object]]) -> tuple[object, ...]:
    """The key the database allocated for each of ``step``'s entries, in entry
    order, read from the rows its statement answered.

    The statement answers one row per entry, each holding exactly the
    allocated key: an integer, distinct from every other the statement
    answered. Anything else raises :class:`WriteResultError` before any key is
    used.
    """
    expected = len(step.entries)
    if len(rows) != expected:
        raise WriteResultError(
            step.entity,
            expected,
            len(rows),
            "a missing row" if len(rows) < expected else "an excess row",
        )
    keys: list[object] = []
    for row in rows:
        if len(row) != 1:
            raise WriteResultError(
                step.entity, expected, len(rows), f"a row of {len(row)} cell(s), not the key alone"
            )
        (key,) = row
        if not isinstance(key, int) or isinstance(key, bool):
            raise WriteResultError(
                step.entity, expected, len(rows), f"a key of type {type(key).__name__}"
            )
        if key in keys:
            raise WriteResultError(step.entity, expected, len(rows), f"the key {key} twice")
        keys.append(key)
    return tuple(keys)


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
    # A step carrying an exact count addresses rows by key: a Resolved Mutation Selection
    # implies an unbounded effect and a Milestone Target belongs to a close,
    # both refused while the step is settled.
    target = step.target
    assert isinstance(target, KeyTarget | MilestoneTarget)
    if actual_count > policy.expected:
        raise CardinalityCorruptionError(step.entity, target, policy.expected, actual_count)
    match policy.on_shortfall:
        case MissingTarget():
            error: type[WriteEffectError] = MissingTargetError
        case StaleWrite():
            error = StaleWriteError
        case OptimisticConflict():
            error = OptimisticLockConflictError
        case FailedPrecondition():
            raise _failed_precondition(step.entity, step.concurrency, target)
    raise error(step.entity, target, policy.expected, actual_count)


def _failed_precondition(
    entity: EntityIdentity,
    concurrency: NonTemporalConcurrency | TemporalConcurrency,
    target: AddressedTarget,
) -> WritePreconditionError:
    """The caller's condition a gated step that fell short bound: its gate
    carries the revision the caller stated, and its target the key."""
    if isinstance(concurrency, Versioned) and isinstance(concurrency.gate, VersionGate):
        expected: object = concurrency.gate.observed_version
    else:
        assert isinstance(concurrency, TemporalGate)  # only a gated step binds a precondition
        expected = concurrency.observed_start
    names = tuple(attribute.name for attribute in target.key_attributes)
    values = target.key_values[0] if isinstance(target, KeyTarget) else target.key_values
    return WritePreconditionError(entity, dict(zip(names, values, strict=True)), expected)


def _address(target: AddressedTarget) -> str:
    if isinstance(target, KeyTarget):
        names = tuple(attribute.name for attribute in target.key_attributes)
        return f"keys={[dict(zip(names, row, strict=True)) for row in target.key_values]!r}"
    key = dict(zip((a.name for a in target.key_attributes), target.key_values, strict=True))
    ends = tuple(attribute.name for attribute in target.end_attributes)
    return f"key={key!r} ends={dict(zip(ends, target.end_values, strict=True))!r}"
