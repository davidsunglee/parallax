from __future__ import annotations

from typing import ClassVar, Final, Self

__all__ = ["ABSENT", "UNLOADED", "Absent", "NodeHandle"]


class Absent:
    """The type of :data:`ABSENT`, named so a reader can spell the test.

    Sameness is identity: :data:`ABSENT` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[Absent | None] = None

    def __new__(cls) -> Absent:
        if Absent._instance is None:
            Absent._instance = super().__new__(cls)
        return Absent._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("Absent admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "ABSENT"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
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
    holds when its path was outside the include set; never a public
    value.

    Sameness is identity: :data:`UNLOADED` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[_Unloaded | None] = None

    def __new__(cls) -> _Unloaded:
        if _Unloaded._instance is None:
            _Unloaded._instance = super().__new__(cls)
        return _Unloaded._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("_Unloaded admits one instance and therefore no subclass")

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNLOADED"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
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
