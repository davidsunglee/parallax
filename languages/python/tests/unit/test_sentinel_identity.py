"""The identity contract every sentinel has to keep.

Each of these singletons answers a question no value could — absent, unloaded,
missing, unavailable, SQL null, latest, unobserved, no stored member at all — and
a site holding one alone asks ``is`` (a site holding a union whose other arms
carry data reads the class instead, which is what narrows to those arms). Those
two readings only agree while no second object passes the class test, so every
route to one is closed here: construction, the copy and pickle boundaries where
a second instance would answer ``is`` with ``False`` while looking identical in
a traceback, and the subclass such an instance would otherwise belong to.

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


@pytest.mark.parametrize(("name", "sentinel"), _SENTINELS, ids=[name for name, _ in _SENTINELS])
def test_a_sentinel_class_admits_no_second_instance(name: str, sentinel: object) -> None:
    # Every class here is exported and callable, and the readers that hold a
    # sentinel inside a union ask `isinstance` because that is what narrows to
    # the arms carrying data. A second instance would satisfy those readers
    # while answering `is` and `==` with `False` against the exported constant,
    # so the class answers the constant instead of constructing one.
    assert type(sentinel)() is sentinel, name


@pytest.mark.parametrize(("name", "sentinel"), _SENTINELS, ids=[name for name, _ in _SENTINELS])
def test_a_sentinel_class_admits_no_subclass_to_hold_a_second_instance(
    name: str, sentinel: object
) -> None:
    # Answering the constant from the class binds only the class itself: a
    # subclass declaring its own `__new__` would pass every `isinstance` reader
    # while answering `is` with `False`, and four of these classes are on the
    # distribution's public surface for a caller to write. Declaring the
    # subclass is what fails, so the second instance has no class to belong to.
    with pytest.raises(TypeError, match="admits one instance"):
        type(f"Second{name}", (type(sentinel),), {})
