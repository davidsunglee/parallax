"""The vocabulary a positional construction input is spelled in, granted nothing.

A positional row has a position for every declared member, so a state an input
does not carry has to be a value there rather than an omission. The values that
spell those states, and the opaque handle a relationship position names another
node by, are the whole of this module, and it imports nothing at all: they are
read by the layout side, by a runtime that lays a stored row out against one, by
the writer, by the descriptors that answer a member read, and by the
instance-state Module that assembles a published value's backing — scopes that
deliberately cannot reach one another. A value housed in any one of them would
have made the others reach through it, and would have let a row's producer reach
the writer, ``construct``, or model formation.

``ABSENT`` is the member algebra's out-of-band state: a position holding it
carried nothing, so the member stays at its declared default and outside the
populated set. ``UNLOADED`` is the relationship algebra's, and the only one:
loaded null is ``None``, loaded empty is ``()``, and a loaded value is the
related node or nodes. That is why a relationship carries no presence bit — the
value at its position already names its state.
"""

from __future__ import annotations

from typing import Final

__all__ = ["ABSENT", "UNLOADED", "Absent", "NodeHandle"]


class Absent:
    """The type of :data:`ABSENT`, named so a reader can spell the test."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT: Final[Absent] = Absent()
"""The one absent-or-unloaded sentinel a positional member row spells absence
with, private to this implementation.

Deliberately not the document codec's ``MISSING`` or ``UNAVAILABLE``, which are
consumed and discarded inside decoding and describe a stored document rather
than a materialized row. It never escapes as a final public value: every
consumer of a row either skips an absent position or is refused before
publication.
"""


class _Unloaded:
    """The private closed-world sentinel a frozen node's relationship position
    holds when its path was outside the include set (spec §3); never a public
    value."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNLOADED"


UNLOADED: _Unloaded = _Unloaded()


class NodeHandle:
    """An opaque, callback-scoped reference to one allocated node.

    It holds nothing whatever: the issuing construction owns the mapping from
    handle to allocation index, so a handle exposes no attribute to read, no
    index to restate, and no route to a partially built instance. A caller
    composes graph shape by passing handles back, never by reading anything off
    one, and a handle means nothing outside the ``construct(...)`` call that
    issued it.
    """

    __slots__ = ()
