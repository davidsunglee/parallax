"""The port's own portable isolation vocabulary (m-db-port). Docker-free.

What the closed set is, that a name outside it is refused as the caller's mistake
rather than carried on to a database that would refuse it later, and what an
accepted name comes back as.
"""

from __future__ import annotations

import pytest

from parallax.core.db_port import ISOLATION_LEVELS, isolation_level


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
