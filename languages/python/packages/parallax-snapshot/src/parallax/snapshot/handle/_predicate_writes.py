"""``parallax.snapshot.handle._predicate_writes`` — the predicate-selected (``_where``) write lane.

The set-based half of the spec §5 write surface, as
free functions rather than :class:`~parallax.snapshot.handle.Transaction`
methods: bare-statement and Valid-Time-window validation into a canonical
:class:`~parallax.core.unit_work.PredicateWrite`, the readless-vs-materialize
dispatch, the minimal resolving read, per-row no-op elimination, and
Materialized Write Group buffering.

Every entry point threads ``(uow, meta, conn, dialect)`` — the four pieces of
transaction state this lane actually reads — mirroring
:func:`~parallax.snapshot.handle._write_inputs.record_observations`'s own shape.
``meta`` is the accepted Metamodel; family shape comes from the Inheritance,
Temporal, and Optimistic Lock facets through :mod:`parallax.snapshot.handle._family`,
and every physical column comes from the target's Storage Layout view, resolved
once here and carried into the per-row column builders
:func:`_materialize_predicate_write` streams into.
``Transaction`` keeps five thin ``_where`` delegates plus the frozen
``_buffer_predicate_instruction`` seam the conformance engine calls, so this
module buffers through ``uow.buffer`` directly and never reaches back into
``Transaction``.

Depends on :mod:`parallax.snapshot.handle._family` (the declaring root, version
attribute, and the layout member-to-column map) and
:mod:`parallax.snapshot.handle._write_inputs` (window validation and the per-row
column contributions).

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, cast

from parallax.core import deep_fetch, inheritance, op_algebra, read_lock
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import Dialect, LockMode
from parallax.core.entity import AttributeAssignment
from parallax.core.entity import Statement as EntityStatement
from parallax.core.metamodel import AttributeMetadata, EntityMetadata, Metamodel
from parallax.core.sql_gen import Statement, compile_read
from parallax.core.unit_work import (
    LATEST_PINNED,
    ChunkedColumnBuilder,
    MaterializedWriteGroup,
    PredecessorColumns,
    PredecessorShape,
    PredicateMutation,
    PredicateWrite,
    TemporalColumns,
    UnitOfWork,
    VersionColumns,
    instructions,
    whole,
)
from parallax.snapshot.handle._family import (
    assignment_member,
    declaring,
    entity_layout,
    entity_of,
    family_primary_key,
    members,
    slot_column,
    version_attribute,
)
from parallax.snapshot.handle._write_inputs import (
    is_no_op_assignment,
    key_column_values,
    predecessor_payload,
    validate_until,
    validate_valid_from,
)


def buffer_predicate(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    mutation: PredicateMutation,
    statement: EntityStatement,
    assignments: Sequence[AttributeAssignment[Any]],
    *,
    valid_from: dt.datetime | None,
    until: dt.datetime | None = None,
) -> None:
    """The neutral seam every ``_where`` verb shares — the SAME seam the
    conformance engine's predicate-write translation drives, so the
    developer-facing verbs and the corpus-driven
    engine path can never diverge in behavior.

    1. **Bare-statement guard** (`python.md` §5 "A statement becomes a
       write target only as a bare statement") — one carrying nothing but
       a predicate; every other clause is rejected (`EntityStatement.
       is_bare`, subsuming ``.distinct()``).
    2. **Target resolution, then operation validation** — the selecting
       predicate is a canonical ``m-op-algebra`` operation and is measured
       against the connected model from its own resolved root, the SAME
       ``validate_operation`` vocabulary a read's
       :func:`~parallax.snapshot.handle._preflight.preflight_find` applies
       and in the SAME order. Authoring reaches no model, so this is the
       only place the whole-model rules — an attribute reference outside
       the active position, an ambiguous Entity spelling, an inverted
       ``between`` window, a literal disagreeing with its member's declared
       type — are enforced on a predicate-selected write. It runs here, at
       build, so a rejection precedes every buffer and the resolving read's
       own force-flush.
    3. **Inheritance rejection** (`m-inheritance` "Per-object writes are
       keyed; set-based inheritance writes are out of scope") — BEFORE any
       SQL, the SAME ``subtype-write-set-based-unsupported`` classification
       a keyless keyed write raises.
    4. **Valid-Time-bound validation** — a Bitemporal target requires
       ``valid_from``; a Transaction-Time-Only or non-temporal target takes none; the
       ``*Until`` forms additionally require ``until``, with
       ``valid_from < until`` — an equal or reversed window rejects
       HERE, at build, before any buffering (:func:`validate_until`).
    5. **Build + validate the canonical instruction** (the SAME
       deserialize/`validate_instruction` round trip a keyed write buys in
       ``Transaction._buffer`` — non-empty/no-duplicate assignments are the
       schema's own check).
    6. **Dispatch**: an unversioned, non-temporal target buffers READLESS
       (one statement, `m-batch-write`); a versioned or temporal one
       MATERIALIZES (``_materialize_predicate_write``, ADR 0014).
    """
    if not statement.is_bare():
        raise ValueError(
            f"{statement.target}: a set-based write target must be a bare statement "
            "(nothing but a predicate) — order_by / limit / distinct / as_of / history / "
            "as_of_range / narrow / include are all rejected on a write target (python.md §5)"
        )
    entity = entity_of(meta, statement.target)
    op_algebra.validate_operation(entity, statement.predicate, meta)
    inheritance.reject_predicate_write(entity)
    declaring_entity = declaring(meta, entity)
    valid_from_literal = validate_valid_from(declaring_entity, mutation, valid_from)
    until_literal: str | None = None
    if until is not None:
        assert valid_from is not None  # `*_until_where` verbs require both together
        until_literal = validate_until(declaring_entity, mutation, valid_from, until)

    doc: dict[str, object] = {
        "mutation": mutation,
        "target": {
            "entity": statement.target,
            "predicate": op_algebra.serialize(statement.predicate),
        },
    }
    if assignments:
        doc["assignments"] = [{"attr": str(a.attr), "value": a.value} for a in assignments]
    if valid_from_literal is not None:
        doc["validFrom"] = valid_from_literal
    if until_literal is not None:
        doc["until"] = until_literal
    instruction = instructions.deserialize(doc)
    assert isinstance(instruction, PredicateWrite)  # this seam always builds the predicate shape
    instructions.validate_instruction(instruction, meta)
    buffer_predicate_instruction(uow, meta, conn, dialect, instruction)


def buffer_predicate_instruction(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
) -> None:
    """The neutral seam UNDERLYING every ``_where`` verb and the
    conformance engine's own predicate-write translation (`m-case-format`
    "predicate-shaped case entries deserialize
    to PredicateWrite through the existing serde and buffer through
    Transaction's own seam"): given an ALREADY-BUILT, already-validated
    :class:`~parallax.core.unit_work.PredicateWrite` instruction, reject an
    inheritance-family target (`m-inheritance`), then dispatch READLESS
    (`m-batch-write`) or MATERIALIZE (`m-opt-lock`, ADR 0014). The typed
    ``_where`` verbs (:func:`buffer_predicate`) build ``instruction`` from
    a bare :class:`~parallax.core.entity.Statement` plus typed
    ``Attr.set(...)`` assignments first; the engine builds it directly
    from the case's own canonical write-instruction document — both
    converge HERE, so the two callers can never diverge in behavior.

    ``Transaction._buffer_predicate_instruction`` is the thin method that
    delegates here. It keeps its leading underscore and its exact signature
    because the conformance engine calls it directly (`parallax.conformance.
    engine`), making it a frozen external seam rather than an ordinary
    cross-module helper.
    """
    entity = entity_of(meta, instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring_entity = declaring(meta, entity)
    version_attr = version_attribute(meta, declaring_entity)
    if not declaring_entity.declared_as_of_axes and version_attr is None:
        # Readless (`m-batch-write.md` "Predicate-selected readless forms"):
        # one statement, no materialization, no equality-elimination pass.
        uow.buffer(instruction)
        return
    _materialize_predicate_write(
        uow, meta, conn, dialect, instruction, entity, declaring_entity, version_attr
    )


def _materialize_predicate_write(
    uow: UnitOfWork,
    meta: Metamodel,
    conn: DbPort,
    dialect: Dialect,
    instruction: PredicateWrite,
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    version_attr: AttributeMetadata | None,
) -> None:
    """Materialize a predicate write on a VERSIONED or TEMPORAL target
    (`m-opt-lock` "Predicate-selected writes materialize when observations
    are needed"; ADR 0014): resolve the predicate through a MINIMAL
    row-form read on THIS transaction's own connection (never instance-form
    — the resolve constructs no object, though it projects whichever Document
    slots the write's own observation and comparison needs require, below),
    then stream each matched row's key and observation values directly into
    bounded column builders — never a per-row keyed-write wrapper, never a
    parallel pending-observation list — and buffer the sealed result as one
    compact :class:`~parallax.core.unit_work.MaterializedWriteGroup` (`m-unit-
    work` "Materialized Write Groups") at the call position. Zero resolved
    rows, or every resolved row eliminated as a no-op, means no group is
    buffered at all. The lock suffix on the resolve derives from the
    transaction's own concurrency mode (``locking`` ⇒ the shared read lock,
    ``optimistic`` ⇒ none) — the SAME rule a real ``Transaction.find``
    applies.

    A TEMPORAL target's raw predicate carries no as-of wrapper (a bare
    statement forbids ``.as_of()``/``.history()``, python.md §5) — exactly
    like an ordinary find's omitted axis, it must still default every
    declared axis to its CURRENT milestone (`m-temporal-read` "default-
    latest"), so the resolve routes through the SAME
    :func:`~parallax.core.deep_fetch.plan` root-canonicalization every
    other read uses (:func:`~parallax.snapshot.handle.find`) rather than
    compiling the raw predicate directly — otherwise a temporal target's
    resolve would match every historical milestone too, not just the open
    one(s).
    """
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a predicate-write target always owns rows
        raise ValueError(f"{entity.identity.canonical}: predicate-write target has no Table")
    lock: LockMode | None = read_lock.mode_for(uow.settings.concurrency)
    plan_ = deep_fetch.plan(entity, instruction.target.predicate, meta)
    assignments = {
        assignment_member(assignment.attr): assignment.value
        for assignment in instruction.assignments
    }
    is_temporal = bool(declaring_entity.declared_as_of_axes)
    # Need-sensitive projection (`m-case-format` "Predicate-selected write
    # instruction"): the resolving read projects the resolved row's own
    # value-object document(s) for TWO independent needs, on EVERY target
    # class — never gated on temporality alone.
    #
    # OBSERVATION need: a TEMPORAL target's per-row observation retains the
    # whole predecessor milestone (`m-unit-work` "A Predecessor Row is the
    # complete, immutable persisted state a Temporal Observation retains"),
    # so its resolving read projects EVERY declared document whatever the
    # verb goes on to do with it. Completeness belongs to the OBSERVATION,
    # not to the topology a verb happens to produce: a decorator must
    # distinguish carried from changed state without a second read (ADR
    # 0042), so a close-only shape — an AUDIT-ONLY `terminate`, which chains
    # nothing — records the same complete predecessor a chain-bearing one
    # does. This subsumes the carry-forward need: a BITEMPORAL rectangle
    # split (`bitemp_write.plan`) carries the old payload into its head and
    # tail on EVERY close-bearing mutation, and an AUDIT-ONLY `update`
    # (`txtime_write.plan`) carries it into its chained row. It is also why
    # EVERY declared document is projected rather than only the assigned
    # ones — a carried row must keep whichever documents the assignments do
    # NOT themselves reassign. Every target's carried state reads through the
    # SAME Predecessor Row (`predecessor_payload`, below); there is no
    # separate audit-only merge.
    #
    # COMPARISON need: an assignment-bearing verb's per-row no-op
    # elimination (below, `is_no_op_assignment`)
    # compares each assigned member's new value against the resolved
    # row's own — a value-object member's comparison can only ever see
    # the STORED document when this read actually projected its column
    # (`m-opt-lock` "when all assignments already equal that row's values,
    # it issues no DML, advances no version"). A VERSIONED NON-TEMPORAL
    # target reaches this need ALONE: it retains only the observed version,
    # never a predecessor row (`m-opt-lock`/`m-descriptor`: versioned and
    # temporal are mutually exclusive). Minimal-read discipline (`m-sql`)
    # then projects the ASSIGNED value-object document(s) only — never every
    # declared one, matching an ordinary read's own need-driven projection.
    assignment_bearing = instruction.mutation in ("update", "updateUntil")
    predecessor_need = version_attr is None and is_temporal
    needs_documents: bool | frozenset[str]
    if predecessor_need:
        needs_documents = True
    elif assignment_bearing:
        member_columns = members(layout)
        needs_documents = frozenset(member for member in assignments if member_columns[member][1])
    else:
        needs_documents = False
    # A materializing predicate write's resolving read is row-form over a
    # non-family target (a family predicate write is rejected before SQL), so
    # its compiled row transform is always the identity — only the statement is
    # consumed here.
    statement = compile_read(
        plan_.root_operation,
        meta,
        dialect,
        entity,
        result_form="row",
        lock=lock,
        include_value_objects=needs_documents,
    ).statement
    rows = uow.read(lambda: _resolve_rows(conn, dialect, statement))
    if not rows:
        return
    pk_attrs = family_primary_key(meta, entity)
    key_attributes = tuple(attr.identity.name for attr in pk_attrs)
    key_builders = tuple(ChunkedColumnBuilder[object]() for _ in pk_attrs)
    matched = 0

    def append_key(row: Row) -> None:
        for builder, value in zip(
            key_builders, key_column_values(pk_attrs, layout, row), strict=True
        ):
            builder.append(value)

    if version_attr is not None:
        version_builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
        for row in rows:
            if assignment_bearing and is_no_op_assignment(layout, assignments, row):
                continue  # per-row no-op elimination (assignment-bearing verbs only)
            append_key(row)
            version_builder.append(cast("int", row[slot_column(layout, version_attr.identity)]))
            matched += 1
        if matched == 0:
            return
        uow.buffer(
            MaterializedWriteGroup(
                mutation=instruction,
                key_attributes=key_attributes,
                key_columns=tuple(whole(builder.build()) for builder in key_builders),
                observations=VersionColumns(versions=whole(version_builder.build())),
            )
        )
        return

    member_columns = members(layout)
    attribute_names = tuple(name for name, (_column, is_vo) in member_columns.items() if not is_vo)
    value_object_names = tuple(name for name, (_column, is_vo) in member_columns.items() if is_vo)
    attribute_builders = {name: ChunkedColumnBuilder[object]() for name in attribute_names}
    value_object_builders = {name: ChunkedColumnBuilder[object]() for name in value_object_names}
    for row in rows:
        if assignment_bearing and is_no_op_assignment(layout, assignments, row):
            continue  # per-row no-op elimination (assignment-bearing verbs only)
        append_key(row)
        payload = predecessor_payload(layout, row)
        for name in attribute_names:
            attribute_builders[name].append(payload[name])
        for name in value_object_names:
            value_object_builders[name].append(payload[name])
        matched += 1
    if matched == 0:
        return
    predecessors = PredecessorColumns(
        shape=PredecessorShape(attributes=attribute_names, value_objects=value_object_names),
        attribute_columns=tuple(
            whole(attribute_builders[name].build()) for name in attribute_names
        ),
        value_object_columns=tuple(
            whole(value_object_builders[name].build()) for name in value_object_names
        ),
    )
    uow.buffer(
        MaterializedWriteGroup(
            mutation=instruction,
            key_attributes=key_attributes,
            key_columns=tuple(whole(builder.build()) for builder in key_builders),
            observations=TemporalColumns(
                predecessors=predecessors, transaction_time_basis=LATEST_PINNED
            ),
        )
    )


def _resolve_rows(conn: DbPort, dialect: Dialect, statement: Statement) -> list[Row]:
    return conn.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
