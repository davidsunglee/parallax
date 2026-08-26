"""A value's own attribute storage, reached past every binding over it.

A framework slot a value carries outside its declared members — a Change Record,
the one lifecycle-state slot, a relationship view on a value Pydantic backs —
lives in the instance storage Pydantic's ``__dict__`` descriptor holds. Reaching
it by name would put a class body between the framework and its own state:
``getattr``, ``object.__getattribute__``, and ``object.__setattr__`` all resolve
a name through the type, so an authored ``__getattr__``, ``__getattribute__``,
or a data descriptor bound under a slot's own name decides what the framework
reads back and where its writes land. (Reservation shortens that list for the two
names instance state is presented under without emptying it: the declaration
engine keeps every class body from binding either one, so no descriptor of a
class's own stands under them — while ``__getattribute__`` remains authorable and
answers a read of any name, those two included.) These read and write the storage
itself, so a class body can neither hide the state a value carries from them,
nor offer them state it never carried, nor divert what they attach somewhere
they do not look.

The framework binds under those two names itself, so these reach past its own
presentation as well: a published value answers ``__dict__`` and
``__pydantic_fields_set__`` with a mapping and a set derived from its compact
row, and what these return is the storage underneath that. On a published value
there is none, and asking is what would CREATE one — permanently, on a read — so
these are for a caller that means the storage itself. Its declared members and
its relationship positions are in the row rather than here, and its author-owned
dynamic state is in a slot beside it, so a framework read of what a value holds
by name goes through the backing instead (``_instance_state.named_state``),
which answers a published value out of the row and that slot.

Construction is the one storage write the framework does not make here: Pydantic
fills a fresh instance by assigning ``__dict__``, which the framework's own
descriptor for that name answers — so the write lands in the storage below and
the value ends up ordinary, whatever it was before. What no seam decides is what
a mapping found in that storage is WORTH, and that stays each reader's question:
the Change Record's reader accepts only the carrier an edit constructs, so
provenance cannot be forged by a well-shaped mapping reaching the storage some
other way.

Reaching past a binding is each caller's own decision, and the framework reads
that do not are deliberate. ``lifecycle_state_of`` resolves the slot through the
class because the read it offers is the class's own surface, and
``BaseModel.__getstate__`` reads ``self.__dict__`` the ordinary way, so what a
pickle carries is what the value ANSWERS for that name rather than the storage
underneath it: the storage itself where Pydantic backs the value and a mapping
derived from the row where it is published — which is what makes a pickle of a
published value cross as an ordinary one — or, on a class that authors
``__getattribute__``, whatever that hook hands back in place of either.

The slots beside those two are a different question and not this Module's. A
value's private-attribute state lives in the object layout rather than in the
storage, so a caller deriving a copy out of semantic state has to carry that
layout across or reset it. Settling that needs to know which slots of the layout the backing
already answers for, which is the backing's own fact rather than Pydantic's, so
the carry lives with it
(:func:`~parallax.core.entity._instance_state.carry_slots_beside_state`).

Declared member access is deliberately not routed here: that surface is the
class's own, and validation, descriptors, and refusals belong on it.
"""

from __future__ import annotations

from typing import Any, Final, cast

from pydantic import BaseModel

__all__ = [
    "MODEL_PRESENCE",
    "MODEL_STORAGE",
    "attach_instance_state",
    "instance_presence",
    "instance_state",
    "replace_instance_presence",
    "replace_instance_state",
]

MODEL_STORAGE: Final = BaseModel.__dict__["__dict__"]
"""Pydantic's own slot descriptor for the instance storage every model carries.

Exported beside the functions over it because a caller layering its own
presentation on this name reaches it once per read of every model in the
process, where the extra call the functions cost is measurable.
"""

MODEL_PRESENCE: Final = BaseModel.__dict__["__pydantic_fields_set__"]
"""Pydantic's own slot descriptor for the populated-member set beside it."""


def instance_state(value: BaseModel) -> dict[str, Any]:
    """``value``'s own attribute storage, as the mutable mapping it is.

    Creates one on a value that holds none, which a published value does — so a
    read that only means to see what a value holds belongs on the backing's own
    reader instead, and this is for the callers that mean the storage.
    """
    return cast("dict[str, Any]", MODEL_STORAGE.__get__(value))


def attach_instance_state(value: BaseModel, name: str, state: object) -> None:
    """Write ``state`` into ``value``'s storage under ``name``."""
    instance_state(value)[name] = state


def replace_instance_state(value: BaseModel, state: dict[str, object]) -> None:
    """Make ``state`` the whole of ``value``'s storage."""
    MODEL_STORAGE.__set__(value, state)


def instance_presence(value: BaseModel) -> set[str]:
    """The populated-member set ``value`` itself holds.

    Raises ``AttributeError`` for a value that holds none, which a shell awaiting
    publication and a published value both do.
    """
    return cast("set[str]", MODEL_PRESENCE.__get__(value))


def replace_instance_presence(value: BaseModel, populated: set[str]) -> None:
    """Make ``populated`` the whole of ``value``'s own populated-member set."""
    MODEL_PRESENCE.__set__(value, populated)
