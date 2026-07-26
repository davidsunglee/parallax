"""The free-standing statement surface (support scope, statement half).

``Entity.where(*predicates)`` builds a side-effect-free :class:`Statement` — the
big-AND of its filter criteria (zero arguments is find-all). ``.order_by`` /
``.limit`` / ``.distinct`` layer the result-shaping directives, and ``.as_of`` /
``.as_of_range`` / ``.history`` layer the axis-keyed temporal-read wrappers
(``m-temporal-read``). ``operation()`` lowers a statement to a canonical
``m-op-algebra`` node and ``serialize()`` to the canonical document, so the API
Conformance Suite can prove an idiomatic statement serializes to the same
operation the corpus authors (the operation no-drift guard).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from typing import Literal

from parallax.core.base import normalize_instant
from parallax.core.entity._binding import MetamodelBinding
from parallax.core.entity._declaration import declaration_of
from parallax.core.entity._expressions import Predicate, RelationshipPath, and_terms
from parallax.core.metamodel import AsOfAxisMetadata, TemporalDimension, entity_by_name
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    AsOfRange,
    DeepFetch,
    Distinct,
    History,
    Limit,
    Narrow,
    Operation,
    OrderBy,
    OrderKey,
    PathSegment,
    serialize,
    validate_operation,
)
from parallax.core.op_algebra.nodes import TemporalDimension as WireDimension
from parallax.core.temporal_read import TX_TIME, VALID_TIME, Latest, TemporalDimensionConstant

__all__ = ["Statement", "UnsupportedFeatureError"]


class UnsupportedFeatureError(ValueError):
    """A deferred (not invalid) statement combination (spec §3): naming the
    deferral, distinct from a validation error."""


class _Unset:
    """Sentinel for an axis a temporal clause did not pass (distinct from ``LATEST``)."""

    __slots__ = ()


_UNSET = _Unset()

# One axis pin: a finite instant (a tz-aware ``datetime``) or the explicit
# Latest sentinel; a range pin is a ``(start, end)`` instant pair.
_Pin = dt.datetime | Latest
_Window = tuple[dt.datetime, dt.datetime]
_DimensionName = Literal["valid_time", "tx_time"]


@dataclass(frozen=True, slots=True)
class Statement:
    """A free-standing, side-effect-free query statement over one target entity."""

    target: str
    predicate: Operation
    order_keys: tuple[OrderKey, ...] = ()
    limit_count: int | None = None
    is_distinct: bool = False
    # The target's declared temporal dimensions, captured at ``Entity.where`` so the
    # dimension-keyed temporal clauses validate against the Entity's declared axes;
    # empty for a non-temporal entity (a temporal clause raises).
    as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    # The temporal-wrapped predicate (``asOf`` / ``asOfRange`` / ``history`` around the
    # conjoined predicate), or ``None`` when the read pins no axis. Single-shot.
    temporal: Operation | None = None
    # Deep-fetch include paths (``m-deep-fetch``), each a hop sequence built by
    # chained ``Rel[T]`` class access (``Order.items.statuses``); accumulates
    # across calls (unlike ``as_of`` / ``narrow``, ``.include`` is not single-shot).
    include_paths: tuple[tuple[PathSegment, ...], ...] = ()
    # Whether the statement-level ``.narrow(...)`` clause already wrapped the
    # predicate (single-shot, like ``as_of``).
    is_narrowed: bool = False
    # The Metamodel Binding of the target's own hub, captured at ``Entity.where``:
    # the model every predicate is validated against, so a rule stated over the
    # model fires as the statement is built rather than at execution. Absent only
    # for a Statement built directly, which validates nothing.
    binding: MetamodelBinding | None = field(default=None, repr=False, compare=False)

    def order_by(self, *keys: OrderKey) -> Statement:
        """Order the result by one or more keys (``Attr.asc()`` / ``Attr.desc()``)."""
        if not keys:
            raise ValueError("order_by requires at least one key")
        return replace(self, order_keys=self.order_keys + tuple(keys))

    def limit(self, count: int) -> Statement:
        """Cap the result row count (a positive integer)."""
        if count < 1:
            raise ValueError("limit requires a positive count")
        return replace(self, limit_count=count)

    def distinct(self) -> Statement:
        """Deduplicate the result rows."""
        return replace(self, is_distinct=True)

    def as_of(
        self,
        *,
        valid_time: _Pin | _Unset = _UNSET,
        tx_time: _Pin | _Unset = _UNSET,
    ) -> Statement:
        """Pin one or both temporal axes to an instant (or the ``LATEST`` sentinel).

        Axis-keyed and single-shot (``m-temporal-read``): an omitted axis serializes
        **no** wrapper (its Latest default is injected at lowering), while an explicit
        :data:`LATEST` pin serializes its wrapper with ``coordinate: latest``. When both
        dimensions are passed the **Valid-Time** wrapper encloses the
        **Transaction-Time** wrapper (the
        corpus's bitemporal nesting order). A naive ``datetime`` is rejected here.
        """
        op = self.predicate
        if not isinstance(tx_time, _Unset):
            op = AsOf(
                operand=op,
                dimension=self._dimension("tx_time"),
                coordinate=_instant(tx_time),
            )
        if not isinstance(valid_time, _Unset):
            op = AsOf(
                operand=op,
                dimension=self._dimension("valid_time"),
                coordinate=_instant(valid_time),
            )
        return self._with_temporal(op)

    def as_of_range(
        self,
        *,
        valid_time: _Window | _Unset = _UNSET,
        tx_time: _Window | _Unset = _UNSET,
    ) -> Statement:
        """Scan one or both axes across a half-open ``[from, to)`` window (edge points)."""
        if self.include_paths:
            raise UnsupportedFeatureError(
                "`.as_of_range()` combined with `.include(...)` is deferred "
                "(snapshot-history-includes, spec §3)"
            )
        op = self.predicate
        if not isinstance(tx_time, _Unset):
            start, end = tx_time
            op = AsOfRange(
                operand=op,
                dimension=self._dimension("tx_time"),
                start=_instant(start),
                end=_instant(end),
            )
        if not isinstance(valid_time, _Unset):
            start, end = valid_time
            op = AsOfRange(
                operand=op,
                dimension=self._dimension("valid_time"),
                start=_instant(start),
                end=_instant(end),
            )
        return self._with_temporal(op)

    def history(self, dimension: TemporalDimensionConstant) -> Statement:
        """Return the full milestone set on ``dimension`` (no predicate injected).

        ``dimension`` is one of the exported ``VALID_TIME`` / ``TX_TIME``
        constants (the ``LATEST`` sentinel pattern); a string dimension
        spelling is rejected here, at statement build.
        """
        if dimension is not VALID_TIME and dimension is not TX_TIME:
            raise ValueError(
                "history() takes its dimension as the exported VALID_TIME / TX_TIME "
                f"constant; a string dimension spelling is rejected (got {dimension!r})"
            )
        if self.include_paths:
            raise UnsupportedFeatureError(
                "`.history()` combined with `.include(...)` is deferred "
                "(snapshot-history-includes, spec §3)"
            )
        name: _DimensionName = "valid_time" if dimension.dimension == "validTime" else "tx_time"
        return self._with_temporal(History(operand=self.predicate, dimension=self._dimension(name)))

    def include(self, *paths: RelationshipPath) -> Statement:
        """Deep-fetch one or more relationship paths (python.md §2):
        ``Order.where(...).include(Order.items.statuses, Order.tags)``. One
        path grammar shared with predicates; a longer path implies its
        intermediates. Accumulates across calls (not single-shot). Validated
        against the metamodel immediately (never at execution, never at the
        database) — an undeclared hop or an illegal narrow raises here.
        """
        if not paths:
            raise ValueError("include requires at least one path")
        if self.is_milestone_set():
            raise UnsupportedFeatureError(
                "`.include(...)` combined with `.history()` / `.as_of_range()` is deferred "
                "(snapshot-history-includes, spec §3)"
            )
        new_paths = self.include_paths + tuple(path.segments for path in paths)
        _validate(self.binding, self.target, DeepFetch(operand=self.predicate, paths=new_paths))
        return replace(self, include_paths=new_paths)

    def narrow(self, *subtypes: type) -> Statement:
        """The whole-statement subtype-narrowing clause (python.md §2):
        ``Animal.where(...).narrow(Dog, Cat)``. A PURE result-set narrowing
        that wraps the already-conjoined ``where`` predicate as the single
        top-level ``narrow``'s operand (zero predicates ⇒ ``all``) and grants
        NO attribute scope to the already-built ``where`` arguments (those
        validated immediately at ``Entity.where`` build time, under the
        UNCONSTRAINED position) — single-shot, like ``as_of``. Converges on
        the identical canonical node as
        ``Entity.where(Entity.narrow(Dog, where=...))``.
        """
        if self.is_narrowed:
            raise ValueError("a narrow clause is single-shot; derive from the un-narrowed base")
        to = tuple(declaration_of(subtype).identity.name for subtype in subtypes)
        node = Narrow(entity=self.target, to=to, operand=self.predicate)
        _validate(self.binding, self.target, node)
        return replace(self, predicate=node, is_narrowed=True)

    def operation(self) -> Operation:
        """The canonical ``m-op-algebra`` operation for this statement."""
        op = self.temporal if self.temporal is not None else self.predicate
        if self.is_distinct:
            op = Distinct(operand=op)
        if self.order_keys:
            op = OrderBy(operand=op, keys=self.order_keys)
        if self.limit_count is not None:
            op = Limit(operand=op, count=self.limit_count)
        if self.include_paths:
            op = DeepFetch(operand=op, paths=self.include_paths)
        return op

    def serialize(self) -> dict[str, object]:
        """The canonical operation document (for the operation no-drift guard)."""
        return serialize(self.operation())

    def is_milestone_set(self) -> bool:
        """Whether this statement's temporal wrapper SCANS an axis (``history``
        / ``as_of_range``) rather than pinning it (``as_of``) — the
        ``snapshot-history-includes`` deferral boundary."""
        return isinstance(self.temporal, (AsOfRange, History))

    def is_bare(self) -> bool:
        """Whether this statement carries NOTHING but a predicate (python.md §5
        "A statement becomes a write target only as a bare statement — one
        carrying nothing but a predicate"): the single guard every ``_where``
        verb shares. Every result-shaping / temporal / narrowing / deep-fetch
        field must sit at its default — ``order_by``, ``limit``, ``as_of`` /
        ``history`` / ``as_of_range``, ``include``, and ``narrow`` are each
        checked (the spec's own enumeration), and ``.distinct()`` is caught the
        SAME way (an explicit non-default field), even though the prose
        enumeration omits it — resolving that gap by construction rather than
        special-casing one flag. ``target`` / ``predicate`` / ``as_of_axes``
        are excluded: the first two are exactly what a bare statement legitimately
        carries, and the third is metadata ``Entity.where`` always captures
        (the entity's own declared temporal dimensions), never an authored
        clause.
        """
        return (
            self.order_keys == ()
            and self.limit_count is None
            and self.is_distinct is False
            and self.temporal is None
            and self.include_paths == ()
            and self.is_narrowed is False
        )

    def _with_temporal(self, op: Operation) -> Statement:
        if self.temporal is not None:
            raise ValueError(
                "a temporal clause is single-shot; derive from the unpinned base (re-pinning "
                "is a deferred additive extension)"
            )
        if op is self.predicate:
            raise ValueError(
                "a temporal clause requires at least one dimension (valid_time= / tx_time=)"
            )
        return replace(self, temporal=op)

    def _dimension(self, name: _DimensionName) -> WireDimension:
        """The canonical wire dimension for the developer-surface coordinate
        spelling ``name`` (the snake→camel boundary: ``tx_time`` maps to
        ``transactionTime``), validated against the target's declared axes."""
        declared = (
            TemporalDimension.VALID_TIME
            if name == "valid_time"
            else TemporalDimension.TRANSACTION_TIME
        )
        dimension: WireDimension = "validTime" if name == "valid_time" else "transactionTime"
        for axis in self.as_of_axes:
            if axis.dimension is declared:
                return dimension
        detail = (
            "declares no temporal dimension"
            if not self.as_of_axes
            else f"declares no {name} dimension"
        )
        raise ValueError(f"{self.target} {detail}")


def _instant(value: _Pin) -> str:
    """A canonical coordinate: ``latest`` or a UTC-normalized finite instant."""
    if isinstance(value, Latest):
        return "latest"
    return normalize_instant(value).isoformat()


def build_statement(
    target: str,
    predicates: tuple[Predicate, ...],
    *,
    as_of_axes: tuple[AsOfAxisMetadata, ...] = (),
    binding: MetamodelBinding | None = None,
) -> Statement:
    """Build a :class:`Statement` conjoining ``predicates`` (empty is find-all).

    The conjoined predicate is validated against ``binding``'s model as it is
    built, so a subtype attribute reached outside a narrow scope is refused
    here rather than at execution.
    """
    predicate = _conjoined(predicates)
    _validate(binding, target, predicate)
    return Statement(target=target, predicate=predicate, as_of_axes=as_of_axes, binding=binding)


def _validate(binding: MetamodelBinding | None, target: str, node: Operation) -> None:
    """Validate ``node`` against the model ``binding``'s hub sealed.

    A Statement built directly carries no Binding and validates nothing, which
    is what lets the operation-shaping clauses be exercised without a whole
    model behind them.
    """
    if binding is None:
        return
    root = entity_by_name(binding.model, target)
    if root is None:  # pragma: no cover - the target is an Entity of its own hub
        return
    validate_operation(root, node, binding.model)


def _conjoined(predicates: tuple[Predicate, ...]) -> Operation:
    if not predicates:
        return All()
    if len(predicates) == 1:
        return predicates[0].op
    operands: list[Operation] = []
    for predicate in predicates:
        operands.extend(and_terms(predicate))
    return And(operands=tuple(operands))
