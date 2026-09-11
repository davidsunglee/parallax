"""What a published rejected value costs, measured (`cost` class).

A rejected structured value crosses four seams on its way to a caller — the
codec's finding, conversion's issue input, the public issue, and the refusal that
reports it — and it is deliberately retained at the end of them. `m-snapshot-read`
*What a delivery costs* admits it into the Parallax-owned working set on one
condition: exactly ONE frozen copy of it survives, shared onward by reference,
so what a caller holds is one copy of the stored value rather than one per seam.

That is a claim about bytes, and only bytes can make it. Identity assertions
(`test_snapshot_classification.py`) prove the object a caller reads IS the object
conversion froze; they cannot see a second copy alive somewhere else — a
provider carrier still held, a per-seam detachment, a dictionary rebuilt on the
way out. The reading here is a DIFFERENCE between two evidence sizes, so
everything the publication costs that does not grow with the rejected value
cancels, and what is left is the number of copies of it that survive.

**The reference is the freezer's own product.** One arm publishes an invalid root
whose rejected value has ``width`` members; the other freezes that same value and
holds nothing else. Growing ``width`` moves both by whatever one frozen copy of
the growth costs on this interpreter, so requiring the two steps to be EQUAL says
the publication kept exactly one — no fitted bound, no tolerance, and no
arithmetic over the interpreter's own container sizing.

**The converse is measured too**, because an equality is only worth what the
instrument could have refused: each further frozen copy of one value steps this
reading by the same amount again — the containers it rebuilds, its already-frozen
members shared. Copies are therefore counted linearly, and a second copy
surviving anywhere between the codec and the record has a figure here that fails
rather than a figure that absorbs it.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable
from typing import Final

from _snapshot_graph_support import GraphFixture, invalid_record
from memory_instruments import (
    Seam,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

from parallax.conformance import vo_models as vo
from parallax.core.db_port import Row
from parallax.snapshot.materialize._evidence import freeze_evidence

_NARROW: Final = 8
_WIDE: Final = 40
"""Two member counts of one rejected object, far enough apart that a copy of the
difference is unmistakable and both are ordinary stored documents."""


def _rejected(width: int) -> dict[str, object]:
    """One stored `many` occurrence written as an object, with ``width`` members.

    A `many` stored in a kind it cannot be read as is the shape whose evidence is
    a whole subtree: the occurrence collapses to its zero value, so the hydrated
    root does not grow with ``width`` and the evidence is the only thing that
    does.
    """
    return {f"member-{index}": f"value-{index}" for index in range(width)}


def _row(width: int) -> Row:
    return {
        "id": 1,
        "name": "Ada",
        "address": {"street": "1 Park Ave", "phones": _rejected(width)},
    }


def _publication(width: int) -> Seam:
    """The published record of one invalid root, held at the sample point.

    The graph, the merge, and the builder are all transient in production and
    none is held here, so what the sample sees through the record is what a
    caller who kept one keeps.
    """

    def run(sample: Callable[[], None]) -> None:
        fixture = GraphFixture(vo.CUSTOMER_MODEL)
        record = invalid_record(fixture.materialize(fixture.node("Customer", _row(width)))[0])
        del fixture
        sample()
        assert record.data is not None

    return run


def _frozen(width: int, copies: int) -> Seam:
    """``copies`` independent freezings of one rejected value, all held.

    One copy is what a publication may keep; two is what the reading has to be
    able to refuse, and building them here rather than reasoning about them is
    what makes the refusal a measurement.
    """

    def run(sample: Callable[[], None]) -> None:
        rejected = _rejected(width)
        evidence = [freeze_evidence(rejected) for _ in range(copies)]
        del rejected
        sample()
        assert len(evidence) == copies

    return run


def _step(seam: Callable[[int], Seam]) -> int:
    """What widening the rejected value costs ``seam``.

    A difference rather than a total, so every byte the arm spends on something
    other than the rejected value — a record, a hydrated root, a frozenset, an
    interpreter's own container floor — is on both sides of it and cancels.
    """
    tracemalloc.start()
    try:
        return retained(seam(_WIDE)) - retained(seam(_NARROW))
    finally:
        tracemalloc.stop()


@in_a_child_interpreter
def test_a_published_rejected_value_costs_exactly_one_frozen_copy_of_it() -> None:
    # The whole retention claim, in one equality. What the caller holds grows by
    # exactly what one frozen copy of the growth costs, so the four seams between
    # the codec's finding and the record share one value rather than detaching,
    # rebuilding, or re-freezing it on the way — and no provider carrier of it
    # survives the publication either.
    assert _step(_publication) == _step(lambda width: _frozen(width, 1))


@in_a_child_interpreter
def test_each_further_copy_of_a_rejected_value_costs_this_reading_the_same_again() -> None:
    # The converse, so the equality above is a refusal rather than a coincidence.
    # Copies are counted linearly: a second freezing of one value costs the
    # containers it rebuilds — its members are already frozen and shared — and a
    # third costs exactly that again. So the step a publication takes fixes how
    # many copies it kept, and one is the only number that answers the first
    # reading.
    one, two, three = (_step(lambda width, at=count: _frozen(width, at)) for count in (1, 2, 3))
    assert two - one == three - two > 0


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
