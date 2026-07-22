"""``parallax.snapshot.handle._write_types`` — the lowering vocabulary.

The two public names every other write module speaks in:
:class:`WriteLoweringError` (the loud refusal a caller wiring defect earns
rather than a wrong emission) and :class:`LoweredStatement` (one lowered DML
statement plus its optimistic-lock affected-row expectation and its
stale-vs-retriable classification hint).

Kept in its own leaf rather than inside :mod:`parallax.snapshot.handle._keyed_sql`
or :mod:`parallax.snapshot.handle._write_lowering` because both of those import
it, as does :mod:`parallax.snapshot.handle._database` (the flush executor
classifies an affected-rows mismatch off ``LoweredStatement.stale_error``);
homing it in either would force a back-edge. Both names are re-exported through
the package's frozen ``__all__``, so their spellings are public API.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.sql_gen import Statement

__all__ = ["LoweredStatement", "WriteLoweringError"]


class WriteLoweringError(ValueError):
    """A planned write cannot be lowered to DML by the write seam (a caller
    wiring defect this seam still refuses loudly rather than mis-emitting —
    e.g. a materializing predicate write that reached here un-decomposed)."""


@dataclass(frozen=True, slots=True)
class LoweredStatement:
    """One lowered DML statement plus its optimistic-lock affected-row EXPECTATION.

    ``expected_affected`` is the count the caller MUST see this ``statement`` affect
    (``None`` means no expectation — an insert, an unversioned/unobserved write, or a
    chained/opened temporal row: `m-txtime-write` "Chained INSERTs carry no
    expectation"). A non-temporal keyed write lowers to exactly ONE statement, so its
    own expectation (unchanged from increment 3, `~parallax.core.unit_work.PlannedWrite.
    expected_affected`) rides here too. A temporal write lowers to MULTIPLE statements
    (a close, then zero-to-three chained opens) — only the close carries an
    expectation (always ``1``, `m-txtime-write` "The close UPDATE MUST affect exactly
    one row" — unconditional on gating), never the whole planned write, since a
    chained INSERT's own affected-row count is meaningless as a conflict signal.

    ``stale_error`` distinguishes the TWO zero-row-close outcomes on a mismatch: a
    GATED (optimistic) mismatch is the retriable ``m-opt-lock`` conflict
    (:class:`~parallax.core.opt_lock.OptimisticLockConflictError`, unchanged from
    increment 3 — every non-temporal expectation and every gated temporal close sets
    this ``False``); an UNGATED (locking-mode) temporal close's mismatch is the
    distinct NON-retriable :class:`~parallax.core.opt_lock.StaleWriteError`
    (``stale_error=True`` — the shared read lock, not a gate, was supposed to make it
    correct, so a zero-row outcome is a consistency violation, not a detected lost
    update).
    """

    statement: Statement
    expected_affected: int | None = None
    stale_error: bool = False
