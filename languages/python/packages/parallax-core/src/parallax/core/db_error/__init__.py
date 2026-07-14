"""``parallax.core.db_error`` enforcement scope (m-db-error).

Maps a raised database error to a neutral **category** so language-neutral code
can react without dialect knowledge. This is the **only** place native error codes
are interpreted — the pure dialect strategy (`m-dialect`) owns the per-dialect
`native code -> category` table (`Dialect.classify`), and this module consumes it;
everything above the seam reasons in categories, never in SQLSTATE.

The category set is closed: :data:`CATEGORIES`. Classification is interrogated at
**distinct call sites**, so the seam exposes it as **predicates defined as category
membership** — not one stringly-typed method:

- the transaction retry loop (`m-auto-retry`) asks :func:`is_retriable`
  (``category == "deadlock"`` — a true deadlock **or** a serialization failure,
  both retriable);
- the insert / detached merge-back path asks :func:`violates_unique_index`
  (``category == "uniqueViolation"``);
- the lock path (`m-read-lock`) asks :func:`is_timed_out`
  (``category == "lockWaitTimeout"``).

:class:`DatabaseError` is the Parallax error a driver exception is re-raised as at
the `m-db-port` boundary — it carries the neutral category, the preserved native
code (SQLSTATE), and the driver message, so no driver exception type crosses above
the port. ``m-db-error`` depends on ``m-db-port`` and ``m-dialect`` only.
"""

from __future__ import annotations

from typing import Final, Literal

from parallax.core.dialect import Dialect

__all__ = [
    "CATEGORIES",
    "CONNECTION_DEAD",
    "DEADLOCK",
    "LOCK_WAIT_TIMEOUT",
    "UNIQUE_VIOLATION",
    "Category",
    "DatabaseError",
    "as_category",
    "classify_error",
    "is_retriable",
    "is_timed_out",
    "violates_unique_index",
]

# The closed neutral category set. `connectionDead` is reserved: it is a member of
# the closed set but no dialect code maps to it yet (a driver connection failure
# carries no SQLSTATE), so today it is never produced — only its slot is held.
Category = Literal["uniqueViolation", "deadlock", "lockWaitTimeout", "connectionDead"]

UNIQUE_VIOLATION: Final[Category] = "uniqueViolation"
DEADLOCK: Final[Category] = "deadlock"
LOCK_WAIT_TIMEOUT: Final[Category] = "lockWaitTimeout"
CONNECTION_DEAD: Final[Category] = "connectionDead"

CATEGORIES: Final[frozenset[Category]] = frozenset(
    {UNIQUE_VIOLATION, DEADLOCK, LOCK_WAIT_TIMEOUT, CONNECTION_DEAD}
)


def is_retriable(category: Category | None) -> bool:
    """Whether ``category`` names a transient, retriable failure (a deadlock).

    Postgres `40P01` (true deadlock) and `40001` (serialization failure) both map
    to the single ``deadlock`` category, so both are retriable — matching Reladomo,
    which retries the same transient-conflict class.
    """
    return category == DEADLOCK


def violates_unique_index(category: Category | None) -> bool:
    """Whether ``category`` names a duplicate-key / unique-index violation."""
    return category == UNIQUE_VIOLATION


def is_timed_out(category: Category | None) -> bool:
    """Whether ``category`` names a blocked-past-the-lock-wait-budget timeout."""
    return category == LOCK_WAIT_TIMEOUT


def as_category(value: str | None) -> Category | None:
    """Narrow a raw category string to a :data:`Category`, or ``None``.

    The dialect's ``classify`` returns a plain ``str | None`` — a member of the
    closed set or ``None`` for an unrecognized code. Anything not in
    :data:`CATEGORIES` (including ``None``) collapses to ``None`` (uncategorized).
    """
    if value in CATEGORIES:
        return value
    return None


class DatabaseError(Exception):
    """A neutral Parallax database error raised at the `m-db-port` boundary.

    Carries the neutral :data:`Category` (``None`` when the native code did not
    classify), the preserved native code (Postgres SQLSTATE), and the driver
    message. Above-seam code reasons over :attr:`category` (or the call-site
    predicate properties) and never sees a driver exception type.
    """

    category: Category | None
    native_code: str | None
    message: str

    def __init__(self, *, category: Category | None, native_code: str | None, message: str) -> None:
        self.category = category
        self.native_code = native_code
        self.message = message
        code = native_code if native_code is not None else "no-sqlstate"
        label = category if category is not None else "uncategorized"
        super().__init__(f"{label} [{code}]: {message}")

    @property
    def is_retriable(self) -> bool:
        """The retry-loop predicate (`m-auto-retry`) over this error's category."""
        return is_retriable(self.category)

    @property
    def violates_unique_index(self) -> bool:
        """The insert / merge-back predicate over this error's category."""
        return violates_unique_index(self.category)

    @property
    def is_timed_out(self) -> bool:
        """The lock-path predicate (`m-read-lock`) over this error's category."""
        return is_timed_out(self.category)


def classify_error(dialect: Dialect, native_code: str | None, message: str) -> DatabaseError:
    """Build the neutral :class:`DatabaseError` for a raised driver exception.

    Category interpretation is delegated to ``dialect.classify`` (the single home
    of the per-dialect ``native code -> category`` table, `m-dialect`); this module
    only assembles the neutral error. A driver exception with no native code (a
    connection failure with no SQLSTATE) yields an uncategorized error.
    """
    category = as_category(dialect.classify(native_code)) if native_code is not None else None
    return DatabaseError(category=category, native_code=native_code, message=message)
