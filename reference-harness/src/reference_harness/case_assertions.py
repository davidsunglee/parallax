"""The assertion vocabulary the compatibility runner and the read oracle share.

A name is offered here only if it has at least one live caller in the runner AND
at least one in the read oracle; what those names are implemented in terms of
travels with them, unless both sides call that primitive directly too — then it
is a module of its own (:mod:`.multiset`) rather than a second offering here. A
name only one side calls belongs to that side instead, so this module never
becomes the place a helper lands when its home is unclear. It imports neither of
them, so neither can reach the other through it.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any

from . import portable_literal
from .case import Case
from .multiset import multiset_matches


class CaseFailure(AssertionError):
    """A compatibility-case assertion failed."""


def _to_decimal(value: Any) -> Any:
    """Normalize a numeric to an EXACT ``Decimal``; pass non-numerics through.

    Integers and ``Decimal``\\ s convert losslessly. A ``float`` is converted via
    its shortest round-tripping repr (``Decimal(str(x))``) so a YAML-authored
    ``0.1`` becomes ``Decimal('0.1')`` — matching the DB's exact ``numeric`` —
    rather than ``Decimal(0.1)``, which would inject the binary-float expansion.
    ``bool`` is deliberately NOT treated as numeric, so ``True`` never equals 1.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    return value


# The host carrier each string-carried Neutral Type decodes to, and the decoder
# that reads its portable literal.
_LITERAL_CARRIERS: tuple[tuple[type, Callable[[str], Any]], ...] = (
    (datetime.datetime, portable_literal.decode_timestamp),
    (datetime.date, portable_literal.decode_date),
    (datetime.time, portable_literal.decode_time),
    (uuid.UUID, portable_literal.decode_uuid),
    (bytes, portable_literal.decode_octets),
)


def _decoded_against(value: Any, other: Any) -> Any:
    """*value* decoded as a portable literal of *other*'s space, else unchanged.

    ``datetime`` is asked before ``date`` because it is a ``date`` subclass, so an
    instant would otherwise be compared against a calendar-date literal.
    """
    if not isinstance(value, str):
        return value
    for carrier, decode in _LITERAL_CARRIERS:
        if isinstance(other, carrier):
            return decode(value) if decode(value) is not None else value
    return value


def scalars_equal(left: Any, right: Any, tolerance: Decimal | None) -> bool:
    """Compare two scalars exactly in Decimal space, or within ``tolerance``.

    Numerics compare as exact Decimals (no ``float`` anywhere) so a ``decimal``
    money column matches to the cent and a value's type never depends on whether
    it is whole. When the case declares a ``tolerance`` — for inherently inexact
    results (stddev / variance / repeating-decimal avg) that cannot be authored
    exactly and differ in scale across dialects — numeric comparison becomes
    ``abs(left - right) <= tolerance``. Non-numerics (str / bool / None) use ``==``.

    A case authors a `date` / `time` / `timestamp` / `uuid` / `bytes` value as its
    PORTABLE LITERAL — the corpus YAML schema resolves four implicit types and no
    more (:mod:`corpus_yaml`), so such a value reaches here as the text its author
    wrote, while the row read back carries the decoded host value. The literal is
    decoded before comparison, so the two name the same value or they do not.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        # bool is not numeric: a boolean equals only a boolean of the same value
        # (so True != 1 and False != 0), never a number that happens to be 0/1.
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    left, right = _decoded_against(left, right), _decoded_against(right, left)
    da, db = _to_decimal(left), _to_decimal(right)
    if isinstance(da, Decimal) and isinstance(db, Decimal):
        if tolerance is not None:
            return abs(da - db) <= tolerance
        return da == db
    return left == right


def _row_matches(left: dict[str, Any], right: dict[str, Any], tolerance: Decimal | None) -> bool:
    if left.keys() != right.keys():
        return False
    return all(scalars_equal(left[key], right[key], tolerance) for key in left)


def rows_equal(
    left: Sequence[dict[str, Any]],
    right: Sequence[dict[str, Any]],
    tolerance: Decimal | None = None,
    *,
    ordered: bool = False,
) -> bool:
    """Order-insensitive multiset comparison of result rows.

    ``ordered`` compares positionally instead, for the one row sequence whose order
    a case fixes: a streamed step's published roots, which arrive in the delivery's
    Continuation Order across every page (m-case-format "Streamed read steps").
    """
    if len(left) != len(right):
        return False
    if ordered:
        return all(
            _row_matches(row, candidate, tolerance)
            for row, candidate in zip(left, right, strict=True)
        )
    return multiset_matches(
        left, right, lambda row, candidate: _row_matches(row, candidate, tolerance)
    )


def coerce_identity_key(value: Any) -> Any:
    """Coerce a DB / expected scalar to an exact hashable identity-key form.

    Identity lives in a separate key space from value comparison: a bucket key, a
    hop dedup key, and a primary-key identity must be exactly equal and hashable,
    while a projected value must keep the type it was read at so
    :func:`scalars_equal` can compare it exactly.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else value
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def assert_step_on_sources(case: Case, step_index: int, step: Mapping[str, Any]) -> None:
    """Validate that a Scenario step's ``on`` names real earlier steps.

    Every index in ``on`` — a single int, or an array of coordinate-group
    sources — MUST be ``>= 0``, strictly EARLIER than this step, and, for the
    array form, UNIQUE. ``on`` is OPTIONAL on the boundary verbs (``flush`` /
    ``commit`` / ``abort``), which target the unit of work rather than a prior
    object; when a boundary step DOES carry one — a ``flush`` documenting its
    buffered write — the same checks apply, which is why this rule is stated once
    for every kind of step rather than once per owner.
    """
    if "on" not in step:
        return
    on = step["on"]
    indices = list(on) if isinstance(on, list) else [on]
    if isinstance(on, list) and len(set(indices)) != len(indices):
        raise CaseFailure(
            f"{case.path.name}: scenario[{step_index}].on {on!r} names a DUPLICATE source; "
            f"a coordinate-grouped action references each source at most once."
        )
    for source in indices:
        if not 0 <= source < step_index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}].on references step {source!r}, "
                f"which is not a real EARLIER step (0 <= source < {step_index}); an action "
                f"targets the result of a prior step."
            )
