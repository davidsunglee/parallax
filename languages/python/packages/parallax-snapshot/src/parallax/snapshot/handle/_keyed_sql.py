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
discipline every builder reuses, so no form reinvents bind order.

The eight builders `_write_lowering` dispatches to are spelled bare; the helpers
they share among themselves keep their leading underscore because every one of
their call sites is in THIS module. (`_ordered_cells` and `_family_column_order`
read as a shared pair but are not: every `_ordered_cells` caller is a builder
here, and `_family_column_order`'s only caller is `_ordered_cells`.)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import inheritance, opt_lock
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Attribute, Entity, Metamodel, column_order
from parallax.core.dialect import Dialect
from parallax.core.sql_gen import Statement, compile_write_predicate
from parallax.core.unit_work import Concurrency, KeyedWrite, Observation, PredicateWrite
from parallax.snapshot.handle._family import assignment_member, members, version_attribute
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = [
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


def _table(meta: Metamodel, entity: Entity) -> str:
    table = inheritance.effective_table(meta, entity)
    if table is None:
        raise WriteLoweringError(f"{entity.name!r}: write target has no effective table")
    return table


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


def _refuse_unrecognized_marker(entity: Entity, column: str, value: object, context: str) -> None:
    """Refuse a marker this ``context`` (``insert`` / ``update``) lowering does
    not render — e.g. an ``increment`` marker reaching an INSERT's value list,
    or a ``computed`` marker reaching an UPDATE's `set` clause. Never fires for
    an ordinary literal or a value-object document (already excluded by
    :func:`_marker_kind`'s shape classification)."""
    kind = _marker_kind(value)
    if kind is not None:
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.name!r}.{column}: a {kind!r} marker is "
            f"not recognized for {context} lowering (COR-3 Phase 8; m-pk-gen)"
        )


def lower_insert(
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
) -> Statement:
    """`insert into <table>(<present columns in family columnOrder>) values (?, …)`,
    or the pk-gen `max` INSERT…SELECT form when a scalar cell carries the
    `{computed: "maxPlusOne"}` marker (`m-pk-gen`).

    Only the columns the write input names are emitted — a row omitting a nullable
    column produces a narrower `INSERT` (never an explicit `NULL` bind), matching the
    corpus (`m-unit-work-003` inserts 4 of OrderItem's 5 columns). A versioned entity's
    row derives the INITIAL version (`m-opt-lock.INITIAL_VERSION`) at the version
    column's family columnOrder position, ignoring any row-carried value; an
    inheritance-family (table-per-hierarchy) concrete additionally derives the tag
    column from its own `tagValue`, slotted right after the primary key
    (`m-inheritance` / `m-sql` "Table-per-hierarchy DML") — neither is ever authored
    in the neutral write input.
    """
    row = dict(instruction.rows[0])
    if version_attr is not None:
        row[version_attr.name] = opt_lock.INITIAL_VERSION
    cells = _ordered_cells(meta, entity, row, _tag_insert_column(entity, declaring))
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


def _require_max_plus_one(entity: Entity, column: str, value: object) -> None:
    marker = cast("Mapping[str, object]", value)
    if marker.get("computed") != "maxPlusOne":
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.name!r}.{column}: "
            f"{marker.get('computed')!r} is not a recognized `computed` strategy (m-pk-gen)"
        )


def _tag_insert_column(entity: Entity, declaring: Entity) -> dict[str, object]:
    """The framework-derived `{tag column: tagValue}` an inheritance-family
    concrete's INSERT carries — empty for a non-participant, a table-per-
    concrete-subtype participant (no shared table, no tag column), or the
    abstract root itself (never a write target)."""
    if entity.inheritance is None or declaring.inheritance is None:
        return {}
    tag_column = declaring.inheritance.tag_column
    tag_value = entity.inheritance.tag_value
    if tag_column is None or tag_value is None:
        return {}
    return {tag_column: tag_value}


def lower_update(
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
    observation: Observation | None,
    concurrency: Concurrency,
) -> Statement:
    """`update <table> set <non-pk columns in family columnOrder> = ?, <version> = ?
    where <pk> = ? [and <tag.column> = ?] [and <version> = ?]`.

    The domain `SET` columns follow the family columnOrder (not the row's data
    order); the FRAMEWORK-DERIVED version advance is NEVER one of them — it is
    appended LAST, after every domain column, unconditionally (`m-value-object-046`:
    a value-object document column sorts AFTER every scalar in columnOrder
    (`m-value-object` "One column"), including the version attribute, so
    threading the derived advance through the SAME columnOrder sort would
    wrongly render it BEFORE the document; the version SET position is a
    framework-owned rendering decision, not a columnOrder fact, mirroring the
    version GATE's own "binds last" rule one clause family over). The `WHERE`
    keys on the (family-effective) primary key, then an inheritance-family tag
    guard (`m-inheritance` / `m-sql` "Opt-lock composition" — the tag guard
    joins the identity predicates, immediately after the pk), then — LAST, no
    exception — the optimistic-lock version gate (`m-opt-lock` "the version gate
    binds last").

    A versioned row's SET carrying an EXPLICIT value for the version attribute
    is refused outright (`opt_lock.reject_caller_authored_version`) — the
    M4-era plain-column-data passthrough some corpus witnesses used to carry
    retired once the corpus amended those witnesses to author an observing
    find instead (COR-3 Phase 8 core amendment bundle): the version is
    framework-owned end to end (ADR 0013), never caller data, so a
    row-carried value is never silently double-assigned against the derived
    advance. Every versioned row's SET derives the advance from this unit of
    work's own recorded observation (`m-opt-lock.require_observed` /
    `.advance`), raising before any DML if this unit of work never observed
    the row's version, and gates on it in optimistic mode only
    (`m-opt-lock.gates`).
    """
    row = dict(instruction.rows[0])
    pk_columns = {attr.column for attr in inheritance.family_primary_key(meta, entity)}
    if version_attr is not None and version_attr.name in row:
        opt_lock.reject_caller_authored_version(entity.name, version_attr.name)
    observed_version: int | None = None
    version_bind: int | None = None
    if version_attr is not None:
        observed_version = opt_lock.require_observed(entity.name, observation)
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
        assignment_parts.append(f"{dialect.quote(version_attr.column)} = ?")
        binds.append(version_bind)
    where_sql, key_binds = key_predicate(meta, entity, row, dialect, declaring)
    if version_attr is not None and opt_lock.gates(concurrency):
        assert observed_version is not None  # derived above whenever version_attr is not None
        where_sql = f"{where_sql} and {dialect.quote(version_attr.column)} = ?"
        key_binds = (*key_binds, observed_version)
    assignments = ", ".join(assignment_parts)
    return Statement(
        f"update {_table(meta, entity)} set {assignments} where {where_sql}",
        (*binds, *key_binds),
    )


def _increment_amount(value: object) -> int | None:
    if _marker_kind(value) == "increment":
        return cast("int", cast("Mapping[str, object]", value)["increment"])
    return None


def lower_delete(
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
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
    where_sql, key_binds = key_predicate(meta, entity, row, dialect, declaring)
    if version_attr is not None:
        observed_version = opt_lock.require_observed(entity.name, observation)
        where_sql = f"{where_sql} and {dialect.quote(version_attr.column)} = ?"
        key_binds = (*key_binds, observed_version)
    return Statement(f"delete from {_table(meta, entity)} where {where_sql}", key_binds)


# --------------------------------------------------------------------------- #
# Set-based collapse lowering (COR-3 Phase 8 increment 5; m-batch-write "Set- #
# based flush"). `parallax.core.batch_write` decides WHETHER a run of rows    #
# collapses (the planner's own collapse stage, injected via `Database.        #
# transact`'s `collapse_policy`); everything here renders the ALREADY-        #
# collapsed multi-row `KeyedWrite` this seam receives. Reuses `_ordered_cells` #
# / `key_predicate` / `_tag_guard` exactly as the single-row forms do — no    #
# reinvented column-order or bind discipline.                                 #
# --------------------------------------------------------------------------- #
def lower_multi_insert(
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
) -> Statement:
    """`insert into <table>(<cols>) values (?, …), (?, …), …` — the multi-row
    INSERT collapse (`m-batch-write.md` L17-19): every row's cells in the SAME
    family columnOrder (`_ordered_cells`, unchanged), one value tuple per row,
    in buffer order. A versioned entity's row derives the SAME
    `opt_lock.INITIAL_VERSION` at its columnOrder position as the single-row
    form — the initial version is a constant, never observed, so it is exactly
    as safe to batch as any other column (`m-opt-lock`).
    """
    tag = _tag_insert_column(entity, declaring)
    columns: list[str] | None = None
    rows_cells: list[list[tuple[str, object]]] = []
    for raw_row in instruction.rows:
        row = dict(raw_row)
        if version_attr is not None:
            row[version_attr.name] = opt_lock.INITIAL_VERSION
        cells = _ordered_cells(meta, entity, row, tag)
        row_columns = [column for column, _ in cells]
        if columns is None:
            columns = row_columns
        elif row_columns != columns:
            raise WriteLoweringError(
                f"multi-row insert on {entity.name!r}: row column sets differ within one "
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
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
) -> Statement:
    """`update <table> set <cols> = ?, … where <pk> in (?, …) [and <tag.column> =
    ?]` — the uniform-value batched UPDATE collapse (`m-batch-write.md` L20-22):
    every row assigns the IDENTICAL non-key values (the injected
    `m-batch-write` eligibility check already verified this), so ONE `SET`
    clause (the first row's own cells, family columnOrder) applies to every
    key in the `IN`-list, in row order. A VERSIONED entity's update never
    reaches here — `m-batch-write` never collapses one (the per-row gate binds
    a per-row observed version no shared statement can carry).
    """
    # `m-batch-write.update_collapses` excludes a versioned entity outright, so
    # this assertion's failure arm is unreachable from any planner-produced
    # instruction (see the outline's retained-assertion record, COR-42).
    assert version_attr is None, "a versioned entity's update never collapses (m-batch-write)"
    pk_attrs = inheritance.family_primary_key(meta, entity)
    pk_names = {attr.name for attr in pk_attrs}
    first_row = dict(instruction.rows[0])
    set_cells = [
        cell for cell in _ordered_cells(meta, entity, first_row) if cell[0] not in pk_names
    ]
    assignment_parts: list[str] = []
    binds: list[object] = []
    for column, value in set_cells:
        _refuse_unrecognized_marker(entity, column, value, "update")
        assignment_parts.append(f"{dialect.quote(column)} = ?")
        binds.append(value)
    in_sql, in_binds = _keys_in_list(pk_attrs, instruction.rows, dialect)
    tag_sql, tag_binds = _tag_guard(entity, declaring, dialect)
    assignments_sql = ", ".join(assignment_parts)
    return Statement(
        f"update {_table(meta, entity)} set {assignments_sql} where {in_sql}{tag_sql}",
        (*binds, *in_binds, *tag_binds),
    )


def lower_multi_delete(
    entity: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    declaring: Entity,
    version_attr: Attribute | None,
) -> Statement:
    """`delete from <table> where <pk> in (?, …) [and <tag.column> = ?]` — the
    IN-list DELETE collapse (`m-batch-write.md` L23-26, "the delete analogue
    of the multi-row INSERT"). A VERSIONED entity's delete never reaches here —
    `m-batch-write` never collapses one (each row must be removed under its
    own observed version, `m-batch-write-004`).
    """
    # `m-batch-write.delete_collapses` excludes a versioned entity outright, so
    # this assertion's failure arm is unreachable from any planner-produced
    # instruction (see the outline's retained-assertion record, COR-42).
    assert version_attr is None, "a versioned entity's delete never collapses (m-batch-write)"
    pk_attrs = inheritance.family_primary_key(meta, entity)
    in_sql, in_binds = _keys_in_list(pk_attrs, instruction.rows, dialect)
    tag_sql, tag_binds = _tag_guard(entity, declaring, dialect)
    return Statement(
        f"delete from {_table(meta, entity)} where {in_sql}{tag_sql}",
        (*in_binds, *tag_binds),
    )


def _keys_in_list(
    pk_attrs: Sequence[Attribute], rows: Sequence[Mapping[str, object]], dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """``<pk> in (?, …)`` (a single-column key) or ``(<pk1>, <pk2>) in ((?, ?),
    …)`` (a composite key), one entry per row, in row order."""
    pk_columns = [attr.column for attr in pk_attrs]
    if len(pk_columns) == 1:
        keys_sql = dialect.quote(pk_columns[0])
        holes = ", ".join("?" for _ in rows)
        binds = tuple(row[pk_attrs[0].name] for row in rows)
        return f"{keys_sql} in ({holes})", binds
    keys_sql = f"({', '.join(dialect.quote(column) for column in pk_columns)})"
    row_hole = f"({', '.join('?' for _ in pk_columns)})"
    holes = ", ".join(row_hole for _ in rows)
    binds = tuple(row[attr.name] for row in rows for attr in pk_attrs)
    return f"{keys_sql} in ({holes})", binds


def _tag_guard(
    entity: Entity, declaring: Entity, dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """`` and <tag.column> = ?`` plus its bind — the SAME inheritance-family
    tag guard `key_predicate` adds to a single-row identity predicate, reused
    for a collapsed multi-row statement's shared `IN`-list (every row of one
    collapsed instruction is the SAME concrete subtype, so the tag value is
    constant); ``("", ())`` for a non-participant or a table-per-concrete-
    subtype one (no shared table, no tag)."""
    if entity.inheritance is None or declaring.inheritance is None:
        return "", ()
    tag_column = declaring.inheritance.tag_column
    tag_value = entity.inheritance.tag_value
    if tag_column is None or tag_value is None:
        return "", ()
    return f" and {dialect.quote(tag_column)} = ?", (tag_value,)


# --------------------------------------------------------------------------- #
# Readless predicate-write lowering (COR-3 Phase 8 increment 5; ADR 0014's    #
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
    columns and their binds follow descriptor DECLARED column order
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
    entity = meta.entity(instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring = inheritance.declaring_entity(meta, entity)
    if declaring.is_temporal or version_attribute(declaring) is not None:
        raise WriteLoweringError(
            f"{instruction.target.entity!r}: a predicate write on a versioned or temporal "
            "target has no readless template — it must materialize to keyed writes before "
            "reaching lower_write (m-opt-lock; ADR 0014); this is a caller wiring defect"
        )
    predicate = compile_write_predicate(
        instruction.target.predicate, meta, dialect, instruction.target.entity
    )
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


def _ordered_cells(
    meta: Metamodel,
    entity: Entity,
    row: Mapping[str, object],
    extra_columns: Mapping[str, object] | None = None,
) -> list[tuple[str, object]]:
    """The row's present members (plus any framework-derived ``extra_columns``,
    e.g. an inheritance tag) as `(column, bind)` pairs, in family columnOrder.

    Each row key names a declared scalar attribute or a value object, resolved
    FAMILY-WIDE (`members`) so an inheritance participant's inherited members
    lower correctly; a value-object member binds as one :class:`JsonDocument` in
    its columnOrder position (the whole document — the write never decomposes
    it), a scalar binds its value (or its DB-computed marker document verbatim,
    classified by the caller).
    """
    member_columns = members(meta, entity)
    order = {column: index for index, column in enumerate(_family_column_order(meta, entity))}
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        column, is_value_object = member_columns[name]
        bind = JsonDocument(value) if is_value_object else value
        cells.append((order[column], column, bind))
    if extra_columns:
        for column, value in extra_columns.items():
            cells.append((order[column], column, value))
    cells.sort(key=lambda cell: cell[0])
    return [(column, bind) for _, column, bind in cells]


def _family_column_order(meta: Metamodel, entity: Entity) -> list[str]:
    """``entity``'s FULL physical columns in canonical order (m-sql
    `column_order`'s own rule — primary key first, then the inheritance tag,
    then the remaining scalars, then value-object documents — resolved across
    the WHOLE inheritance family for a participant).

    `~parallax.core.descriptor.column_order` is deliberately a bare PER-ENTITY
    view whose own docstring defers the full inherited chain to "above this
    per-entity view" (m-inheritance): a concrete subtype's OWN compiled record
    carries only its own locally-declared attributes (its ancestry-inherited
    members, including the primary key itself, live on the root's record
    alone), so calling it directly on a family participant would silently
    drop every inherited column from a write's emission. This is that
    "above" resolution, mirroring the ancestry-chain walk
    `~parallax.conformance.provision._fixture_columns` already performs for
    fixture loading (a sibling provisioning concern, not reused directly: DDL/
    fixture column order is an unasserted provisioning choice, m-case-format,
    so it need not — and does not — match this WRITE-EMISSION order byte for
    byte).
    """
    if entity.inheritance is None:
        return list(column_order(entity))
    chain = (*inheritance.ancestor_chain(meta, (entity.name,)), entity)
    pk_columns: list[str] = []
    rest_columns: list[str] = []
    for member in chain:
        for attribute in member.attributes:
            (pk_columns if attribute.primary_key else rest_columns).append(attribute.column)
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None  # a resolved family root always carries one
    tag_columns = [root.inheritance.tag_column] if root.inheritance.tag_column is not None else []
    document_columns = [vo.storage_column for member in chain for vo in member.value_objects]
    return [*pk_columns, *tag_columns, *rest_columns, *document_columns]


def key_predicate(
    meta: Metamodel, entity: Entity, row: Mapping[str, object], dialect: Dialect, declaring: Entity
) -> tuple[str, tuple[object, ...]]:
    """The `<pk1> = ? [and <pk2> = ?] [and <tag.column> = ?]` identity predicate
    and its ordered binds — the primary key (family-effective,
    `inheritance.family_primary_key`), then an inheritance-family
    table-per-hierarchy concrete's own tag guard, joining the identity
    predicates immediately after the pk (`m-inheritance` / `m-sql` resolved
    Q9) — never present for a table-per-concrete-subtype participant (no
    shared table, no tag) or a non-participant.
    """
    keys = inheritance.family_primary_key(meta, entity)
    predicate = " and ".join(f"{dialect.quote(attr.column)} = ?" for attr in keys)
    binds: tuple[object, ...] = tuple(row[attr.name] for attr in keys)
    if entity.inheritance is not None and declaring.inheritance is not None:
        tag_column = declaring.inheritance.tag_column
        tag_value = entity.inheritance.tag_value
        if tag_column is not None and tag_value is not None:
            predicate = f"{predicate} and {dialect.quote(tag_column)} = ?"
            binds = (*binds, tag_value)
    return predicate, binds
