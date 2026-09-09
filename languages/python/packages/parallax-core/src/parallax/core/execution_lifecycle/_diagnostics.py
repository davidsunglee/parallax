"""The database facts a failed Database Call reports, and the causal attribution
an activity failure carries.

The generic projection both build on — :class:`FailureDiagnostic`, its byte
ceilings, and the guarded extraction under it — lives in
:mod:`parallax.core.diagnostics`, because a resource cleanup issue and a pool
sample need exactly that projection and none of the lifecycle's own vocabulary.
What stays here is what only a database execution can state: the neutral
`m-db-error` category and native code copied off an already-classified error,
and how an activity's single failure is attributed.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.db_error import Category, DatabaseError, as_category
from parallax.core.diagnostics import FailureDiagnostic, diagnostic_for, exact_str, guarded


@dataclass(frozen=True, slots=True)
class DatabaseFailureDiagnostic:
    """A failed Database Call's diagnostic: the ordinary projection plus the two
    neutral database facts.

    ``category`` and ``native_code`` are copied straight off the `m-db-error`
    Database Error and are never reclassified here. An unexpected non-Database
    error escaping the port carries ``None`` for both, which is the honest
    report: no classification was ever made.
    """

    failure: FailureDiagnostic
    category: Category | None
    native_code: str | None


@dataclass(frozen=True, slots=True)
class DirectFailure:
    """The failure this activity has no child to name for.

    Either no report ever paired this exception value with a direct child of it
    — neither a child finishing failed with the value nor an explicit
    enforcement relation naming an already-finished one — or a report did and a
    different value has since taken the activity's one attribution: a value a
    scope does not hold when it fails is the scope's own.
    """

    diagnostic: FailureDiagnostic


@dataclass(frozen=True, slots=True)
class CausedFailure:
    """The failure is attributed to an already-finished DIRECT child: the one
    this activity holds its single attribution for.

    Attribution follows exception identity or an explicit enforcement relation,
    never temporal proximity, so a completed zero-row write call can be named by
    a Write Batch failure while a conversion error that merely unwound past a
    successful call names nothing. Every level names its own child, so a deeper
    cause is reached by walking the chain rather than read off one event.
    """

    diagnostic: FailureDiagnostic
    cause_activity_id: int


type ActivityFailure = DirectFailure | CausedFailure
"""How an activity's failure is attributed, a closed union of exactly one member."""


def _category(exc: DatabaseError) -> Category | None:
    """``exc``'s already-classified category, narrowed to the closed set.

    Narrowed rather than trusted: :class:`~parallax.core.db_error.DatabaseError`
    declares the attribute, but a subclass may shadow it with anything, and a
    diagnostic states a category only where the closed set has one to state.
    Made exact BEFORE narrowing, because membership is decided by equality: a
    ``str`` subclass spelling a category compares equal to it and would
    otherwise be kept by identity, holding whatever its instance references.
    """
    category = exc.category
    return as_category(exact_str(category)) if isinstance(category, str) else None


def _native_code(exc: DatabaseError) -> str | None:
    """``exc``'s preserved native code, admitted only as a detached string."""
    native_code = exc.native_code
    return exact_str(native_code) if isinstance(native_code, str) else None


def database_diagnostic_for(exc: BaseException) -> DatabaseFailureDiagnostic:
    """``exc`` as a failed Database Call's diagnostic.

    A Database Error contributes its already-classified category and native
    code; anything else escaping the port contributes neither, because no
    classification of it exists to copy. Both database fields are read behind
    their own guards for the same reason every ordinary field is: the port
    raises whatever it raises, and a subclass that shadows either attribute must
    cost that field alone rather than the caller's failure.
    """
    database = guarded(lambda: exc if isinstance(exc, DatabaseError) else None, None)
    return DatabaseFailureDiagnostic(
        failure=diagnostic_for(exc),
        category=None if database is None else guarded(lambda: _category(database), None),
        native_code=None if database is None else guarded(lambda: _native_code(database), None),
    )
