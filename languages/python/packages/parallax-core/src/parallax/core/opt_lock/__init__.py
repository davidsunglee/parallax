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
   axis; a versioned non-temporal row satisfies this trivially. Every
   engine-supplied temporal observation is latest-pinned by construction (the
   conformance engine's case-local shadow tracker only ever tracks the
   CURRENT milestone), so this stays a no-op there — but a REAL
   `Transaction.find` observation of a temporal entity threads the read's own
   processing-axis pin through :attr:`~parallax.core.unit_work.Observation.
   latest_pinned` (Phase-8 mid-phase review remediation), so a locking-mode
   write whose only transaction-scoped observation is historical or
   edge-pinned genuinely raises here today, ahead of the developer-facing
   typed temporal verbs (COR-3 Phase 8 increment 7).
5. **Conflict classification** (:class:`OptimisticLockConflictError`,
   :class:`StaleWriteError`): the two zero-row-close outcomes `m-opt-lock` /
   `m-audit-write` / `m-bitemp-write` distinguish. ``OptimisticLockConflictError``
   is the retriable-when-opted-in conflict an ``updatedRows != 1`` GATED write
   raises (a versioned keyed write in either mode, or a temporal close under
   optimistic concurrency). ``StaleWriteError`` is the distinct NON-retriable
   sibling a zero-row UNGATED temporal close raises (locking mode, where the
   shared read lock — not a gate — was supposed to make the write correct):
   the current-row predicate alone is not a gate, so an ungated mismatch is a
   consistency violation, not a detected-and-retriable conflict. Neither
   ``!= 1`` shape ever exceeds 1 (a PK-keyed or milestone-current-row
   statement structurally cannot affect more than one row) — Reladomo's
   separate corruption class for ``> 1`` is deliberately not mirrored. Not
   wired to ``m-auto-retry``'s retriability predicate yet (the opt-in joins
   the retriable set once a later increment's boundary runner exists, COR-3
   Phase 8 increment 6).

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
    "CallerAuthoredVersionError",
    "HistoricalObservationError",
    "OptimisticLockConflictError",
    "StaleWriteError",
    "UnobservedMilestoneError",
    "UnobservedVersionError",
    "advance",
    "check_locking_license",
    "classify_mismatch",
    "gates",
    "reject_caller_authored_version",
    "require_observed",
    "require_observed_milestone",
]

# The derived initial version every versioned INSERT carries, ignoring any
# row-carried value (`core/schemas/metamodel.schema.json` $comment L165;
# `m-sql.md` L871's "derived initial version" — pinned here since no COR-3
# Phase 8 increment 3 corpus witness inserts a versioned row).
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


class StaleWriteError(RuntimeError):
    """The ``updatedRows != 1`` outcome on an UNGATED (locking-mode) temporal close
    (`m-audit-write` "Affected-row conflict contract for closes"; `m-bitemp-write`).

    A zero-row temporal close is an error in ANY mode, never silent. Under optimistic
    concurrency the observed-``in_z`` gate (and, bitemporal, the business discriminator)
    makes a stale close a detectable, retriable :class:`OptimisticLockConflictError` —
    but under locking concurrency the close carries no gate at all (the shared read
    lock is supposed to make it correct), so a zero-row locking-mode close is a
    categorically DIFFERENT, NON-retriable outcome: a consistency violation the current-
    row predicate alone (``pk and out_z = infinity``) could not have prevented, not a
    lost-update conflict a retry could resolve by re-reading. Carries the SAME context
    fields as :class:`OptimisticLockConflictError` (``entity`` / ``key`` / ``expected`` /
    ``actual``) so a caller renders the SAME ``affectedRows`` observation either way;
    the sibling class is what distinguishes the two outcomes.
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
            f"{entity}: locking-mode (ungated) temporal close affected {actual} row(s), "
            f"expected {expected} (key={dict(key)!r}) — a non-retriable stale/consistency "
            "outcome, distinct from a gated optimistic-lock conflict (m-audit-write / "
            "m-bitemp-write affected-row conflict contract)"
        )


def require_observed(entity: str, observation: Observation | None) -> int:
    """The version a keyed update/delete of a versioned row advances from.

    Raises :class:`UnobservedVersionError` when ``observation`` carries no
    version — this unit of work never observed the row (`m-opt-lock` "Version
    values are framework-owned"). A row that itself carries an explicit
    version value is refused earlier, by :func:`reject_caller_authored_version`
    (`parallax.snapshot.handle._lower_update`) — this function's own row is
    always the framework-derived one, never a caller-authored version.
    """
    if observation is None or observation.version is None:
        raise UnobservedVersionError(
            f"{entity}: a keyed update/delete of a versioned row requires a version this "
            "unit of work already observed (a prior transaction-scoped find) — the "
            "framework never issues an implicit resolving read on behalf of a keyed write"
        )
    return observation.version


def require_observed_milestone(entity: str, observation: Observation | None) -> None:
    """The transaction-scoped-observation license for a keyed temporal
    update/terminate (`python.md` §5 "Temporal `update`/`terminate` follow the
    same prior-observation rule as versioned writes").

    Raises :class:`UnobservedMilestoneError` when this unit of work never
    observed the row's milestone via a transaction-scoped find — the temporal
    sibling of :func:`require_observed`, enforced at the DEVELOPER verb
    (`parallax.snapshot.handle.Transaction`'s keyed temporal writes), never at
    the shared lowering: the neutral conformance engine legitimately lowers
    case-authored unobserved instructions (a writeSequence row's own
    ``observedInZ`` control key, or none), and its choreography is graded
    against its own goldens.
    """
    if observation is None or observation.in_z is None:
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
    """Whether ``concurrency`` emits the ``and <version> = ?`` gate on a
    versioned UPDATE's ``where`` clause.

    Optimistic mode only — the version still advances in the ``set`` of BOTH
    modes (`m-opt-lock` "The version column"); locking mode's shared read lock
    is what makes an ungated write correct.
    """
    return concurrency == "optimistic"


def classify_mismatch(
    entity: str,
    key: tuple[tuple[str, object], ...],
    expected: int,
    actual: int | None,
    *,
    stale_error: bool,
) -> OptimisticLockConflictError | StaleWriteError:
    """The affected-row-mismatch error for one lowered statement whose actual
    ``execute_write`` count disagreed with its ``expected_affected`` count.

    The single classification both render-seam call sites share: the render
    seam's flush executor (``parallax.snapshot.handle._flush_executor``, every
    non-temporal expectation and every gated temporal close) and the
    conformance engine's standalone conflict-close probe
    (``parallax.conformance.engine._run_conflict_close``, the one caller
    outside production that renders a close directly, never through a
    ``FlushPlan``) — so the two error CLASSES this scope owns (the retriable
    :class:`OptimisticLockConflictError` for a GATED mismatch, the
    non-retriable :class:`StaleWriteError` for an UNGATED temporal close's
    mismatch) can never drift between the two callers. ``actual`` is ``None``
    exactly when the underlying port reported no count at all — normalized to
    ``0`` (a mismatch either way, since ``expected`` is always positive).
    """
    error_cls = StaleWriteError if stale_error else OptimisticLockConflictError
    return error_cls(entity, key, expected, actual if actual is not None else 0)


def check_locking_license(concurrency: Concurrency, *, latest_pinned: bool) -> None:
    """Raise :class:`HistoricalObservationError` when a locking-mode write's
    observation was not read latest-pinned on the written (processing) axis.

    A no-op in optimistic mode (the observed gate detects staleness instead)
    and for a trivially latest-pinned observation (``latest_pinned=True`` —
    every versioned non-temporal row, and every ENGINE-supplied temporal
    observation this increment, which is latest-pinned by construction: the
    conformance engine's case-local temporal tracker only ever tracks the
    CURRENT milestone, never a historical or edge-pinned one). A genuinely
    non-latest-pinned observation reaching a locking-mode write — a
    developer-driven historical/edge-pinned read (COR-3 Phase 8 increment 7's
    typed temporal verbs) — is the case this check exists to catch; this
    increment's own callers never construct one.
    """
    if concurrency == "locking" and not latest_pinned:
        raise HistoricalObservationError(
            "a locking-mode write's only transaction-scoped observation is historical or "
            "edge-pinned (not latest-pinned on the written processing axis) — the shared "
            "read lock would protect the wrong row; re-fetch the current milestone inside "
            "the transaction, or run this write under optimistic concurrency"
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
