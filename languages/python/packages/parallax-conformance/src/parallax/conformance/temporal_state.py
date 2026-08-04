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

from collections.abc import Mapping, Sequence

from parallax.core import bitemp_write, inheritance, temporal_read, txtime_write
from parallax.core.metamodel import EntityMetadata, Metamodel, PrimaryKey, TemporalDimension
from parallax.core.unit_work import (
    KeyedWrite,
    PredecessorRow,
    TemporalAxes,
    TemporalObservation,
    expand_milestone,
)

__all__ = ["AmbiguousObservationError", "TemporalShadow"]

_ObjectKey = tuple[str, tuple[object, ...]]


class AmbiguousObservationError(ValueError):
    """More than one current milestone is tracked for one (entity, pk) — several
    disjoint Valid-Time rectangles of one key may be current on Transaction Time
    (`m-bitemp-write.md`), and the write-sequence/scenario input handled here
    names no rectangle, so this tracker refuses rather than silently guessing
    which candidate a later step means."""


class TemporalShadow:
    """The case-local map of (entity, primary key) -> its tracked CURRENT
    (``out_z = infinity``) milestone, advanced as each temporal write plans."""

    __slots__ = ("_current",)

    def __init__(self) -> None:
        self._current: dict[_ObjectKey, list[TemporalObservation]] = {}

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
        for row in rows:
            if row.get(tx_end) != "infinity":
                continue  # not current on Transaction Time
            key = self._key(entity_name, pk_names, row)
            observation = TemporalObservation(predecessor=PredecessorRow(members=row))
            self._current.setdefault(key, []).append(observation)

    def resolve(
        self, model: Metamodel, entity: EntityMetadata, row: Mapping[str, object]
    ) -> TemporalObservation | None:
        """The tracked observation a temporal update/terminate/updateUntil/
        terminateUntil instruction's close/chain consumes, or ``None`` for a
        pk this tracker has never seen open (an insert, or a genuinely
        unobserved close the write itself will surface as a conflict/stale
        error at execution).

        Raises :class:`AmbiguousObservationError` when more than one current
        candidate is tracked for this pk — naming one rectangle explicitly is a
        conflict-shape-only mechanism, carried by the case's own
        ``write.validEnd`` / ``observedTxStart`` fields, never this tracker (see
        the module docstring).
        """
        entity_name = entity.identity.name
        pk_names = _primary_key_names(model, entity)
        key = self._key(entity_name, pk_names, row)
        candidates = self._current.get(key)
        if not candidates:
            return None
        if len(candidates) > 1:
            raise AmbiguousObservationError(
                f"{entity_name}: {len(candidates)} current milestones are tracked for "
                f"{dict(zip(pk_names, key[1], strict=True))!r} — disambiguation between "
                "them is not supported"
            )
        return candidates[0]

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
        state")."""
        entity_name = entity.identity.name
        pk_names = _primary_key_names(model, entity)
        key = self._key(entity_name, pk_names, instruction.rows[0])
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
        if not opened:
            self._current.pop(key, None)  # a terminate/terminateUntil closes with no chain
            return
        # An opened row is the whole milestone the mutation just wrote, axis
        # bounds included, so it is exactly the Predecessor Row a later step
        # observes.
        self._current[key] = [
            TemporalObservation(predecessor=PredecessorRow(members=milestone.members))
            for milestone in opened
        ]

    @staticmethod
    def _key(entity_name: str, pk_names: Sequence[str], row: Mapping[str, object]) -> _ObjectKey:
        return (entity_name, tuple(row[name] for name in pk_names))


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
