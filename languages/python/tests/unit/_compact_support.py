"""Building a compactly backed Entity or Value Object without a database, and
reading what one physically holds.

Publication drives this door itself, and reaching it needs a Domain Model, a
graph, and a build callback. A suite grading what the second backing IS rather
than how a read reaches it drives the instance-state Module's own door directly
instead: the same shell, the same whole row, attached the same once.
"""

from __future__ import annotations

import gc
from types import MemberDescriptorType
from typing import TYPE_CHECKING, Any, cast

from parallax.core.entity._instance_state import COMPACT_STATE_SLOT, allocate, publish
from parallax.core.entity._pydantic_storage import instance_state

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import BaseModel

__all__ = [
    "carries_instance_storage",
    "layout_slots",
    "published",
    "raw_row",
    "real_storage",
]


def published[M](
    cls: type[M], relationships: Mapping[str, object] | None = None, /, **members: object
) -> M:
    """A published value of ``cls`` carrying exactly ``members``.

    A member left unnamed is absent: it reads its declared default and its
    presence bit stays clear, which is the distinction ``model_fields_set`` and
    ``exclude_unset`` preserve. A relationship left unnamed holds the unloaded
    sentinel, as every relationship a read did not load does.
    """
    instance = allocate(cast("type[Any]", cls))
    publish(instance, members, relationships or {})
    return cast("M", instance)


def raw_row(value: BaseModel) -> tuple[Any, ...] | None:
    """``value``'s compact row itself, read off its slot.

    Not ``value.__dict__``: what a published value answers there is a
    presentation of this row, and what a suite grading the representation needs
    is the row.
    """
    return cast("tuple[Any, ...] | None", object.__getattribute__(value, COMPACT_STATE_SLOT))


def carries_instance_storage(value: BaseModel) -> bool:
    """Whether ``value``'s own instance storage exists yet, asked without creating it.

    Every dictionary the value refers to, minus the ones its object layout holds
    in slots of their own — auxiliary state, private attributes, extra fields.
    Scanning for a dictionary at all would answer yes for any value whose class
    declares a ``PrivateAttr`` or whose ``cached_property`` has been read, so a
    grading of whether STORAGE was created must ask by identity or be restricted
    to classes that carry neither.
    """
    beside: set[int] = set()
    for slot in layout_slots(type(value)).values():
        try:
            held = cast("object", slot.__get__(value))
        except AttributeError:
            continue
        if isinstance(held, dict):
            beside.add(id(cast("object", held)))
    return any(
        isinstance(held, dict) and id(cast("object", held)) not in beside
        for held in gc.get_referents(value)
    )


def real_storage(value: BaseModel) -> dict[str, Any]:
    """``value``'s own instance storage, underneath whatever it presents.

    Reading it CREATES it on a value that had none, so an assertion over it
    belongs last in a test that also grades whether one was ever created.
    """
    return instance_state(value)


def layout_slots(cls: type) -> dict[str, MemberDescriptorType]:
    """Every slot ``cls``'s object layout actually gives its instances, by name.

    Walked over the concrete class's whole MRO and off each ancestor's own
    namespace, so a suite grading what a derived copy carries inspects the layout
    the value really has rather than the one any single base declares. That is
    also what lets a suite grade the claim that the two are the same: no declared
    class may lay out ``__slots__``, so its layout is the shared root's.
    """
    return {
        name: descriptor
        for ancestor in reversed(cls.__mro__)
        for name, descriptor in vars(ancestor).items()
        if isinstance(descriptor, MemberDescriptorType)
    }
