"""The identity contract every sentinel has to keep.

Each of these singletons answers a question no value could — absent, unloaded,
missing, unavailable, SQL null, latest, unobserved, no stored member at all — and
a site holding one alone asks ``is`` (a site holding a union whose other arms
carry data reads the class instead, which is what narrows to those arms). A copy
boundary is where the contract is easiest to lose silently: a second instance
would answer ``is`` with ``False`` while looking identical in a traceback, so a
sentinel that crossed a deep copy or a pickle would turn a settled question back
into an open one.

The public API snapshot diffs ``__all__`` alone, so it cannot see this. Nothing
else grades it either, which is why the contract is stated in ``python.md`` and
pinned here.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from parallax.core.base import SQL_NULL
from parallax.core.document_codec import MISSING, NULL, UNAVAILABLE
from parallax.core.entity._construction_input import ABSENT, UNLOADED
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.object_query import LATEST
from parallax.snapshot import MISSING_STORED_VALUE

_SENTINELS: list[tuple[str, object]] = [
    ("LATEST", LATEST),
    ("UNLOADED", UNLOADED),
    ("ABSENT", ABSENT),
    ("INERT", INERT),
    ("NULL", NULL),
    ("MISSING", MISSING),
    ("UNAVAILABLE", UNAVAILABLE),
    ("SQL_NULL", SQL_NULL),
    ("MISSING_STORED_VALUE", MISSING_STORED_VALUE),
]


@pytest.mark.parametrize(("name", "sentinel"), _SENTINELS, ids=[name for name, _ in _SENTINELS])
def test_a_sentinel_stays_itself_across_copy_deep_copy_and_pickle(
    name: str, sentinel: object
) -> None:
    assert copy.copy(sentinel) is sentinel
    assert copy.deepcopy(sentinel) is sentinel
    assert copy.deepcopy({"held": (sentinel,)})["held"][0] is sentinel
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(sentinel, protocol)) is sentinel, name


@pytest.mark.parametrize(("name", "sentinel"), _SENTINELS, ids=[name for name, _ in _SENTINELS])
def test_a_sentinel_repr_names_the_export_a_reader_would_spell(name: str, sentinel: object) -> None:
    assert repr(sentinel) == name


def test_a_sentinel_class_admits_no_second_meaningful_instance() -> None:
    # A zero-field frozen dataclass compares a fresh instance equal to the
    # singleton, so two notions of sameness would coexist where a use site asks
    # `is`. These classes are plain identity classes: a second construction is a
    # distinct object under both `is` and `==`.
    assert type(NULL)() != NULL
    assert type(MISSING)() != MISSING
    assert type(UNAVAILABLE)() != UNAVAILABLE
    assert type(SQL_NULL)() != SQL_NULL
    assert type(MISSING_STORED_VALUE)() != MISSING_STORED_VALUE
