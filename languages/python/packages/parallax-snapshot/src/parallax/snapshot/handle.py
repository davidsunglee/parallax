"""``parallax.snapshot.handle`` — the composition surface (connect / transact / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
flush planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.FlushPlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. :func:`lower_write` is the single
lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

M4 lowered the non-temporal keyed write forms; COR-3 Phase 8 increment 3 added the
``m-opt-lock`` version gate/advance and inheritance-family DML; increment 4 adds the
**temporal** milestone forms — audit-only close-and-chain and full-bitemporal
rectangle splits (``insert`` / ``update`` / ``terminate`` and the bounded ``*Until``
trio), composing `parallax.core.audit_write` / `.bitemp_write`'s neutral milestone
planning with the ``m-opt-lock`` gate policy this seam already owns. Predicate-
selected (set-based) writes and multi-row batch collapse still land with a later
write increment; reaching one raises a loud :class:`WriteLoweringError` naming the
deferral, never a wrong emission — mirroring the read compiler's forward-error
posture.

The **developer transaction surface** (spec §5) also composes here:
:meth:`Database.connect` wires a concrete ``m-db-port`` adapter to a metamodel,
and :meth:`Database.transact` is the callback demarcation — sentinel-backed
options, join with the option-conflict check, the ``m-auto-retry`` bounded retry
loop, and the injected flush executor that lowers each planned write and runs it
on the transaction's own connection. Per ledger D-16 (COR-3 Phase 7 increment
6a, full graduation) the :class:`Transaction` verbs take entity instances:
``insert(instance)`` (the Create Payload), ``update(edited_copy)`` (the sparse
row: primary key + effective change set), ``delete(node_or_instance)`` (keys
off it); :meth:`Database.find` / :meth:`Transaction.find` both wrap the SAME
production find executor below in ``Snapshot[T]`` (DQ6).

:meth:`Transaction.find` participates in the transaction (force-flush +
read-your-own-writes, the transaction's own lock suffix) by running the shared
:func:`find` / :func:`find_history` executor through
:meth:`~parallax.core.unit_work.UnitOfWork.read` — root canonicalization
(``m-temporal-read`` + ``m-navigate``) happens inside the shared executor via
``parallax.core.deep_fetch.plan``, never re-derived here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core import audit_write, bitemp_write, deep_fetch, inheritance, op_algebra, opt_lock
from parallax.core.auto_retry import run_with_retry
from parallax.core.base import INFINITY_LITERAL
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.descriptor import AsOfAttribute, Attribute, Entity, Metamodel, column_order
from parallax.core.dialect import POSTGRES, Dialect, LockMode
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import Statement as EntityStatement
from parallax.core.entity import (
    canonical_row,
    effective_change_set,
    entity_record_of,
    full_row,
    primary_key_row,
)
from parallax.core.sql_gen import Statement, apply_family_variant, compile_read, family_variant_plan
from parallax.core.temporal_read import AXIS_ORDER, LATEST, Edge, Pin, milestone_edge, statement_pin
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    FlushExecutor,
    FlushPlan,
    KeyedWrite,
    ObjectKey,
    Observation,
    PlannedWrite,
    PredicateWrite,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    active_unit_of_work,
    instructions,
    object_key,
    run_unit_of_work,
    validate_write,
)
from parallax.snapshot import materialize, wrap

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "LoweredStatement",
    "MilestoneGraph",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "Transaction",
    "TransactionOptionConflictError",
    "WriteLoweringError",
    "connect",
    "find",
    "find_history",
    "lower_temporal_close",
    "lower_write",
]

# The keyed mutation verbs the write seam lowers (the non-temporal write
# triad). The temporal `*Until` / `terminate` verbs open / split / close
# milestones and land with the temporal write path (COR-3 Phase 8 increment 4).
_NON_TEMPORAL_VERBS: Final[frozenset[str]] = frozenset({"insert", "update", "delete"})

# A scalar cell's recognized DB-computed marker kinds (`m-pk-gen`;
# `write-instruction.schema.json#/$defs/writeComputedMarker`): `computed` (the
# `max` strategy's `coalesce(max(col), ?) + ?` INSERT fold) and `increment`
# (a self-referential `col = col + ?` SET advance, e.g. a sequence registry's
# `next_val`). Each is legal only at the mutation that can render it.
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


class WriteLoweringError(ValueError):
    """A planned write cannot be lowered to DML by the keyed write seam (the
    deferred forms — predicate-selected / set-based, multi-row batch collapse —
    raise here, never a wrong emission)."""


@dataclass(frozen=True, slots=True)
class LoweredStatement:
    """One lowered DML statement plus its optimistic-lock affected-row EXPECTATION.

    ``expected_affected`` is the count the caller MUST see this ``statement`` affect
    (``None`` means no expectation — an insert, an unversioned/unobserved write, or a
    chained/opened temporal row: `m-audit-write` "Chained INSERTs carry no
    expectation"). A non-temporal keyed write lowers to exactly ONE statement, so its
    own expectation (unchanged from increment 3, `~parallax.core.unit_work.PlannedWrite.
    expected_affected`) rides here too. A temporal write lowers to MULTIPLE statements
    (a close, then zero-to-three chained opens) — only the close carries an
    expectation (always ``1``, `m-audit-write` "The close UPDATE MUST affect exactly
    one row" — unconditional on gating), never the whole planned write, since a
    chained INSERT's own affected-row count is meaningless as a conflict signal.

    ``stale_error`` distinguishes the TWO zero-row-close outcomes on a mismatch: a
    GATED (optimistic) mismatch is the retriable ``m-opt-lock`` conflict
    (:class:`~parallax.core.opt_lock.OptimisticLockConflictError`, unchanged from
    increment 3 — every non-temporal expectation and every gated temporal close sets
    this ``False``); an UNGATED (locking-mode) temporal close's mismatch is the
    distinct NON-retriable :class:`~parallax.core.opt_lock.StaleWriteError`
    (``stale_error=True`` — the shared read lock, not a gate, was supposed to make it
    correct, so a zero-row outcome is a consistency violation, not a detected lost
    update).
    """

    statement: Statement
    expected_affected: int | None = None
    stale_error: bool = False


def lower_write(
    planned: PlannedWrite,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str | None = None,
) -> list[LoweredStatement]:
    """Lower one planned write to its ordered DML statements (m-sql write DML).

    ``planned`` is one execution-ordered item of a :class:`FlushPlan`: a (coalesced,
    FK-ordered, elided) write instruction plus its bound transaction observation and
    affected-rows expectation. ``concurrency`` is the owning unit of work's
    participation mode (m-opt-lock: whether a versioned UPDATE's version gate, or a
    temporal close's observed-in_z/business-discriminator gate, is emitted).
    ``tx_instant`` is the flush's Clock-supplied processing instant
    (``FlushPlan.tx_instant``) — REQUIRED for a temporal write (bound as the close's
    new ``out_z`` and every chained row's fresh ``in_z``), unused by the non-temporal
    forms.

    Dispatches on the entity's FAMILY-EFFECTIVE temporal classification (ADR 0026:
    an inheritance participant declares its as-of axes on the root alone, so
    `entity.is_temporal` — a bare, non-flattening LOCAL view — would silently miss a
    temporal-family concrete's own write). A temporal entity's write composes
    `parallax.core.audit_write` / `parallax.core.bitemp_write`'s neutral milestone
    plan with the `m-opt-lock` gate policy and this seam's existing descriptor-driven
    column/tag machinery (reused unchanged for every chained INSERT — value objects,
    inheritance tag derivation, pk-gen markers all compose exactly as a non-temporal
    insert's do, since a chained row is structurally an ordinary full-row insert). A
    non-temporal entity's write is unchanged from increment 3 (insert / update /
    delete, plain or inheritance-family, versioned or not, pk-generated or not).
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        raise WriteLoweringError(
            f"predicate-selected (set-based) write on {instruction.target.entity!r}: "
            "materialize-then-lower lands with the write path (COR-3 Phase 8 increment 5; "
            "m-batch-write / m-opt-lock)"
        )
    entity = meta.entity(instruction.entity)
    # Temporal classification MUST be the family-EFFECTIVE one (ADR 0026) — see the
    # docstring above.
    declaring = inheritance.declaring_entity(meta, entity)
    if len(instruction.rows) != 1:
        raise WriteLoweringError(
            f"multi-row keyed {instruction.mutation!r} on {entity.name!r} "
            f"({len(instruction.rows)} rows): the set-based collapse lands with the write path "
            "(COR-3 Phase 8 increment 5; m-batch-write) — this seam lowers single-row keyed "
            "writes only"
        )
    if declaring.is_temporal:
        if tx_instant is None:  # pragma: no cover - defends a caller that skips the Clock
            raise WriteLoweringError(
                f"temporal write on {entity.name!r}: no transaction instant supplied "
                "(FlushPlan.tx_instant) — a temporal write cannot lower without one"
            )
        return _lower_temporal_write(
            entity,
            declaring,
            instruction,
            dialect,
            meta,
            concurrency,
            planned.observation,
            tx_instant,
        )
    if instruction.mutation not in _NON_TEMPORAL_VERBS:
        raise WriteLoweringError(
            f"{instruction.mutation!r} is a temporal milestone verb; its lowering lands with the "
            f"write path (COR-3 Phase 8 increment 4) — {entity.name!r} is not a temporal entity"
        )
    version_attr = _version_attribute(declaring)
    if instruction.mutation == "insert":
        return [
            LoweredStatement(
                _lower_insert(entity, instruction, dialect, meta, declaring, version_attr)
            )
        ]
    if instruction.mutation == "update":
        return [
            LoweredStatement(
                _lower_update(
                    entity,
                    instruction,
                    dialect,
                    meta,
                    declaring,
                    version_attr,
                    planned.observation,
                    concurrency,
                ),
                expected_affected=planned.expected_affected,
            )
        ]
    return [
        LoweredStatement(
            _lower_delete(
                entity, instruction, dialect, meta, declaring, version_attr, planned.observation
            ),
            expected_affected=planned.expected_affected,
        )
    ]


# --------------------------------------------------------------------------- #
# Temporal (audit-only / bitemporal) keyed writes (COR-3 Phase 8 increment 4). #
# The MILESTONE PLANNING (which rows close, which chain, split arithmetic) is  #
# `parallax.core.audit_write` / `.bitemp_write`'s job — pure functions the     #
# scopes themselves never render SQL with. This seam composes their neutral    #
# `MilestonePlan` with the `m-opt-lock` gate policy and RENDERS the SQL,       #
# reusing the non-temporal helpers below (`_key_predicate` for a close's       #
# identity predicate, `_lower_insert` unchanged for every chained/opened row — #
# value objects, inheritance tag derivation, and pk-gen markers all compose    #
# exactly as they do for an ordinary insert, since a chained row IS one).      #
# --------------------------------------------------------------------------- #
def _lower_temporal_write(
    entity: Entity,
    declaring: Entity,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    concurrency: Concurrency,
    observation: Observation | None,
    tx_instant: str,
) -> list[LoweredStatement]:
    plan_fn = bitemp_write.plan if declaring.temporal == "bitemporal" else audit_write.plan
    milestone_plan = plan_fn(instruction, declaring, tx_instant, observation)
    if observation is not None:
        # The REAL licensing check (`m-opt-lock` "Locking mode additionally
        # requires that the observation be of the current milestone"): every
        # engine-supplied temporal observation is latest-pinned by
        # construction (a no-op here), but a real `Transaction.find` observes
        # `observation.latest_pinned` from the read's own processing-axis pin
        # — a locking-mode write whose only observation is historical or
        # edge-pinned raises `HistoricalObservationError` here.
        opt_lock.check_locking_license(concurrency, latest_pinned=observation.latest_pinned)
    gated = opt_lock.gates(concurrency)
    version_attr = _version_attribute(declaring)  # always None for a temporal entity
    statements: list[LoweredStatement] = []
    for step in milestone_plan.steps:
        if isinstance(step, audit_write.MilestoneClose):
            statements.append(
                _render_close(step, entity, declaring, dialect, meta, tx_instant, gated)
            )
        else:
            synthetic = KeyedWrite(mutation="insert", entity=entity.name, rows=(step.row,))
            statements.append(
                LoweredStatement(
                    _lower_insert(entity, synthetic, dialect, meta, declaring, version_attr)
                )
            )
    return statements


def _render_close(
    step: audit_write.MilestoneClose,
    entity: Entity,
    declaring: Entity,
    dialect: Dialect,
    meta: Metamodel,
    tx_instant: str,
    gated: bool,
) -> LoweredStatement:
    """`update <table> set <out_col> = ? where <pk> [and <tag.column> = ?] and
    <out_col> = infinity [and <business.from_col> = ? and <in_col> = ?]`.

    The current-row predicate (``<out_col> = infinity``) and, when gated, the
    business discriminator then the observed-``in_z`` gate — LAST, no exception,
    the direct extension of `m-opt-lock`'s "the gate binds last" to a milestone
    close (`m-audit-write` "Composed predicate order under optimistic mode"). The
    identity predicate (pk, inheritance tag guard) reuses `_key_predicate`
    unchanged. Ungated (locking mode) renders neither the business discriminator
    nor the ``in_z`` gate, regardless of whether ``step`` carries candidates for
    them — gating is concurrency-driven, never data-driven (`m-bitemp-write`
    "Locking-mode closes are UNGATED").
    """
    proc = _processing_axis(declaring)
    where_sql, key_binds = _key_predicate(meta, entity, step.identity, dialect, declaring)
    where_sql = f"{where_sql} and {dialect.quote(proc.to_column)} = ?"
    key_binds = (*key_binds, INFINITY_LITERAL)
    if gated and step.gate_from_z is not None:
        biz = _business_axis(declaring)
        where_sql = f"{where_sql} and {dialect.quote(biz.from_column)} = ?"
        key_binds = (*key_binds, step.gate_from_z)
    if gated and step.gate_in_z is not None:
        where_sql = f"{where_sql} and {dialect.quote(proc.from_column)} = ?"
        key_binds = (*key_binds, step.gate_in_z)
    statement = Statement(
        f"update {entity.table} set {dialect.quote(proc.to_column)} = ? where {where_sql}",
        (tx_instant, *key_binds),
    )
    return LoweredStatement(statement, expected_affected=1, stale_error=not gated)


def _processing_axis(declaring: Entity) -> AsOfAttribute:
    return next(aoa for aoa in declaring.as_of_attributes if aoa.axis == "processing")


def _business_axis(declaring: Entity) -> AsOfAttribute:
    return next(aoa for aoa in declaring.as_of_attributes if aoa.axis == "business")


def lower_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    observed_in_z: str | None,
    observed_business_from: str | None = None,
) -> LoweredStatement:
    """Lower a STANDALONE temporal milestone close — the `m-opt-lock` CONFLICT
    lane's own shape (`m-audit-write` / `m-bitemp-write`: "a conflict case runs
    only that single gated close, not the replacement INSERT(s) a full write
    would go on to emit"). Every REAL temporal mutation (`audit_write.plan` /
    `bitemp_write.plan`) chains at least one row for a close-bearing verb — the
    conflict lane's own probe is not one of those verbs, so this composes the
    SAME close-rendering seam (:func:`_render_close`) directly from an
    :class:`~parallax.core.audit_write.MilestoneClose`, never through the
    plan dispatch.

    ``identity`` is the (at minimum, primary-key) row the close's identity
    predicate keys on; ``observed_in_z`` / ``observed_business_from`` are the
    gate candidates a conflict case authors EXPLICITLY (``when.observedInZ`` /
    the write row's own ``businessFrom``) — never a shadow-tracker lookup, a
    conflict case tests a KNOWN stale-or-fresh value.
    """
    entity = meta.entity(entity_name)
    declaring = inheritance.declaring_entity(meta, entity)
    if observed_in_z is not None or observed_business_from is not None:
        opt_lock.check_locking_license(concurrency, latest_pinned=True)
    step = audit_write.MilestoneClose(
        identity=identity, gate_in_z=observed_in_z, gate_from_z=observed_business_from
    )
    gated = opt_lock.gates(concurrency)
    return _render_close(step, entity, declaring, dialect, meta, tx_instant, gated)


def _version_attribute(declaring: Entity) -> Attribute | None:
    """``declaring``'s own ``optimisticLocking`` version attribute, if any.

    ``declaring`` is already the FAMILY-EFFECTIVE declaring entity (the root for
    an inheritance participant, `inheritance.declaring_entity` — the version
    column is family-wide metadata declared only there, `m-opt-lock` "The
    version column"; ADR 0027), so a plain local scan of its own attributes is
    correct without a further family walk.
    """
    return next((attr for attr in declaring.attributes if attr.optimistic_locking), None)


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


def _lower_insert(
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
        return Statement(f"insert into {entity.table}({columns}) values ({holes})", tuple(binds))
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
        f"insert into {entity.table}({columns}) select {select_list} from {entity.table} t0",
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


def _lower_update(
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

    A versioned row whose SET already carries an EXPLICIT value for the version
    attribute (the M4-era plain-column-data shape some existing corpus witnesses
    carry, e.g. `m-unit-work-005`) passes it through unchanged, sorted by
    columnOrder like any other authored field: no observation is required, no
    advance is computed, no gate is emitted — exactly the pre-COR-3-Phase-8-
    increment-3 behavior. Every OTHER versioned row's SET derives the advance
    from this unit of work's own recorded observation (`m-opt-lock.
    require_observed` / `.advance`), raising before any DML if this unit of work
    never observed the row's version, and gates on it in optimistic mode only
    (`m-opt-lock.gates`).
    """
    row = dict(instruction.rows[0])
    pk_columns = {attr.column for attr in inheritance.family_primary_key(meta, entity)}
    carries_version = version_attr is not None and version_attr.name in row
    observed_version: int | None = None
    version_bind: int | None = None
    if version_attr is not None and not carries_version:
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
    where_sql, key_binds = _key_predicate(meta, entity, row, dialect, declaring)
    if version_attr is not None and not carries_version and opt_lock.gates(concurrency):
        assert observed_version is not None  # derived above whenever not carries_version
        where_sql = f"{where_sql} and {dialect.quote(version_attr.column)} = ?"
        key_binds = (*key_binds, observed_version)
    assignments = ", ".join(assignment_parts)
    return Statement(
        f"update {entity.table} set {assignments} where {where_sql}", (*binds, *key_binds)
    )


def _increment_amount(value: object) -> int | None:
    if _marker_kind(value) == "increment":
        return cast("int", cast("Mapping[str, object]", value)["increment"])
    return None


def _lower_delete(
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
    where_sql, key_binds = _key_predicate(meta, entity, row, dialect, declaring)
    if version_attr is not None:
        observed_version = opt_lock.require_observed(entity.name, observation)
        where_sql = f"{where_sql} and {dialect.quote(version_attr.column)} = ?"
        key_binds = (*key_binds, observed_version)
    return Statement(f"delete from {entity.table} where {where_sql}", key_binds)


def _ordered_cells(
    meta: Metamodel,
    entity: Entity,
    row: Mapping[str, object],
    extra_columns: Mapping[str, object] | None = None,
) -> list[tuple[str, object]]:
    """The row's present members (plus any framework-derived ``extra_columns``,
    e.g. an inheritance tag) as `(column, bind)` pairs, in family columnOrder.

    Each row key names a declared scalar attribute or a value object, resolved
    FAMILY-WIDE (`_members`) so an inheritance participant's inherited members
    lower correctly; a value-object member binds as one :class:`JsonDocument` in
    its columnOrder position (the whole document — the write never decomposes
    it), a scalar binds its value (or its DB-computed marker document verbatim,
    classified by the caller).
    """
    members = _members(meta, entity)
    order = {column: index for index, column in enumerate(_family_column_order(meta, entity))}
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        column, is_value_object = members[name]
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
    document_columns = [vo.column for member in chain for vo in member.value_objects]
    return [*pk_columns, *tag_columns, *rest_columns, *document_columns]


def _key_predicate(
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


def _members(meta: Metamodel, entity: Entity) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(column, is_value_object)`, FAMILY-WIDE
    (`inheritance.family_attributes` / `.superset_value_objects` — both already
    degrade to ``entity``'s own declarations for a non-participant)."""
    members: dict[str, tuple[str, bool]] = {
        attr.name: (attr.column, False) for attr in inheritance.family_attributes(meta, entity)
    }
    for value_object in inheritance.superset_value_objects(meta, (entity.name,)):
        members[value_object.name] = (value_object.column, True)
    return members


# --------------------------------------------------------------------------- #
# The production find executor (m-deep-fetch / m-snapshot-read; COR-3 Phase 7  #
# increment 5). The module DAG's snapshot-handle scope already reaches         #
# `materialize` + `m-sql` + `m-db-port`, so the deliberate DAG-forbidden edges  #
# (`m-deep-fetch`/`m-snapshot-read` may not import `m-sql`; `m-sql` may not    #
# import `m-navigate`/`m-temporal-read`) are composed HERE, exactly like       #
# `lower_write` composes the write-side `m-unit-work` x `m-sql` edge above —   #
# one executor, production-owned: `db.find`/`tx.find` (a later increment) and  #
# the conformance run lane both call the SAME `find`/`find_history`, wrap or   #
# render the SAME neutral `materialize.Node`s, and no engine-local level loop  #
# exists anywhere in this codebase.                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ExecutedStatement:
    """One statement this executor actually ran (or would run — the caller's own
    compile-eligibility posture is not this module's concern). ``duration`` is
    the WALL-CLOCK seconds the port's own ``execute`` call took — informational
    only (spec §3: never graded, never used for control flow)."""

    sql: str
    binds: tuple[object, ...]
    duration: float = 0.0


@dataclass(frozen=True, slots=True)
class Execution:
    """The ordered record of every statement one `find` / `find_history` call
    executed — the production analogue of the conformance adapter's `emissions`
    + `roundTrips`, built once here and consumed by both."""

    statements: tuple[ExecutedStatement, ...]

    @property
    def round_trips(self) -> int:
        return len(self.statements)


class NoResultFound(RuntimeError):
    """``Snapshot.result()`` matched zero roots (spec §2/§3)."""


class TooManyResultsFound(RuntimeError):
    """``Snapshot.result()`` / ``.result_or_none()`` matched more than one root
    (spec §2/§3)."""


class Snapshot[T]:
    """The Python reification of a core Snapshot Graph (spec §3): ``db.find`` /
    ``tx.find``'s result. The complete surface: :meth:`result`,
    :meth:`result_or_none`, :meth:`results` (a FRESH ``list[T]`` per call),
    :attr:`pin` (the lowered as-of coordinates — only genuinely PINNED axes; a
    scanned axis is absent), :attr:`execution` (per-statement ``sql`` /
    ``binds``, informational ``duration``, and ``round_trips``), and
    ``__repr__``. Deliberately ABSENT: iteration / ``len`` / truthiness /
    indexing on the container, refresh or write methods, and any lazy
    behavior — every accessor is a pure in-memory read over roots already
    materialized in full by ``db.find`` / ``tx.find``.
    """

    __slots__ = ("_execution", "_pin", "_roots")

    _roots: tuple[T, ...]
    _pin: Pin
    _execution: Execution

    def __init__(self, roots: tuple[T, ...], pin: Pin, execution: Execution) -> None:
        self._roots = roots
        self._pin = pin
        self._execution = execution

    def result(self) -> T:
        """The single matched root; raises on zero or more than one."""
        count = len(self._roots)
        if count == 0:
            raise NoResultFound("the snapshot matched no roots")
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected exactly 1")
        return self._roots[0]

    def result_or_none(self) -> T | None:
        """The single matched root, or ``None`` on zero; raises on more than one."""
        count = len(self._roots)
        if count == 0:
            return None
        if count > 1:
            raise TooManyResultsFound(f"the snapshot matched {count} roots, expected 0 or 1")
        return self._roots[0]

    def results(self) -> list[T]:
        """Every matched root as an ordinary ``list[T]`` the caller owns (a
        fresh copy per call — this accessor is unaffected by node immutability)."""
        return list(self._roots)

    @property
    def pin(self) -> Pin:
        """The statement's OWN lowered as-of coordinates (spec §3): only
        genuinely pinned axes — a scanned (``history`` / ``as_of_range``) axis
        is absent, per the core rule that a scan is not a pin."""
        return self._pin

    @property
    def execution(self) -> Execution:
        """This find's execution record (per-statement ``sql`` / ``binds``,
        informational ``duration``, and ``round_trips``)."""
        return self._execution

    def __repr__(self) -> str:
        return (
            f"Snapshot(roots={len(self._roots)}, pin={self._pin!r}, "
            f"round_trips={self._execution.round_trips})"
        )


@dataclass(frozen=True, slots=True)
class FindResult:
    """A single-graph find's root nodes plus its execution record.

    ``all_nodes`` is EVERY node this find materialized — root and every
    attached deep-fetch level — paired with its OWN target entity name (the
    same name a subsequent keyed write on that row would carry, `m-unit-work`
    `KeyedWrite.entity`): the seam :meth:`Transaction.find` walks to record a
    versioned row's observed version (`m-opt-lock`), since ``Node`` itself
    carries no entity identity of its own (m-snapshot-read: a neutral,
    class-free field dict).
    """

    nodes: tuple[materialize.Node, ...]
    execution: Execution
    all_nodes: tuple[tuple[str, materialize.Node], ...] = ()


@dataclass(frozen=True, slots=True)
class MilestoneGraph:
    """One `history` / `asOfRange` milestone's own edge-pinned graph (m-snapshot-
    read "The whole-graph pin"): ``pin`` maps each declared as-of attribute name
    to its edge (from-instant) coordinate for this milestone; ``nodes`` is the
    root-only graph at that milestone (a v1 milestone-set graph carries no
    includes, m-case-format)."""

    pin: Mapping[str, object]
    nodes: tuple[materialize.Node, ...]


@dataclass(frozen=True, slots=True)
class HistoryFindResult:
    """A milestone-set find's ordered per-milestone graphs plus its (single-
    statement) execution record."""

    graphs: tuple[MilestoneGraph, ...]
    execution: Execution


def find(
    op: op_algebra.Operation,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    port: DbPort,
    *,
    lock: LockMode | None = None,
) -> FindResult:
    """The one per-level deep-fetch / snapshot-materialization loop (m-deep-fetch
    "one query per non-empty relationship level"; m-snapshot-read "round trips").

    ``op`` is the read's raw operation: a `DeepFetch` node, or any other read
    operation planned with zero levels (root-only instance-form materialization
    — a plain snapshot read, or the source find behind a scenario `mutate`
    action). Canonicalizes the root query (`m-temporal-read` + `m-navigate`,
    composed here — the M2 precedent), compiles and executes it, then for each
    planned level: gathers the distinct non-null parent keys; an empty gathered
    set attaches the empty/null relationship result and issues no child SQL; a
    back-reference level issues no SQL either (resolved via the assembler's own
    graph-local identity map); otherwise compiles and executes ONE child query
    (declared relationship ordering rendered through the dialect's NULLs-last
    rule), applies `familyVariant` materialization (`m-sql`) to its rows, and
    feeds the assembler. Returns the root's own materialized nodes — reached
    from them, every attached level's nodes hang off `Node.fields` — plus the
    full ordered execution record.
    """
    plan_ = deep_fetch.plan(target, op, meta)
    statements: list[ExecutedStatement] = []

    root_statement = compile_read(
        plan_.root_operation, meta, dialect, target, result_form="instance", lock=lock
    )
    root_rows = _execute(port, dialect, root_statement, statements)
    root_plan = family_variant_plan(meta, target, plan_.root_operation)
    root_rows = [apply_family_variant(row, root_plan) for row in root_rows]

    assembler = materialize.Assembler(meta=meta)
    root_nodes = assembler.materialize_root(target, root_rows)
    all_nodes: list[tuple[str, materialize.Node]] = [(target, node) for node in root_nodes]

    level_rows: list[Sequence[Row]] = []
    level_nodes: list[list[materialize.Node]] = []
    for level in plan_.levels:
        parent_rows, parent_nodes = _parent_data(
            level.parent, root_rows, root_nodes, level_rows, level_nodes
        )
        if level.is_back_reference:
            nodes = assembler.attach_level(level, parent_nodes, parent_rows, None)
            level_rows.append(())
            level_nodes.append(nodes)
            continue
        keys = _distinct_keys(parent_rows, level.parent_column)
        if not keys:
            nodes = assembler.attach_level(level, parent_nodes, parent_rows, None)
            level_rows.append(())
            level_nodes.append(nodes)
            continue
        child_target, child_op = level.child_operation(keys)
        child_statement = compile_read(
            child_op,
            meta,
            dialect,
            child_target,
            result_form="instance",
            lock=lock,
            relationship_order=True,
        )
        rows = _execute(port, dialect, child_statement, statements)
        variant_plan = family_variant_plan(meta, child_target, child_op)
        rows = [apply_family_variant(row, variant_plan) for row in rows]
        nodes = assembler.attach_level(level, parent_nodes, parent_rows, rows)
        level_rows.append(rows)
        level_nodes.append(nodes)
        all_nodes.extend((child_target, node) for node in nodes)

    return FindResult(
        nodes=tuple(root_nodes), execution=Execution(tuple(statements)), all_nodes=tuple(all_nodes)
    )


def find_history(
    op: op_algebra.Operation, meta: Metamodel, dialect: Dialect, target: str, port: DbPort
) -> HistoryFindResult:
    """The milestone-set snapshot read (m-snapshot-read "The whole-graph pin";
    m-case-format "Milestone-set graphs"): `history` / `asOfRange` return the
    full matching milestone SET in one statement, partitioned here by each
    row's own edge (`~parallax.core.temporal_read.milestone_edge`) into one
    root-only graph per milestone — no levels (a v1 milestone-set graph carries
    no includes). Rows are grouped in chronological edge order (business axis
    first, matching the corpus's own authored `then.graphs` order) rather than
    relying on the database's unspecified natural row order.
    """
    plan_ = deep_fetch.plan(target, op, meta)
    if plan_.levels:
        raise ValueError(  # pragma: no cover - m-case-format: v1 carries no includes
            "a milestone-set (history / asOfRange) read carries no deep-fetch levels"
        )
    # `inheritance.declaring_entity` resolves the entity whose `as_of_attributes`
    # are this target's FAMILY's actual temporal declaration (the root, for a
    # participant — temporality is family-wide, `m-inheritance`); every
    # `~parallax.core.temporal_read` per-entity primitive below (`milestone_edge`,
    # `_edge_pin`, `_edge_sort_key`) MUST resolve through it rather than the
    # queried target's own (possibly locally-empty) `as_of_attributes`.
    entity = inheritance.declaring_entity(meta, meta.entity(target))
    statement = compile_read(plan_.root_operation, meta, dialect, target, result_form="instance")
    statements: list[ExecutedStatement] = []
    rows = _execute(port, dialect, statement, statements)

    order: list[Edge] = []
    groups: dict[Edge, list[Row]] = {}
    for row in sorted(rows, key=lambda row: _edge_sort_key(entity, row)):
        edge = milestone_edge(entity, row)
        if edge not in groups:
            groups[edge] = []
            order.append(edge)
        groups[edge].append(row)

    graphs = tuple(
        MilestoneGraph(
            pin=_edge_pin(entity, edge),
            nodes=tuple(materialize.Assembler(meta=meta).materialize_root(target, groups[edge])),
        )
        for edge in order
    )
    return HistoryFindResult(graphs=graphs, execution=Execution(tuple(statements)))


def _execute(
    port: DbPort, dialect: Dialect, statement: Statement, statements: list[ExecutedStatement]
) -> list[Row]:
    started = time.perf_counter()
    rows = port.execute(dialect.to_driver_sql(statement.sql), list(statement.binds))
    statements.append(
        ExecutedStatement(statement.sql, statement.binds, time.perf_counter() - started)
    )
    return rows


def _parent_data(
    parent: deep_fetch.ParentRef,
    root_rows: Sequence[Row],
    root_nodes: Sequence[materialize.Node],
    level_rows: Sequence[Sequence[Row]],
    level_nodes: Sequence[list[materialize.Node]],
) -> tuple[Sequence[Row], Sequence[materialize.Node]]:
    if isinstance(parent, deep_fetch.RootRef):
        return root_rows, root_nodes
    return level_rows[parent.index], level_nodes[parent.index]


def _distinct_keys(rows: Sequence[Row], column: str) -> list[op_algebra.Scalar]:
    """The distinct NON-NULL values of ``column`` across ``rows``, in first-
    encountered order (m-deep-fetch: the gathered set is unordered for grading
    purposes — an implementation MUST NOT sort at runtime to match a fixture —
    so encounter order is as good as any, and deterministic run to run).

    A gathered key is always a declared PRIMARY-KEY (or unique FK) attribute's
    own value — one of `m-op-algebra`'s neutral scalar types — even though the
    port's own row values are typed as plain ``object`` (`m-db-port`); the cast
    reflects that runtime invariant, not a widening of the membership node's
    own typed-literal contract.
    """
    values = dict.fromkeys(row[column] for row in rows if row[column] is not None)
    return cast("list[op_algebra.Scalar]", list(values))


def _edge_sort_key(entity: Entity, row: Row) -> tuple[object, ...]:
    """Business axis first, then processing (m-sql's own bind-order convention),
    each axis's own from-column value — used only to chronologically order a
    milestone-set read's grouped graphs, never to select or filter rows."""
    ordered = sorted(entity.as_of_attributes, key=lambda aoa: AXIS_ORDER[aoa.axis])
    return tuple(row[aoa.from_column] for aoa in ordered)


def _edge_pin(entity: Entity, edge: Edge) -> dict[str, object]:
    """The milestone-set `then.graphs` `pin` entry: each declared as-of attribute
    name mapped to its edge (from-instant) coordinate on that axis."""
    return {
        aoa.name: (edge.business if aoa.axis == "business" else edge.processing)
        for aoa in entity.as_of_attributes
    }


# --------------------------------------------------------------------------- #
# The developer transaction surface (spec §5) — connect / transact.           #
# --------------------------------------------------------------------------- #


class TransactionOptionConflictError(ValueError):
    """A joining ``db.transact`` call tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    (non-``None``) option whose value conflicts with the outermost boundary's
    resolved setting raises; an explicit equal value and an omitted option are
    accepted (spec §5).
    """


@dataclass(frozen=True, slots=True)
class _ResolvedOptions:
    """The outermost boundary's resolved ``db.transact`` options.

    ``concurrency`` also lives on the core :class:`TransactionSettings`;
    ``retries`` and ``retry_optimistic_conflicts`` are demarcation-level only
    (the core unit of work never sees them). ``retry_optimistic_conflicts`` is
    stored for the join/conflict contract but cannot alter retry classification
    yet — no optimistic-conflict error category exists until ``m-opt-lock``
    (COR-3 Phase 8; see ``parallax.core.auto_retry``).
    """

    retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class _Demarcation:
    """What the outermost boundary publishes on the unit of work's ``companion``.

    A joining ``db.transact`` call needs the same :class:`Transaction` to hand
    its closure and the boundary's resolved options for the conflict check;
    both ride core's single per-thread active binding, so their visibility ends
    exactly when it does (no handle-owned thread-local, nothing to clean up).
    """

    tx: Transaction
    options: _ResolvedOptions


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure (spec §5).

    A facade over the active unit of work and the transaction's own connection.
    The graduated D-16 verbs take entity instances: :meth:`insert` a full
    instance (the Create Payload), :meth:`update` an edited copy (the sparse
    row: primary key + effective change set — an empty effective set is a
    no-op, zero round trips), :meth:`delete` a node or instance (keys off its
    primary key). :meth:`find` runs a participating read and returns
    ``Snapshot[T]`` (DQ6): force-flush + the transaction's own lock suffix,
    otherwise identical to :meth:`Database.find`. A reference used after its
    owning scope ends raises
    :class:`~parallax.core.unit_work.EscapedTransactionError` (every verb
    delegates to the unit of work, which fences use-after-scope).
    """

    __slots__ = ("_conn", "_dialect", "_meta", "_uow")

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DbPort,
        meta: Metamodel,
        dialect: Dialect,
    ) -> None:
        self._uow = uow
        self._conn = conn
        self._meta = meta
        self._dialect = dialect

    def insert(self, instance: EntityBase) -> None:
        """Buffer a keyed ``insert`` of a full instance (the Create Payload,
        spec §5): every member the instance actually SET."""
        record = _entity_record_of_instance(instance)
        self._buffer("insert", record.name, full_row(instance))

    def update(self, copy: EntityBase) -> None:
        """Buffer a sparse keyed ``update``: primary key + the effective change
        set of an edited copy (touched fields whose current value differs from
        the recorded original, spec §3/§5). An EMPTY effective change set
        issues no DML at all (zero round trips, the net-zero-chain no-op rule
        — the no-op-first ordering `m-opt-lock` fixes: dropped before any
        observation or locking concern). Raises
        :class:`~parallax.core.entity.ProvenanceError` for a provenance-less
        instance (never produced via ``model_copy``). The version column, if
        any, is never authored here — it is framework-owned end to end
        (`m-opt-lock`; ADR 0013): the write seam derives its advance from this
        unit of work's own recorded observation at lowering
        (`parallax.snapshot.handle.lower_write`), never from the edited copy."""
        record = _entity_record_of_instance(copy)
        effective = effective_change_set(copy)
        if not effective:
            return
        row: dict[str, object] = primary_key_row(copy)
        row.update(canonical_row(copy, effective))
        self._buffer("update", record.name, row)

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values, spec §5)."""
        record = _entity_record_of_instance(node_or_instance)
        self._buffer("delete", record.name, primary_key_row(node_or_instance))

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Run a participating read for ``statement`` and return ``Snapshot[T]``
        (DQ6): force-flushes pending writes first (read-your-own-writes), and
        the transaction's participation mode renders the read-lock suffix
        (``locking`` takes the dialect's shared row lock; ``optimistic`` takes
        none). Otherwise identical to :meth:`Database.find` — the SAME shared
        find executor, the SAME frozen-node wrapping. Returns ``Snapshot[Any]``:
        the concrete root type is resolved only at runtime (from the
        statement's own target), so callers annotate their own binding
        (``snapshot: Snapshot[Order] = tx.find(...)``) for static typing.

        Every materialized node of a VERSIONED entity — root and included
        (deep-fetch) alike — records its observed version on this unit of work
        (`m-opt-lock`; ADR 0013), in EITHER concurrency mode: a later keyed
        update/delete of that SAME object derives its version advance (and,
        under optimistic concurrency, its gate) from THIS observation, never
        from an implicit resolving read at write time. Every materialized node
        of a TEMPORAL entity likewise records its observed processing-from
        (`in_z`) plus PIN PROVENANCE (`Observation.latest_pinned`, derived from
        this statement's own processing-axis pin below): a later temporal
        write's close/chain, or a locking-mode write's historical-observation
        license (`~parallax.core.opt_lock.check_locking_license`), derives from
        THIS observation, never a shadow lookup or an implicit resolving read
        (a MILESTONE-SET read — `.history()` / `.as_of_range()` — records
        nothing here; its own dispatch branch returns before this point).
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = _statement_pin(op, entity)
        lock = self._uow.settings.concurrency
        if _is_milestone_set_op(op):
            history_result = self._uow.read(
                lambda: find_history(op, self._meta, self._dialect, target, self._conn)
            )
            return _snapshot_from_history_result(history_result, target, self._meta)
        find_result = self._uow.read(
            lambda: find(op, self._meta, self._dialect, target, self._conn, lock=lock)
        )
        _record_observations(self._uow, self._meta, find_result, pin)
        return _snapshot_from_find_result(find_result, target, self._meta, pin)

    def _buffer(
        self,
        mutation: str,
        entity: str,
        row: Mapping[str, object],
        *,
        business_from: str | None = None,
        business_to: str | None = None,
    ) -> None:
        # The document route buys the IR's structural validation (no `at` alias,
        # no observation keys) first (`deserialize`), then the model-aware
        # `validate_write` (the SAME validator the conformance engine's
        # rejected lane calls, COR-3 Phase 8 increment 2 — one validator, two
        # callers): its inheritance payload-shape checks
        # (`subtype-write-metadata-field` / `-sibling-attribute` /
        # `-set-based-unsupported`, m-inheritance) classify a framework-owned
        # metadata key or a cross-branch field MORE SPECIFICALLY than the
        # generic member-name-honesty gate below ever could, so it runs
        # first — member-name honesty (`validate_instruction`) still catches
        # any OTHERWISE-unknown member a validate_write pass left unexamined
        # (it walks only DECLARED members, never flags a stray key itself).
        #
        # `business_from` / `business_to` extend this neutral seam for a TEMPORAL
        # keyed write (COR-3 Phase 8 increment 4): the typed verbs above never
        # pass them (temporal developer verbs are COR-3 Phase 8 increment 7), so
        # every existing call site is unaffected; the conformance engine's own
        # temporal write translation is the sole caller that does (`m-audit-write`
        # / `m-bitemp-write` — the axis-explicit `businessFrom` / `businessTo`
        # instruction fields, never smuggled onto `row`, ADR 0010/0013).
        doc: dict[str, object] = {"mutation": mutation, "entity": entity, "rows": [dict(row)]}
        if business_from is not None:
            doc["businessFrom"] = business_from
        if business_to is not None:
            doc["businessTo"] = business_to
        instruction = instructions.deserialize(doc)
        validate_write(self._meta.entity(entity), row, self._meta, mutation=mutation)
        instructions.validate_instruction(instruction, self._meta)
        self._uow.buffer(instruction)


def _record_observations(uow: UnitOfWork, meta: Metamodel, result: FindResult, pin: Pin) -> None:
    """Record this unit of work's observed version/temporal-milestone for
    every VERSIONED or TEMPORAL node :func:`find` materialized (`m-opt-lock`;
    ADR 0013; Phase-8 mid-phase review remediation).

    Keyed by the SAME ``(entity name, ordered pk pairs)`` shape a subsequent
    keyed write's own :func:`~parallax.core.unit_work.object_key` computes —
    ``entity_name`` here is the node's OWN queried/attached target (never
    family-normalized to the root), matching `KeyedWrite.entity`'s own
    convention (a developer's later ``tx.update(copy)`` names its instance's
    OWN class). A node whose (family-effective) primary key, version column,
    or processing-axis interval is absent from its own materialized fields is
    defensively skipped — never reachable for a well-formed corpus model, but
    this seam takes no data on faith. A versioned entity is never also
    temporal (`m-opt-lock`/`m-descriptor`: the two are mutually exclusive), so
    each node takes exactly one branch.

    ``pin`` is the STATEMENT's OWN lowered as-of coordinates
    (``Transaction.find``'s own ``_statement_pin`` call): the whole-graph pin
    propagates per hop, matched by axis, to every temporal entity in the
    include tree (spec §3), so this SAME root-level processing-axis pin
    licenses every attached temporal node's own recorded observation — an
    omitted axis or an explicit `LATEST` pin is latest-pinned; an explicit
    as-of instant is not (`~parallax.core.opt_lock.check_locking_license`'s
    own historical-observation rule).
    """
    latest_pinned = pin.processing is None or pin.processing is LATEST
    for entity_name, node in result.all_nodes:
        entity = meta.entity(entity_name)
        declaring = inheritance.declaring_entity(meta, entity)
        pk_attrs = declaring.primary_key
        if not pk_attrs or any(  # pragma: no cover - defends a malformed model/projection
            attr.column not in node.fields for attr in pk_attrs
        ):
            continue
        key: ObjectKey = (
            entity_name,
            tuple((attr.name, node.fields[attr.column]) for attr in pk_attrs),
        )
        version_attr = _version_attribute(declaring)
        if version_attr is not None:
            if version_attr.column in node.fields:
                uow.observe(key, Observation(version=cast("int", node.fields[version_attr.column])))
            continue
        if not declaring.is_temporal:
            continue
        proc = _processing_axis(declaring)
        if proc.from_column not in node.fields:  # pragma: no cover - malformed model/projection
            continue
        uow.observe(key, _temporal_observation(meta, declaring, node, proc, latest_pinned))


def _temporal_observation(
    meta: Metamodel,
    declaring: Entity,
    node: materialize.Node,
    proc: AsOfAttribute,
    latest_pinned: bool,
) -> Observation:
    """The :class:`Observation` a materialized TEMPORAL node licenses: the
    observed processing-from (``in_z``) plus pin provenance always; the
    observed business bounds and payload too when ``declaring`` is
    bitemporal — the same fields temporal lowering (`~parallax.core.
    bitemp_write.plan`) already consumes, so a transaction-scoped find ->
    temporal write sequence works end-to-end, not just the licensing check.
    """
    in_z = cast("str", node.fields[proc.from_column])
    if declaring.temporal != "bitemporal":
        return Observation(in_z=in_z, latest_pinned=latest_pinned)
    biz = _business_axis(declaring)
    if biz.from_column not in node.fields or biz.to_column not in node.fields:  # pragma: no cover
        return Observation(in_z=in_z, latest_pinned=latest_pinned)  # malformed model/projection
    excluded = {proc.from_column, proc.to_column, biz.from_column, biz.to_column}
    payload = {
        name: node.fields[column]
        for name, (column, _is_value_object) in _members(meta, declaring).items()
        if column in node.fields and column not in excluded
    }
    return Observation(
        in_z=in_z,
        business_from=cast("str", node.fields[biz.from_column]),
        business_to=cast("str", node.fields[biz.to_column]),
        payload=payload,
        latest_pinned=latest_pinned,
    )


def _entity_record_of_instance(instance: EntityBase) -> Entity:
    record = entity_record_of(type(instance))
    if record is None:  # pragma: no cover - guards a non-Parallax-compiled class
        raise TypeError(f"{type(instance).__name__} is not a registered Parallax entity class")
    return record


def _statement_pin(op: op_algebra.Operation, entity: Entity) -> Pin:
    """``snapshot.pin`` for ``op`` (spec §3): identical to
    ``~parallax.core.temporal_read.statement_pin``, except that an outer
    ``DeepFetch`` directive (``.include(...)`` composed after ``.as_of(...)``)
    is peeled first. ``m-temporal-read`` never imports ``m-deep-fetch`` (the
    DAG forbids the reverse dependency direction), so `statement_pin`'s own
    directive-peeling (`Limit`/`OrderBy`/`Distinct` only) cannot see a
    `DeepFetch` wrapper — this composition, mirroring the M2 precedent, is the
    handle's own job. A milestone-set read (`.history()`/`.as_of_range()`)
    never carries an outer `DeepFetch` (`Statement.include`/`.history`/
    `.as_of_range` mutually refuse the combination, spec §3
    ``snapshot-history-includes``), so this peel is unconditionally safe.
    """
    pin_op = op.operand if isinstance(op, op_algebra.DeepFetch) else op
    return statement_pin(pin_op, entity)


def _is_milestone_set_op(op: op_algebra.Operation) -> bool:
    """Whether ``op``'s temporal wrapper SCANS an axis (``history`` /
    ``as_of_range``) rather than pinning it — the milestone-set find shape
    (spec §3 "one root per milestone")."""
    current: op_algebra.Operation = op
    while isinstance(current, (op_algebra.Limit, op_algebra.OrderBy, op_algebra.Distinct)):
        current = current.operand
    return isinstance(current, (op_algebra.AsOfRange, op_algebra.History))


def _pin_from_milestone(entity: Entity, milestone_pin: Mapping[str, object]) -> Pin:
    """One milestone's own edge, rendered as a :class:`Pin` (spec §3: each
    milestone-set root is edge-pinned at its own milestone's from-instant)."""
    coords: dict[str, object] = {}
    for aoa in entity.as_of_attributes:
        if aoa.name in milestone_pin:
            coords[aoa.axis] = milestone_pin[aoa.name]
    return Pin(
        processing=cast("Any", coords.get("processing")),
        business=cast("Any", coords.get("business")),
    )


def _snapshot_from_find_result(
    result: FindResult, target: str, meta: Metamodel, pin: Pin
) -> Snapshot[Any]:
    roots = wrap.wrap_graph(result.nodes, target, meta, pin)
    return Snapshot(roots, pin, result.execution)


def _snapshot_from_history_result(
    result: HistoryFindResult, target: str, meta: Metamodel
) -> Snapshot[Any]:
    entity = inheritance.declaring_entity(meta, meta.entity(target))
    roots: list[Any] = []
    for graph in result.graphs:
        milestone_pin = _pin_from_milestone(entity, graph.pin)
        roots.extend(wrap.wrap_graph(graph.nodes, target, meta, milestone_pin))
    return Snapshot(tuple(roots), Pin(), result.execution)


class Database:
    """A connected Parallax database handle: one adapter, one metamodel (spec §5)."""

    __slots__ = ("_clock", "_dialect", "_meta", "_port")

    def __init__(
        self,
        port: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> None:
        self._port = port
        self._meta = meta
        self._dialect = dialect
        self._clock: Clock = clock if clock is not None else SystemClock()

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the metamodel it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port. ``dialect``
        defaults to the sole adapter's; ``clock`` defaults to the system clock
        (inject a fixed clock in tests).
        """
        return cls(adapter, meta, dialect=dialect, clock=clock)

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Execute ``statement`` exactly once, materializing fully, and return
        ``Snapshot[T]`` (spec §3). Non-transactional: no read lock, no
        participation mode. ``.history()`` / ``.as_of_range()`` return one root
        per milestone, each edge-pinned at its own milestone's from-instant.
        Returns ``Snapshot[Any]``: the concrete root type is resolved only at
        runtime (from the statement's own target), so callers annotate their
        own binding (``snapshot: Snapshot[Order] = db.find(...)``) for static
        typing.
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = _statement_pin(op, entity)
        if _is_milestone_set_op(op):
            history_result = find_history(op, self._meta, self._dialect, target, self._port)
            return _snapshot_from_history_result(history_result, target, self._meta)
        find_result = find(op, self._meta, self._dialect, target, self._port)
        return _snapshot_from_find_result(find_result, target, self._meta, pin)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
    ) -> T:
        """Run ``fn(tx)`` in a transaction, returning its value only after commit.

        Every option is sentinel-backed (spec §5): ``None`` means *apply the
        outermost defaults when this call opens the transaction* (``retries=10``,
        ``concurrency="locking"``, ``retry_optimistic_conflicts=False``) *and
        inherit the active transaction's settings when it joins one*. A call
        while a transaction is active on the current thread joins it — the
        closure receives the **same** :class:`Transaction`, its value returns
        immediately, and an explicit option that conflicts with the boundary
        raises :class:`TransactionOptionConflictError`. The outermost boundary
        owns commit, abort, and the ``m-auto-retry`` bounded retry loop; abort
        withholds the callback value, and an inner failure dooms the whole
        transaction (rollback-only) even if caught.
        """
        active = active_unit_of_work()
        if active is not None:
            demarcation = active.companion
            if not isinstance(demarcation, _Demarcation):
                raise UnitOfWorkError(
                    "a bare unit of work is active on this thread; db.transact can "
                    "only join a transaction it opened"
                )
            _check_join_options(
                demarcation.options,
                retries=retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
            )
            # The join path returns immediately and ignores these arguments in
            # favor of the active transaction's own (m-unit-work); rollback-only
            # foreclosure happens before the closure runs.
            return run_unit_of_work(
                lambda _: fn(demarcation.tx),
                settings=active.settings,
                clock=active.clock,
                meta=active.meta,
                flush_executor=active.flush_executor,
            )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "locking",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
        )

        def attempt() -> T:
            def in_txn(conn: DbPort) -> T:
                def body(uow: UnitOfWork) -> T:
                    tx = Transaction(uow, conn, self._meta, self._dialect)
                    # Published for joining calls; visible only while core's
                    # active-transaction binding is, so it needs no cleanup.
                    uow.companion = _Demarcation(tx=tx, options=options)
                    return fn(tx)

                return run_unit_of_work(
                    body,
                    settings=TransactionSettings(concurrency=options.concurrency),
                    clock=self._clock,
                    meta=self._meta,
                    flush_executor=_flush_executor(
                        conn, self._meta, self._dialect, options.concurrency
                    ),
                )

            return self._port.transaction(in_txn)

        return run_with_retry(attempt, retries=options.retries)


# The spec §8 module-level spelling of the composition-root entry point.
connect = Database.connect


def _check_join_options(
    active: _ResolvedOptions,
    *,
    retries: int | None,
    concurrency: Concurrency | None,
    retry_optimistic_conflicts: bool | None,
) -> None:
    """Refuse a joining call's explicit option that conflicts with the boundary."""
    _refuse_conflict("retries", retries, active.retries)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict(
        "retry_optimistic_conflicts", retry_optimistic_conflicts, active.retry_optimistic_conflicts
    )


def _refuse_conflict(name: str, explicit: object | None, active_value: object) -> None:
    if explicit is not None and explicit != active_value:
        raise TransactionOptionConflictError(
            f"cannot join the active transaction with {name}={explicit!r}: the boundary "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)"
        )


def _flush_executor(
    conn: DbPort, meta: Metamodel, dialect: Dialect, concurrency: Concurrency
) -> FlushExecutor:
    """The unit of work's injected flush sink: lower each planned write, execute
    every lowered statement in order, and enforce each STATEMENT's own
    affected-rows expectation (`m-opt-lock`; `m-audit-write`; `m-bitemp-write`).

    The single write-lowering seam (:func:`lower_write`) run on the transaction's
    own connection, inside the still-open ``port.transaction`` scope — so an
    abort rolls back force-flushed writes with everything else. Checking is
    PER-STATEMENT, not per-planned-write: a non-temporal keyed write lowers to
    exactly one statement (its own expectation, unchanged from increment 3), while
    a temporal write lowers to a close then zero-to-three chained opens — only the
    close carries an expectation (always ``1``), so a mismatch there raises and
    ABORTS BEFORE the chained rows ever execute (`m-audit-write` "MUST NOT silently
    succeed and proceed to chain"). ``LoweredStatement.stale_error`` picks the raised
    class: the retriable :class:`~parallax.core.opt_lock.OptimisticLockConflictError`
    for a gated mismatch (every non-temporal expectation, and a gated temporal
    close), the non-retriable :class:`~parallax.core.opt_lock.StaleWriteError` for an
    ungated (locking-mode) temporal close's mismatch.
    """

    def execute(plan: FlushPlan) -> None:
        for planned in plan.writes:
            for lowered in lower_write(planned, meta, dialect, concurrency, plan.tx_instant):
                affected = conn.execute_write(
                    dialect.to_driver_sql(lowered.statement.sql), list(lowered.statement.binds)
                )
                if lowered.expected_affected is not None and affected != lowered.expected_affected:
                    raise _conflict_error(planned, meta, affected, lowered)

    return execute


def _conflict_error(
    planned: PlannedWrite, meta: Metamodel, actual: int | None, lowered: LoweredStatement
) -> opt_lock.OptimisticLockConflictError | opt_lock.StaleWriteError:
    """The affected-row-mismatch error for one lowered statement — the retriable
    gated conflict, or (``lowered.stale_error``) the non-retriable ungated
    temporal-close outcome (`m-audit-write` / `m-bitemp-write`)."""
    instruction = planned.instruction
    assert isinstance(instruction, KeyedWrite)  # only a keyed write ever carries an expectation
    key = object_key(instruction, meta)
    assert key is not None  # an expectation is attached only alongside a resolved object key
    assert lowered.expected_affected is not None  # the caller's own guard
    error_cls = (
        opt_lock.StaleWriteError if lowered.stale_error else opt_lock.OptimisticLockConflictError
    )
    return error_cls(
        instruction.entity, key[1], lowered.expected_affected, actual if actual is not None else 0
    )
