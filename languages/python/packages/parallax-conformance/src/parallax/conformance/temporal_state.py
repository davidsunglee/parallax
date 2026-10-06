from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Generator, Iterable, Mapping, Sequence

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY, normalize_instant
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    TemporalDimension,
    ValueObjectIdentity,
)
from parallax.core.unit_work import (
    ObservedStateKey,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.unit_work.plan import RangeAcquisition
from parallax.core.unit_work.planned import (
    Finite,
    PlannedClose,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
)
from parallax.core.unit_work.planner import TemporalStateKey

__all__ = [
    "AmbiguousObservationError",
    "MilestoneEdgeError",
    "TemporalShadow",
    "predecessor_row",
]

# A tracked milestone's slot: its object identity plus the milestone's own edge —
# `parallax.core.temporal_read.Edge`, the same value the production read side
# keys an observation by, since every coordinate reaching this module is
# normalized to a UTC instant before it is stored (:func:`_coordinate`).
# Identity alone will not do — one key may hold several disjoint Valid-Time
# rectangles current on Transaction Time at once (`m-bitemp-write`), so a
# pk-keyed slot silently loses every rectangle but the last one written.
_ObjectKey = tuple[str, tuple[object, ...], temporal_read.Edge]


class AmbiguousObservationError(ValueError):
    """This tracker cannot name one milestone, so it refuses rather than
    silently guessing which one a later step means. Two shapes reach it: several
    current milestones are tracked for one (entity, pk) — several disjoint
    Valid-Time rectangles of one key may be current on Transaction Time
    (`m-bitemp-write.md`), and a step's row names the object rather than the
    rectangle, so the remedy is a write naming the find it settles against
    (`m-case-format` "Settling against a grouped find"); or two tracked
    milestones of one key carry the SAME edge, which no edge could tell apart, so
    the state itself is unaddressable."""


class MilestoneEdgeError(ValueError):
    """A milestone's as-of axis start is not a finite instant, so it keys no
    edge. An edge is the guaranteed-selecting start instant per declared axis
    (`m-temporal-read`); the open bound belongs to an axis END alone."""


class TemporalShadow:
    """The case-local map of (entity, primary key, milestone edge) -> that tracked
    CURRENT (``out_z = infinity``) milestone, advanced as each temporal write
    plans.

    Keying by the milestone's own edge rather than by identity alone is what lets
    one key hold every rectangle it genuinely has current.
    """

    __slots__ = ("_current", "_materialized", "_out_of_band", "_overtaken")

    def __init__(self) -> None:
        self._current: dict[_ObjectKey, TemporalObservation] = {}
        self._out_of_band = False
        self._overtaken: set[_ObjectKey] = set()
        self._materialized: set[_ObjectKey] = set()

    def accounts_for(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> bool:
        """Whether what this tracker holds for the milestone ``row`` addresses is
        the WHOLE stored row.

        A milestone stays ADDRESSABLE whatever the answer — the key is the case's
        own — but a consumer that REBUILDS a row rather than merely addressing one
        has to answer for the difference, and this is the question it asks.

        ``False`` in exactly two states, both of them consequences of out-of-band
        statements (:meth:`note_out_of_band_write`):

        - the milestone was tracked when those statements ran, so they may have
          stored something no member of it names; and
        - no milestone of this key is tracked at all, which after such statements
          means the row they may have left is one the tracker has no account of
          whatsoever.

        A milestone the case's own writes opened AFTERWARDS is ``True`` again: a
        Planned Insert's entry row IS the whole row the flush writes, so tracking
        it establishes a complete account of that milestone even though this
        tracker never re-reads. Overtaking is per MILESTONE for that reason, not
        per case.

        The bound is the tightest one available without reading the statements:
        which rows a naive ``sql`` string touched is not something this tracker
        can know, so every milestone it held when they ran is treated as
        overtaken even if they named another target.
        """
        if not self._out_of_band:
            return True
        slot = self._slot(model, entity, row)
        return slot is not None and slot not in self._overtaken

    def moved_by_materialization(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> bool:
        """Whether the milestone ``row`` addresses is one a materializing
        predicate write of this case already retired
        (:meth:`note_materialized_write`).

        ``True`` means the tracked milestone is stale in the strongest sense: the
        database holds a successor of it opened at that write's own instant, and a
        close addressed at what this tracker still holds current would match no
        row at all.
        """
        slot = self._slot(model, entity, row)
        return slot is not None and slot in self._materialized

    @contextlib.contextmanager
    def staged(self, *, doomed: bool) -> Generator[None]:
        """One choreography unit's advances, staged on that unit's own
        transaction outcome (`m-unit-work` abort contract).

        A unit's writes retire and open milestones as they resolve, so a later
        step of the SAME unit observes them — read-your-own-writes holds for this
        tracker exactly as it holds for the rows. A DOOMED unit's transaction
        then erases the rows it wrote, and this discards the advances it made
        with them: a step AFTER the abort resolves the milestone the abort left
        standing, never a successor no transaction ever stored, and a milestone
        the aborted unit retired or re-accounted for is restored to what it was.

        The whole tracker is captured rather than a per-key undo log, which is
        exact because one unit at a time advances it: the state before a doomed
        unit IS the state its abort restores.
        """
        if not doomed:
            yield
            return
        current = dict(self._current)
        overtaken = set(self._overtaken)
        materialized = set(self._materialized)
        out_of_band = self._out_of_band
        try:
            yield
        finally:
            self._current = current
            self._overtaken = overtaken
            self._materialized = materialized
            self._out_of_band = out_of_band

    def note_materialized_write(self, entity: EntityMetadata) -> None:
        """Record that a materializing predicate write over ``entity`` committed —
        it resolved its own rows and, for each, retired the milestone it found and
        opened a successor (`m-opt-lock` predicate-selected writes materialize).

        Production performs that resolve and plans those rows internally, and
        hands back neither, so this tracker cannot advance to what the write left:
        which of ``entity``'s milestones its predicate selected is not derivable
        here at all. Every milestone of ``entity`` tracked right now is therefore
        recorded as MOVED, which is a stronger statement than the doubt
        out-of-band statements raise (:meth:`accounts_for`) — the row it names is
        not merely unaccounted for, it is no longer the current one — and it is
        the tightest bound available without the plan.

        Milestones of OTHER entities are untouched: a predicate names one target,
        and a write of that target moves no other table's rows.
        """
        name = entity.identity.name
        self._materialized |= {key for key in self._current if key[0] == name}

    def note_out_of_band_write(self) -> None:
        """Record that statements outside this tracker's own accounting ran
        against the tables it shadows (`m-case-format` ``given.apply``).

        Every milestone held right now MAY have been overtaken by them and is
        treated as though it were (:meth:`accounts_for` states the bound), and
        every key with none is left with no account of a row they may have
        written. Both states are one-way for the milestones they name — the
        tracker never re-reads — and both end for a key the moment a later write
        opens a milestone of it.
        """
        self._out_of_band = True
        self._overtaken |= set(self._current)

    def seed_fixtures(
        self, model: Metamodel, entity: EntityMetadata, rows: Sequence[Mapping[str, object]]
    ) -> None:
        """Seed the tracker from a case's loaded fixture rows for ``entity``
        (`given.fixtures: true`, or a scenario case's own default
        lifecycle load). A non-temporal entity's rows are a no-op.

        Each row holds managed members, its open axis ends
        :data:`~parallax.core.base.INFINITY`, as case ingress decodes a fixture.
        It is already the whole persisted milestone, Attribute-named, so it IS the
        Predecessor Row a later close addresses, gates on, and carries state
        forward from.
        """
        shape = temporal_read.view(model).shape(entity.identity)
        if shape is None or isinstance(shape, temporal_read.NonTemporal):
            return
        entity_name = entity.identity.name
        _tx_start, tx_end = _axis_names(model, entity, TemporalDimension.TRANSACTION_TIME)
        pk_names = _primary_key_names(model, entity)
        start_names = _axis_start_names(model, entity)
        for row in rows:
            if row.get(tx_end) is not INFINITY:
                continue  # not current on Transaction Time
            key = self._key(entity_name, pk_names, start_names, row)
            self._track(key, TemporalObservation(predecessor=PredecessorRow(members=row)))

    def resolve(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> TemporalObservation | None:
        """The tracked observation a temporal update/terminate/updateUntil/
        terminateUntil instruction's close/chain consumes, or ``None`` for a
        milestone this tracker has never seen open (an insert, or a genuinely
        unobserved close the write itself will surface as a conflict/stale
        error at execution).

        A writeSequence/scenario step's row names the object and not the
        rectangle, so the one current milestone is returned, and several raise
        :class:`AmbiguousObservationError`.
        """
        slot = self._slot(model, entity, row)
        return None if slot is None else self._current[slot]

    def _slot(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> _ObjectKey | None:
        """The one tracked slot ``row`` addresses, or ``None`` for a key this
        tracker holds no current milestone of.

        The ONE place an input's identity is turned into a slot, so every question
        asked about the addressed milestone — what it is, and whether it is still
        a whole account of the stored row — is asked of the same milestone.
        """
        entity_name = entity.identity.name
        pk_names = _primary_key_names(model, entity)
        identity = (entity_name, tuple(row[name] for name in pk_names))
        candidates = [key for key in self._current if key[:2] == identity]
        if not candidates:
            return None
        if len(candidates) > 1:
            raise AmbiguousObservationError(
                f"{entity_name}: {len(candidates)} current milestones are tracked for "
                f"{dict(zip(pk_names, identity[1], strict=True))!r}, at the edges "
                f"{sorted(str(key[2]) for key in candidates)} — this input names none of "
                "them, and an observation is keyed by the milestone it observed"
            )
        return candidates[0]

    def retire(
        self, model: Metamodel, entity: EntityMetadata, observed: TemporalObservation
    ) -> None:
        """Drop the milestone a close addressed.

        Exactly that one: a key's OTHER current rectangles are untouched, because
        the write neither closed nor superseded them. The retirement is driven by
        the observation the close CONSUMED rather than by the Planned Close the
        plan carries, because a Milestone Target addresses a milestone by its
        axis ENDS while a tracked milestone is keyed by its own edge — the axis
        STARTS — and the plan carries no way back from one to the other.
        """
        key = self._key(
            entity.identity.name,
            _primary_key_names(model, entity),
            _axis_start_names(model, entity),
            observed.predecessor.members,
        )
        self._current.pop(key, None)
        self._overtaken.discard(key)
        self._materialized.discard(key)

    def track_opened(
        self,
        model: Metamodel,
        steps: Iterable[PlannedWrite],
        *,
        retired: Iterable[ObservedStateKey] = (),
    ) -> None:
        """Track every milestone ``steps`` OPENS as the current state a later step
        observes, once every milestone in ``retired`` — the states a bound range
        changed — has been dropped.

        The successor rows come off the plan the write lane already produced, so
        the tracker holds exactly what the flush will write rather than a second
        expansion of the same topology computed beside it. A Planned Insert's
        entry row is the whole milestone, axis bounds and framework-owned values
        included, which is exactly the Predecessor Row a later close addresses,
        gates on, and carries state forward from.

        Rows of a NON-temporal entity are skipped: they open no milestone, and a
        ledger of them would answer no question a later step can ask.
        """
        for state in retired:
            if not isinstance(state, TemporalStateKey):
                continue
            key = (
                state.object.entity.name,
                tuple(value for _name, value in state.object.primary_key),
                state.milestone,
            )
            self._current.pop(key, None)
            self._overtaken.discard(key)
            self._materialized.discard(key)
        for step in steps:
            if not isinstance(step, PlannedInsert):
                continue
            entity = model.entity(step.entity)
            if entity is None:  # pragma: no cover - a planned step names an accepted Entity
                continue
            shape = temporal_read.view(model).shape(entity.identity)
            if shape is None or isinstance(shape, temporal_read.NonTemporal):
                continue
            pk_names = _primary_key_names(model, entity)
            start_names = _axis_start_names(model, entity)
            for entry in step.entries:
                predecessor = predecessor_row(entry.row.attributes, entry.row.value_objects)
                key = self._key(entity.identity.name, pk_names, start_names, predecessor.members)
                self._track(key, TemporalObservation(predecessor=predecessor))

    def keep_unchanged(
        self,
        model: Metamodel,
        steps: Iterable[PlannedWrite],
        observed: Iterable[tuple[EntityMetadata, TemporalObservation]],
    ) -> None:
        """Track again each ``observed`` milestone — retired as its write
        resolved (:meth:`retire`) — that no step of ``steps`` closes, revises, or
        removes: a write that leaves a milestone as it was keeps it current
        (`m-txtime-write`, `m-bitemp-write`)."""
        changed: set[tuple[str, tuple[object, ...], tuple[dt.datetime | None, ...]]] = set()
        for step in steps:
            if isinstance(step, PlannedClose | PlannedTemporalRevision | PlannedTemporalRemoval):
                target = step.target
                changed.add(
                    (
                        step.entity.name,
                        target.key_values,
                        tuple(
                            _end_coordinate(end.instant) if isinstance(end, Finite) else None
                            for end in target.end_values
                        ),
                    )
                )
        for entity, observation in observed:
            members = observation.predecessor.members
            pk_names = _primary_key_names(model, entity)
            ends: list[dt.datetime | None] = []
            for dimension in _declared_dimensions(model, entity):
                ends.append(_end_coordinate(members[_axis_names(model, entity, dimension)[1]]))
            address = (entity.identity.name, tuple(members[name] for name in pk_names))
            if (*address, tuple(ends)) in changed:
                continue
            key = self._key(
                entity.identity.name, pk_names, _axis_start_names(model, entity), members
            )
            self._track(key, observation)

    def coverage(
        self, model: Metamodel, acquisition: RangeAcquisition
    ) -> tuple[PredecessorRow, ...]:
        """The tracked current milestones of ``acquisition``'s object that
        overlap its Valid-Time window, or all of them where it has none — what
        the execution's own coverage read returns from the rows this tracker
        accounts for."""
        entity = acquisition.entity
        identity = (entity.identity.name, (acquisition.key_value,))
        window = acquisition.valid_time_window
        if window is None:
            return tuple(
                observation.predecessor
                for key, observation in self._current.items()
                if key[:2] == identity
            )
        shape = temporal_read.view(model).shape(entity.identity)
        assert shape is not None  # the facet covers every accepted Entity
        covered: list[PredecessorRow] = []
        for key, observation in self._current.items():
            if key[:2] != identity:
                continue
            predecessor = observation.predecessor
            coverage = temporal_read.valid_time_coverage(shape, predecessor, None)
            if coverage is not None and coverage.overlaps(window):
                covered.append(predecessor)
        return tuple(covered)

    def _track(self, key: _ObjectKey, observation: TemporalObservation) -> None:
        """Store one milestone in its own slot, refusing a slot already taken.

        A slot is keyed by the milestone's edge, so two current milestones of one
        key sharing an edge are a state no write can address: overwriting would
        silently drop one and hand every later step the other.

        Storing a milestone is also what re-establishes a whole account of it: the
        row stored here came from the case's own fixtures or from the plan that
        wrote it, so neither the doubt earlier out-of-band statements raised nor
        an earlier materializing write's displacement can still stand for the slot
        it occupies.
        """
        existing = self._current.get(key)
        if existing is not None and existing.predecessor.members != observation.predecessor.members:
            entity_name, pk, edge = key
            raise AmbiguousObservationError(
                f"{entity_name}: two current milestones of {pk!r} carry the edge {edge!r} — "
                "an edge names exactly one milestone, so no observation could tell them apart"
            )
        self._current[key] = observation
        self._overtaken.discard(key)
        self._materialized.discard(key)

    @staticmethod
    def _key(
        entity_name: str,
        pk_names: Sequence[str],
        start_names: Mapping[TemporalDimension, str],
        row: Mapping[str, object],
    ) -> _ObjectKey:
        return (
            entity_name,
            tuple(row[name] for name in pk_names),
            _edge({dimension: _coordinate(row[name]) for dimension, name in start_names.items()}),
        )


def predecessor_row(
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> PredecessorRow:
    """The ONE conversion from identity-keyed carriers to a Predecessor Row.

    Every engine-side milestone — a row the write plan opened, a node a grouped
    find returned — arrives as a scalar map keyed by
    :class:`~parallax.core.metamodel.AttributeIdentity` beside a Value Object map
    keyed by :class:`~parallax.core.metamodel.ValueObjectIdentity`, and a
    Predecessor Row is read by DECLARED MEMBER NAME, which is also the spelling a
    milestone edge is keyed by. Both carriers convert here so the tracked
    milestone and the observed one can never be flattened two different ways.

    The row it builds is purely LOGICAL: neither carrier retains the raw
    Structured Column document the observing read returned, so
    :attr:`~parallax.core.unit_work.PredecessorRow.document` is absent and a
    successor is patched from the declared members rather than from what the row
    physically held.
    """
    members: dict[str, object] = {identity.name: value for identity, value in attributes.items()}
    for identity, value in value_objects.items():
        members[identity.path[-1]] = value
    return PredecessorRow(members=members)


_NOT_AN_INSTANT = "an as-of axis start is a finite instant, and {value!r} is not one"


def _end_coordinate(value: object) -> dt.datetime | None:
    return None if value is INFINITY else _coordinate(value)


def _coordinate(value: object) -> dt.datetime:
    """One managed axis-start value as the shared comparable an edge is keyed by.

    An axis START is always a finite instant — the open bound belongs to an axis
    END alone — and it is normalized to UTC, so two offsets of one instant name
    one edge rather than two.
    """
    if not isinstance(value, dt.datetime):
        raise MilestoneEdgeError(_NOT_AN_INSTANT.format(value=value))
    return normalize_instant(value)


def _declared_dimensions(model: Metamodel, entity: EntityMetadata) -> tuple[TemporalDimension, ...]:
    """``entity``'s declared as-of dimensions in canonical axis order."""
    shape = temporal_read.view(model).shape(entity.identity)
    if isinstance(shape, temporal_read.Bitemporal):
        return (TemporalDimension.VALID_TIME, TemporalDimension.TRANSACTION_TIME)
    return (TemporalDimension.TRANSACTION_TIME,)


def _edge(coordinates: Mapping[TemporalDimension, dt.datetime]) -> temporal_read.Edge:
    """One milestone's edge from its per-axis start instants. An axis absent from
    ``coordinates`` is one the target does not declare, which is exactly what an
    :class:`~parallax.core.temporal_read.Edge` spells as ``None``."""
    return temporal_read.Edge(
        valid_time=coordinates.get(TemporalDimension.VALID_TIME),
        tx_time=coordinates.get(TemporalDimension.TRANSACTION_TIME),
    )


def _axis_start_names(model: Metamodel, entity: EntityMetadata) -> Mapping[TemporalDimension, str]:
    """``entity``'s family-effective axis START Attribute name per DECLARED axis —
    the members an edge is made of (`m-temporal-read`: a milestone's edge is its
    guaranteed-selecting from-instant per axis, and an axis END never
    participates)."""
    return {
        dimension: _axis_names(model, entity, dimension)[0]
        for dimension in _declared_dimensions(model, entity)
    }


def _axis_names(
    model: Metamodel, entity: EntityMetadata, dimension: TemporalDimension
) -> tuple[str, str]:
    """``entity``'s family-effective Attribute names for one temporal dimension it declares."""
    axis = temporal_read.view(model).axis(entity.identity, dimension)
    assert axis is not None  # every caller asks for a dimension the entity declares
    return axis.start_attribute.name, axis.end_attribute.name


def _primary_key_names(model: Metamodel, entity: EntityMetadata) -> list[str]:
    """``entity``'s family-effective primary-key Attribute names.

    A participant's key is declared on its family root alone, so the applicable
    member chain the Inheritance Facet precomputes is what carries it.
    """
    position = inheritance.view(model).entity(entity.identity)
    members = entity.declared_attributes if position is None else position.applicable_attributes
    return [
        attribute.identity.name
        for attribute in members
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
