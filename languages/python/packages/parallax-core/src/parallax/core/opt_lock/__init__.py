from __future__ import annotations

from typing import Final

from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.opt_lock._compile import MODEL_COMPILER
from parallax.core.opt_lock._facet import (
    FACET_KEY,
    OPT_LOCK_MODULE,
    ExplicitVersion,
    OptimisticKey,
    OptimisticLockFacet,
    TransactionTimeDerived,
    view,
)
from parallax.core.opt_lock._rules import ISSUE_CODES, RULE_SET
from parallax.core.unit_work import (
    Concurrency,
    KeyedMutation,
    ObjectKey,
    RetainedObservation,
    SettledEvidence,
    VersionObservation,
    WriteObservation,
)

__all__ = [
    "FACET_KEY",
    "INITIAL_VERSION",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "OPT_LOCK_MODULE",
    "RULE_SET",
    "CallerAuthoredVersionError",
    "ExplicitVersion",
    "OptimisticKey",
    "OptimisticLockFacet",
    "TransactionTimeDerived",
    "UnobservedVersionError",
    "advance",
    "effective_strategy",
    "optimistic_key",
    "reject_caller_authored_version",
    "require_observed",
    "settled_evidence",
    "view",
]

# The derived initial version every versioned insert carries, ignoring any
# row-carried value (`core/schemas/metamodel.schema.json` and `m-sql.md`).
INITIAL_VERSION: Final[int] = 1


class CallerAuthoredVersionError(RuntimeError):
    """A keyed update's row carries an explicit value for the entity's own
    optimistic-lock version attribute (`m-opt-lock` "Version values are
    framework-owned"; ADR 0013).

    The version is framework-owned end to end: the new version is always
    runtime-computed (``observed + 1``) from the observation the write's own
    source retained, never a value the row carries. A row that still authors the
    version attribute is refused loudly here — never silently double-assigned
    against whichever of the two (the row's value, or the derived advance)
    happened to win.
    """


class UnobservedVersionError(RuntimeError):
    """A keyed update/delete of a versioned row reached settlement carrying no
    observed version.

    The new version is always computed from the observed one (``observed + 1``),
    so with no observed version there is nothing to advance from — and, in
    optimistic mode, nothing to gate on. The framework never issues an implicit
    resolving ``SELECT`` on behalf of a keyed write (`m-opt-lock` "Version values
    are framework-owned"; ADR 0013): this is a read-before-write programming
    error, raised before any DML runs, in EITHER concurrency mode.
    """


def require_observed(entity: str, observation: WriteObservation | None) -> int:
    """The version a keyed update/delete of a versioned row advances from.

    Raises :class:`UnobservedVersionError` when the write reached settlement
    carrying no Version Observation (`m-opt-lock` "Version values are
    framework-owned"). A row that itself carries an explicit version value is
    refused earlier, by :func:`reject_caller_authored_version` — this function's
    own row is always the framework-derived one, never a caller-authored version.
    """
    if not isinstance(observation, VersionObservation):
        raise UnobservedVersionError(
            f"{entity}: a keyed update/delete of a versioned row requires the version its "
            "source value observed (a prior find) — the framework never issues an implicit "
            "resolving read on behalf of a keyed write"
        )
    return observation.observed_version


def advance(observed: int) -> int:
    """The next version a successful write advances to: ``observed + 1``.

    Runtime-computed, always — a caller-authored version value is never
    accepted as the new version (`m-opt-lock` "Version values are
    framework-owned").
    """
    return observed + 1


def effective_strategy(preference: Concurrency, key: OptimisticKey | None) -> Concurrency:
    """The Effective Concurrency Strategy an Entity whose Optimistic Lock Facet
    answers ``key`` participates under, given the unit of work's resolved
    Concurrency Preference (`m-unit-work` "Strategy selection"; ADR 0059).

    The preference is the caller's ergonomic choice and this is the safe result
    derived from it. ``locking`` forces the Locking strategy on every Entity —
    the workflow-level override. ``optimistic`` means *gate-preferred*, not
    lock-free: an Entity whose family supplies a version source (an explicit
    version Attribute, or a Transaction-Time milestone start) participates
    optimistically, while an unversioned Non-Temporal family has no gate to
    recover correctness with and therefore falls back to `m-read-lock`'s shared
    lock. One transaction consequently mixes strategies across Entities, and
    every consumer — read-lock derivation per deep-fetch level, gate settlement
    per planned write, write-evidence rules — resolves through the key's own
    answer rather than reading the preference directly.

    An Identity the facet does not name has no key and takes the same Locking
    fallback: an unrecognized Entity is never granted a gate it cannot supply.
    """
    if preference == "locking" or key is None:
        return "locking"
    return key.effective_strategy(preference)


def optimistic_key(model: Metamodel, entity: EntityIdentity) -> OptimisticKey:
    """``entity``'s Optimistic Key under ``model`` — one of the three variants,
    never their absence (:meth:`OptimisticLockFacet.required_key`).

    :func:`effective_strategy` takes the facet's own answer instead, absence
    included, because what follows from absence there is the shared lock a write
    it cannot gate would get anyway — safe for a lock, and a different question
    from which state a write claims.
    """
    return view(model).required_key(entity)


def settled_evidence(
    key: OptimisticKey,
    mutation: KeyedMutation,
    *,
    object_key: ObjectKey | None,
    observation: WriteObservation | RetainedObservation | None,
) -> SettledEvidence | None:
    """What a keyed write settles against, and therefore claims — the total
    derivation over the write kind (`m-unit-work` "Observed-State Coalescing"),
    which ``key``'s own variant answers.

    The arms are derived from declared facts alone — this family's Optimistic Key
    and the write's own mutation — never from an absent observation, which would
    sweep in the insert: it observes no state either and has no prior row to
    claim at all. ``observation`` reaches the answer only for a versioned or
    temporal family, and ``object_key`` only for an unversioned Non-Temporal
    one; either may be absent for a write that has nothing for a claim to be
    about, which then settles against nothing.
    """
    return key.settled_evidence(mutation, object_key=object_key, observation=observation)


def reject_caller_authored_version(entity: str, version_attr: str) -> None:
    """Raise :class:`CallerAuthoredVersionError` for a keyed update row that
    itself carries an explicit value for ``version_attr`` (`m-opt-lock`
    "Version values are framework-owned"; ADR 0013).

    Checked BEFORE the observation-required path (:func:`require_observed`)
    even runs: the version is framework-owned end to end, so a row-carried
    value is never a legitimate alternative source, observed or not — it is
    refused outright, never silently preferred over (or overridden by) the
    observation the write's source retained.
    """
    raise CallerAuthoredVersionError(
        f"{entity}: a keyed update's row carries an explicit value for {version_attr!r} — "
        "the optimistic-lock version is framework-owned end to end and is never caller "
        "data; the advance is always derived from the observation the write's source "
        "retained (a prior find), never a row-carried value (m-opt-lock)"
    )
