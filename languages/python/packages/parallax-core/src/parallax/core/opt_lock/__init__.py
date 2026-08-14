"""``parallax.core.opt_lock`` enforcement scope (m-opt-lock).

The optimistic-locking POLICY scope: this module never renders SQL (`m-sql` /
`parallax.snapshot.handle` is the one seam that does) — it owns the
version arithmetic, the observation-licensing rules, and the conflict error
vocabulary the write seam consumes. It also owns the formation half of the
same concern: the Rule Set that keeps a family's version source unambiguous, and
the Optimistic Lock Facet naming that source once per formation so no write path
rediscovers a version column. Consumers reach the facet through :func:`view`, so
generic facet retrieval stays an internal formation seam.
``m-opt-lock`` depends on ``m-unit-work``, ``m-temporal-read``, ``m-metamodel``,
``m-model-formation``, and ``m-inheritance``.
Five normative pieces (`core/spec/
m-opt-lock.md`; `python.md` §5; ADR 0013):

1. **No-op-first.** An update whose effective change set is empty is dropped
   before any observation or locking concern — no observation read, no DML,
   zero round trips. Already enforced upstream of this scope, by construction:
   ``Transaction.update`` returns before buffering, on the ``None`` the Entity
   Row Codec's ``edited_row`` answers for a net-zero edit
   (`parallax.snapshot.handle`), and the Write Planner's own no-op elimination
   stage (:class:`~parallax.core.unit_work.WritePlanner`) drops an empty keyed
   update before it is ever settled. This module has nothing to add to an
   ordering its two callers already establish structurally.
2. **Prior-observation rule** (:func:`require_observed`): the version driving a
   keyed update/delete of a versioned row must be one a read actually observed
   and the write's own source carries; unobserved raises before any DML. Which
   reads qualify is the write-evidence rule's answer, under the target Entity's
   Effective Concurrency Strategy — a read of the writing transaction under
   Locking, any authentic source's retained observation under Optimistic — and
   is settled before a write is ever buffered. Caller-authored version values are
   never accepted as gate or new version: the observed value is the only
   legitimate source, and the new version is always ``observed + 1``.
3. **Gate/advance** (:data:`INITIAL_VERSION`, :func:`advance`): every versioned
   UPDATE sets ``version = observed + 1`` under BOTH strategies; the Optimistic
   strategy additionally gates ``and <version> = ?`` binding the observed value
   LAST. INSERT derives the initial version unconditionally (never a
   row-carried value).
4. **Effective Concurrency Strategy** (:func:`effective_strategy`): the unit of
   work resolves ONE Concurrency Preference, and this module derives the
   strategy each Entity actually participates under by combining that
   preference with the Entity's own Optimistic Lock Facet. An unversioned
   Non-Temporal family supplies no gate, so it falls back to `m-read-lock`'s
   shared lock even under the `optimistic` preference; one transaction
   therefore mixes strategies across Entities without any per-object
   bookkeeping (`m-unit-work` "Strategy selection"; ADR 0059).
5. **What a keyed write settles against** (:func:`settled_evidence`): the same
   Optimistic Lock Facet answer that derives the strategy also derives what a
   write against existing state settles against and therefore claims — the exact
   observed state for a family with a version source, and the OBJECT for an
   unversioned Non-Temporal one, whose shared row lock is its evidence and is
   held on the object rather than on any state of it (`m-unit-work`
   "Observed-State Coalescing").
6. **Conflict classification policy**: this module decides only which shortfall
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

from typing import Final, assert_never

from parallax.core.metamodel import EntityIdentity, Metamodel
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
    INSERT_MUTATIONS,
    Concurrency,
    KeyedMutation,
    ObjectKey,
    RetainedObservation,
    SettledEvidence,
    TemporalObservation,
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
    "OptimisticKey",
    "OptimisticLockFacet",
    "OptimisticLockModelCompiler",
    "OptimisticLockRuleSet",
    "TransactionTimeDerived",
    "UnobservedMilestoneError",
    "UnobservedVersionError",
    "Unversioned",
    "advance",
    "compile_facet",
    "effective_strategy",
    "optimistic_key",
    "reject_caller_authored_version",
    "require_observed",
    "require_observed_milestone",
    "settled_evidence",
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


class UnobservedMilestoneError(RuntimeError):
    """A keyed temporal update/terminate reached the verb carrying no observed
    milestone.

    Temporal ``update``/``terminate`` (and their ``*Until`` window forms)
    follow the SAME prior-observation rule as versioned writes (`python.md` §5):
    the close targets — and, under optimistic mode, gates on — the milestone its
    source value observed, and in locking mode that read is the writing
    transaction's own, whose shared lock is the ungated close's only protection.
    The
    framework never issues an implicit resolving ``SELECT`` on behalf of a
    keyed write: this is a read-before-write programming error, raised before
    any DML runs, in EITHER concurrency mode. (The neutral conformance lane is
    unaffected — a case document authors its observation control keys
    explicitly, and its choreography is graded against its own goldens.)
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


def require_observed_milestone(entity: str, observation: WriteObservation | None) -> None:
    """The observed-milestone license for a keyed temporal update/terminate
    (`python.md` §5 "Temporal `update`/`terminate` follow the same
    prior-observation rule as versioned writes").

    Raises :class:`UnobservedMilestoneError` when the value the verb was handed
    carries no observed milestone — the temporal
    sibling of :func:`require_observed`, enforced at the DEVELOPER verb
    (`parallax.snapshot.handle.Transaction`'s keyed temporal writes), never at
    the shared lowering: the neutral conformance engine legitimately lowers
    case-authored unobserved instructions (a writeSequence row's own
    ``observedTxStart`` control key, or none), and its choreography is graded
    against its own goldens.
    """
    if not isinstance(observation, TemporalObservation):
        raise UnobservedMilestoneError(
            f"{entity}: a keyed temporal update/terminate requires the milestone its "
            "source value observed (a prior find) — the framework never issues an implicit "
            "resolving read on behalf of a keyed write"
        )


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
    per planned write, write-evidence rules — resolves through this one
    function rather than reading the preference directly.

    An Identity the facet does not name has no key and takes the same Locking
    fallback: an unrecognized Entity is never granted a gate it cannot supply.
    """
    if preference == "locking":
        return "locking"
    return "optimistic" if isinstance(key, ExplicitVersion | TransactionTimeDerived) else "locking"


def optimistic_key(model: Metamodel, entity: EntityIdentity) -> OptimisticKey:
    """``entity``'s Optimistic Key under ``model``, total over any Identity.

    The Optimistic Lock Facet answers every accepted Entity and nothing else, so
    a spelling this model does not carry reaches no key of its own; it reads as
    :class:`Unversioned` here, which is the answer :func:`effective_strategy`
    already gives it — an unrecognized Entity is never granted a gate it cannot
    supply, so its shared lock is all it has.

    A consumer whose domain is the three variants themselves
    (:func:`settled_evidence`) resolves the key through this rather than widening
    itself to an absence that would then need an arm.
    """
    key = view(model).key(entity)
    return UNVERSIONED if key is None else key


def settled_evidence(
    key: OptimisticKey,
    mutation: KeyedMutation,
    *,
    object_key: ObjectKey | None,
    observation: WriteObservation | RetainedObservation | None,
) -> SettledEvidence | None:
    """What a keyed write settles against, and therefore claims — the total
    derivation over the write kind (`m-unit-work` "Observed-State Coalescing").

    Three arms, each named by what the write IS:

    * an **insert** settles against nothing and claims nothing: it opens a row
      rather than writing against one, so there is no prior row to conflict over,
      and a value naming a row that IS stored has its own provenance refusal;
    * a **versioned or temporal** existing-row write settles against the exact
      observed state its source retained and claims that state, because two
      writes of one key that observed two different states are two independent
      intents;
    * an **unversioned Non-Temporal** existing-row write settles against its
      **object**, because the shared row lock its evidence rule demands (arm 4
      above) is held on the object and covers every state the row can be in. Two
      such writes can never have observed two different states, so the
      state-keyed rule's own reason does not apply and the object is the correct
      grain.

    The arms are derived from declared facts alone — this family's Optimistic Key
    and the write's own mutation — exactly as :func:`effective_strategy` derives a
    strategy from a preference and that same key. Each is named by the fact that
    selects it and none is reached by falling through the others; absence is not
    among the inputs, and every Identity has a key (:func:`optimistic_key`).
    Deriving the object arm from a missing observation instead would sweep in the
    insert, which observes no state either and has no prior row to claim at all.

    ``observation`` is what the producer resolved for the write, and reaches the
    answer only on the state-keyed arm; a state-keyed write handed none settles
    against nothing here and is refused where every buffered write is settled
    (`m-unit-work`: a required observation that is missing is a planning error).
    ``object_key`` is what the object arm claims, absent for a write that
    addresses no single object — a row naming no complete primary key, or an
    instruction naming several rows — which leaves nothing for a claim to be
    about and settles the write against nothing.
    """
    if mutation in INSERT_MUTATIONS:
        return None
    match key:
        case ExplicitVersion() | TransactionTimeDerived():
            return observation
        case Unversioned():
            return object_key
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(key)


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
