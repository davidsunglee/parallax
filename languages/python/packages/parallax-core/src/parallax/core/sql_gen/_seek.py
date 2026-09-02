"""The continuation lane of m-sql: capture cells, the order clause, and the seek.

One RESOLVER per read shape feeds all three, so the expression a page orders by,
the hidden cell that captures what that expression evaluated to, and the
comparison the next page seeks past it with cannot disagree. That is the whole
reason this lives beside the compiler rather than in
:mod:`parallax.core.continuation`: only the module that emitted the ordering
clause knows where the dialect put a NULL, and only it knows what expression a
member's placement resolved to.

What is shared is the FUNCTION rather than one resolved value. A term's subject
is resolved through a caller-supplied :data:`TermSubject` because a wrapped
table-per-concrete-subtype union names its members by the result alias every
branch projects them under rather than by any one branch's physical column, and
it is called once per emitted occurrence rather than once per term: a
document-resident member's expression carries its own path binds, binds are
positional, and each occurrence in the emitted statement must push its own. The
resolver answers the same expression every time, so agreement rests on the
resolver being a function of the member alone, not on a memoized product.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.base import INFINITY_LITERAL, TemporalBound
from parallax.core.dialect import Dialect
from parallax.core.metamodel import AttributeMetadata
from parallax.core.object_query._validated import (
    ContinuationTerm,
    ValidatedOrderTerm,
    ValidatedSeek,
)
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._predicate import MemberSubject

__all__ = [
    "LoweredTerm",
    "TermSubject",
    "capture_cells",
    "coordinate_reads",
    "lower_seek",
    "lowered_terms",
    "order_clause",
]

type TermSubject = Callable[[AttributeMetadata], MemberSubject]
"""How one read shape resolves an ordering term's member to what it compares."""

_EXHAUSTED: Final = "1 = 0"
"""The seek past a coordinate the database placed last in its own ordering."""

_CAPTURE_PREFIX: Final = "parallax_seek_"
"""The framework-owned result alias a captured coordinate arrives under.

Never a reused projected cell: proving a projection is the same expression AND
the same carrier as `ORDER BY` holds for too thin a slice to be worth the
consequence of being wrong — a coordinate that differs from what the database
ordered by makes the next seek skip or repeat roots.
"""


@dataclass(frozen=True, slots=True)
class LoweredTerm:
    """One Continuation Order term as this statement lowers it.

    ``alias`` is the hidden result cell this term's coordinate is captured
    under, allocated from the term's own position so capture, tie comparison,
    and rebinding all address the order the same way.
    """

    term: ValidatedOrderTerm
    alias: str

    @property
    def member(self) -> AttributeMetadata:
        return self.term.member


def lowered_terms(
    order_by: Sequence[ValidatedOrderTerm], reserved: Set[str] = frozenset()
) -> tuple[LoweredTerm, ...]:
    """``order_by`` with each term's capture alias allocated outside ``reserved``.

    Allocation is hygienic in the same sense a wrapped union's result aliases
    are (`m-sql`): the reservation set is every result key the read can already
    carry under its own name, so an authored physical `parallax_seek_0` keeps
    its own cell and the coordinate that would have collided with it takes the
    next free index. Two cells sharing one result key would collapse into one
    driver-row entry, and lifting the coordinate off would then either delete
    the authored member or capture its value.
    """
    terms: list[LoweredTerm] = []
    index = 0
    for term in order_by:
        while f"{_CAPTURE_PREFIX}{index}" in reserved:
            index += 1
        terms.append(LoweredTerm(term, f"{_CAPTURE_PREFIX}{index}"))
        index += 1
    return tuple(terms)


def coordinate_reads(terms: Sequence[LoweredTerm]) -> tuple[str, ...]:
    """The result keys a materializing consumer lifts this read's coordinate off."""
    return tuple(term.alias for term in terms)


def capture_cells(terms: Sequence[LoweredTerm], subject: TermSubject) -> str:
    """The hidden select-list cells that capture one coordinate per term.

    Emitted through the same ``subject`` the ``order by`` clause is, so what a
    row carries back is what the database ordered it by. Empty for a read that
    pages through nothing, which is every eager read.
    """
    return "".join(f", {subject(term.member).compared} {term.alias}" for term in terms)


def order_clause(terms: Sequence[LoweredTerm], subject: TermSubject, dialect: Dialect) -> str:
    """The whole ``order by`` clause, or the empty string for an unordered read.

    A NULLABLE key takes the dialect's Null Placement term; every other key
    renders plain, leaving the dialect's own :meth:`~Dialect.native_placement`
    deciding where a NULL would fall — which is a fact a seek past that key then
    reads back rather than assumes.
    """
    if not terms:
        return ""
    rendered = ", ".join(
        dialect.null_order(subject(term.member).compared, term.term.direction, term.term.nulls)
        if term.member.nullable
        else f"{subject(term.member).compared} {term.term.direction}"
        for term in terms
    )
    return f"order by {rendered}"


def lower_seek(
    seek: ValidatedSeek,
    terms: Sequence[LoweredTerm],
    subject: TermSubject,
    ctx: StatementBuilder,
) -> str:
    """The `where`-clause fragment admitting exactly the roots after ``seek``.

    The lexicographic expansion: one branch per tie depth, each tying with every
    term above it and stepping past its own, with the branches whose leaf admits
    nothing omitted. Ahead of them, for a NON-NULLABLE leading term over a
    non-null carrier, the redundant non-strict range that gives a planner a
    leading index range to seek — the disjunction alone offers nothing to push
    down. Where the leading term can hold a NULL, "after" is two disjoint ranges
    of the index and no single comparison covers both, so there is nothing to
    hoist.

    A coordinate the emitted ordering placed LAST leaves every branch vacuous,
    and the seek then admits nothing — the ordinary way a delivery that ended on
    the final root discovers there is no more.

    Every comparison is emitted from the same ``subject`` the order clause was,
    and every leaf is measured against the placement this statement KNOWS it
    emitted rather than one it assumes.

    Binds append in emitted order, after whatever the caller's own predicate has
    already pushed.
    """
    if len(seek.terms) != len(terms):
        raise SqlGenError(
            f"a seek over {len(seek.terms)} term(s) cannot be lowered against "
            f"{len(terms)} ordering term(s)"
        )
    carriers = seek.coordinate.carriers
    if len(carriers) != len(terms):
        raise SqlGenError(
            f"a coordinate carrying {len(carriers)} value(s) cannot be lowered against "
            f"{len(terms)} ordering term(s)"
        )
    for term, lowered in zip(seek.terms, terms, strict=True):
        _refuse_a_crossed_term(term, lowered)
    dialect = ctx.dialect
    lead = seek.terms[0]
    parts: list[str] = []
    if len(terms) > 1 and not lead.nullable and carriers[0] is not None:
        comparator = ">=" if lead.direction == "asc" else "<="
        parts.append(_compared(terms[0], subject, carriers[0], comparator, ctx))
    branches: list[str] = []
    for depth, term in enumerate(seek.terms):
        if carriers[depth] is None and _placement(term, dialect) == "last":
            continue
        conjuncts = [_ties_with(terms[at], subject, carriers[at], ctx) for at in range(depth)]
        after = _after(term, terms[depth], subject, carriers[depth], ctx)
        if not conjuncts:
            branches.append(after)
            continue
        conjuncts.append(f"({after})" if _spans_a_disjunction(term, carriers[depth]) else after)
        branches.append(f"({' and '.join(conjuncts)})")
    if not branches:
        # The database placed this coordinate last in its own ordering, so
        # nothing follows it. Emitted rather than skipped: the page is an
        # ordinary statement returning no root, which is how the delivery
        # discovers that it is exhausted.
        return _EXHAUSTED
    disjunction = " or ".join(branches)
    # A lone branch parenthesizes itself where it needs to — it is either one
    # comparison or a conjunction this loop already grouped.
    parts.append(f"({disjunction})" if len(branches) > 1 else disjunction)
    return " and ".join(parts)


def _refuse_a_crossed_term(term: ContinuationTerm, lowered: LoweredTerm) -> None:
    """Refuse a seek whose terms are not the ordering clause's own.

    The two arrive from one Continuation Order and are aligned positionally, so
    a disagreement means the page was composed against a different order than it
    is being lowered under — which would seek past a coordinate the statement
    never evaluated.

    Every field the two spellings share is compared, not the member alone: the
    order clause reads direction, Null Placement, and nullability off
    :class:`LoweredTerm`, while every branch of the seek reads them off
    :class:`~parallax.core.object_query._validated.ContinuationTerm`. Agreeing on
    the member while disagreeing on any of the three would emit an opposite
    comparator, or measure a branch against a placement the clause did not
    take.
    """
    if (
        term.identity != lowered.member.identity
        or term.direction != lowered.term.direction
        or term.nulls != lowered.term.nulls
        or term.nullable != lowered.member.nullable
    ):
        raise SqlGenError(
            f"the seek's term {term.identity.name!r} "
            f"({term.direction}, nulls {term.nulls}, "
            f"{'nullable' if term.nullable else 'non-nullable'}) is not the ordering term "
            f"{lowered.member.identity.name!r} "
            f"({lowered.term.direction}, nulls {lowered.term.nulls}, "
            f"{'nullable' if lowered.member.nullable else 'non-nullable'}) "
            f"at the same position"
        )


def _placement(term: ContinuationTerm, dialect: Dialect) -> Literal["first", "last"]:
    """Where the emitted clause actually placed this term's NULLs.

    A nullable key lowers through the dialect's Null Placement seam, so its
    authored placement is the effective one; every other key lowers to the plain
    term, leaving the dialect's own convention in force.
    """
    return term.nulls if term.nullable else dialect.native_placement(term.direction)


def _spans_a_disjunction(term: ContinuationTerm, carrier: object) -> bool:
    """Whether "after this coordinate" reaches this term's nulls as well."""
    return term.nullable and carrier is not None and term.nulls == "last"


def _after(
    term: ContinuationTerm,
    lowered: LoweredTerm,
    subject: TermSubject,
    carrier: object,
    ctx: StatementBuilder,
) -> str:
    """Everything ``lowered`` orders strictly after ``carrier``.

    Measured in the term's OWN ordering: a descending term reverses the
    comparison, and where the emitted clause placed nulls first, a null carrier
    is followed by every non-null. The ``or is null`` arm is guarded on declared
    nullability rather than applied everywhere — widening it would put a
    disjunction on the primary-key term of every seek for a value conforming
    storage cannot hold.
    """
    if carrier is None:
        return f"{subject(lowered.member).extraction} is not null"
    strict = ">" if term.direction == "asc" else "<"
    comparison = _compared(lowered, subject, carrier, strict, ctx)
    if not _spans_a_disjunction(term, carrier):
        return comparison
    return f"{comparison} or {subject(lowered.member).extraction} is null"


def _ties_with(
    lowered: LoweredTerm, subject: TermSubject, carrier: object, ctx: StatementBuilder
) -> str:
    if carrier is None:
        return f"{subject(lowered.member).extraction} is null"
    return _compared(lowered, subject, carrier, "=", ctx)


def _compared(
    lowered: LoweredTerm,
    subject: TermSubject,
    carrier: object,
    comparator: str,
    ctx: StatementBuilder,
) -> str:
    """One comparison of ``lowered``'s expression against its own carrier.

    The carrier is bound in the form that expression compares, which is the
    split an authored predicate over the same member already takes: a direct
    Column compares in the engine's own column type, a document extraction that
    casts compares in the declared type, and one that does not — like a wrapped
    union's already-encoded `bytes` result key — compares as the codec's own
    text. Which of the two a resolved subject is stands on the subject itself,
    so a shape whose expression is neither a bare Column nor an extraction still
    rebinds in the form it actually compares.

    An open temporal bound is the one carrier that is neither: the database
    answers it as the `m-core` sentinel, which is a member of no declared value
    space, so it crosses as a framework bind reported by the canonical
    `infinity` literal — the treatment a written temporal row already takes.

    Nothing else is re-derived. A carrier already IS what its own expression
    evaluated to, so the split decides which BIND ROLE the value crosses under
    rather than what to convert it into. Converting would be the one place a
    coordinate stopped being the database's own answer.
    """
    resolved = subject(lowered.member)
    if isinstance(carrier, TemporalBound):
        ctx.bind_framework(carrier, wire_value=INFINITY_LITERAL)
    elif resolved.text_compared:
        ctx.bind_comparison_text(carrier, resolved.type)
    else:
        ctx.bind_managed(carrier, resolved.type)
    return f"{resolved.compared} {comparator} ?"
