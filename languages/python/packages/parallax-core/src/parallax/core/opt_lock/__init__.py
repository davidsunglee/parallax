"""``parallax.core.opt_lock`` enforcement scope (m-opt-lock).

The optimistic-locking POLICY scope: this module never renders SQL (`m-sql` /
`parallax.snapshot.handle` is the one seam that does) — it owns the
version arithmetic, the observation-licensing rules, and the conflict/historical
error vocabulary the write seam consumes. It also owns the formation half of the
same concern: the Rule Set that keeps a family's version source unambiguous, and
the Optimistic Lock Facet naming that source once per formation so no write path
rediscovers a version column. Consumers reach the facet through :func:`view`, so
generic facet retrieval stays an internal formation seam.
``m-opt-lock`` depends on ``m-unit-work``, ``m-temporal-read``, ``m-metamodel``,
``m-model-formation``, and ``m-inheritance``.
Five normative pieces (`core/spec/
m-opt-lock.md`; `python.md` §5 L584-641; ADR 0013):

1. **No-op-first.** An update whose effective change set is empty is dropped
   before any observation or locking concern — no observation read, no DML,
   zero round trips. Already enforced upstream of this scope, by construction:
   ``Transaction.update`` returns before buffering an empty ``effective_change_set``
   (`parallax.snapshot.handle`), and ``m-unit-work``'s own flush-planner elision
   (:func:`~parallax.core.unit_work.planner._elide`) drops an empty keyed update
   BEFORE observations ever attach (:func:`~parallax.core.unit_work.planner.plan_flush`
   coalesce -> FK-order -> elide -> attach). This module has nothing to add to an
   ordering its two callers already establish structurally.
2. **Prior-observation rule** (:func:`require_observed`): the version driving a
   keyed update/delete of a versioned row must already have been observed by
   this unit of work; unobserved raises before any DML. Caller-authored version
   values are never accepted as gate or new version — the observed value is the
   only legitimate source, and the new version is always ``observed + 1``.
3. **Gate/advance** (:data:`INITIAL_VERSION`, :func:`advance`, :func:`gates`):
   every versioned UPDATE sets ``version = observed + 1`` in BOTH modes;
   optimistic mode additionally gates ``and <version> = ?`` binding the
   observed value LAST. INSERT derives the initial version unconditionally
   (never a row-carried value).
4. **Historical-observation licensing** (:func:`check_locking_license`,
   :class:`HistoricalObservationError`): a temporal observation licenses a
   locking-mode write only when its read was latest-pinned on the Transaction-Time
   axis; a versioned non-temporal row satisfies this trivially. Every
   engine-supplied temporal observation is latest-pinned by construction (the
   conformance engine's case-local shadow tracker only ever tracks the
   CURRENT milestone), so this stays a no-op there — but a REAL
   `Transaction.find` observation of a temporal entity threads the read's own
   Transaction-Time pin through :data:`~parallax.core.unit_work.
   TransactionTimeBasis`, so a locking-mode
   write whose only transaction-scoped observation is historical or
   edge-pinned genuinely raises here. Typed temporal verbs reach this check
   through their transaction-scoped observations.
5. **Conflict classification policy**: this module decides only which shortfall
   tag a write's settled gate earns — a GATED write's shortfall is the
   retriable-when-opted-in optimistic conflict, an UNGATED
   observation-requiring one the distinct non-retriable stale write, because a
   close's ADDRESS is not a gate and so an ungated mismatch is a consistency
   violation rather than a detected-and-retriable conflict. Carrying that
   decision to execution is not this module's concern: a step records the tag,
   and ``m-unit-work``'s affected-row enforcer raises the Write Effect Error it
   names (ADR 0048).

Prior art (Reladomo; semantics, not idioms): the gate plus the
``updatedRows != 1`` conflict mirrors ``MithraAbstractDatabaseObject.
checkUpdatedRows`` under ``ReadCacheWithOptimisticLockingTxParticipationMode``;
retriability-only-on-opt-in mirrors ``MithraTransaction.
setRetryOnOptimisticLockFailure`` (default off).
"""

from __future__ import annotations

from typing import Final

from parallax.core.opt_lock._compile import (
    MODEL_COMPILER,
    OptimisticLockModelCompiler,
    compile_facet,
)
from parallax.core.opt_lock._facet import (
    FACET_KEY,
    OPT_LOCK_MODULE,
    UNVERSIONED,
    ExplicitVersion,
    OptimisticKey,
    OptimisticLockFacet,
    TransactionTimeDerived,
    Unversioned,
    view,
)
from parallax.core.opt_lock._rules import (
    ISSUE_CODES,
    MULTIPLE_ATTRIBUTES,
    RULE_SET,
    TEMPORAL_EXPLICIT_ATTRIBUTE,
    OptimisticLockRuleSet,
    validate_optimistic_locking,
)
from parallax.core.unit_work import (
    Concurrency,
    HistoricalPinned,
    TemporalObservation,
    TransactionTimeBasis,
    VersionObservation,
    WriteObservation,
)

__all__ = [
    "FACET_KEY",
    "INITIAL_VERSION",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "MULTIPLE_ATTRIBUTES",
    "OPT_LOCK_MODULE",
    "RULE_SET",
    "TEMPORAL_EXPLICIT_ATTRIBUTE",
    "UNVERSIONED",
    "CallerAuthoredVersionError",
    "ExplicitVersion",
    "HistoricalObservationError",
    "OptimisticKey",
    "OptimisticLockFacet",
    "OptimisticLockModelCompiler",
    "OptimisticLockRuleSet",
    "TransactionTimeDerived",
    "UnobservedMilestoneError",
    "UnobservedVersionError",
    "Unversioned",
    "advance",
    "check_locking_license",
    "compile_facet",
    "gates",
    "reject_caller_authored_version",
    "require_observed",
    "require_observed_milestone",
    "validate_optimistic_locking",
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
    runtime-computed (``observed + 1``) from this unit of work's own recorded
    observation, never a value the row carries. A row that still authors the
    version attribute is refused loudly here — never silently double-assigned
    against whichever of the two (the row's value, or the derived advance)
    happened to win.
    """


class UnobservedVersionError(RuntimeError):
    """A keyed update/delete of a versioned row this unit of work never observed.

    The new version is always computed from the observed one (``observed + 1``),
    so with no observed version there is nothing to advance from — and, in
    optimistic mode, nothing to gate on. The framework never issues an implicit
    resolving ``SELECT`` on behalf of a keyed write (`m-opt-lock` "Version values
    are framework-owned"; ADR 0013): this is a read-before-write programming
    error, raised before any DML runs, in EITHER concurrency mode.
    """


class UnobservedMilestoneError(RuntimeError):
    """A keyed temporal update/terminate of a milestone this unit of work never
    observed.

    Temporal ``update``/``terminate`` (and their ``*Until`` window forms)
    follow the SAME prior-observation rule as versioned writes (`python.md` §5):
    the close targets — and, under optimistic mode, gates on — the milestone
    this unit of work observed via a transaction-scoped read, and in locking
    mode that read's shared lock is the ungated close's only protection. The
    framework never issues an implicit resolving ``SELECT`` on behalf of a
    keyed write: this is a read-before-write programming error, raised before
    any DML runs, in EITHER concurrency mode. (The neutral conformance lane is
    unaffected — a case document authors its observation control keys
    explicitly, and its choreography is graded against its own goldens.)
    """


class HistoricalObservationError(RuntimeError):
    """A locking-mode write's only transaction-scoped observation is historical
    or edge-pinned (not latest-pinned on the written Transaction-Time dimension).

    Locking-mode closes are ungated, so the shared read lock is the only
    protection; a shared lock on a historical or edge-pinned milestone locks
    the wrong row — a concurrent chain replaces the current row without
    touching the locked one, and the ungated close would then silently re-close
    the replacement (a lost update). The same observation is legal in
    optimistic mode, where the observed gate detects the staleness instead
    (`python.md` §5 L596-611).
    """


def require_observed(entity: str, observation: WriteObservation | None) -> int:
    """The version a keyed update/delete of a versioned row advances from.

    Raises :class:`UnobservedVersionError` when this unit of work recorded no
    Version Observation for the row (`m-opt-lock` "Version values are
    framework-owned"). A row that itself carries an explicit version value is
    refused earlier, by :func:`reject_caller_authored_version` — this function's
    own row is always the framework-derived one, never a caller-authored version.
    """
    if not isinstance(observation, VersionObservation):
        raise UnobservedVersionError(
            f"{entity}: a keyed update/delete of a versioned row requires a version this "
            "unit of work already observed (a prior transaction-scoped find) — the "
            "framework never issues an implicit resolving read on behalf of a keyed write"
        )
    return observation.observed_version


def require_observed_milestone(entity: str, observation: WriteObservation | None) -> None:
    """The transaction-scoped-observation license for a keyed temporal
    update/terminate (`python.md` §5 "Temporal `update`/`terminate` follow the
    same prior-observation rule as versioned writes").

    Raises :class:`UnobservedMilestoneError` when this unit of work never
    observed the row's milestone via a transaction-scoped find — the temporal
    sibling of :func:`require_observed`, enforced at the DEVELOPER verb
    (`parallax.snapshot.handle.Transaction`'s keyed temporal writes), never at
    the shared lowering: the neutral conformance engine legitimately lowers
    case-authored unobserved instructions (a writeSequence row's own
    ``observedTxStart`` control key, or none), and its choreography is graded
    against its own goldens.
    """
    if not isinstance(observation, TemporalObservation):
        raise UnobservedMilestoneError(
            f"{entity}: a keyed temporal update/terminate requires a milestone this "
            "unit of work already observed (a prior transaction-scoped find) — the "
            "framework never issues an implicit resolving read on behalf of a keyed write"
        )


def advance(observed: int) -> int:
    """The next version a successful write advances to: ``observed + 1``.

    Runtime-computed, always — a caller-authored version value is never
    accepted as the new version (`m-opt-lock` "Version values are
    framework-owned").
    """
    return observed + 1


def gates(concurrency: Concurrency) -> bool:
    """Whether ``concurrency`` emits an observation-bound gate predicate.

    The answer is UNIFORM across every observation-requiring write — a
    versioned keyed UPDATE, a versioned keyed DELETE, and a temporal close all
    consult this one decision (`m-opt-lock` "Concurrency mode determines the
    gate uniformly"), so a gate's presence never depends on the mutation kind.
    Optimistic mode only — the version still advances in the ``set`` of BOTH
    modes (`m-opt-lock` "The version column"); locking mode's shared read lock
    is what makes an ungated write correct.
    """
    return concurrency == "optimistic"


def check_locking_license(concurrency: Concurrency, basis: TransactionTimeBasis) -> None:
    """Raise :class:`HistoricalObservationError` when a locking-mode write's
    observation was not read latest-pinned on the written Transaction-Time axis.

    Only a Temporal Observation can answer anything but latest-pinned: a
    versioned non-temporal row is always the current one, which is why its
    observation carries no basis to check at all. A no-op in optimistic mode (the
    observed gate detects staleness instead) and for an engine-supplied temporal
    observation, which is latest-pinned by construction — the conformance
    engine's case-local temporal tracker only ever tracks the CURRENT milestone.
    A genuinely historical or edge-pinned developer read reaching a locking-mode
    write is the case this check exists to catch.
    """
    if concurrency == "locking" and isinstance(basis, HistoricalPinned):
        raise HistoricalObservationError(
            "a locking-mode write's only transaction-scoped observation is historical or "
            "edge-pinned (not latest-pinned on the written Transaction-Time dimension) — "
            "the shared read lock would protect the wrong row; re-fetch the current "
            "milestone inside the transaction, or run this write under optimistic concurrency"
        )


def reject_caller_authored_version(entity: str, version_attr: str) -> None:
    """Raise :class:`CallerAuthoredVersionError` for a keyed update row that
    itself carries an explicit value for ``version_attr`` (`m-opt-lock`
    "Version values are framework-owned"; ADR 0013).

    Checked BEFORE the observation-required path (:func:`require_observed`)
    even runs: the version is framework-owned end to end, so a row-carried
    value is never a legitimate alternative source, observed or not — it is
    refused outright, never silently preferred over (or overridden by) the
    unit of work's own recorded observation.
    """
    raise CallerAuthoredVersionError(
        f"{entity}: a keyed update's row carries an explicit value for {version_attr!r} — "
        "the optimistic-lock version is framework-owned end to end and is never caller "
        "data; the advance is always derived from this unit of work's own recorded "
        "observation (a prior transaction-scoped find), never a row-carried value "
        "(m-opt-lock)"
    )
