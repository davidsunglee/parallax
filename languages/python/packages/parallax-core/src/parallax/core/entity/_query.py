"""The Find Query surface (support scope, query half).

``Entity.where(first, *rest)`` builds a side-effect-free :class:`FindQuery` — the
big-AND of its filter criteria, or the explicitly unfiltered ``Entity.all``.
``.narrow`` / ``.as_of`` / ``.as_of_range`` / ``.history`` / ``.order_by`` /
``.limit`` / ``.include`` layer the remaining clauses, each returning a new value
and leaving its receiver unchanged.

A Find Query is a CLAUSE RECORD, not a partially built operation. Each clause is
retained independently and none wraps another, so clause invocation order cannot
reach the wire: :func:`lower_find_query` places them in the one canonical
inner-to-outer order — predicate, root narrow, temporal wrapper(s), ordering,
limit, deep fetch — every time it runs. Permuting otherwise valid calls therefore
produces the identical canonical operation by construction rather than by
discipline.

Lowering lives here rather than in a module of its own for one reason: it reads
the query's private clause state, and a seam that reached it from outside would
either publish that state or copy it. What it answers is a
:class:`LoweredFindQuery` — a target Entity Identity and a canonical
``m-predicate`` operation, and nothing else. It completes the class-local
temporal authoring contract: omitted Transaction Time becomes explicit Latest,
while omitted Valid Time on a Bitemporal target raises. It is never memoized:
each call returns a fresh lowering, and one execution keeps its result locally.

Authoring reaches no model. Every rule stated here is class-local — clause
arity, single-shot clauses, the target's own declared temporal axes, literal
shapes — and every rule that needs a whole model is stated once at execution
preflight, which is also what covers the wire path and any untyped caller.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from parallax.core.base import normalize_instant
from parallax.core.entity._declaration import declaration_of
from parallax.core.entity._expressions import (
    AllPredicate,
    Predicate,
    RelationshipPath,
    SortKey,
    conjoin,
)
from parallax.core.metamodel import AsOfAxisMetadata, EntityIdentity, TemporalDimension
from parallax.core.predicate import (
    AsOf,
    AsOfRange,
    DeepFetch,
    History,
    Limit,
    Narrow,
    NavigationPath,
    OrderBy,
    OrderKey,
    PredicateNode,
    QueryDefinitionError,
)
from parallax.core.predicate._builders import _canonical_includes
from parallax.core.predicate._nodes import (
    TemporalDimension as WireDimension,
)
from parallax.core.predicate._nodes import (
    canonical_subtype_selection,
)
from parallax.core.temporal_read import TX_TIME, VALID_TIME, Latest, TemporalDimensionConstant

if TYPE_CHECKING:
    # The narrowing bound alone, and a PEP 695 bound is evaluated lazily, so this
    # states the rule without an import cycle: `_entity` imports this module for
    # `Entity.where`'s own answer.
    from parallax.core.entity._entity import Entity

__all__ = [
    "FindQuery",
    "LoweredFindQuery",
    "MutationSelection",
    "build_find_query",
    "lower_find_query",
    "mutation_selection",
]


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
class _AsOfClause:
    """One axis PINNED at a coordinate (``asOf``)."""

    dimension: WireDimension
    coordinate: str

    def wrap(self, operand: PredicateNode) -> PredicateNode:
        return AsOf(operand=operand, dimension=self.dimension, coordinate=self.coordinate)


@dataclass(frozen=True, slots=True)
class _AsOfRangeClause:
    """One axis SCANNED across a half-open window (``asOfRange``)."""

    dimension: WireDimension
    start: str
    end: str

    def wrap(self, operand: PredicateNode) -> PredicateNode:
        return AsOfRange(operand=operand, dimension=self.dimension, start=self.start, end=self.end)


@dataclass(frozen=True, slots=True)
class _HistoryClause:
    """One axis's full milestone set (``history``)."""

    dimension: WireDimension

    def wrap(self, operand: PredicateNode) -> PredicateNode:
        return History(operand=operand, dimension=self.dimension)


_TemporalClause = _AsOfClause | _AsOfRangeClause | _HistoryClause


def _temporal_rank(clause: _TemporalClause) -> int:
    """Canonical inner-to-outer rank: Transaction Time, then Valid Time."""
    return 0 if clause.dimension == "transaction-time" else 1


@dataclass(frozen=True, slots=True, eq=False)
class FindQuery[E, S]:
    """An immutable, side-effect-free query over one target Entity.

    ``E`` is the Entity QUERIED and ``S`` the Entity the result RETURNS, which
    ``narrow`` — and only ``narrow`` — moves. The split is what makes
    ``include`` and ``order_by`` measure different things: an include path's
    source is legal against the queried position, while a sort key addresses the
    rows the query actually returns.

    Every field is private authoring state. A Find Query exposes no execution,
    serialization, canonical-operation inspection, or refinement ``.where(...)``,
    carries no Snapshot feature tags and no model, and defines no structural
    equality or semantic hash — two independently authored queries lowering to
    one operation are still two objects, and conformance code compares canonical
    lowerings through :func:`lower_find_query` instead. ``bool(query)`` raises:
    a Find Query has no pre-execution empty/nonempty state.

    ``Entity.where(...)`` is the sole public constructor; direct construction is
    a first-party spelling with no supported contract.
    """

    _target: EntityIdentity
    _predicate: PredicateNode
    # The target family's declared temporal axes, captured at ``Entity.where`` so
    # the dimension-keyed temporal clauses validate against them; empty for a
    # non-temporal Entity (every temporal clause then raises).
    _as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    # The root narrow's authored subtype list, or ``None`` for no narrow clause.
    # Kept as the canonical Subtype Selection rather than a built node:
    # `to: [Pet]` and `to: [Cat, Dog]` stay distinct canonical nodes even where
    # they resolve to the same effective set.
    _narrow: tuple[str, ...] | None = None
    # The axis-keyed temporal wrappers, innermost first. Each dimension is
    # single-shot; separate calls may fill separate dimensions.
    _temporal: tuple[_TemporalClause, ...] = ()
    _order_keys: tuple[OrderKey, ...] = ()
    _limit: int | None = None
    # Deep-fetch include paths (``m-deep-fetch``), each a hop sequence built by
    # chained ``Rel[T]`` class access; canonicalized after every accumulation.
    _include: tuple[NavigationPath, ...] = ()

    def include(self, *paths: RelationshipPath[E, Any]) -> FindQuery[E, S]:
        """Deep-fetch one or more relationship paths (python.md §2):
        ``Order.where(...).include(Order.items, Order.tags)``. One path grammar
        shared with predicates; a longer path implies its intermediates.
        Accumulates across calls (not single-shot) into the canonical include
        set: sorted, deduplicated, and stripped of exact prefixes a retained
        extension already materializes.

        Legality is measured against the QUERIED Entity, never against the
        narrowed result: a root narrow constrains which objects come back, not
        which sources a path may start from, so a path rooted at a subtype the
        narrow excludes is legal and populates nowhere. Every hop's own legality
        — an undeclared relationship, a value-object segment, an illegal hop
        narrow — is a whole-model question and is settled at execution preflight.

        A path seeded through a subtype (``include(Dog.owner, Cat.owner)``)
        carries that class's path-root guard, so the two are one relationship
        fetched for disjoint sets of queried objects — never two relationships,
        and never two views (spec §3).
        """
        if not paths:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="include requires at least one path"
            )
        added = tuple(
            NavigationPath(segments=path.segments, narrow=self._root_guard(path.source))
            for path in paths
        )
        return replace(self, _include=_canonical_includes(self._include + added))

    def order_by(self, *keys: SortKey[S]) -> FindQuery[E, S]:
        """Order the result by one or more Sort Keys (``Attr.asc()`` /
        ``Attr.desc()``), in precedence order. Accumulates across calls.

        A Sort Key carries the position it was built from and the canonical
        ordering term it holds; the query keeps the term alone, because the
        ordered rows' position is a property of the query rather than of a key.

        Keys are measured against the RESULT, so a subtype's key requires the
        root narrow that establishes its scope first — and that ordering rule is
        STATIC ONLY. Clause order does not reach the wire: ordering before
        narrowing and narrowing before ordering lower to one canonical
        operation, so no model-aware rule could refuse the first and accept the
        second. What refuses it is this parameter, against the result the
        receiver carries at the moment the call is written.

        One resolved Attribute Identity may occur only once across the whole
        accumulated ordering, whichever direction each occurrence carries: a
        second ordering term over one attribute states nothing the first did not
        and is refused rather than silently dropped.
        """
        if not keys:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="order_by requires at least one key"
            )
        accumulated = self._order_keys + tuple(key.key for key in keys)
        seen: set[str] = set()
        for key in accumulated:
            if key.attr in seen:
                raise QueryDefinitionError(
                    code="query-clause-invalid",
                    message=(
                        f"{key.attr} already orders this query; one attribute occurs once "
                        "across the whole accumulated ordering, whatever direction each "
                        "occurrence carries"
                    ),
                )
            seen.add(key.attr)
        return replace(self, _order_keys=accumulated)

    def limit(self, count: int) -> FindQuery[E, S]:
        """Cap the result row count at a positive built-in ``int``. Single-shot:
        a second call is refused rather than replacing or tightening the first,
        so alternate limits derive from the same unbounded base.

        ``bool``, zero, negative values, and anything that would need coercion
        are refused rather than coerced — ``True`` is not the limit 1.
        """
        if self._limit is not None:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message="a limit clause is single-shot; derive from the unbounded base",
            )
        if type(count) is not int or count < 1:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=f"limit requires a positive built-in int (got {count!r})",
            )
        return replace(self, _limit=count)

    # Each arity overload's parameters are positional-only and never read, so
    # they are spelled with a leading underscore: the arity is the whole content
    # of the declaration, and the names cannot be written by a caller.
    @overload
    def narrow[N: Entity](self, _one: type[N], /) -> FindQuery[E, N]: ...
    @overload
    def narrow[N: Entity](self, _one: type[N], _two: type[N], /) -> FindQuery[E, N]: ...
    @overload
    def narrow[N: Entity](
        self, _one: type[N], _two: type[N], _three: type[N], /
    ) -> FindQuery[E, N]: ...
    @overload
    def narrow(self, *subtypes: type[Entity]) -> FindQuery[E, S]: ...
    def narrow(self, *subtypes: type[Entity]) -> FindQuery[E, Any]:
        """The whole-query subtype-narrowing clause (python.md §2):
        ``Animal.where(...).narrow(Dog, Cat)``. A PURE result-set narrowing that
        wraps the already-conjoined ``where`` predicate as the single top-level
        ``narrow``'s operand and grants NO attribute scope to the already-built
        ``where`` arguments — single-shot, like the temporal family. Converges on
        the identical canonical node as
        ``Entity.where(Entity.narrow(Dog, where=...))``.

        The RESULT parameter moves and the queried one does not, so a later sort
        key addresses the narrowed subtypes while a later include path is still
        measured against the queried Entity. Arities one through three answer the
        union of what they name; a longer list leaves the result parameter where
        it was, which is the widest honest answer a fixed overload set can give.

        Whether the named classes are subtypes of the narrowed position at all is
        NOT stated statically: a type parameter's bound may not itself be
        generic, so ``N`` cannot be bounded by ``S``. An unrelated class keeps its
        preflight rejection (``narrow-outside-position``), as does the per-model
        question of which concrete subtypes the named classes resolve to.
        """
        if self._narrow is not None:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message="a narrow clause is single-shot; derive from the un-narrowed base",
            )
        if not subtypes:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="narrow requires at least one subtype"
            )
        alternatives = tuple(declaration_of(subtype).identity.canonical for subtype in subtypes)
        if len(set(alternatives)) != len(alternatives):
            raise QueryDefinitionError(
                code="query-path-invalid",
                message="narrow alternatives must not repeat the same subtype",
            )
        return replace(self, _narrow=canonical_subtype_selection(alternatives))

    def as_of(
        self,
        *,
        valid_time: _Pin | _Unset = _UNSET,
        tx_time: _Pin | _Unset = _UNSET,
    ) -> FindQuery[E, S]:
        """Pin one or both temporal axes to an instant (or the ``LATEST`` sentinel).

        Axis-keyed and single-shot per dimension (``m-temporal-read``): an
        omitted Transaction-Time axis normalizes to an explicit Latest wrapper
        during lowering, while Valid Time must be selected for a Bitemporal
        query. When both dimensions are passed the
        **Valid-Time** wrapper encloses the **Transaction-Time** wrapper (the
        corpus's bitemporal nesting order). A naive ``datetime`` is rejected here.
        """
        clauses: list[_TemporalClause] = []
        if not isinstance(tx_time, _Unset):
            clauses.append(_AsOfClause(self._dimension("tx_time"), _instant(tx_time)))
        if not isinstance(valid_time, _Unset):
            clauses.append(_AsOfClause(self._dimension("valid_time"), _instant(valid_time)))
        return self._with_temporal(tuple(clauses))

    def as_of_range(
        self,
        *,
        valid_time: _Window | _Unset = _UNSET,
        tx_time: _Window | _Unset = _UNSET,
    ) -> FindQuery[E, S]:
        """Scan one or both axes across a half-open ``[from, to)`` window (edge points).

        Each window is an exact built-in two-item ``tuple`` of finite instants
        ordered ``start < end``. A list, a ``tuple`` subclass, any other
        iterable, an endpoint that would need coercion, a :data:`LATEST`
        endpoint, and an equal or reversed window are each refused HERE — an
        ``asOfRange``'s bounds are canonically finite and ordered
        (``predicate.schema.json``'s ``finiteTemporalInstant``, `m-temporal-read`
        "scans every milestone whose interval overlaps ``[start, end)``"), so
        the clause is never built carrying anything else and no scan reaches SQL
        with a reversed window or a ``latest`` bind.
        """
        clauses: list[_TemporalClause] = []
        if not isinstance(tx_time, _Unset):
            start, end = _window(tx_time, "tx_time")
            clauses.append(_AsOfRangeClause(self._dimension("tx_time"), start, end))
        if not isinstance(valid_time, _Unset):
            start, end = _window(valid_time, "valid_time")
            clauses.append(_AsOfRangeClause(self._dimension("valid_time"), start, end))
        return self._with_temporal(tuple(clauses))

    def history(self, dimension: TemporalDimensionConstant) -> FindQuery[E, S]:
        """Return the full milestone set on ``dimension`` (no predicate injected).

        ``dimension`` is one of the exported ``VALID_TIME`` / ``TX_TIME``
        constants (the ``LATEST`` sentinel pattern); a string dimension spelling
        is rejected here, at query build.
        """
        if dimension is not VALID_TIME and dimension is not TX_TIME:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=(
                    "history() takes its dimension as the exported VALID_TIME / TX_TIME "
                    f"constant; a string dimension spelling is rejected (got {dimension!r})"
                ),
            )
        name: _DimensionName = "valid_time" if dimension.dimension == "valid-time" else "tx_time"
        return self._with_temporal((_HistoryClause(self._dimension(name)),))

    def _root_guard(self, source: str | None) -> tuple[str, ...] | None:
        """The path-root guard an include path seeded through ``source`` authors.

        A guard is what makes a path start from fewer than every queried object,
        so it is the ACCESS SOURCE — the Entity the first hop was reached
        through — measured against this query's own queried position, never
        against the relationship's declaring Entity. That distinction is the
        whole point of keeping the two identities apart: ``Dog.doghouse``,
        declared on ``Dog``, and ``Dog.owner``, inherited from ``Animal``, guard
        an ``Animal`` query identically. Reaching the first hop through the
        queried position itself guards nothing, so it authors no narrow at all
        rather than one resolving to the whole position.
        """
        if source is None or source == self._target.canonical:
            return None
        return (source,)

    def _with_temporal(self, clauses: tuple[_TemporalClause, ...]) -> FindQuery[E, S]:
        if not clauses:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=(
                    "a temporal clause requires at least one dimension (valid_time= / tx_time=)"
                ),
            )
        existing = {clause.dimension for clause in self._temporal}
        for clause in clauses:
            if clause.dimension in existing:
                raise QueryDefinitionError(
                    code="query-clause-invalid",
                    message=(
                        f"the {clause.dimension} dimension is single-shot; derive from a "
                        "query that has not selected that dimension"
                    ),
                )
            existing.add(clause.dimension)
        merged = self._temporal + clauses
        return replace(self, _temporal=tuple(sorted(merged, key=_temporal_rank)))

    def _dimension(self, name: _DimensionName) -> WireDimension:
        """The canonical wire dimension for the developer-surface coordinate
        spelling ``name`` (the snake→camel boundary: ``tx_time`` maps to
        ``transaction-time``), validated against the target's declared axes."""
        declared = (
            TemporalDimension.VALID_TIME
            if name == "valid_time"
            else TemporalDimension.TRANSACTION_TIME
        )
        dimension: WireDimension = "valid-time" if name == "valid_time" else "transaction-time"
        for axis in self._as_of_axes:
            if axis.dimension is declared:
                return dimension
        detail = (
            "declares no temporal dimension"
            if not self._as_of_axes
            else f"declares no {name} dimension"
        )
        raise QueryDefinitionError(
            code="query-clause-invalid", message=f"{self._target.name} {detail}"
        )

    def __bool__(self) -> bool:
        raise TypeError(
            "a Find Query has no truth value before it runs; execute it through "
            "Database.find / Transaction.find and inspect the Snapshot it returns"
        )

    def _lower(self) -> LoweredFindQuery:
        """:func:`lower_find_query`'s body, stated where the clauses live."""
        op = self._predicate
        if self._narrow is not None:
            op = Narrow(to=self._narrow, operand=op)
        for clause in self._normalized_temporal():
            op = clause.wrap(op)
        if self._order_keys:
            op = OrderBy(operand=op, keys=self._order_keys)
        if self._limit is not None:
            op = Limit(operand=op, count=self._limit)
        if self._include:
            op = DeepFetch(operand=op, paths=self._include)
        return LoweredFindQuery(target=self._target, operation=op)

    def _normalized_temporal(self) -> tuple[_TemporalClause, ...]:
        """Complete the target's per-dimension temporal selection for lowering."""
        selected = {clause.dimension for clause in self._temporal}
        declared = {
            "valid-time" if axis.dimension is TemporalDimension.VALID_TIME else "transaction-time"
            for axis in self._as_of_axes
        }
        if "valid-time" in declared and "valid-time" not in selected:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=(
                    f"{self._target.name} is bitemporal and requires an explicit Valid-Time "
                    "selection through valid_time= or history(VALID_TIME)"
                ),
            )
        clauses = self._temporal
        if "transaction-time" in declared and "transaction-time" not in selected:
            clauses += (_AsOfClause("transaction-time", "latest"),)
        return tuple(sorted(clauses, key=_temporal_rank))

    def _selection(self) -> MutationSelection:
        """:func:`mutation_selection`'s body, stated where the clauses live."""
        carried = [
            name
            for name, present in (
                ("order_by", bool(self._order_keys)),
                ("limit", self._limit is not None),
                ("as_of / history / as_of_range", bool(self._temporal)),
                ("include", bool(self._include)),
                ("narrow", self._narrow is not None),
            )
            if present
        ]
        if carried:
            raise QueryDefinitionError(
                code="query-not-mutation-compatible",
                message=(
                    f"{self._target.name}: a set-based write target carries nothing but a "
                    f"predicate, and this query carries {', '.join(carried)}"
                ),
            )
        return MutationSelection(target=self._target, predicate=self._predicate)


@dataclass(frozen=True, slots=True)
class LoweredFindQuery:
    """One lowering of one Find Query (:func:`lower_find_query`).

    ``target`` is the queried position's Entity Identity and ``operation`` the
    canonical ``m-predicate`` operation. Deliberately the shape a predicate
    selection already uses, because a Predicate Node is position-relative and never
    self-locating: it names attributes and relationships within a position it
    does not itself carry.

    It is not a canonical Find Query — only its Predicate Node is canonical, while its
    target is a position the connected model resolves at execution. It contains
    no model, Entity Class, class index, Snapshot feature tag, provider state,
    SQL, serialization method, or execution surface.
    """

    target: EntityIdentity
    operation: PredicateNode


@dataclass(frozen=True, slots=True)
class MutationSelection:
    """What a predicate-selected write reads off a Find Query
    (:func:`mutation_selection`).

    The ephemeral normalization of a mutation-compatible query: the position to
    write and the predicate that selects within it, and nothing else. It is
    neither exported nor serialized, and it is NOT
    ``parallax.core.unit_work.PredicateSelection`` — the write boundary builds
    that canonical value from these two facts, so a Find Query never reaches the
    unit of work, the planner, or SQL lowering.
    """

    target: EntityIdentity
    predicate: PredicateNode


def mutation_selection(query: FindQuery[Any, Any]) -> MutationSelection:
    """``query`` as a write selection, or refuse it as not mutation-compatible.

    A query becomes a write target only in its mutation-compatible form —
    carrying nothing but a target and a predicate (`python.md` §5). Every
    result-shaping, temporal, narrowing, and deep-fetch clause is refused here,
    before the write boundary builds anything from it, because each shapes a
    RESULT and a set-based write has none to shape.
    """
    return query._selection()  # pyright: ignore[reportPrivateUsage] - the seam reads the query's own clause state


def lower_find_query(query: FindQuery[Any, Any]) -> LoweredFindQuery:
    """``query``'s canonical lowering, memoized nowhere.

    The clauses are placed in the one fixed inner-to-outer order — predicate,
    root narrow, temporal wrapper(s), ordering, limit, deep fetch — so a query
    built by any permutation of the same clause calls lowers to the identical
    operation. Class-local temporal completeness is settled here from the
    target's declared axes; nothing here measures a clause against a connected
    model, whose semantic rules remain execution-preflight concerns.

    Each call builds a fresh value. A Find Query caches no lowering and no global
    memo retains one, so one execution lowers once and keeps that value locally,
    and a later execution of the same query lowers again.
    """
    return query._lower()  # pyright: ignore[reportPrivateUsage] - the seam reads the query's own clause state


def _instant(value: _Pin) -> str:
    """A canonical coordinate: ``latest`` or a UTC-normalized finite instant."""
    if isinstance(value, Latest):
        return "latest"
    return normalize_instant(value).isoformat()


def _window(value: object, axis: _DimensionName) -> tuple[str, str]:
    """``value`` as one scan window's canonical ``(start, end)`` literals.

    Takes the value a caller actually passed rather than the one the parameter
    promises, because this is the rule a dynamically composed argument meets: a
    scan window is judged as a SHAPE — exactly a built-in two-item ``tuple``,
    both endpoints finite instants, ordered — and nothing is coerced into that
    shape. A ``LATEST`` endpoint fails it by definition: Latest pins an axis,
    and an ``asOfRange`` bound is finite.
    """
    if type(value) is not tuple:
        raise QueryDefinitionError(
            code="query-clause-invalid",
            message=(
                f"{axis}= takes an exact built-in tuple; a list, a tuple subclass, and "
                f"any other iterable are refused rather than coerced (got {value!r})"
            ),
        )
    endpoints = cast("tuple[object, ...]", value)
    if len(endpoints) != 2:
        raise QueryDefinitionError(
            code="query-clause-invalid",
            message=(
                f"{axis}= takes a two-item window, the (start, end) edge points (got {value!r})"
            ),
        )
    start, end = endpoints
    if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
        raise QueryDefinitionError(
            code="query-clause-invalid",
            message=(
                f"{axis}= takes two finite instants; LATEST pins an axis rather than "
                f"scanning one, and nothing else is coerced (got {value!r})"
            ),
        )
    first, last = normalize_instant(start), normalize_instant(end)
    if first >= last:
        raise QueryDefinitionError(
            code="query-clause-invalid",
            message=(
                f"{axis}= scans the half-open window [start, end), so start < end; "
                f"{first.isoformat()} does not precede {last.isoformat()}"
            ),
        )
    return first.isoformat(), last.isoformat()


def build_find_query(
    target: EntityIdentity,
    predicates: tuple[Predicate[Any] | AllPredicate[Any], ...],
    *,
    as_of_axes: tuple[AsOfAxisMetadata, ...] = (),
) -> FindQuery[Any, Any]:
    """Build the :class:`FindQuery` conjoining ``predicates`` — ``Entity.where``'s
    whole body, kept beside the value it constructs.

    At least one predicate is required: an accidentally empty argument list is a
    mistake rather than a find-all, which ``Entity.all`` spells explicitly. That
    unfiltered spelling is the WHOLE filter or none of it, so it never combines
    with another term.
    """
    if not predicates:
        raise QueryDefinitionError(
            code="query-clause-invalid",
            message=(
                "where() requires at least one predicate; spell an explicitly unfiltered "
                "query as where(Entity.all)"
            ),
        )
    if len(predicates) > 1 and any(isinstance(p, AllPredicate) for p in predicates):
        raise QueryDefinitionError(
            code="query-expression-invalid",
            message=(
                "Entity.all is legal only as the sole where() argument; an unfiltered query "
                "is the whole filter or it is not the filter at all"
            ),
        )
    predicate = conjoin(predicates)
    assert predicate is not None  # the empty argument list is refused above
    return FindQuery(_target=target, _predicate=predicate, _as_of_axes=as_of_axes)
