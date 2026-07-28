"""``parallax.snapshot.handle._keyed_sql`` — SQL DML bodies for keyed writes.

The output side of the write-lowering boundary: everything here RENDERS a
:class:`~parallax.core.sql_gen.Statement` (SQL text plus ordered binds) for one
already-decided mutation. The deciding — temporal vs plain, single vs collapsed,
which milestone rows close and which chain — belongs one level up in
:mod:`parallax.snapshot.handle._write_lowering`, which imports this module; the
edge runs dispatch → builders and never back.

Inside the handle package "write" keeps meaning the NEUTRAL instruction level
(`m-unit-work`'s :class:`~parallax.core.unit_work.KeyedWrite`, `_write_types`,
`_write_inputs`, `_write_lowering`); this is the one module named for the SQL
side. It owns the shared column-ordering, key-predicate, and marker/tag-column
discipline every builder reuses, so no form reinvents bind order. Every physical
fact comes from the target's Storage Layout Entity view (`_family.entity_layout`)
— its Table, its Table-ordered applicable slots, and its derived discriminator
assignment. Semantic selections stay where they are decided: the family-effective
primary key (`_family.family_primary_key`) and the version column
(`OptimisticLockFacet`, resolved through `_family`) name Attribute identities,
which this module maps onto layout slots rather than reading storage
declarations of its own.

The same slot selection that fixes a statement's column list also fixes which
buffered rows may share one: `collapse_group_key` answers a row's filtered,
table-ordered selection for the planner's batch grouping, so a collapsed
multi-row instruction is same-shaped before any builder sees it.

The eight builders `_write_lowering` dispatches to are spelled bare, as is
`collapse_group_key` (the composition root and the conformance engine inject
it); the helpers they share among themselves keep their leading underscore
because every one of their call sites is in THIS module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import inheritance, opt_lock
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import Statement, compile_write_predicate
from parallax.core.storage_layout import ColumnContributor, EntityLayoutView
from parallax.core.unit_work import Concurrency, KeyedWrite, Observation, PredicateWrite
from parallax.snapshot.handle._family import (
    assignment_member,
    declaring,
    entity_layout,
    entity_of,
    family_primary_key,
    slot_column,
    version_attribute,
)
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = [
    "collapse_group_key",
    "key_predicate",
    "lower_batched_update",
    "lower_delete",
    "lower_insert",
    "lower_multi_delete",
    "lower_multi_insert",
    "lower_predicate_write",
    "lower_update",
]


# A scalar cell's recognized DB-computed marker kinds (`m-pk-gen`;
# `write-instruction.schema.json#/$defs/writeComputedMarker`): `computed` (the
# `max` strategy's `coalesce(max(col), ?) + ?` INSERT fold) and `increment`
# (a self-referential `col = col + ?` SET advance, e.g. a sequence registry's
# `next_val`). Each is legal only at the mutation that can render it.
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


def _layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView:
    """``entity``'s canonical physical layout selection, or a loud refusal when
    it owns no rows (an abstract family position is never a write target)."""
    view = entity_layout(meta, entity)
    if view is None:
        raise WriteLoweringError(f"{entity.identity.name!r}: write target has no effective table")
    return view


def _table(meta: Metamodel, entity: EntityMetadata) -> str:
    return _layout(meta, entity).layout.table.name


def _tag(meta: Metamodel, entity: EntityMetadata) -> tuple[str, str] | None:
    """``(tag column, tag value)`` for an inheritance-family table-per-hierarchy
    concrete, else ``None`` — the discriminator assignment a keyed write derives
    from the layout's own slot (never authored in the neutral write input)."""
    discriminator = _layout(meta, entity).discriminator
    if discriminator is None:
        return None
    return discriminator.slot.column.name, discriminator.value


def _marker_kind(value: object) -> str | None:
    """A scalar cell's DB-computed marker kind (``computed`` / ``increment``),
    or ``None`` for an ordinary literal — classified by SHAPE (a one-key
    mapping naming a recognized marker key), never by the member's declared
    role: a value-object document is wrapped in :class:`JsonDocument` before
    this ever runs, so it is never mistaken for a marker (m-value-object
    "Writing" marker disambiguation)."""
    if isinstance(value, Mapping):
        marker = cast("Mapping[str, object]", value)
        if len(marker) == 1 and (key := next(iter(marker))) in _MARKER_KEYS:
            return key
    return None


def _refuse_unrecognized_marker(
    entity: EntityMetadata, column: str, value: object, context: str
) -> None:
    """Refuse a marker this ``context`` (``insert`` / ``update``) lowering does
    not render — e.g. an ``increment`` marker reaching an INSERT's value list,
    or a ``computed`` marker reaching an UPDATE's `set` clause. Never fires for
    an ordinary literal or a value-object document (already excluded by
    :func:`_marker_kind`'s shape classification)."""
    kind = _marker_kind(value)
    if kind is not None:
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{column}: a {kind!r} "
            f"marker is not recognized for {context} lowering"
        )


def lower_insert(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
) -> Statement:
    """`insert into <table>(<present columns in Table Layout order>) values (?, …)`,
    or the pk-gen `max` INSERT…SELECT form when a scalar cell carries the
    `{computed: "maxPlusOne"}` marker (`m-pk-gen`).

    Only the columns the write input names are emitted — a row omitting a nullable
    column produces a narrower `INSERT` (never an explicit `NULL` bind), matching the
    corpus (`m-unit-work-003` inserts 4 of OrderItem's 5 columns). A versioned entity's
    row derives the INITIAL version (`m-opt-lock.INITIAL_VERSION`) at the version
    column's own slot position, ignoring any row-carried value; an
    inheritance-family (table-per-hierarchy) concrete additionally derives the tag
    column from its own `tagValue` at the layout's Discriminator-tier slot
    (`m-inheritance` / `m-sql` "Table-per-hierarchy DML") — neither is ever authored
    in the neutral write input.
    """
    row = dict(instruction.rows[0])
    if version_attr is not None:
        row[version_attr.identity.name] = opt_lock.INITIAL_VERSION
    cells = _ordered_cells(meta, entity, row, discriminator=True)
    columns = ", ".join(dialect.quote(column) for column, _ in cells)
    has_computed = any(_marker_kind(value) == "computed" for _, value in cells)
    if not has_computed:
        binds: list[object] = []
        for column, value in cells:
            _refuse_unrecognized_marker(entity, column, value, "insert")
            binds.append(value)
        holes = ", ".join("?" for _ in cells)
        return Statement(
            f"insert into {_table(meta, entity)}({columns}) values ({holes})", tuple(binds)
        )
    select_parts: list[str] = []
    binds = []
    for column, value in cells:
        if _marker_kind(value) == "computed":
            _require_max_plus_one(entity, column, value)
            select_parts.append(f"coalesce(max(t0.{dialect.quote(column)}), ?) + ?")
            binds.extend([0, 1])
        else:
            _refuse_unrecognized_marker(entity, column, value, "insert")
            select_parts.append("?")
            binds.append(value)
    select_list = ", ".join(select_parts)
    return Statement(
        f"insert into {_table(meta, entity)}({columns}) select {select_list} "
        f"from {_table(meta, entity)} t0",
        tuple(binds),
    )


def _require_max_plus_one(entity: EntityMetadata, column: str, value: object) -> None:
    marker = cast("Mapping[str, object]", value)
    if marker.get("computed") != "maxPlusOne":
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{column}: "
            f"{marker.get('computed')!r} is not a recognized `computed` strategy (m-pk-gen)"
        )


def lower_update(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
    observation: Observation | None,
    concurrency: Concurrency,
) -> Statement:
    """`update <table> set <non-pk columns in Table Layout order> = ?, <version> = ?
    where <pk> = ? [and <tag.column> = ?] [and <version> = ?]`.

    The domain `SET` columns follow the Table Layout's slot order (not the row's
    data order); the FRAMEWORK-DERIVED version advance is NEVER one of them — it is
    appended LAST, after every domain column, unconditionally (`m-value-object-046`:
    a value-object document occupies the Document tier, after every scalar tier
    (`m-value-object` "One column"), including the version attribute's own slot,
    so threading the derived advance through the SAME slot order would
    wrongly render it BEFORE the document; the version SET position is a
    framework-owned rendering decision, not a layout fact, mirroring the
    version GATE's own "binds last" rule one clause family over). The `WHERE`
    keys on the (family-effective) primary key, then an inheritance-family tag
    guard (`m-inheritance` / `m-sql` "Opt-lock composition" — the tag guard
    joins the identity predicates, immediately after the pk), then — LAST, no
    exception — the optimistic-lock version gate (`m-opt-lock` "the version gate
    binds last").

    A versioned row's SET carrying an EXPLICIT value for the version attribute
    is refused outright (`opt_lock.reject_caller_authored_version`): the
    version is framework-owned end to end (ADR 0013), never caller data, so a
    row-carried value is never silently double-assigned against the derived
    advance. Every versioned row's SET derives the advance from this unit of
    work's own recorded observation (`m-opt-lock.require_observed` /
    `.advance`), raising before any DML if this unit of work never observed
    the row's version, and gates on it in optimistic mode only
    (`m-opt-lock.gates`).
    """
    row = dict(instruction.rows[0])
    layout = _layout(meta, entity)
    pk_columns = {column for _, column in _key_columns(layout, meta, entity)}
    if version_attr is not None and version_attr.identity.name in row:
        opt_lock.reject_caller_authored_version(entity.identity.name, version_attr.identity.name)
    observed_version: int | None = None
    version_bind: int | None = None
    if version_attr is not None:
        observed_version = opt_lock.require_observed(entity.identity.name, observation)
        opt_lock.check_locking_license(concurrency, latest_pinned=True)
        version_bind = opt_lock.advance(observed_version)
    set_cells = [cell for cell in _ordered_cells(meta, entity, row) if cell[0] not in pk_columns]
    assignment_parts: list[str] = []
    binds: list[object] = []
    for column, value in set_cells:
        amount = _increment_amount(value)
        quoted = dialect.quote(column)
        if amount is not None:
            assignment_parts.append(f"{quoted} = {quoted} + ?")
            binds.append(amount)
        else:
            _refuse_unrecognized_marker(entity, column, value, "update")
            assignment_parts.append(f"{quoted} = ?")
            binds.append(value)
    if version_bind is not None:
        assert version_attr is not None  # derived above whenever version_bind is set
        assignment_parts.append(f"{dialect.quote(_version_column(layout, version_attr))} = ?")
        binds.append(version_bind)
    where_sql, key_binds = key_predicate(meta, entity, row, dialect)
    if version_attr is not None and opt_lock.gates(concurrency):
        assert observed_version is not None  # derived above whenever version_attr is not None
        where_sql = f"{where_sql} and {dialect.quote(_version_column(layout, version_attr))} = ?"
        key_binds = (*key_binds, observed_version)
    assignments = ", ".join(assignment_parts)
    return Statement(
        f"update {layout.layout.table.name} set {assignments} where {where_sql}",
        (*binds, *key_binds),
    )


def _increment_amount(value: object) -> int | None:
    if _marker_kind(value) == "increment":
        return cast("int", cast("Mapping[str, object]", value)["increment"])
    return None


def lower_delete(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
    observation: Observation | None,
) -> Statement:
    """`delete from <table> where <pk> = ? [and <tag.column> = ?] [and <version> =
    ?]` — keyed by the (family-effective) primary key, tag-guarded for an
    inheritance-family concrete.

    A keyed DELETE of a VERSIONED row requires a PRIOR observation, exactly as a
    keyed UPDATE does (`m-opt-lock`; `python.md` §5 "A keyed update or delete of a
    versioned row this unit of work never observed raises in either mode"): this
    unit of work never issues an implicit resolving read on behalf of a keyed
    write, so with no observed version there is nothing to bind. Unobserved raises
    `UnobservedVersionError` before any DML, in EITHER concurrency mode
    (`opt_lock.require_observed`); observed binds the observed version
    (`m-batch-write-004`'s own default-mode witness). Non-versioned deletes never
    reach this at all (``version_attr is None``).
    """
    row = instruction.rows[0]
    layout = _layout(meta, entity)
    where_sql, key_binds = key_predicate(meta, entity, row, dialect)
    if version_attr is not None:
        observed_version = opt_lock.require_observed(entity.identity.name, observation)
        where_sql = f"{where_sql} and {dialect.quote(_version_column(layout, version_attr))} = ?"
        key_binds = (*key_binds, observed_version)
    return Statement(f"delete from {layout.layout.table.name} where {where_sql}", key_binds)


# --------------------------------------------------------------------------- #
# Set-based collapse lowering (m-batch-write "Set-                            #
# based flush"). `parallax.core.batch_write` decides WHETHER a run of rows    #
# collapses (the planner's own collapse stage, injected via `Database.        #
# transact`'s `collapse_policy`); everything here renders the ALREADY-        #
# collapsed multi-row `KeyedWrite` this seam receives. Reuses `_ordered_cells` #
# / `key_predicate` / `_tag_guard` exactly as the single-row forms do — no    #
# reinvented column-order or bind discipline.                                 #
# --------------------------------------------------------------------------- #
def lower_multi_insert(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
) -> Statement:
    """`insert into <table>(<cols>) values (?, …), (?, …), …` — the multi-row
    INSERT collapse (`m-batch-write.md` L17-19): every row's cells in the SAME
    Table Layout order (`_ordered_cells`, unchanged), one value tuple per row,
    in buffer order. A versioned entity's row derives the SAME
    `opt_lock.INITIAL_VERSION` at its own slot position as the single-row
    form — the initial version is a constant, never observed, so it is exactly
    as safe to batch as any other column (`m-opt-lock`).

    Batch grouping (:func:`collapse_group_key`) already keeps differing slot
    selections in separate runs, so the mixed-shape refusal below can only fire
    for a hand-built instruction — where refusing beats binding a later row's
    values positionally against the first row's column list.
    """
    columns: list[str] | None = None
    rows_cells: list[list[tuple[str, object]]] = []
    for raw_row in instruction.rows:
        row = dict(raw_row)
        if version_attr is not None:
            row[version_attr.identity.name] = opt_lock.INITIAL_VERSION
        cells = _ordered_cells(meta, entity, row, discriminator=True)
        row_columns = [column for column, _ in cells]
        if columns is None:
            columns = row_columns
        elif row_columns != columns:
            raise WriteLoweringError(
                f"multi-row insert on {entity.identity.name!r}: row column sets differ within one "
                f"collapsed instruction ({columns} vs {row_columns}) — a batch collapse "
                "requires every row to carry the same members"
            )
        rows_cells.append(cells)
    assert columns is not None  # `instruction.rows` is schema-required non-empty
    quoted_columns = ", ".join(dialect.quote(column) for column in columns)
    binds: list[object] = []
    value_groups: list[str] = []
    for cells in rows_cells:
        holes: list[str] = []
        for column, value in cells:
            _refuse_unrecognized_marker(entity, column, value, "insert")
            holes.append("?")
            binds.append(value)
        value_groups.append(f"({', '.join(holes)})")
    return Statement(
        f"insert into {_table(meta, entity)}({quoted_columns}) values {', '.join(value_groups)}",
        tuple(binds),
    )


def lower_batched_update(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
) -> Statement:
    """`update <table> set <cols> = ?, … where <pk> in (?, …) [and <tag.column> =
    ?]` — the uniform-value batched UPDATE collapse (`m-batch-write.md` L20-22):
    every row assigns the IDENTICAL non-key values (the injected
    `m-batch-write` eligibility check already verified this), so ONE `SET`
    clause (the first row's own cells, Table Layout order) applies to every
    key in the `IN`-list, in row order. A VERSIONED entity's update never
    reaches here — `m-batch-write` never collapses one (the per-row gate binds
    a per-row observed version no shared statement can carry).
    """
    # `m-batch-write.update_collapses` excludes a versioned entity outright, so
    # this assertion's failure arm is unreachable from any planner-produced
    # instruction.
    assert version_attr is None, "a versioned entity's update never collapses (m-batch-write)"
    layout = _layout(meta, entity)
    key_columns = _key_columns(layout, meta, entity)
    pk_columns = {column for _, column in key_columns}
    first_row = dict(instruction.rows[0])
    set_cells = [
        cell for cell in _ordered_cells(meta, entity, first_row) if cell[0] not in pk_columns
    ]
    assignment_parts: list[str] = []
    binds: list[object] = []
    for column, value in set_cells:
        _refuse_unrecognized_marker(entity, column, value, "update")
        assignment_parts.append(f"{dialect.quote(column)} = ?")
        binds.append(value)
    in_sql, in_binds = _keys_in_list(key_columns, instruction.rows, dialect)
    tag_sql, tag_binds = _tag_guard(meta, entity, dialect)
    assignments_sql = ", ".join(assignment_parts)
    return Statement(
        f"update {layout.layout.table.name} set {assignments_sql} where {in_sql}{tag_sql}",
        (*binds, *in_binds, *tag_binds),
    )


def lower_multi_delete(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
) -> Statement:
    """`delete from <table> where <pk> in (?, …) [and <tag.column> = ?]` — the
    IN-list DELETE collapse (`m-batch-write.md` L23-26, "the delete analogue
    of the multi-row INSERT"). A VERSIONED entity's delete never reaches here —
    `m-batch-write` never collapses one (each row must be removed under its
    own observed version, `m-batch-write-004`).
    """
    # `m-batch-write.delete_collapses` excludes a versioned entity outright, so
    # this assertion's failure arm is unreachable from any planner-produced
    # instruction.
    assert version_attr is None, "a versioned entity's delete never collapses (m-batch-write)"
    layout = _layout(meta, entity)
    in_sql, in_binds = _keys_in_list(_key_columns(layout, meta, entity), instruction.rows, dialect)
    tag_sql, tag_binds = _tag_guard(meta, entity, dialect)
    return Statement(
        f"delete from {layout.layout.table.name} where {in_sql}{tag_sql}",
        (*in_binds, *tag_binds),
    )


def _keys_in_list(
    key_columns: Sequence[tuple[AttributeMetadata, str]],
    rows: Sequence[Mapping[str, object]],
    dialect: Dialect,
) -> tuple[str, tuple[object, ...]]:
    """``<pk> in (?, …)`` (a single-column key) or ``(<pk1>, <pk2>) in ((?, ?),
    …)`` (a composite key), one entry per row, in row order."""
    if len(key_columns) == 1:
        attribute, column = key_columns[0]
        keys_sql = dialect.quote(column)
        holes = ", ".join("?" for _ in rows)
        binds = tuple(row[attribute.identity.name] for row in rows)
        return f"{keys_sql} in ({holes})", binds
    keys_sql = f"({', '.join(dialect.quote(column) for _, column in key_columns)})"
    row_hole = f"({', '.join('?' for _ in key_columns)})"
    holes = ", ".join(row_hole for _ in rows)
    binds = tuple(row[attribute.identity.name] for row in rows for attribute, _ in key_columns)
    return f"{keys_sql} in ({holes})", binds


def _tag_guard(
    meta: Metamodel, entity: EntityMetadata, dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """`` and <tag.column> = ?`` plus its bind — the SAME inheritance-family
    tag guard `key_predicate` adds to a single-row identity predicate, reused
    for a collapsed multi-row statement's shared `IN`-list (every row of one
    collapsed instruction is the SAME concrete subtype, so the tag value is
    constant); ``("", ())`` for a non-participant or a table-per-concrete-
    subtype one (no shared table, no tag)."""
    tag = _tag(meta, entity)
    if tag is None:
        return "", ()
    return f" and {dialect.quote(tag[0])} = ?", (tag[1],)


# --------------------------------------------------------------------------- #
# Readless predicate-write lowering (ADR 0014's                               #
# unversioned/non-temporal exception, `m-batch-write.md` "Predicate-selected  #
# readless forms"). A MATERIALIZING predicate write (versioned or temporal    #
# target) never reaches here — `_predicate_writes.buffer_predicate` decomposes #
# it to per-row keyed writes at BUFFER time, before it is ever planned; the   #
# defensive check below only ever catches a caller wiring defect, never a     #
# legal readless write.                                                       #
# --------------------------------------------------------------------------- #
def lower_predicate_write(
    instruction: PredicateWrite, meta: Metamodel, dialect: Dialect
) -> Statement:
    """`update <table> set <col> = ?, … where <predicate>` / `delete from
    <table> where <predicate>` — one readless statement, no materialization,
    no equality-elimination pass (`m-batch-write.md` L59-92). The `SET`
    columns and their binds follow Table Layout order
    (`_ordered_cells`, reused unchanged), never the authored assignment order;
    predicate binds come AFTER assignment binds. The rendered predicate is
    UNALIASED (`compile_write_predicate`), contrasting the resolving read's
    `t0`-aliased form.

    Rejects an INHERITANCE-FAMILY target here, at the lowering boundary, BEFORE
    any SQL (`python.md` §5 "a set-based write whose target entity belongs to an
    inheritance family is rejected before SQL"; `m-inheritance` "Per-object
    writes are keyed; set-based inheritance writes are out of scope"), with the
    SAME ``subtype-write-set-based-unsupported`` classification the buffer-time
    seams raise (:func:`~parallax.snapshot.handle._predicate_writes.
    buffer_predicate` / :func:`~parallax.snapshot.handle._predicate_writes.
    buffer_predicate_instruction`). Those two guard the DEVELOPER `_where` verbs
    and the engine's own buffering translation, but they are NOT the only road
    here: `lower_write` is exported (`parallax.snapshot.handle.__all__`), and the
    conformance engine's readless predicate-write step
    (`conformance.engine._lower_predicate_write_step`) reaches `lower_write`
    straight from a deserialized instruction, never through a buffer seam. The
    rejection therefore belongs on the lowering side of the boundary as well,
    where EVERY caller passes — the tightest total point, since this function is
    `compile_write_predicate`'s only production caller. Without it a family
    target renders its tag guard into unaliased DML (`delete from payment where
    (card_network = ? and t0.kind = ?)`), naming a `t0` the statement never
    declares.
    """
    entity = entity_of(meta, instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring_entity = declaring(meta, entity)
    if (
        declaring_entity.declared_as_of_axes
        or version_attribute(meta, declaring_entity) is not None
    ):
        raise WriteLoweringError(
            f"{instruction.target.entity!r}: a predicate write on a versioned or temporal "
            "target has no readless template — it must materialize to keyed writes before "
            "reaching lower_write (m-opt-lock; ADR 0014); this is a caller wiring defect"
        )
    predicate = compile_write_predicate(instruction.target.predicate, meta, dialect, entity)
    where_sql, predicate_binds = predicate.sql, predicate.binds
    if instruction.mutation == "delete":
        return Statement(f"delete from {_table(meta, entity)} where {where_sql}", predicate_binds)
    assignment_row = {
        assignment_member(assignment.attr): assignment.value
        for assignment in instruction.assignments
    }
    cells = _ordered_cells(meta, entity, assignment_row)
    assignment_parts: list[str] = []
    binds: list[object] = []
    for column, value in cells:
        assignment_parts.append(f"{dialect.quote(column)} = ?")
        binds.append(value)
    assignments_sql = ", ".join(assignment_parts)
    return Statement(
        f"update {_table(meta, entity)} set {assignments_sql} where {where_sql}",
        (*binds, *predicate_binds),
    )


def _member_contributor(contributor: ColumnContributor) -> str | None:
    """The declared member name behind ``contributor``, or ``None`` for the
    framework-owned discriminator (which no write input ever names)."""
    if isinstance(contributor, AttributeIdentity):
        return contributor.name
    if isinstance(contributor, ValueObjectIdentity):
        return contributor.path[-1]
    return None


def _member_ordinals(layout: EntityLayoutView) -> dict[str, tuple[int, str, bool]]:
    """Each member name the view carries, mapped to its
    ``(slot ordinal, physical column, is a document slot)``.

    The framework-owned discriminator has no member name and is absent: no write
    input ever names it, and every form that emits it derives it from the view's
    own assignment instead.
    """
    ordinals: dict[str, tuple[int, str, bool]] = {}
    for ordinal, slot in enumerate(layout.columns):
        member = _member_contributor(slot.contributor)
        if member is not None:
            is_document = isinstance(slot.contributor, ValueObjectIdentity)
            ordinals[member] = (ordinal, slot.column.name, is_document)
    return ordinals


def collapse_group_key(
    meta: Metamodel, entity: EntityMetadata, mutation: str, row: Mapping[str, object]
) -> object:
    """The physical shape a buffered row must share with its neighbours before
    they may collapse into one statement — this layer's half of the planner's
    batch grouping (`m-sql` "Physical DML ordering": grouping compares the
    FILTERED, table-ordered slot selections, never the payload mapping).

    Two rows carrying different members select different columns, so one shared
    statement could only bind the later row's values positionally against the
    first row's column list. Answering their shapes apart keeps them in separate
    runs, which is why every collapsed instruction that reaches a batch builder
    is same-shaped by construction.

    TOTAL: the planner asks this of every collapse candidate, long before any
    lowering decides the row is renderable at all. A target owning no table and a
    row naming a member its view does not carry both answer ``None`` — one
    undifferentiated group, leaving the loud refusal to the builder that would
    have rendered them.
    """
    view = entity_layout(meta, entity)
    if view is None:
        return None
    ordinals = _member_ordinals(view)
    selection: list[tuple[int, str]] = []
    for name in row:
        slot = ordinals.get(name)
        if slot is None:
            return None
        selection.append((slot[0], slot[1]))
    selection.sort()
    return (mutation, tuple(column for _, column in selection))


def _ordered_cells(
    meta: Metamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    *,
    discriminator: bool = False,
) -> list[tuple[str, object]]:
    """The row's present members as `(column, bind)` pairs, in Table Layout order.

    The target's Storage Layout Entity view supplies both the physical column of
    each member and the one order every cell follows, so a row's data order never
    reaches the statement. Each row key names a declared scalar Attribute or a
    top-level Value Object of that view; a value-object member binds as one
    :class:`JsonDocument` at its Document-tier slot (the whole document — the
    write never decomposes it), a scalar binds its value (or its DB-computed
    marker document verbatim, classified by the caller). ``discriminator``
    additionally emits the layout's derived table-per-hierarchy tag value at its
    own Discriminator-tier slot — the one cell a full-row write derives rather
    than reads.
    """
    layout = _layout(meta, entity)
    assignment = layout.discriminator
    ordinals = _member_ordinals(layout)
    discriminator_cell: tuple[int, str, object] | None = None
    if discriminator and assignment is not None:
        for ordinal, slot in enumerate(layout.columns):
            if slot == assignment.slot:
                discriminator_cell = (ordinal, slot.column.name, assignment.value)
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        ordinal, column, is_value_object = ordinals[name]
        cells.append((ordinal, column, JsonDocument(value) if is_value_object else value))
    if discriminator_cell is not None:
        cells.append(discriminator_cell)
    cells.sort(key=lambda cell: cell[0])
    return [(column, bind) for _, column, bind in cells]


def _key_columns(
    layout: EntityLayoutView, meta: Metamodel, entity: EntityMetadata
) -> tuple[tuple[AttributeMetadata, str], ...]:
    """The family-effective primary-key Attributes paired with the physical
    Columns their slots occupy.

    Operation key selection stays semantic (`_family.family_primary_key`); only
    the mapping onto physical Columns comes from the layout, so an update or
    delete predicate keys on the model identity rather than on the Table's own
    physical key.
    """
    return tuple(
        (attribute, slot_column(layout, attribute.identity))
        for attribute in family_primary_key(meta, entity)
    )


def _version_column(layout: EntityLayoutView, version_attr: AttributeMetadata) -> str:
    """The physical Column the optimistic-lock version Attribute's slot occupies."""
    return slot_column(layout, version_attr.identity)


def key_predicate(
    meta: Metamodel, entity: EntityMetadata, row: Mapping[str, object], dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """The `<pk1> = ? [and <pk2> = ?] [and <tag.column> = ?]` identity predicate
    and its ordered binds — the family-effective primary key, then an
    inheritance-family table-per-hierarchy concrete's own tag guard, joining the
    identity predicates immediately after the pk (`m-inheritance` / `m-sql`) —
    never present for a table-per-concrete-subtype participant or a
    non-participant.
    """
    keys = _key_columns(_layout(meta, entity), meta, entity)
    predicate = " and ".join(f"{dialect.quote(column)} = ?" for _, column in keys)
    binds: tuple[object, ...] = tuple(row[attribute.identity.name] for attribute, _ in keys)
    tag = _tag(meta, entity)
    if tag is not None:
        predicate = f"{predicate} and {dialect.quote(tag[0])} = ?"
        binds = (*binds, tag[1])
    return predicate, binds
