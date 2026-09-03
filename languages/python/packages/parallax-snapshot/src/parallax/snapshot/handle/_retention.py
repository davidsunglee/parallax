"""``parallax.snapshot.handle._retention`` — write-observation retention.

The evidence a graph-form read leaves on the values it publishes: the Write
Observation each materialized row licensed, filed under the object it observed
plus that observation's own coordinate, and the Source Hint that selects it. A
read collects its rows into :class:`ObservedRows` while they are still live,
then hands the whole collection to :func:`retain_evidence`, which walks it once
and answers the :data:`ReadSources` a materializer attaches to the values it
builds.

Everything between those two steps is this module's own: the family-aware Object
Key a row denotes, the versioned / temporal / neither branch each row takes, the
complete Predecessor Row a temporal row licenses, the within-pass deduplication
that makes two projections of one state answer one claim, the interning across
passes an :class:`ObservationLedger` performs, and the participation and pin each
hint is stamped with. A caller learns one collector and one verb.

The read executor drives this module while its rows are live, and the dependency
goes that way and ONLY that way — nothing here names
:mod:`parallax.snapshot.handle._read`. No generated contract can say so: a child
scope's forbidden row can never name its own parent, and the read executor lives
in the parent scope. This scope is SEALED instead (`spec/python.md` §7), so the
rule is graded over this file — every import into the handle package that this
scope's grants do not cover is refused, the executor among them.

Semantic family facts come from the accepted Metamodel and its facets, resolved
through :mod:`parallax.snapshot.handle._family` (the declaring root, the
family-effective primary key, the version attribute, the as-of axes). Every
PHYSICAL column instead comes from the row-owning Entity's Storage Layout view,
resolved once per observed row and carried into the helpers that read it.

:func:`row_payload` is the one rule that crosses out of here. A materializing
predicate-write resolve streams the SAME complete payload into its
:class:`~parallax.core.unit_work.MaterializedWriteGroup` that a real find
retains, so the extraction lives once and both sides share it
(:mod:`parallax.snapshot.handle._predicate_writes`).

The participating unit of work is reached as :class:`ObservationLedger` — the two
answers retention needs from a transaction — rather than as the whole scope, so a
standalone read satisfies this module by passing none of it.

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    ObjectKey,
    ObservedStateKey,
    ParticipationToken,
    PredecessorRow,
    RetainedObservation,
    SourceHint,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    observed_state_key,
)
from parallax.snapshot.handle._family import (
    axis_columns,
    declaring,
    entity_layout,
    family_primary_key,
    is_temporal,
    members,
    placed_members,
    slot_column,
    tx_time_axis,
    version_attribute,
)

__all__ = [
    "ObservationLedger",
    "ObservedRows",
    "ReadSources",
    "retain_evidence",
    "row_payload",
]


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state, keyed by PHYSICAL column.

    ``node`` is the graph projection this row converted into, which is how
    the evidence built from it reaches the value that projection becomes.
    ``entity`` is the row's own resolved concrete Entity. ``columns`` is every
    value the row materialized — the primary key, the version column, the axis
    bounds, and every other applicable member — which is what makes a
    Predecessor Row complete. ``document`` is the raw Structured Column under
    Relational Document Layout.

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    node: int
    entity: EntityIdentity
    columns: Mapping[str, object]
    document: object | None


class ObservedRows:
    """What one :func:`~parallax.snapshot.handle.find` collects for the write
    side while its rows are still live.

    Physical, column-keyed snapshots of materialized rows: :meth:`observe_row` is
    the only way in and iteration the only way out, so what a row is recorded AS
    stays unnameable outside this module. :func:`retain_evidence` is the only
    consumer. Every graph-form read collects: a value's write evidence belongs to
    the value, so a standalone read produces sources exactly as a participating
    one does and differs only in the participation it can stamp.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        self._rows: list[_ObservedRow] = []

    def observe_row(
        self,
        node: int,
        entity: EntityIdentity,
        columns: Mapping[str, object],
        document: object | None,
    ) -> None:
        """Snapshot one materialized row's observable state. ``columns`` stays the
        caller's, so a later edit to it cannot reach the recorded observation."""
        self._rows.append(_ObservedRow(node, entity, dict(columns), document))

    def __iter__(self) -> Iterator[_ObservedRow]:
        """Every row observed so far, in the order the executor materialized them
        (root first, then each level in plan order). Nothing outside this module
        can name what is yielded, and nothing addresses a hint by that order:
        :func:`retain_evidence` keys its answer by each row's own projection."""
        return iter(self._rows)


type ReadSources = Mapping[int, SourceHint]
"""The Source Hint each observed projection's value carries, keyed by that
projection's own index in the read's sealed graph.

Only the executor can build this pairing: it alone holds the row and the
projection it converted into at the same time, and by the time a materializer
builds the value the row is gone."""


class ObservationLedger(Protocol):
    """The unit of work an observing read files into, satisfied structurally.

    ``find`` needs exactly two things from a transaction — the participation its
    reads stamp, and the chance to answer evidence it already holds for a state
    this read saw again — so it names those two rather than the whole scope. A
    standalone read passes none of it.
    """

    @property
    def participation(self) -> ParticipationToken: ...

    def retain(self, observation: RetainedObservation, /) -> RetainedObservation: ...


def retain_evidence(
    meta: Metamodel,
    observations: ObservedRows,
    *,
    ledger: ObservationLedger | None,
    pin: Pin | None = None,
) -> ReadSources:
    """Retain the observed version/temporal-milestone of every VERSIONED or
    TEMPORAL row :func:`find` materialized, onto the values that observed them
    (`m-opt-lock`; ADR 0013; `m-unit-work` "Observation lifetime").

    Evidence is addressed by the exact state it is about
    (:func:`~parallax.core.unit_work.observed_state_key`), so a second read of
    one primary key that resolves to a DIFFERENT version or milestone is
    evidence about the row it actually saw rather than an overwrite of the first
    read's, and a live value keeps the state IT observed however often the row
    is read again. The identity half is the SAME
    :class:`~parallax.core.unit_work.ObjectKey` a subsequent keyed write's own
    :func:`~parallax.core.unit_work.object_key` computes — the Entity here is the
    row's OWN resolved concrete Entity (never family-normalized to the root),
    which is what a developer's later ``tx.update(copy)`` resolves its instance's
    own class to; the coordinate half is derived from the observation itself.

    Every observed row also yields a Source Hint, including an UNVERSIONED
    Non-Temporal row, which observes no state: what its hint carries is the
    object it denotes and the participation its read licensed, which is the whole
    of what an effective-Locking write asks of it. A row whose (family-effective)
    primary key, version column, or Transaction-Time interval is absent from its
    own observed columns is defensively skipped — never reachable for a
    well-formed corpus model, but this seam takes no data on faith. A versioned
    entity is never also temporal (`m-opt-lock`/`m-descriptor`: the two are
    mutually exclusive), so each row takes exactly one branch.

    The statement's own as-of coordinates are deliberately no part of that
    EVIDENCE. What a write settles against is the state its value came from, and
    that state is what the key names; the pin that selected it is a property of
    the read, so two pins selecting one milestone retain one indistinguishable
    piece of evidence. The pin rides each hint instead (``pin`` below), where it
    answers a different question — whether this value may be written at all —
    rather than which state a write settles against.

    ``find`` is always INSTANCE-form, which projects every applicable Column, so
    an observed row's columns are the COMPLETE persisted row a Predecessor Row
    requires. Under Relational Document Layout the read ALSO carried the row's raw
    Structured Column past the fan-out that decoded those members, and a temporal
    observation retains it (`m-unit-work`) so a successor is patched from what the
    row held rather than rebuilt from the members this model declares — at no
    extra query, because the predecessor read already materialized it.

    ``ledger`` is the participating unit of work, absent for a standalone read.
    Its two answers are the participation each hint carries and the evidence it
    already holds for a state this read saw again; a standalone read stamps no
    participation and shares nothing beyond this one pass.

    ``pin`` is the read's own whole-graph as-of coordinate, which each hint
    carries for a TEMPORAL row and leaves absent otherwise — the same rule the
    typed materializer applies to a node's own lifecycle state, so a Typed node
    and a Wire node of one row answer the same pin to the finite-Transaction-Time
    refusal every keyed verb runs.
    """
    participation = None if ledger is None else ledger.participation
    hints: dict[int, SourceHint] = {}
    # One observed state, one retained observation within this pass, so two
    # projections of one row answer one claim exactly as graph aliases do.
    pass_states: dict[ObservedStateKey, RetainedObservation] = {}
    for observed in observations:
        resolved = _observed_object(meta, observed)
        if resolved is None:  # pragma: no cover - defends a malformed model/projection
            continue
        object_key, declaring_entity, observation = resolved
        observed_pin = pin if is_temporal(declaring_entity) else None
        if observation is None:
            hints[observed.node] = SourceHint(
                observed.entity, object_key, participation, None, observed_pin
            )
            continue
        key = observed_state_key(object_key, observation, declaring_entity)
        held = pass_states.get(key)
        if held is None:
            held = RetainedObservation(key, observation, participation)
            if ledger is not None:
                held = ledger.retain(held)
            pass_states[key] = held
        hints[observed.node] = SourceHint(
            observed.entity, object_key, participation, held, observed_pin
        )
    return MappingProxyType(hints)


def _observed_object(
    meta: Metamodel, observed: _ObservedRow
) -> tuple[ObjectKey, EntityMetadata, WriteObservation | None] | None:
    """One observed row's object, its declaring root, and the evidence it
    observed — or ``None`` where the row cannot be read as an object at all.

    The evidence is absent for an unversioned Non-Temporal row, which observes
    no state; the object and the declaring root are answered either way, because
    a hint names the object whether or not a state stands behind it.
    """
    observed_fields = observed.columns
    entity = meta.entity(observed.entity)
    if entity is None:  # pragma: no cover - a materialized row resolved within this model
        return None
    declaring_entity = declaring(meta, entity)
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a materialized node always owns rows
        return None
    pk_attrs = family_primary_key(meta, declaring_entity)
    pk_columns = [slot_column(layout, attr.identity) for attr in pk_attrs]
    if not pk_attrs or any(  # pragma: no cover - defends a malformed model/projection
        column not in observed_fields for column in pk_columns
    ):
        return None
    object_key = ObjectKey(
        observed.entity,
        tuple(
            (attr.identity.name, observed_fields[column])
            for attr, column in zip(pk_attrs, pk_columns, strict=True)
        ),
    )
    version_attr = version_attribute(meta, declaring_entity)
    if version_attr is not None:
        version_column = slot_column(layout, version_attr.identity)
        if version_column not in observed_fields:  # pragma: no cover - malformed projection
            return object_key, declaring_entity, None
        return (
            object_key,
            declaring_entity,
            VersionObservation(observed_version=cast("int", observed_fields[version_column])),
        )
    if not is_temporal(declaring_entity):
        return object_key, declaring_entity, None
    tx_axis = tx_time_axis(declaring_entity)
    tx_start_column, _tx_end_column = axis_columns(layout, tx_axis)
    if tx_start_column not in observed_fields:  # pragma: no cover - malformed model/projection
        return object_key, declaring_entity, None
    return (
        object_key,
        declaring_entity,
        _temporal_observation(
            members(placed_members(meta, entity, layout)), observed_fields, observed.document
        ),
    )


def _temporal_observation(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
    document: object | None = None,
) -> TemporalObservation:
    """The :class:`TemporalObservation` a materialized TEMPORAL row licenses: its
    complete Predecessor Row.

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
    ``Transaction.find``) — and :func:`row_payload` is the extraction a
    materializing predicate-write resolve applies to its OWN rows, so both sides
    share the SAME rule rather than duplicating it. Extraction renders nothing of
    its own: every value passes through EXACTLY as ``fields`` carries it, which
    for a scalar or interval column is exactly what the port returned (a real
    ``timestamptz`` column may be a driver-native ``datetime.datetime`` or the
    native-infinity sentinel, never pre-rendered to a wire string here) — the
    SAME driver-native-passthrough contract every other temporal bind already
    carries; wire-rendering for REPORTING is the conformance ADAPTER's own
    boundary concern (`parallax.conformance.engine._json_bind`), never this
    seam's.

    ``document`` is the row's raw Structured Column under Relational Document
    Layout, which the Predecessor Row retains beside — never among — those
    members, so a successor built from it keeps keys no member declares. It is
    absent under `Columns` layout, where the row has no such column.
    """
    return TemporalObservation(
        predecessor=PredecessorRow(row_payload(member_columns, fields), document=document)
    )


def row_payload(
    member_columns: Mapping[str, tuple[str, bool]],
    fields: Mapping[str, object],
) -> dict[str, object]:
    """``fields``'s COMPLETE payload: every applicable member the row carries a
    column for, value-object documents included.

    The one extraction a real TEMPORAL find's Predecessor Row
    (:func:`_temporal_observation`, above) and a materializing predicate-write
    resolve's own Predecessor Row share, so a Predecessor Row means the same
    thing whichever read produced it (`m-unit-work` "A Predecessor Row is the
    complete, immutable persisted state").

    ``column in fields`` is the whole of the rule. Both readings are
    INSTANCE-form or carry every declared document, so a member absent from
    ``fields`` is one the entity does not store rather than one this extraction
    chose to drop, and a value-object-free entity contributes nothing either way.
    """
    return {
        name: fields[column]
        for name, (column, _is_value_object) in member_columns.items()
        if column in fields
    }
