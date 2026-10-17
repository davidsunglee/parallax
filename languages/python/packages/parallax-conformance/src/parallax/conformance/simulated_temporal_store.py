from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Generator, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core.base import INFINITY, normalize_instant
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import (
    AttributeIdentity,
    DocumentMember,
    EntityIdentity,
    EntityMetadata,
    Leaf,
    MemberShape,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    TemporalDimension,
    ValueObjectIdentity,
)
from parallax.core.write_plan import (
    ObjectStateKey,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.write_plan.keys import TemporalObjectStateKey
from parallax.core.write_plan.steps import (
    Finite,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
)

__all__ = [
    "AmbiguousObservationError",
    "MilestoneEdgeError",
    "SimulatedStoreError",
    "SimulatedTemporalStore",
    "predecessor_row",
]

# A stored milestone's slot: its object identity plus the milestone's own edge —
# `parallax.core.temporal_read.Edge`, the same value the production read side
# keys an observation by, since every coordinate reaching this module is
# normalized to a UTC instant before it is stored (:func:`_coordinate`).
# Identity alone will not do — one key may hold several disjoint Valid-Time
# rectangles current on Transaction Time at once (`m-temporal-write`), so a
# pk-keyed slot silently loses every rectangle but the last one written.
_ObjectKey = tuple[str, tuple[object, ...], temporal_read.Edge]

# A stored milestone's complete physical address: its object identity plus
# each declared axis END in canonical axis order, the open bound spelled
# `None` — what a Milestone Target names a row by. A planned step carries no
# axis start, so this, not the slot, is how a step finds the row it acts on.
_Address = tuple[str, tuple[object, ...], tuple[dt.datetime | None, ...]]


class SimulatedStoreError(ValueError):
    """What a case asks of the simulated rows names no one stored row, so the
    store refuses rather than guess: a refusal of the case's composition, not
    a defect of the store."""


class AmbiguousObservationError(SimulatedStoreError):
    """This store cannot name one milestone, so it refuses rather than
    silently guessing which one a later step means. Three shapes reach it:
    several current milestones are stored for one (entity, pk) — several
    disjoint Valid-Time rectangles of one key may be current on Transaction
    Time (`m-temporal-write.md`), and a step's row names the object rather
    than the rectangle, so the remedy is a write naming the find it settles
    against (`m-case-format` "Settling against a grouped find"); two stored
    milestones of one key carry the SAME edge, which no edge could tell apart;
    or two of them share one complete address, which no planned step could
    tell apart. Either of the last two leaves the state itself
    unaddressable."""


class MilestoneEdgeError(SimulatedStoreError):
    """A milestone's as-of axis start is not a finite instant, so it keys no
    edge, or an axis end is neither a finite instant nor the open bound, so it
    addresses no row. An edge is the guaranteed-selecting start instant per
    declared axis (`m-temporal-read`); the open bound belongs to an axis END
    alone."""


@dataclass(frozen=True, slots=True)
class _StoredRow:
    """One current stored milestone: the observation a later write consumes,
    and the complete address a planned step names it by."""

    observation: TemporalObservation
    address: _Address


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """The canonical rows and accounting flags one simulated transaction
    restores; the address view is rebuilt from the rows rather than kept."""

    current: dict[_ObjectKey, _StoredRow]
    overtaken: set[_ObjectKey]
    materialized: set[_ObjectKey]
    out_of_band: bool


class SimulatedTemporalStore:
    """The case-local stored rows of a case's temporal Entities: each CURRENT
    (``out_z = infinity``) milestone, keyed by (entity, primary key, milestone
    edge), as the database holds it once the case's own fixtures and writes
    have run.

    Keying by the milestone's own edge rather than by identity alone is what
    lets one key hold every rectangle it genuinely has current. A view from
    each row's complete address to its slot is maintained beside the rows with
    every change, so a planned step finds the row it acts on without a scan.
    These are simulated database rows, not an attempt's ownership: what a unit
    of work owns is its own to track.
    """

    __slots__ = ("_current", "_located", "_materialized", "_out_of_band", "_overtaken")

    def __init__(self) -> None:
        self._current: dict[_ObjectKey, _StoredRow] = {}
        self._located: dict[_Address, tuple[_ObjectKey, ...]] = {}
        self._out_of_band = False
        self._overtaken: set[_ObjectKey] = set()
        self._materialized: set[_ObjectKey] = set()

    def has_complete_stored_row(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> bool:
        """Whether what this store holds for the milestone ``row`` addresses is
        the WHOLE stored row.

        A milestone stays ADDRESSABLE whatever the answer — the key is the case's
        own — but a consumer that REBUILDS a row rather than merely addressing one
        has to answer for the difference, and this is the question it asks.

        ``False`` in exactly two states, both of them consequences of out-of-band
        statements (:meth:`note_out_of_band_write`):

        - the milestone was stored when those statements ran, so they may have
          stored something no member of it names; and
        - no milestone of this key is stored at all, which after such statements
          means the row they may have left is one the store has no account of
          whatsoever.

        A milestone the case's own writes opened AFTERWARDS is ``True`` again: a
        Planned Insert's entry row IS the whole row the flush writes, so storing
        it establishes a complete account of that milestone even though this
        store never re-reads. Overtaking is per MILESTONE for that reason, not
        per case.

        The bound is the tightest one available without reading the statements:
        which rows a naive ``sql`` string touched is not something this store
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

        ``True`` means the stored milestone is stale in the strongest sense: the
        database holds a successor of it opened at that write's own instant, and a
        close addressed at what this store still holds current would match no
        row at all.
        """
        slot = self._slot(model, entity, row)
        return slot is not None and slot in self._materialized

    @contextlib.contextmanager
    def transaction(self, *, rollback: bool) -> Generator[None]:
        """One simulated database transaction over these rows: what runs inside
        it changes them as it runs, and they keep those changes only if it
        commits.

        A declared ``rollback``, and any exception escaping the transaction —
        an interruption included — restore every row and accounting flag to
        what they were when it began. The canonical rows are captured once,
        shallowly, which is exact because a stored row is replaced rather than
        changed in place.
        """
        snapshot = _Snapshot(
            dict(self._current), set(self._overtaken), set(self._materialized), self._out_of_band
        )
        try:
            yield
        except BaseException:
            self._restore(snapshot)
            raise
        if rollback:
            self._restore(snapshot)

    @contextlib.contextmanager
    def staged(self, *, doomed: bool) -> Generator[None]:
        """One choreography unit's advances, staged on that unit's own
        transaction outcome (`m-unit-work` abort contract).

        A unit's writes retire and open milestones as they resolve, so a later
        step of the SAME unit observes them — read-your-own-writes holds for this
        store exactly as it holds for the rows. A DOOMED unit's transaction
        then erases the rows it wrote, and this discards the advances it made
        with them: a step AFTER the abort resolves the milestone the abort left
        standing, never a successor no transaction ever stored, and a milestone
        the aborted unit retired or re-accounted for is restored to what it was.
        """
        if not doomed:
            yield
            return
        with self.transaction(rollback=True):
            yield

    def note_materialized_write(self, entity: EntityMetadata) -> None:
        """Record that a materializing predicate write over ``entity`` committed —
        it resolved its own rows and, for each, retired the milestone it found and
        opened a successor (`m-opt-lock` predicate-selected writes materialize).

        Production performs that resolve and plans those rows internally, and
        hands back neither, so this store cannot advance to what the write left:
        which of ``entity``'s milestones its predicate selected is not derivable
        here at all. Every milestone of ``entity`` stored right now is therefore
        recorded as MOVED, which is a stronger statement than the doubt
        out-of-band statements raise (:meth:`has_complete_stored_row`) — the row
        it names is not merely unaccounted for, it is no longer the current one —
        and it is the tightest bound available without the plan.

        Milestones of OTHER entities are untouched: a predicate names one target,
        and a write of that target moves no other table's rows.
        """
        name = entity.identity.name
        self._materialized |= {key for key in self._current if key[0] == name}

    def note_out_of_band_write(self) -> None:
        """Record that statements outside this store's own accounting ran
        against the tables it simulates (`m-case-format` ``given.apply``).

        Every milestone held right now MAY have been overtaken by them and is
        treated as though it were (:meth:`has_complete_stored_row` states the
        bound), and every key with none is left with no account of a row they
        may have written. Both states are one-way for the milestones they name —
        the store never re-reads — and both end for a key the moment a later
        write opens a milestone of it.
        """
        self._out_of_band = True
        self._overtaken |= set(self._current)

    def seed_fixtures(
        self, model: Metamodel, entity: EntityMetadata, rows: Sequence[Mapping[str, object]]
    ) -> None:
        """Seed the store from a case's loaded fixture rows for ``entity``
        (`given.fixtures: true`, or a scenario case's own default
        lifecycle load). A non-temporal entity's rows are a no-op.

        Each row holds managed members, its open axis ends
        :data:`~parallax.core.base.INFINITY`, as case ingress decodes a fixture.
        It is already the whole persisted milestone, Attribute-named, so it IS the
        Predecessor Row a later close addresses, gates on, and carries state
        forward from.
        """
        layout = _layout(model, entity)
        if layout is None:
            return
        _tx_start, tx_end = _axis_names(model, entity, TemporalDimension.TRANSACTION_TIME)
        for row in rows:
            if row.get(tx_end) is not INFINITY:
                continue  # not current on Transaction Time
            self._track(layout, TemporalObservation(predecessor=PredecessorRow(members=row)))

    def predecessor_for(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> TemporalObservation | None:
        """The stored observation a temporal amend/terminate/amendUntil/
        terminateUntil instruction's close/chain consumes, or ``None`` for a
        milestone this store has never seen open (an insert, or a genuinely
        unobserved close the write itself will surface as a conflict/stale
        error at execution).

        A writeSequence/scenario step's row names the object and not the
        rectangle, so the one current milestone is returned, and several raise
        :class:`AmbiguousObservationError`.
        """
        slot = self._slot(model, entity, row)
        return None if slot is None else self._current[slot].observation

    def _slot(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
    ) -> _ObjectKey | None:
        """The one stored slot ``row`` addresses, or ``None`` for a key this
        store holds no current milestone of.

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
                f"{entity_name}: {len(candidates)} current milestones are stored for "
                f"{dict(zip(pk_names, identity[1], strict=True))!r}, at the edges "
                f"{sorted(str(key[2]) for key in candidates)} — this input names none of "
                "them, and an observation is keyed by the milestone it observed"
            )
        return candidates[0]

    def apply(self, model: Metamodel, step: PlannedWrite) -> None:
        """Change the stored rows as executing ``step`` changes the rows a
        database holds.

        An insert stores each temporal row it opens, as planned; a close or a
        removal retires the row its target addresses; a revision replaces the
        members it assigns, keeps every other member, and moves the row to its
        new edge where its Valid-Time start moved, a Value Object occurrence it
        assigns replacing the stored one whole. A guard, and every Non-Temporal
        step, leaves the stored rows as they are. Nothing a database would
        enforce is simulated: a target no stored row answers changes nothing.
        """
        match step:
            case PlannedInsert():
                self._open(model, step)
            case PlannedClose() | PlannedTemporalRemoval():
                slot = self._addressed(step.target, step.entity)
                if slot is not None:
                    self._forget(slot)
            case PlannedTemporalRevision():
                slot = self._addressed(step.target, step.entity)
                if slot is not None:
                    self._revise(model, step.entity, slot, step.assignments)
            case _:
                return

    def _open(self, model: Metamodel, step: PlannedInsert) -> None:
        entity = model.entity(step.entity)
        if entity is None:  # pragma: no cover - a planned step names an accepted Entity
            return
        layout = _layout(model, entity)
        if layout is None:
            return
        for entry in step.entries:
            predecessor = predecessor_row(entry.row.attributes, entry.row.value_objects)
            self._track(layout, TemporalObservation(predecessor=predecessor))

    def _revise(
        self,
        model: Metamodel,
        entity_identity: EntityIdentity,
        slot: _ObjectKey,
        assignments: PlannedAssignments,
    ) -> None:
        entity = model.entity(entity_identity)
        layout = None if entity is None else _layout(model, entity)
        assert layout is not None  # only a temporal row is ever stored and revised
        members = {
            **self._current[slot].observation.predecessor.members,
            **_members_by_name(assignments.attributes, assignments.value_objects),
        }
        overtaken = slot in self._overtaken
        materialized = slot in self._materialized
        self._forget(slot)
        revised = self._track(
            layout, TemporalObservation(predecessor=PredecessorRow(members=members))
        )
        # Revising assigns some members, so it re-accounts for none the store
        # had already lost track of.
        if overtaken:
            self._overtaken.add(revised)
        if materialized:
            self._materialized.add(revised)

    def _addressed(self, target: MilestoneTarget, entity: EntityIdentity) -> _ObjectKey | None:
        """The slot of the one stored row ``target`` addresses, or ``None``
        where it addresses none."""
        address = _target_address(entity, target)
        located = self._located.get(address)
        if located is None:
            return None
        if len(located) == 1:
            return located[0]
        raise AmbiguousObservationError(
            f"{entity.name}: {len(located)} current milestones of {target.key_values!r} "
            f"end at {address[2]!r} — a planned step addresses one row by its key and axis "
            "ends, and these share both"
        )

    def retire(
        self, model: Metamodel, entity: EntityMetadata, observed: TemporalObservation
    ) -> None:
        """Drop the milestone a close addressed.

        Exactly that one: a key's OTHER current rectangles are untouched, because
        the write neither closed nor superseded them. The retirement is driven by
        the observation the close CONSUMED rather than by the Planned Close the
        plan carries.
        """
        layout = _layout(model, entity)
        assert layout is not None  # only a temporal write consumes a temporal observation
        self._forget(layout.key(observed.predecessor.members))

    def track_opened(
        self,
        model: Metamodel,
        steps: Iterable[PlannedWrite],
        *,
        retired: Iterable[ObjectStateKey] = (),
    ) -> None:
        """Store every milestone ``steps`` OPENS as the current state a later step
        observes, once every milestone in ``retired`` — the states a bound range
        changed — has been dropped.

        The successor rows come off the plan the write lane already produced, so
        the store holds exactly what the flush will write rather than a second
        expansion of the same topology computed beside it. A Planned Insert's
        entry row is the whole milestone, axis bounds and framework-owned values
        included, which is exactly the Predecessor Row a later close addresses,
        gates on, and carries state forward from.

        Rows of a NON-temporal entity are skipped: they open no milestone, and a
        ledger of them would answer no question a later step can ask.
        """
        for state in retired:
            if not isinstance(state, TemporalObjectStateKey):
                continue
            self._forget(
                (
                    state.object.entity.name,
                    tuple(value for _name, value in state.object.primary_key),
                    state.milestone,
                )
            )
        for step in steps:
            if isinstance(step, PlannedInsert):
                self._open(model, step)

    def keep_unchanged(
        self,
        model: Metamodel,
        steps: Iterable[PlannedWrite],
        observed: Iterable[tuple[EntityMetadata, TemporalObservation]],
    ) -> None:
        """Store again each ``observed`` milestone — retired as its write
        resolved (:meth:`retire`) — that no step of ``steps`` closes, revises, or
        removes: a write that leaves a milestone as it was keeps it current
        (`m-temporal-write`)."""
        changed = {
            _target_address(step.entity, step.target)
            for step in steps
            if isinstance(step, PlannedClose | PlannedTemporalRevision | PlannedTemporalRemoval)
        }
        for entity, observation in observed:
            layout = _layout(model, entity)
            assert layout is not None  # only a temporal write observes a milestone
            if layout.address(observation.predecessor.members) not in changed:
                self._track(layout, observation)

    def coverage_acquisition(self, model: Metamodel) -> AcquireRows:
        """The row acquisition a unit of work planning against this case state
        reads its coverage through: each coverage read answers the stored
        current milestones of its object that overlap any of its Valid-Time
        windows, or all of them where it names none — what the execution's own
        coverage read returns from the rows this store holds, through the same
        consumer."""
        return _CaseStateAcquisition(self, model)

    def coverage_rows(
        self, model: Metamodel, request: CoverageReadRequest
    ) -> list[tuple[object, ...]]:
        """The stored current milestones ``request`` reads, each positional
        over its target's member selection."""
        entity = request.entity
        windows_of: dict[tuple[str, tuple[object, ...]], tuple[temporal_read.TimeInterval, ...]] = {
            (entity.identity.name, (term.key_value,)): term.valid_time_windows
            for term in request.terms
        }
        shape = temporal_read.view(model).shape(entity.identity)
        assert shape is not None  # the facet covers every accepted Entity
        members = _member_selection(model, entity).shape
        rows: list[tuple[object, ...]] = []
        for slot, stored in self._current.items():
            windows = windows_of.get((slot[0], slot[1]))
            if windows is None:
                continue
            predecessor = stored.observation.predecessor
            if windows:
                coverage = temporal_read.valid_time_coverage(shape, predecessor, None)
                if coverage is None or not any(coverage.overlaps(window) for window in windows):
                    continue
            rows.append(_positional(members, predecessor.members))
        return rows

    def _track(self, layout: _Layout, observation: TemporalObservation) -> _ObjectKey:
        """Store one milestone in its own slot, refusing a slot already taken,
        and answer that slot.

        A slot is keyed by the milestone's edge, so two current milestones of one
        key sharing an edge are a state no write can address: overwriting would
        silently drop one and hand every later step the other.

        Storing a milestone is also what re-establishes a whole account of it: the
        row stored here came from the case's own fixtures or from the plan that
        wrote it, so neither the doubt earlier out-of-band statements raised nor
        an earlier materializing write's displacement can still stand for the slot
        it occupies.
        """
        members = observation.predecessor.members
        key = layout.key(members)
        existing = self._current.get(key)
        if existing is None:
            address = layout.address(members)
            self._located[address] = (*self._located.get(address, ()), key)
        elif existing.observation.predecessor.members != members:
            entity_name, pk, edge = key
            raise AmbiguousObservationError(
                f"{entity_name}: two current milestones of {pk!r} carry the edge {edge!r} — "
                "an edge names exactly one milestone, so no observation could tell them apart"
            )
        else:
            address = existing.address
        self._current[key] = _StoredRow(observation, address)
        self._overtaken.discard(key)
        self._materialized.discard(key)
        return key

    def _forget(self, slot: _ObjectKey) -> None:
        stored = self._current.pop(slot, None)
        if stored is not None:
            remaining = tuple(other for other in self._located[stored.address] if other != slot)
            if remaining:
                self._located[stored.address] = remaining
            else:
                del self._located[stored.address]
        self._overtaken.discard(slot)
        self._materialized.discard(slot)

    def _restore(self, snapshot: _Snapshot) -> None:
        self._current = snapshot.current
        self._overtaken = snapshot.overtaken
        self._materialized = snapshot.materialized
        self._out_of_band = snapshot.out_of_band
        located: dict[_Address, tuple[_ObjectKey, ...]] = {}
        for slot, stored in self._current.items():
            located[stored.address] = (*located.get(stored.address, ()), slot)
        self._located = located


@dataclass(frozen=True, slots=True)
class _Layout:
    """How one temporal Entity's stored milestones are keyed and addressed:
    its family-effective primary-key, axis-start, and axis-end Attribute
    names."""

    entity: str
    keys: tuple[str, ...]
    starts: Mapping[TemporalDimension, str]
    ends: tuple[str, ...]

    def key(self, members: Mapping[str, object]) -> _ObjectKey:
        return (
            self.entity,
            tuple(members[name] for name in self.keys),
            _edge(
                {dimension: _coordinate(members[name]) for dimension, name in self.starts.items()}
            ),
        )

    def address(self, members: Mapping[str, object]) -> _Address:
        return (
            self.entity,
            tuple(members[name] for name in self.keys),
            tuple(_end_coordinate(members[name]) for name in self.ends),
        )


def _target_address(entity: EntityIdentity, target: MilestoneTarget) -> _Address:
    return (
        entity.name,
        target.key_values,
        tuple(
            _end_coordinate(end.instant) if isinstance(end, Finite) else None
            for end in target.end_values
        ),
    )


def _layout(model: Metamodel, entity: EntityMetadata) -> _Layout | None:
    """``entity``'s layout, or ``None`` for a Non-Temporal Entity, which opens
    no milestone."""
    shape = temporal_read.view(model).shape(entity.identity)
    if shape is None or isinstance(shape, temporal_read.NonTemporal):
        return None
    dimensions = _declared_dimensions(model, entity)
    return _Layout(
        entity.identity.name,
        tuple(_primary_key_names(model, entity)),
        _axis_start_names(model, entity),
        tuple(_axis_names(model, entity, dimension)[1] for dimension in dimensions),
    )


@dataclass(frozen=True, slots=True)
class _CaseStateAcquisition:
    """:meth:`SimulatedTemporalStore.coverage_acquisition`'s answer: coverage
    reads over the stored milestones, which hold no raw Structured Column."""

    store: SimulatedTemporalStore
    model: Metamodel

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if not isinstance(
            request, CoverageReadRequest
        ):  # pragma: no cover - planning reads coverage alone
            raise TypeError(f"case state answers coverage reads alone, not {request!r}")
        rows = self.store.coverage_rows(self.model, request)
        selection = _member_selection(self.model, request.entity)
        return consumer(request, selection, iter(rows), _ABSENT, None, len(rows))


def _member_selection(model: Metamodel, entity: EntityMetadata) -> EntityMemberSelection:
    position = inheritance.view(model).entity(entity.identity)
    assert position is not None  # every accepted Entity has a view
    return position.member_selection


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
    milestone edge is keyed by. Both carriers convert here so the stored
    milestone and the observed one can never be flattened two different ways.

    The row it builds is purely LOGICAL: neither carrier retains the raw
    Structured Column document the observing read returned, so
    :attr:`~parallax.core.write_plan.PredecessorRow.document` is absent and a
    successor is patched from the declared members rather than from what the row
    physically held.
    """
    return PredecessorRow(members=_members_by_name(attributes, value_objects))


def _members_by_name(
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> dict[str, object]:
    """Identity-keyed members by declared name, each top-level Value Object
    occurrence whole under its member's name."""
    members: dict[str, object] = {identity.name: value for identity, value in attributes.items()}
    for identity, value in value_objects.items():
        members[identity.path[-1]] = value
    return members


_ABSENT: Final = object()
"""The member a stored milestone does not hold, in the positional rows
:meth:`SimulatedTemporalStore.coverage_rows` answers."""


def _positional(shape: MemberShape, members: Mapping[str, object]) -> tuple[object, ...]:
    """``members`` positional over ``shape``, as a read's judged member row is:
    a member it does not name is :data:`_ABSENT`, and each Value Object
    occurrence is positional over its own shape."""
    return tuple(
        _positional_cell(member, members[member.name]) if member.name in members else _ABSENT
        for member in shape.members
    )


def _positional_cell(member: DocumentMember, value: object) -> object:
    if isinstance(member, Leaf) or value is None:
        return value
    if member.multiplicity is Multiplicity.MANY:
        return tuple(
            _positional(member.shape, cast("Mapping[str, object]", element))
            for element in cast("Sequence[object]", value)
        )
    return _positional(member.shape, cast("Mapping[str, object]", value))


_NOT_AN_INSTANT = "an as-of axis start is a finite instant, and {value!r} is not one"
_NOT_AN_END = "an as-of axis end is a finite instant or the open bound, and {value!r} is neither"


def _end_coordinate(value: object) -> dt.datetime | None:
    """One managed axis-end value as the comparable an address is keyed by: the
    open bound as ``None``, and a finite end normalized as a start is."""
    if value is INFINITY:
        return None
    if not isinstance(value, dt.datetime):
        raise MilestoneEdgeError(_NOT_AN_END.format(value=value))
    return normalize_instant(value)


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
