"""The sentinels a construction input spells, in a scope granted nothing.

A positional row has a position for every declared member, so a state an input
does not carry has to be a value there rather than an omission. The values that
spell those states are the whole of this module, and it imports nothing at all:
they are read by the layout side, by the writer, by the descriptors that answer
a member read, and by the instance-state Module that assembles a published
value's backing — scopes that deliberately cannot reach one another. A sentinel
housed in any one of them would have made the others reach through it.

``UNLOADED`` is the relationship algebra's out-of-band state, and the only one:
loaded null is ``None``, loaded empty is ``()``, and a loaded value is the
related object or objects. That is why a relationship carries no presence bit —
the value at its position already names its state.
"""

from __future__ import annotations

__all__ = ["UNLOADED"]


class _Unloaded:
    """The private closed-world sentinel a frozen node's relationship position
    holds when its path was outside the include set (spec §3); never a public
    value."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNLOADED"


UNLOADED: _Unloaded = _Unloaded()
