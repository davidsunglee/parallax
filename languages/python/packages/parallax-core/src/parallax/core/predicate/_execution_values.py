from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.metamodel import TemporalDimension
from parallax.core.predicate._resolved import (
    DeferredKeySet,
    OccurrenceMove,
    OccurrencePath,
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedStringMatch,
    tracked_conjunction,
)

type ExecutionValueSource = (
    tuple[Literal["predicate"], int]
    | tuple[Literal["temporal"], TemporalDimension, Literal["coordinate", "start", "end"]]
    | tuple[Literal["paging"], int]
    | tuple[Literal["limit"]]
    | tuple[Literal["keys"]]
)
"""Where a template obtains one execution value when it renders.

An authored predicate operand by its canonical ordinal, a temporal selection's
bound, a continuation carrier by its term position, a page's cap, or a child
read's gathered parent keys.
"""

_CATEGORY_ORDER: dict[str, int] = {
    "predicate": 0,
    "temporal": 1,
    "paging": 2,
    "limit": 3,
    "keys": 4,
}


def source_order(source: ExecutionValueSource) -> tuple[object, ...]:
    """The canonical sort key of ``source``: its category, then its position
    within that category."""
    category, *rest = source
    return (
        _CATEGORY_ORDER[category],
        *(part.value if isinstance(part, TemporalDimension) else part for part in rest),
    )


def predicate_operands(predicate: ResolvedPredicate) -> Iterator[object]:  # noqa: C901 - exhaustive dispatcher
    """``predicate``'s authored operands in canonical order: depth first, a
    range's lower bound before its upper and a membership's values in sequence.

    The position of an operand in this order is its ordinal.
    """
    match predicate:
        case ResolvedComparison(value=value):
            yield value
        case ResolvedRange(lower=lower, upper=upper):
            yield lower
            yield upper
        case ResolvedMembership(values=values):
            if not isinstance(values, DeferredKeySet):
                yield from values
        case ResolvedStringMatch(pattern=pattern):
            yield pattern
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            for operand in operands:
                yield from predicate_operands(operand)
        case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
            yield from predicate_operands(operand)
        case (
            ResolvedNarrow(operand=operand)
            | ResolvedQuantifier(where=operand)
            | ResolvedPresence(where=operand)
        ):
            if operand is not None:
                yield from predicate_operands(operand)
        case ResolvedConstant() | ResolvedNullCheck():
            pass


@dataclass(frozen=True, slots=True)
class ExecutionValueSources:
    """The execution value each operand-bearing occurrence of one predicate
    renders from, by the occurrence's path.

    An occurrence of several operands renders them from consecutive ordinals.
    These are associations a cold template build consumes, never values.
    """

    _occurrences: Mapping[OccurrencePath, ExecutionValueSource]

    @staticmethod
    def authored(predicate: ResolvedPredicate) -> ExecutionValueSources:
        """Every authored operand of ``predicate`` at its canonical ordinal."""
        occurrences: dict[OccurrencePath, ExecutionValueSource] = {}
        _record_authored(predicate, (), occurrences, 0)
        return ExecutionValueSources(occurrences)

    @staticmethod
    def generated(source: ExecutionValueSource) -> ExecutionValueSources:
        """A generated one-operand predicate's operand rendering from ``source``."""
        return ExecutionValueSources({(): source})

    def operand(self, path: OccurrencePath, index: int = 0) -> ExecutionValueSource | None:
        """The source of operand ``index`` of the occurrence at ``path``, if it
        defers one."""
        source = self._occurrences.get(path)
        if source is None or not index:
            return source
        if source[0] != "predicate":
            raise ValueError("only an authored occurrence renders several operands")
        return ("predicate", source[1] + index)

    def within(self, path: OccurrencePath) -> ExecutionValueSources:
        """These associations re-rooted at the occurrence at ``path``."""
        depth = len(path)
        return ExecutionValueSources(
            {
                occurrence[depth:]: source
                for occurrence, source in self._occurrences.items()
                if occurrence[:depth] == path
            }
        )

    @staticmethod
    def moved(
        parts: Iterable[tuple[ExecutionValueSources, tuple[OccurrenceMove, ...]]],
    ) -> ExecutionValueSources:
        """Each part's associations where a composition moved its occurrences."""
        occurrences: dict[OccurrencePath, ExecutionValueSource] = {}
        for sources, moves in parts:
            for occurrence, source in sources._occurrences.items():
                for origin, destination in moves:
                    if occurrence[: len(origin)] == origin:
                        occurrences[(*destination, *occurrence[len(origin) :])] = source
                        break
        return ExecutionValueSources(occurrences)


NO_EXECUTION_VALUE_SOURCES: Final = ExecutionValueSources({})


def sourced_conjunction(
    *terms: tuple[ResolvedPredicate, ExecutionValueSources],
) -> tuple[ResolvedPredicate, ExecutionValueSources]:
    """The conjunction of ``terms`` with each term's associations carried to
    where the composition placed its occurrences."""
    predicate, moves = tracked_conjunction(tuple(term for term, _ in terms))
    return predicate, ExecutionValueSources.moved(
        zip((sources for _, sources in terms), moves, strict=True)
    )


def _record_authored(
    predicate: ResolvedPredicate,
    path: OccurrencePath,
    occurrences: dict[OccurrencePath, ExecutionValueSource],
    ordinal: int,
) -> int:
    """Record the operands at or beneath ``path`` from ``ordinal`` on, in the
    order :func:`predicate_operands` yields them, and return the next ordinal."""
    match predicate:
        case ResolvedComparison() | ResolvedStringMatch():
            width = 1
        case ResolvedRange():
            width = 2
        case ResolvedMembership(values=values):
            width = 0 if isinstance(values, DeferredKeySet) else len(values)
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            for index, operand in enumerate(operands):
                ordinal = _record_authored(operand, (*path, index), occurrences, ordinal)
            return ordinal
        case (
            ResolvedNot(operand=operand)
            | ResolvedGroup(operand=operand)
            | ResolvedNarrow(operand=operand)
            | ResolvedQuantifier(where=operand)
            | ResolvedPresence(where=operand)
        ):
            if operand is None:
                return ordinal
            return _record_authored(operand, (*path, 0), occurrences, ordinal)
        case ResolvedConstant() | ResolvedNullCheck():
            return ordinal
    if width:
        occurrences[path] = ("predicate", ordinal)
    return ordinal + width
