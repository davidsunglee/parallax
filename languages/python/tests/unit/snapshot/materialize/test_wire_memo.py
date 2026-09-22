"""Identity semantics of Wire projection's call-local memo."""

from __future__ import annotations

import gc
import weakref
from typing import cast

import pytest

from parallax.snapshot.materialize import WireEntity, _wire_memo
from parallax.snapshot.materialize._wire_memo import (
    IndexMemo,
    StrongIdentityMemo,
    WeakIdentityMemo,
)


class _WeakNode:
    __slots__ = ("__weakref__", "peer")

    def __init__(self) -> None:
        self.peer: _WeakNode | None = None

    def __eq__(self, other: object) -> bool:
        del other
        raise AssertionError("identity memo compared Entity values")

    def __hash__(self) -> int:
        raise AssertionError("identity memo hashed an Entity value")


class _Output:
    pass


def test_strong_memo_keys_actual_identity_not_equality() -> None:
    first: list[object] = []
    equal_but_distinct: list[object] = []
    output = cast("WireEntity", {"id": 1})
    memo = StrongIdentityMemo[list[object]]()

    memo.put(first, -1, output)

    assert memo.get(first, -1) is output
    assert memo.get(equal_but_distinct, -1) is None


def test_strong_memo_separates_render_tokens_and_releases_owners() -> None:
    node = object()
    leaf = cast("WireEntity", {"id": 1})
    continued = cast("WireEntity", {"id": 1, "children": []})
    memo = StrongIdentityMemo[object]()

    memo.put(node, -1, leaf)
    memo.put(node, 3, continued)
    assert memo.get(node, -1) is leaf
    assert memo.get(node, 3) is continued

    memo.clear()
    assert memo.get(node, -1) is None


def test_index_memo_releases_completed_outputs() -> None:
    output = cast("WireEntity", {"id": 1})
    memo = IndexMemo()
    memo.put(3, -1, output)

    memo.clear()

    assert memo.get(3, -1) is None


def test_weak_memo_uses_identity_without_hashing_and_releases_with_its_owner() -> None:
    node = _WeakNode()
    output = _Output()
    continued = _Output()
    output_ref = weakref.ref(output)
    memo = WeakIdentityMemo[_WeakNode]()
    memo.put(node, -1, cast("WireEntity", output))
    memo.put(node, 3, cast("WireEntity", continued))

    assert memo.get(node, -1) is output
    assert memo.get(node, 3) is continued
    del output
    gc.collect()
    assert output_ref() is not None

    del node
    gc.collect()
    assert output_ref() is None


def test_weak_memo_does_not_keep_a_cyclic_input_graph_alive() -> None:
    first = _WeakNode()
    second = _WeakNode()
    first.peer = second
    second.peer = first
    first_ref = weakref.ref(first)
    second_ref = weakref.ref(second)
    memo = WeakIdentityMemo[_WeakNode]()
    memo.put(first, -1, cast("WireEntity", _Output()))

    del first, second
    gc.collect()

    assert first_ref() is None
    assert second_ref() is None


def test_weak_memo_collection_callback_cannot_delete_a_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _WeakNode()
    second = _WeakNode()
    second_output = _Output()

    def shared_identity(_value: object) -> int:
        return 7

    monkeypatch.setattr(_wire_memo, "id", shared_identity, raising=False)
    memo = WeakIdentityMemo[_WeakNode]()
    memo.put(first, -1, cast("WireEntity", _Output()))
    memo.put(second, -1, cast("WireEntity", second_output))

    del first
    gc.collect()

    assert memo.get(second, -1) is second_output


def test_weak_memo_callback_does_not_keep_the_memo_alive() -> None:
    node = _WeakNode()
    memo = WeakIdentityMemo[_WeakNode]()
    memo.put(node, -1, cast("WireEntity", _Output()))
    memo_ref = weakref.ref(memo)

    del memo
    gc.collect()

    assert memo_ref() is None
