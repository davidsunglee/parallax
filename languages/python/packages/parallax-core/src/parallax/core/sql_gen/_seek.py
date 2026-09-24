from __future__ import annotations

from collections.abc import Callable, Sequence, Set
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.base import INFINITY_LITERAL, TemporalBound
from parallax.core.dialect import Dialect
from parallax.core.metamodel import AttributeMetadata
from parallax.core.object_query._validated import (
    ContinuationCoordinate,
    ContinuationTerm,
    ValidatedOrderTerm,
    ValidatedSeek,
)
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._predicate import MemberSubject

__all__ = [
    "LoweredTerm",
    "NullPattern",
    "TermSubject",
    "capture_cells",
    "coordinate_reads",
    "emits_null_tail",
    "lower_seek",
    "lowered_terms",
    "null_pattern",
    "order_clause",
]

type TermSubject = Callable[[AttributeMetadata], MemberSubject]
"""How one read shape resolves an ordering term's member to what it compares."""

type NullPattern = tuple[bool, ...]
"""Which carriers of one continuation coordinate are NULL, in term order."""

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
    under. Aliases are allocated in term order but not at the term's own index —
    :func:`lowered_terms` skips a reserved spelling — so capture, tie
    comparison, and rebinding all address the order through the alias the term
    was allocated rather than through its position.
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


def null_pattern(coordinate: ContinuationCoordinate) -> NullPattern:
    """The reusable statement-template shape of one coordinate."""
    return tuple(carrier is None for carrier in coordinate.carriers)


def emits_null_tail(seek: ValidatedSeek, dialect: Dialect, *, leading_resident: bool) -> bool:
    """Whether this continuing page needs a second arm for the leading NULL tail."""
    return (
        bool(seek.terms)
        and bool(seek.coordinate.carriers)
        and seek.coordinate.carriers[0] is not None
        and not leading_resident
        and _placement(seek.terms[0], dialect) == "last"
    )


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
    *,
    leading_resident: bool,
) -> str:
    """The `where`-clause fragment admitting the roots after ``seek``.

    The lexicographic expansion: one branch per tie depth, each tying with every
    term above it and stepping past its own, with the branches whose leaf admits
    nothing omitted. Every leaf is measured against the placement this statement
    KNOWS it emitted (:func:`_placement`) rather than against declared
    nullability, so a term whose NULLs the clause placed after this coordinate
    admits them.

    Ahead of the branches, :func:`_hoists_a_leading_range` may add a redundant
    non-strict range for the planner. Where that range excludes a NULL region
    ordered after the coordinate, the statement assembler emits the disjoint
    NULL-tail arm described by :func:`emits_null_tail`.
    ``leading_resident`` is the caller's Member Placement answer for the leading
    term, which that decision needs and no resolution here may ask for: resolving
    a subject binds an extraction's path segments, so a probe would push binds no
    text consumes.

    A coordinate the emitted ordering placed LAST leaves every branch vacuous,
    and the seek then admits nothing — the ordinary way a delivery that ended on
    the final root discovers there is no more.

    Every comparison is emitted from the same ``subject`` the order clause was.

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
    parts: list[str] = []
    if _hoists_a_leading_range(seek.terms, carriers, resident=leading_resident):
        lead = seek.terms[0]
        comparator = ">=" if lead.direction == "asc" else "<="
        parts.append(_compared(terms[0], subject, carriers[0], comparator, ctx))
    branches: list[str] = []
    loose = False
    for depth, term in enumerate(seek.terms):
        if carriers[depth] is None and _placement(term, dialect) == "last":
            continue
        conjuncts = [_ties_with(terms[at], subject, carriers[at], ctx) for at in range(depth)]
        after = _after(term, terms[depth], subject, carriers[depth], ctx)
        spans = _spans_a_disjunction(term, carriers[depth], dialect)
        if not conjuncts:
            branches.append(after)
            loose = loose or spans
            continue
        conjuncts.append(f"({after})" if spans else after)
        branches.append(f"({' and '.join(conjuncts)})")
    if not branches:
        # The database placed this coordinate last in its own ordering, so
        # nothing follows it. Emitted rather than skipped: the page is an
        # ordinary statement returning no root, which is how the delivery
        # discovers that it is exhausted.
        return _EXHAUSTED
    disjunction = " or ".join(branches)
    # Grouped wherever the fragment carries a top-level `or`, because the caller
    # conjoins it with `and`, which binds tighter. A LONE branch is not
    # automatically atomic: at depth 0 it is `after(0)` ungrouped, and `after`
    # is itself a disjunction wherever the emitted clause placed this term's
    # NULLs after the coordinate.
    parts.append(f"({disjunction})" if len(branches) > 1 or loose else disjunction)
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


def _spans_a_disjunction(term: ContinuationTerm, carrier: object, dialect: Dialect) -> bool:
    """Whether "after this coordinate" reaches this term's NULLs as well.

    Asks :func:`_placement` rather than re-deriving the answer from declared
    nullability. Where the emitted clause put a NULL is one question with one
    answer in this module, and a stored NULL under a `NOT NULL` constraint that
    is gone lands exactly where that answer says — so the branch admitting it is
    the branch this decides.
    """
    return carrier is not None and _placement(term, dialect) == "last"


def _hoists_a_leading_range(
    terms: Sequence[ContinuationTerm], carriers: Sequence[object], *, resident: bool
) -> bool:
    """Whether to emit the redundant leading range a planner can seek on.

    Over a DIRECT Column the non-strict comparison is the range a planner can
    seek on. It is useful for one or many terms and for nullable and non-nullable
    declarations alike, so only a non-null carrier and direct placement guard it.
    When it excludes NULLs ordered after the coordinate, the compiler preserves
    completeness with a separate NULL-tail arm instead of widening this range.

    A DOCUMENT-RESIDENT term takes the opposite answer: its extraction goes NULL
    for ordinary invalid stored data, while a range over an extraction offers no
    index range to buy. The branch tree's own placement answer therefore admits
    those roots without a hoist or a second arm.
    """
    return bool(terms) and not resident and carriers[0] is not None


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
    is followed by every non-null. The ``or is null`` arm follows the emitted
    placement alone, so a term whose NULLs the clause put after this coordinate
    admits them here whether or not the model says it can hold one — which is
    what a delivery over non-conforming storage needs, since a `NOT NULL`
    constraint that is gone leaves a NULL the ordering still ranks.
    """
    if carrier is None:
        return f"{subject(lowered.member).extraction} is not null"
    strict = ">" if term.direction == "asc" else "<"
    comparison = _compared(lowered, subject, carrier, strict, ctx)
    if not _spans_a_disjunction(term, carrier, ctx.dialect):
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
