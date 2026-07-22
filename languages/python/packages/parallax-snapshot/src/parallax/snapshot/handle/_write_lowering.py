"""``parallax.snapshot.handle._write_lowering`` — the write-lowering dispatch.

:func:`lower_write` is the single write-lowering seam: both the developer
transaction path (the ``FlushExecutor`` :meth:`Database.transact` injects) and
the conformance engine call THIS function, so there is exactly one place a
neutral :class:`~parallax.core.unit_work.PlannedWrite` becomes DML. It dispatches
on the entity's FAMILY-EFFECTIVE temporal classification (ADR 0026), composing
`parallax.core.audit_write` / `.bitemp_write`'s neutral milestone plans with the
`m-opt-lock` gate policy this seam owns, and hands the actual SQL rendering to
:mod:`parallax.snapshot.handle._keyed_sql`. :func:`lower_temporal_close` is the
`m-opt-lock` CONFLICT lane's standalone close, rendered through the same seam.

This module sits ABOVE the builders and below nothing else in the package: it
imports `_family`, `_write_types`, and `_keyed_sql`, and none of those imports
back. Its two public names are re-exported through the package's frozen
``__all__``; the temporal-close rendering (`_lower_temporal_write`,
`_render_close`) is read only from here and keeps its underscores.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from parallax.core import audit_write, bitemp_write, inheritance, opt_lock
from parallax.core.base import INFINITY_LITERAL
from parallax.core.descriptor import Entity, Metamodel
from parallax.core.dialect import Dialect
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    Concurrency,
    KeyedWrite,
    Observation,
    PlannedWrite,
    PredicateWrite,
)
from parallax.snapshot.handle._family import (
    axis_columns,
    transaction_time_axis,
    valid_time_axis,
    version_attribute,
)
from parallax.snapshot.handle._keyed_sql import (
    key_predicate,
    lower_batched_update,
    lower_delete,
    lower_insert,
    lower_multi_delete,
    lower_multi_insert,
    lower_predicate_write,
    lower_update,
)
from parallax.snapshot.handle._write_types import LoweredStatement, WriteLoweringError

__all__ = ["lower_temporal_close", "lower_write"]


# The keyed mutation verbs the write seam lowers (the non-temporal write
# triad). The temporal `*Until` / `terminate` verbs open / split / close
# milestones and land with the temporal write path (COR-3 Phase 8 increment 4).
_NON_TEMPORAL_VERBS: Final[frozenset[str]] = frozenset({"insert", "update", "delete"})


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
    temporal close's observed Transaction-Time/Valid-Time gate, is emitted).
    ``tx_instant`` is the flush's Clock-supplied Transaction-Time instant
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
    non-temporal entity's write may be single-row (unchanged since increment 3) or a
    COLLAPSED multi-row instruction the planner's collapse stage produced
    (COR-3 Phase 8 increment 5, `m-batch-write`): a multi-row INSERT, a uniform-value
    IN-list UPDATE, or a non-versioned IN-list DELETE.

    A :class:`~parallax.core.unit_work.PredicateWrite` lowers READLESS
    (`m-batch-write.md` "Predicate-selected readless forms") when its target is
    unversioned and non-temporal — the only shape ever reaches here: a versioned
    or temporal predicate write MATERIALIZES to per-row keyed writes at BUFFER
    time (:func:`~parallax.snapshot.handle._predicate_writes.buffer_predicate`,
    which ``Transaction``'s ``_where`` verbs only delegate to; ADR 0014), before
    ever entering a :class:`FlushPlan`. An INHERITANCE-FAMILY target is refused
    the same way — but NOT only upstream: this function is exported, and the
    conformance engine's readless predicate-write step reaches it straight from
    a deserialized instruction, so the buffer-time rejection is not on every
    road. :func:`~parallax.snapshot.handle._keyed_sql.lower_predicate_write`
    carries its own ``subtype-write-set-based-unsupported`` guard for that
    reason (`python.md` §5 "rejected before SQL").
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        return [LoweredStatement(lower_predicate_write(instruction, meta, dialect))]
    entity = meta.entity(instruction.entity)
    # Temporal classification MUST be the family-EFFECTIVE one (ADR 0026) — see the
    # docstring above.
    declaring = inheritance.declaring_entity(meta, entity)
    if declaring.is_temporal:
        if len(instruction.rows) != 1:
            raise WriteLoweringError(
                f"multi-row temporal {instruction.mutation!r} on {entity.name!r} "
                f"({len(instruction.rows)} rows): a temporal keyed write lowers one row at a "
                "time (m-audit-write / m-bitemp-write) — the set-based batch collapse never "
                "applies to a temporal entity's own milestone chain (m-batch-write)"
            )
        if tx_instant is None:
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
            f"{instruction.mutation!r} is a temporal milestone verb, and {entity.name!r} "
            "declares no temporal dimension — a milestone verb never applies to a "
            "non-temporal entity (m-audit-write / m-bitemp-write)"
        )
    version_attr = version_attribute(declaring)
    if instruction.mutation == "insert":
        if len(instruction.rows) > 1:
            return [
                LoweredStatement(
                    lower_multi_insert(entity, instruction, dialect, meta, declaring, version_attr)
                )
            ]
        return [
            LoweredStatement(
                lower_insert(entity, instruction, dialect, meta, declaring, version_attr)
            )
        ]
    if instruction.mutation == "update":
        if len(instruction.rows) > 1:
            return [
                LoweredStatement(
                    lower_batched_update(
                        entity, instruction, dialect, meta, declaring, version_attr
                    )
                )
            ]
        return [
            LoweredStatement(
                lower_update(
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
    if len(instruction.rows) > 1:
        return [
            LoweredStatement(
                lower_multi_delete(entity, instruction, dialect, meta, declaring, version_attr)
            )
        ]
    return [
        LoweredStatement(
            lower_delete(
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
# reusing the non-temporal helpers below (`key_predicate` for a close's       #
# identity predicate, `lower_insert` unchanged for every chained/opened row — #
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
        # `observation.latest_pinned` from the read's own Transaction-Time pin
        # — a locking-mode write whose only observation is historical or
        # edge-pinned raises `HistoricalObservationError` here.
        opt_lock.check_locking_license(concurrency, latest_pinned=observation.latest_pinned)
    gated = opt_lock.gates(concurrency)
    version_attr = version_attribute(declaring)  # always None for a temporal entity
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
                    lower_insert(entity, synthetic, dialect, meta, declaring, version_attr)
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
    <out_col> = infinity [and <valid.start_col> = ? and <tx.start_col> = ?]`.

    The current-row predicate (``<out_col> = infinity``) and, when gated, the
    Valid-Time discriminator then the observed-``tx_start`` gate — LAST, no exception,
    the direct extension of `m-opt-lock`'s "the gate binds last" to a milestone
    close (`m-audit-write` "Composed predicate order under optimistic mode"). The
    identity predicate (pk, inheritance tag guard) reuses `key_predicate`
    unchanged. Ungated (locking mode) renders neither the Valid-Time discriminator
    nor the Transaction-Time gate, regardless of whether ``step`` carries candidates for
    them — gating is concurrency-driven, never data-driven (`m-bitemp-write`
    "Locking-mode closes are UNGATED").
    """
    tx_axis = transaction_time_axis(declaring)
    tx_start_column, tx_end_column = axis_columns(declaring, tx_axis)
    where_sql, key_binds = key_predicate(meta, entity, step.identity, dialect, declaring)
    where_sql = f"{where_sql} and {dialect.quote(tx_end_column)} = ?"
    key_binds = (*key_binds, INFINITY_LITERAL)
    if gated and step.gate_valid_start is not None:
        valid_axis = valid_time_axis(declaring)
        valid_start_column, _valid_end_column = axis_columns(declaring, valid_axis)
        where_sql = f"{where_sql} and {dialect.quote(valid_start_column)} = ?"
        key_binds = (*key_binds, step.gate_valid_start)
    if gated and step.gate_tx_start is not None:
        where_sql = f"{where_sql} and {dialect.quote(tx_start_column)} = ?"
        key_binds = (*key_binds, step.gate_tx_start)
    table = inheritance.effective_table(meta, entity)
    if table is None:
        raise WriteLoweringError(f"{entity.name!r}: temporal write target has no effective table")
    statement = Statement(
        f"update {table} set {dialect.quote(tx_end_column)} = ? where {where_sql}",
        (tx_instant, *key_binds),
    )
    return LoweredStatement(statement, expected_affected=1, stale_error=not gated)


def lower_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: str,
    observed_tx_start: str | None,
    observed_valid_start: str | None = None,
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
    predicate keys on; ``observed_tx_start`` / ``observed_valid_start`` are the
    gate candidates a conflict case authors explicitly (``when.observedTxStart`` /
    the write row's own ``valid_start``) — never a shadow-tracker lookup, a
    conflict case tests a KNOWN stale-or-fresh value.
    """
    entity = meta.entity(entity_name)
    declaring = inheritance.declaring_entity(meta, entity)
    if observed_tx_start is not None or observed_valid_start is not None:
        opt_lock.check_locking_license(concurrency, latest_pinned=True)
    step = audit_write.MilestoneClose(
        identity=identity,
        gate_tx_start=observed_tx_start,
        gate_valid_start=observed_valid_start,
    )
    gated = opt_lock.gates(concurrency)
    return _render_close(step, entity, declaring, dialect, meta, tx_instant, gated)
