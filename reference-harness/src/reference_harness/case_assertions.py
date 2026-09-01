"""The assertion vocabulary the compatibility harness's grading seams share.

A name is offered here only if MORE THAN ONE of those seams has a live caller for
it — the case runner, write grading, the read oracle, Unit Work Scenario
grading — and what those names are implemented in terms of travels with them,
unless several seams call that primitive directly too, in which case it is a
module of its own (:mod:`.multiset`) rather than a second offering here. A name
one seam alone calls belongs to that seam instead, so this module never becomes
the place a helper lands when its home is unclear. It imports none of them, so no
seam can reach another through it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any

from . import multiset
from .case import Case


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


def scalars_equal(left: Any, right: Any, tolerance: Decimal | None) -> bool:
    """Compare already-canonical scalars, except for an authored tolerance.

    Declared-type projection happens before this generic grader. This seam does
    not repair Decimal/float, instant/string, UUID/string, or bytes/string carrier
    differences when no metadata says which value space they occupy.
    """
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and _mappings_equal(left, right, tolerance)
        )
    if _is_structural_sequence(left) or _is_structural_sequence(right):
        return (
            _is_structural_sequence(left)
            and _is_structural_sequence(right)
            and len(left) == len(right)
            and all(
                scalars_equal(one, other, tolerance) for one, other in zip(left, right, strict=True)
            )
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if tolerance is not None:
        da, db = _to_decimal(left), _to_decimal(right)
        if isinstance(da, Decimal) and isinstance(db, Decimal):
            return abs(da - db) <= tolerance
    if isinstance(left, int) and not isinstance(left, bool):
        return isinstance(right, int) and not isinstance(right, bool) and left == right
    if isinstance(left, float):
        return isinstance(right, float) and left == right
    return type(left) is type(right) and left == right


def _mappings_equal(
    left: Mapping[Any, Any],
    right: Mapping[Any, Any],
    tolerance: Decimal | None,
) -> bool:
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for left_key, left_value in left.items():
        right_index = next(
            (
                index
                for index, candidate in enumerate(unmatched)
                if type(left_key) is type(candidate) and left_key == candidate
            ),
            None,
        )
        if right_index is None:
            return False
        right_key = unmatched.pop(right_index)
        if not scalars_equal(left_value, right[right_key], tolerance):
            return False
    return not unmatched


def _is_structural_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    )


def _row_matches(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    tolerance: Decimal | None,
) -> bool:
    return scalars_equal(left, right, tolerance)


def rows_equal(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
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
    return multiset.multiset_matches(
        left, right, lambda row, candidate: _row_matches(row, candidate, tolerance)
    )


def write_value_equal(left: Any, right: Any) -> bool:
    """Exact structural equality for canonical Wire write values and binds."""
    return scalars_equal(left, right, None)


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


@contextlib.contextmanager
def reported_against(case: Case, step_index: int) -> Iterator[None]:
    """Name *case* and the Scenario step at *step_index* on every authored failure
    raised inside.

    A step's grading reaches oracles that speak of the read, statement, or write
    input they were handed rather than of the Scenario position that handed it
    over, so the position is added at the boundary that knows it rather than
    threaded through every one of them as a second parameter. Idempotent: a
    failure already naming both the case and this step — a delivery pointed at
    ``scenario[i].statements``, an Include level at ``when.scenario[i].statements``
    — is re-raised as it was written, so nesting one boundary inside another it
    already crossed adds nothing a second time. A driver exception is not an
    authored failure and passes through untouched.
    """
    try:
        yield
    except CaseFailure as failure:
        marker = f"scenario[{step_index}]"
        prefix = f"{case.path.name}: "
        message = str(failure)
        if message.startswith(prefix) and marker in message:
            raise
        detail = message[len(prefix) :] if message.startswith(prefix) else message
        raise CaseFailure(f"{prefix}{marker} {detail}") from failure
