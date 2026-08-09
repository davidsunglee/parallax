"""The neutral row-assembly record the corpus ``read (graph)`` lane grades.

A graded graph observation is **row-shaped and per-projection**: one logical row
reached through two projections is graded twice, each time under the exact
physical columns that projection emitted — including a sibling concrete's own
null-padded columns, which the resolved concrete does not declare. :class:`Node`
is that wire: four separate physical-key namespaces (scalar columns, decoded
Value Object documents under their storage keys, relationship attachments under
their view keys, and the synthetic ``familyVariant`` spelling) so a Value Object
storage key may equal a relationship name without either overwriting the other,
plus the declared primary-key columns a back-reference cycle truncates to.

:func:`find` and :func:`find_history` are the lane's own executors: they compile
and execute one statement per non-empty level through the injected ``m-db-port``
and assemble the observed rows, so the corpus keeps grading the class-free
compile → execute → wire spine rather than a language-specific object graph. The
developer-facing read path is graded by the API Conformance suite instead.

Every row this module assembles arrives with the provenance its own compiled
read decided — the resolved position, each row's resolved concrete Entity, its
``familyVariant`` spelling, and the document contributors — so nothing here
re-derives what the projection already settled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from parallax.core import deep_fetch, inheritance, op_algebra
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import Dialect
from parallax.core.document_codec import (
    LeafEncodingError,
    occurrence_shape,
    reduce_declared_members,
)
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    TablePerConcreteSubtype,
    TemporalDimension,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.sql_gen import CompiledRead, LoweredStatement, MaterializedReadRow, compile_read
from parallax.core.temporal_read import Edge, milestone_edge
from parallax.snapshot.handle import ExecutedStatement, Execution

__all__ = [
    "AssembledFind",
    "AssembledHistory",
    "AssembledMilestone",
    "Assembler",
    "AssemblyError",
    "Node",
    "find",
    "find_history",
]

_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

_IdentityKey = tuple[EntityIdentity, tuple[object, ...]]


class AssemblyError(ValueError):
    """The lane cannot assemble a row or resolve a back-reference."""


def _new_field_map() -> dict[str, object]:
    return {}


@dataclass(slots=True)
class Node:
    """One neutral, class-free graph node keyed entirely by physical names.

    ``fields`` holds scalar column values, ``value_objects`` the decoded
    documents under their storage keys, ``relationships`` one attachment per
    attached level under that level's own view key, and ``family_variant`` the
    synthetic polymorphic spelling. Absence from ``relationships`` IS the
    closed-world "not loaded" state, never a sentinel value. ``pk_columns``
    names the declared primary-key columns among ``fields``, in declaration
    order — what a back-reference cycle renders as its primary-key-only stub.

    ``resolved_entity`` is the row's own concrete Entity Identity, which a
    table-per-concrete-subtype read resolving to exactly one concrete carries
    nowhere else: that read emits no ``familyVariant`` column at all. It is
    bookkeeping rather than wire state, and ``None`` only for a node built
    outside :class:`Assembler`.
    """

    fields: dict[str, object]
    pk_columns: tuple[str, ...]
    resolved_entity: EntityIdentity | None = None
    value_objects: dict[str, object] = field(default_factory=_new_field_map)
    relationships: dict[str, object] = field(default_factory=_new_field_map)
    family_variant: str | None = None


def _entity(meta: Metamodel, name: str) -> EntityMetadata:
    """The accepted Metadata a bare-or-canonical Entity spelling names, resolved
    by :func:`~parallax.core.metamodel.entity_by_name`'s ambiguity-rejecting
    rule. Raises :class:`KeyError` when the model declares no such Entity."""
    entity = entity_by_name(meta, name)
    if entity is None:  # pragma: no cover - a level target always names a declared Entity
        raise KeyError(name)
    return entity


def _family_root(meta: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    """``entity``'s family root, which for a standalone Entity is itself: the
    primary key and the as-of axes alike are family-wide metadata declared only
    there."""
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity
    root = meta.entity(position.root)
    return entity if root is None else root


def _declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _identity_key(
    meta: Metamodel, resolved: EntityIdentity, row: Mapping[str, object]
) -> _IdentityKey:
    """One row's graph-local identity: ``(family-normalized identity, primary-key
    values)``.

    Family-normalized, so the same physical row reached through a broad and a
    narrowed projection resolves to one key. Table-per-concrete-subtype is the
    exception: each concrete owns its own table with its own primary-key
    namespace, so normalizing to the family root would conflate two different
    physical rows that merely share a key value — the row's own resolved
    concrete is the identity there.

    The as-of coordinate the core identity triple names is omitted: every node
    of one assembled graph shares the same whole-graph pin, so it can never
    distinguish two rows here.
    """
    view = inheritance.view(meta).entity(resolved)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return (resolved, ())
    declaring = meta.entity(view.root)
    if declaring is None:  # pragma: no cover - a family root is always accepted
        return (resolved, ())
    pk_attrs = _declared_primary_key(declaring)
    identity = (
        resolved if isinstance(view.strategy, TablePerConcreteSubtype) else declaring.identity
    )
    return (identity, tuple(row[attr.storage.name] for attr in pk_attrs))


def _pk_columns(meta: Metamodel, entity: EntityMetadata) -> tuple[str, ...]:
    return tuple(attr.storage.name for attr in _declared_primary_key(_family_root(meta, entity)))


def _decode_element(raw: object, container: _VoContainer) -> dict[str, object] | None:
    """Decode one ``one``-shaped Value Object document (or array element) to its
    declared shape: a non-mapping — SQL NULL, JSON null, a non-object scalar —
    collapses to ``None``, the whole composite absent, never a partial dict. An
    absent or JSON-null leaf is that member's own not-present state."""
    try:
        reduced = reduce_declared_members(
            occurrence_shape(container), raw, collapse_invalid_occurrences=True
        )
    except LeafEncodingError as exc:
        identity = container.identity
        member = ".".join(identity.path)
        raise AssemblyError(
            f"{identity.entity.canonical}.{member}.{exc} — invalid stored data"
        ) from exc
    return cast("dict[str, object] | None", reduced)


def _decode_many(raw: object, container: _VoContainer) -> list[dict[str, object] | None]:
    """Decode a ``many``-multiplicity member: a non-list collapses to an EMPTY
    list — never a nullability violation, per the array-absence rule."""
    if not isinstance(raw, list):
        return []
    items = cast("list[object]", raw)
    return [_decode_element(item, container) for item in items]


def _decode_value_object(raw: object, vo: ValueObjectMetadata) -> object:
    if vo.multiplicity is Multiplicity.MANY:
        return _decode_many(raw, vo)
    return _decode_element(raw, vo)


def _decode_row_parts(
    row: Mapping[str, object], documents: Sequence[ValueObjectMetadata]
) -> tuple[dict[str, object], dict[str, object]]:
    """Split one row into its scalar and Value Object contributors, preserving
    each side's own provenance."""
    vo_columns = {vo.storage.name for vo in documents}
    fields = {key: value for key, value in row.items() if key not in vo_columns}
    decoded = {
        vo.storage.name: _decode_value_object(row.get(vo.storage.name), vo) for vo in documents
    }
    return fields, decoded


def _new_identity_map() -> dict[_IdentityKey, Node]:
    return {}


@dataclass(slots=True)
class Assembler:
    """One graph's builder: an identity-keyed node registry plus per-level row
    decoding and fan-back.

    Never reused across graphs — graph-local identity resolution promises no
    same-node reuse beyond one graph. The first node registered under a key is
    the one every later back-reference to that row resolves to; a duplicate
    projection still decodes its own node, because the lane grades each
    projection's own wire.
    """

    meta: Metamodel
    _identity: dict[_IdentityKey, Node] = field(default_factory=_new_identity_map)

    def materialize_root(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        *,
        resolved_entities: Sequence[EntityIdentity],
        family_variants: Sequence[str | None],
        documents: Sequence[ValueObjectMetadata],
    ) -> list[Node]:
        """Decode the root query's own rows into fresh, identity-registered nodes."""
        return self._materialize(
            entity_name,
            rows,
            resolved_entities=resolved_entities,
            family_variants=family_variants,
            documents=documents,
        )

    def attach_level(
        self,
        level: deep_fetch.FetchLevel,
        parent_nodes: Sequence[Node],
        parent_rows: Sequence[Mapping[str, object]],
        child_rows: Sequence[Mapping[str, object]] | None,
        *,
        resolved_entities: Sequence[EntityIdentity] = (),
        family_variants: Sequence[str | None] = (),
        documents: Sequence[ValueObjectMetadata] = (),
    ) -> list[Node]:
        """Attach one level's children to ``parent_nodes`` under its own view
        key; returns that level's own child nodes — the parent nodes of any
        level attaching beneath it, and empty for a back-reference or an empty
        level.

        ``child_rows`` is ``None`` exactly when the level's gathered parent-key
        set was empty, so no child SQL ran and every parent receives the
        empty/null relationship result. A back-reference level receives no rows
        at all: each parent's gathered key resolves against the identity map.
        """
        if level.is_back_reference:
            return self._attach_back_reference(level, parent_nodes, parent_rows)
        if child_rows is None:
            empty: object = [] if level.to_many else None
            for node in parent_nodes:
                node.relationships[level.attach_key] = empty
            return []
        assert level.child_target is not None
        assert level.related is not None
        child_nodes = self._materialize(
            level.child_target,
            child_rows,
            resolved_entities=resolved_entities,
            family_variants=family_variants,
            documents=documents,
        )
        buckets: dict[object, list[Node]] = {}
        for row, node in zip(child_rows, child_nodes, strict=True):
            buckets.setdefault(row[level.related.column], []).append(node)
        for row, node in zip(parent_rows, parent_nodes, strict=True):
            matched = buckets.get(row[level.owner.column], [])
            node.relationships[level.attach_key] = (
                matched if level.to_many else _one_or_none(matched)
            )
        return child_nodes

    def _attach_back_reference(
        self,
        level: deep_fetch.FetchLevel,
        parent_nodes: Sequence[Node],
        parent_rows: Sequence[Mapping[str, object]],
    ) -> list[Node]:
        assert level.back_reference_family is not None
        for row, node in zip(parent_rows, parent_nodes, strict=True):
            fk = row[level.owner.column]
            if fk is None:
                node.relationships[level.attach_key] = [] if level.to_many else None
                continue
            referenced = self._identity.get((level.back_reference_family, (fk,)))
            if referenced is None:
                raise AssemblyError(
                    f"back-reference {level.attach_key!r}: no already-assembled "
                    f"{level.back_reference_family} node for key {fk!r}"
                )
            node.relationships[level.attach_key] = [referenced] if level.to_many else referenced
        return []

    def _materialize(
        self,
        entity_name: str,
        rows: Sequence[Mapping[str, object]],
        *,
        resolved_entities: Sequence[EntityIdentity],
        family_variants: Sequence[str | None],
        documents: Sequence[ValueObjectMetadata],
    ) -> list[Node]:
        entity = _entity(self.meta, entity_name)
        pk_columns = _pk_columns(self.meta, entity)
        if len(resolved_entities) != len(rows):
            raise AssemblyError("resolved entity count does not match row count")
        if len(family_variants) != len(rows):
            raise AssemblyError("familyVariant count does not match row count")
        nodes: list[Node] = []
        for index, row in enumerate(rows):
            variant = family_variants[index]
            resolved_entity = resolved_entities[index]
            fields, value_objects = _decode_row_parts(row, documents)
            if variant is not None:
                fields.pop("familyVariant", None)
            node = Node(
                fields=fields,
                pk_columns=pk_columns,
                resolved_entity=resolved_entity,
                value_objects=value_objects,
                family_variant=variant,
            )
            self._identity.setdefault(_identity_key(self.meta, resolved_entity, row), node)
            nodes.append(node)
        return nodes


def _one_or_none(matched: list[Node]) -> Node | None:
    return matched[0] if matched else None


@dataclass(frozen=True, slots=True)
class AssembledFind:
    """One graph read's root nodes plus its ordered execution record."""

    nodes: tuple[Node, ...]
    execution: Execution


@dataclass(frozen=True, slots=True)
class AssembledMilestone:
    """One milestone's own edge-pinned root-only graph. ``pin`` maps each
    declared as-of dimension's wire spelling to that milestone's from-instant."""

    pin: Mapping[str, object]
    nodes: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class AssembledHistory:
    """A milestone-set read's ordered graphs plus its single-statement execution."""

    graphs: tuple[AssembledMilestone, ...]
    execution: Execution


def find(
    op: op_algebra.Operation, meta: Metamodel, dialect: Dialect, target: str, port: DbPort
) -> AssembledFind:
    """Assemble one graph: the root query plus one statement per non-empty
    relationship level.

    Each level is the same three steps — compile, execute, materialize — with
    every row's ``familyVariant`` and resolved concrete coming from that level's
    own compiled read. A path-root guard restricts the parents a level gathers
    keys from and attaches to, so an excluded parent never sees the level's view
    key at all. An empty gathered key set issues no child SQL and attaches the
    empty/null result; a back-reference level issues none either, resolving each
    parent's key against the identity map.
    """
    root_entity = _entity(meta, target)
    plan = deep_fetch.plan(root_entity, op, meta)
    statements: list[ExecutedStatement] = []

    root_compiled = compile_read(
        plan.root_operation, meta, dialect, root_entity, result_form="instance"
    )
    root_materialized = _execute_compiled(port, dialect, root_compiled, statements)
    root_rows = [row.values for row in root_materialized]

    assembler = Assembler(meta=meta)
    root_nodes = assembler.materialize_root(
        target,
        root_rows,
        resolved_entities=[row.resolved_entity for row in root_materialized],
        family_variants=[row.family_variant for row in root_materialized],
        documents=root_compiled.documents,
    )

    level_rows: list[Sequence[Row]] = []
    level_nodes: list[list[Node]] = []
    for level in plan.levels:
        parent_rows, parent_nodes = _guarded_parents(
            level, *_parent_data(level.parent, root_rows, root_nodes, level_rows, level_nodes)
        )
        if level.is_back_reference:
            level_nodes.append(assembler.attach_level(level, parent_nodes, parent_rows, None))
            level_rows.append(())
            continue
        keys = _distinct_keys(parent_rows, level.owner.column)
        if not keys:
            level_nodes.append(assembler.attach_level(level, parent_nodes, parent_rows, None))
            level_rows.append(())
            continue
        child_target, child_op = level.child_operation(keys)
        child_compiled = compile_read(
            child_op, meta, dialect, _entity(meta, child_target), result_form="instance"
        )
        child_materialized = _execute_compiled(port, dialect, child_compiled, statements)
        rows = [row.values for row in child_materialized]
        level_nodes.append(
            assembler.attach_level(
                level,
                parent_nodes,
                parent_rows,
                rows,
                resolved_entities=[row.resolved_entity for row in child_materialized],
                family_variants=[row.family_variant for row in child_materialized],
                documents=child_compiled.documents,
            )
        )
        level_rows.append(rows)

    return AssembledFind(nodes=tuple(root_nodes), execution=Execution(tuple(statements)))


def find_history(
    op: op_algebra.Operation, meta: Metamodel, dialect: Dialect, target: str, port: DbPort
) -> AssembledHistory:
    """Assemble a milestone-set read: one statement whose rows partition by their
    own edge into one root-only graph per milestone, ordered chronologically
    (Valid Time first) rather than by the database's unspecified row order."""
    metadata = _entity(meta, target)
    plan = deep_fetch.plan(metadata, op, meta)
    if plan.levels:
        raise AssemblyError(
            "a milestone-set (history / asOfRange) read carries no deep-fetch levels"
        )
    entity = _family_root(meta, metadata)
    compiled = compile_read(plan.root_operation, meta, dialect, metadata, result_form="instance")
    statements: list[ExecutedStatement] = []
    materialized_rows = _execute_compiled(port, dialect, compiled, statements)

    order: list[Edge] = []
    groups: dict[Edge, list[MaterializedReadRow]] = {}
    for row in sorted(materialized_rows, key=lambda row: _edge_sort_key(entity, row.values)):
        edge = milestone_edge(entity, row.values)
        if edge not in groups:
            groups[edge] = []
            order.append(edge)
        groups[edge].append(row)

    graphs = tuple(
        AssembledMilestone(
            pin=_edge_pin(entity, edge),
            nodes=tuple(
                Assembler(meta=meta).materialize_root(
                    target,
                    [row.values for row in groups[edge]],
                    resolved_entities=[row.resolved_entity for row in groups[edge]],
                    family_variants=[row.family_variant for row in groups[edge]],
                    documents=compiled.documents,
                )
            ),
        )
        for edge in order
    )
    return AssembledHistory(graphs=graphs, execution=Execution(tuple(statements)))


def _execute_compiled(
    port: DbPort, dialect: Dialect, compiled: CompiledRead, statements: list[ExecutedStatement]
) -> list[MaterializedReadRow]:
    """Execute one compiled read, materializing its rows through its OWN
    transform, so a root compile and a child compile can never be crossed."""
    return [
        compiled.materialize_row(row)
        for row in _execute(port, dialect, compiled.statement, statements)
    ]


def _execute(
    port: DbPort, dialect: Dialect, statement: LoweredStatement, statements: list[ExecutedStatement]
) -> list[Row]:
    rows = port.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
    statements.append(ExecutedStatement(statement.sql, statement.binds))
    return rows


def _parent_data(
    parent: deep_fetch.ParentRef,
    root_rows: Sequence[Row],
    root_nodes: Sequence[Node],
    level_rows: Sequence[Sequence[Row]],
    level_nodes: Sequence[list[Node]],
) -> tuple[Sequence[Row], Sequence[Node]]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_rows, root_nodes
    return level_rows[parent.index], level_nodes[parent.index]


def _guarded_parents(
    level: deep_fetch.FetchLevel, parent_rows: Sequence[Row], parent_nodes: Sequence[Node]
) -> tuple[Sequence[Row], Sequence[Node]]:
    """The parent rows and nodes a path-root guard admits into ``level``.

    A guard is a source filter, not a view: an excluded parent never sees the
    level's view key at all, which is the closed-world distinction between "no
    such related row" and "this object never participated". Selection is by each
    parent's own resolved concrete Entity, which is what a guard's resolved
    source set enumerates.
    """
    if level.source_position is None:
        return parent_rows, parent_nodes
    admitted = frozenset(level.source_position)
    pairs = [
        (row, node)
        for row, node in zip(parent_rows, parent_nodes, strict=True)
        if node.resolved_entity in admitted
    ]
    return [row for row, _ in pairs], [node for _, node in pairs]


def _distinct_keys(rows: Sequence[Row], column: str) -> list[op_algebra.Scalar]:
    """The distinct non-null values of ``column`` in first-encountered order. The
    gathered set is unordered for grading purposes, so encounter order is as good
    as any and deterministic run to run."""
    values = dict.fromkeys(row[column] for row in rows if row[column] is not None)
    return cast("list[op_algebra.Scalar]", list(values))


# The wire spelling each Temporal Dimension is emitted under in a milestone-set
# graph's pin entry. The dimension itself is structured everywhere above this seam.
_DIMENSION_NAMES: Final[Mapping[TemporalDimension, str]] = {
    TemporalDimension.VALID_TIME: "valid-time",
    TemporalDimension.TRANSACTION_TIME: "transaction-time",
}


def _start_column(entity: EntityMetadata, axis: AsOfAxisMetadata) -> str:
    declared = entity.attribute(axis.start_attribute.name)
    if declared is None:  # pragma: no cover - an accepted axis names a declared Attribute
        raise AssemblyError(
            f"{entity.identity.canonical}: {axis.start_attribute.name} is undeclared"
        )
    return declared.storage.name


def _edge_sort_key(entity: EntityMetadata, row: Row) -> tuple[object, ...]:
    """Valid Time first, then Transaction Time, each dimension's start-column
    value — used only to order a milestone-set read's grouped graphs
    chronologically, never to select or filter rows."""
    ordered = sorted(entity.declared_as_of_axes, key=lambda axis: axis.dimension.value)
    return tuple(row[_start_column(entity, axis)] for axis in ordered)


def _edge_pin(entity: EntityMetadata, edge: Edge) -> dict[str, object]:
    """One milestone's pin entry, keyed by each declared dimension's wire spelling."""
    return {
        _DIMENSION_NAMES[axis.dimension]: (
            edge.valid_time if axis.dimension is TemporalDimension.VALID_TIME else edge.tx_time
        )
        for axis in entity.declared_as_of_axes
    }
