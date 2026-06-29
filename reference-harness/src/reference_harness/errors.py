"""The M11 error-code classification core (dialect-agnostic, DB-free).

Reladomo's `DatabaseType` exposes error classification not as one string map but
as a set of neutral predicates interrogated at distinct call sites: the txn retry
loop asks `isRetriable` (deadlock / serialization failure), the insert/merge path
asks `violatesUniqueIndex`, the lock path asks `isTimedOut`. This module is the
language-neutral equivalent: a closed category vocabulary, the per-dialect native
code -> category map, and the call-site predicates defined as category membership
(so a predicate can never drift from its category).

The native code lives in a DIFFERENT attribute per dialect, and the same value
can mean different things: Postgres keys on the SQLSTATE string (`23505`,
`40P01`), MariaDB on the vendor errno (`1062`, `1213`). SQLSTATE `40001` is a
serialization failure on Postgres but the deadlock state on MariaDB -- which is
exactly why the code source is a dialect decision, not a shared lookup.
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

# Postgres keys on the SQLSTATE string.
_POSTGRES_CODES: dict[str, str] = {
    "23505": UNIQUE_VIOLATION,
    "40P01": DEADLOCK,
    "40001": DEADLOCK,  # serialization_failure -- retriable, folded into deadlock
    "55P03": LOCK_WAIT_TIMEOUT,  # lock_not_available (SET lock_timeout exceeded)
}

# MariaDB keys on the vendor errno (an int).
_MARIADB_CODES: dict[int, str] = {
    1062: UNIQUE_VIOLATION,  # ER_DUP_ENTRY
    1213: DEADLOCK,  # ER_LOCK_DEADLOCK
    1205: LOCK_WAIT_TIMEOUT,  # ER_LOCK_WAIT_TIMEOUT
}


def classify(dialect: str, code: str | int | None) -> str:
    """Map a native DB error code to a neutral M11 category.

    *code* is the SQLSTATE string for ``postgres`` and the vendor errno (int) for
    ``mariadb`` -- the value each driver surfaces (see the providers). Returns
    :data:`UNKNOWN` for an unrecognized or missing code, so an unclassified error
    fails an assertion loudly rather than passing silently.
    """
    if code is None:
        return UNKNOWN
    if dialect == "postgres":
        return _POSTGRES_CODES.get(str(code), UNKNOWN)
    if dialect == "mariadb":
        try:
            errno = int(code)
        except (TypeError, ValueError):
            return UNKNOWN
        return _MARIADB_CODES.get(errno, UNKNOWN)
    return UNKNOWN


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
