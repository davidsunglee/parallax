"""Pure streamed-Page request and verdict policy.

A delivery asks :class:`PagePlan` how many roots its next statement may read,
then gives :func:`page_decision` only the evaluated coordinates. The policy owns
lookahead, limit, tie, and maximal-prefix arithmetic; SQL compilation, execution,
Page assembly, and continuation retention belong to
:class:`~parallax.snapshot.handle._materialization.Materializer`.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.continuation import ContinuationPlan
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query._validated import ContinuationCoordinate

__all__ = [
    "At",
    "PagePlan",
    "PageRequest",
    "PageVerdict",
    "TieFound",
    "page_decision",
]


@dataclass(frozen=True, slots=True)
class PageRequest:
    """How many roots one page asks for, and how its answer is to be read.

    ``lookahead`` is the whole difference between the two kinds of page. With
    one, ``size`` is a root MORE than the page may deliver, so a full result
    means "one more root exists" and a short one proves exhaustion outright. On
    a final page there is no such root to ask for, and a full result proves
    nothing about what follows — the authored limit settles it instead.

    ``emitted`` travels with them because a tie's ordinal counts from the start
    of the delivery rather than from the start of this page.
    """

    size: int
    lookahead: bool
    emitted: int


@dataclass(frozen=True, slots=True)
class TieFound:
    """Two adjacent roots one page's statement evaluated to ONE coordinate.

    The Continuation Order is total over storage the model describes, so this is
    storage that has lost a constraint the order rests on. Everything the
    refusal reports is settled here, where it was discovered: ``terms`` is the
    order that turned out not to be total, ``ordinal`` counts the first
    undeliverable root from the start of the delivery, and ``coordinate`` is the
    inert diagnostic copy of where it stood — never a coordinate, which is
    pagination authority.
    """

    terms: tuple[AttributeIdentity, ...]
    ordinal: int
    coordinate: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class PageVerdict:
    """Which of a page's roots survive, and what the delivery does after them.

    ``keep`` is the count taken from the FRONT of what the statement returned:
    the discarded lookahead root and every root from a tie onwards are the same
    kind of thing to everything downstream — read, never converted.
    """

    keep: int
    exhausted: bool
    tie: TieFound | None


@dataclass(frozen=True, slots=True)
class PagePlan:
    """How one delivery pages: its page nodes and the two counts bounding them.

    All three are fixed for a delivery's whole life and mean nothing apart —
    ``batch_size`` is how many roots a page may DELIVER — what its statement
    asks for is :meth:`page_request`'s answer — ``limit`` is the authored
    cap the delivery may never read past, and ``plan`` is what turns either into
    a node. Carrying them as one value is what leaves the stream holding a
    position and nothing else.
    """

    plan: ContinuationPlan
    batch_size: int
    limit: int | None

    def page_request(self, emitted: int) -> PageRequest:
        """What the page after ``emitted`` asks the database for.

        A page reads one root PAST its batch, which is what proves exhaustion
        without a terminal statement that returns nothing and what puts the
        first root of the next page inside this page's own tie scan — a tie
        with it would otherwise be stepped straight over by a strict seek.

        An authored limit is a hard database-read and locking boundary rather
        than a filter applied afterwards, so the final page it caps asks for
        exactly what is left of it and reads no excluded root merely to inspect
        a boundary tie. The tie there goes undetected, and no later seek exists
        that could skip it.
        """
        if self.limit is None or self.limit - emitted > self.batch_size:
            return PageRequest(size=self.batch_size + 1, lookahead=True, emitted=emitted)
        return PageRequest(size=self.limit - emitted, lookahead=False, emitted=emitted)


@dataclass(frozen=True, slots=True)
class At:
    """Where a delivery stands: what it last delivered, and how much.

    ``coordinate`` is absent on the first page alone. It is the coordinate the
    DATABASE evaluated for the last root the previous page kept, which is what
    lets a delivery resume past a root whose stored data contradicted the model.
    """

    coordinate: ContinuationCoordinate | None
    emitted: int


def page_decision(
    request: PageRequest,
    terms: tuple[AttributeIdentity, ...],
    coordinates: tuple[ContinuationCoordinate, ...],
) -> PageVerdict:
    """Which of the roots a page returned it may deliver, and what follows them.

    A scan over the coordinates and nothing else. Sameness is the coordinate's
    own rule — comparing carriers here would put a provider judgment where no
    provider knowledge is — and the scan covers the lookahead root, which is
    what makes a tie that spans a page boundary reachable at all: resuming from
    a kept root that ties with the root after it emits a strict comparison
    stepping over its twin.

    A tie at ``index`` means the tied group starts at ``index - 1``, so the kept
    prefix is the maximal strictly ordered one and the coordinate after it is
    the first undeliverable root. Keeping nothing is ordinary: the page
    publishes no root and the delivery refuses immediately.

    ``terms`` is the Continuation Order those coordinates were evaluated
    against, positionally, and is reported by a tie alone.
    """
    for index in range(1, len(coordinates)):
        if coordinates[index] == coordinates[index - 1]:
            keep = index - 1
            return PageVerdict(
                keep=keep,
                exhausted=True,
                tie=TieFound(
                    terms=terms,
                    ordinal=request.emitted + keep,
                    coordinate=coordinates[keep].snapshot(),
                ),
            )
    if request.lookahead and len(coordinates) == request.size:
        return PageVerdict(keep=request.size - 1, exhausted=False, tie=None)
    return PageVerdict(keep=len(coordinates), exhausted=True, tie=None)
