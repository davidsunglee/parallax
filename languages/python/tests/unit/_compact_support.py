"""Building a compactly backed Entity or Value Object without a database.

Nothing in production publishes compact backing yet — Entity Graph Construction
still writes ordinary Pydantic state — so the suites that grade the second
backing build one by driving the instance-state Module's own door directly. That
is deliberately the SAME door construction will drive: a shell is allocated, its
whole row is assembled, and the row is attached once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from parallax.core.entity._instance_state import COMPACT_STATE_SLOT, allocate, publish
from parallax.core.entity._pydantic_storage import instance_state

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import BaseModel

__all__ = ["published", "raw_row", "real_storage"]


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


def real_storage(value: BaseModel) -> dict[str, Any]:
    """``value``'s own instance storage, underneath whatever it presents.

    Reading it CREATES it on a value that had none, so an assertion over it
    belongs last in a test that also grades whether one was ever created.
    """
    return instance_state(value)
