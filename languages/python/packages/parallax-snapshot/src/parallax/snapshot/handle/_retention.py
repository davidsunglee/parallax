from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core import inheritance, opt_lock, temporal_read
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.opt_lock import ExplicitVersion, TransactionTimeDerived
from parallax.core.temporal_read import (
    NON_TEMPORAL,
    Bitemporal,
    Pin,
    TemporalFacet,
    TransactionTimeOnly,
)
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

__all__ = [
    "ObservationLedger",
    "ObservedRows",
    "ReadSources",
    "deferred_read_sources",
]


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    """One materialized row's observation provenance, pending its judged state.

    ``node`` is the Page occurrence this row converted into, which is how
    the evidence built from it reaches the value that projection becomes.
    ``entity`` is the row's own resolved concrete Entity. ``document`` is the
    raw Structured Column under Relational Document Layout, held as the dialect
    transferred it and read only (:class:`PredecessorRow` owns that contract).

    It holds neither a raw driver row nor a materialized node, so an observation
    outlives the read that produced it without pinning either.
    """

    node: int
    entity: EntityIdentity
    document: object | None


type _PendingObservation = int | _ObservedRow


class ObservedRows:
    """What one :func:`~parallax.snapshot.handle.find` collects for the write
    side while its rows are still live.

    Occurrence references paired with their row provenance, recorded through
    :meth:`observe_occurrence`: each receives its members only from the judged,
    Page-owned Entity State, and :func:`deferred_read_sources` is the only consumer.
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
        self._rows.append(node if document is None else _ObservedRow(node, entity, document))


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


type _Locator = ExplicitVersion | TransactionTimeOnly | Bitemporal
"""The owner object that says what evidence a row carries: its family's shared
explicit version key, or its family's shared Temporal Shape."""


def _released_callback(*_args: object) -> None:
    raise RuntimeError("all deferred read sources have already resolved")


class _DeferredReadSources(Mapping[int, ReadOrigin]):
    """Evidence retained only after its page-owned Entity State is judged valid.

    The pass holds the three family-fact owners by reference until every
    origin resolves, and each retained row keeps only the owner object its
    family's evidence is read through.
    """

    __slots__ = (
        "_admitted",
        "_entity",
        "_families",
        "_keys",
        "_ledger",
        "_observations",
        "_participation",
        "_pass_states",
        "_pin",
        "_primary_key",
        "_resolved",
        "_resolved_count",
        "_temporal",
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
        self._families = inheritance.view(meta)
        self._keys = opt_lock.view(meta)
        self._temporal = temporal_read.view(meta)
        retained: list[_PendingObservation] = [
            pending
            if not isinstance(pending, _ObservedRow)
            or isinstance(self._keys.key(pending.entity), TransactionTimeDerived)
            else pending.node
            for pending in observations._rows  # pyright: ignore[reportPrivateUsage] - same-module transfer
        ]
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
            self._resolve_origin(key)
            resolved = self._resolved[key]
        if resolved is None:
            raise KeyError(key)
        return resolved

    def __iter__(self) -> Iterator[int]:
        return (index for index, origin in enumerate(self._resolved) if origin is not None)

    def __len__(self) -> int:
        return self._resolved_count

    def _resolve_origin(self, key: int) -> None:
        try:
            pending = self._observations[key]
        except IndexError:  # pragma: no cover - Root Views request Page occurrence indices only
            raise KeyError(key) from None
        entity = self._entity(key) if isinstance(pending, int) else pending.entity
        self._observations[key] = key
        locator: _Locator
        match self._keys.key(entity):
            case None:
                return
            case ExplicitVersion() as version:
                locator = version
            case TransactionTimeDerived():
                locator = self._temporal_shape(entity)
            case _:
                self._resolve_unversioned(key, entity)
                return
        admitted = self._admitted(key)
        # Invalid roots suppress their complete origin map before this callback.
        if admitted is None:  # pragma: no cover
            return
        layout, member_row = admitted
        document = None if isinstance(pending, int) else pending.document
        if self._ledger is None:
            primary_key = self._primary_key(key)
            if primary_key is None:  # pragma: no cover - conforming roots carry identity
                return
            self._settle(
                key,
                ReadOrigin.deferred(
                    entity,
                    _DeferredEvidence(primary_key, locator, layout, member_row, document),
                    pin=None if isinstance(locator, ExplicitVersion) else self._pin,
                ),
            )
            return
        self._settle(
            key,
            _retain_observed(
                layout,
                member_row,
                document,
                locator,
                participation=self._participation,
                pass_states=self._pass_states,
                ledger=self._ledger,
                pin=self._pin,
            ),
        )

    def _resolve_unversioned(self, key: int, entity: EntityIdentity) -> None:
        """An unversioned Non-Temporal row's origin, which names its object and
        observes no state."""
        primary_key = self._primary_key(key)
        view = self._families.entity(entity)
        # Conforming roots carry identity, and the facet covers every accepted Entity.
        if primary_key is None or view is None:  # pragma: no cover
            return
        self._settle(
            key,
            ReadOrigin.from_single_primary_key(
                entity, view.primary_key.identity.name, primary_key, self._participation
            ),
        )

    def _temporal_shape(self, entity: EntityIdentity) -> TransactionTimeOnly | Bitemporal:
        shape = self._temporal.shape(entity)
        if not isinstance(shape, TransactionTimeOnly | Bitemporal):  # pragma: no cover
            raise RuntimeError(f"{entity.canonical}: a Transaction-Time key has no temporal shape")
        return shape

    def _settle(self, key: int, origin: ReadOrigin) -> None:
        self._resolved[key] = origin
        self._resolved_count += 1
        if self._resolved_count == len(self._observations):
            self._release_inputs()

    def _release_inputs(self) -> None:
        self._observations.clear()
        self._pass_states.clear()
        self._admitted = cast(
            "Callable[[int], tuple[EntityLayout, tuple[object, ...]] | None]", _released_callback
        )
        self._entity = cast("Callable[[int], EntityIdentity]", _released_callback)
        self._primary_key = cast("Callable[[int], object | None]", _released_callback)
        self._ledger = None
        self._families = cast("inheritance.InheritanceFacet", None)
        self._keys = cast("opt_lock.OptimisticLockFacet", None)
        self._temporal = cast("TemporalFacet", None)


def deferred_read_sources(
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
    layout: EntityLayout,
    member_row: tuple[object, ...],
    document: object | None,
    locator: _Locator,
    *,
    participation: ParticipationToken | None,
    pass_states: dict[ObservedStateKey, RetainedObservation],
    ledger: ObservationLedger | None,
    pin: Pin,
) -> ReadOrigin:
    object_key, observation, key = _observed_state(
        layout, member_row[layout.primary_key[0]], member_row, document, locator
    )
    held = pass_states.get(key)
    if held is None:
        held = RetainedObservation(key, observation, participation)
        if ledger is not None:
            held = ledger.retain(held)
        pass_states[key] = held
    observed_pin = None if isinstance(locator, ExplicitVersion) else pin
    return ReadOrigin(layout.concrete, object_key, participation, held, observed_pin)


def _observed_state(
    layout: EntityLayout,
    primary_key: object,
    member_row: tuple[object, ...],
    document: object | None,
    locator: _Locator,
) -> tuple[ObjectKey, WriteObservation, ObservedStateKey]:
    """One judged row's object, the evidence its family's ``locator`` reads off
    it, and the exact state that evidence is about.

    The object is the row's own concrete Entity paired with ``primary_key``
    under the name of the family key at its layout position. An
    explicit-version family is Non-Temporal by formation, so its observed state
    key reads no Temporal Shape.
    """
    key_member = cast("AttributeIdentity", layout.members[layout.primary_key[0]])
    object_key = ObjectKey(layout.concrete, ((key_member.name, primary_key),))
    if isinstance(locator, ExplicitVersion):
        members = EntityStateRow.over_declared_members(
            layout.member_selection, member_row, absent=ABSENT
        )
        observation: WriteObservation = VersionObservation(
            observed_version=cast("int", members[locator.attribute.name])
        )
        return object_key, observation, observed_state_key(object_key, observation, NON_TEMPORAL)
    observation = _temporal_observation(layout, member_row, document)
    return object_key, observation, observed_state_key(object_key, observation, locator)


class _DeferredEvidence:
    """A standalone read's evidence for one row, materialized on first use.

    Until then it holds the row's judged state and its family's ``_locator``;
    afterwards it holds only the produced Object Key and observation.
    """

    __slots__ = (
        "_document",
        "_layout",
        "_locator",
        "_member_row",
        "_primary_key",
    )

    _primary_key: object
    _locator: _Locator | None
    _layout: EntityLayout | None

    def __init__(
        self,
        primary_key: object,
        locator: _Locator,
        layout: EntityLayout,
        member_row: tuple[object, ...],
        document: object | None,
    ) -> None:
        self._primary_key = primary_key
        self._locator = locator
        self._layout = layout
        self._member_row = member_row
        self._document = document

    def object_key(self) -> ObjectKey:
        return self._materialized()[0]

    @property
    def entity(self) -> EntityIdentity:
        layout = self._layout
        return self._materialized()[0].entity if layout is None else layout.concrete

    def observation(self) -> RetainedObservation:
        return self._materialized()[1]

    def _materialized(self) -> tuple[ObjectKey, RetainedObservation]:
        locator = self._locator
        layout = self._layout
        if locator is None or layout is None:
            return cast("tuple[ObjectKey, RetainedObservation]", self._primary_key)
        object_key, evidence, key = _observed_state(
            layout, self._primary_key, self._member_row, self._document, locator
        )
        held = (object_key, RetainedObservation(key, evidence, None))
        self._primary_key = held
        self._locator = None
        self._layout = None
        self._member_row = ()
        self._document = None
        return held


def _temporal_observation(
    layout: EntityLayout, member_row: tuple[object, ...], document: object | None
) -> TemporalObservation:
    """The :class:`TemporalObservation` a materialized TEMPORAL row licenses: its
    complete Predecessor Row.

    The Predecessor Row retains EVERY applicable member ``member_row`` carries —
    scalars, value-object documents, the primary key, and both axis intervals —
    because temporal expansion carries members the authored mutation never
    mentioned, and because the close's own address and gate are read off the same
    observed row rather than from separate per-axis fields. The bounds are the
    only members every consumer names; the rest ride through as the payload a
    chained or split successor carries forward (`m-bitemp-write` "head/tail old
    values"; `m-value-object` "the document rides every chained/split row
    whole").

    ``member_row`` is the judged positional state, aligned to ``layout``'s
    member selection, and it is retained by reference: nothing here copies,
    renders, or re-keys it. Every value passes through EXACTLY as the row
    carries it, which for a scalar or interval column is exactly what the port
    returned (a real
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
        predecessor=PredecessorRow.over_row(layout.member_selection, member_row, document, ABSENT)
    )
