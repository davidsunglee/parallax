"""A class body standing between a value and its own instance storage.

Several unit proofs need a declaration that answers for its instance state with
a mapping of its own choosing, so that a framework read of a private slot can be
shown to reach the storage underneath rather than the name. They differ only in
which slot is doctored and what an invented one holds, so the hook is shared and
each suite supplies those two facts.

``__dict__`` is not the route, because no declared class body may bind it: the
framework presents a published value's compact row under that name, and a body
answering for it would decide what Pydantic reads of every instance of the
class. The route that remains is ``__getattribute__``, which is deliberately
authorable and which answers every read of the name — ``getattr`` and
``object.__getattribute__`` alike. It cannot reach a write: Pydantic fills a
fresh instance by assigning ``__dict__``, and that assignment resolves a data
descriptor rather than an attribute hook. So a forgery is written into the
storage directly (:func:`forge_into_storage`), which is the residual any
in-process design leaves open and the one these proofs are stated against.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, cast

from pydantic import BaseModel

__all__ = ["answering_for_instance_state", "forge_into_storage", "stored_state"]

_MODEL_STORAGE: Final = BaseModel.__dict__["__dict__"]

_DENIED: Final = object()


def stored_state(value: BaseModel) -> dict[str, Any]:
    """``value``'s real storage, reached through Pydantic's own slot descriptor.

    Derived here rather than imported from the framework, so an assertion about
    what a value carries is independent of the seam under proof.
    """
    return cast("dict[str, Any]", _MODEL_STORAGE.__get__(value))


def answering_for_instance_state(
    slot: str, invented: object = _DENIED
) -> Callable[[Any, str], Any]:
    """A ``__getattribute__`` for a class body, doctoring one slot of ``__dict__``.

    With no ``invented`` state it hides ``slot`` from every read of the name,
    whatever the storage holds under it; with one it offers ``slot`` holding that
    state, which nothing wrote. The same object is answered on every read, so a
    reader that mutates what it was given changes what the next read sees.
    """

    def doctored(self: Any, name: str) -> Any:
        if name != "__dict__":
            return object.__getattribute__(self, name)
        stored = stored_state(self)
        if invented is _DENIED:
            return {held: value for held, value in stored.items() if held != slot}
        return {**stored, slot: invented}

    return doctored


def forge_into_storage(value: BaseModel, slot: str, state: object) -> None:
    """Write ``state`` into ``value``'s real storage under ``slot``.

    The forgery a class body cannot make and arbitrary code holding a value
    always can: what lands here is what every framework reader of that slot
    really finds, so a guarantee stated against it is stated against the storage
    rather than against an answer a reader could reach past.
    """
    stored_state(value)[slot] = state
