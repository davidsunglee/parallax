from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, assert_never

from parallax.core.base import (
    INFINITY,
    ManagedValue,
    TemporalBound,
    normalize_instant,
)
from parallax.core.inheritance import root_metadata
from parallax.core.inheritance import view as inheritance_view
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
from parallax.core.temporal_read._compile import MODEL_COMPILER
from parallax.core.temporal_read._facet import (
    FACET_KEY,
    NON_TEMPORAL,
    TEMPORAL_READ_MODULE,
    Bitemporal,
    NonTemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
    ranked_axes,
    view,
)

__all__ = [
    "FACET_KEY",
    "MODEL_COMPILER",
    "NON_TEMPORAL",
    "TEMPORAL_READ_MODULE",
    "Bitemporal",
    "Edge",
    "MilestoneRows",
    "NonTemporal",
    "Pin",
    "TemporalFacet",
    "TemporalReadError",
    "TemporalShape",
    "TimeInterval",
    "TransactionTimeOnly",
    "UndeclaredAxisError",
    "inject_resolved_as_of",
    "milestone_edge",
    "ranked_axes",
    "resolved_pinned_instants",
    "scans_validated_axis",
    "valid_time_coverage",
    "validated_hop_as_of_terms",
    "validated_query_pin",
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


type _End = _dt.datetime | Literal[TemporalBound.INFINITY]


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """A nonempty half-open ``[start, end)`` interval on one As-Of Axis.

    The endpoints are managed values held exactly as their owner supplied them:
    construction checks only that ``start`` precedes ``end`` — raising
    ``ValueError`` for an empty or reversed interval — and nothing here parses,
    normalizes, or encodes an endpoint. :data:`~parallax.core.base.INFINITY` is
    the open end, later than every finite instant. Holders name the axis and the
    role the interval plays for them.
    """

    start: _dt.datetime
    end: _dt.datetime | Literal[TemporalBound.INFINITY]

    def __post_init__(self) -> None:
        end = self.end
        if end is not INFINITY and not self.start < end:
            raise ValueError(
                f"a TimeInterval requires start < end: [{self.start.isoformat()}, "
                f"{end.isoformat()})"
            )

    def overlaps(self, other: TimeInterval) -> bool:
        """Whether the two share an instant; adjacent intervals do not."""
        return _before(self.start, other.end) and _before(other.start, self.end)

    def disjoint(self, other: TimeInterval) -> bool:
        """Whether the two share no instant, so adjacent intervals are disjoint."""
        return not self.overlaps(other)

    def contains(self, value: _dt.datetime | TimeInterval) -> bool:
        """Whether a finite instant lies in ``[start, end)``, or another interval
        lies entirely within this one, equal intervals included."""
        if isinstance(value, TimeInterval):
            return self.start <= value.start and _ends_by(value.end, self.end)
        return self.start <= value and _before(value, self.end)

    def meets(self, other: TimeInterval) -> bool:
        """Whether ``other`` begins exactly where this interval ends."""
        end = self.end
        return end is not INFINITY and end == other.start

    def precedes(self, other: TimeInterval) -> bool:
        """Whether this interval ends strictly before ``other`` begins, so that a
        gap separates them; adjacency is :meth:`meets`, not precedence."""
        end = self.end
        return end is not INFINITY and end < other.start

    def starts_after(self, instant: _dt.datetime) -> bool:
        """Whether this interval begins strictly after a finite instant."""
        return self.start > instant

    def ends_after(self, instant: _dt.datetime) -> bool:
        """Whether this interval ends strictly after a finite instant."""
        return _before(instant, self.end)

    def intersection(self, other: TimeInterval) -> TimeInterval | None:
        """The instants both intervals share, or ``None`` where they share none.

        An operand that already is the shared extent is answered itself; only a
        partial overlap constructs a new interval over the operands' endpoints.
        """
        if self.disjoint(other):
            return None
        if self.contains(other):
            return other
        if other.contains(self):
            return self
        start = self.start if other.start < self.start else other.start
        end = self.end if _ends_by(self.end, other.end) else other.end
        return TimeInterval(start, end)

    def clipped(
        self,
        *,
        start: _dt.datetime | None = None,
        end: _dt.datetime | None = None,
    ) -> TimeInterval | None:
        """This interval narrowed to the finite limits given, or ``None`` where
        nothing of it lies between them.

        A limit only narrows: one outside the interval leaves that side as it
        is, and an unchanged extent is answered by this interval itself.
        """
        clipped_start = self.start if start is None or start <= self.start else start
        clipped_end = self.end if end is None or not _before(end, self.end) else end
        if clipped_start is self.start and clipped_end is self.end:
            return self
        if clipped_end is not INFINITY and not clipped_start < clipped_end:
            return None
        return TimeInterval(clipped_start, clipped_end)

    def first_uncovered(self, coverage: Iterable[TimeInterval]) -> _dt.datetime | None:
        """The earliest instant of this interval that no interval of ``coverage``
        contains, or ``None`` where they cover all of it.

        ``coverage`` must be ordered by start; adjacent, overlapping, and
        duplicate intervals are all accepted. It is consumed once, and only
        until the answer is known.
        """
        cursor = self.start
        end = self.end
        for interval in coverage:
            if interval.starts_after(cursor):
                return cursor
            covered = interval.end
            if covered is INFINITY:
                return None
            if covered > cursor:
                if end is not INFINITY and not covered < end:
                    return None
                cursor = covered
        return cursor


def _before(instant: _dt.datetime, end: _End) -> bool:
    return end is INFINITY or instant < end


def _ends_by(end: _End, limit: _End) -> bool:
    return limit is INFINITY or (end is not INFINITY and end <= limit)


class MilestoneRows[At](Protocol):
    """A carrier that already holds milestones' As-Of Axis start and end values.

    ``at`` addresses one milestone within the carrier, in whatever reference the
    carrier indexes its own storage by. ``axis_start`` and ``axis_end`` answer
    the value stored for ``attribute`` there through that storage's own lookup,
    returning an absent or undecoded value as it is rather than refusing it:
    :func:`milestone_edge` and :func:`valid_time_coverage` own that judgement.
    """

    def axis_start(self, at: At, attribute: AttributeIdentity, /) -> object: ...

    def axis_end(self, at: At, attribute: AttributeIdentity, /) -> object: ...


def milestone_edge[At](shape: TemporalShape, rows: MilestoneRows[At], at: At) -> Edge:
    """A milestone's :class:`Edge`: each axis's start value in ``rows`` at ``at``.

    Each declared axis's edge is the milestone's own **from-instant** — its start
    Attribute's value — the one instant guaranteed to re-select exactly that
    milestone on a half-open ``[from, to)`` interval. ``shape`` is the family's
    Temporal Shape, so an inherited position reads the root's axes without its
    Metadata. Raises :class:`TemporalReadError` for a Non-Temporal family and
    for a start value that is not a timestamp instant.
    """
    match shape:
        case TransactionTimeOnly(transaction_time=tx):
            return Edge(
                tx_time=_instant(tx.start_attribute, rows.axis_start(at, tx.start_attribute))
            )
        case Bitemporal(valid_time=vt, transaction_time=tx):
            return Edge(
                tx_time=_instant(tx.start_attribute, rows.axis_start(at, tx.start_attribute)),
                valid_time=_instant(vt.start_attribute, rows.axis_start(at, vt.start_attribute)),
            )
        case NonTemporal():
            raise TemporalReadError("a Non-Temporal family has no milestone edge")


def _instant(attribute: AttributeIdentity, value: object) -> _dt.datetime:
    if not isinstance(value, _dt.datetime):
        raise TemporalReadError(
            f"{attribute.entity.name}.{attribute.name}: the milestone start value "
            "is not a timestamp instant"
        )
    return normalize_instant(value)


def valid_time_coverage[At](
    shape: TemporalShape, rows: MilestoneRows[At], at: At
) -> TimeInterval | None:
    """The Valid-Time interval a milestone in ``rows`` at ``at`` covers, over the
    very endpoint objects its carrier holds, or ``None`` for a family without
    Valid Time.

    Only the representation is checked: a start that is not a datetime, or an
    end that is neither a datetime nor :data:`~parallax.core.base.INFINITY`,
    raises :class:`TemporalReadError` naming its member, and an empty or
    reversed extent raises ``ValueError``. Endpoints are neither decoded nor
    normalized.
    """
    match shape:
        case Bitemporal(valid_time=vt):
            start = rows.axis_start(at, vt.start_attribute)
            end = rows.axis_end(at, vt.end_attribute)
            if not isinstance(start, _dt.datetime):
                raise _not_an_endpoint(vt.start_attribute)
            if end is not INFINITY and not isinstance(end, _dt.datetime):
                raise _not_an_endpoint(vt.end_attribute)
            return TimeInterval(start, end)
        case TransactionTimeOnly() | NonTemporal():
            return None


def _not_an_endpoint(attribute: AttributeIdentity) -> TemporalReadError:
    return TemporalReadError(
        f"{attribute.entity.name}.{attribute.name}: the milestone's Valid-Time "
        "value is not a managed interval endpoint"
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
                    _framework_comparison(op="eq", attr=end_ref, member=end, value=INFINITY)
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
    shape = view(model).shape(target.identity)
    if shape is None:  # pragma: no cover - accepted metadata is total
        raise TemporalReadError(f"{target.identity.canonical}: no temporal shape")
    axes = ranked_axes(shape)
    if not axes:
        return ()
    declarer = root_metadata(inheritance_view(model), model, target.identity)
    terms: list[ValidatedPredicate] = []
    for axis in axes:
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
                    value=INFINITY,
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
