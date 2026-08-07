"""``parallax.core.temporal_read`` enforcement scope (m-temporal-read).

The as-of read model: temporal entities whose rows are **milestones** over
``[from, to)`` intervals, with the as-of predicate **auto-injected** on read.
This scope owns the *interval model, the default-injection rule, and the
milestone (edge-pin) behaviour* (``m-op-algebra`` / ``m-temporal-read``);
``m-sql`` owns the concrete SQL fragments and bind order. Because the normative
module DAG forbids ``m-sql`` from importing ``m-temporal-read`` (they are siblings
over ``m-op-algebra``), the temporal → predicate lowering is expressed **here**,
as a rewrite of the temporal wrapper nodes into ordinary ``m-op-algebra``
predicate nodes, which ``m-sql`` then lowers with no temporal knowledge. A caller
that can legally compose both scopes (the conformance engine; later the snapshot
handle and the statement compile path) applies :func:`inject_as_of` before
``compile_read``.

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

``m-temporal-read`` depends on ``m-op-algebra``, ``m-metamodel``,
``m-model-formation``, and ``m-inheritance``; it never imports ``m-dialect`` or
``m-sql``. The open upper bound is
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
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    AsOfRange,
    Comparison,
    Distinct,
    Group,
    History,
    Limit,
    Operation,
    Or,
    OrderBy,
)
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
    "LATEST",
    "MODEL_COMPILER",
    "NON_TEMPORAL",
    "TEMPORAL_READ_MODULE",
    "TX_TIME",
    "VALID_TIME",
    "Bitemporal",
    "Edge",
    "Latest",
    "NonTemporal",
    "Pin",
    "TemporalDimensionConstant",
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
    "resolve_pinned_instants",
    "scans_an_axis",
    "statement_pin",
    "view",
]

# The wire dimension spelling an operation node carries, mapped to the accepted
# model's own Temporal Dimension. The two vocabularies meet only here. Valid Time
# is the OUTER pin (the corpus's bitemporal nesting order) and its injected
# fragment reads first; that rank is the Dimension's own member value, so
# ordering axes needs no table of its own.
_DIMENSIONS: Final[Mapping[str, AcceptedDimension]] = {
    "valid-time": AcceptedDimension.VALID_TIME,
    "transaction-time": AcceptedDimension.TRANSACTION_TIME,
}


class TemporalReadError(ValueError):
    """A temporal read is malformed (undeclared axis, non-temporal target, double pin)."""


class UndeclaredAxisError(TemporalReadError):
    """A strict :class:`Edge` / :class:`Pin` axis accessor named an axis the entity
    does not declare (the arity-accessor house pattern; use the ``*_or_none`` form)."""


class Latest:
    """The explicit Latest pin sentinel — spells the default injection.

    ``LATEST`` on an axis lowers to the **identical** current-row predicate the
    default-injection rule produces for an omitted axis (``to = infinity``), but is
    an *explicit* pin: it serializes its wrapper (``coordinate: latest``) rather than being
    absent. It is deliberately not a coordinate — it re-resolves to whatever
    milestone is current at read time, so it is never replayable (python.md, the
    stale-web-edit recipe).
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "LATEST"


LATEST: Final[Latest] = Latest()


class TemporalDimensionConstant:
    """One exported Temporal Dimension constant — :data:`VALID_TIME` / :data:`TX_TIME`.

    The developer-surface spelling of a Temporal Dimension value wherever the
    statement surface takes a dimension argument (``.history(TX_TIME)``),
    following the :data:`LATEST` sentinel pattern: one ``Final`` module-level
    singleton per dimension of the closed two-member algebra, giving completion
    and static checking where a string offers neither. A string dimension
    spelling is rejected at statement build — a dual-accept surface would be an
    alias. Instances are immutable: the statement surface accepts the constants
    by identity, so a mutable dimension could silently flip what an accepted
    constant lowers to.
    """

    __slots__ = ("_dimension",)

    _dimension: str

    def __init__(self, dimension: str) -> None:
        # Frozen by hand, matching `Edge`: construction writes through
        # `object.__setattr__`, and the overrides below refuse every later
        # assignment or deletion.
        object.__setattr__(self, "_dimension", dimension)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"TemporalDimensionConstant is frozen; cannot assign {name!r}")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"TemporalDimensionConstant is frozen; cannot delete {name!r}")

    @property
    def dimension(self) -> str:
        """The canonical dimension spelling this constant maps to at the wire boundary."""
        return self._dimension

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "VALID_TIME" if self._dimension == "valid-time" else "TX_TIME"


VALID_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("valid-time")
"""The Valid Time dimension constant: the sole developer-surface spelling of the
``valid-time`` dimension wherever a statement takes a dimension argument
(``.history(VALID_TIME)``). A frozen module-level singleton — the statement
surface accepts exactly this instance, by identity, never an equal copy or a
string."""

TX_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("transaction-time")
"""The Transaction Time dimension constant: the sole developer-surface spelling
of the ``transaction-time`` dimension wherever a statement takes a dimension
argument (``.history(TX_TIME)``). A frozen module-level singleton — the
statement surface accepts exactly this instance, by identity, never an equal
copy or a string."""


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
# As-of injection (temporal wrappers -> plain m-op-algebra predicate).         #
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


def inject_as_of(op: Operation, entity: EntityMetadata) -> Operation:
    """Rewrite the temporal wrapper nodes of ``op`` into plain ``m-op-algebra`` predicates.

    The single lowering entry point for a temporal read. For a **non-temporal**
    entity it is a strict identity (no as-of dimension to default). For a temporal
    entity it:

    - peels any result-shaping directives (``orderBy`` / ``limit`` / ``distinct``)
      off the top, so they survive around the rewritten predicate;
    - peels the temporal wrappers (``asOf`` / ``asOfRange`` / ``history``), reading
      each axis's pin and rejecting a double-pinned or undeclared axis;
    - **defaults every omitted axis to the current milestone** (the default-latest
      rule), in **Valid-Time-first** order;
    - composes the user predicate ``and`` the per-axis interval terms into one flat
      conjunction (user binds first, then the as-of binds).

    ``history`` injects **no** term for its axis; a read whose every axis is scanned
    (bitemporal ``history``) therefore keeps the user predicate unchanged.
    """
    core, directives = _peel_directives(op)
    injected = _inject_core(core, entity)
    return _rewrap_directives(injected, directives)


def _inject_core(core: Operation, entity: EntityMetadata) -> Operation:
    modes: dict[AcceptedDimension, _AxisMode] = {}
    current: Operation = core
    while isinstance(current, (AsOf, AsOfRange, History)):
        axis = _declared_axis(current.dimension, entity)
        if axis.dimension in modes:
            raise TemporalReadError(
                f"{entity.identity.name}: the {current.dimension} dimension is pinned "
                "or scanned twice"
            )
        modes[axis.dimension] = _mode_of(current)
        current = current.operand
    user_predicate = current

    axis_terms: list[Operation] = []
    # A Temporal Dimension's member value IS its canonical axis rank, so
    # Valid-Time-first needs no separate ordering table.
    for axis in sorted(entity.declared_as_of_axes, key=lambda item: item.dimension.value):
        mode = modes.get(axis.dimension, _Latest())
        axis_terms.extend(_terms(mode, axis, entity))

    if not axis_terms:
        # Non-temporal read, or a read whose every declared axis is scanned
        # (bitemporal history): the user predicate stands unchanged.
        return user_predicate
    terms = (*conjunction_terms(user_predicate), *axis_terms)
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


def _mode_of(wrapper: AsOf | AsOfRange | History) -> _AxisMode:
    if isinstance(wrapper, History):
        return _Scan()
    if isinstance(wrapper, AsOfRange):
        return _Range(from_=wrapper.start, to=wrapper.end)
    if wrapper.coordinate == "latest":
        return _Latest()
    return _Containment(instant=wrapper.coordinate)


def _terms(mode: _AxisMode, axis: AcceptedAsOfAxis, entity: EntityMetadata) -> list[Operation]:
    start_ref = f"{entity.identity.name}.{axis.start_attribute.name}"
    end_ref = f"{entity.identity.name}.{axis.end_attribute.name}"
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


def conjunction_terms(op: Operation) -> tuple[Operation, ...]:
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


def resolve_pinned_instants(op: Operation, entity: EntityMetadata) -> dict[AcceptedDimension, str]:
    """The per-axis literal instant this read pins ``entity`` to a specific PAST
    moment (an ``asOf(..., date=<instant>)`` wrapper) — the coordinate ``m-navigate``
    re-applies, matched by axis, to a temporal entity reached by navigation.

    Every other axis — undeclared by ``entity``, pinned/defaulted to ``now``, or
    scanned via ``history`` / ``asOfRange`` — independently resolves to **latest**
    at its own hop target (`m-navigate` "As-of propagation across relationships"),
    so this map omits them; the caller defaults an absent axis to latest by
    construction rather than re-deriving it here.

    Called on the SAME raw (pre-:func:`inject_as_of`) operation ``inject_as_of``
    itself consumes — an independent, side-effect-free read of the same input, not
    incremental parsing of the root-injected result (the module DAG forbids
    ``m-sql`` from ever seeing a temporal wrapper, so nothing downstream re-derives
    this from already-lowered predicate nodes).
    """
    core, _directives = _peel_directives(op)
    pins: dict[AcceptedDimension, str] = {}
    current = core
    while isinstance(current, (AsOf, AsOfRange, History)):
        axis = _declared_axis(current.dimension, entity)
        mode = _mode_of(current)
        if isinstance(mode, _Containment):
            pins[axis.dimension] = mode.instant
        current = current.operand
    return pins


def statement_pin(op: Operation, entity: EntityMetadata) -> Pin:
    """The as-of coordinates a statement's OWN temporal wrapper explicitly
    pins (spec §3 ``snapshot.pin``): an OMITTED axis (no wrapper at all — its
    latest default is injected only at lowering) or a SCANNED axis (``history``
    / ``as_of_range`` — "a scan is not a pin") is absent; a PINNED axis carries
    its coordinate, including the explicit :data:`LATEST` sentinel
    (``coordinate: latest``). The whole-graph pin ``Database.find`` / ``Transaction.find``
    (``parallax.snapshot.handle``) attach to the returned ``Snapshot``.

    Called on the SAME raw (pre-:func:`inject_as_of`) operation
    :func:`resolve_pinned_instants` consumes — an independent, side-effect-free
    read of the statement's own temporal wrapper, never a database round trip.
    """
    core, _directives = _peel_directives(op)
    tx_time: _dt.datetime | Latest | None = None
    valid_time: _dt.datetime | Latest | None = None
    current = core
    while isinstance(current, (AsOf, AsOfRange, History)):
        axis = _declared_axis(current.dimension, entity)
        if isinstance(current, AsOf):
            value: _dt.datetime | Latest = (
                LATEST
                if current.coordinate == "latest"
                else _dt.datetime.fromisoformat(current.coordinate)
            )
            if axis.dimension is AcceptedDimension.TRANSACTION_TIME:
                tx_time = value
            else:
                valid_time = value
        current = current.operand
    return Pin(tx_time=tx_time, valid_time=valid_time)


def scans_an_axis(op: Operation) -> bool:
    """Whether ``op`` SCANS ANY temporal axis (``asOfRange`` / ``history``)
    rather than pinning every axis it names — the milestone-set read shape, and
    the negative half of :func:`statement_pin`'s "a scan is not a pin" rule.

    A read pins or unpins each dimension with its own wrapper, so a bitemporal
    read nests one wrapper per dimension and the WHOLE nest decides: one scanned
    dimension answers a milestone set however the other dimension is pinned, and
    ``asOf(valid-time, history(transaction-time, …))`` therefore scans.

    Directives are peeled first, so a scan stays a scan under any result-shaping
    wrapper. An outer ``deepFetch`` is deliberately NOT peeled: this scope takes
    no ``m-deep-fetch`` edge, so a caller composing the two holds the
    graph-shaping question itself.
    """
    current, _directives = _peel_directives(op)
    while isinstance(current, (AsOf, AsOfRange, History)):
        if isinstance(current, (AsOfRange, History)):
            return True
        current = current.operand
    return False


def _peel_directives(op: Operation) -> tuple[Operation, list[Limit | OrderBy | Distinct]]:
    """Split leading result-shaping directives off the temporal/predicate core.

    Returns the inner core and the peeled directive nodes outermost-first, so they
    can be rebuilt around the rewritten predicate.

    The peeled set is ``m-op-algebra``'s closed set of row-preserving result
    directives — ``limit`` / ``orderBy`` / ``distinct`` — read off the algebra
    rather than off whichever clauses an authoring surface offers. ``distinct``
    is peeled for that reason alone: every canonical operation reaches this
    walk, including one deserialized rather than authored, so a member left
    unpeeled would make the walk answer a legal operation wrongly.
    """
    directives: list[Limit | OrderBy | Distinct] = []
    current = op
    while isinstance(current, (Limit, OrderBy, Distinct)):
        directives.append(current)
        current = current.operand
    return current, directives


def _rewrap_directives(op: Operation, directives: list[Limit | OrderBy | Distinct]) -> Operation:
    result = op
    for node in reversed(directives):
        if isinstance(node, Limit):
            result = Limit(operand=result, count=node.count)
        elif isinstance(node, OrderBy):
            result = OrderBy(operand=result, keys=node.keys)
        else:
            result = Distinct(operand=result)
    return result
