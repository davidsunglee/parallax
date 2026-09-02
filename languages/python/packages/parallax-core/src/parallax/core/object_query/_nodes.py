"""Object Query values (m-object-query).

The canonical query value and the clause values it carries, as frozen ``slots``
dataclasses with no base class. An :class:`ObjectQueryNode` is FLAT: every clause
is a sibling field, so clause authoring order carries no meaning and no clause
can nest inside another. Recursion belongs to ``m-predicate`` alone, which this
module carries as one field.

The private deep-fetch flat-query product is the non-wire value ``m-sql`` compiles — one
root or related-Entity query whose temporal terms are already injected into its
predicate. It is deliberately separate from :class:`ObjectQueryNode`: a child
fetch level derives one without ever being an authored query.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, Final, Literal, Self

from parallax.core.metamodel import EntityIdentity
from parallax.core.predicate import (
    PredicateNode,
    QueryDefinitionError,
    SubtypeSelection,
    canonical_subtype_selection,
)

__all__ = [
    "LATEST",
    "TX_TIME",
    "VALID_TIME",
    "AsOf",
    "AsOfRange",
    "History",
    "IncludePath",
    "IncludeSegment",
    "Latest",
    "MutationSelection",
    "ObjectQueryNode",
    "OrderKey",
    "TemporalDimension",
    "TemporalDimensionConstant",
    "TemporalSelection",
]

TemporalDimension = Literal["valid-time", "transaction-time"]


class Latest:
    """The explicit Latest coordinate sentinel — including normalized Transaction-Time omission.

    ``LATEST`` on a dimension lowers to the **identical** current-row predicate the
    authoring default produces for omitted Transaction Time (``to = infinity``).
    A canonical Object Query always states it (``asOf: latest``) rather than
    leaving the dimension absent. It is deliberately not a coordinate — it
    re-resolves to whatever milestone is current at read time, so it is never
    replayable (python.md, the stale-web-edit recipe).

    Sameness is identity: :data:`LATEST` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[Latest | None] = None

    def __new__(cls) -> Latest:
        if Latest._instance is None:
            Latest._instance = super().__new__(cls)
        return Latest._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "LATEST"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "LATEST"


LATEST: Final[Latest] = Latest()


class TemporalDimensionConstant:
    """One exported Temporal Dimension constant — :data:`VALID_TIME` / :data:`TX_TIME`.

    The developer-surface spelling of a Temporal Dimension value wherever the
    query surface takes a dimension argument (``.history(TX_TIME)``), following
    the :data:`LATEST` sentinel pattern: one ``Final`` module-level singleton per
    dimension of the closed two-member algebra, giving completion and static
    checking where a string offers neither. A string dimension spelling is
    rejected at query build — a dual-accept surface would be an alias. Instances
    are immutable: the query surface accepts the constants by identity, so a
    mutable dimension could silently flip what an accepted constant selects.
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
    def dimension(self) -> TemporalDimension:
        """The canonical dimension spelling this constant maps to at the wire boundary."""
        return "valid-time" if self._dimension == "valid-time" else "transaction-time"

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "VALID_TIME" if self._dimension == "valid-time" else "TX_TIME"


VALID_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("valid-time")
"""The Valid Time dimension constant: the sole developer-surface spelling of the
``valid-time`` dimension wherever a query takes a dimension argument
(``.history(VALID_TIME)``). A frozen module-level singleton — the query surface
accepts exactly this instance, by identity, never an equal copy or a string."""

TX_TIME: Final[TemporalDimensionConstant] = TemporalDimensionConstant("transaction-time")
"""The Transaction Time dimension constant: the sole developer-surface spelling
of the ``transaction-time`` dimension wherever a query takes a dimension
argument (``.history(TX_TIME)``). A frozen module-level singleton — the query
surface accepts exactly this instance, by identity, never an equal copy or a
string."""


@dataclass(frozen=True, slots=True)
class AsOf:
    """Pin one dimension at a coordinate: ``latest`` or a finite instant."""

    coordinate: str


@dataclass(frozen=True, slots=True)
class AsOfRange:
    """Scan one dimension across the finite half-open window ``[start, end)``."""

    start: str
    end: str


@dataclass(frozen=True, slots=True)
class History:
    """Return one dimension's full milestone set (no as-of term injected)."""


TemporalSelection = AsOf | AsOfRange | History
"""One dimension's closed Temporal Selection (m-temporal-read)."""


@dataclass(frozen=True, slots=True)
class OrderKey:
    """One Sort Key of an Object Query's ordering.

    ``direction`` is ``None`` when the authored key omitted it (the schema's
    optional ``direction`` defaults to ``asc``), and ``nulls`` is ``None`` when it
    omitted the Null Placement (schema default ``last``). Serde round-trips both
    absences faithfully — an omitted member serializes back omitted — while SQL
    lowering treats them as the ``asc`` and ``last`` defaults.

    A Sort Key is a query-definition construct, so a rejected placement
    composition raises :class:`~parallax.core.predicate.QueryDefinitionError`. The
    relationship-declaration ordering term (``OrderTerm``) carries the same
    single-shot placement rule but is part of a model declaration rather than of
    a query, so it stays outside that family and raises a plain
    :class:`ValueError`; the two spellings differ because the surfaces do, not by
    accident.
    """

    attr: str
    direction: Literal["asc", "desc"] | None = None
    nulls: Literal["first", "last"] | None = None

    def nulls_first(self) -> OrderKey:
        """This key with NULLs placed first. Single-shot (m-object-query)."""
        return self._with_placement("first")

    def nulls_last(self) -> OrderKey:
        """This key with NULLs placed last — the default, stated explicitly."""
        return self._with_placement("last")

    def _with_placement(self, placement: Literal["first", "last"]) -> OrderKey:
        if self.nulls is not None:
            raise QueryDefinitionError(
                code="query-expression-invalid",
                message=(
                    f"{self.attr}: null placement is single-shot and is already "
                    f"{self.nulls!r}; derive the key from the unplaced base"
                ),
            )
        return OrderKey(attr=self.attr, direction=self.direction, nulls=placement)


@dataclass(frozen=True, slots=True)
class IncludeSegment:
    """One hop of an Include Path: a relationship, optionally subtype-narrowed."""

    rel: str
    narrow_to: SubtypeSelection = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "narrow_to", canonical_subtype_selection(self.narrow_to))


@dataclass(frozen=True, slots=True)
class IncludePath:
    """One Include Path: the ordered, non-empty hops it traverses, and the
    optional source guard restricting which queried objects it starts from.

    A path is its own value rather than a bare segment tuple, so what qualifies
    the path as a whole stays distinguishable from what qualifies one hop.
    """

    segments: tuple[IncludeSegment, ...]
    applies_to: SubtypeSelection | None = None

    def __post_init__(self) -> None:
        if self.applies_to is not None:
            object.__setattr__(self, "applies_to", canonical_subtype_selection(self.applies_to))


_NO_TEMPORAL: Final[Mapping[TemporalDimension, TemporalSelection]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ObjectQueryNode:
    """The canonical Object Query: one flat query for full objects.

    ``target`` is the queried position and ``predicate`` its selection logic;
    both are always present, an unfiltered query carrying
    :class:`~parallax.core.predicate.All`. Every other clause is optional and
    occurs at most once — ``temporal`` is keyed by Temporal Dimension, so "one
    selection per dimension" is a property of the mapping rather than a rule
    something restates.

    ``narrow_to`` and an Include Path's own selections keep their AUTHORED
    Subtype Selection spellings: ``[Pet]`` and ``[Cat, Dog]`` stay distinct
    canonical queries even where they resolve to the same effective set, so
    resolution against a model stays a preflight and planning concern.
    """

    target: EntityIdentity
    predicate: PredicateNode
    narrow_to: SubtypeSelection | None = None
    temporal: Mapping[TemporalDimension, TemporalSelection] = _NO_TEMPORAL
    order_by: tuple[OrderKey, ...] = ()
    limit: int | None = None
    includes: tuple[IncludePath, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MutationSelection:
    """What a predicate-selected write reads off an Object Query.

    The ephemeral normalization of a mutation-compatible query: the position to
    write and the predicate that selects within it, and nothing else. It is
    neither exported nor serialized, and it is NOT
    ``parallax.core.unit_work.PredicateSelection`` — the write boundary builds
    that canonical value from these two facts, so an Object Query never reaches
    the unit of work, the planner, or SQL lowering.
    """

    target: EntityIdentity
    predicate: PredicateNode
