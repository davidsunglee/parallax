"""The production Snapshot materialization workload, under both storage layouts.

One representative graph shape — a table-per-hierarchy family with an abstract
middle, nested One and Many Value Objects at two depths, every declarable Neutral
Type as an Entity Attribute and again as a document leaf, duplicate logical nodes
through a narrowed view, three view slots and a back-reference — driven through
the SHIPPED read loop from ``PreparedRead.materialize`` to ``GraphBuilder.seal``,
with no database anywhere.

The loop is the driver's own: :func:`batch` calls ``handle/_read.py``'s private
helpers rather than copying them, so what it measures is the code a ``find``
runs. What it cannot borrow is the interleaving — a child level's ``compile_read``
runs between gathering its parents' keys and converting its rows, so a repeated
batch would compile once per repetition. Compilation and the binding that
follows it therefore happen once, outside the batch, against the keys this
module's own fixture is built from; the gather still runs inside it, because
production pays for it per batch.

A fourth workload model rather than a reuse: ``tools/snapshot_graph_overhead.py``
is ``Columns``-only and declares four Neutral Types, ``_document_layout_support``
is a layout twin at the accepted-Metamodel level with no ``DomainModel`` for
``prepare_model`` to prepare, and ``test_snapshot_graph_retention.py``'s workload
is the frozen cost item. The members are declared once, in a factory over the
layout, which is why the two layouts are two namespaces rather than two
transcriptions.

Rows are synthesized from the compiled read itself — one value per Attribute
contract, one document per projected occurrence, each leaf in the codec's own
canonical spelling and each member placed where ``m-storage-layout`` says it
lives — so the fixture cannot drift from what the statement projects.
:func:`verify` is what states that: a conforming batch, every member position
filled, and every declarable Neutral Type reached.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal as PyDecimal
from functools import cache
from typing import Final, Literal, cast

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
from parallax.core.base import (
    Boolean,
    Bytes,
    Date,
    Decimal,
    DocumentValue,
    Float64,
    Int64,
    Json,
    NeutralType,
    PresentDocument,
    String,
    Time,
    Timestamp,
    Uuid,
)
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.document_codec import (
    DocumentShape,
    Leaf,
    Occurrence,
    encode_leaf,
    occurrence_shape,
)
from parallax.core.entity._layout import CatalogedModel, EntityLayout
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
    Multiplicity,
    entity_by_name,
)
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.sql_gen._compile import CompiledRead, MaterializedReadRow, compile_read
from parallax.core.storage_layout import DirectColumn, TableLayout
from parallax.core.storage_layout import view as storage_layout_view
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle import _read
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._retention import ObservedRows
from parallax.snapshot.materialize import SnapshotGraph
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder, graph_rows
from parallax.snapshot.materialize._prepared import PreparedRead, bind
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

__all__ = [
    "LAYOUTS",
    "OWNERS",
    "PROJECTIONS_PER_BATCH",
    "ROWS_PER_BATCH",
    "Layout",
    "batch",
    "compiled_levels",
    "driver_rows",
    "fetch_plan",
    "metamodel",
    "prepared_levels",
    "query",
    "rows_per_level",
    "verify",
    "workload",
]

type Layout = Literal["columns", "document"]

LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
"""Every storage layout the workload is measured under, in report order."""

OWNERS: Final = 8
FANOUT: Final = 4
DUPLICATES: Final = 2
"""Root objects per batch, children per root, and how many of those children a
narrowed view converts a second time."""

NESTED: Final = 2
"""Elements a Many occurrence carries, at every depth."""

PROJECTIONS_PER_BATCH: Final = OWNERS * (1 + FANOUT + DUPLICATES + 1)
"""Converted rows per batch: each root, its children, the narrowed duplicates,
and the to-one hop that re-converts one child."""

ROWS_PER_BATCH: Final = PROJECTIONS_PER_BATCH
"""Stored rows per batch. Equal to the projection count because every row of a
conforming batch converts, which :func:`verify` is what states."""

_PIN: Final = Pin()
_EPOCH: Final = dt.date(2026, 1, 1)
_INSTANT: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)

_ROOT: Final = ""
_NODES: Final = "nodes"
_NARROWED: Final = "special[Alpha]"
_FAVORITE: Final = "favorite"


# --------------------------------------------------------------------------- #
# The model, declared once over the layout.                                    #
# --------------------------------------------------------------------------- #


def _entity_classes(layout: Layout) -> tuple[type[Entity], ...]:
    namespace = f"snapshot.materialization.{layout}"
    placement = Document(column="payload") if layout == "document" else None

    class Detail(ValueObject):
        """The deepest nested Value Object."""

        note: Attr[str | None]
        depth: Attr[int | None] = attr(type=Int32)
        marked: Attr[bool | None]

    class Tag(ValueObject):
        """One leaf of every declarable Neutral Type, a nested One, and a nested
        Many — so a document reaches every codec row at two depths."""

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
        """The family root: one Attribute of every declarable Neutral Type, a
        top-level One occurrence, a top-level Many, and the back reference."""

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
        """The abstract middle a narrowed view resolves through."""

        rank: Attr[int | None] = attr(type=Int32)

    class Alpha(Special, namespace=namespace, inheritance=ConcreteSubtype(tag_value="alpha")):
        """The concrete reached both broadly and through the narrowed view, which
        is what gives the batch its duplicate projections."""

    class Beta(Node, namespace=namespace, inheritance=ConcreteSubtype(tag_value="beta")):
        """The family's other concrete, reached broadly alone."""

        weight: Attr[float | None]

    class Owner(
        Entity,
        table="materialization_owner",
        namespace=namespace,
        layout=placement,
    ):
        """The root of every batch, carrying the three view slots: a broad
        to-many, a narrowed to-many, and a to-one into the same family."""

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
    return DomainModel(*_entity_classes(layout))


@cache
def metamodel(layout: Layout) -> Metamodel:
    """``layout``'s accepted Metamodel, formed outside every measured window."""
    return model_of(workload(layout))


def query(model: Metamodel) -> ValidatedObjectQuery:
    """The read every batch runs: three includes off the root and one
    back-reference revisiting it."""
    return preflight(
        deserialize_query(
            {
                "target": "Owner",
                "predicate": {"all": {}},
                "includes": [
                    {"segments": [{"rel": "Owner.nodes"}]},
                    {"segments": [{"rel": "Owner.special", "narrowTo": ["Alpha"]}]},
                    {"segments": [{"rel": "Owner.favorite"}]},
                    {"segments": [{"rel": "Owner.nodes"}, {"rel": "Node.owner"}]},
                ],
            }
        ),
        model=model,
        form="graph",
    )


def fetch_plan(validated: ValidatedObjectQuery, model: Metamodel) -> deep_fetch.ObjectQueryPlan:
    """``validated``'s plan, projecting every member as an instance-form read does."""
    return deep_fetch.plan(
        validated, model, projection=deep_fetch.ReadProjectionRequest("all", True)
    )


def compiled_levels(
    plan: deep_fetch.ObjectQueryPlan, model: Metamodel
) -> tuple[CompiledRead | None, ...]:
    """One compiled read per source level: the root at 0, plan level ``i`` at
    ``i + 1``, and absence for the back-reference level, which issues no statement.

    Each child level is compiled against the keys this module's fixture supplies,
    which is what lets the batch be repeated without recompiling.
    """
    reads: list[CompiledRead | None] = [
        compile_read(plan.root, model, POSTGRES, result_form="instance")
    ]
    for level in plan.levels:
        if level.is_back_reference:
            reads.append(None)
            continue
        reads.append(
            compile_read(
                level.query_for(_level_keys(level.attach_key)),
                model,
                POSTGRES,
                result_form="instance",
            )
        )
    return tuple(reads)


def prepared_levels(
    model: CatalogedModel, reads: Sequence[CompiledRead | None]
) -> tuple[PreparedRead[MaterializedReadRow] | None, ...]:
    """One prepared read per compiled one, indexed as :func:`compiled_levels`
    indexes its reads.

    Bound outside the repeated batch for the same reason compilation is: a
    production level binds where it compiles, once per statement, so a batch
    repeated against reads compiled before it must be repeated against the
    levels bound with them.
    """
    return tuple(None if read is None else bind(model, read) for read in reads)


# --------------------------------------------------------------------------- #
# The fixture: which rows each level returns, and what each one holds.         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _RowSpec:
    """One stored row: the concrete Entity it resolves to, the join values it
    carries, and the seed every other member's value is derived from."""

    entity: str
    joins: Mapping[str, object]
    seed: int


def _owner_id(index: int) -> int:
    return 1_000 + index


def _node_id(index: int, offset: int) -> int:
    return 10_000 + index * 10 + offset


def _node_spec(index: int, offset: int) -> _RowSpec:
    node = _node_id(index, offset)
    return _RowSpec(
        entity="Alpha" if offset < DUPLICATES else "Beta",
        joins={"id": node, "ownerId": _owner_id(index)},
        seed=node,
    )


def _specs(attach_key: str, owners: int, first: int) -> tuple[_RowSpec, ...]:
    indices = range(first, first + owners)
    if attach_key == _ROOT:
        return tuple(
            _RowSpec(
                entity="Owner",
                joins={"id": _owner_id(index), "favoriteId": _node_id(index, 0)},
                seed=_owner_id(index),
            )
            for index in indices
        )
    if attach_key == _NODES:
        return tuple(_node_spec(index, offset) for index in indices for offset in range(FANOUT))
    if attach_key == _NARROWED:
        return tuple(_node_spec(index, offset) for index in indices for offset in range(DUPLICATES))
    if attach_key == _FAVORITE:
        return tuple(_node_spec(index, 0) for index in indices)
    return ()


def _level_keys(attach_key: str) -> list[object]:
    """The distinct parent keys a level's statement binds, as the fixture fixes
    them — what the batch's own ``_gather_keys`` answers.

    Always the whole fixture's keys, whatever a caller then converts: a statement
    is compiled once and its binds are not what a row materializes under."""
    if attach_key == _FAVORITE:
        return [_node_id(index, 0) for index in range(OWNERS)]
    return [_owner_id(index) for index in range(OWNERS)]


def _managed(neutral_type: NeutralType, seed: int) -> object:
    """One conforming value of ``neutral_type``, fixed by ``seed``."""
    match neutral_type:
        case Boolean():
            return seed % 2 == 0
        case Int32():
            return seed % 2_000
        case Int64():
            return seed * 7
        case Float32():
            return float(seed % 64) + 0.5
        case Float64():
            return float(seed % 1_024) + 0.25
        case String():
            return f"text-{seed}"
        case Decimal(precision=precision, scale=scale):
            whole = seed % 10 ** (precision - scale)
            fraction = f"{seed % 10**scale:0{scale}d}" if scale else ""
            return PyDecimal(f"{whole}.{fraction}" if scale else f"{whole}")
        case Bytes():
            return bytes((seed % 251, (seed * 3) % 251, 7))
        case Date():
            return _EPOCH + dt.timedelta(days=seed % 900)
        case Time():
            return dt.time(seed % 24, seed % 60, (seed * 7) % 60)
        case Timestamp():
            return _INSTANT + dt.timedelta(seconds=seed % 86_400)
        case Uuid():
            return uuid.UUID(int=seed)
        case Json():
            return {"seed": seed}


def _document(shape: DocumentShape, seed: int) -> dict[str, DocumentValue]:
    """One conforming document of ``shape``, every leaf in its canonical spelling."""
    document: dict[str, DocumentValue] = {}
    for position, member in enumerate(shape.members):
        match member:
            case Leaf(name=name, type=neutral_type):
                document[name] = cast(
                    "DocumentValue",
                    encode_leaf(neutral_type, _managed(neutral_type, seed + position)),
                )
            case Occurrence(name=name, multiplicity=multiplicity, shape=nested):
                document[name] = (
                    [_document(nested, seed + position + element) for element in range(NESTED)]
                    if multiplicity is Multiplicity.MANY
                    else _document(nested, seed + position)
                )
    return document


def _driver_row(
    model: CatalogedModel, compiled: CompiledRead, entity: EntityIdentity, spec: _RowSpec
) -> Row:
    """One stored row as the driver answers it: direct Columns under their own
    result keys, and every document-resident member inside the Structured Column."""
    meta = model.meta
    layout = model.layouts.entity(entity)
    table = _table_layout(meta, entity)
    contracts = {
        contract.attribute.identity: contract for contract in compiled.attribute_reads(entity)
    }
    projected = frozenset(member.storage.name for member in compiled.projected_documents)
    row: dict[str, object] = {}
    document: dict[str, DocumentValue] = {}
    for attribute in layout.attributes:
        contract = contracts[attribute.identity]
        scalar = spec.joins.get(
            attribute.identity.name, _managed(attribute.type, spec.seed + len(row))
        )
        if isinstance(table.placement(attribute.identity), DirectColumn):
            row[contract.result_key] = (
                encode_leaf(attribute.type, scalar) if contract.encoded else scalar
            )
        else:
            document[attribute.identity.name] = cast(
                "DocumentValue", encode_leaf(attribute.type, scalar)
            )
    for occurrence in layout.occurrences:
        if occurrence.storage.name not in projected:
            continue
        shape = occurrence_shape(occurrence)
        occurrence_value: DocumentValue = (
            [_document(shape, spec.seed + element) for element in range(NESTED)]
            if occurrence.multiplicity is Multiplicity.MANY
            else _document(shape, spec.seed)
        )
        if isinstance(table.placement(occurrence.identity), DirectColumn):
            row[occurrence.storage.name] = PresentDocument(occurrence_value)
        else:
            document[occurrence.identity.path[-1]] = occurrence_value
    discriminator = _discriminator(meta, entity)
    if discriminator is not None and len(compiled.resolved_position) > 1:
        row[discriminator[0]] = discriminator[1]
    column = compiled.structured_column
    if column is not None:
        row[column] = PresentDocument(document)
    return row


def driver_rows(
    model: CatalogedModel,
    compiled: CompiledRead,
    attach_key: str,
    owners: int = OWNERS,
    first: int = 0,
) -> list[Row]:
    """Every row one level's statement returns for ``owners`` root objects
    beginning at ``first``, keyed by that statement's own result keys.

    ``first`` moves the whole tree's keys and every value seeded from them, so
    two ranges that do not overlap share no key, no composed row, and no value of
    a Neutral Type whose domain the earlier range did not cover. ``Boolean`` is
    the one type it does cover: :func:`_managed` answers it from ``seed % 2``, and
    every range carries both parities. The other modular domains are SAMPLED
    rather than exhausted — a range's seeds are scattered rather than contiguous,
    so a further range still carries ``Float32`` and ``Time`` values the earlier
    one did not. That is what lets a caller hand a warmed process rows it has
    never decoded, and what bounds the claim to rows rather than to every value in
    one."""
    meta = model.meta
    return [
        _driver_row(model, compiled, _identity(meta, spec.entity), spec)
        for spec in _specs(attach_key, owners, first)
    ]


def rows_per_level(
    model: CatalogedModel,
    plan: deep_fetch.ObjectQueryPlan,
    reads: Sequence[CompiledRead | None],
    owners: int = OWNERS,
    first: int = 0,
) -> tuple[tuple[Row, ...], ...]:
    """Every level's rows, indexed as :func:`compiled_levels` indexes its reads."""
    root = reads[0]
    assert root is not None
    rows: list[tuple[Row, ...]] = [tuple(driver_rows(model, root, _ROOT, owners, first))]
    for index, level in enumerate(plan.levels):
        compiled = reads[index + 1]
        rows.append(
            ()
            if compiled is None
            else tuple(driver_rows(model, compiled, level.attach_key, owners, first))
        )
    return tuple(rows)


# --------------------------------------------------------------------------- #
# The batch: the shipped per-level loop, with compilation lifted out of it.    #
# --------------------------------------------------------------------------- #

_slot_table = _read._slot_table  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_convert_rows = _read._convert_rows  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_parent_refs = _read._parent_refs  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_guarded_parents = _read._guarded_parents  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_gather_keys = _read._gather_keys  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_correlation_member = _read._correlation_member  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_attach_children = _read._attach_children  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_attach_empty = _read._attach_empty  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied
_attach_back_reference = _read._attach_back_reference  # pyright: ignore[reportPrivateUsage] - the shipped loop's own helper, driven rather than copied


def batch(
    model: CatalogedModel,
    plan: deep_fetch.ObjectQueryPlan,
    prepared: Sequence[PreparedRead[MaterializedReadRow] | None],
    rows: Sequence[Sequence[Row]],
) -> SnapshotGraph:
    """One whole graph, built the way ``build_graph`` builds one.

    The root statement's rows are materialized WHOLE before the loop opens and
    held until it closes, as ``read_roots`` materializes them and as the read it
    answers holds them; a level below the root converts straight out of its own
    lazy materialization and holds one row at a time.

    Each level's gathered keys decide its branch and stay live across the
    conversion beneath them, which is the compiled child query holding them in
    production. An empty gathered set is the only thing that attaches an empty
    result: a level with keys and no rows converts the empty result and fans it
    back, exactly as a child statement returning nothing does.
    """
    meta = model.meta
    root = prepared[0]
    assert root is not None
    root_rows = tuple(map(root.materialize, rows[0]))
    builder = GraphBuilder(ViewSchema(_slot_table(plan)))
    observations = ObservedRows()
    root_refs = _convert_rows(builder, ROOT_LEVEL, root, root_rows, observations)
    level_refs: list[tuple[int, ...]] = []
    for index, level in enumerate(plan.levels):
        parents = _guarded_parents(
            builder, level, _parent_refs(level.parent, root_refs, level_refs)
        )
        if level.is_back_reference:
            _attach_back_reference(builder, meta, level, parents)
            level_refs.append(())
            continue
        keys = _gather_keys(builder, parents, _correlation_member(meta, level.owner.identity))
        if not keys:
            _attach_empty(builder, level, parents)
            level_refs.append(())
            continue
        level_read = prepared[index + 1]
        assert level_read is not None
        child_refs = _convert_rows(
            builder,
            index + 1,
            level_read,
            map(level_read.materialize, rows[index + 1]),
            observations,
        )
        _attach_children(builder, meta, level, parents, child_refs)
        level_refs.append(child_refs)
    return builder.seal(root_refs, _PIN)


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


def _leaf_types(shape: DocumentShape) -> set[str]:
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


def verify(model: CatalogedModel, plan: deep_fetch.ObjectQueryPlan, graph: SnapshotGraph) -> None:
    """That the batch measured is the one described: the stated shape, every
    member position filled from the stored row, and no stored-data issue anywhere.

    A row whose keys did not match what the statement projected would leave
    ``ABSENT`` positions or raise an issue, so this is also what holds the
    synthesized fixture to the compiled projection.
    """
    rows = graph_rows(graph)
    assert len(rows.layouts) == PROJECTIONS_PER_BATCH, len(rows.layouts)
    assert len(rows.roots) == OWNERS, len(rows.roots)
    assert len(plan.levels) == 4, len(plan.levels)
    for projection, member_row in enumerate(rows.member_rows):
        assert ABSENT not in member_row, rows.layouts[projection].concrete
        assert rows.issues[projection] == (), rows.layouts[projection].concrete
    reached = _declared_types(
        model.layouts.entity(_identity(model.meta, name)) for name in ("Alpha", "Beta", "Owner")
    )
    assert reached >= DECLARABLE_TYPES, DECLARABLE_TYPES - reached
