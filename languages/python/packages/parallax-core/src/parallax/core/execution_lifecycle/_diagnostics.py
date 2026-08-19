"""Detached, bounded projections of an exception, and the causal attribution
an activity failure carries.

Every field is read behind its own guard, so a hostile ``code`` property costs
that one field rather than collapsing the whole diagnostic, and observing a
failure can never replace the failure the caller needs to see. Rendering is
eager because detachment demands it: the diagnostic retains no exception,
traceback, cause graph, or frame, so there is nothing left to format later.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from parallax.core.db_error import Category, DatabaseError

MESSAGE_LIMIT_BYTES: Final = 8 * 1024
"""The best-effort message's UTF-8 byte ceiling."""

STACK_LIMIT_BYTES: Final = 64 * 1024
"""The rendered chained stack's UTF-8 byte ceiling."""

_UNAVAILABLE: Final = "<unavailable>"
"""What a field a guarded read could not produce reports instead."""


@dataclass(frozen=True, slots=True)
class FailureDiagnostic:
    """A total, detached, deeply immutable projection of one exception.

    ``qualified_type`` is ``module.qualname``, spelled the same way for every
    exception including the builtins, so a reader never has to know which rule
    produced it. ``message`` and ``stack`` are bounded to
    :data:`MESSAGE_LIMIT_BYTES` and :data:`STACK_LIMIT_BYTES` of UTF-8 with
    their own truncation flags, and the stack renders the declared cause chain
    without locals. ``code`` is the stable string an exception publishes as its
    own ``code`` attribute, absent for one that publishes none.

    Nothing here references the exception, its traceback, its cause graph, a
    frame, a local, transaction state, a statement, or a bind: an enclosing
    failure reuses this same object rather than copying its bounded strings.
    """

    qualified_type: str
    message: str
    code: str | None
    stack: str
    message_truncated: bool
    stack_truncated: bool


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
    """The activity itself produced the failure."""

    diagnostic: FailureDiagnostic


@dataclass(frozen=True, slots=True)
class CausedFailure:
    """The failure is attributed to an already-finished descendant activity.

    Attribution follows exception identity or an explicit enforcement relation,
    never temporal proximity, so a completed zero-row write call can be named by
    a Write Batch failure while a conversion error that merely unwound past a
    successful call names nothing.
    """

    diagnostic: FailureDiagnostic
    cause_activity_id: int


type ActivityFailure = DirectFailure | CausedFailure
"""How an activity's failure is attributed, a closed union of exactly one member."""


def _guarded[T](read: Callable[[], T], fallback: T) -> T:
    """One guarded diagnostic extraction.

    Deliberately swallows ``BaseException``: observing a failure must never
    replace the failure the caller needs to see, and the exception being
    projected is arbitrary caller code whose ``__str__`` or ``code`` may raise
    anything at all. This exists for diagnostic extraction alone — swallowing
    control-flow exceptions anywhere else is a defect.
    """
    try:
        return read()
    except BaseException:
        return fallback


def _bounded(text: str, limit: int) -> tuple[str, bool]:
    """``text`` within ``limit`` UTF-8 bytes, and whether it had to be cut.

    The bound is a byte count, so truncation slices encoded bytes; decoding the
    slice with ``ignore`` discards a code point the cut split rather than
    reporting a replacement character the original never contained. Encoding
    with ``replace`` is what lets a message carrying lone surrogates — a
    ``str`` Python admits and UTF-8 does not — be projected at all.
    """
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode("utf-8", errors="ignore"), True


def _qualified_type(exc: BaseException) -> str:
    runtime_type = type(exc)
    return f"{runtime_type.__module__}.{runtime_type.__qualname__}"


def _code(exc: BaseException) -> str | None:
    """``exc``'s own stable ``code``, or absence when it publishes none.

    Only a string is admitted: the attribute is read off arbitrary caller code,
    so a ``code`` of some other shape is no more usable than a missing one.
    """
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) else None


def _stack(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


def diagnostic_for(exc: BaseException) -> FailureDiagnostic:
    """``exc`` as a detached diagnostic, without ever raising.

    Each field is read behind its own guard, so a type whose ``__str__`` raises
    still yields a full stack, and one whose ``code`` property raises still
    yields a full message.
    """
    message, message_truncated = _bounded(
        _guarded(lambda: str(exc), _UNAVAILABLE), MESSAGE_LIMIT_BYTES
    )
    stack, stack_truncated = _bounded(
        _guarded(lambda: _stack(exc), _UNAVAILABLE), STACK_LIMIT_BYTES
    )
    return FailureDiagnostic(
        qualified_type=_guarded(lambda: _qualified_type(exc), _UNAVAILABLE),
        message=message,
        code=_guarded(lambda: _code(exc), None),
        stack=stack,
        message_truncated=message_truncated,
        stack_truncated=stack_truncated,
    )


def database_diagnostic_for(exc: BaseException) -> DatabaseFailureDiagnostic:
    """``exc`` as a failed Database Call's diagnostic.

    A Database Error contributes its already-classified category and native
    code; anything else escaping the port contributes neither, because no
    classification of it exists to copy.
    """
    database = exc if isinstance(exc, DatabaseError) else None
    return DatabaseFailureDiagnostic(
        failure=diagnostic_for(exc),
        category=None if database is None else database.category,
        native_code=None if database is None else database.native_code,
    )
