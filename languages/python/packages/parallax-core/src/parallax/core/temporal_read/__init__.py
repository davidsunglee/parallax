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

``m-temporal-read`` depends on ``m-op-algebra`` only (transitively ``m-descriptor``
/ ``m-core``); it never imports ``m-dialect`` or ``m-sql``. The open upper bound is
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
from parallax.core.descriptor import AsOfAxisMetadata, Entity, TemporalDimension
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

__all__ = [
    "AXIS_ORDER",
    "LATEST",
    "TX_TIME",
    "VALID_TIME",
    "Edge",
    "Latest",
    "Pin",
    "TemporalDimensionConstant",
    "TemporalReadError",
    "UndeclaredAxisError",
    "attr_ref_for_column",
    "conjunction_terms",
    "edge_of",
    "inject_as_of",
    "milestone_edge",
    "pin_of",
    "resolve_pinned_instants",
    "statement_pin",
]

# Valid Time is the OUTER pin (the corpus's bitemporal nesting order) and its
# injected fragment reads first; Transaction Time is inner. The injected terms
# therefore compose Valid-Time-first. Exported (m-navigate reuses the same ordering
# when propagating a
# root's as-of coordinates per hop).
AXIS_ORDER: Final[dict[TemporalDimension, int]] = {"validTime": 0, "transactionTime": 1}
_AXIS_ORDER = AXIS_ORDER


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
    alias.
    """

    __slots__ = ("_dimension",)

    _dimension: TemporalDimension

    def __init__(self, dimension: TemporalDimension) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> TemporalDimension:
        """The canonical dimension spelling this constant maps to at the wire boundary."""
        return self._dimension

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "VALID_TIME" if self._dimension == "validTime" else "TX_TIME"


VALID_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("validTime")
TX_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("transactionTime")


@dataclass(frozen=True, slots=True)
class Pin:
    """A temporal read's as-of coordinates — one entry per **genuinely pinned** axis.

    A scanned axis (``history`` / ``as_of_range``) is **absent** (``None``), per the
    core rule that a scan is not a pin. A pinned axis carries either the finite pin
    instant or the :data:`LATEST` sentinel. ``Pin`` is what
    ``snapshot.pin`` reports and what :func:`pin_of` returns for one node.
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


# The private attributes a materialized snapshot node carries (attached by the
# snapshot materializer through its setattr backdoor, COR-3 Phase 7). `pin_of` /
# `edge_of` read them; the value model and the milestone-edge computation
# (`milestone_edge`) are the reusable core the materializer builds on.
_PIN_ATTR: Final[str] = "__parallax_pin__"
_EDGE_ATTR: Final[str] = "__parallax_edge__"


def pin_of(node: object) -> Pin:
    """The as-of coordinates a materialized temporal node was read at (its :class:`Pin`).

    The pin is attached to the node at materialization (whole-graph pinning,
    ``m-snapshot-read``); a non-temporal node — or a node not produced by a
    temporal materialization — carries none and raises.
    """
    pin = getattr(node, _PIN_ATTR, None)
    if not isinstance(pin, Pin):
        raise TemporalReadError("node carries no temporal pin (not a materialized temporal node)")
    return pin


def edge_of(node: object) -> Edge:
    """The milestone :class:`Edge` of a materialized temporal node (its from-instants).

    Defined for every temporal node regardless of how the read was pinned; calling
    it on a non-temporal node (one with no attached edge) raises.
    """
    edge = getattr(node, _EDGE_ATTR, None)
    if not isinstance(edge, Edge):
        raise TemporalReadError("edge_of() requires a materialized temporal node")
    return edge


def milestone_edge(entity: Entity, row: Mapping[str, object]) -> Edge:
    """Compute a milestone's :class:`Edge` from one row's interval columns (the edge-pin rule).

    Each declared axis's edge is its milestone's own **from-instant** — the value of
    the axis's start Attribute column in ``row`` — the one instant guaranteed to re-select
    exactly that milestone on a half-open ``[from, to)`` interval. This is the
    reusable core the snapshot materializer (COR-3 Phase 7) uses to edge-pin each
    ``history`` / ``as_of_range`` result; here it is unit-verifiable against corpus
    row values without a materialized graph.
    """
    if not entity.as_of_axes:
        raise TemporalReadError(f"{entity.name} is not a temporal entity")
    coords: dict[TemporalDimension, _dt.datetime] = {}
    for axis in entity.as_of_axes:
        start_column = _column_for_attribute(entity, axis.start_attribute)
        value = row.get(start_column)
        if not isinstance(value, _dt.datetime):
            raise TemporalReadError(
                f"{entity.name}.{axis.start_attribute}: milestone start column "
                f"{start_column!r} "
                "is not a timestamp instant"
            )
        coords[axis.dimension] = normalize_instant(value)
    return Edge(
        tx_time=coords.get("transactionTime"),
        valid_time=coords.get("validTime"),
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


def inject_as_of(op: Operation, entity: Entity) -> Operation:
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


def _inject_core(core: Operation, entity: Entity) -> Operation:
    modes: dict[TemporalDimension, _AxisMode] = {}
    current: Operation = core
    while isinstance(current, (AsOf, AsOfRange, History)):
        axis = _resolve_axis(current.dimension, entity)
        if axis.dimension in modes:
            raise TemporalReadError(
                f"{entity.name}: the {axis.dimension} dimension is pinned or scanned twice"
            )
        modes[axis.dimension] = _mode_of(current)
        current = current.operand
    user_predicate = current

    axis_terms: list[Operation] = []
    for axis in sorted(entity.as_of_axes, key=lambda item: _AXIS_ORDER[item.dimension]):
        mode = modes.get(axis.dimension, _Latest())
        axis_terms.extend(_terms(mode, axis, entity))

    if not axis_terms:
        # Non-temporal read, or a read whose every declared axis is scanned
        # (bitemporal history): the user predicate stands unchanged.
        return user_predicate
    terms = (*conjunction_terms(user_predicate), *axis_terms)
    return terms[0] if len(terms) == 1 else And(operands=terms)


def _resolve_axis(dimension: TemporalDimension, entity: Entity) -> AsOfAxisMetadata:
    for axis in entity.as_of_axes:
        if axis.dimension == dimension:
            return axis
    reason = "non-temporal entity" if not entity.as_of_axes else "undeclared dimension"
    raise TemporalReadError(
        f"{entity.name} declares no temporal dimension {dimension!r} ({reason})"
    )


def _mode_of(wrapper: AsOf | AsOfRange | History) -> _AxisMode:
    if isinstance(wrapper, History):
        return _Scan()
    if isinstance(wrapper, AsOfRange):
        return _Range(from_=wrapper.start, to=wrapper.end)
    if wrapper.coordinate == "latest":
        return _Latest()
    return _Containment(instant=wrapper.coordinate)


def _terms(mode: _AxisMode, axis: AsOfAxisMetadata, entity: Entity) -> list[Operation]:
    start_ref = f"{entity.name}.{axis.start_attribute}"
    end_ref = f"{entity.name}.{axis.end_attribute}"
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


def attr_ref_for_column(entity: Entity, column: str) -> str:
    """The ``Entity.attribute`` reference of the interval column ``column``.

    A temporal entity's interval columns are ordinary declared attributes
    (``m-descriptor``: ``startAttribute`` / ``endAttribute`` reference ordinary
    Attributes), so the injected comparison references them by name exactly
    as a user predicate would, and ``m-sql`` resolves the column with no temporal
    special-casing. Exported so ``m-navigate`` can build the identically-shaped
    per-hop as-of predicate over a temporal entity reached by navigation (the same
    column-lookup rule, applied to the hop's own target entity).
    """
    for attr in entity.attributes:
        if attr.column == column:
            return f"{entity.name}.{attr.name}"
    # Defensive: a well-formed temporal descriptor always declares its interval
    # columns as attributes (the descriptor validator + `m-descriptor` authoring
    # rule guarantee it), so this is unreachable for a validated metamodel.
    raise TemporalReadError(  # pragma: no cover - guards a malformed descriptor
        f"{entity.name}: interval column {column!r} is not a declared attribute"
    )


def _column_for_attribute(entity: Entity, attribute_name: str) -> str:
    for attribute in entity.attributes:
        if attribute.name == attribute_name:
            return attribute.column
    raise TemporalReadError(  # pragma: no cover - guards a malformed descriptor
        f"{entity.name}: temporal Attribute {attribute_name!r} is not declared"
    )


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


def resolve_pinned_instants(op: Operation, entity: Entity) -> dict[TemporalDimension, str]:
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
    pins: dict[TemporalDimension, str] = {}
    current = core
    while isinstance(current, (AsOf, AsOfRange, History)):
        axis = _resolve_axis(current.dimension, entity)
        mode = _mode_of(current)
        if isinstance(mode, _Containment):
            pins[axis.dimension] = mode.instant
        current = current.operand
    return pins


def statement_pin(op: Operation, entity: Entity) -> Pin:
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
        axis = _resolve_axis(current.dimension, entity)
        if isinstance(current, AsOf):
            value: _dt.datetime | Latest = (
                LATEST
                if current.coordinate == "latest"
                else _dt.datetime.fromisoformat(current.coordinate)
            )
            if axis.dimension == "transactionTime":
                tx_time = value
            else:
                valid_time = value
        current = current.operand
    return Pin(tx_time=tx_time, valid_time=valid_time)


def _peel_directives(op: Operation) -> tuple[Operation, list[Limit | OrderBy | Distinct]]:
    """Split leading result-shaping directives off the temporal/predicate core.

    Returns the inner core and the peeled directive nodes outermost-first, so they
    can be rebuilt around the rewritten predicate.
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
