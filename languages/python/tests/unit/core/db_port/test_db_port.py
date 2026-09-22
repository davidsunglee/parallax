"""The port's own portable vocabularies (m-db-port). Docker-free.

For isolation: what the closed set is, that a name outside it is refused as the
caller's mistake rather than carried on to a database that would refuse it
later, and what an accepted name comes back as. For acquisition failure: which
reasons a caller can be given at all.
"""

from __future__ import annotations

from typing import get_args

import pytest

from parallax.core.db_port import (
    ISOLATION_LEVELS,
    AcquisitionReason,
    ConnectionContext,
    ConnectionContextSource,
    InvalidAuthorizationError,
    isolation_level,
)


class UnhashableName(str):
    """A ``str`` subclass no set can be asked about.

    It passes every type check a level name passes, so it is what separates
    validating by membership (which hashes, and would raise ``TypeError``) from
    validating by comparison.
    """

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_three_levels() -> None:
    assert set(ISOLATION_LEVELS) == {"read_committed", "repeatable_read", "serializable"}


@pytest.mark.parametrize("level", sorted(ISOLATION_LEVELS))
def test_every_level_of_the_vocabulary_is_returned_unchanged(level: str) -> None:
    assert isolation_level(level) == level


@pytest.mark.parametrize(
    "value",
    [
        "read uncommitted",  # a real level, deliberately outside the vocabulary
        "repeatable read",  # a database's own spelling rather than the portable one
        "REPEATABLE_READ",  # the vocabulary is exact, not case-folded
        "",
        None,
        3,
        [],  # unhashable: a set membership test alone would raise TypeError here
        {"level": "serializable"},
        UnhashableName("bogus"),  # unhashable AND a str: it clears an isinstance guard
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"isolation must be one of \['read_committed', "):
        isolation_level(value)


def test_an_accepted_level_comes_back_as_a_plain_hashable_str() -> None:
    level = isolation_level(UnhashableName("serializable"))

    assert level == "serializable"
    assert {level: "an adapter's per-level spelling"}


def test_a_connection_context_source_declares_resource_free_context_creation() -> None:
    class _Source:
        def new_context(self) -> ConnectionContext:
            raise AssertionError("the structural check must perform no I/O")

    assert isinstance(_Source(), ConnectionContextSource)


def test_invalid_authorization_is_a_caller_value_error() -> None:
    assert issubclass(InvalidAuthorizationError, ValueError)


def test_an_acquisition_names_one_of_six_reasons_for_granting_nothing() -> None:
    # Read back off the alias rather than off a table that projects it, so a
    # member added on one side and not the other is caught here rather than as
    # a lookup that raises on the one acquisition that failed that way.
    assert set(get_args(AcquisitionReason.__value__)) == {
        "timeout",
        "queue_rejected",
        "closed",
        "preparation_failed",
        "authorization_failed",
        "credentials_refused",
    }
