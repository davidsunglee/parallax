"""Identity semantics of Wire projection's call-local memo."""

from __future__ import annotations

from typing import cast

from parallax.snapshot.materialize import WireEntity
from parallax.snapshot.materialize._wire_memo import IndexMemo, StrongIdentityMemo


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
