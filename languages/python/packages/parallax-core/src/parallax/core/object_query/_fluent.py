"""The typed Object Query authoring surface (support scope, query half).

``Entity.where(first, *rest)`` builds a side-effect-free :class:`ObjectQuery` —
the big-AND of its filter criteria, or the explicitly unfiltered ``Entity.all``.
``.narrow`` / ``.as_of`` / ``.as_of_range`` / ``.history`` / ``.order_by`` /
``.limit`` / ``.include`` fill the remaining clauses, each returning a new value
and leaving its receiver unchanged.

An Object Query holds the CANONICAL query value the whole time: a clause method
rebuilds :class:`~parallax.core.object_query.ObjectQueryNode` with one more
clause filled, and no clause nests inside another, so clause invocation order
cannot reach the wire. Permuting otherwise valid calls therefore produces the
identical canonical query by construction rather than by discipline.

Authoring reaches no model. Every rule stated here is class-local — clause
arity, single-shot clauses, the target's own declared temporal axes, literal
shapes — and every rule that needs a whole model is stated once at execution
preflight, which is also what covers the wire path and any untyped caller. The
one class-local rule that cannot be settled while clauses are still being added
is the target's own temporal completeness, which :func:`object_query_node`
settles when the query is read.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from parallax.core.base import TIMESTAMP, normalize_instant
from parallax.core.metamodel import AsOfAxisMetadata
from parallax.core.metamodel import TemporalDimension as AxisKind
from parallax.core.object_query._canonical import object_query, subtype_spelling
from parallax.core.object_query._nodes import (
    TX_TIME,
    VALID_TIME,
    AsOf,
    AsOfRange,
    History,
    IncludePath,
    Latest,
    MutationSelection,
    ObjectQueryNode,
    TemporalDimension,
    TemporalDimensionConstant,
    TemporalSelection,
)
from parallax.core.predicate import QueryDefinitionError, canonical_subtype_selection
from parallax.core.wire import encode_wire

if TYPE_CHECKING:
    # Annotation-only, and deliberately so: the Entity frontend's descriptors are
    # what a caller writes a clause argument with, while this module reads only
    # the canonical values they carry. Keeping the reach static is what lets the
    # frontend re-export this surface without an import cycle.
    from parallax.core.entity._entity import Entity
    from parallax.core.entity._expressions import RelationshipPath, SortKey

__all__ = [
    "ObjectQuery",
    "mutation_selection",
    "object_query_node",
]


class _Unset:
    """Sentinel for an axis a temporal clause did not pass (distinct from ``LATEST``)."""

    __slots__ = ()


_UNSET = _Unset()

# One dimension pin: a finite instant (a tz-aware ``datetime``) or the explicit
# Latest sentinel; a range pin is a ``(start, end)`` instant pair.
_Pin = dt.datetime | Latest
_Window = tuple[dt.datetime, dt.datetime]
_DimensionName = Literal["valid_time", "tx_time"]


@dataclass(frozen=True, slots=True, eq=False)
class ObjectQuery[E, S]:
    """An immutable, side-effect-free query over one target Entity.

    ``E`` is the Entity QUERIED and ``S`` the Entity the result RETURNS, which
    ``narrow`` — and only ``narrow`` — moves. The split is what makes
    ``include`` and ``order_by`` measure different things: an include path's
    source is legal against the queried position, while a sort key addresses the
    rows the query actually returns.

    Every field is private authoring state. An Object Query exposes no execution,
    serialization, canonical-query inspection, or refinement ``.where(...)``,
    carries no Snapshot feature tags and no model, and defines no structural
    equality or semantic hash — two independently authored queries carrying one
    canonical node are still two objects, and conformance code compares canonical
    nodes through :func:`object_query_node` instead. ``bool(query)`` raises: an
    Object Query has no pre-execution empty/nonempty state.

    ``Entity.where(...)`` is the sole public constructor; direct construction is
    a first-party spelling with no supported contract.
    """

    _node: ObjectQueryNode
    # The target family's declared temporal axes, captured at ``Entity.where`` so
    # the dimension-keyed temporal clauses validate against them; empty for a
    # non-temporal Entity (every temporal clause then raises).
    _as_of_axes: tuple[AsOfAxisMetadata, ...] = ()

    def include(self, *paths: RelationshipPath[E, Any]) -> ObjectQuery[E, S]:
        """Deep-fetch one or more relationship paths (python.md §2):
        ``Order.where(...).include(Order.items, Order.tags)``. One path grammar
        shared with predicates; a longer path implies its intermediates.
        Accumulates across calls (not single-shot) into the canonical include
        set: sorted, deduplicated, and stripped of exact prefixes a retained
        extension already materializes.

        Legality is measured against the QUERIED Entity, never against the
        narrowed result: a result narrowing constrains which objects come back,
        not which sources a path may start from, so a path rooted at a subtype
        the narrowing excludes is legal and populates nowhere. Every hop's own
        legality — an undeclared relationship, a value-object segment, an illegal
        hop narrow — is a whole-model question and is settled at execution
        preflight.

        A path seeded through a subtype (``include(Dog.owner, Cat.owner)``)
        carries that class's source guard, so the two are one relationship
        fetched for disjoint sets of queried objects — never two relationships,
        and never two views (spec §3).
        """
        if not paths:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="include requires at least one path"
            )
        added = tuple(
            IncludePath(segments=path.segments, applies_to=self._source_guard(path.source))
            for path in paths
        )
        return self._with(includes=self._node.includes + added)

    def order_by(self, *keys: SortKey[S]) -> ObjectQuery[E, S]:
        """Order the result by one or more Sort Keys (``Attr.asc()`` /
        ``Attr.desc()``), in precedence order. Accumulates across calls.

        A Sort Key carries the position it was built from and the canonical
        ordering term it holds; the query keeps the term alone, because the
        ordered rows' position is a property of the query rather than of a key.

        Keys are measured against the RESULT, so a subtype's key requires the
        result narrowing that establishes its scope first — and that ordering
        rule is STATIC ONLY. Clause order does not reach the wire: ordering
        before narrowing and narrowing before ordering build one canonical query,
        so no model-aware rule could refuse the first and accept the second. What
        refuses it is this parameter, against the result the receiver carries at
        the moment the call is written.

        One resolved Attribute Identity may occur only once across the whole
        accumulated ordering, whichever direction each occurrence carries: a
        second ordering term over one attribute states nothing the first did not
        and is refused rather than silently dropped.
        """
        if not keys:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="order_by requires at least one key"
            )
        accumulated = self._node.order_by + tuple(key.key for key in keys)
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
        return self._with(order_by=accumulated)

    def limit(self, count: int) -> ObjectQuery[E, S]:
        """Cap the result row count at a positive built-in ``int``. Single-shot:
        a second call is refused rather than replacing or tightening the first,
        so alternate limits derive from the same unbounded base.

        ``bool``, zero, negative values, and anything that would need coercion
        are refused rather than coerced — ``True`` is not the limit 1.
        """
        if self._node.limit is not None:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message="a limit clause is single-shot; derive from the unbounded base",
            )
        if type(count) is not int or count < 1:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=f"limit requires a positive built-in int (got {count!r})",
            )
        return self._with(limit=count)

    # Each arity overload's parameters are positional-only and never read, so
    # they are spelled with a leading underscore: the arity is the whole content
    # of the declaration, and the names cannot be written by a caller.
    @overload
    def narrow[N: Entity](self, _one: type[N], /) -> ObjectQuery[E, N]: ...
    @overload
    def narrow[N: Entity](self, _one: type[N], _two: type[N], /) -> ObjectQuery[E, N]: ...
    @overload
    def narrow[N: Entity](
        self, _one: type[N], _two: type[N], _three: type[N], /
    ) -> ObjectQuery[E, N]: ...
    @overload
    def narrow(self, *subtypes: type[Entity]) -> ObjectQuery[E, S]: ...
    def narrow(self, *subtypes: type[Entity]) -> ObjectQuery[E, Any]:
        """The whole-result subtype-narrowing clause (python.md §2):
        ``Animal.where(...).narrow(Dog, Cat)``. A PURE result-set narrowing that
        fills the query's own ``narrowTo`` clause — single-shot, like each
        temporal dimension. ``Entity.where(Entity.narrow(Dog, where=...))``
        builds the identical canonical query: a narrowing that is the WHOLE
        filter narrows the result, and that is the spelling a checker agrees
        with when the predicate addresses the narrowed subtype, because it
        narrows before the predicate is measured.

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
        if self._node.narrow_to is not None:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message="a narrow clause is single-shot; derive from the un-narrowed base",
            )
        if not subtypes:
            raise QueryDefinitionError(
                code="query-clause-invalid", message="narrow requires at least one subtype"
            )
        alternatives = tuple(subtype_spelling(subtype) for subtype in subtypes)
        if len(set(alternatives)) != len(alternatives):
            raise QueryDefinitionError(
                code="query-path-invalid",
                message="narrow alternatives must not repeat the same subtype",
            )
        return self._with(narrow_to=canonical_subtype_selection(alternatives))

    def as_of(
        self,
        *,
        valid_time: _Pin | _Unset = _UNSET,
        tx_time: _Pin | _Unset = _UNSET,
    ) -> ObjectQuery[E, S]:
        """Pin one or both temporal dimensions to an instant (or the ``LATEST`` sentinel).

        Dimension-keyed and single-shot per dimension (``m-temporal-read``): an
        omitted Transaction-Time dimension normalizes to an explicit
        ``asOf latest`` selection when the query is read, while Valid Time must
        be selected for a Bitemporal query. A naive ``datetime`` is rejected here.
        """
        selections: dict[TemporalDimension, TemporalSelection] = {}
        if not isinstance(tx_time, _Unset):
            selections[self._dimension("tx_time")] = AsOf(_instant(tx_time))
        if not isinstance(valid_time, _Unset):
            selections[self._dimension("valid_time")] = AsOf(_instant(valid_time))
        return self._with_temporal(selections)

    def as_of_range(
        self,
        *,
        valid_time: _Window | _Unset = _UNSET,
        tx_time: _Window | _Unset = _UNSET,
    ) -> ObjectQuery[E, S]:
        """Scan one or both dimensions across a half-open ``[from, to)`` window (edge points).

        Each window is an exact built-in two-item ``tuple`` of finite instants
        ordered ``start < end``. A list, a ``tuple`` subclass, any other
        iterable, an endpoint that would need coercion, a :data:`LATEST`
        endpoint, and an equal or reversed window are each refused HERE — an
        ``asOfRange``'s bounds are canonically finite and ordered
        (``object-query.schema.json``'s ``finiteTemporalInstant``,
        `m-temporal-read` "scans every milestone whose interval overlaps
        ``[start, end)``"), so the clause is never built carrying anything else
        and no scan reaches SQL with a reversed window or a ``latest`` bind.
        """
        selections: dict[TemporalDimension, TemporalSelection] = {}
        if not isinstance(tx_time, _Unset):
            start, end = _window(tx_time, "tx_time")
            selections[self._dimension("tx_time")] = AsOfRange(start=start, end=end)
        if not isinstance(valid_time, _Unset):
            start, end = _window(valid_time, "valid_time")
            selections[self._dimension("valid_time")] = AsOfRange(start=start, end=end)
        return self._with_temporal(selections)

    def history(self, dimension: TemporalDimensionConstant) -> ObjectQuery[E, S]:
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
        return self._with_temporal({self._dimension(name): History()})

    def _source_guard(self, source: str | None) -> tuple[str, ...] | None:
        """The source guard an include path seeded through ``source`` authors.

        A guard is what makes a path start from fewer than every queried object,
        so it is the ACCESS SOURCE — the Entity the first hop was reached
        through — measured against this query's own queried position, never
        against the relationship's declaring Entity. That distinction is the
        whole point of keeping the two identities apart: ``Dog.doghouse``,
        declared on ``Dog``, and ``Dog.owner``, inherited from ``Animal``, guard
        an ``Animal`` query identically. Reaching the first hop through the
        queried position itself guards nothing, so it authors no selection at all
        rather than one resolving to the whole position.
        """
        if source is None or source == self._node.target.canonical:
            return None
        return (source,)

    def _with_temporal(
        self, selections: Mapping[TemporalDimension, TemporalSelection]
    ) -> ObjectQuery[E, S]:
        if not selections:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=(
                    "a temporal clause requires at least one dimension (valid_time= / tx_time=)"
                ),
            )
        for dimension in selections:
            if dimension in self._node.temporal:
                raise QueryDefinitionError(
                    code="query-clause-invalid",
                    message=(
                        f"the {dimension} dimension is single-shot; derive from a "
                        "query that has not selected that dimension"
                    ),
                )
        return self._with(temporal={**self._node.temporal, **selections})

    def _with(self, **clauses: object) -> ObjectQuery[E, Any]:
        """Rebuild this query's canonical node with ``clauses`` replaced."""
        node = self._node
        return replace(
            self,
            _node=object_query(
                node.target,
                node.predicate,
                narrow_to=cast("Any", clauses.get("narrow_to", node.narrow_to)),
                temporal=cast("Any", clauses.get("temporal", node.temporal)),
                order_by=cast("Any", clauses.get("order_by", node.order_by)),
                limit=cast("Any", clauses.get("limit", node.limit)),
                includes=cast("Any", clauses.get("includes", node.includes)),
            ),
        )

    def _dimension(self, name: _DimensionName) -> TemporalDimension:
        """The canonical wire dimension for the developer-surface coordinate
        spelling ``name`` (the snake→camel boundary: ``tx_time`` maps to
        ``transaction-time``), validated against the target's declared axes."""
        declared = AxisKind.VALID_TIME if name == "valid_time" else AxisKind.TRANSACTION_TIME
        dimension: TemporalDimension = "valid-time" if name == "valid_time" else "transaction-time"
        for axis in self._as_of_axes:
            if axis.dimension is declared:
                return dimension
        detail = (
            "declares no temporal dimension"
            if not self._as_of_axes
            else f"declares no {name} dimension"
        )
        raise QueryDefinitionError(
            code="query-clause-invalid", message=f"{self._node.target.name} {detail}"
        )

    def __bool__(self) -> bool:
        raise TypeError(
            "an Object Query has no truth value before it runs; execute it through "
            "Database.find / Transaction.find and inspect the Snapshot it returns"
        )

    def _canonical(self) -> ObjectQueryNode:
        """:func:`object_query_node`'s body, stated where the clauses live."""
        declared = {
            "valid-time" if axis.dimension is AxisKind.VALID_TIME else "transaction-time"
            for axis in self._as_of_axes
        }
        selected = self._node.temporal
        if "valid-time" in declared and "valid-time" not in selected:
            raise QueryDefinitionError(
                code="query-clause-invalid",
                message=(
                    f"{self._node.target.name} is bitemporal and requires an explicit "
                    "Valid-Time selection through valid_time= or history(VALID_TIME)"
                ),
            )
        if "transaction-time" in declared and "transaction-time" not in selected:
            completed: dict[TemporalDimension, TemporalSelection] = {
                **selected,
                "transaction-time": AsOf("latest"),
            }
            return self._with(temporal=completed)._node
        return self._node

    def _selection(self) -> MutationSelection:
        """:func:`mutation_selection`'s body, stated where the clauses live."""
        node = self._node
        carried = [
            name
            for name, present in (
                ("order_by", bool(node.order_by)),
                ("limit", node.limit is not None),
                ("as_of / history / as_of_range", bool(node.temporal)),
                ("include", bool(node.includes)),
                ("narrow", node.narrow_to is not None),
            )
            if present
        ]
        if carried:
            raise QueryDefinitionError(
                code="query-not-mutation-compatible",
                message=(
                    f"{node.target.name}: a set-based write target carries nothing but a "
                    f"predicate, and this query carries {', '.join(carried)}"
                ),
            )
        return MutationSelection(target=node.target, predicate=node.predicate)


def mutation_selection(query: ObjectQuery[Any, Any]) -> MutationSelection:
    """``query`` as a write selection, or refuse it as not mutation-compatible.

    A query becomes a write target only in its mutation-compatible form —
    carrying nothing but a target and a predicate (`python.md` §5). Every
    result-shaping, temporal, narrowing, and Includes clause is refused here,
    before the write boundary builds anything from it, because each shapes a
    RESULT and a set-based write has none to shape.
    """
    return query._selection()  # pyright: ignore[reportPrivateUsage] - the seam reads the query's own clause state


def object_query_node(query: ObjectQuery[Any, Any]) -> ObjectQueryNode:
    """``query``'s canonical Object Query, memoized nowhere.

    An Object Query already holds its canonical node; what this settles is the
    one class-local rule no clause call could settle while further clauses were
    still legal — the target's own temporal completeness. An omitted
    Transaction-Time selection becomes the explicit ``asOf latest`` the canonical
    document always states, and an omitted Valid-Time selection on a Bitemporal
    target raises. Nothing here changes representation: there is no wrapper tree
    to build and no clause to reorder.

    Each call answers a fresh value. An Object Query caches nothing and no global
    memo retains one, so one execution reads once and keeps that value locally.
    """
    return query._canonical()  # pyright: ignore[reportPrivateUsage] - the seam reads the query's own clause state


def _instant(value: _Pin) -> str:
    """A canonical coordinate: ``latest`` or a UTC-normalized finite instant."""
    if isinstance(value, Latest):
        return "latest"
    return cast("str", encode_wire(TIMESTAMP, normalize_instant(value)))


def _window(value: object, axis: _DimensionName) -> tuple[str, str]:
    """``value`` as one scan window's canonical ``(start, end)`` literals.

    Takes the value a caller actually passed rather than the one the parameter
    promises, because this is the rule a dynamically composed argument meets: a
    scan window is judged as a SHAPE — exactly a built-in two-item ``tuple``,
    both endpoints finite instants, ordered — and nothing is coerced into that
    shape. A ``LATEST`` endpoint fails it by definition: Latest pins a dimension,
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
                f"{axis}= takes two finite instants; LATEST pins a dimension rather than "
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
    return (
        cast("str", encode_wire(TIMESTAMP, first)),
        cast("str", encode_wire(TIMESTAMP, last)),
    )
