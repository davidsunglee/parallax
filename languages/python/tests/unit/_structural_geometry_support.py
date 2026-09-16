"""The geometry-varying Value Object structures the structural read and write
families measure, under both storage layouts.

Each :class:`~parallax.conformance.workloads.GeometryLevel` fixes one nesting
depth, one Many cardinality, one leaf width, and one populated-leaf count; this
module realizes the distinct structures those levels need — one chain of One
occurrences per (depth, width) and one Many element shape per width — as
class-backed declarations, and one Entity per structure and layout. A level's
authored value populates the first ``populated`` leaves of every occurrence with
fixed-width strings, so two values of one level weigh the same and two levels
differ only in the dimension they vary.

The write families insert one such value; the read families materialize
:data:`~parallax.conformance.workloads.READ_GEOMETRY_ROOTS` stored rows of it
through a provider-free port that composes each row fresh when the statement
runs, so nothing but production owns a row once it is returned.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

# No `from __future__ import annotations`: the Value Object and Entity classes
# are composed at import time from class objects, and a stringized annotation
# would name a class the declaration engine cannot resolve.

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from parallax.conformance.workloads import (
    GEOMETRY_LEVELS,
    READ_GEOMETRY_ROOTS,
    GeometryLevel,
)
from parallax.core import Attr, Document, DomainModel, Entity, ValueObject, attr
from parallax.core.db_port import DocumentReadOrdinals, PipelineStatement, Row
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.object_query._fluent import ObjectQuery
from tests._support.db_port import ConnectsAsItself, projected_rows

__all__ = [
    "ENTITY_CLASSES",
    "GEOMETRY_LEVELS",
    "LAYOUTS",
    "MODEL",
    "READ_GEOMETRY_ROOTS",
    "GeometryPort",
    "GeometryShape",
    "Layout",
    "entity_class",
    "instance",
    "level_named",
    "read_query",
    "shape_of",
    "stored_row",
    "wire_row",
]

type Layout = Literal["columns", "document"]

LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")

_NAMESPACE: Final = "structural.geometry"
_MANY: Final = "items"
_ONE: Final = "body"
_NEXT: Final = "next"
_PAYLOAD: Final = "payload"


@dataclass(frozen=True, slots=True)
class GeometryShape:
    """The declarations one (depth, width) geometry needs, shared by every level
    and layout with that depth and width."""

    depth: int
    width: int
    bodies: tuple[type[ValueObject], ...]
    item: type[ValueObject]
    entities: Mapping[Layout, type[Entity]]

    @property
    def body(self) -> type[ValueObject]:
        return self.bodies[0]


def _leaf_name(index: int) -> str:
    return f"f{index}"


def _leaf_annotations(width: int) -> dict[str, object]:
    return {_leaf_name(index): Attr[str | None] for index in range(width)}


def _value_object(name: str, annotations: Mapping[str, object]) -> type[ValueObject]:
    namespace = {"__annotations__": dict(annotations), "__module__": __name__}
    return cast("type[ValueObject]", type(name, (ValueObject,), namespace))


def _body_chain(depth: int, width: int) -> tuple[type[ValueObject], ...]:
    """``depth`` nested One occurrences of ``width`` leaves each, root first."""
    chain: list[type[ValueObject]] = []
    for level in range(depth, 0, -1):
        annotations = _leaf_annotations(width)
        if chain:
            annotations[_NEXT] = Attr[chain[-1] | None]
        chain.append(_value_object(f"Body{level}W{width}", annotations))
    return tuple(reversed(chain))


def _entity(
    name: str, body: type[ValueObject], item: type[ValueObject], layout: Layout
) -> type[Entity]:
    annotations: dict[str, object] = {
        "id": Attr[int],
        _ONE: Attr[body],
        _MANY: Attr[tuple[item, ...]],
    }
    namespace = {
        "__annotations__": annotations,
        "__module__": __name__,
        "id": attr(primary_key=True),
    }
    keywords: dict[str, object] = {"table": name.lower(), "namespace": _NAMESPACE}
    if layout == "document":
        keywords["layout"] = Document(column=_PAYLOAD)
    return cast("type[Entity]", type(name, (Entity,), namespace, **keywords))


def _shape(depth: int, width: int) -> GeometryShape:
    bodies = _body_chain(depth, width)
    item = _value_object(f"ItemW{width}", _leaf_annotations(width))
    return GeometryShape(
        depth,
        width,
        bodies,
        item,
        {
            layout: _entity(
                f"Geometry{layout.capitalize()}D{depth}W{width}", bodies[0], item, layout
            )
            for layout in LAYOUTS
        },
    )


SHAPES: Final[Mapping[tuple[int, int], GeometryShape]] = {
    key: _shape(*key) for key in sorted({(level.depth, level.width) for level in GEOMETRY_LEVELS})
}

ENTITY_CLASSES: Final[tuple[type[Entity], ...]] = tuple(
    shape.entities[layout] for shape in SHAPES.values() for layout in LAYOUTS
)
"""Every geometry Entity, in shape then layout order."""

MODEL: Final = DomainModel(*ENTITY_CLASSES)


def level_named(name: str) -> GeometryLevel:
    for level in GEOMETRY_LEVELS:
        if level.id == name:
            return level
    raise KeyError(f"{name!r} is not a geometry level: {[level.id for level in GEOMETRY_LEVELS]}")


def shape_of(level: GeometryLevel) -> GeometryShape:
    return SHAPES[(level.depth, level.width)]


def entity_class(level: GeometryLevel, layout: Layout) -> type[Entity]:
    return shape_of(level).entities[layout]


def _leaf_value(index: int, key: int) -> str:
    return f"{index:03d}-{key:08d}"


def _leaves(level: GeometryLevel, key: int) -> dict[str, str]:
    return {_leaf_name(index): _leaf_value(index, key) for index in range(level.populated)}


def _body_document(level: GeometryLevel, key: int) -> dict[str, object]:
    """The root occurrence's authored document, chained ``depth`` levels deep."""
    document: dict[str, object] | None = None
    for _ in range(level.depth):
        inner: dict[str, object] = dict(_leaves(level, key))
        if document is not None:
            inner[_NEXT] = document
        document = inner
    assert document is not None
    return document


def _items_document(level: GeometryLevel, key: int) -> list[dict[str, object]]:
    return [dict(_leaves(level, key + element)) for element in range(level.many)]


def wire_row(level: GeometryLevel, key: int) -> dict[str, object]:
    """One authored row as a Wire caller states it, fresh on every call."""
    return {"id": key, _ONE: _body_document(level, key), _MANY: _items_document(level, key)}


def _body_instance(shape: GeometryShape, level: GeometryLevel, key: int) -> ValueObject:
    instance: ValueObject | None = None
    for cls in reversed(shape.bodies):
        members: dict[str, object] = dict(_leaves(level, key))
        if instance is not None:
            members[_NEXT] = instance
        instance = cls(**members)
    assert instance is not None
    return instance


def instance(level: GeometryLevel, layout: Layout, key: int) -> Entity:
    """One authored Typed value of ``level`` under ``layout``."""
    shape = shape_of(level)
    items = tuple(shape.item(**_leaves(level, key + element)) for element in range(level.many))
    return shape.entities[layout](id=key, **{_ONE: _body_instance(shape, level, key), _MANY: items})


def stored_row(level: GeometryLevel, layout: Layout, key: int) -> dict[str, object]:
    """One stored row as the driver would answer it, keyed by physical column."""
    if layout == "document":
        return {
            "id": key,
            _PAYLOAD: {_ONE: _body_document(level, key), _MANY: _items_document(level, key)},
        }
    return wire_row(level, key)


def read_query(level: GeometryLevel, layout: Layout) -> ObjectQuery[Any, Any]:
    """The whole-table instance read of ``level``'s Entity under ``layout``."""
    cls = entity_class(level, layout)
    return cls.where(cls.all)


class GeometryPort(ConnectsAsItself):
    """Provider-free stored rows for one geometry level and layout.

    Every statement composes its rows afresh and keeps none of them, so what a
    reading retains after materialization is what production kept.
    """

    dialect: Dialect = POSTGRES
    __slots__ = ("_layout", "_level", "_roots")
    _level: GeometryLevel
    _layout: Layout
    _roots: int

    def __init__(self, level: GeometryLevel, layout: Layout, roots: int) -> None:
        self._level = level
        self._layout = layout
        self._roots = roots

    def rows(self) -> Iterator[Mapping[str, object]]:
        for offset in range(self._roots):
            yield stored_row(self._level, self._layout, 1 + offset)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del binds
        return projected_rows(sql, self.rows(), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        raise NotImplementedError

    def transaction[T](
        self,
        body: Callable[[Any], T],
        *,
        isolation: str | None = None,
    ) -> Any:
        del body, isolation
        raise NotImplementedError

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]
