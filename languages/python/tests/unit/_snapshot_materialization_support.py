"""The production Snapshot materialization workload, under both storage layouts.

One representative graph shape — a table-per-hierarchy family with an abstract
middle, nested One and Many Value Objects at two depths, every declarable Neutral
Type as an Entity Attribute and again as a document leaf, duplicate logical nodes
through a narrowed view, three view slots and a back-reference — driven through
production's own read loop with no database anywhere: ``UNCACHED_READ_PLANNER``
plans the read, ``PageReader._read_root`` executes and holds the root statement,
and ``PageReader._build_page`` converts it, renders and executes every fetch
template, and retains the Page's read sources. :class:`StressPort` answers each
statement with rows composed before it.

The two PageReader steps are private, and are reached here rather than copied:
a measured window opens between them, so the root statement's execution stays
outside it while every fetch the Page build runs stays inside.

A fourth workload model rather than a reuse: the older Snapshot graph baseline
workload was ``Columns``-only and declared four Neutral Types, ``_document_layout_support``
is a layout twin at the accepted-Metamodel level with no ``DomainModel`` for
``prepare_model`` to prepare, and the earlier retention workload predates the
Page contract. Members are declared once in a factory over the layout, while both
layouts retain the descriptor's one canonical namespace.

Rows are projected from the catalog fixture itself through each level's compiled
read: authored values, nulls, omissions, and occurrence cardinalities are
preserved, then each authored member is placed where ``m-storage-layout`` says it
lives. :func:`verify` states that the resulting sparse rows form the expected Page
without stored-data findings and that the model still declares every supported
Neutral Type.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

# No `from __future__ import annotations`: the Entity classes are declared inside
# a factory, and a stringized `Attr[Tag | None]` names a local the declaration
# engine cannot resolve. The one forward reference that survives — a Rel to an
# Entity declared after it — is resolved against this module's globals, which is
# why the factory binds `Owner` there before composing the model.

import datetime as dt
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal as PyDecimal
from functools import cache
from typing import Any, Final, Literal, cast

from parallax.conformance.provision import fixture_document, fixture_literal
from parallax.conformance.workloads import catalog
from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Float32,
    Int32,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    deep_fetch,
    rel,
)
from parallax.core.base import SQL_NULL, DocumentValue, ManagedValue, PresentDocument
from parallax.core.db_port import DocumentReadOrdinals, Row
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.document_codec import (
    Leaf,
    MemberShape,
    Occurrence,
    encode_leaf,
    occurrence_shape,
)
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import model_of
from parallax.core.execution._page_origins import ObservedPageProjections
from parallax.core.execution._preflight import preflight
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    Multiplicity,
    entity_by_name,
)
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._page import ABSENT, Page, page_rows
from parallax.core.read_delivery._page_reader import (
    EagerPageResult,
    PageReader,
    _RootRead,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, ReadPlan
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.storage_layout import DirectColumn, TableLayout
from parallax.core.storage_layout import view as storage_layout_view
from parallax.core.unit_work import ReadOrigin
from tests._support.db_port import ConnectsAsItself

__all__ = [
    "LAYOUTS",
    "OWNERS",
    "PROJECTIONS_PER_BATCH",
    "ROWS_PER_BATCH",
    "Layout",
    "StressPort",
    "batch",
    "build_page",
    "compiled_levels",
    "driver_rows",
    "metamodel",
    "query",
    "read_plan",
    "read_root",
    "rows_per_level",
    "verify",
    "workload",
]

type Layout = Literal["columns", "document"]

LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
"""Every storage layout the workload is measured under, in report order."""

_WORKLOAD_IDS: Final[Mapping[Layout, str]] = {
    "columns": "stress-columns",
    "document": "stress-document",
}
_WORKLOADS: Final = {
    layout: catalog()[workload_id] for layout, workload_id in _WORKLOAD_IDS.items()
}

FANOUT: Final = _WORKLOADS["columns"].fanout
OWNERS: Final = FANOUT * 2
DUPLICATES: Final = len(_WORKLOADS["columns"].rows(1).entity("snapshot.materialization.Alpha"))
"""Root objects per batch, children per root, and how many of those children a
narrowed view converts a second time."""


PROJECTIONS_PER_BATCH: Final = OWNERS * (1 + FANOUT + DUPLICATES + 1)
"""Converted rows per batch: each root, its children, the narrowed duplicates,
and the to-one hop that re-converts one child."""

ROWS_PER_BATCH: Final = PROJECTIONS_PER_BATCH
"""Stored rows per batch. Equal to the projection count because every row of a
conforming batch converts, which :func:`verify` is what states."""

_ROOT: Final = ""
_NODES: Final = "nodes"
_NARROWED: Final = "special[Alpha]"
_FAVORITE: Final = "favorite"


def _entity_classes(layout: Layout) -> tuple[type[Entity], ...]:
    namespace = "snapshot.materialization"
    placement = Document(column="payload") if layout == "document" else None

    class Detail(ValueObject):
        note: Attr[str | None]
        depth: Attr[int | None] = attr(type=Int32)
        marked: Attr[bool | None]

    class Tag(ValueObject):
        label: Attr[str | None]
        flag: Attr[bool | None]
        small: Attr[int | None] = attr(type=Int32)
        big: Attr[int | None]
        ratio: Attr[float | None] = attr(type=Float32)
        measure: Attr[float | None]
        amount: Attr[PyDecimal | None] = attr(precision=12, scale=2)
        blob: Attr[bytes | None]
        day: Attr[dt.date | None]
        clock: Attr[dt.time | None]
        instant: Attr[dt.datetime | None]
        token: Attr[uuid.UUID | None]
        detail: Attr[Detail | None]
        details: Attr[tuple[Detail, ...]]

    class Node(
        Entity,
        table="materialization_node",
        namespace=namespace,
        inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
        layout=placement,
    ):
        id: Attr[int] = attr(primary_key=True)
        owner_id: Attr[int | None]
        label: Attr[str | None] = attr(max_length=32)
        flag: Attr[bool | None]
        small: Attr[int | None] = attr(type=Int32)
        big: Attr[int | None]
        ratio: Attr[float | None] = attr(type=Float32)
        measure: Attr[float | None]
        amount: Attr[PyDecimal | None] = attr(precision=12, scale=2)
        blob: Attr[bytes | None]
        day: Attr[dt.date | None]
        clock: Attr[dt.time | None]
        instant: Attr[dt.datetime | None]
        token: Attr[uuid.UUID | None]
        primary_tag: Attr[Tag | None]
        tags: Attr[tuple[Tag, ...]]
        owner: Rel["Owner | None"] = rel(reverse_of="nodes")

    class Special(Node, namespace=namespace, inheritance=AbstractSubtype):
        rank: Attr[int | None] = attr(type=Int32)

    class Alpha(Special, namespace=namespace, inheritance=ConcreteSubtype(tag_value="alpha")):
        pass

    class Beta(Node, namespace=namespace, inheritance=ConcreteSubtype(tag_value="beta")):
        weight: Attr[float | None]

    class Owner(
        Entity,
        table="materialization_owner",
        namespace=namespace,
        layout=placement,
    ):
        id: Attr[int] = attr(primary_key=True)
        name: Attr[str | None] = attr(max_length=32)
        favorite_id: Attr[int | None]
        nodes: Rel[tuple[Node, ...]] = rel(
            cardinality=ONE_TO_MANY, join=("id", "owner_id"), dependent=True
        )
        special: Rel[tuple[Special, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))
        favorite: Rel[Node | None] = rel(cardinality=MANY_TO_ONE, join=("favorite_id", "id"))

    globals()["Owner"] = Owner
    return (Node, Special, Alpha, Beta, Owner)


@cache
def workload(layout: Layout) -> DomainModel:
    """The representative Domain Model under ``layout``."""
    fixture = _WORKLOADS[layout]
    realized = DomainModel(*_entity_classes(layout))
    fixture.validate_class_backed(realized)
    return realized


@cache
def metamodel(layout: Layout) -> Metamodel:
    """``layout``'s accepted Metamodel, formed outside every measured window."""
    return model_of(workload(layout))


def query(layout: Layout, model: Metamodel) -> ResolvedObjectQuery:
    """The read every batch runs: three includes off the root and one
    back-reference revisiting it."""
    return preflight(
        _WORKLOADS[layout].query,
        model=model,
        form="graph",
    )


def read_plan(model: CatalogedModel, validated: ResolvedObjectQuery) -> ReadPlan:
    """``validated``'s instance-form read plan for a read no unit of work owns,
    compiled afresh on every call."""
    return UNCACHED_READ_PLANNER.plan(
        edition="",
        model=model,
        dialect=POSTGRES,
        query=validated,
        result_form="instance",
        preference=None,
    )


def compiled_levels(layout: Layout, plan: ReadPlan) -> tuple[CompiledRead | None, ...]:
    """One compiled read per source position: the root at 0, fetch step ``i`` at
    ``i + 1``, and absence for the back-reference level, which issues no statement.

    Each fetch template is rendered with the keys this module's fixture supplies,
    which are the keys the Page build gathers from the fixture's root rows.
    """
    root, _prepared = plan.root_read()
    reads: list[CompiledRead | None] = [root]
    for index in range(plan.fetch_count):
        step = plan.fetch_step(index)
        if isinstance(step, deep_fetch.BackReferenceFetchStep):
            reads.append(None)
            continue
        compiled, _prepared = plan.fetch_read(index, _level_keys(layout, _attach_key(plan, step)))
        reads.append(compiled)
    return tuple(reads)


def _attach_key(plan: ReadPlan, step: deep_fetch.FetchStep) -> str:
    view = plan.include_tree().position(step.position).view
    assert view is not None
    return view.narrowed_view or view.relationship.name


# --------------------------------------------------------------------------- #
# The fixture: which rows each level returns, and what each one holds.         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _RowSpec:
    """One fixture-authored logical row and the concrete Entity it resolves to."""

    entity: str
    values: Mapping[str, object]


def _row_spec(entity: str, row: Mapping[str, object]) -> _RowSpec:
    return _RowSpec(entity.rsplit(".", 1)[-1], row)


def _specs(layout: Layout, attach_key: str, owners: int, first: int) -> tuple[_RowSpec, ...]:
    scripted = _WORKLOADS[layout].rows(first + owners)
    owner_rows = scripted.entity("snapshot.materialization.Owner")[first:]
    owner_ids = {row["id"] for row in owner_rows}
    favorite_ids = {row["favoriteId"] for row in owner_rows}
    alpha = scripted.entity("snapshot.materialization.Alpha")
    beta = scripted.entity("snapshot.materialization.Beta")
    nodes = tuple(
        sorted(
            (row for row in (*alpha, *beta) if row["ownerId"] in owner_ids),
            key=lambda row: cast("int", row["id"]),
        )
    )
    if attach_key == _ROOT:
        selected = (("snapshot.materialization.Owner", row) for row in owner_rows)
    elif attach_key == _NODES:
        selected = (
            (
                "snapshot.materialization.Alpha"
                if row in alpha
                else "snapshot.materialization.Beta",
                row,
            )
            for row in nodes
        )
    elif attach_key == _NARROWED:
        selected = (
            ("snapshot.materialization.Alpha", row) for row in alpha if row["ownerId"] in owner_ids
        )
    elif attach_key == _FAVORITE:
        selected = (
            (
                "snapshot.materialization.Alpha"
                if row in alpha
                else "snapshot.materialization.Beta",
                row,
            )
            for row in nodes
            if row["id"] in favorite_ids
        )
    else:
        return ()
    return tuple(_row_spec(entity, row) for entity, row in selected)


def _level_keys(layout: Layout, attach_key: str) -> list[ManagedValue]:
    """The distinct parent keys a level's statement binds, as the fixture fixes
    them — what the Page build's own key gathering answers.

    Always the whole fixture's keys, whatever a caller then converts: the rendered
    statement's text, which is all a rendering here is for, does not depend on
    them."""
    rows = _WORKLOADS[layout].rows(OWNERS).entity("snapshot.materialization.Owner")
    key = "favoriteId" if attach_key == _FAVORITE else "id"
    return [cast("ManagedValue", row[key]) for row in rows]


def _occurrence_value(shape: MemberShape, multiplicity: Multiplicity, raw: object) -> DocumentValue:
    if multiplicity is Multiplicity.MANY:
        if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
            return cast("DocumentValue", raw)
        source = cast("Sequence[object]", raw)
        return cast(
            "DocumentValue",
            [
                fixture_document(shape, cast("Mapping[str, object]", element))
                if isinstance(element, Mapping)
                else element
                for element in source
            ],
        )
    return cast(
        "DocumentValue",
        fixture_document(shape, cast("Mapping[str, object]", raw))
        if isinstance(raw, Mapping)
        else raw,
    )


def _driver_row(
    model: CatalogedModel, compiled: CompiledRead, entity: EntityIdentity, spec: _RowSpec
) -> Row:
    """One stored row as the driver answers it: direct Columns under their own
    result keys, and every document-resident member inside the Structured Column."""
    meta = model.meta
    layout = model.layouts.entity(entity)
    table = _table_layout(meta, entity)
    storage_view = storage_layout_view(meta).entity(entity)
    if storage_view is None:  # pragma: no cover - every materialized concrete owns rows
        raise AssertionError(f"{entity.canonical}: no storage layout view")
    contracts = {
        contract.attribute.identity: contract for contract in compiled.attribute_reads(entity)
    }
    projected = frozenset(member.storage.name for member in compiled.projected_documents)
    row: dict[str, object] = {}
    residents = storage_view.document_residents
    document = (
        {}
        if residents is None
        else cast(
            "dict[str, DocumentValue]",
            fixture_document(residents.shape, spec.values, preserve_unknown=False),
        )
    )
    for attribute in layout.attributes:
        if not isinstance(table.placement(attribute.identity), DirectColumn):
            continue
        contract = contracts[attribute.identity]
        raw = spec.values.get(attribute.identity.name)
        scalar = (
            fixture_literal(attribute.type, raw)
            if attribute.identity.name in spec.values and raw is not None
            else None
        )
        row[contract.result_key] = (
            encode_leaf(attribute.type, scalar)
            if contract.encoded and scalar is not None
            else scalar
        )
    for occurrence in layout.occurrences:
        if occurrence.storage.name not in projected or not isinstance(
            table.placement(occurrence.identity), DirectColumn
        ):
            continue
        name = occurrence.identity.path[-1]
        raw = spec.values.get(name)
        row[occurrence.storage.name] = (
            PresentDocument(
                _occurrence_value(occurrence_shape(occurrence), occurrence.multiplicity, raw)
            )
            if name in spec.values and raw is not None
            else SQL_NULL
        )
    discriminator = _discriminator(meta, entity)
    if discriminator is not None and len(compiled.resolved_position) > 1:
        row[discriminator[0]] = discriminator[1]
    column = compiled.structured_column
    if column is not None:
        row[column] = PresentDocument(document)
    return tuple(row.get(result_key) for result_key in compiled.result_keys)


def driver_rows(
    layout: Layout,
    model: CatalogedModel,
    compiled: CompiledRead,
    attach_key: str,
    owners: int = OWNERS,
    first: int = 0,
) -> list[Row]:
    """Every row one level's statement returns for ``owners`` root objects
    beginning at ``first``, keyed by that statement's own result keys.

    Values come only from ``layout``'s catalog row descriptors. ``first`` moves
    the generated fixture's whole key range, so non-overlapping ranges share no
    key or composed row."""
    meta = model.meta
    return [
        _driver_row(model, compiled, _identity(meta, spec.entity), spec)
        for spec in _specs(layout, attach_key, owners, first)
    ]


def rows_per_level(
    layout: Layout,
    model: CatalogedModel,
    plan: ReadPlan,
    reads: Sequence[CompiledRead | None],
    owners: int = OWNERS,
    first: int = 0,
) -> tuple[tuple[Row, ...], ...]:
    """Every level's rows, indexed as :func:`compiled_levels` indexes its reads."""
    root = reads[0]
    assert root is not None
    rows: list[tuple[Row, ...]] = [tuple(driver_rows(layout, model, root, _ROOT, owners, first))]
    for index in range(plan.fetch_count):
        compiled = reads[index + 1]
        rows.append(
            ()
            if compiled is None
            else tuple(
                driver_rows(
                    layout,
                    model,
                    compiled,
                    _attach_key(plan, plan.fetch_step(index)),
                    owners,
                    first,
                )
            )
        )
    return tuple(rows)


# --------------------------------------------------------------------------- #
# The batch: production's own read loop over a provider-free port.            #
# --------------------------------------------------------------------------- #


class StressPort(ConnectsAsItself):
    """Provider-free stored rows for one batch, answered by statement.

    Every level's rows are composed with the port, so a statement executed
    inside a measured window costs that window a fresh list of them and nothing
    else the port does.
    """

    dialect: Dialect = POSTGRES
    __slots__ = ("_rows",)
    _rows: Mapping[str, tuple[Row, ...]]

    def __init__(self, reads: Sequence[CompiledRead | None], rows: Sequence[Sequence[Row]]) -> None:
        answers: dict[str, tuple[Row, ...]] = {}
        for read, level_rows in zip(reads, rows, strict=True):
            if read is None:
                continue
            sql = self.dialect.to_driver_sql(read.statement.sql)
            if sql in answers:  # pragma: no cover - every level reads a distinct statement
                raise AssertionError(f"two levels issue one statement: {sql}")
            answers[sql] = tuple(level_rows)
        self._rows = answers

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del binds, document_reads
        return list(self._rows[sql])

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


_MATERIALIZER: Final = PageReader()


def read_root(
    model: CatalogedModel, validated: ResolvedObjectQuery, plan: ReadPlan, port: StressPort
) -> _RootRead:
    """``plan``'s root statement executed on ``port`` and held for one Page build."""
    return _MATERIALIZER._read_root(  # pyright: ignore[reportPrivateUsage]
        validated,
        model,
        port,
        calls=INERT,
        planner=UNCACHED_READ_PLANNER,
        plan=plan,
    )


def build_page(
    model: CatalogedModel, root: _RootRead, port: StressPort
) -> EagerPageResult[ReadOrigin]:
    """One whole Page built from an executed ``root``: its rows converted, every
    fetch rendered, executed on ``port``, converted, and attached, and the Page's
    read sources retained. ``root`` is consumed."""
    return _MATERIALIZER._build_page(  # pyright: ignore[reportPrivateUsage]
        root,
        model,
        port,
        origins=ObservedPageProjections(model.meta, ledger=None, scanned=False),
        calls=INERT,
    )


def batch(
    model: CatalogedModel, validated: ResolvedObjectQuery, plan: ReadPlan, port: StressPort
) -> EagerPageResult[ReadOrigin]:
    """One whole standalone find of ``validated`` over ``port``."""
    return build_page(model, read_root(model, validated, plan, port), port)


# --------------------------------------------------------------------------- #
# What the workload claims about itself.                                       #
# --------------------------------------------------------------------------- #


def _identity(model: Metamodel, name: str) -> EntityIdentity:
    metadata = entity_by_name(model, name)
    assert metadata is not None, name
    return metadata.identity


def _table_layout(model: Metamodel, entity: EntityIdentity) -> TableLayout:
    view = storage_layout_view(model).entity(entity)
    assert view is not None, entity
    return view.layout


def _discriminator(model: Metamodel, entity: EntityIdentity) -> tuple[str, str] | None:
    view = storage_layout_view(model).entity(entity)
    assert view is not None, entity
    assignment = view.discriminator
    return None if assignment is None else (assignment.slot.column.name, assignment.value)


def _leaf_types(shape: MemberShape) -> set[str]:
    reached: set[str] = set()
    for member in shape.members:
        match member:
            case Leaf(type=neutral_type):
                reached.add(type(neutral_type).__name__)
            case Occurrence(shape=nested):
                reached |= _leaf_types(nested)
    return reached


def _declared_types(layouts: Iterable[EntityLayout]) -> set[str]:
    reached: set[str] = set()
    for layout in layouts:
        reached |= {type(attribute.type).__name__ for attribute in layout.attributes}
        for occurrence in layout.occurrences:
            reached |= _leaf_types(occurrence_shape(occurrence))
    return reached


DECLARABLE_TYPES: Final = frozenset(
    {
        "Boolean",
        "Int32",
        "Int64",
        "Float32",
        "Float64",
        "String",
        "Decimal",
        "Bytes",
        "Date",
        "Time",
        "Timestamp",
        "Uuid",
    }
)
"""Every Neutral Type an Entity or Value Object declaration can name. ``Json`` is
absent: no Python annotation denotes it, so a class-backed model declares none."""


def verify(model: CatalogedModel, plan: ReadPlan, page: Page) -> None:
    """That the fixture-authored batch has the stated shape and no data issues."""
    rows = page_rows(page)
    assert len(rows.layouts) == PROJECTIONS_PER_BATCH, len(rows.layouts)
    assert len(rows.roots) == OWNERS, len(rows.roots)
    assert plan.fetch_count == 4, plan.fetch_count
    for projection, member_row in enumerate(rows.member_rows):
        assert ABSENT not in member_row, rows.layouts[projection].concrete
        assert rows.issues[projection] == (), rows.layouts[projection].concrete
    reached = _declared_types(
        model.layouts.entity(_identity(model.meta, name)) for name in ("Alpha", "Beta", "Owner")
    )
    assert reached >= DECLARABLE_TYPES, DECLARABLE_TYPES - reached
