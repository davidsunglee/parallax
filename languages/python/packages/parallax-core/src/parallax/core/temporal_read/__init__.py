"""``parallax.core.temporal_read`` enforcement scope (m-temporal-read).

The as-of read model: temporal entities whose rows are **milestones** over
``[from, to)`` intervals, with the as-of predicate **auto-injected** on read.
This scope owns the *interval model, the explicit-selection injection rule, and the
milestone (edge-pin) behaviour* (``m-object-query`` / ``m-temporal-read``);
``m-sql`` owns the concrete SQL fragments and bind order. Because the normative
module DAG forbids ``m-sql`` from importing ``m-temporal-read``, the temporal →
predicate lowering is expressed **here**, as a rewrite of an Object Query's
Temporal Selection clause into ordinary ``m-predicate`` predicate nodes, which
``m-sql`` then lowers with no temporal knowledge. The ``m-deep-fetch`` planning
boundary passes the query's predicate and Temporal Selections to
:func:`inject_as_of`, then places the result in the flat ``EntityQuery``
consumed by ``compile_read``.

Every entry point here takes accepted Entity Metadata, and each resolves an
axis through the same declared lookup, so the wire dimension spelling an
operation node carries meets the model's own Temporal Dimension in exactly one
place.

This scope also owns the Temporal Facet: the immutable per-formation view that
answers each Entity's effective temporal shape from its family root's declared
As-Of Axes. It contributes that Model Compiler and no Rule Set, because every
axis defect belongs to ``m-metamodel`` or ``m-inheritance``. Consumers reach the
facet through :func:`view`, so generic facet retrieval stays an internal
formation seam.

``m-temporal-read`` depends on ``m-object-query``, ``m-predicate``,
``m-metamodel``, ``m-model-formation``, and ``m-inheritance``; it never imports
``m-dialect`` or ``m-sql``. The Temporal Selection VALUE belongs to the query it
is a clause of, so this scope consumes it rather than defining it. The open upper bound is
carried as the ``m-core`` canonical ``infinity`` literal — a plain bind — so the
dialect's physical infinity representation stays owned by the adapter, exactly as
every other literal (``m-sql``: the current-row bind is the ``infinity`` literal).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from parallax.core.base import INFINITY_LITERAL, normalize_instant
from parallax.core.metamodel import AsOfAxisMetadata as AcceptedAsOfAxis
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.metamodel import TemporalDimension as AcceptedDimension
from parallax.core.object_query import (
    LATEST,
    AsOf,
    AsOfRange,
    History,
    Latest,
    ObjectQueryNode,
    TemporalSelection,
)
from parallax.core.object_query import TemporalDimension as WireDimension
from parallax.core.predicate import All, And, Comparison, Group, Or, PredicateNode
from parallax.core.temporal_read._compile import (
    MODEL_COMPILER,
    TemporalReadModelCompiler,
    compile_facet,
)
from parallax.core.temporal_read._facet import (
    FACET_KEY,
    NON_TEMPORAL,
    TEMPORAL_READ_MODULE,
    Bitemporal,
    NonTemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
    view,
)

__all__ = [
    "FACET_KEY",
    "MODEL_COMPILER",
    "NON_TEMPORAL",
    "TEMPORAL_READ_MODULE",
    "Bitemporal",
    "Edge",
    "NonTemporal",
    "Pin",
    "TemporalFacet",
    "TemporalReadError",
    "TemporalReadModelCompiler",
    "TemporalShape",
    "TransactionTimeOnly",
    "UndeclaredAxisError",
    "compile_facet",
    "conjunction_terms",
    "inject_as_of",
    "milestone_edge",
    "milestone_edge_from_members",
    "milestone_edge_of",
    "query_pin",
    "resolve_pinned_instants",
    "scans_an_axis",
    "view",
]

# The wire dimension spelling a Temporal Selection is keyed by, mapped to the
# accepted model's own Temporal Dimension. The two vocabularies meet only here.
# Valid Time's injected fragment reads first; that rank is the Dimension's own
# member value, so ordering axes needs no table of its own.
_DIMENSIONS: Final[Mapping[str, AcceptedDimension]] = {
    "valid-time": AcceptedDimension.VALID_TIME,
    "transaction-time": AcceptedDimension.TRANSACTION_TIME,
}


class TemporalReadError(ValueError):
    """A temporal read is malformed (undeclared axis, non-temporal target, double pin)."""


class UndeclaredAxisError(TemporalReadError):
    """A strict :class:`Edge` / :class:`Pin` axis accessor named an axis the entity
    does not declare (the arity-accessor house pattern; use the ``*_or_none`` form)."""


@dataclass(frozen=True, slots=True)
class Pin:
    """A temporal read's as-of coordinates — one entry per **genuinely pinned** axis.

    A scanned axis (``history`` / ``as_of_range``) is **absent** (``None``), per the
    core rule that a scan is not a pin. A pinned axis carries either the finite pin
    instant or the :data:`LATEST` sentinel. ``Pin`` is what ``snapshot.pin``
    reports and what ``parallax.snapshot.pin_of`` answers for one node.
    """

    tx_time: _dt.datetime | Latest | None = None
    valid_time: _dt.datetime | Latest | None = None

    @property
    def is_empty(self) -> bool:
        """Whether no axis is pinned (both axes scanned, or a non-temporal read)."""
        return self.tx_time is None and self.valid_time is None


class Edge:
    """A temporal milestone's **edge** — the finite from-instant on every declared axis.

    Unlike a :class:`Pin`, an ``Edge`` answers *every declared axis* and is always
    finite (never :data:`LATEST`, never absent-because-scanned): a milestone's
    from-instant lies inside its own ``[from, to)`` interval on each axis, so it is
    the one coordinate guaranteed to re-select exactly that milestone (core's edge
    pin; Reladomo's ``equalsEdgePoint``). The strict accessor raises
    :class:`UndeclaredAxisError` for an axis the entity does not declare; the
    ``*_or_none`` accessor returns ``None`` instead — the arity-accessor house
    pattern applied to axis access, keeping replay code narrowing-free.
    """

    __slots__ = ("_tx_time", "_valid_time")

    _tx_time: _dt.datetime | None
    _valid_time: _dt.datetime | None

    def __init__(
        self,
        *,
        tx_time: _dt.datetime | None = None,
        valid_time: _dt.datetime | None = None,
    ) -> None:
        # Frozen by hand (the raise-on-undeclared accessor properties preclude a
        # frozen dataclass): construction writes through `object.__setattr__`,
        # and the overrides below refuse every later mutation — a hashable Edge
        # can never change under a dictionary or set.
        object.__setattr__(self, "_tx_time", tx_time)
        object.__setattr__(self, "_valid_time", valid_time)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Edge is frozen; cannot assign {name!r}")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"Edge is frozen; cannot delete {name!r}")

    @property
    def tx_time(self) -> _dt.datetime:
        """The Transaction-Time start instant; raises when undeclared."""
        if self._tx_time is None:
            raise UndeclaredAxisError("entity declares no `tx_time` dimension")
        return self._tx_time

    @property
    def tx_time_or_none(self) -> _dt.datetime | None:
        """The Transaction-Time start instant, or ``None`` when undeclared."""
        return self._tx_time

    @property
    def valid_time(self) -> _dt.datetime:
        """The Valid-Time start instant; raises when undeclared."""
        if self._valid_time is None:
            raise UndeclaredAxisError("entity declares no `valid_time` dimension")
        return self._valid_time

    @property
    def valid_time_or_none(self) -> _dt.datetime | None:
        """The Valid-Time start instant, or ``None`` when undeclared."""
        return self._valid_time

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Edge):
            return NotImplemented
        return self._tx_time == other._tx_time and self._valid_time == other._valid_time

    def __hash__(self) -> int:
        return hash((self._tx_time, self._valid_time))

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"Edge(tx_time={self._tx_time!r}, valid_time={self._valid_time!r})"


# `Pin` and `Edge` are lifecycle-neutral values, so reading either OFF a
# materialized node belongs to the lifecycle that produced it
# (`parallax.snapshot.pin_of` / `edge_of`). What stays here is the value model
# and the milestone-edge computation every materializer builds on.


def milestone_edge(entity: EntityMetadata, row: Mapping[str, object]) -> Edge:
    """Compute a milestone's :class:`Edge` from one row's interval columns (the edge-pin rule).

    Each declared axis's edge is its milestone's own **from-instant** — the value of
    the axis's start Attribute column in ``row`` — the one instant guaranteed to re-select
    exactly that milestone on a half-open ``[from, to)`` interval. This is the
    reusable core a read uses to edge-pin each ``history`` / ``as_of_range``
    result; here it is unit-verifiable against corpus row values without a
    materialized graph.

    ``entity`` is the Entity whose declaration carries the family's axes, which
    the caller resolves; a position that inherits them declares none of its own.
    """
    return _edge(
        entity,
        {
            axis.start_attribute: row.get(_column_for_attribute(entity, axis.start_attribute))
            for axis in entity.declared_as_of_axes
        },
    )


def milestone_edge_of(entity: EntityMetadata, values: Mapping[AttributeIdentity, object]) -> Edge:
    """The same edge-pin rule, read off values keyed by **member identity**.

    The form a materialized node answers in: once a row has been converted, its
    interval values are held by Attribute Identity and the physical column that
    carried them is gone. Inverting one back would re-derive a mapping the model
    already fixes, in a layer that otherwise never needs to know one.
    """
    return _edge(entity, values)


def milestone_edge_from_members(entity: EntityMetadata, members: Mapping[str, object]) -> Edge:
    """The same edge-pin rule, read off values keyed by **declared member name**.

    The form a retained row payload answers in — a Write Observation's
    Predecessor Row holds the observed milestone's complete state by declared
    name, with neither the physical column nor the Attribute Identity that
    carried it. Deriving the edge from that payload rather than beside it is
    what keeps a recorder structurally unable to file an observation under a
    milestone other than the one it is recording.
    """
    return _edge(
        entity,
        {
            axis.start_attribute: members.get(axis.start_attribute.name)
            for axis in entity.declared_as_of_axes
        },
    )


def _edge(entity: EntityMetadata, values: Mapping[AttributeIdentity, object]) -> Edge:
    name = entity.identity.name
    if not entity.declared_as_of_axes:
        raise TemporalReadError(f"{name} is not a temporal entity")
    coords: dict[AcceptedDimension, _dt.datetime] = {}
    for axis in entity.declared_as_of_axes:
        value = values.get(axis.start_attribute)
        if not isinstance(value, _dt.datetime):
            raise TemporalReadError(
                f"{name}.{axis.start_attribute.name}: the milestone start value "
                "is not a timestamp instant"
            )
        coords[axis.dimension] = normalize_instant(value)
    return Edge(
        tx_time=coords.get(AcceptedDimension.TRANSACTION_TIME),
        valid_time=coords.get(AcceptedDimension.VALID_TIME),
    )


# --------------------------------------------------------------------------- #
# As-of injection (Temporal Selections -> plain m-predicate terms).          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _Latest:
    """Pin a dimension to its latest milestone (``end = infinity``)."""


@dataclass(frozen=True, slots=True)
class _Containment:
    """Pin an axis to a past instant (``from <= d and to >(=) d``)."""

    instant: str


@dataclass(frozen=True, slots=True)
class _Range:
    """Scan an axis across a half-open window (``from < to and to > from``)."""

    from_: str
    to: str


@dataclass(frozen=True, slots=True)
class _Scan:
    """Scan an axis as edge points (``history``) — no as-of term injected."""


_AxisMode = _Latest | _Containment | _Range | _Scan


def inject_as_of(
    predicate: PredicateNode,
    selections: Mapping[WireDimension, TemporalSelection],
    entity: EntityMetadata,
) -> PredicateNode:
    """Inject an Object Query's explicit Temporal Selections into its predicate.

    ``selections`` is the query's own dimension-keyed clause, so "at most one
    selection per dimension" is settled by the mapping rather than re-checked
    here. This module owns only temporal semantics: it derives the interval terms
    in Valid-Time-first order and appends them after the user predicate so bind
    order remains user-first.

    ``history`` injects no term for its dimension. A non-temporal read with no
    selections is a strict identity; a selection naming a dimension the entity
    does not declare is rejected by the same declared-axis rule as before.
    """
    modes: dict[AcceptedDimension, _AxisMode] = {}
    for dimension, selection in selections.items():
        axis = _declared_axis(dimension, entity)
        modes[axis.dimension] = _mode_of(selection)

    axis_terms: list[PredicateNode] = []
    for axis in sorted(entity.declared_as_of_axes, key=lambda item: item.dimension.value):
        mode = modes.get(axis.dimension)
        if mode is None:
            raise TemporalReadError(
                f"{entity.identity.name}: internal temporal lowering received no selection "
                f"for declared dimension {axis.dimension.value!r}"
            )
        axis_terms.extend(_terms(mode, axis, entity))

    if not axis_terms:
        return predicate
    terms = (*conjunction_terms(predicate), *axis_terms)
    return terms[0] if len(terms) == 1 else And(operands=terms)


def _declared_axis(dimension: str, entity: EntityMetadata) -> AcceptedAsOfAxis:
    """The As-Of Axis ``entity`` declares for the wire dimension ``dimension``.

    ``entity`` is the Entity whose declaration actually carries the family's
    axes, which the caller resolves; a read against a position that inherits
    them therefore never reaches this with an empty declaration of its own.
    """
    axis = entity.as_of_axis(_DIMENSIONS[dimension])
    if axis is not None:
        return axis
    reason = "non-temporal entity" if not entity.declared_as_of_axes else "undeclared dimension"
    raise TemporalReadError(
        f"{entity.identity.name} declares no temporal dimension {dimension!r} ({reason})"
    )


def _mode_of(selection: TemporalSelection) -> _AxisMode:
    if isinstance(selection, History):
        return _Scan()
    if isinstance(selection, AsOfRange):
        return _Range(from_=selection.start, to=selection.end)
    if selection.coordinate == "latest":
        return _Latest()
    return _Containment(instant=selection.coordinate)


def _terms(mode: _AxisMode, axis: AcceptedAsOfAxis, entity: EntityMetadata) -> list[PredicateNode]:
    start_ref = f"{entity.identity.canonical}.{axis.start_attribute.name}"
    end_ref = f"{entity.identity.canonical}.{axis.end_attribute.name}"
    if isinstance(mode, _Scan):
        return []
    if isinstance(mode, _Latest):
        return [Comparison(op="eq", attr=end_ref, value=INFINITY_LITERAL)]
    if isinstance(mode, _Containment):
        return [
            Comparison(op="lessThanEquals", attr=start_ref, value=mode.instant),
            Comparison(op="greaterThan", attr=end_ref, value=mode.instant),
        ]
    # _Range — overlap of the milestone with the window [from, to): the milestone's
    # start compares to the window END and its end to the window START, so the binds
    # read window-end-first (m-sql: `from < ? and to > ?` binds `[to, from]`).
    return [
        Comparison(op="lessThan", attr=start_ref, value=mode.to),
        Comparison(op="greaterThan", attr=end_ref, value=mode.from_),
    ]


def _column_for_attribute(entity: EntityMetadata, attribute: AttributeIdentity) -> str:
    """The physical column an axis endpoint Attribute is stored in.

    An As-Of Axis names ordinary declared Attributes, so the interval bounds
    resolve through the Entity's own local member lookup with no temporal
    special-casing.
    """
    declared = entity.attribute(attribute.name)
    if declared is None:  # pragma: no cover - an accepted axis names a declared Attribute
        raise TemporalReadError(
            f"{entity.identity.name}: temporal Attribute {attribute.name!r} is not declared"
        )
    return declared.storage.name


def conjunction_terms(op: PredicateNode) -> tuple[PredicateNode, ...]:
    """The top-level conjuncts of a user predicate (mirrors the statement builder).

    ``all`` contributes nothing; an ``and`` flattens (order-preserving); an ``or``
    binds looser than the enclosing ``and`` and is wrapped in a ``group`` so the
    injected as-of term does not silently re-associate into it; every other node is
    a single conjunct. Exported so ``m-navigate`` composes a hop's own per-axis as-of
    terms onto its interior predicate with the identical flattening rule.
    """
    if isinstance(op, All):
        return ()
    if isinstance(op, And):
        return op.operands
    if isinstance(op, Or):
        return (Group(operand=op),)
    return (op,)


def resolve_pinned_instants(
    selections: Mapping[WireDimension, TemporalSelection], entity: EntityMetadata
) -> dict[AcceptedDimension, str]:
    """The per-axis literal instant this read pins ``entity`` to a specific PAST
    moment (an ``asOf`` Temporal Selection) — the coordinate ``m-navigate``
    re-applies, matched by axis, to a temporal entity reached by navigation.

    Every other axis — undeclared by ``entity``, pinned to Latest, or
    scanned via ``history`` / ``asOfRange`` — independently resolves to **latest**
    at its own hop target (`m-navigate` "As-of propagation across relationships"),
    so this map omits them; the caller defaults an absent axis to latest by
    construction rather than re-deriving it here.

    Called on the same Temporal Selection clause :func:`inject_as_of` consumes.
    """
    pins: dict[AcceptedDimension, str] = {}
    for dimension, selection in selections.items():
        axis = _declared_axis(dimension, entity)
        mode = _mode_of(selection)
        if isinstance(mode, _Containment):
            pins[axis.dimension] = mode.instant
    return pins


def query_pin(query: ObjectQueryNode, entity: EntityMetadata) -> Pin:
    """The as-of coordinates ``query``'s Temporal Selections pin.

    A SCANNED dimension (``history`` / ``asOfRange`` — "a scan is not a pin") is
    absent; a PINNED dimension carries its coordinate, including the explicit
    :data:`LATEST` sentinel. Authoring-defaulted Transaction Time has already
    normalized to that explicit selection. The whole-graph pin ``Database.find``
    / ``Transaction.find`` attach to the returned ``Snapshot``.

    A side-effect-free read of the query's own clause, never a database round
    trip.
    """
    tx_time: _dt.datetime | Latest | None = None
    valid_time: _dt.datetime | Latest | None = None
    for dimension, selection in query.temporal.items():
        if not isinstance(selection, AsOf):
            continue
        axis = _declared_axis(dimension, entity)
        value: _dt.datetime | Latest = (
            LATEST
            if selection.coordinate == "latest"
            else _dt.datetime.fromisoformat(selection.coordinate)
        )
        if axis.dimension is AcceptedDimension.TRANSACTION_TIME:
            tx_time = value
        else:
            valid_time = value
    return Pin(tx_time=tx_time, valid_time=valid_time)


def scans_an_axis(query: ObjectQueryNode) -> bool:
    """Whether ``query`` SCANS ANY temporal dimension (``asOfRange`` / ``history``)
    rather than pinning every dimension it names — the milestone-set read shape,
    and the negative half of :func:`query_pin`'s "a scan is not a pin" rule.

    Each dimension carries its own selection, so the WHOLE clause decides: one
    scanned dimension answers a milestone set however the other is pinned.
    Includes are deliberately NOT consulted: this scope takes no
    ``m-deep-fetch`` edge, so a caller composing the two holds the graph-shaping
    question itself.
    """
    return any(isinstance(selection, (AsOfRange, History)) for selection in query.temporal.values())
