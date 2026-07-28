"""``parallax.snapshot.handle._write_inputs`` — verb-input preparation and observations.

Everything a write verb needs BEFORE an instruction reaches the unit of work,
plus the observation machinery a read leaves behind for it:

* build-time window validation every keyed AND ``_where`` temporal verb shares
  (:func:`validate_valid_from`, :func:`validate_until`), the finite-Transaction-
  Time-pin refusal every keyed verb runs on its source instance
  (:class:`TransactionTimePinReadOnlyError`, :func:`validate_source_pin`,
  :func:`source_pin`), and the sparse keyed ``update`` row
  (:func:`prepare_sparse_row`);
* instance -> accepted-Metadata resolution (:func:`metadata_of_instance`) and the
  verb-time license key (:func:`observation_key`);
* observation recording after a real :func:`~parallax.snapshot.handle.find`
  (:func:`record_observations`) and its row-form twin for a materializing
  predicate-write resolve (:func:`materialize_row`), which share their payload
  extraction through the module-local ``_temporal_observation`` / ``_row_payload``.

Semantic family facts come from the accepted Metamodel and its facets, resolved
through :mod:`parallax.snapshot.handle._family` (the declaring root,
family-effective axes and primary key, version attribute). Every PHYSICAL column
instead comes from the row-owning Entity's Storage Layout view, which each entry
point resolves once and carries into the helpers that read or write a row's
columns. For the
:class:`~parallax.snapshot.handle.FindResult` :func:`record_observations`
consumes it also imports :mod:`parallax.snapshot.handle._read`. That edge is
deliberately one-way: the pin helpers ``Transaction.find`` shares with the read
executor stay in ``_read``, so ``_read`` never imports this module.

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

from parallax.core.base import normalize_instant
from parallax.core.db_port import Row
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import (
    binding_of,
    canonical_row,
    effective_change_set,
    primary_key_row,
)
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    TemporalDimension,
)
from parallax.core.storage_layout import EntityLayoutView
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
    declaring,
    entity_layout,
    entity_of,
    family_primary_key,
    members,
    slot_column,
    tx_time_axis,
    valid_time_axis,
    version_attribute,
)
from parallax.snapshot.handle._read import FindResult

__all__ = [
    "TransactionTimePinReadOnlyError",
    "materialize_row",
    "metadata_of_instance",
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


def _declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """``entity``'s OWN declared primary key — used where ``entity`` is already
    the declaring root, so its local declaration IS the family key."""
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _is_temporal(declaring_entity: EntityMetadata) -> bool:
    return bool(declaring_entity.declared_as_of_axes)


def _is_bitemporal(declaring_entity: EntityMetadata) -> bool:
    return declaring_entity.as_of_axis(TemporalDimension.VALID_TIME) is not None


def observation_key(
    record: EntityMetadata, declaring_entity: EntityMetadata, instance: object
) -> ObjectKey:
    """The ``(entity name, ordered pk pairs)`` observation key for a WRITTEN
    instance — the same shape :func:`record_observations` records under (the
    instance's OWN entity name, never family-normalized; pk pairs by canonical
    attribute name, in the declaring entity's primary-key order) and
    `unit_work.object_key` computes at flush, so a verb-time license lookup
    and the flush-time attach can never diverge."""
    row = primary_key_row(instance)
    return (
        record.identity.name,
        tuple(
            (attr.identity.name, row[attr.identity.name])
            for attr in _declared_primary_key(declaring_entity)
        ),
    )


def record_observations(uow: UnitOfWork, meta: Metamodel, result: FindResult, pin: Pin) -> None:
    """Record this unit of work's observed version/temporal-milestone for
    every VERSIONED or TEMPORAL node :func:`find` materialized (`m-opt-lock`;
    ADR 0013).

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
        observed_fields = {**node.fields, **node.value_objects}
        entity = entity_of(meta, entity_name)
        declaring_entity = declaring(meta, entity)
        layout = entity_layout(meta, entity)
        if layout is None:  # pragma: no cover - a materialized node always owns rows
            continue
        pk_attrs = _declared_primary_key(declaring_entity)
        pk_columns = [slot_column(layout, attr.identity) for attr in pk_attrs]
        if not pk_attrs or any(  # pragma: no cover - defends a malformed model/projection
            column not in observed_fields for column in pk_columns
        ):
            continue
        key: ObjectKey = (
            entity_name,
            tuple(
                (attr.identity.name, observed_fields[column])
                for attr, column in zip(pk_attrs, pk_columns, strict=True)
            ),
        )
        version_attr = version_attribute(meta, declaring_entity)
        if version_attr is not None:
            version_column = slot_column(layout, version_attr.identity)
            if version_column in observed_fields:
                uow.observe(key, Observation(version=cast("int", observed_fields[version_column])))
            continue
        if not _is_temporal(declaring_entity):
            continue
        tx_axis = tx_time_axis(declaring_entity)
        tx_start_column, _tx_end_column = axis_columns(layout, tx_axis)
        if tx_start_column not in observed_fields:  # pragma: no cover - malformed model/projection
            continue
        uow.observe(
            key,
            _temporal_observation(
                layout, declaring_entity, observed_fields, tx_axis, latest_pinned
            ),
        )


def _temporal_observation(
    layout: EntityLayoutView,
    declaring_entity: EntityMetadata,
    fields: Mapping[str, object],
    tx_axis: AsOfAxisMetadata,
    latest_pinned: bool,
) -> Observation:
    """The :class:`Observation` a materialized TEMPORAL row licenses: the
    observed Transaction-Time start (``in_z``) plus pin provenance always, PLUS the
    observed payload (every
    real ``Transaction.find`` of a temporal row carries one, audit-only
    included) — the same fields temporal lowering (`~parallax.core.
    txtime_write.plan` / `~parallax.core.bitemp_write.plan`) already consumes,
    so a transaction-scoped find -> temporal write sequence works end-to-end,
    not just the licensing check. The observed Valid-Time bounds are Bitemporal-only.

    ``fields`` is a plain column-keyed mapping — a materialized
    :class:`~parallax.snapshot.materialize.Node`'s own ``.fields`` (a real
    ``Transaction.find``), or a raw driver row (the
    materializing predicate-write resolve, :func:`materialize_row`) — so both
    callers share the SAME payload-extraction logic rather than duplicating it.
    Every extracted value passes through EXACTLY as the port returned it (a
    real ``timestamptz`` column may be a driver-native ``datetime.datetime``
    or the native-infinity sentinel, never pre-rendered to a wire string here)
    — the SAME driver-native-passthrough contract every other temporal bind in
    this seam already carries; wire-rendering for REPORTING is the conformance
    ADAPTER's own boundary concern (`parallax.conformance.engine._json_bind`),
    never this seam's.

    The bitemporal payload KEEPS a value-object document whenever ``fields``
    carries one (`include_value_objects=True` below): a real
    ``Transaction.find`` is always INSTANCE-form, which
    projects every document unconditionally (`m-sql`), so ``fields`` already
    carries it there; a materializing predicate-write resolve's ROW-form
    ``fields`` carries one whenever its own need-sensitive projection
    requested it (`_predicate_writes._materialize_predicate_write`'s
    ``needs_documents``) — ``column in fields`` still gates every member exactly
    as it does for scalars, so this is a no-op only for a VO-free entity, and
    never drops one `bitemp_write.plan`'s head/middle/tail split needs to carry
    forward whole (`m-bitemp-write` "head/tail old values"; `m-value-object`
    "the document rides every chained/split row whole").
    """
    tx_start_column, tx_end_column = axis_columns(layout, tx_axis)
    tx_start = cast("str", fields[tx_start_column])
    if not _is_bitemporal(declaring_entity):
        # Audit-only: the observed payload every other member besides
        # the sole Transaction-Time axis — `txtime_write.plan`'s own update-branch
        # merge (`_merged_row`) overlays a public `tx.update(copy)`'s SPARSE
        # row onto it, so an unauthored field carries forward from THIS
        # observation rather than being silently dropped.
        payload = _row_payload(
            layout,
            fields,
            {tx_start_column, tx_end_column},
            include_value_objects=True,
        )
        return Observation(tx_start=tx_start, payload=payload, latest_pinned=latest_pinned)
    valid_axis = valid_time_axis(declaring_entity)
    valid_start_column, valid_end_column = axis_columns(layout, valid_axis)
    if valid_start_column not in fields or valid_end_column not in fields:  # pragma: no cover
        return Observation(
            tx_start=tx_start, latest_pinned=latest_pinned
        )  # malformed model/projection
    excluded = {tx_start_column, tx_end_column, valid_start_column, valid_end_column}
    payload = _row_payload(layout, fields, excluded, include_value_objects=True)
    return Observation(
        tx_start=tx_start,
        valid_start=cast("str", fields[valid_start_column]),
        valid_end=cast("str", fields[valid_end_column]),
        payload=payload,
        latest_pinned=latest_pinned,
    )


def _row_payload(
    layout: EntityLayoutView,
    fields: Mapping[str, object],
    excluded: set[str],
    *,
    include_value_objects: bool = False,
) -> dict[str, object]:
    """``fields``'s own payload (every applicable member besides ``excluded``
    axis-bound columns) — the observed-payload source a real TEMPORAL find's
    :class:`Observation` (`_temporal_observation`, above — audit-only and
    bitemporal alike) and an audit-only materializing resolve's CHAINED
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
        for name, (column, is_value_object) in members(layout).items()
        if (include_value_objects or not is_value_object)
        and column in fields
        and column not in excluded
    }


# --------------------------------------------------------------------------- #
# Predicate-write materialization (m-opt-lock                                 #
# "Predicate-selected writes materialize when observations are needed";       #
# ADR 0014) — plus the build-time window/no-op validators every keyed AND     #
# `_where` temporal verb shares (`validate_valid_from` / `validate_until`#
# / `prepare_sparse_row`).                                                    #
# `materialize_row`/`_apply_assignments` below are pure functions the SOLE   #
# caller (`_predicate_writes._materialize_predicate_write`) drives against    #
# its OWN resolved rows — never an implicit read of their own.               #
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
    declaring_entity: EntityMetadata, mutation: KeyedMutation, valid_from: dt.datetime | None
) -> str | None:
    """Validate and render a write verb's ``valid_from`` (`python.md` §5):
    a Bitemporal target requires it (the mutation's own Valid-Time instant
    ``B``, `m-bitemp-write` "Plain (unbounded) bitemporal writes"); a
    non-temporal or Transaction-Time-Only target takes none."""
    name = declaring_entity.identity.name
    if _is_bitemporal(declaring_entity):
        if valid_from is None:
            raise ValueError(
                f"{name}: a bitemporal {mutation!r} requires valid_from "
                "(the mutation's own Valid-Time instant)"
            )
        return instant_literal(valid_from)
    if valid_from is not None:
        shape = "a Transaction-Time-Only" if _is_temporal(declaring_entity) else "a non-temporal"
        raise ValueError(
            f"{name}: {shape} {mutation!r} takes no valid_from "
            f"({name!r} declares no Valid-Time dimension to bound)"
        )
    return None


def prepare_sparse_row(copy: EntityBase) -> dict[str, object] | None:
    """The sparse keyed ``update``/``updateUntil`` row: primary key + the
    edited copy's own effective
    change set (:func:`effective_change_set`) — ``None`` for an EMPTY
    effective set (the no-op-first rule, spec §3/§5): ``update`` returns
    immediately on ``None`` (no window to validate); ``updateUntil`` calls
    this AFTER its own window-order validation already ran
    (:func:`validate_until` runs BEFORE this no-op
    check, never after, so an equal or reversed window still rejects even
    when the effective change set would otherwise have been empty)."""
    effective = effective_change_set(copy)
    if not effective:
        return None
    row: dict[str, object] = primary_key_row(copy)
    row.update(canonical_row(copy, effective))
    return row


def validate_until(
    declaring_entity: EntityMetadata,
    mutation: KeyedMutation,
    valid_from: dt.datetime,
    until: dt.datetime,
) -> str:
    """Validate + render a ``*Until`` verb's window bound (`python.md` §5:
    "both aware-UTC-microsecond datetimes, all validated at build" ... "the
    `*_until` trio additionally requires `until`, with `valid_from <
    until` ... all validated at build"): reject an equal or reversed window
    — ``until`` must be strictly later than ``valid_from`` — at the verb
    call, before any buffering (never at flush time). Shared by every keyed
    AND ``_where`` ``*Until`` verb (``update_until`` / ``terminate_until`` /
    ``update_until_where`` / ``terminate_until_where``) — one validator,
    so none of the four can drift
    from the others.

    NORMALIZES both bounds BEFORE comparing them: comparing raw,
    un-normalized datetimes let a naive ``until``
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
            f"{declaring_entity.identity.name}: {mutation!r} requires valid_from < until "
            f"(python.md §5) — got valid_from={valid_from!r}, until={until!r}"
        )
    return until_normalized.isoformat()


def materialize_row(
    meta: Metamodel,
    layout: EntityLayoutView,
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    version_attr: AttributeMetadata | None,
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
    (never an implicit second read), keyed by the physical Columns ``layout``
    names, which is also where the resulting keyed instruction's own cells land.
    """
    pk_attrs = family_primary_key(meta, entity)
    pk_row = {attr.identity.name: row[slot_column(layout, attr.identity)] for attr in pk_attrs}
    key: ObjectKey = (entity.identity.name, tuple(pk_row.items()))
    assignment_bearing = mutation in ("update", "updateUntil")

    if version_attr is not None:
        observation = Observation(
            version=cast("int", row[slot_column(layout, version_attr.identity)])
        )
        if not assignment_bearing:
            return key, observation, dict(pk_row)
        new_row, changed = _apply_assignments(layout, pk_row, row, assignments)
        return key, observation, (new_row if changed else None)

    tx_axis = tx_time_axis(declaring_entity)
    tx_start_column, tx_end_column = axis_columns(layout, tx_axis)
    tx_start = cast("str", row[tx_start_column])
    if _is_bitemporal(declaring_entity):
        # A SPARSE new row: `bitemp_write.plan` merges it onto the observed
        # payload itself (`_merged_payload`), the bitemporal analogue of an
        # edited copy's effective change set.
        observation = _temporal_observation(
            layout, declaring_entity, row, tx_axis, latest_pinned=True
        )
        if not assignment_bearing:
            return key, observation, dict(pk_row)
        new_row, changed = _apply_assignments(layout, pk_row, row, assignments)
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
        # `in_z` is the temporal analogue of a versioned optimistic gate, so
        # an OPTIMISTIC-mode close binds it (`and in_z = ?`), gate-last,
        # exactly as a keyed temporal terminate already does — `txtime_write.
        # plan` composes the gate candidate straight from this SAME
        # observation, no separate branch. A LOCKING-mode close still renders
        # ungated (the render seam only ever BINDS the candidate under
        # optimistic concurrency, `~parallax.core.opt_lock.gates`), so
        # recording the observation here never changes locking mode's own
        # ungated shape.
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
            layout,
            row,
            {tx_start_column, tx_end_column},
            include_value_objects=True,
        ),
    }
    new_row, changed = _apply_assignments(layout, full_row, row, assignments)
    return key, observation, (new_row if changed else None)


def _apply_assignments(
    layout: EntityLayoutView,
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
    member_columns = members(layout)
    new_row = dict(base_row)
    changed = False
    for member, value in assignments.items():
        column = member_columns[member][0]
        if value != row.get(column):
            changed = True
        new_row[member] = value
    return new_row, changed


def metadata_of_instance(meta: Metamodel, instance: EntityBase) -> EntityMetadata:
    """``instance``'s accepted Entity Metadata within ``meta``, or a loud
    ``TypeError`` when its class belongs to no hub or to a different one.

    Membership is decided by the Metamodel Binding the class was claimed by, and
    that Binding must be the one that sealed ``meta`` itself — never by the
    Entity Identity it names. Identity is not unique across hubs: two distinct
    classes in two separate models may declare the same one, so resolving an
    identity out of one hub and looking it up in another would silently accept a
    foreign instance and key its write against the wrong model.
    """
    cls = type(instance)
    binding = binding_of(cls)
    identity = None if binding is None or binding.model is not meta else binding.identity_of(cls)
    metadata = None if identity is None else meta.entity(identity)
    if metadata is None:
        raise TypeError(f"{cls.__name__} is not an Entity Class of this model")
    return metadata
