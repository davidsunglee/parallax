"""Read-projection fixtures under both storage layouts.

One standalone Entity declares :data:`WIDTH` top-level Value Object occurrences
of one small shape, so a read selecting all of them names many occurrence
identities rather than many leaves inside a few. The two layout twins declare
the same members and differ only in ``layout``. These wide models are frozen:
their member names, shapes, and widths are measurement inputs.

The matrix families, one per inheritance strategy and layout, give every read
shape a position to select from. An abstract ``Root`` declares an inherited
Value Object; its concrete ``Left`` and ``Right`` each declare a distinct
``home`` occurrence of the same storage spelling, except under table-per-hierarchy
``Columns`` layout, where the shared Table refuses the collision and ``Right``'s
occurrence takes its own Column. Concrete ``Plain`` declares one Attribute and no
Value Object, so under ``Document`` layout it alone keeps a document-resident
Attribute. A standalone ``Holder`` includes every ``Root``.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

# No `from __future__ import annotations`: the Entity classes are declared by a
# factory from annotation values, and a stringized annotation would name a local
# the declaration engine cannot resolve.

from collections.abc import Mapping
from typing import Any, Final, Literal

from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    ObjectQuery,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)
from parallax.core._execution._preflight import preflight
from parallax.core.entity._authored_resolver import object_query_node
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    EntityMetadata,
    Metamodel,
    TablePerConcreteSubtype,
    entity_by_name,
)
from parallax.core.object_query._resolved import ResolvedObjectQuery

__all__ = [
    "LAYOUTS",
    "MATRIX_FAMILIES",
    "MATRIX_META",
    "MATRIX_MODEL",
    "OCCURRENCES",
    "STRATEGIES",
    "WIDE_MODELS",
    "WIDTH",
    "Facet",
    "Layout",
    "Spot",
    "Strategy",
    "matrix_entity",
    "resolved",
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


type Strategy = Literal["tph", "tpcs"]

STRATEGIES: Final[tuple[Strategy, ...]] = ("tph", "tpcs")


class Spot(ValueObject):
    city: Attr[str | None]


def _matrix_family(strategy: Strategy, layout: Layout) -> Mapping[str, Any]:
    namespace = f"read.projection.matrix.{strategy}.{layout}"
    hierarchy = strategy == "tph"
    table = f"mx_{strategy}_{layout}"
    root: Any = type(
        "Root",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {
                "id": Attr[int],
                "holder_id": Attr[int | None],
                "origin": Attr[Spot | None],
            },
            "id": attr(primary_key=True),
        },
        namespace=namespace,
        inheritance=AbstractRoot(
            TablePerHierarchy("kind") if hierarchy else TablePerConcreteSubtype()
        ),
        **({"table": table} if hierarchy else {}),
        **({"layout": Document()} if layout == "document" else {}),
    )
    declared: Mapping[str, tuple[Mapping[str, object], Mapping[str, object]]] = {
        "Left": ({"home": Attr[Spot | None]}, {}),
        "Right": (
            {"home": Attr[Spot | None]},
            {"home": attr(column="right_home")} if hierarchy and layout == "columns" else {},
        ),
        "Plain": ({"note": Attr[str | None]}, {}),
    }
    classes: dict[str, Any] = {"Root": root}
    for name, (annotations, members) in declared.items():
        tag = name.lower()
        classes[name] = type(
            name,
            (root,),
            {"__module__": __name__, "__annotations__": dict(annotations), **members},
            namespace=namespace,
            inheritance=ConcreteSubtype(tag_value=tag) if hierarchy else ConcreteSubtype(),
            **({} if hierarchy else {"table": f"{table}_{tag}"}),
        )
    classes["Holder"] = type(
        "Holder",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int], "members": Rel[tuple[root, ...]]},
            "id": attr(primary_key=True),
            "members": rel(cardinality=ONE_TO_MANY, join=("id", "holder_id")),
        },
        table=f"{table}_holder",
        namespace=namespace,
    )
    return classes


MATRIX_FAMILIES: Final[Mapping[tuple[Strategy, Layout], Mapping[str, Any]]] = {
    (strategy, layout): _matrix_family(strategy, layout)
    for strategy in STRATEGIES
    for layout in LAYOUTS
}
"""Every matrix family's classes under their own names."""
MATRIX_MODEL: Final = DomainModel(
    *(cls for classes in MATRIX_FAMILIES.values() for cls in classes.values())
)
MATRIX_META: Final[Metamodel] = model_of(MATRIX_MODEL)


def matrix_entity(strategy: Strategy, layout: Layout, name: str) -> EntityMetadata:
    """``name``'s accepted metadata in the ``strategy``/``layout`` matrix family."""
    metadata = entity_by_name(MATRIX_META, f"read.projection.matrix.{strategy}.{layout}.{name}")
    assert metadata is not None
    return metadata


def resolved(
    query: ObjectQuery[Any, Any], *, form: Literal["rows", "graph"] = "graph"
) -> ResolvedObjectQuery:
    """``query`` against :data:`MATRIX_MODEL`, validated as a read in ``form`` is."""
    return preflight(object_query_node(query, MATRIX_MODEL), model=MATRIX_META, form=form)
