"""``parallax.core.opt_lock`` enforcement scope (m-opt-lock).

The optimistic-locking POLICY scope: this module never renders SQL (`m-sql` /
`parallax.snapshot.handle.lower_write` is the one seam that does) — it owns the
version arithmetic, the observation-licensing rules, and the conflict/historical
error vocabulary the write seam consumes. Five normative pieces (`core/spec/
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
   locking-mode write only when its read was latest-pinned on the processing
   axis; a versioned non-temporal row satisfies this trivially. Landed here
   now, unit-test-pinned; its real (non-trivial) consumers arrive with the
   temporal write path (COR-3 Phase 8 increment 4) — this increment's own
   callers only ever pass the trivial ``latest_pinned=True``.
5. **Conflict classification** (:class:`OptimisticLockConflictError`): the
   retriable-when-opted-in conflict an ``updatedRows != 1`` gated write raises.
   ``!= 1`` is the ONE conflict outcome (a PK-keyed statement structurally
   cannot affect more than one row) — Reladomo's separate corruption class for
   ``> 1`` is deliberately not mirrored. Not wired to ``m-auto-retry``'s
   retriability predicate yet (the opt-in joins the retriable set once a later
   increment's boundary runner exists, COR-3 Phase 8 increment 6).

Prior art (Reladomo; semantics, not idioms): the gate plus the
``updatedRows != 1`` conflict mirrors ``MithraAbstractDatabaseObject.
checkUpdatedRows`` under ``ReadCacheWithOptimisticLockingTxParticipationMode``;
retriability-only-on-opt-in mirrors ``MithraTransaction.
setRetryOnOptimisticLockFailure`` (default off).
"""

from __future__ import annotations

from typing import Final

from parallax.core.unit_work import Concurrency, Observation

__all__ = [
    "INITIAL_VERSION",
    "HistoricalObservationError",
    "OptimisticLockConflictError",
    "UnobservedVersionError",
    "advance",
    "check_locking_license",
    "gates",
    "require_observed",
]

# The derived initial version every versioned INSERT carries, ignoring any
# row-carried value (`core/schemas/metamodel.schema.json` $comment L165;
# `m-sql.md` L871's "derived initial version" — pinned here since no COR-3
# Phase 8 increment 3 corpus witness inserts a versioned row).
INITIAL_VERSION: Final[int] = 1


class UnobservedVersionError(RuntimeError):
    """A keyed update/delete of a versioned row this unit of work never observed.

    The new version is always computed from the observed one (``observed + 1``),
    so with no observed version there is nothing to advance from — and, in
    optimistic mode, nothing to gate on. The framework never issues an implicit
    resolving ``SELECT`` on behalf of a keyed write (`m-opt-lock` "Version values
    are framework-owned"; ADR 0013): this is a read-before-write programming
    error, raised before any DML runs, in EITHER concurrency mode.
    """


class HistoricalObservationError(RuntimeError):
    """A locking-mode write's only transaction-scoped observation is historical
    or edge-pinned (not latest-pinned on the written processing axis).

    Locking-mode closes are ungated, so the shared read lock is the only
    protection; a shared lock on a historical or edge-pinned milestone locks
    the wrong row — a concurrent chain replaces the current row without
    touching the locked one, and the ungated close would then silently re-close
    the replacement (a lost update). The same observation is legal in
    optimistic mode, where the observed gate detects the staleness instead
    (`python.md` §5 L596-611).
    """


class OptimisticLockConflictError(RuntimeError):
    """The ``updatedRows != 1`` conflict on a versioned keyed write (`m-opt-lock`).

    The retriable-when-opted-in signal: a concurrent write changed the version
    (or, for a keyed DELETE, the row) first, so the gated/version-bound
    statement matched zero rows instead of the expected one. Carries the
    context an engine or caller needs to render an ``affectedRows`` observation:
    ``entity`` (the write's target entity name), ``key`` (its object key, the
    same ``(pk attribute name, value)`` pairs `~parallax.core.unit_work.
    ObjectKey` carries), ``expected`` (always ``1`` this increment), and
    ``actual`` (the port's own reported affected-row count).
    """

    def __init__(
        self,
        entity: str,
        key: tuple[tuple[str, object], ...],
        expected: int,
        actual: int,
    ) -> None:
        self.entity = entity
        self.key = key
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"{entity}: versioned write affected {actual} row(s), expected {expected} "
            f"(key={dict(key)!r}) — a concurrent write changed the version first "
            "(m-opt-lock optimistic-lock conflict)"
        )


def require_observed(entity: str, observation: Observation | None) -> int:
    """The version a keyed update/delete of a versioned row advances from.

    Raises :class:`UnobservedVersionError` when ``observation`` carries no
    version — this unit of work never observed the row (`m-opt-lock` "Version
    values are framework-owned"). Never called for a row that carries its
    version as plain caller-authored data (the M4-era passthrough shape
    ``parallax.snapshot.handle`` still recognizes byte-for-byte); only the
    framework-derived path — the one with no row-carried version — reaches
    here at all.
    """
    if observation is None or observation.version is None:
        raise UnobservedVersionError(
            f"{entity}: a keyed update/delete of a versioned row requires a version this "
            "unit of work already observed (a prior transaction-scoped find) — the "
            "framework never issues an implicit resolving read on behalf of a keyed write"
        )
    return observation.version


def advance(observed: int) -> int:
    """The next version a successful write advances to: ``observed + 1``.

    Runtime-computed, always — a caller-authored version value is never
    accepted as the new version (`m-opt-lock` "Version values are
    framework-owned").
    """
    return observed + 1


def gates(concurrency: Concurrency) -> bool:
    """Whether ``concurrency`` emits the ``and <version> = ?`` gate on a
    versioned UPDATE's ``where`` clause.

    Optimistic mode only — the version still advances in the ``set`` of BOTH
    modes (`m-opt-lock` "The version column"); locking mode's shared read lock
    is what makes an ungated write correct.
    """
    return concurrency == "optimistic"


def check_locking_license(concurrency: Concurrency, *, latest_pinned: bool) -> None:
    """Raise :class:`HistoricalObservationError` when a locking-mode write's
    observation was not read latest-pinned on the written (processing) axis.

    A no-op in optimistic mode (the observed gate detects staleness instead)
    and for a trivially latest-pinned observation (``latest_pinned=True`` —
    every versioned non-temporal row, this increment's only caller). The
    temporal case that can genuinely fail this check — a locking-mode write
    whose sole transaction-scoped observation is historical or edge-pinned —
    arrives with the temporal write path (COR-3 Phase 8 increment 4), which
    threads a real ``latest_pinned`` computed from the observed milestone.
    """
    if concurrency == "locking" and not latest_pinned:
        raise HistoricalObservationError(
            "a locking-mode write's only transaction-scoped observation is historical or "
            "edge-pinned (not latest-pinned on the written processing axis) — the shared "
            "read lock would protect the wrong row; re-fetch the current milestone inside "
            "the transaction, or run this write under optimistic concurrency"
        )
