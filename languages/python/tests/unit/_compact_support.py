"""Building a compactly backed Entity or Value Object without a database.

Nothing in production publishes compact backing yet — Entity Graph Construction
still writes ordinary Pydantic state — so the suites that grade the second
backing build one by driving the instance-state Module's own door directly. That
is deliberately the SAME door construction will drive: a shell is allocated, its
whole row is assembled, and the row is attached once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from parallax.core.entity._instance_state import allocate, publish

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["published"]


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
