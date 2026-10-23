"""A wide Value Object selection under both storage layouts.

One standalone Entity declares :data:`WIDTH` top-level Value Object occurrences
of one small shape, so a read selecting all of them names many occurrence
identities rather than many leaves inside a few. The two layout twins declare
the same members and differ only in ``layout``.

The models are frozen: their member names, shapes, and widths are measurement
inputs, so a suite needing another shape declares its own.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

# No `from __future__ import annotations`: the Entity classes are declared by a
# factory from annotation values, and a stringized annotation would name a local
# the declaration engine cannot resolve.

from collections.abc import Mapping
from typing import Any, Final, Literal

from parallax.core import Attr, Document, DomainModel, Entity, Int32, ObjectQuery, ValueObject, attr

__all__ = [
    "LAYOUTS",
    "OCCURRENCES",
    "WIDE_MODELS",
    "WIDTH",
    "Facet",
    "Layout",
    "wide_entity",
    "wide_query",
]

type Layout = Literal["columns", "document"]

LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
WIDTH: Final = 32
OCCURRENCES: Final = tuple(f"facet_{index:02d}" for index in range(WIDTH))
"""Every top-level occurrence name, in declaration order."""


class Facet(ValueObject):
    label: Attr[str | None]
    rank: Attr[int | None] = attr(type=Int32)


def _wide_entity(layout: Layout) -> Any:
    annotations: dict[str, object] = {"id": Attr[int]}
    annotations.update({name: Attr[Facet | None] for name in OCCURRENCES})
    return type(
        "WideHolder",
        (Entity,),
        {"__module__": __name__, "__annotations__": annotations, "id": attr(primary_key=True)},
        table=f"wide_holder_{layout}",
        namespace=f"read.projection.wide.{layout}",
        **({"layout": Document()} if layout == "document" else {}),
    )


_ENTITIES: Final[Mapping[Layout, Any]] = {layout: _wide_entity(layout) for layout in LAYOUTS}
WIDE_MODELS: Final[Mapping[Layout, DomainModel]] = {
    layout: DomainModel(entity) for layout, entity in _ENTITIES.items()
}


def wide_entity(layout: Layout) -> Any:
    """``layout``'s wide Entity Class."""
    return _ENTITIES[layout]


def wide_query(layout: Layout) -> ObjectQuery[Any, Any]:
    """Every row of ``layout``'s wide Entity."""
    entity = _ENTITIES[layout]
    return entity.where(entity.all)
