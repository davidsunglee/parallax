"""A class body standing between a value and its own instance storage.

Several unit proofs need a declaration whose ``__dict__`` answers with a mapping
of its own choosing, so that a framework read of a private slot can be shown to
reach the storage underneath rather than the name. They differ only in which
slot is doctored and what an invented one holds, so the descriptor is shared and
each suite supplies those two facts.

Pydantic's own slot descriptor is what holds the storage, so an authored
``__dict__`` can delegate every write to it — leaving the value really carrying
whatever the framework attached — and still deny one slot on the way out, or
offer one the value never held.

Construction is the one write worth doctoring rather than forwarding: Pydantic
fills a fresh instance by assigning ``__dict__`` under that name, so a class
body binding it can add a slot to the storage a value really starts out with
rather than merely answer for one (:class:`ForgingInstanceDict`).
"""

from __future__ import annotations

from typing import Any, Final, cast

from pydantic import BaseModel

__all__ = ["AuthoredInstanceDict", "ForgingInstanceDict", "stored_state"]

_MODEL_STORAGE: Final = BaseModel.__dict__["__dict__"]

_DENIED: Final = object()


def stored_state(value: BaseModel) -> dict[str, Any]:
    """``value``'s real storage, reached through Pydantic's own slot descriptor.

    Derived here rather than imported from the framework, so an assertion about
    what a value carries is independent of the seam under proof.
    """
    return cast("dict[str, Any]", _MODEL_STORAGE.__get__(value))


class AuthoredInstanceDict:
    """A ``__dict__`` descriptor answering for one doctored slot.

    An invented slot is answered with the same object on every read, so a reader
    that mutates what it was given changes what the next read sees.
    """

    def __init__(self, slot: str, invented: object) -> None:
        self._slot = slot
        self._invented = invented

    @classmethod
    def denying(cls, slot: str) -> AuthoredInstanceDict:
        """A ``__dict__`` hiding ``slot``, whatever the storage holds under it."""
        return cls(slot, _DENIED)

    @classmethod
    def inventing(cls, slot: str, state: object) -> AuthoredInstanceDict:
        """A ``__dict__`` answering ``slot`` with ``state``, which nothing wrote."""
        return cls(slot, state)

    def __get__(self, instance: BaseModel, owner: type[object] | None = None) -> dict[str, Any]:
        stored = stored_state(instance)
        if self._invented is _DENIED:
            return {name: value for name, value in stored.items() if name != self._slot}
        return {**stored, self._slot: self._invented}

    def __set__(self, instance: BaseModel, value: dict[str, Any]) -> None:
        _MODEL_STORAGE.__set__(instance, value)


class ForgingInstanceDict:
    """A ``__dict__`` descriptor writing one slot into every storage assigned through it.

    Reads answer with the storage itself, so what this class body offers is what
    the value really holds: the forgery is in the write construction makes, not
    in an answer a reader could reach past.
    """

    def __init__(self, slot: str, state: object) -> None:
        self._slot = slot
        self._state = state

    def __get__(self, instance: BaseModel, owner: type[object] | None = None) -> dict[str, Any]:
        return stored_state(instance)

    def __set__(self, instance: BaseModel, value: dict[str, Any]) -> None:
        _MODEL_STORAGE.__set__(instance, {**value, self._slot: self._state})
