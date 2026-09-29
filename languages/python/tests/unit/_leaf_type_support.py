"""The leaf-type Value Object structures the leaf-type read, keyed-write, and
predicate-acquisition families measure, under both storage layouts.

Every type the leaf-type manifest names is declared at one geometry,
:func:`~parallax.conformance.workloads.leaf_type_level`: a root occurrence and
a Many of its elements, each declaring that level's width of leaves of the
type, every leaf populated. The leaves live inside structured documents under
both layouts, so two types differ only in how production decodes, compares,
publishes, and encodes a leaf, never in where it is stored. Each type has a
non-temporal Entity per layout, which the reads materialize and the inserts
open, and a Bitemporal one per layout, which the predicate acquisition
resolves. A stored row spells every leaf in its canonical Wire form, as the
driver answers a document.

A leaf's value is a function of its index and of the occurrence's key alone,
so rows of one type weigh the same and every value is taken on its type's
general path: Float64 leaves are decimal tenths, which binary64 cannot represent
exactly. String is the control each type is read against, valued exactly as the
geometry families value their leaves. Where a geometry cell already measures
that structure — the level's read and its Typed insert — the geometry cell is
the control and the String type declares none; the Wire insert and the
acquisition, which no geometry case measures at this level, read a String cell
of their own.

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
    LEAF_CONTROL_TYPE_ID,
    LEAF_TYPE_IDS,
    GeometryLevel,
    leaf_type_level,
)
from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, ValueObject, attr
from parallax.core.db_port import DocumentReadOrdinals, PipelineStatement, Row
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import model_of
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.storage_layout import view as storage_layout_view
from tests._support.db_port import ConnectsAsItself, projected_rows
from tests.unit import _structural_geometry_support as geometry_support

__all__ = [
    "ACQUIRED_TYPES",
    "CONTROL",
    "LAYOUTS",
    "LEVEL",
    "MEASURED_TYPES",
    "MODEL",
    "READ_GROUP",
    "READ_PREFIX",
    "WIRE_INSERTED_TYPES",
    "Layout",
    "LeafPort",
    "LeafType",
    "acquisition_entity",
    "body_document",
    "entity_class",
    "instance",
    "leaf_type_named",
    "read_address",
    "read_query",
    "read_workload",
    "stored_row",
    "wire_row",
]

type Layout = Literal["columns", "document"]

LAYOUTS: Final[tuple[Layout, ...]] = geometry_support.LAYOUTS
LEVEL: Final[GeometryLevel] = leaf_type_level()

READ_GROUP: Final = "leaf"
"""The name the Snapshot report selects every leaf-type read by."""
READ_PREFIX: Final = "leaf-"
"""What every leaf-type read workload is named with, ahead of its type id."""

_NAMESPACE: Final = "structural.leaf"
_MANY: Final = "items"
_ONE: Final = "body"

if LEVEL.depth != 1 or LEVEL.populated != LEVEL.width:
    raise ValueError(
        f"{LEVEL.id}: a leaf-type level is one root occurrence with every leaf populated"
    )


def _decimal_tenths(index: int, key: int) -> float:
    """A decimal tenth whose tenths digit is never 0 or 5, so binary64 holds it
    inexactly while its canonical spelling stays short."""
    return (key * 10_000 + index * 10 + index % 4 + 1) / 10


@dataclass(frozen=True, slots=True, eq=False)
class LeafType:
    """One declarable Neutral Type as every leaf of a structure declares it.

    ``annotation`` is the host type an ``Attr`` names and ``declaration``
    composes the namespace value that narrows it, when one does. ``typed`` is
    the Typed value of leaf ``index`` in the occurrence keyed ``key`` and
    ``wire`` its canonical Wire spelling; both are spelled directly, so
    composing a row runs no codec. Each type is declared once, so identity is
    equality.
    """

    id: str
    annotation: type
    declaration: Callable[[], object] | None
    typed: Callable[[int, int], object]
    wire: Callable[[int, int], object]

    @property
    def title(self) -> str:
        return self.id.capitalize()


_LEAF_TYPES: Final[Mapping[str, LeafType]] = {
    leaf.id: leaf
    for leaf in (
        LeafType("string", str, None, geometry_support.leaf_value, geometry_support.leaf_value),
        LeafType("float64", float, None, _decimal_tenths, _decimal_tenths),
    )
}

CONTROL: Final[LeafType] = _LEAF_TYPES[LEAF_CONTROL_TYPE_ID]
MEASURED_TYPES: Final[tuple[LeafType, ...]] = tuple(_LEAF_TYPES[name] for name in LEAF_TYPE_IDS)
"""Every type the manifest measures, in manifest order."""
if CONTROL in MEASURED_TYPES:
    raise ValueError(f"{CONTROL.id} is the control every measured leaf type is read against")
_DECLARED_TYPES: Final[tuple[LeafType, ...]] = (CONTROL, *MEASURED_TYPES)
WIRE_INSERTED_TYPES: Final[tuple[LeafType, ...]] = (CONTROL, *MEASURED_TYPES)
"""Every type a Wire insert opens a row of: the measured types and their
String control, which no geometry case inserts through Wire."""
ACQUIRED_TYPES: Final[tuple[LeafType, ...]] = (CONTROL, *MEASURED_TYPES)
"""Every type the predicate acquisition resolves rows of: the measured types
and their String control, which no geometry case acquires."""


def leaf_type_named(name: str) -> LeafType:
    try:
        return _LEAF_TYPES[name]
    except KeyError:
        raise KeyError(f"{name!r} is not a leaf type: {list(_LEAF_TYPES)}") from None


def _leaf_name(index: int) -> str:
    return f"f{index}"


def _value_object(name: str, leaf: LeafType) -> type[ValueObject]:
    names = tuple(_leaf_name(index) for index in range(LEVEL.width))
    namespace: dict[str, object] = {
        "__annotations__": {name: Attr[leaf.annotation | None] for name in names},
        "__module__": __name__,
    }
    if leaf.declaration is not None:
        namespace.update({name: leaf.declaration() for name in names})
    return cast("type[ValueObject]", type(name, (ValueObject,), namespace))


def _entity(
    name: str,
    body: type[ValueObject],
    item: type[ValueObject],
    layout: Layout,
    base: type[Entity],
) -> type[Entity]:
    namespace = {
        "__annotations__": {"id": Attr[int], _ONE: Attr[body], _MANY: Attr[tuple[item, ...]]},
        "__module__": __name__,
        "id": attr(primary_key=True),
    }
    keywords: dict[str, object] = {"table": name.lower(), "namespace": _NAMESPACE}
    if layout == "document":
        keywords["layout"] = Document(column="payload")
    return cast("type[Entity]", type(name, (base,), namespace, **keywords))


@dataclass(frozen=True, slots=True)
class _Declared:
    """The declarations one leaf type needs under every layout."""

    body: type[ValueObject]
    item: type[ValueObject]
    entities: Mapping[Layout, type[Entity]]
    acquired: Mapping[Layout, type[Entity]]


def _declared(leaf: LeafType) -> _Declared:
    body = _value_object(f"LeafBody{leaf.title}", leaf)
    item = _value_object(f"LeafItem{leaf.title}", leaf)
    return _Declared(
        body,
        item,
        {
            layout: _entity(f"Leaf{leaf.title}{layout.capitalize()}", body, item, layout, Entity)
            for layout in LAYOUTS
        },
        {
            layout: _entity(
                f"LeafAcquisition{leaf.title}{layout.capitalize()}", body, item, layout, Bitemporal
            )
            for layout in LAYOUTS
        },
    )


_DECLARED: Final[Mapping[str, _Declared]] = {leaf.id: _declared(leaf) for leaf in _DECLARED_TYPES}

MODEL: Final = DomainModel(
    *(
        entities[layout]
        for declared in _DECLARED.values()
        for entities in (declared.entities, declared.acquired)
        for layout in LAYOUTS
    )
)
"""Every leaf-type Entity, a model of its own: joining the structural write
model would move what that model's preparation and every read of it retain."""


def entity_class(leaf: LeafType, layout: Layout) -> type[Entity]:
    """The non-temporal Entity a read materializes and an insert opens."""
    return _DECLARED[leaf.id].entities[layout]


def acquisition_entity(leaf: LeafType, layout: Layout) -> type[Entity]:
    """The Bitemporal Entity the predicate acquisition resolves rows of."""
    return _DECLARED[leaf.id].acquired[layout]


def _document_placement(cls: type[Entity]) -> tuple[str, tuple[str, ...]]:
    """The Structured Column ``cls`` stores its document residents in, and their
    names in residency order."""
    view = storage_layout_view(model_of(MODEL)).entity(cls.identity)
    residents = None if view is None else view.document_residents
    assert residents is not None, cls
    (column,) = {placement.slot.column.name for placement in residents.placements}
    return column, tuple(member.name for member in residents.shape.members)


_DOCUMENT_PLACEMENTS: Final[Mapping[type[Entity], tuple[str, tuple[str, ...]]]] = {
    entities["document"]: _document_placement(entities["document"])
    for declared in _DECLARED.values()
    for entities in (declared.entities, declared.acquired)
}
"""Where each document-layout Entity's stored row carries its members, resolved
once so composing a row consults nothing but this mapping."""

_LEAF_TYPE_OF: Final[Mapping[type[Entity], LeafType]] = {
    entity: leaf
    for leaf in _DECLARED_TYPES
    for entities in (_DECLARED[leaf.id].entities, _DECLARED[leaf.id].acquired)
    for entity in entities.values()
}


def body_document(leaf: LeafType, key: int) -> dict[str, object]:
    """The root occurrence keyed ``key`` in Wire spellings, fresh on every call."""
    wire = leaf.wire
    return {_leaf_name(index): wire(index, key) for index in range(LEVEL.width)}


def _items_document(leaf: LeafType, key: int) -> list[dict[str, object]]:
    return [body_document(leaf, key + element) for element in range(LEVEL.many)]


def wire_row(leaf: LeafType, key: int) -> dict[str, object]:
    """One authored row as a Wire caller states it, fresh on every call."""
    return {"id": key, _ONE: body_document(leaf, key), _MANY: _items_document(leaf, key)}


def instance(leaf: LeafType, layout: Layout, key: int) -> Entity:
    """One authored Typed value of ``leaf`` under ``layout``."""
    declared = _DECLARED[leaf.id]
    typed = leaf.typed

    def members(occurrence: int) -> dict[str, object]:
        return {_leaf_name(index): typed(index, occurrence) for index in range(LEVEL.width)}

    items = tuple(declared.item(**members(key + element)) for element in range(LEVEL.many))
    return declared.entities[layout](id=key, **{_ONE: declared.body(**members(key)), _MANY: items})


def stored_row(entity: type[Entity], key: int) -> dict[str, object]:
    """One stored row of ``entity`` as the driver would answer it, keyed by
    physical column; a temporal Entity's bounds are the caller's to add."""
    row = wire_row(_LEAF_TYPE_OF[entity], key)
    placement = _DOCUMENT_PLACEMENTS.get(entity)
    if placement is None:
        return row
    column, members = placement
    return {"id": key, column: {name: row[name] for name in members}}


def read_workload(leaf: LeafType) -> str:
    """The Snapshot workload a read of ``leaf`` is reported under."""
    return f"{READ_PREFIX}{leaf.id}"


def read_address(workload: str) -> LeafType | None:
    """The leaf type a read workload names, or absence for any other workload."""
    if not workload.startswith(READ_PREFIX):
        return None
    leaf = leaf_type_named(workload.removeprefix(READ_PREFIX))
    if leaf not in MEASURED_TYPES:
        raise KeyError(f"{workload} is not a measured leaf-type read")
    return leaf


def read_query(leaf: LeafType, layout: Layout) -> ObjectQuery[Any, Any]:
    """The whole-table instance read of ``leaf``'s Entity under ``layout``."""
    cls = entity_class(leaf, layout)
    return cls.where(cls.all)


class LeafPort(ConnectsAsItself):
    """Provider-free stored rows of one leaf-type Entity.

    Every statement composes its rows afresh and keeps none of them, so what a
    reading retains after materialization is what production kept.
    """

    dialect: Dialect = POSTGRES
    __slots__ = ("_entity", "_roots")
    _entity: type[Entity]
    _roots: int

    def __init__(self, entity: type[Entity], roots: int) -> None:
        self._entity = entity
        self._roots = roots

    def rows(self) -> Iterator[Mapping[str, object]]:
        for offset in range(self._roots):
            yield stored_row(self._entity, 1 + offset)

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
