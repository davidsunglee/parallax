from __future__ import annotations

from typing import Final, Literal

from parallax.core.dialect import Dialect, PhysicalIndexName

__all__ = [
    "Category",
    "DatabaseError",
    "as_category",
    "classify_error",
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
    classify), the preserved native code (Postgres SQLSTATE), the driver
    message, and the Physical Index Name the violation names when there is one.
    Above-seam code reasons over :attr:`category` (or the call-site predicate
    properties) and never sees a driver exception type.
    """

    category: Category | None
    native_code: str | None
    message: str
    violated_index: PhysicalIndexName | None

    def __init__(
        self,
        *,
        category: Category | None,
        native_code: str | None,
        message: str,
        violated_index: PhysicalIndexName | None = None,
    ) -> None:
        self.category = category
        self.native_code = native_code
        self.message = message
        self.violated_index = violated_index
        code = native_code if native_code is not None else "no-sqlstate"
        label = category if category is not None else "uncategorized"
        super().__init__(f"{label} [{code}]: {message}")

    @property
    def is_retriable(self) -> bool:
        """The retry-loop predicate (`m-auto-retry`) over this error's category."""
        return is_retriable(self.category)

    @property
    def violates_unique_index(self) -> bool:
        """The insert-path predicate over this error's category."""
        return violates_unique_index(self.category)

    @property
    def is_timed_out(self) -> bool:
        """The lock-path predicate (`m-read-lock`) over this error's category."""
        return is_timed_out(self.category)


def classify_error(
    dialect: Dialect,
    native_code: str | None,
    message: str,
    *,
    constraint_name: str | None = None,
) -> DatabaseError:
    """Build the neutral :class:`DatabaseError` for a raised driver exception.

    Category interpretation is delegated to ``dialect.classify`` (the single home
    of the per-dialect ``native code -> category`` table, `m-dialect`); this module
    only assembles the neutral error. A driver exception with no native code (a
    connection failure with no SQLSTATE) yields an uncategorized error.

    ``constraint_name`` is whatever structured name the adapter read off the
    driver's own diagnostics, uninterpreted. It becomes the violated Physical
    Index Name only for a unique violation, which is the one category the name
    can be an index's: a check or foreign-key constraint reports its name the
    same way and is not an Index, so nothing else may carry it.
    """
    category = as_category(dialect.classify(native_code)) if native_code is not None else None
    violated = (
        PhysicalIndexName(constraint_name)
        if constraint_name and violates_unique_index(category)
        else None
    )
    return DatabaseError(
        category=category,
        native_code=native_code,
        message=message,
        violated_index=violated,
    )
