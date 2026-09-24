"""The Concurrency Preference vocabulary and its owner-provided validator
(`m-unit-work` "Strategy selection"): what the closed two-valued vocabulary
admits, how it refuses everything else, and what an accepted value comes back
as.
"""

from __future__ import annotations

import pytest

from parallax.core.unit_work import concurrency_preference
from parallax.core.unit_work.strategy import CONCURRENCY_PREFERENCES


class _UnhashableName(str):
    """A ``str`` no set can be asked about, so the validator is proved to compare."""

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_two_preferences() -> None:
    assert set(CONCURRENCY_PREFERENCES) == {"locking", "optimistic"}


@pytest.mark.parametrize("preference", sorted(CONCURRENCY_PREFERENCES))
def test_every_preference_of_the_vocabulary_is_returned_unchanged(preference: str) -> None:
    assert concurrency_preference(preference) == preference


@pytest.mark.parametrize(
    "value",
    [
        "pessimistic",
        "LOCKING",
        "",
        None,
        True,
        3,
        [],
        {"concurrency": "locking"},
        _UnhashableName("bogus"),
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"concurrency must be one of \['locking', 'optimistic'\]"):
        concurrency_preference(value)


def test_an_accepted_preference_comes_back_as_a_plain_hashable_str() -> None:
    preference = concurrency_preference(_UnhashableName("locking"))

    assert preference == "locking"
    assert {preference: "keyable"}
