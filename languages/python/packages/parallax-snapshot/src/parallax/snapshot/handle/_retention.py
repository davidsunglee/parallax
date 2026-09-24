from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core.base import retain_document_value
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import (
    EntityStateRow,
    ObjectKey,
    ObservedStateKey,
    ParticipationToken,
    PredecessorRow,
    ReadOrigin,
    RetainedObservation,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    observed_state_key,
)
from parallax.snapshot.handle._family import (
    declaring,
    family_primary_key,
    is_temporal,
    tx_time_axis,
    version_attribute,
)

__all__ = [
    "ObservationLedger",
    "ObservedRows",
    "ReadSources",
    "deferred_evidence",
]


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state.

    ``node`` is the Page occurrence this row converted into, which is how
    the evidence built from it reaches the value that projection becomes.
    ``entity`` is the row's own resolved concrete Entity. ``state`` is absent
    until the Page judges that occurrence, and is then the declared-name
    :class:`EntityStateRow` view over its shared positional Entity State.
    ``document`` is the raw Structured Column under Relational Document Layout.

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    node: int
    entity: EntityIdentity
    state: EntityStateRow | None
    document: object | None


type _PendingObservation = int | _ObservedRow


class ObservedRows:
    """What one :func:`~parallax.snapshot.handle.find` collects for the write
    side while its rows are still live.

    Occurrence references paired with their row provenance, recorded through
    :meth:`observe_occurrence`: each receives its members only from the judged,
    Page-owned Entity State, and :func:`deferred_evidence` is the only consumer.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        self._rows: list[_PendingObservation] = []

    def observe_occurrence(
        self,
        node: int,
        entity: EntityIdentity,
        document: object | None,
    ) -> None:
        """Record a projection whose columns will come from its judged Entity State."""
        self._rows.append(node if document is None else _ObservedRow(node, entity, None, document))


type ReadSources = Mapping[int, ReadOrigin]
"""The Read Origin each observed projection's value carries, keyed by that
projection's own index in the read's sealed Page.

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


def _released_callback(*_args: object) -> None:
    raise RuntimeError("all deferred read sources have already resolved")


class _DeferredReadSources(Mapping[int, ReadOrigin]):
    """Evidence retained only after its page-owned Entity State is judged valid."""

    __slots__ = (
        "_admitted",
        "_entity",
        "_ledger",
        "_meta",
        "_observations",
        "_participation",
        "_pass_states",
        "_pin",
        "_primary_key",
        "_resolved",
        "_resolved_count",
        "_shapes",
    )

    def __init__(
        self,
        meta: Metamodel,
        observations: ObservedRows,
        admitted: Callable[[int], tuple[EntityLayout, tuple[object, ...]] | None],
        entity: Callable[[int], EntityIdentity],
        primary_key: Callable[[int], object | None],
        *,
        ledger: ObservationLedger | None,
        pin: Pin,
    ) -> None:
        self._meta = meta
        self._shapes: dict[EntityIdentity, _ObservationShape | None] = {}
        retained: list[_PendingObservation] = []
        for pending in observations._rows:  # pyright: ignore[reportPrivateUsage] - same-module transfer
            if not isinstance(pending, _ObservedRow):
                retained.append(pending)
                continue
            shape = self._shapes.get(pending.entity)
            if shape is None and pending.entity not in self._shapes:
                shape = _observation_shape(meta, pending.entity)
                self._shapes[pending.entity] = shape
            retained.append(
                _ObservedRow(
                    pending.node,
                    pending.entity,
                    pending.state,
                    (None if pending.document is None else retain_document_value(pending.document)),
                )
                if shape is not None and shape.temporal
                else pending.node
            )
        self._observations = retained
        self._admitted = admitted
        self._entity = entity
        self._primary_key = primary_key
        self._ledger = ledger
        self._participation = None if ledger is None else ledger.participation
        # One observed state, one retained observation within this pass, so two
        # projections of one row answer one claim exactly as graph aliases do.
        self._pass_states: dict[ObservedStateKey, RetainedObservation] = {}
        self._pin = pin
        self._resolved: list[ReadOrigin | None] = [None] * len(retained)
        self._resolved_count = 0

    def __getitem__(self, key: int) -> ReadOrigin:
        try:
            resolved = self._resolved[key]
        except IndexError:
            raise KeyError(key) from None
        if resolved is None:
            self._refresh_one(key)
            resolved = self._resolved[key]
        if resolved is None:
            raise KeyError(key)
        return resolved

    def __iter__(self) -> Iterator[int]:
        return (index for index, origin in enumerate(self._resolved) if origin is not None)

    def __len__(self) -> int:
        return self._resolved_count

    def _refresh_one(self, key: int) -> None:
        try:
            pending = self._observations[key]
        except IndexError:  # pragma: no cover - Root Views request Page occurrence indices only
            raise KeyError(key) from None
        entity = self._entity(key) if isinstance(pending, int) else pending.entity
        self._observations[key] = key
        shape = self._shapes.get(entity)
        if shape is None and entity not in self._shapes:
            shape = _observation_shape(self._meta, entity)
            self._shapes[entity] = shape
        if shape is not None and shape.version_member is None and not shape.temporal:
            primary_key = self._primary_key(key)
            if primary_key is None:  # pragma: no cover - conforming roots carry identity
                return
            self._resolved[key] = ReadOrigin.from_single_primary_key(
                entity, shape.primary_key[0], primary_key, self._participation
            )
            self._resolved_count += 1
            if self._resolved_count == len(self._observations):
                self._release_inputs()
            return
        admitted = self._admitted(key)
        # Invalid roots suppress their complete origin map before this callback.
        if admitted is None:  # pragma: no cover
            return
        layout, member_row = admitted
        if self._ledger is None and shape is not None:
            primary_key = self._primary_key(key)
            if primary_key is None:  # pragma: no cover - conforming roots carry identity
                return
            self._resolved[key] = ReadOrigin.deferred(
                entity,
                _StandaloneObservedEvidence(
                    entity,
                    primary_key,
                    shape,
                    layout,
                    member_row,
                    None if isinstance(pending, int) else pending.document,
                ),
                pin=self._pin if shape.temporal else None,
            )
            self._resolved_count += 1
            if self._resolved_count == len(self._observations):
                self._release_inputs()
            return
        observed = _ObservedRow(
            key,
            entity,
            EntityStateRow.over_declared_members(
                layout.member_selection, member_row, absent=ABSENT
            ),
            None if isinstance(pending, int) else pending.document,
        )
        origin = _retain_observed(
            self._meta,
            observed,
            participation=self._participation,
            pass_states=self._pass_states,
            shapes=self._shapes,
            ledger=self._ledger,
            pin=self._pin,
        )
        if origin is not None:
            self._resolved[key] = origin
            self._resolved_count += 1
            if self._resolved_count == len(self._observations):
                self._release_inputs()

    def _release_inputs(self) -> None:
        self._observations.clear()
        self._shapes.clear()
        self._pass_states.clear()
        self._admitted = cast(
            "Callable[[int], tuple[EntityLayout, tuple[object, ...]] | None]", _released_callback
        )
        self._entity = cast("Callable[[int], EntityIdentity]", _released_callback)
        self._primary_key = cast("Callable[[int], object | None]", _released_callback)
        self._ledger = None
        self._meta = cast("Metamodel", None)


def deferred_evidence(
    meta: Metamodel,
    observations: ObservedRows,
    admitted: Callable[[int], tuple[EntityLayout, tuple[object, ...]] | None],
    entity: Callable[[int], EntityIdentity],
    primary_key: Callable[[int], object | None],
    *,
    ledger: ObservationLedger | None,
    pin: Pin,
) -> ReadSources:
    """A mapping that retains evidence as valid judged states become reachable
    (`m-opt-lock`; ADR 0013; `m-unit-work` "Observation lifetime").

    Each projection's Read Origin resolves when first read. Versioned and
    temporal evidence comes from the Entity State the Page judged for that
    projection (``admitted``), viewed by declared member name, and is retained
    only once that state is reachable and valid.

    Evidence is addressed by the exact state it is about
    (:func:`~parallax.core.unit_work.observed_state_key`), so a second read of
    one primary key that resolves to a different version or milestone is
    evidence about the row it saw rather than an overwrite of the first read's.
    The identity half is the :class:`~parallax.core.unit_work.ObjectKey` a later
    keyed write computes, over the row's own resolved concrete Entity (never
    family-normalized to the root), which is what ``tx.update(copy)`` resolves
    its instance's class to.

    An unversioned Non-Temporal row observes no state, yet still yields a Read
    Origin naming the object and the participation its read licensed, which is
    the whole of what an effective-Locking write asks of it.

    ``pin`` is the read's whole-graph as-of coordinate and no part of the
    evidence, so two pins selecting one milestone retain one state. Each hint of
    a temporal row carries it instead, where it answers whether the value may be
    written at all rather than which state a write settles against.

    ``ledger`` is the participating unit of work, absent for a standalone read.
    It supplies the participation each hint carries and answers evidence it
    already holds for a state this read saw again; a standalone read stamps no
    participation.

    Under Relational Document Layout a temporal observation also retains the
    row's raw Structured Column, so a successor is patched from what the row
    held rather than rebuilt from the members this model declares.
    """
    return _DeferredReadSources(
        meta,
        observations,
        admitted,
        entity,
        primary_key,
        ledger=ledger,
        pin=pin,
    )


def _retain_observed(
    meta: Metamodel,
    observed: _ObservedRow,
    *,
    participation: ParticipationToken | None,
    pass_states: dict[ObservedStateKey, RetainedObservation],
    shapes: dict[EntityIdentity, _ObservationShape | None],
    ledger: ObservationLedger | None,
    pin: Pin | None,
) -> ReadOrigin | None:
    resolved = _observed_object(meta, observed, shapes)
    if resolved is None:  # pragma: no cover - defends a malformed model/projection
        return None
    object_key, declaring_entity, observation = resolved
    observed_pin = pin if is_temporal(declaring_entity) else None
    if observation is None:
        return ReadOrigin(observed.entity, object_key, participation, None, observed_pin)
    key = observed_state_key(object_key, observation, declaring_entity)
    held = pass_states.get(key)
    if held is None:
        held = RetainedObservation(key, observation, participation)
        if ledger is not None:
            held = ledger.retain(held)
        pass_states[key] = held
    return ReadOrigin(observed.entity, object_key, participation, held, observed_pin)


@dataclass(frozen=True, slots=True)
class _ObservationShape:
    """The family facts one concrete Entity's rows are read through, every
    member named by its DECLARED name."""

    identity: EntityIdentity
    declaring: EntityMetadata
    primary_key: tuple[str, ...]
    version_member: str | None
    temporal: bool
    tx_start_member: str | None


class _StandaloneObservedEvidence:
    __slots__ = (
        "_document",
        "_layout",
        "_member_row",
        "_primary_key",
        "_shape",
    )

    _primary_key: object
    _shape: _ObservationShape | None

    def __init__(
        self,
        entity: EntityIdentity,
        primary_key: object,
        shape: _ObservationShape,
        layout: EntityLayout,
        member_row: tuple[object, ...],
        document: object | None,
    ) -> None:
        if entity != shape.identity:  # pragma: no cover - shape cache keys concrete Entities
            raise ValueError("deferred evidence entity does not match its observation shape")
        self._primary_key = primary_key
        self._shape = shape
        self._layout = layout
        self._member_row = member_row
        self._document = None if document is None else retain_document_value(document)

    def object_key(self) -> ObjectKey:
        return self._materialized()[0]

    @property
    def entity(self) -> EntityIdentity:
        shape = self._shape
        if shape is None:
            return cast("tuple[ObjectKey, RetainedObservation]", self._primary_key)[0].entity
        return shape.identity

    def observation(self) -> RetainedObservation:
        return self._materialized()[1]

    def _materialized(self) -> tuple[ObjectKey, RetainedObservation]:
        shape = self._shape
        if shape is None:
            return cast("tuple[ObjectKey, RetainedObservation]", self._primary_key)
        values = (
            cast("tuple[object, ...]", self._primary_key)
            if len(shape.primary_key) > 1
            else (self._primary_key,)
        )
        object_key = ObjectKey(shape.identity, tuple(zip(shape.primary_key, values, strict=True)))
        members = EntityStateRow.over_declared_members(
            self._layout.member_selection, self._member_row, absent=ABSENT
        )
        if shape.version_member is not None:
            evidence: WriteObservation = VersionObservation(
                observed_version=cast("int", members[shape.version_member])
            )
        else:
            evidence = _temporal_observation(members, self._document)
        retained = RetainedObservation(
            observed_state_key(object_key, evidence, shape.declaring), evidence, None
        )
        held = (object_key, retained)
        self._primary_key = held
        self._shape = None
        self._member_row = ()
        self._document = None
        return held


def _observation_shape(meta: Metamodel, identity: EntityIdentity) -> _ObservationShape | None:
    entity = meta.entity(identity)
    if entity is None:  # pragma: no cover - a materialized row resolved within this model
        return None
    declaring_entity = declaring(meta, entity)
    version_attr = version_attribute(meta, declaring_entity)
    temporal = is_temporal(declaring_entity)
    return _ObservationShape(
        identity=identity,
        declaring=declaring_entity,
        primary_key=tuple(
            attr.identity.name for attr in family_primary_key(meta, declaring_entity)
        ),
        version_member=None if version_attr is None else version_attr.identity.name,
        temporal=temporal,
        tx_start_member=(tx_time_axis(declaring_entity).start_attribute.name if temporal else None),
    )


def _observed_object(
    meta: Metamodel,
    observed: _ObservedRow,
    shapes: dict[EntityIdentity, _ObservationShape | None],
) -> tuple[ObjectKey, EntityMetadata, WriteObservation | None] | None:
    """One observed row's object, its declaring root, and the evidence it
    observed — or ``None`` where the row cannot be read as an object at all.

    The evidence is absent for an unversioned Non-Temporal row, which observes
    no state; the object and the declaring root are answered either way, because
    a hint names the object whether or not a state stands behind it.
    """
    shape = shapes.get(observed.entity)
    if shape is None and observed.entity not in shapes:
        shape = _observation_shape(meta, observed.entity)
        shapes[observed.entity] = shape
    if shape is None:
        return None
    members = observed.state
    if members is None:  # pragma: no cover - deferred retention supplies judged state
        return None
    if not shape.primary_key or any(  # pragma: no cover - defends a malformed model/projection
        name not in members for name in shape.primary_key
    ):
        return None
    object_key = ObjectKey(
        observed.entity, tuple((name, members[name]) for name in shape.primary_key)
    )
    version_member = shape.version_member
    if version_member is not None:
        if version_member not in members:  # pragma: no cover - malformed projection
            return object_key, shape.declaring, None
        return (
            object_key,
            shape.declaring,
            VersionObservation(observed_version=cast("int", members[version_member])),
        )
    if not shape.temporal:
        return object_key, shape.declaring, None
    if cast("str", shape.tx_start_member) not in members:  # pragma: no cover - malformed model
        return object_key, shape.declaring, None
    return object_key, shape.declaring, _temporal_observation(members, observed.document)


def _temporal_observation(
    members: EntityStateRow, document: object | None = None
) -> TemporalObservation:
    """The :class:`TemporalObservation` a materialized TEMPORAL row licenses: its
    complete Predecessor Row.

    The Predecessor Row retains EVERY applicable member ``members`` carries —
    scalars, value-object documents, the primary key, and both axis intervals —
    because temporal expansion carries members the authored mutation never
    mentioned, and because the close's own address and gate are read off the same
    observed row rather than from separate per-axis fields. The bounds are the
    only members every consumer names; the rest ride through as the payload a
    chained or split successor carries forward (`m-bitemp-write` "head/tail old
    values"; `m-value-object` "the document rides every chained/split row
    whole").

    ``members`` is the judged positional state viewed by DECLARED member name,
    and it is retained as that view: nothing here copies, renders, or re-keys
    it. Every value passes through EXACTLY as the row carries it, which
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
    return TemporalObservation(predecessor=PredecessorRow(members, document=document))
