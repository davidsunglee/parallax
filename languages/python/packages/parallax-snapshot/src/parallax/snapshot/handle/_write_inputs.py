"""``parallax.snapshot.handle._write_inputs`` — verb-input preparation and observations.

Everything a write verb needs BEFORE an instruction reaches the unit of work,
plus the observation machinery a read leaves behind for it:

* build-time window validation every keyed AND ``_where`` temporal verb shares
  (:func:`validate_valid_from`, :func:`validate_until`), the finite-Transaction-
  Time-pin refusal every keyed verb runs on its source instance
  (:class:`TransactionTimePinReadOnlyError`, :func:`validate_source_pin`,
  :func:`source_pin`), and the sparse keyed ``update`` row
  (:func:`prepare_sparse_row`);
* instance -> record resolution (:func:`entity_record_of_instance`) and the
  verb-time license key (:func:`observation_key`);
* observation recording after a real :func:`~parallax.snapshot.handle.find`
  (:func:`record_observations`) and its row-form twin for a materializing
  predicate-write resolve (:func:`materialize_row`), which share their payload
  extraction through the module-local ``_temporal_observation`` / ``_row_payload``.

Depends on :mod:`parallax.snapshot.handle._family` (family-effective axes,
version attribute, member-to-column map) and — for the
:class:`~parallax.snapshot.handle.FindResult` :func:`record_observations`
consumes — on :mod:`parallax.snapshot.handle._read`. That edge is deliberately
one-way: the pin helpers ``Transaction.find`` shares with the read executor stay
in ``_read``, so ``_read`` never imports this module.

Names crossing a module boundary (read from ``_transaction`` / ``_predicate_writes``)
are spelled bare; a helper whose every caller lives here keeps its underscore.
Privacy is carried by this MODULE's leading underscore and by the package's
frozen ``__all__``, never by per-name underscores —
:class:`TransactionTimePinReadOnlyError` and :func:`validate_source_pin` are
additionally re-exported through that ``__all__`` (the conformance engine's
scenario grading shares the exact validator the developer verbs run).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.base import normalize_instant
from parallax.core.db_port import Row
from parallax.core.descriptor import AsOfAxisMetadata, Attribute, Entity, Metamodel
from parallax.core.entity import Entity as EntityBase

# `entity_record_of` is the core registry lookup this module's own
# `entity_record_of_instance` wraps (it adds the not-a-Parallax-entity refusal):
# near-miss spellings, deliberately both visible here.
from parallax.core.entity import (
    canonical_row,
    effective_change_set,
    entity_record_of,
    primary_key_row,
)
from parallax.core.temporal_read import LATEST, Latest, Pin
from parallax.core.unit_work import (
    KeyedMutation,
    ObjectKey,
    Observation,
    UnitOfWork,
    instant_literal,
)
from parallax.snapshot.handle._family import (
    axis_columns,
    members,
    tx_time_axis,
    valid_time_axis,
    version_attribute,
)
from parallax.snapshot.handle._read import FindResult

__all__ = [
    "TransactionTimePinReadOnlyError",
    "entity_record_of_instance",
    "materialize_row",
    "observation_key",
    "prepare_sparse_row",
    "record_observations",
    "source_pin",
    "validate_source_pin",
    "validate_until",
    "validate_valid_from",
]


class TransactionTimePinReadOnlyError(ValueError):
    """A mutation verb's source view is pinned at a finite Transaction-Time
    instant (`m-temporal-read`'s finite-pin mutation row; `m-identity-map`):
    the Transaction-Time past records what the system knew and is never
    rewritten, so the verb refuses at the call — before any buffering — and
    emits no DML. This is the neutral application-lifecycle error the
    conformance contract reports as ``errorClass:
    transaction-time-pin-read-only`` (`m-conformance-adapter`), distinct from
    the `m-db-error` database taxonomy. A ``LATEST`` Transaction-Time pin and
    a finite Valid-Time pin stay writable — the Valid-Time case is the
    retroactive correction that lowers to the `m-bitemp-write` rectangle
    split."""

    code: Final[str] = "transaction-time-pin-read-only"


def observation_key(record: Entity, declaring: Entity, instance: object) -> ObjectKey:
    """The ``(entity name, ordered pk pairs)`` observation key for a WRITTEN
    instance — the same shape :func:`record_observations` records under (the
    instance's OWN entity name, never family-normalized; pk pairs by canonical
    attribute name, in the declaring entity's primary-key order) and
    `unit_work.object_key` computes at flush, so a verb-time license lookup
    and the flush-time attach can never diverge."""
    row = primary_key_row(instance)
    return (record.name, tuple((attr.name, row[attr.name]) for attr in declaring.primary_key))


def record_observations(uow: UnitOfWork, meta: Metamodel, result: FindResult, pin: Pin) -> None:
    """Record this unit of work's observed version/temporal-milestone for
    every VERSIONED or TEMPORAL node :func:`find` materialized (`m-opt-lock`;
    ADR 0013; Phase-8 mid-phase review remediation).

    Keyed by the SAME ``(entity name, ordered pk pairs)`` shape a subsequent
    keyed write's own :func:`~parallax.core.unit_work.object_key` computes —
    ``entity_name`` here is the node's OWN queried/attached target (never
    family-normalized to the root), matching `KeyedWrite.entity`'s own
    convention (a developer's later ``tx.update(copy)`` names its instance's
    OWN class). A node whose (family-effective) primary key, version column,
    or Transaction-Time interval is absent from its own materialized fields is
    defensively skipped — never reachable for a well-formed corpus model, but
    this seam takes no data on faith. A versioned entity is never also
    temporal (`m-opt-lock`/`m-descriptor`: the two are mutually exclusive), so
    each node takes exactly one branch.

    ``pin`` is the STATEMENT's OWN lowered as-of coordinates
    (``Transaction.find``'s own ``deep_fetch_statement_pin`` call): the whole-graph pin
    propagates per hop, matched by axis, to every temporal entity in the
    include tree (spec §3), so this SAME root-level Transaction-Time pin
    licenses every attached temporal node's own recorded observation — an
    omitted axis or an explicit `LATEST` pin is latest-pinned; an explicit
    as-of instant is not (`~parallax.core.opt_lock.check_locking_license`'s
    own historical-observation rule).
    """
    latest_pinned = pin.tx_time is None or pin.tx_time is LATEST
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
        version_attr = version_attribute(declaring)
        if version_attr is not None:
            if version_attr.column in node.fields:
                uow.observe(key, Observation(version=cast("int", node.fields[version_attr.column])))
            continue
        if not declaring.is_temporal:
            continue
        tx_axis = tx_time_axis(declaring)
        tx_start_column, _tx_end_column = axis_columns(declaring, tx_axis)
        if tx_start_column not in node.fields:  # pragma: no cover - malformed model/projection
            continue
        uow.observe(
            key,
            _temporal_observation(meta, declaring, node.fields, tx_axis, latest_pinned),
        )


def _temporal_observation(
    meta: Metamodel,
    declaring: Entity,
    fields: Mapping[str, object],
    tx_axis: AsOfAxisMetadata,
    latest_pinned: bool,
) -> Observation:
    """The :class:`Observation` a materialized TEMPORAL row licenses: the
    observed Transaction-Time start (``in_z``) plus pin provenance always, PLUS the
    observed payload (D-30, COR-3 Phase 8 increment 7 completion round — every
    real ``Transaction.find`` of a temporal row now carries one, audit-only
    included) — the same fields temporal lowering (`~parallax.core.
    txtime_write.plan` / `~parallax.core.bitemp_write.plan`) already consumes,
    so a transaction-scoped find -> temporal write sequence works end-to-end,
    not just the licensing check. The observed Valid-Time bounds are Bitemporal-only.

    ``fields`` is a plain column-keyed mapping — a materialized
    :class:`~parallax.snapshot.materialize.Node`'s own ``.fields`` (a real
    ``Transaction.find``), or a raw driver row (COR-3 Phase 8 increment 5's
    materializing predicate-write resolve, :func:`materialize_row`) — so both
    callers share the SAME payload-extraction logic rather than duplicating it.
    Every extracted value passes through EXACTLY as the port returned it (a
    real ``timestamptz`` column may be a driver-native ``datetime.datetime``
    or the native-infinity sentinel, never pre-rendered to a wire string here)
    — the SAME driver-native-passthrough contract every other temporal bind in
    this seam already carries (`test_transaction_reads.py::
    test_optimistic_mode_temporal_write_after_an_as_of_find_gates_on_observed_in_z`);
    wire-rendering for REPORTING is the conformance ADAPTER's own boundary
    concern (`parallax.conformance.engine._json_bind`), never this seam's.

    The bitemporal payload KEEPS a value-object document whenever ``fields``
    carries one (`include_value_objects=True` below; confirmation-pass
    residual P2): a real ``Transaction.find`` is always INSTANCE-form, which
    projects every document unconditionally (`m-sql`), so ``fields`` already
    carries it there; a materializing predicate-write resolve's ROW-form
    ``fields`` carries one whenever its own need-sensitive projection
    requested it (`_predicate_writes._materialize_predicate_write`'s
    ``needs_documents``, which — completing residual P2 — requests it for
    EVERY bitemporal mutation this branch ever sees: update, updateUntil,
    terminate, terminateUntil alike, since the rectangle split chains all
    four) — ``column in fields`` still gates every member exactly as it does
    for scalars, so this is a no-op only for a VO-free entity, and never
    drops one `bitemp_write.plan`'s head/middle/tail split (`_merged_payload`
    / the old-payload rectangles) needs to carry forward whole
    (`m-bitemp-write` "head/tail old values"; `m-value-object` "the document
    rides every chained/split row whole").
    """
    tx_start_column, tx_end_column = axis_columns(declaring, tx_axis)
    tx_start = cast("str", fields[tx_start_column])
    if declaring.temporal != "bitemporal":
        # Audit-only (D-30): the observed payload every other member besides
        # the sole Transaction-Time axis — `txtime_write.plan`'s own update-branch
        # merge (`_merged_row`) overlays a public `tx.update(copy)`'s SPARSE
        # row onto it, so an unauthored field carries forward from THIS
        # observation rather than being silently dropped.
        payload = _row_payload(
            meta,
            declaring,
            fields,
            {tx_start_column, tx_end_column},
            include_value_objects=True,
        )
        return Observation(tx_start=tx_start, payload=payload, latest_pinned=latest_pinned)
    valid_axis = valid_time_axis(declaring)
    valid_start_column, valid_end_column = axis_columns(declaring, valid_axis)
    if valid_start_column not in fields or valid_end_column not in fields:  # pragma: no cover
        return Observation(
            tx_start=tx_start, latest_pinned=latest_pinned
        )  # malformed model/projection
    excluded = {tx_start_column, tx_end_column, valid_start_column, valid_end_column}
    payload = _row_payload(meta, declaring, fields, excluded, include_value_objects=True)
    return Observation(
        tx_start=tx_start,
        valid_start=cast("str", fields[valid_start_column]),
        valid_end=cast("str", fields[valid_end_column]),
        payload=payload,
        latest_pinned=latest_pinned,
    )


def _row_payload(
    meta: Metamodel,
    declaring: Entity,
    fields: Mapping[str, object],
    excluded: set[str],
    *,
    include_value_objects: bool = False,
) -> dict[str, object]:
    """``fields``'s own payload (every declared member besides ``excluded``
    axis-bound columns) — the observed-payload source a real TEMPORAL find's
    :class:`Observation` (`_temporal_observation`, above — audit-only and
    bitemporal alike, D-30) and an audit-only materializing resolve's CHAINED
    full row (:func:`materialize_row`) share.

    Value-object columns are OMITTED by default (row-form never projects one,
    `m-value-object-047`'s own byte-identical row-form witness).
    ``include_value_objects`` opts in (`m-case-format.md:727`): its callers —
    `_temporal_observation`'s audit-only and bitemporal branches alike (every
    real ``Transaction.find``, always INSTANCE-form, so ``fields`` always
    carries one; a materializing resolve only when its own need-sensitive
    projection requested it) and `materialize_row`'s audit-only chain merge
    (an audit-only materializing resolve, same gate) — so ``column in
    fields`` still gates every member exactly as it already does for
    scalars; a VO-free entity's empty ``value_objects`` makes this flag a
    no-op either way.
    """
    return {
        name: fields[column]
        for name, (column, is_value_object) in members(meta, declaring).items()
        if (include_value_objects or not is_value_object)
        and column in fields
        and column not in excluded
    }


# --------------------------------------------------------------------------- #
# Predicate-write materialization (COR-3 Phase 8 increment 5; m-opt-lock      #
# "Predicate-selected writes materialize when observations are needed";       #
# ADR 0014) — plus the build-time window/no-op validators every keyed AND     #
# `_where` temporal verb shares (`validate_valid_from` / `validate_until`#
# / `prepare_sparse_row`, S4/N2 COR-3 Phase 8 increment 7 remediation).       #
# `materialize_row`/`_apply_assignments` below are pure functions the SOLE   #
# caller (`_predicate_writes._materialize_predicate_write`) drives against    #
# its OWN resolved rows — never an implicit read of their own.                #
# --------------------------------------------------------------------------- #
# The private slot `parallax.snapshot.handle._wrap` attaches a materialized
# temporal node's whole-graph Pin under — the same spelling
# `parallax.core.temporal_read.pin_of` reads.
_PIN_ATTR: Final[str] = "__parallax_pin__"


def source_pin(instance: object) -> Pin | None:
    """The whole-graph as-of :class:`Pin` a materialized snapshot node carries,
    or ``None`` for anything else — a fresh instance, or an edited copy
    (``model_copy(update=...)`` builds a new validated instance, so the pin
    stays with the materialized view it describes; that is what keeps the
    spec §3 stale-web-edit recipe's edge-pinned re-fetch -> edited-copy ->
    optimistic ``tx.update`` writable while the view itself stays
    read-only)."""
    pin = getattr(instance, _PIN_ATTR, None)
    return pin if isinstance(pin, Pin) else None


def validate_source_pin(entity_name: str, pin: Pin | None) -> None:
    """Reject a mutation sourced from a view pinned at a FINITE Transaction-Time
    instant (`m-temporal-read`'s finite-pin mutation row): raise
    :class:`TransactionTimePinReadOnlyError` at the verb call, before any
    buffering, so no DML is ever emitted. An absent pin, a ``LATEST``
    Transaction-Time pin, and a finite Valid-Time pin all pass — the finite
    Valid-Time pin is the writable retroactive correction (`m-bitemp-write`).
    Shared by every keyed developer verb (`_prepare_keyed_write` / ``delete``)
    and the conformance engine's scenario ``mutate`` grading, so the two
    callers can never drift. The predicate-selected ``_where`` family needs no
    counterpart: a set-based write target must be a bare statement, so it can
    never carry an as-of pin at all."""
    if pin is None:
        return
    tx_time = pin.tx_time
    if tx_time is None or isinstance(tx_time, Latest):
        return
    raise TransactionTimePinReadOnlyError(
        f"{entity_name}: the write's source view is pinned at the finite Transaction-Time "
        f"instant {tx_time.isoformat()} and is read-only — the Transaction-Time past "
        "records what the system knew and is never rewritten "
        "(transaction-time-pin-read-only); read the current milestone "
        "(Transaction Time Latest) to mutate it"
    )


def validate_valid_from(
    declaring: Entity, mutation: KeyedMutation, valid_from: dt.datetime | None
) -> str | None:
    """Validate and render a write verb's ``valid_from`` (`python.md` §5):
    a Bitemporal target requires it (the mutation's own Valid-Time instant
    ``B``, `m-bitemp-write` "Plain (unbounded) bitemporal writes"); a
    non-temporal or Transaction-Time-Only target takes none."""
    if declaring.temporal == "bitemporal":
        if valid_from is None:
            raise ValueError(
                f"{declaring.name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)"
            )
        return instant_literal(valid_from)
    if valid_from is not None:
        shape = "a Transaction-Time-Only" if declaring.is_temporal else "a non-temporal"
        raise ValueError(
            f"{declaring.name}: {shape} {mutation!r} takes no valid_from "
            f"({declaring.name!r} declares no Valid-Time dimension to bound)"
        )
    return None


def prepare_sparse_row(copy: EntityBase) -> dict[str, object] | None:
    """The sparse keyed ``update``/``updateUntil`` row (N2, COR-3 Phase 8
    increment 7 remediation): primary key + the edited copy's own effective
    change set (:func:`effective_change_set`) — ``None`` for an EMPTY
    effective set (the no-op-first rule, spec §3/§5): ``update`` returns
    immediately on ``None`` (no window to validate); ``updateUntil`` calls
    this AFTER its own window-order validation already ran (R2, COR-3 Phase 7
    increment 7 round-2 — :func:`validate_until` runs BEFORE this no-op
    check, never after, so an equal or reversed window still rejects even
    when the effective change set would otherwise have been empty)."""
    effective = effective_change_set(copy)
    if not effective:
        return None
    row: dict[str, object] = primary_key_row(copy)
    row.update(canonical_row(copy, effective))
    return row


def validate_until(
    declaring: Entity, mutation: KeyedMutation, valid_from: dt.datetime, until: dt.datetime
) -> str:
    """Validate + render a ``*Until`` verb's window bound (`python.md` §5:
    "both aware-UTC-microsecond datetimes, all validated at build" ... "the
    `*_until` trio additionally requires `until`, with `valid_from <
    until` ... all validated at build"): reject an equal or reversed window
    — ``until`` must be strictly later than ``valid_from`` — at the verb
    call, before any buffering (never at flush time). Shared by every keyed
    AND ``_where`` ``*Until`` verb (``update_until`` / ``terminate_until`` /
    ``update_until_where`` / ``terminate_until_where``, S4 COR-3 Phase 8
    increment 7 remediation) — one validator, so none of the four can drift
    from the others.

    NORMALIZES both bounds BEFORE comparing them (R2, COR-3 Phase 7 increment
    7 round-2): comparing raw, un-normalized datetimes let a naive ``until``
    (compared against an already-aware ``valid_from``, since
    ``validate_valid_from`` — this verb's own sibling, called first —
    already normalizes/rejects a naive ``valid_from``) leak a bare
    ``TypeError`` from the ``<=`` comparison itself, rather than the proper
    ``ValueError`` :func:`~parallax.core.base.normalize_instant` raises for
    any naive datetime (mirroring ``validate_valid_from``'s own
    ``instant_literal``-based handling exactly)."""
    valid_from_normalized = normalize_instant(valid_from)
    until_normalized = normalize_instant(until)
    if until_normalized <= valid_from_normalized:
        raise ValueError(
            f"{declaring.name}: {mutation!r} requires valid_from < until "
            f"(python.md §5) — got valid_from={valid_from!r}, until={until!r}"
        )
    return until_normalized.isoformat()


def materialize_row(
    meta: Metamodel,
    entity: Entity,
    declaring: Entity,
    version_attr: Attribute | None,
    mutation: KeyedMutation,
    assignments: Mapping[str, object],
    row: Row,
) -> tuple[ObjectKey, Observation | None, dict[str, object] | None]:
    """One resolved row's materialized keyed write: its
    :class:`~parallax.core.unit_work.ObjectKey`, its recorded
    :class:`Observation` (every branch records one — a versioned row's version,
    a temporal row's observed Transaction-Time start, `m-opt-lock` "observations are
    mode-independent; only the gate is mode-dependent"), and the new row a
    keyed write of ``mutation`` carries — ``None`` for the new row when every
    assignment already equals the row's own value (`m-opt-lock` "For
    assignment-bearing mutations, no-op elimination is per resolved row";
    `delete` / `terminate` / `terminateUntil` always write every resolved row,
    no assignments to compare). ``row`` is the resolve's OWN row-form row
    (never an implicit second read).
    """
    pk_attrs = inheritance.family_primary_key(meta, entity)
    pk_row = {attr.name: row[attr.column] for attr in pk_attrs}
    key: ObjectKey = (entity.name, tuple(pk_row.items()))
    assignment_bearing = mutation in ("update", "updateUntil")

    if version_attr is not None:
        observation = Observation(version=cast("int", row[version_attr.column]))
        if not assignment_bearing:
            return key, observation, dict(pk_row)
        new_row, changed = _apply_assignments(meta, entity, pk_row, row, assignments)
        return key, observation, (new_row if changed else None)

    tx_axis = tx_time_axis(declaring)
    tx_start_column, tx_end_column = axis_columns(declaring, tx_axis)
    tx_start = cast("str", row[tx_start_column])
    if declaring.temporal == "bitemporal":
        # A SPARSE new row: `bitemp_write.plan` merges it onto the observed
        # payload itself (`_merged_payload`), the bitemporal analogue of an
        # edited copy's effective change set.
        observation = _temporal_observation(meta, declaring, row, tx_axis, latest_pinned=True)
        if not assignment_bearing:
            return key, observation, dict(pk_row)
        new_row, changed = _apply_assignments(meta, declaring, pk_row, row, assignments)
        return key, observation, (new_row if changed else None)

    # Audit-only: `txtime_write.plan` chains the instruction's OWN authored
    # FULL row verbatim (never a separate observed payload), so the full
    # merge happens HERE — the resolved row's own scalar payload (VO
    # documents omitted; row-form never projects one) with the assignments
    # overlaid.
    observation = Observation(tx_start=tx_start, latest_pinned=True)
    if not assignment_bearing:
        # A plain (chain-free) audit-only `terminate` records its resolved
        # row's observed `in_z` exactly like every other materializing verb
        # (`m-opt-lock` "Predicate-selected writes materialize when
        # observations are needed" — observations are MODE-INDEPENDENT; only
        # the GATE is mode-dependent, `m-txtime-write.md:65`). The observed
        # `in_z` is the temporal analogue of a versioned optimistic gate
        # (`m-txtime-write` "Affected-row conflict contract for closes"), so
        # an OPTIMISTIC-mode close binds it (`and in_z = ?`, `m-opt-lock.md`
        # "Temporal entities derive the version from the Transaction-Time dimension"),
        # gate-last, exactly as a keyed temporal terminate already does
        # (`m-txtime-write-006`) — `txtime_write.plan` composes the gate
        # candidate straight from this SAME observation, no separate branch.
        # A LOCKING-mode close still renders ungated (the render seam only
        # ever BINDS the candidate under optimistic concurrency,
        # `~parallax.core.opt_lock.gates`), so recording the observation here
        # never changes locking mode's own ungated shape.
        return key, observation, dict(pk_row)
    # Reached only for an assignment-bearing (`update`) audit-only mutation —
    # exactly when `_materialize_predicate_write`'s own resolving read
    # requested the value-object document column(s) too
    # (`include_value_objects`, `m-case-format.md:727`), so the merge below
    # carries forward whichever documents `assignments` does NOT itself
    # reassign, never dropping them from the chained row.
    full_row: dict[str, object] = {
        **pk_row,
        **_row_payload(
            meta,
            declaring,
            row,
            {tx_start_column, tx_end_column},
            include_value_objects=True,
        ),
    }
    new_row, changed = _apply_assignments(meta, declaring, full_row, row, assignments)
    return key, observation, (new_row if changed else None)


def _apply_assignments(
    meta: Metamodel,
    entity: Entity,
    base_row: Mapping[str, object],
    row: Row,
    assignments: Mapping[str, object],
) -> tuple[dict[str, object], bool]:
    """Overlay ``assignments`` (declared member name -> new value) onto
    ``base_row``, reporting whether at least one assigned member's value
    genuinely DIFFERS from ``row``'s own resolved value (`m-opt-lock` per-row
    no-op elimination — structural equality, the SAME comparison a keyed
    no-op's effective-change-set test uses). ``row`` is the row-form RESOLVED
    row the comparison reads from; ``base_row`` is what the eventual keyed
    write carries."""
    member_columns = members(meta, entity)
    new_row = dict(base_row)
    changed = False
    for member, value in assignments.items():
        column = member_columns[member][0]
        if value != row.get(column):
            changed = True
        new_row[member] = value
    return new_row, changed


def entity_record_of_instance(instance: EntityBase) -> Entity:
    record = entity_record_of(type(instance))
    if record is None:
        raise TypeError(f"{type(instance).__name__} is not a registered Parallax entity class")
    return record
