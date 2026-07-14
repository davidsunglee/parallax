"""``parallax.core.db_error`` unit tests (m-db-error, Docker-free).

Covers the closed neutral category set, the classification seam over the pure
Postgres dialect code table, and the call-site **predicate partition** (each
category fires exactly one of ``is_retriable`` / ``violates_unique_index`` /
``is_timed_out``, and the reserved ``connectionDead`` and the uncategorized
``None`` fire none). The port-boundary re-raise is proven separately in
``test_postgres_adapter`` (Docker-free) and end-to-end by the provider deadlock
proof.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.core.db_error import (
    CATEGORIES,
    CONNECTION_DEAD,
    DEADLOCK,
    LOCK_WAIT_TIMEOUT,
    UNIQUE_VIOLATION,
    Category,
    DatabaseError,
    as_category,
    classify_error,
    is_retriable,
    is_timed_out,
    violates_unique_index,
)
from parallax.core.dialect import POSTGRES

pytestmark = pytest.mark.unit

_PREDICATES: dict[str, Callable[[Category | None], bool]] = {
    "is_retriable": is_retriable,
    "violates_unique_index": violates_unique_index,
    "is_timed_out": is_timed_out,
}

# The exact single predicate each category fires (empty for the reserved slot and
# for the uncategorized None). This is the closed partition the seam guarantees.
_PARTITION: list[tuple[Category | None, set[str]]] = [
    (UNIQUE_VIOLATION, {"violates_unique_index"}),
    (DEADLOCK, {"is_retriable"}),
    (LOCK_WAIT_TIMEOUT, {"is_timed_out"}),
    (CONNECTION_DEAD, set()),
    (None, set()),
]


def test_category_set_is_the_closed_four() -> None:
    assert {"uniqueViolation", "deadlock", "lockWaitTimeout", "connectionDead"} == CATEGORIES


@pytest.mark.parametrize(("category", "expected"), _PARTITION, ids=[str(c) for c, _ in _PARTITION])
def test_call_site_predicate_partition(category: Category | None, expected: set[str]) -> None:
    fired = {name for name, predicate in _PREDICATES.items() if predicate(category)}
    assert fired == expected


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("23505", UNIQUE_VIOLATION),
        ("40P01", DEADLOCK),
        # A serialization failure (40001) is retriable and shares the deadlock
        # category — the load-bearing distinction the seam localizes.
        ("40001", DEADLOCK),
        ("55P03", LOCK_WAIT_TIMEOUT),
    ],
)
def test_classify_error_maps_each_postgres_code(code: str, category: Category) -> None:
    error = classify_error(POSTGRES, code, "boom")
    assert error.category == category
    assert error.native_code == code
    assert error.message == "boom"


def test_classify_error_uncategorized_for_an_unknown_code() -> None:
    error = classify_error(POSTGRES, "99999", "mystery")
    assert error.category is None
    assert error.native_code == "99999"
    assert not error.is_retriable
    assert not error.violates_unique_index
    assert not error.is_timed_out


def test_classify_error_uncategorized_without_a_native_code() -> None:
    # A driver failure with no SQLSTATE (a dropped connection) never touches the
    # dialect code table; it is uncategorized (the reserved connectionDead slot).
    error = classify_error(POSTGRES, None, "server closed the connection")
    assert error.category is None
    assert error.native_code is None
    assert error.message == "server closed the connection"


@pytest.mark.parametrize(
    ("category", "retriable", "unique", "timed_out"),
    [
        (UNIQUE_VIOLATION, False, True, False),
        (DEADLOCK, True, False, False),
        (LOCK_WAIT_TIMEOUT, False, False, True),
        (None, False, False, False),
    ],
)
def test_database_error_properties_reflect_predicates(
    category: Category | None, retriable: bool, unique: bool, timed_out: bool
) -> None:
    error = DatabaseError(category=category, native_code="x", message="m")
    assert error.is_retriable is retriable
    assert error.violates_unique_index is unique
    assert error.is_timed_out is timed_out


def test_database_error_str_carries_category_code_and_message() -> None:
    error = DatabaseError(category=DEADLOCK, native_code="40P01", message="deadlock detected")
    assert str(error) == "deadlock [40P01]: deadlock detected"
    uncategorized = DatabaseError(category=None, native_code=None, message="down")
    assert str(uncategorized) == "uncategorized [no-sqlstate]: down"


def test_as_category_narrows_only_known_members() -> None:
    assert as_category("deadlock") == DEADLOCK
    assert as_category("connectionDead") == CONNECTION_DEAD
    assert as_category("not-a-category") is None
    assert as_category(None) is None
