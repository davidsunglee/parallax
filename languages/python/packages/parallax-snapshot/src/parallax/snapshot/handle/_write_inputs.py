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
* the observation record a read leaves behind (:class:`ReadObservations`) and its
  recording into the unit of work (:func:`record_observations`), plus the per-row
  column contributions a materializing predicate-write resolve streams into its
  :class:`~parallax.core.unit_work.MaterializedWriteGroup`
  (:func:`is_no_op_assignment`, :func:`key_column_values`,
  :func:`predecessor_payload`), which share their payload extraction with
  :func:`record_observations` through the module-local ``_row_payload``.

Semantic family facts come from the accepted Metamodel and its facets, resolved
through :mod:`parallax.snapshot.handle._family` (the declaring root,
family-effective axes and primary key, version attribute). Every PHYSICAL column
instead comes from the row-owning Entity's Storage Layout view, which each entry
point resolves once and carries into the helpers that read or write a row's
columns. :class:`ReadObservations` satisfies the read executor's own
``ObservationCollector`` structurally rather than by import, so this module and
:mod:`parallax.snapshot.handle._read` name each other in neither direction.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from parallax.core.base import normalize_instant
from parallax.core.db_port import Row
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import canonical_row, effective_change_set, primary_key_row
from parallax.core.entity._declaration import declaration_of
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    TemporalDimension,
    ValueObjectMetadata,
)
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.temporal_read import LATEST, Latest, Pin
from parallax.core.unit_work import (
    HISTORICAL_PINNED,
    LATEST_PINNED,
    KeyedMutation,
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    TransactionTimeBasis,
    UnitOfWork,
    VersionObservation,
    instant_literal,
)
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle._family import (
    axis_columns,
    declaring,
    entity_layout,
    members,
    placed_members,
    slot_column,
    tx_time_axis,
    version_attribute,
)

__all__ = [
    "ReadObservations",
    "TransactionTimePinReadOnlyError",
    "is_no_op_assignment",
    "key_column_values",
    "metadata_of_instance",
    "observation_key",
    "predecessor_payload",
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
    """The observation key for a WRITTEN instance — the same key
    :func:`record_observations` records under (the instance's OWN Entity
    Identity, never family-normalized; pk pairs by canonical attribute name, in
    the declaring entity's primary-key order) and `unit_work.object_key`
    computes at flush, so a verb-time license lookup and the flush-time attach
    can never diverge."""
    row = primary_key_row(instance)
    return ObjectKey(
        record.identity,
        tuple(
            (attr.identity.name, row[attr.identity.name])
            for attr in _declared_primary_key(declaring_entity)
        ),
    )


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state, keyed by PHYSICAL column.

    ``entity`` is the row's own resolved concrete Entity. ``columns`` is every
    value the row materialized — the primary key, the version column, the axis
    bounds, and every other applicable member — which is what makes a
    Predecessor Row complete. ``document`` is the raw Structured Column under
    Relational Document Layout.

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    entity: EntityIdentity
    columns: Mapping[str, object]
    document: object | None


class ReadObservations:
    """What one :func:`~parallax.snapshot.handle.find` leaves behind for the
    write side — the read executor's ``ObservationCollector``, satisfied
    structurally.

    A caller with a unit of work behind it constructs one and hands it to the
    executor; a caller without one hands nothing, which is how a
    non-transactional read allocates no observation state. Rows accumulate in the
    order the executor materializes them (root first, then each level in plan
    order), and :func:`record_observations` is the only consumer.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        self._rows: list[_ObservedRow] = []

    def observe_row(
        self, entity: EntityIdentity, columns: Mapping[str, object], document: object | None
    ) -> None:
        """Snapshot one materialized row's observable state. ``columns`` stays the
        caller's, so a later edit to it cannot reach the recorded observation."""
        self._rows.append(_ObservedRow(entity, dict(columns), document))

    @property
    def rows(self) -> Sequence[_ObservedRow]:
        """Every row observed so far, in materialization order."""
        return self._rows


def record_observations(
    uow: UnitOfWork, meta: Metamodel, observations: ReadObservations, pin: Pin
) -> None:
    """Record this unit of work's observed version/temporal-milestone for
    every VERSIONED or TEMPORAL row :func:`find` materialized (`m-opt-lock`;
    ADR 0013).

    Keyed by the SAME :class:`~parallax.core.unit_work.ObjectKey` a subsequent
    keyed write's own :func:`~parallax.core.unit_work.object_key` computes —
    the Entity here is the row's OWN resolved concrete Entity (never
    family-normalized to the root), which is what a developer's later
    ``tx.update(copy)`` resolves its instance's own class to. A row whose
    (family-effective) primary key, version column, or Transaction-Time
    interval is absent from its own observed columns is defensively skipped —
    never reachable for a well-formed corpus model, but this seam takes no data
    on faith. A versioned entity is never also
    temporal (`m-opt-lock`/`m-descriptor`: the two are mutually exclusive), so
    each row takes exactly one branch.

    ``pin`` is the STATEMENT's OWN lowered as-of coordinates
    (``Transaction.find``'s own ``deep_fetch_statement_pin`` call): the whole-graph pin
    propagates per hop, matched by axis, to every temporal entity in the
    include tree (spec §3), so this SAME root-level Transaction-Time pin
    licenses every attached temporal node's own recorded observation — an
    omitted axis or an explicit `LATEST` pin is latest-pinned; an explicit
    as-of instant is not (`~parallax.core.opt_lock.check_locking_license`'s
    own historical-observation rule).

    ``find`` is always INSTANCE-form, which projects every applicable Column, so
    an observed row's columns are the COMPLETE persisted row a Predecessor Row
    requires. Under Relational Document Layout the read ALSO carried the row's raw
    Structured Column past the fan-out that decoded those members, and a temporal
    observation retains it (`m-unit-work`) so a successor is patched from what the
    row held rather than rebuilt from the members this model declares — at no
    extra query, because the predecessor read already materialized it.
    """
    basis = LATEST_PINNED if pin.tx_time is None or pin.tx_time is LATEST else HISTORICAL_PINNED
    for observed in observations.rows:
        observed_fields = observed.columns
        entity = meta.entity(observed.entity)
        if entity is None:  # pragma: no cover - a materialized row resolved within this model
            continue
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
        key = ObjectKey(
            observed.entity,
            tuple(
                (attr.identity.name, observed_fields[column])
                for attr, column in zip(pk_attrs, pk_columns, strict=True)
            ),
        )
        version_attr = version_attribute(meta, declaring_entity)
        if version_attr is not None:
            version_column = slot_column(layout, version_attr.identity)
            if version_column in observed_fields:
                uow.observe(
                    key,
                    VersionObservation(
                        observed_version=cast("int", observed_fields[version_column])
                    ),
                )
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
                members(placed_members(meta, entity, layout)),
                observed_fields,
                basis,
                observed.document,
            ),
        )


def _temporal_observation(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
    basis: TransactionTimeBasis,
    document: object | None = None,
) -> TemporalObservation:
    """The :class:`TemporalObservation` a materialized TEMPORAL row licenses: its
    complete Predecessor Row plus the observing read's Transaction-Time Basis.

    The Predecessor Row retains EVERY applicable member ``fields`` carries —
    scalars, value-object documents, the primary key, and both axis intervals —
    because temporal expansion carries members the authored mutation never
    mentioned, and because the close's own address and gate are read off the same
    observed row rather than from separate per-axis fields. The bounds are the
    only members every consumer names; the rest ride through as the payload a
    chained or split successor carries forward (`m-bitemp-write` "head/tail old
    values"; `m-value-object` "the document rides every chained/split row
    whole").

    ``fields`` is a plain column-keyed mapping — one materialized row's own
    observable columns, documents decoded
    (:func:`~parallax.snapshot.materialize.observable_columns`, a real
    ``Transaction.find``), or one resolved row of a materializing predicate-write
    resolve (:func:`predecessor_payload`) — so both callers share the SAME
    extraction rather than duplicating it. Extraction renders nothing of its own:
    every value passes through EXACTLY as ``fields`` carries it, which for a
    scalar or interval column is exactly what the port returned (a real
    ``timestamptz`` column may be a driver-native ``datetime.datetime`` or the
    native-infinity sentinel, never pre-rendered to a wire string here) — the
    SAME driver-native-passthrough contract every other temporal bind in this
    seam already carries; wire-rendering for REPORTING is the conformance ADAPTER's
    own boundary concern (`parallax.conformance.engine._json_bind`), never this
    seam's.

    ``document`` is the row's raw Structured Column under Relational Document
    Layout, which the Predecessor Row retains beside — never among — those
    members, so a successor built from it keeps keys no member declares. It is
    absent under `Columns` layout, where the row has no such column.
    """
    return TemporalObservation(
        predecessor=PredecessorRow(
            _row_payload(member_columns, fields, include_value_objects=True), document=document
        ),
        transaction_time_basis=basis,
    )


def _row_payload(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
    excluded: frozenset[str] = frozenset(),
    *,
    include_value_objects: bool = False,
) -> dict[str, object]:
    """``fields``'s own payload (every applicable member besides ``excluded``
    columns) — the extraction a real TEMPORAL find's Predecessor Row
    (`_temporal_observation`, above) and a materializing resolve's own
    Predecessor Row (:func:`predecessor_payload`) share. A Predecessor Row
    excludes nothing; a caller excluding the axis bounds its own milestone plan
    stamps afresh names them.

    Value-object members are OMITTED by default (a plain row-form read projects
    no `Document` slot, `m-sql` *Read projection*). ``include_value_objects``
    opts in, and both callers are observation-side: `_temporal_observation`
    (every real ``Transaction.find``, always INSTANCE-form, and every
    materializing resolve on a temporal target, whose own projection carries
    every declared document so the Predecessor Row is complete) and
    `predecessor_payload` (that same resolve). ``column in fields`` still gates
    every member exactly as it does for scalars; a VO-free entity's empty
    value-object half makes this flag a no-op either way.
    """
    return {
        name: fields[column]
        for name, (column, is_value_object) in member_columns.items()
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
# `is_no_op_assignment` / `key_column_values` / `predecessor_payload` below   #
# are pure per-row functions the SOLE caller                                  #
# (`_predicate_writes._materialize_predicate_write`) drives against its OWN   #
# resolved rows while streaming them into column builders — never an         #
# implicit read of their own, and never a merged per-row dict of their own.   #
# --------------------------------------------------------------------------- #
def source_pin(instance: object) -> Pin | None:
    """The whole-graph as-of :class:`Pin` a materialized snapshot node carries,
    or ``None`` for anything else — a fresh instance, or an edited copy
    (``edit(**changes)`` builds a new validated instance, so the pin
    stays with the materialized view it describes; that is what keeps the
    spec §3 stale-web-edit recipe's edge-pinned re-fetch -> edited-copy ->
    optimistic ``tx.update`` writable while the view itself stays
    read-only)."""
    state = snapshot_state_of(instance)
    return None if state is None else state.pin


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


def is_no_op_assignment(
    member_columns: Mapping[str, tuple[str, bool]],
    assignments: Mapping[str, object],
    row: Row,
    occurrences: Mapping[str, ValueObjectMetadata] | None = None,
) -> bool:
    """Whether EVERY assigned member's new value already equals ``row``'s own
    (`m-opt-lock` per-row no-op elimination — structural equality, the SAME
    comparison a keyed no-op's effective-change-set test uses).

    ``row`` is one resolved row of the write's own resolving read, after that
    read's row transform: a document-mapped member is compared against the value
    the fan-out decoded, in its declared Neutral Type, rather than against a
    fragment of the raw Structured Column. An absent Document Path and an
    explicit JSON null both decode to ``None``, which is the one logical
    not-present state a NULL Column also carries, so a member assigned ``None``
    is a no-op in either spelling.

    This is the ONE narrow result-dependent normalization a materializing
    resolve performs while streaming: a resolved row an assignment-bearing
    verb would leave unchanged never joins its Materialized Write Group.
    ``delete`` / ``terminate`` / ``terminateUntil`` have no assignments to
    compare and therefore never call this — every resolved row is retained.
    """
    from parallax.core.document_codec import (
        LeafEncodingError,
        occurrence_shape,
        reduce_declared_members,
    )

    occurrence_index: Mapping[str, ValueObjectMetadata] = (
        cast("Mapping[str, ValueObjectMetadata]", {}) if occurrences is None else occurrences
    )
    for member, value in assignments.items():
        stored = row.get(member_columns[member][0])
        occurrence = occurrence_index.get(member)
        if occurrence is None:
            if value != stored:
                return False
            continue
        shape = occurrence_shape(occurrence)
        if occurrence.multiplicity is Multiplicity.MANY:
            if not isinstance(stored, list):
                raise LeafEncodingError(f"{member}: expected array, got {type(stored).__name__}")
            stored_items = cast("Sequence[object]", stored)
            assigned_items: Sequence[object] = (
                cast("Sequence[object]", value) if isinstance(value, (list, tuple)) else ()
            )
            if [reduce_declared_members(shape, item) for item in stored_items] != [
                reduce_declared_members(shape, item) for item in assigned_items
            ]:
                return False
        elif reduce_declared_members(shape, stored, named_by=value) != reduce_declared_members(
            shape, value, named_by=value
        ):
            return False
    return True


def key_column_values(
    pk_attrs: Sequence[AttributeMetadata], layout: EntityLayoutView, row: Row
) -> tuple[object, ...]:
    """One resolved row's aligned primary-key value tuple, in ``pk_attrs``
    order — a Materialized Write Group's own per-row key-column contribution.
    """
    return tuple(row[slot_column(layout, attr.identity)] for attr in pk_attrs)


def predecessor_payload(
    member_columns: Mapping[str, tuple[str, bool]], row: Row
) -> dict[str, object]:
    """One resolved row's COMPLETE Predecessor Row payload — every applicable
    member, value-object documents included — the SAME complete extraction
    :func:`record_observations` retains for a real find (`m-unit-work` "A
    Predecessor Row is the complete, immutable persisted state"), applied to a
    materializing resolve's own row-form row. A materializing resolve reads
    the CURRENT milestone by construction, so every predecessor it retains is
    latest-pinned.
    """
    return _row_payload(member_columns, row, include_value_objects=True)


def metadata_of_instance(meta: Metamodel, instance: EntityBase) -> EntityMetadata:
    """``instance``'s accepted Entity Metadata within ``meta``, or a loud
    ``TypeError`` when the connected model declares no such Entity.

    Membership is decided by the Entity Identity the instance's class declares:
    one class participates in any number of models, so belonging is a question
    about this model rather than about the class. What a shared identity cannot
    settle — whether a foreign class's MEMBERS are this model's — is settled one
    layer down and unchanged: every keyed write still routes ``deserialize`` ->
    ``validate_write`` -> ``validate_instruction`` against the connected model,
    where member-name honesty and the declared-type walk reject a foreign
    instance's row.
    """
    cls = type(instance)
    metadata = meta.entity(declaration_of(cls).identity)
    if metadata is None:
        raise TypeError(f"{cls.__name__} is not an Entity Class of this model")
    return metadata
