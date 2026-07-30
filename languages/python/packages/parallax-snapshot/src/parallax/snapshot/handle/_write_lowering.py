"""``parallax.snapshot.handle._write_lowering`` — the write-lowering dispatch.

:func:`lower_write` is the single write-lowering seam: both the developer
transaction path (the ``FlushExecutor`` :meth:`Database.transact` injects) and
the conformance engine call THIS function, so there is exactly one place a
neutral :class:`~parallax.core.unit_work.PlannedWrite` becomes DML.

A family whose write finalization has landed crosses TWO seams here rather than
one: :func:`~parallax.snapshot.handle._finalize.finalize_item` settles it into
finalized steps, and :func:`~parallax.snapshot.handle._step_lowering.lower_step`
renders each step physically. What remains in this module is the dispatch for
every family still lowered from the instruction itself — it dispatches on the
entity's FAMILY-EFFECTIVE temporal classification (ADR 0026), composing
`parallax.core.txtime_write` / `.bitemp_write`'s neutral milestone plans with the
`m-opt-lock` gate policy this seam owns, and hands the actual SQL rendering to
:mod:`parallax.snapshot.handle._keyed_sql`. :func:`lower_temporal_close` is the
`m-opt-lock` CONFLICT lane's standalone close, rendered through the same seam.

This module sits ABOVE the builders and below nothing else in the package: it
imports `_family`, `_write_types`, `_keyed_sql`, `_finalize`, and
`_step_lowering`, and none of those imports back. Its two public names are
re-exported through the package's frozen ``__all__``; the temporal-close
rendering (`_lower_temporal_write`, `_render_close`) is read only from here and
keeps its underscores.
"""

from __future__ import annotations

from collections.abc import Mapping

from parallax.core import bitemp_write, opt_lock, txtime_write
from parallax.core.base import INFINITY_LITERAL
from parallax.core.dialect import Dialect
from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.sql_gen import Statement
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.unit_work import (
    LATEST_PINNED,
    Concurrency,
    KeyedWrite,
    PlannedWrite,
    PredicateWrite,
    TemporalObservation,
    TransactionInstant,
    WriteObservation,
)
from parallax.snapshot.handle._family import (
    axis_columns,
    declaring,
    entity_layout,
    entity_of,
    tx_time_axis,
    valid_time_axis,
    version_attribute,
)
from parallax.snapshot.handle._finalize import finalize_item
from parallax.snapshot.handle._keyed_sql import key_predicate, lower_insert
from parallax.snapshot.handle._step_lowering import lower_step
from parallax.snapshot.handle._write_types import LoweredStatement, WriteLoweringError

__all__ = ["lower_temporal_close", "lower_write"]


def _layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView:
    view = entity_layout(meta, entity)
    if view is None:
        raise WriteLoweringError(
            f"{entity.identity.name!r}: temporal write target has no effective table"
        )
    return view


def _is_bitemporal(declaring_entity: EntityMetadata) -> bool:
    return declaring_entity.as_of_axis(TemporalDimension.VALID_TIME) is not None


def lower_write(
    planned: PlannedWrite,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: TransactionInstant,
) -> list[LoweredStatement]:
    """Lower one planned write to its ordered DML statements (m-sql write DML).

    ``planned`` is one execution-ordered item of a :class:`FlushPlan`: a (coalesced,
    FK-ordered, elided) write instruction plus its bound transaction observation and
    affected-rows expectation. ``concurrency`` is the owning unit of work's
    participation mode (m-opt-lock: whether an observation-requiring write's gate —
    a versioned UPDATE's or DELETE's version gate, a temporal close's observed
    Transaction-Time gate — is emitted at all).
    ``tx_instant`` is the attempt's lazy Transaction Instant
    (``FlushPlan.tx_instant``). Only a temporal write consults it, binding the
    close's new ``out_z`` and every chained row's fresh ``in_z``; the
    non-temporal forms leave it uncaptured, which is how a flush that declares no
    Transaction-Time boundary completes without reading the Clock Strategy at all
    (ADR 0010).

    A write whose family finalizes (:func:`~parallax.snapshot.handle._finalize.
    finalize_item`) is settled into steps first and rendered one statement per
    step, consulting neither the concurrency mode nor the instant on the way. That
    is every non-temporal keyed write and every readless predicate write; the
    dispatch below is what the temporal families still lower through.

    The affected-rows expectation each finalized statement carries is still the
    PLAN item's own (`m-opt-lock`), not the step's Affected Rows Policy: the
    policy is settled but not yet enforced, so wiring it here would change
    outcomes ahead of the enforcer that owns them.

    Dispatches on the entity's FAMILY-EFFECTIVE temporal classification (ADR 0026:
    an inheritance participant declares its as-of axes on the root alone, so a
    bare, non-flattening LOCAL view would silently miss a temporal-family concrete's
    own write). A temporal entity's write composes
    `parallax.core.txtime_write` / `parallax.core.bitemp_write`'s neutral milestone
    plan with the `m-opt-lock` gate policy and this seam's existing column/tag
    machinery (reused unchanged for every chained INSERT — value objects,
    inheritance tag derivation, pk-gen markers all compose exactly as a non-temporal
    insert's do, since a chained row is structurally an ordinary full-row insert).
    """
    steps = finalize_item(planned, meta, concurrency)
    if steps is not None:
        # An ungated (locking-mode) shortfall on an observation-requiring write is
        # the same non-retriable stale outcome an ungated close's is: no gate could
        # have caused it, so it is a consistency violation rather than a detected
        # lost update a re-read could resolve (`m-opt-lock`, ADR 0047).
        expected = planned.expected_affected
        return [
            LoweredStatement(
                lower_step(step, meta, dialect),
                expected_affected=expected,
                stale_error=expected is not None and not opt_lock.gates(concurrency),
            )
            for step in steps
        ]
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):  # pragma: no cover - finalization is total here
        raise WriteLoweringError(
            f"{instruction.target.entity!r}: a readless predicate {instruction.mutation!r} is "
            "settled into a Planned Update or Planned Delete, never lowered from the "
            "instruction"
        )
    entity = entity_of(meta, instruction.entity)
    # Temporal classification MUST be the family-EFFECTIVE one (ADR 0026) — see the
    # docstring above.
    declaring_entity = declaring(meta, entity)
    if declaring_entity.declared_as_of_axes:
        if len(instruction.rows) != 1:
            raise WriteLoweringError(
                f"multi-row temporal {instruction.mutation!r} on {entity.identity.name!r} "
                f"({len(instruction.rows)} rows): a temporal keyed write lowers one row at a "
                "time (m-txtime-write / m-bitemp-write) — the set-based batch collapse never "
                "applies to a temporal entity's own milestone chain (m-batch-write)"
            )
        return _lower_temporal_write(
            entity,
            declaring_entity,
            instruction,
            dialect,
            meta,
            concurrency,
            planned.observation,
            tx_instant,
        )
    raise WriteLoweringError(
        f"{instruction.mutation!r} is a temporal milestone verb, and {entity.identity.name!r} "
        "declares no temporal dimension — a milestone verb never applies to a "
        "non-temporal entity (m-txtime-write / m-bitemp-write)"
    )


# --------------------------------------------------------------------------- #
# Temporal (audit-only / bitemporal) keyed writes.                             #
# The MILESTONE PLANNING (which rows close, which chain, split arithmetic) is  #
# `parallax.core.txtime_write` / `.bitemp_write`'s job — pure functions the     #
# scopes themselves never render SQL with. This seam composes their neutral    #
# `MilestonePlan` with the `m-opt-lock` gate policy and RENDERS the SQL,       #
# reusing the non-temporal helpers below (`key_predicate` for a close's       #
# identity predicate, `lower_insert` unchanged for every chained/opened row — #
# value objects, inheritance tag derivation, and pk-gen markers all compose    #
# exactly as they do for an ordinary insert, since a chained row IS one).      #
# --------------------------------------------------------------------------- #
def _lower_temporal_write(
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    concurrency: Concurrency,
    observation: WriteObservation | None,
    tx_instant: TransactionInstant,
) -> list[LoweredStatement]:
    # The milestone arithmetic reads the family's axes through the Temporal
    # Facet, so it takes the write's own target position rather than the
    # declaring one this seam resolves for its column machinery.
    target = entity_of(meta, instruction.entity)
    observed = observation if isinstance(observation, TemporalObservation) else None
    plan_fn = bitemp_write.plan if _is_bitemporal(declaring_entity) else txtime_write.plan
    # Reaching a temporal write is what makes the attempt capture its instant;
    # every milestone bound below, and the close's own new `out_z`, derive from
    # that one value.
    milestone_plan = plan_fn(instruction, meta, target, tx_instant.value(), observed)
    if observed is not None:
        # The REAL licensing check (`m-opt-lock` "Locking mode additionally
        # requires that the observation be of the current milestone"): every
        # engine-supplied temporal observation is latest-pinned by
        # construction (a no-op here), but a real `Transaction.find` records the
        # read's own Transaction-Time pin as the observation's basis — a
        # locking-mode write whose only observation is historical or edge-pinned
        # raises `HistoricalObservationError` here.
        opt_lock.check_locking_license(concurrency, observed.transaction_time_basis)
    gated = opt_lock.gates(concurrency)
    version_attr = version_attribute(meta, declaring_entity)  # always None for a temporal entity
    statements: list[LoweredStatement] = []
    for step in milestone_plan.steps:
        if isinstance(step, txtime_write.MilestoneClose):
            statements.append(
                _render_close(step, entity, declaring_entity, dialect, meta, tx_instant, gated)
            )
        else:
            synthetic = KeyedWrite(mutation="insert", entity=entity.identity.name, rows=(step.row,))
            statements.append(
                LoweredStatement(lower_insert(entity, synthetic, dialect, meta, version_attr))
            )
    return statements


def _render_close(
    step: txtime_write.MilestoneClose,
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    dialect: Dialect,
    meta: Metamodel,
    tx_instant: TransactionInstant,
    gated: bool,
) -> LoweredStatement:
    """`update <table> set <out_col> = ? where <pk> [and <tag.column> = ?]
    [and <valid.end_col> = ?] and <out_col> = infinity [and <tx.start_col> = ?]`.

    The predicate is the ADDRESS then the gate. The address is the identity
    predicate (pk, inheritance tag guard — `key_predicate`, unchanged) followed by
    one exclusive upper bound per As-Of Axis in canonical axis order: the observed
    rectangle's Valid-Time end where that axis exists, then the invariant
    ``<out_col> = infinity`` that keeps an operational close on the current
    milestone. Every component of it renders in BOTH concurrency modes (ADR 0046) —
    which stored row the close means to close never depends on the mode.

    Only the observed-``tx_start`` gate is mode-dependent, and it binds LAST, no
    exception — the direct extension of `m-opt-lock`'s "the gate binds last" to a
    milestone close (`m-txtime-write` "Composed predicate order under optimistic
    mode"). Ungated (locking mode) renders no gate at all, regardless of whether
    ``step`` carries a candidate for one: gating is concurrency-driven, never
    data-driven (`m-bitemp-write` "Locking-mode closes are UNGATED").
    """
    layout = _layout(meta, entity)
    tx_axis = tx_time_axis(declaring_entity)
    tx_start_column, tx_end_column = axis_columns(layout, tx_axis)
    where_sql, key_binds = key_predicate(meta, entity, step.identity, dialect)
    if _is_bitemporal(declaring_entity):
        if step.target_valid_end is None:
            raise WriteLoweringError(
                f"bitemporal close on {entity.identity.name!r}: no observed Valid-Time end "
                "supplied — a Bitemporal milestone address needs one exclusive upper bound "
                "per As-Of Axis (m-bitemp-write 'Address and gate are separate')"
            )
        valid_axis = valid_time_axis(declaring_entity)
        _valid_start_column, valid_end_column = axis_columns(layout, valid_axis)
        where_sql = f"{where_sql} and {dialect.quote(valid_end_column)} = ?"
        key_binds = (*key_binds, step.target_valid_end)
    where_sql = f"{where_sql} and {dialect.quote(tx_end_column)} = ?"
    key_binds = (*key_binds, INFINITY_LITERAL)
    if gated and step.gate_tx_start is not None:
        where_sql = f"{where_sql} and {dialect.quote(tx_start_column)} = ?"
        key_binds = (*key_binds, step.gate_tx_start)
    statement = Statement(
        f"update {layout.layout.table.name} set {dialect.quote(tx_end_column)} = ? "
        f"where {where_sql}",
        (tx_instant.value(), *key_binds),
    )
    return LoweredStatement(statement, expected_affected=1, stale_error=not gated)


def lower_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    meta: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: TransactionInstant,
    observed_tx_start: str | None,
    observed_valid_end: str | None = None,
) -> LoweredStatement:
    """Lower a STANDALONE temporal milestone close — the `m-opt-lock` CONFLICT
    lane's own shape (`m-txtime-write` / `m-bitemp-write`: "a conflict case runs
    only that single gated close, not the replacement INSERT(s) a full write
    would go on to emit"). Every REAL temporal mutation (`txtime_write.plan` /
    `bitemp_write.plan`) chains at least one row for a close-bearing verb — the
    conflict lane's own probe is not one of those verbs, so this composes the
    SAME close-rendering seam (:func:`_render_close`) directly from an
    :class:`~parallax.core.txtime_write.MilestoneClose`, never through the
    plan dispatch.

    ``identity`` is the (at minimum, primary-key) row the close's identity
    predicate keys on, and ``observed_valid_end`` completes its address on a
    Bitemporal target; ``observed_tx_start`` is the gate candidate. Both observed
    values are authored explicitly by a conflict case (``when.observedTxStart`` /
    the write row's own ``valid_end``) — never a shadow-tracker lookup, a conflict
    case tests a KNOWN stale-or-fresh value.
    """
    entity = entity_of(meta, entity_name)
    declaring_entity = declaring(meta, entity)
    if observed_tx_start is not None:
        opt_lock.check_locking_license(concurrency, LATEST_PINNED)
    step = txtime_write.MilestoneClose(
        identity=identity,
        target_valid_end=observed_valid_end,
        gate_tx_start=observed_tx_start,
    )
    gated = opt_lock.gates(concurrency)
    return _render_close(step, entity, declaring_entity, dialect, meta, tx_instant, gated)
