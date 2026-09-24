from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar
from weakref import ReferenceType, ref

from parallax.core.deep_fetch import RenderToken

if TYPE_CHECKING:
    from parallax.snapshot.materialize._wire import WireEntity

Node = TypeVar("Node", contravariant=True)


class WireMemo(Protocol[Node]):
    def get(self, node: Node, token: RenderToken) -> WireEntity | None: ...

    def put(self, node: Node, token: RenderToken, value: WireEntity) -> None: ...

    def clear(self) -> None: ...


class IndexMemo:
    """Completed RootView outputs keyed by stable allocation index and token."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[int, dict[RenderToken, WireEntity]] = {}

    def get(self, node: int, token: RenderToken) -> WireEntity | None:
        held = self._entries.get(node)
        return None if held is None else held.get(token)

    def put(self, node: int, token: RenderToken, value: WireEntity) -> None:
        self._entries.setdefault(node, {})[token] = value

    def clear(self) -> None:
        self._entries.clear()


class StrongIdentityMemo[Node]:
    """Call-local completed outputs keyed by actual input identity and token."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[int, tuple[Node, dict[RenderToken, WireEntity]]] = {}

    def get(self, node: Node, token: RenderToken) -> WireEntity | None:
        held = self._entries.get(id(node))
        if held is None or held[0] is not node:
            return None
        return held[1].get(token)

    def put(self, node: Node, token: RenderToken, value: WireEntity) -> None:
        identity = id(node)
        held = self._entries.get(identity)
        if held is None or held[0] is not node:
            self._entries[identity] = (node, {token: value})
            return
        held[1][token] = value

    def clear(self) -> None:
        self._entries.clear()


class WeakIdentityMemo[Node]:
    """Page-owned completed outputs whose input owners remain weak."""

    __slots__ = ("__weakref__", "_entries")

    def __init__(self) -> None:
        self._entries: dict[int, tuple[ReferenceType[Node], dict[RenderToken, WireEntity]]] = {}

    def get(self, node: Node, token: RenderToken) -> WireEntity | None:
        held = self._entries.get(id(node))
        if held is None or held[0]() is not node:
            return None
        return held[1].get(token)

    def put(self, node: Node, token: RenderToken, value: WireEntity) -> None:
        identity = id(node)
        held = self._entries.get(identity)
        if held is not None and held[0]() is node:
            held[1][token] = value
            return

        memo = ref(self)

        def collected(owner: ReferenceType[Node]) -> None:
            current = memo()
            if current is not None:
                current._remove(identity, owner)

        self._entries[identity] = (ref(node, collected), {token: value})

    def clear(self) -> None:
        self._entries.clear()

    def _remove(self, identity: int, owner: ReferenceType[Node]) -> None:
        held = self._entries.get(identity)
        if held is not None and held[0] is owner:
            del self._entries[identity]
