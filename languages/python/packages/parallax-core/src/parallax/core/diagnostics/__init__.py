"""``parallax.core.diagnostics`` enforcement scope — detached exception projection.

The one import home for turning an arbitrary exception into a bounded, deeply
immutable value something else may retain: a lifecycle event a Handler receives,
a resource cleanup issue a caller reads back, a pool sample that could not be
taken. Every consumer of that projection names this module; there is no second
copy and no compatibility re-export from the scope this was extracted out of.

Every field is read AND rendered behind its own guard, so a hostile ``code``
property costs that one field rather than collapsing the whole diagnostic, and
observing a failure can never replace the failure the caller needs to see.
Rendering is eager because detachment demands it: the diagnostic retains no
exception, traceback, cause graph, or frame, so there is nothing left to format
later — and every projected string is an exact ``str`` copy, because a ``str``
subclass is a reference back into the failure wearing a string's shape.

The scope depends on the standard library alone. That is what lets the database
port, the execution lifecycle, and the resource contracts between them share one
projection without any of them inheriting the others' edges.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

__all__ = [
    "MESSAGE_LIMIT_BYTES",
    "STACK_LIMIT_BYTES",
    "UNAVAILABLE",
    "FailureDiagnostic",
    "bounded",
    "diagnostic_for",
    "exact_str",
    "guarded",
    "qualified_type",
]

MESSAGE_LIMIT_BYTES: Final = 8 * 1024
"""The best-effort message's UTF-8 byte ceiling."""

STACK_LIMIT_BYTES: Final = 64 * 1024
"""The rendered chained stack's UTF-8 byte ceiling."""

UNAVAILABLE: Final = "<unavailable>"
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

    ``qualified_type`` and ``code`` carry no byte ceiling of their own: a type
    name and an opaque published code are identifiers rather than free text, and
    truncating either would silently corrupt the thing it identifies. So this is
    a bound on the two rendered fields and on the retained graph, and not a fixed
    total byte bound for the value.

    Nothing here references the exception, its traceback, its cause graph, a
    frame, a local, transaction state, a statement, or a bind, so a failure with
    this projection already at hand reports this same object rather than copying
    its bounded strings.
    """

    qualified_type: str
    message: str
    code: str | None
    stack: str
    message_truncated: bool
    stack_truncated: bool


def guarded[T](read: Callable[[], T], fallback: T) -> T:
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


def exact_str(text: str) -> str:
    """``text`` as an exact ``str``, round-tripped through UTF-8.

    A projected field is read off arbitrary caller code, and a ``str`` SUBCLASS
    is not a value a detached, deeply immutable diagnostic may keep: an instance
    can hold attributes — the failing exception and its frames among them — and
    can override every method a consumer calls, including the encoding this
    module bounds it with. The round trip is taken through ``str``'s own
    unbound method for that second reason: a subclass cannot substitute it.
    """
    if type(text) is str:
        return text
    return str.encode(text, "utf-8", "surrogatepass").decode("utf-8", "surrogatepass")


def bounded(text: str, limit: int) -> tuple[str, bool]:
    """``text`` within ``limit`` UTF-8 bytes, and whether it had to be cut.

    Total for every ``str``, including a subclass whose ``encode`` is hostile:
    the encoding is ``str``'s own unbound method, and what comes back is always
    an exact ``str`` decoded from exact bytes. The bound is a byte count, so
    truncation slices encoded bytes; decoding the slice with ``ignore`` discards
    a code point the cut split rather than reporting a replacement character the
    original never contained. Encoding with ``replace`` is what lets a message
    carrying lone surrogates — a ``str`` Python admits and UTF-8 does not — be
    projected at all, at every length rather than only past the bound.
    """
    raw = str.encode(text, "utf-8", "replace")
    if len(raw) <= limit:
        return raw.decode("utf-8"), False
    return raw[:limit].decode("utf-8", errors="ignore"), True


def _formatted_type(value: object) -> str:
    runtime_type = type(value)
    return f"{runtime_type.__module__}.{runtime_type.__qualname__}"


def qualified_type(value: object, /) -> str:
    """``module.qualname`` of ``value``'s runtime type, or ``"<unavailable>"``.

    Guarded: a metaclass may make either name raise or answer something no
    format string accepts, and naming a type may never replace the failure being
    reported.
    """
    return guarded(lambda: exact_str(_formatted_type(value)), UNAVAILABLE)


def _code(exc: BaseException) -> str | None:
    """``exc``'s own stable ``code``, or absence when it publishes none.

    Only a string is admitted: the attribute is read off arbitrary caller code,
    so a ``code`` of some other shape is no more usable than a missing one.
    """
    code = getattr(exc, "code", None)
    return exact_str(code) if isinstance(code, str) else None


def _stack(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


def _projected(read: Callable[[], str], limit: int) -> tuple[str, bool]:
    """One field read, bounded, and detached, entirely inside one guard.

    Bounding is inside the guard rather than after it because the value read is
    arbitrary: ``__str__`` may legally answer a ``str`` subclass, and a guard
    around the read alone would leave the rendering that follows it able to
    replace the failure it describes.
    """
    return guarded(lambda: bounded(read(), limit), (UNAVAILABLE, False))


def diagnostic_for(exc: BaseException) -> FailureDiagnostic:
    """``exc`` as a detached diagnostic, without ever raising.

    Each field is read behind its own guard, so a type whose ``__str__`` raises
    still yields a full stack, and one whose ``code`` property raises still
    yields a full message.
    """
    message, message_truncated = _projected(lambda: str(exc), MESSAGE_LIMIT_BYTES)
    stack, stack_truncated = _projected(lambda: _stack(exc), STACK_LIMIT_BYTES)
    return FailureDiagnostic(
        qualified_type=qualified_type(exc),
        message=message,
        code=guarded(lambda: _code(exc), None),
        stack=stack,
        message_truncated=message_truncated,
        stack_truncated=stack_truncated,
    )
