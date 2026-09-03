"""The port's own portable isolation vocabulary (m-db-port). Docker-free.

What the closed set is, and that a name outside it is refused as the caller's
mistake rather than carried on to a database that would refuse it later.
"""

from __future__ import annotations

import pytest

from parallax.core.db_port import ISOLATION_LEVELS, isolation_level


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
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"isolation must be one of \['read_committed', "):
        isolation_level(value)
