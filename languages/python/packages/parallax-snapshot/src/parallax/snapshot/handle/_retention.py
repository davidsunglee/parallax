"""``parallax.snapshot.handle._retention`` — write-observation retention.

The evidence a graph-form read leaves on the values it publishes: the Write
Observation each materialized row licensed, filed under the object it observed
plus that observation's own coordinate, and the Read Origin that selects it. A
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
observed row is read by DECLARED member name once it reaches the helpers that
derive its object, version, or milestone: judged, Page-owned positional Entity
State is viewed directly through
:meth:`~parallax.core.unit_work.EntityStateRow.over_declared_members`, and a
physical-column-keyed mapping a direct fixture supplied is remapped through the
row-owning Entity's Storage Layout view first, so no helper here reads both
namings. A materializing predicate-write resolve views its own rows the same
way and streams them whole into its
:class:`~parallax.core.unit_work.MaterializedWriteGroup`
(:mod:`parallax.snapshot.handle._predicate_writes`), so a Predecessor Row means
the same thing whichever read produced it.

The participating unit of work is reached as :class:`ObservationLedger` — the two
answers retention needs from a transaction — rather than as the whole scope, so a
standalone read satisfies this module by passing none of it.

Names crossing a module boundary are spelled bare; a helper whose every caller
lives here keeps its underscore. Privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, never by per-name
underscores.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
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
    entity_layout,
    family_primary_key,
    is_temporal,
    members,
    tx_time_axis,
    version_attribute,
)

__all__ = [
    "ObservationLedger",
    "ObservedRows",
    "ReadSources",
    "deferred_evidence",
    "retain_evidence",
]


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observable state.

    ``node`` is the Page occurrence this row converted into, which is how
    the evidence built from it reaches the value that projection becomes.
    ``entity`` is the row's own resolved concrete Entity. The state arrives in
    exactly one of two namings, and in neither until the Page judges that
    occurrence: ``members`` is the declared-name view over its shared positional
    Entity State, and ``columns`` is the physical-column-keyed mapping a direct
    fixture supplied, remapped to declared names only when the row is retained.
    ``document`` is the raw Structured Column under Relational Document Layout.

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    node: int
    entity: EntityIdentity
    columns: Mapping[str, object] | None
    members: EntityStateRow | None
    document: object | None


type _PendingObservation = int | _ObservedRow


class ObservedRows:
    """What one :func:`~parallax.snapshot.handle.find` collects for the write
    side while its rows are still live.

    Occurrence references paired with their row provenance: graph-form reads use
    :meth:`observe_occurrence` and receive their members only from the judged,
    Page-owned Entity State, while direct unit-work fixtures may supply a
    physical-column-keyed mapping through :meth:`observe_row`. Iteration is the
    only way out and :func:`retain_evidence` is the only consumer.
    """

    __slots__ = ("_rows",)

    def __init__(self) -> None:
        self._rows: list[_PendingObservation] = []

    def observe_row(
        self,
        node: int,
        entity: EntityIdentity,
        columns: Mapping[str, object],
        document: object | None,
    ) -> None:
        """Snapshot one materialized row's observable state, keyed by physical
        column. ``columns`` stays the caller's, so a later edit to it cannot reach
        the recorded observation."""
        self._rows.append(_ObservedRow(node, entity, dict(columns), None, document))

    def observe_occurrence(
        self,
        node: int,
        entity: EntityIdentity,
        document: object | None,
    ) -> None:
        """Record a projection whose columns will come from its judged Entity State."""
        self._rows.append(
            node if document is None else _ObservedRow(node, entity, None, None, document)
        )

    def __iter__(self) -> Iterator[_ObservedRow]:
        """Every row observed so far, in the order the executor materialized them
        (root first, then each level in plan order). Nothing outside this module
        can name what is yielded, and nothing addresses a hint by that order:
        :func:`retain_evidence` keys its answer by each row's own projection."""
        return (observed for observed in self._rows if isinstance(observed, _ObservedRow))


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
                    pending.columns,
                    pending.members,
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
            None,
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
    """A mapping that retains evidence as valid judged states become reachable."""
    return _DeferredReadSources(
        meta,
        observations,
        admitted,
        entity,
        primary_key,
        ledger=ledger,
        pin=pin,
    )


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

    Every observed row also yields a Read Origin, including an UNVERSIONED
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
    hints: dict[int, ReadOrigin] = {}
    # One observed state, one retained observation within this pass, so two
    # projections of one row answer one claim exactly as graph aliases do.
    pass_states: dict[ObservedStateKey, RetainedObservation] = {}
    shapes: dict[EntityIdentity, _ObservationShape | None] = {}
    for observed in observations:
        origin = _retain_observed(
            meta,
            observed,
            participation=participation,
            pass_states=pass_states,
            shapes=shapes,
            ledger=ledger,
            pin=pin,
        )
        if origin is not None:
            hints[observed.node] = origin
    return MappingProxyType(hints)


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
    member named by its DECLARED name; ``member_columns`` is the physical
    translation a column-keyed source is remapped through before any of the
    others is read."""

    identity: EntityIdentity
    declaring: EntityMetadata
    primary_key: tuple[str, ...]
    version_member: str | None
    temporal: bool
    tx_start_member: str | None
    member_columns: Mapping[str, tuple[str, bool]]


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
    layout = entity_layout(meta, entity)
    if layout is None:  # pragma: no cover - a materialized node always owns rows
        return None
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
        member_columns=members(layout),
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

    The row is read by declared member name throughout: a judged positional
    state arrives already viewed that way, and a physical-column-keyed source is
    remapped through the shape's own column translation before any member is
    read.
    """
    shape = shapes.get(observed.entity)
    if shape is None and observed.entity not in shapes:
        shape = _observation_shape(meta, observed.entity)
        shapes[observed.entity] = shape
    if shape is None:
        return None
    members = observed.members
    if members is None:
        columns = observed.columns
        if columns is None:  # pragma: no cover - deferred retention supplies judged state
            return None
        members = EntityStateRow.remap(shape.member_columns, columns)
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

    ``members`` is the row's state keyed by DECLARED member name — a judged
    positional state viewed directly, or a physical-column-keyed source already
    remapped — and it is retained as that view: nothing here copies, renders, or
    re-keys it. Every value passes through EXACTLY as the row carries it, which
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
