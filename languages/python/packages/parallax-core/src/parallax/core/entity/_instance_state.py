"""A value's own attribute storage, reached past every authored binding.

Every framework slot a value carries outside its declared members — a Change
Record, a relationship view, the one lifecycle-state slot — lives in the
instance storage Pydantic's ``__dict__`` descriptor holds. Reaching it by name
would put a class body between the framework and its own state: ``getattr``,
``object.__getattribute__``, and ``object.__setattr__`` all resolve a name
through the type, so an authored ``__dict__``, ``__getattr__``,
``__getattribute__``, or a data descriptor bound under a slot's own name decides
what the framework reads back and where its writes land. These read and write
the storage itself, so a class body can neither hide the state a value carries
from them, nor offer them state it never carried, nor divert what they attach
somewhere they do not look.

Reaching past a binding is each caller's own decision, and the framework reads
that do not are deliberate. ``lifecycle_state_of`` resolves the slot through the
class because the read it offers is the class's own surface, and
``BaseModel.__getstate__`` reads ``self.__dict__`` the ordinary way, so what a
pickle carries is what the value's class answers for that name rather than the
storage underneath it.

Declared member access is deliberately not routed here: that surface is the
class's own, and validation, descriptors, and refusals belong on it.
"""

from __future__ import annotations

from typing import Any, Final, cast

from pydantic import BaseModel

__all__ = [
    "attach_instance_state",
    "instance_state",
    "replace_instance_state",
]

_MODEL_STORAGE: Final = BaseModel.__dict__["__dict__"]
"""Pydantic's own slot descriptor for the instance storage every model carries."""


def instance_state(value: BaseModel) -> dict[str, Any]:
    """``value``'s own attribute storage, as the mutable mapping it is."""
    return cast("dict[str, Any]", _MODEL_STORAGE.__get__(value))


def attach_instance_state(value: BaseModel, name: str, state: object) -> None:
    """Write ``state`` into ``value``'s storage under ``name``."""
    instance_state(value)[name] = state


def replace_instance_state(value: BaseModel, state: dict[str, object]) -> None:
    """Make ``state`` the whole of ``value``'s storage."""
    _MODEL_STORAGE.__set__(value, state)
