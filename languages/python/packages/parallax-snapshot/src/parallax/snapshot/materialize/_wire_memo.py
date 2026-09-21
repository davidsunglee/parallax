"""Identity memo implementations used by Wire publication walks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

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
