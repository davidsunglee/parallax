from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import assert_never

from parallax.core.base import INFINITY_LITERAL, ManagedValue, normalize_instant
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, Metamodel
from parallax.core.metamodel import TemporalDimension as AcceptedDimension
from parallax.core.object_query import LATEST, Latest
from parallax.core.object_query._validated import (
    ValidatedAsOfSelection,
    ValidatedHistorySelection,
    ValidatedLatestSelection,
    ValidatedRangeSelection,
    ValidatedTemporalSelection,
)
from parallax.core.predicate._validated import (
    ValidatedPredicate,
)
from parallax.core.predicate._validated import (
    conjunction as _validated_conjunction,
)
from parallax.core.predicate._validated import (
    framework_comparison as _framework_comparison,
)
from parallax.core.predicate._validated import (
    managed_comparison as _managed_comparison,
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
    "milestone_edge_from_members",
    "milestone_edge_of",
    "validated_hop_as_of_terms",
    "view",
]


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


def milestone_edge_of(entity: EntityMetadata, values: Mapping[AttributeIdentity, object]) -> Edge:
    """A milestone's :class:`Edge`, read off values keyed by **member identity**.

    Each declared axis's edge is the milestone's own **from-instant** — its start
    Attribute's value — the one instant guaranteed to re-select exactly that
    milestone on a half-open ``[from, to)`` interval. Attribute Identity is the
    form a materialized node answers in: once a row has been converted, the
    physical column that carried each value is gone.

    ``entity`` is the Entity whose declaration carries the family's axes, which
    the caller resolves; a position that inherits them declares none of its own.
    """
    return _edge(entity, values)


def milestone_edge_from_members(entity: EntityMetadata, members: Mapping[str, object]) -> Edge:
    """The :func:`milestone_edge_of` rule, read off values keyed by **declared member name**.

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


def inject_resolved_as_of(
    predicate: ValidatedPredicate,
    selections: tuple[ValidatedTemporalSelection, ...],
    entity: EntityMetadata,
) -> ValidatedPredicate:
    """Append temporal terms from managed, resolved selections."""
    terms: list[ValidatedPredicate] = []
    for selection in selections:
        start = entity.attribute(selection.axis.start_attribute.name)
        end = entity.attribute(selection.axis.end_attribute.name)
        if start is None or end is None:
            raise TemporalReadError(f"{entity.identity.name}: temporal axis member is undeclared")
        start_ref = f"{entity.identity.canonical}.{start.identity.name}"
        end_ref = f"{entity.identity.canonical}.{end.identity.name}"
        match selection:
            case ValidatedHistorySelection():
                continue
            case ValidatedLatestSelection():
                terms.append(
                    _framework_comparison(op="eq", attr=end_ref, member=end, value=INFINITY_LITERAL)
                )
            case ValidatedAsOfSelection(coordinate=coordinate):
                terms.extend(
                    (
                        _managed_comparison(
                            op="lessThanEquals",
                            attr=start_ref,
                            member=start,
                            value=coordinate,
                        ),
                        _managed_comparison(
                            op="greaterThan", attr=end_ref, member=end, value=coordinate
                        ),
                    )
                )
            case ValidatedRangeSelection(start=window_start, end=window_end):
                terms.extend(
                    (
                        _managed_comparison(
                            op="lessThan", attr=start_ref, member=start, value=window_end
                        ),
                        _managed_comparison(
                            op="greaterThan", attr=end_ref, member=end, value=window_start
                        ),
                    )
                )
            case _:
                assert_never(selection)
    return predicate if not terms else _validated_conjunction(predicate, *terms)


def resolved_pinned_instants(
    selections: tuple[ValidatedTemporalSelection, ...],
) -> dict[AcceptedDimension, ManagedValue]:
    return {
        selection.axis.dimension: selection.coordinate
        for selection in selections
        if isinstance(selection, ValidatedAsOfSelection)
    }


def validated_query_pin(selections: tuple[ValidatedTemporalSelection, ...]) -> Pin:
    """Return the pin already decoded by Object Query validation."""
    tx_time: _dt.datetime | Latest | None = None
    valid_time: _dt.datetime | Latest | None = None
    for selection in selections:
        value: _dt.datetime | Latest
        if isinstance(selection, ValidatedLatestSelection):
            value = LATEST
        elif isinstance(selection, ValidatedAsOfSelection):
            if not isinstance(selection.coordinate, _dt.datetime):
                raise TemporalReadError("a temporal coordinate is not a managed datetime")
            value = selection.coordinate
        else:
            continue
        if selection.axis.dimension is AcceptedDimension.TRANSACTION_TIME:
            tx_time = value
        else:
            valid_time = value
    return Pin(tx_time=tx_time, valid_time=valid_time)


def scans_validated_axis(selections: tuple[ValidatedTemporalSelection, ...]) -> bool:
    return any(
        isinstance(selection, ValidatedHistorySelection | ValidatedRangeSelection)
        for selection in selections
    )


def validated_hop_as_of_terms(
    target: EntityMetadata,
    model: Metamodel,
    root_pins: Mapping[AcceptedDimension, ManagedValue],
) -> tuple[ValidatedPredicate, ...]:
    """Build managed per-hop terms; an absent pin means the framework Latest sentinel."""
    # Import locally to keep the existing temporal facet's module layering unchanged.
    from parallax.core import inheritance

    declarer_view = inheritance.view(model).entity(target.identity)
    if declarer_view is None:  # pragma: no cover - accepted metadata is total
        raise TemporalReadError(f"{target.identity.canonical}: no inheritance view")
    declarer = model.entity(declarer_view.root)
    if declarer is None:  # pragma: no cover - accepted metadata is total
        raise TemporalReadError(f"{declarer_view.root.canonical}: no declaring entity")
    terms: list[ValidatedPredicate] = []
    for axis in sorted(declarer.declared_as_of_axes, key=lambda item: item.dimension.value):
        instant = root_pins.get(axis.dimension)
        if instant is None:
            end = declarer.attribute(axis.end_attribute.name)
            if end is None:
                raise TemporalReadError(
                    f"{declarer.identity.name}: temporal axis member is undeclared"
                )
            terms.append(
                _framework_comparison(
                    op="eq",
                    attr=f"{declarer.identity.canonical}.{end.identity.name}",
                    member=end,
                    value=INFINITY_LITERAL,
                )
            )
            continue
        start = declarer.attribute(axis.start_attribute.name)
        end = declarer.attribute(axis.end_attribute.name)
        if start is None or end is None:
            raise TemporalReadError(f"{declarer.identity.name}: temporal axis member is undeclared")
        terms.extend(
            (
                _managed_comparison(
                    op="lessThanEquals",
                    attr=f"{declarer.identity.canonical}.{start.identity.name}",
                    member=start,
                    value=instant,
                ),
                _managed_comparison(
                    op="greaterThan",
                    attr=f"{declarer.identity.canonical}.{end.identity.name}",
                    member=end,
                    value=instant,
                ),
            )
        )
    return tuple(terms)
