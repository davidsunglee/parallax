"""The m-db-error neutral category vocabulary (dialect-agnostic, DB-free).

Reladomo's `DatabaseType` exposes error classification not as one string map but
as a set of neutral predicates interrogated at distinct call sites: the txn retry
loop asks `isRetriable` (deadlock / serialization failure), the insert/merge path
asks `violatesUniqueIndex`, the lock path asks `isTimedOut`. This module is the
language-neutral equivalent of that half: a closed category vocabulary and the
call-site predicates defined as category membership (so a predicate can never
drift from its category).

The native code a category is reached FROM is a per-dialect fact, so it lives on
the provider that owns the engine rather than here: the code arrives in a
different attribute per driver, and the same value can mean different things.
Postgres keys on the SQLSTATE string (`23505`, `40P01`), MariaDB on the vendor
errno (`1062`, `1213`); SQLSTATE `40001` is a serialization failure on Postgres
but the deadlock state on MariaDB -- which is exactly why no shared lookup can
classify for both.
"""

from __future__ import annotations

UNIQUE_VIOLATION = "uniqueViolation"
DEADLOCK = "deadlock"  # covers true deadlock AND serialization failure (retriable)
LOCK_WAIT_TIMEOUT = "lockWaitTimeout"
CONNECTION_DEAD = "connectionDead"  # reserved for language impls; not exercised
UNKNOWN = "unknown"

CATEGORIES: frozenset[str] = frozenset(
    {UNIQUE_VIOLATION, DEADLOCK, LOCK_WAIT_TIMEOUT, CONNECTION_DEAD, UNKNOWN}
)


def is_retriable(category: str) -> bool:
    """The transaction retry loop's question: deadlock or serialization failure."""
    return category == DEADLOCK


def violates_unique_index(category: str) -> bool:
    """The insert / detached merge-back path's question."""
    return category == UNIQUE_VIOLATION


def is_timed_out(category: str) -> bool:
    """The lock path's question: blocked past the lock-wait budget."""
    return category == LOCK_WAIT_TIMEOUT


_PREDICATE_BY_CATEGORY: dict[str, str] = {
    DEADLOCK: "is_retriable",
    UNIQUE_VIOLATION: "violates_unique_index",
    LOCK_WAIT_TIMEOUT: "is_timed_out",
}


def predicate_for(category: str) -> str | None:
    """Name of the single call-site predicate true for *category* (else None)."""
    return _PREDICATE_BY_CATEGORY.get(category)
