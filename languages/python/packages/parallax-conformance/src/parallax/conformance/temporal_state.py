"""Case-local temporal shadow state (engine translation layer only).

The conformance engine's write lanes (writeSequence / scenario / conflict) drive
production ``db.transact`` per choreography unit. A later unit's temporal write
needs "the observed current milestone" its
close/chain consumes, but the framework itself never issues an implicit resolving
read for one (`core/spec/m-txtime-write.md` / `m-bitemp-write.md`: "the engine
supplies observed rows from case state"). This module is the engine-side tracker
that makes that observation available WITHOUT a database round trip — fixtures (for
a case that loads them) seed it, and each temporal write advances it through the
SAME neutral topology (:mod:`parallax.core.txtime_write` /
:mod:`parallax.core.bitemp_write`) and the SAME expansion
(:func:`~parallax.core.unit_work.expand_milestone`) production finalization uses,
so COMPILE and RUN consume the identical in-memory state and the tracker can never
disagree with the rendered SQL.

Non-normative engine-internal bookkeeping: never serialized, never a
:class:`~parallax.core.unit_work.WriteInstruction` field, never consulted by
production code (:mod:`parallax.snapshot.handle`) — the conformance family's own
translation-layer state, mirroring how a real caller would have read the current
milestone via an earlier transaction-scoped find.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

from parallax.core import bitemp_write, inheritance, temporal_read, txtime_write
from parallax.core.base import normalize_instant
from parallax.core.metamodel import EntityMetadata, Metamodel, PrimaryKey, TemporalDimension
from parallax.core.unit_work import (
    KeyedWrite,
    PredecessorRow,
    TemporalAxes,
    TemporalObservation,
    expand_milestone,
)

__all__ = [
    "AmbiguousObservationError",
    "MilestoneEdgeError",
    "TemporalShadow",
    "observed_close_coordinates",
    "observed_edge",
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
    current milestones are tracked for one (entity, pk) and the input named no
    edge to choose between them — several disjoint Valid-Time rectangles of one
    key may be current on Transaction Time (`m-bitemp-write.md`), and the remedy
    is to name the observed milestone's own edge, which a conflict case authors
    beside its write; or two tracked milestones of one key carry the SAME edge,
    which no edge could tell apart, so the state itself is unaddressable."""


class MilestoneEdgeError(ValueError):
    """An observed milestone's edge does not name the target's declared as-of
    axes: it is short of one, or it supplies a coordinate for an axis the target
    does not declare. An edge is the guaranteed-selecting start instant per
    DECLARED axis (`m-temporal-read`), so either way it selects no milestone —
    a coordinate short of one axis is not a partial name for a milestone, and a
    coordinate on an undeclared axis names an axis the target has no milestones
    on."""


class TemporalShadow:
    """The case-local map of (entity, primary key, milestone edge) -> that tracked
    CURRENT (``out_z = infinity``) milestone, advanced as each temporal write
    plans.

    Keying by the milestone's own edge rather than by identity alone is what lets
    one key hold every rectangle it genuinely has current, and what lets a case
    that names an observed edge address exactly the milestone it observed.
    """

    __slots__ = ("_current",)

    def __init__(self) -> None:
        self._current: dict[_ObjectKey, TemporalObservation] = {}

    def seed_fixtures(
        self, model: Metamodel, entity: EntityMetadata, rows: Sequence[Mapping[str, object]]
    ) -> None:
        """Seed the tracker from a case's loaded fixture rows for ``entity``
        (`given.fixtures: true`, or a scenario/conflict case's own default
        lifecycle load). A non-temporal entity's rows are a no-op.

        A fixture row is already the whole persisted milestone, Attribute-named,
        so it IS the Predecessor Row a later close addresses, gates on, and
        carries state forward from.
        """
        shape = temporal_read.view(model).shape(entity.identity)
        if shape is None or isinstance(shape, temporal_read.NonTemporal):
            return
        entity_name = entity.identity.name
        _tx_start, tx_end = _axis_names(model, entity, TemporalDimension.TRANSACTION_TIME)
        pk_names = _primary_key_names(model, entity)
        start_names = _axis_start_names(model, entity)
        for row in rows:
            if row.get(tx_end) != "infinity":
                continue  # not current on Transaction Time
            key = self._key(entity_name, pk_names, start_names, row)
            self._track(key, TemporalObservation(predecessor=PredecessorRow(members=row)))

    def resolve(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        row: Mapping[str, object],
        edge: temporal_read.Edge | None = None,
    ) -> TemporalObservation | None:
        """The tracked observation a temporal update/terminate/updateUntil/
        terminateUntil instruction's close/chain consumes, or ``None`` for a
        milestone this tracker has never seen open (an insert, or a genuinely
        unobserved close the write itself will surface as a conflict/stale
        error at execution).

        ``edge`` is the observed milestone's own coordinate
        (:func:`observed_edge`), which a case authors beside its write. Given
        one, the milestone is addressed directly and a key holding several
        current rectangles is no obstacle. Given none — the shape every
        writeSequence/scenario step takes, whose row names the object and not the
        rectangle — the one current milestone is returned, and several raise
        :class:`AmbiguousObservationError`.
        """
        entity_name = entity.identity.name
        pk_names = _primary_key_names(model, entity)
        identity = (entity_name, tuple(row[name] for name in pk_names))
        if edge is not None:
            return self._current.get((*identity, edge))
        candidates = [
            (key[2], observation)
            for key, observation in self._current.items()
            if key[:2] == identity
        ]
        if not candidates:
            return None
        if len(candidates) > 1:
            raise AmbiguousObservationError(
                f"{entity_name}: {len(candidates)} current milestones are tracked for "
                f"{dict(zip(pk_names, identity[1], strict=True))!r}, at the edges "
                f"{sorted(str(edge) for edge, _ in candidates)} — this input names none of "
                "them, and an observation is keyed by the milestone it observed"
            )
        return candidates[0][1]

    def advance(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        instruction: KeyedWrite,
        tx_instant: str,
        observed: TemporalObservation | None,
    ) -> None:
        """Replace this pk's tracked current milestone(s) with the newly OPENED
        rows the SAME topology (:mod:`parallax.core.txtime_write` /
        :mod:`parallax.core.bitemp_write`) and the SAME expansion production
        finalization applies compute — never a separately re-derived arithmetic,
        so the tracker and the rendered SQL can never disagree (m-txtime-write.md
        / m-bitemp-write.md "the engine supplies observed rows from case
        state").

        Only the milestone ``observed`` names is retired. A key's OTHER current
        rectangles are untouched, because this write neither closed nor
        superseded them."""
        entity_name = entity.identity.name
        pk_names = _primary_key_names(model, entity)
        start_names = _axis_start_names(model, entity)
        is_bitemporal = isinstance(
            temporal_read.view(model).shape(entity.identity), temporal_read.Bitemporal
        )
        # Each facet's own `topology(mutation)` is single-param — the
        # entity-aware dispatch between the two facets belongs to the
        # composition root's `TemporalStrategy` adapter, which this
        # engine-internal tracker performs itself since it already has the
        # entity in hand.
        strategy = bitemp_write.RECTANGLE_SPLIT if is_bitemporal else txtime_write.MILESTONE_CHAIN
        topology = strategy.topology(instruction.mutation)
        opened = expand_milestone(
            topology,
            _axes(model, entity, bitemporal=is_bitemporal),
            transaction_instant=tx_instant,
            authored=instruction.rows[0],
            valid_from=instruction.valid_from,
            until=instruction.until,
            predecessor=None if observed is None else observed.predecessor,
        )
        if observed is not None:
            # The close retires exactly the milestone it addressed; a
            # terminate/terminateUntil chains nothing after it.
            self._current.pop(
                self._key(entity_name, pk_names, start_names, observed.predecessor.members), None
            )
        # An opened row is the whole milestone the mutation just wrote, axis
        # bounds included, so it is exactly the Predecessor Row a later step
        # observes.
        for milestone in opened:
            key = self._key(entity_name, pk_names, start_names, milestone.members)
            self._track(
                key, TemporalObservation(predecessor=PredecessorRow(members=milestone.members))
            )

    def _track(self, key: _ObjectKey, observation: TemporalObservation) -> None:
        """Store one milestone in its own slot, refusing a slot already taken.

        An edge names exactly one milestone (`m-case-format`), so two current
        milestones of one key sharing an edge are a state no case can address:
        overwriting would silently drop one and hand every later step the other.
        The independent grader refuses the same state where it scans for the one
        fixture row an edge selects.
        """
        existing = self._current.get(key)
        if existing is not None and existing.predecessor.members != observation.predecessor.members:
            entity_name, pk, edge = key
            raise AmbiguousObservationError(
                f"{entity_name}: two current milestones of {pk!r} carry the edge {edge!r} — "
                "an edge names exactly one milestone, so no observation could tell them apart"
            )
        self._current[key] = observation

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


def observed_edge(
    model: Metamodel,
    entity: EntityMetadata,
    *,
    valid_start: object | None,
    tx_start: object | None,
) -> temporal_read.Edge:
    """The edge coordinate a case authored for the milestone its write observed.

    Built from the SAME instant normalization :class:`TemporalShadow` keys its
    tracked milestones by, so a coordinate the case spells and a milestone the
    tracker holds agree by shared derivation rather than by two sites being
    careful.

    The target's DECLARED axes decide which coordinates are legal, in both
    directions: a declared axis the case named nothing for is refused, and so is
    a coordinate the case supplied for an axis the target does not declare. The
    second is what keeps `observedValidStart` a Bitemporal-only control key
    rather than a field a Transaction-Time-Only case may author and have
    silently dropped.
    """
    declared = _declared_dimensions(model, entity)
    supplied: dict[TemporalDimension, tuple[str, object | None]] = {
        TemporalDimension.VALID_TIME: ("valid-time", valid_start),
        TemporalDimension.TRANSACTION_TIME: ("transaction-time", tx_start),
    }
    coordinates: dict[TemporalDimension, dt.datetime] = {}
    for dimension, (spelling, value) in supplied.items():
        if dimension not in declared:
            if value is not None:
                raise MilestoneEdgeError(
                    f"{entity.identity.name}: an observed milestone's edge names the target's "
                    f"declared as-of axes, and this target declares no {spelling} axis to "
                    f"carry the start {value!r}"
                )
            continue
        if value is None:
            raise MilestoneEdgeError(
                f"{entity.identity.name}: an observed milestone's edge names every declared "
                f"as-of axis, and the {spelling} start is missing"
            )
        coordinates[dimension] = _coordinate(value)
    return _edge(coordinates)


def observed_close_coordinates(
    model: Metamodel, entity: EntityMetadata, observation: TemporalObservation
) -> tuple[object | None, object]:
    """The close coordinates a resolved observation supplies: the observed
    milestone's own Valid-Time end (the address's exclusive upper bound on that
    axis, ``None`` for a Transaction-Time-Only target, which has no Valid-Time
    axis to bound) and its own Transaction-Time start (the optimistic gate's
    candidate).

    Both are read off the ONE predecessor the observation names, so a close's
    address and its gate cannot come from two different milestones.
    """
    members = observation.predecessor.members
    tx_start, _tx_end = _axis_names(model, entity, TemporalDimension.TRANSACTION_TIME)
    dimensions = _declared_dimensions(model, entity)
    valid_end: object | None = None
    if TemporalDimension.VALID_TIME in dimensions:
        _valid_start, valid_end_name = _axis_names(model, entity, TemporalDimension.VALID_TIME)
        valid_end = members[valid_end_name]
    return valid_end, members[tx_start]


_NOT_AN_INSTANT = "an as-of axis start is a finite instant, and {value!r} is not one"


def _coordinate(value: object) -> dt.datetime:
    """One axis-start value as the shared comparable an edge is keyed by.

    An axis START is always a finite instant — the open-bound sentinel bounds an
    axis END alone — and it is normalized to UTC, so two spellings of one instant
    name one edge rather than two.
    """
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value)
        except ValueError as exc:
            raise MilestoneEdgeError(_NOT_AN_INSTANT.format(value=value)) from exc
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
    """``entity``'s family-effective Attribute names for one temporal dimension."""
    return txtime_write.axis_attr_names(model, entity, dimension)


def _axes(model: Metamodel, entity: EntityMetadata, *, bitemporal: bool) -> TemporalAxes:
    """The Attribute names ``entity``'s family bounds its milestone intervals with."""
    tx_start, tx_end = _axis_names(model, entity, TemporalDimension.TRANSACTION_TIME)
    if not bitemporal:
        return TemporalAxes(transaction_start=tx_start, transaction_end=tx_end)
    valid_start, valid_end = _axis_names(model, entity, TemporalDimension.VALID_TIME)
    return TemporalAxes(
        transaction_start=tx_start,
        transaction_end=tx_end,
        valid_start=valid_start,
        valid_end=valid_end,
    )


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
