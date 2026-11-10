from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal, TypeGuard

from parallax.core.internal.base import ConflictError, InternalError
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.write_plan.steps import (
    AnyCount,
    FailedPrecondition,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    MissingTarget,
    NonTemporalConcurrency,
    OptimisticConflict,
    PlannedInsert,
    PlannedStep,
    StaleWrite,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
)

__all__ = [
    "CARDINALITY_CORRUPTION",
    "MISSING_TARGET",
    "OPTIMISTIC_LOCK_CONFLICT",
    "STALE_WRITE",
    "WRITE_PRECONDITION_FAILED",
    "WRITE_RESULT_INVALID",
    "ShortfallCode",
    "WriteEffectCode",
    "WritePreconditionError",
    "allocated_keys",
    "cardinality_corruption",
    "enforce_affected_rows",
    "returns_allocated_keys",
    "shortfall",
]

type AddressedTarget = KeyTarget | MilestoneTarget
"""The Write Target kinds that carry an exact expectation, and therefore the
only kinds an affected-row refusal can name."""

type WriteEffectCode = Literal[
    "missing-target",
    "stale-write",
    "optimistic-lock-conflict",
    "write-precondition-failed",
]
"""The :class:`~parallax.core.internal.base.ConflictError` codes a write's effect is
refused by, of which only an Optimistic Lock Conflict is transient."""

MISSING_TARGET: Final = "missing-target"
STALE_WRITE: Final = "stale-write"
OPTIMISTIC_LOCK_CONFLICT: Final = "optimistic-lock-conflict"
WRITE_PRECONDITION_FAILED: Final = "write-precondition-failed"
CARDINALITY_CORRUPTION: Final = "cardinality-corruption"
WRITE_RESULT_INVALID: Final = "write-result-invalid"

type ShortfallCode = Literal["missing-target", "stale-write", "optimistic-lock-conflict"]

_SUMMARIES: Final[dict[str, str]] = {
    MISSING_TARGET: "the addressed rows do not exist",
    STALE_WRITE: "an ungated observation-requiring write fell short",
    OPTIMISTIC_LOCK_CONFLICT: "a concurrent write changed the gated rows first",
    CARDINALITY_CORRUPTION: "the write affected more rows than its target addresses",
}


def shortfall(
    code: ShortfallCode,
    entity: EntityIdentity,
    target: AddressedTarget,
    expected: int,
    actual: int,
) -> ConflictError:
    """The conflict a write that reached fewer rows than ``target`` addresses
    is refused by, naming the row by its key; the counts are in the message.

    Only a gated shortfall, ``optimistic-lock-conflict``, is transient: a
    re-read resolves it, so the bounded retry loop replays it. The addressed
    rows being absent, or an ungated write falling short, cannot change on a
    re-run.
    """
    return ConflictError(
        code,
        _effect_message(code, entity, target, expected, actual),
        entity=entity.canonical,
        key=_target_key(target),
        transient=code == OPTIMISTIC_LOCK_CONFLICT,
    )


def cardinality_corruption(
    entity: EntityIdentity, target: AddressedTarget, expected: int, actual: int
) -> InternalError:
    """The invariant failure a write that affected more rows than ``target``
    addresses is refused by: an accepted identity, storage, or lowering
    invariant does not hold, so it is no concurrency outcome."""
    return InternalError(
        CARDINALITY_CORRUPTION,
        _effect_message(CARDINALITY_CORRUPTION, entity, target, expected, actual),
    )


def _effect_message(
    code: str, entity: EntityIdentity, target: AddressedTarget, expected: int, actual: int
) -> str:
    return (
        f"{entity.name}: {_SUMMARIES[code]} — affected {actual} row(s), expected {expected} "
        f"({_address(target)})"
    )


def _target_key(target: AddressedTarget) -> dict[str, object]:
    """The primary key, by declared attribute name, of the row ``target``
    addresses first."""
    names = tuple(attribute.name for attribute in target.key_attributes)
    values = target.key_values[0] if isinstance(target, KeyTarget) else target.key_values
    return dict(zip(names, values, strict=True))


class WritePreconditionError(ConflictError):
    """A target write's expected starting state no longer holds.

    A target write's caller-stated starting condition does not hold: the
    state it addresses is gone, or a revision other than ``expected`` replaced
    it.

    ``entity`` is the canonical Entity name, ``key`` names the object by its
    primary key, and ``expected`` is the revision the caller stated, unchanged.
    Re-running the transaction re-states the same condition, so this is never
    transient; nothing reads the row again to say which of the two happened.
    """

    def __init__(self, entity: EntityIdentity, key: Mapping[str, object], expected: object) -> None:
        super().__init__(
            WRITE_PRECONDITION_FAILED,
            f"{entity.name}: the state this write starts from no longer matches its "
            f"precondition — key={dict(key)!r}, expected revision {expected!r}",
            entity=entity.canonical,
            key=key,
        )
        self._expected = expected

    @property
    def entity(self) -> str:
        entity = super().entity
        assert entity is not None  # the constructor always names the row
        return entity

    @property
    def key(self) -> Mapping[str, object]:
        key = super().key
        assert key is not None  # the constructor always names the row
        return key

    @property
    def expected(self) -> object:
        return self._expected


def _write_result_refusal(
    entity: EntityIdentity, expected: int, actual: int, reason: str
) -> InternalError:
    """The invariant failure a row-producing write is refused by where it
    answered rows its statement cannot produce: a row missing or in excess of
    the rows it opened, a row of another width, a cell of another type, or one
    key answered twice. The rows themselves are not retained."""
    return InternalError(
        WRITE_RESULT_INVALID,
        f"{entity.name}: the write answered {actual} row(s) for {expected} it opened — {reason}",
    )


def returns_allocated_keys(step: PlannedStep) -> TypeGuard[PlannedInsert]:
    """Whether ``step``'s statement answers rows: an insert whose key the
    database allocates and returns. Every entry of one Planned Insert carries
    the same generated-value shape, so the first answers for all."""
    if not isinstance(step, PlannedInsert):
        return False
    for value in step.entries[0].row.cells:
        if isinstance(value, MaxPlusOne) and value.returned:
            return True
    return False


def allocated_keys(step: PlannedInsert, rows: Sequence[Sequence[object]]) -> tuple[object, ...]:
    """The key the database allocated for each of ``step``'s entries, in entry
    order, read from the rows its statement answered.

    The statement answers one row per entry, each holding exactly the
    allocated key: an integer, distinct from every other the statement
    answered. Anything else raises the ``write-result-invalid``
    :class:`~parallax.core.internal.base.InternalError` before any key is used.
    """
    expected = len(step.entries)
    if len(rows) != expected:
        raise _write_result_refusal(
            step.entity,
            expected,
            len(rows),
            "a missing row" if len(rows) < expected else "an excess row",
        )
    keys: list[object] = []
    for row in rows:
        if len(row) != 1:
            raise _write_result_refusal(
                step.entity, expected, len(rows), f"a row of {len(row)} cell(s), not the key alone"
            )
        (key,) = row
        if not isinstance(key, int) or isinstance(key, bool):
            raise _write_result_refusal(
                step.entity, expected, len(rows), f"a key of type {type(key).__name__}"
            )
        if key in keys:
            raise _write_result_refusal(step.entity, expected, len(rows), f"the key {key} twice")
        keys.append(key)
    return tuple(keys)


def enforce_affected_rows(step: PlannedStep, actual_count: int) -> None:
    """Interpret one step's execution result against its Affected Rows Policy.

    Inserts carry no policy, so they are accepted and return. An ``AnyCount``
    policy accepts every nonnegative result. Against an ``ExactCount`` a
    shortfall raises the conflict named by the step's own shortfall tag, and an
    excess always raises the ``cardinality-corruption`` invariant failure — the
    excess failure is invariant and is never carried in the policy.
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
        raise cardinality_corruption(step.entity, target, policy.expected, actual_count)
    match policy.on_shortfall:
        case MissingTarget():
            code: ShortfallCode = MISSING_TARGET
        case StaleWrite():
            code = STALE_WRITE
        case OptimisticConflict():
            code = OPTIMISTIC_LOCK_CONFLICT
        case FailedPrecondition():
            raise _failed_precondition(step.entity, step.concurrency, target)
    raise shortfall(code, step.entity, target, policy.expected, actual_count)


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
    return WritePreconditionError(entity, _target_key(target), expected)


def _address(target: AddressedTarget) -> str:
    if isinstance(target, KeyTarget):
        names = tuple(attribute.name for attribute in target.key_attributes)
        return f"keys={[dict(zip(names, row, strict=True)) for row in target.key_values]!r}"
    key = dict(zip((a.name for a in target.key_attributes), target.key_values, strict=True))
    ends = tuple(attribute.name for attribute in target.end_attributes)
    return f"key={key!r} ends={dict(zip(ends, target.end_values, strict=True))!r}"
