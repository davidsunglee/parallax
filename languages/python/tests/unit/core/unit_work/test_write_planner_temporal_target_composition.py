"""How caller-addressed and observed writes of a temporal object join its
pending writes, driven at the composition seam without a database:
exact-window composition, disjoint operations, and the compositions an
ordering barrier keeps apart. What a composition binds to is
``test_ranges_targets``'s."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.core import predicate as predicate_algebra
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    KeyedWrite,
    PredicateSelection,
    PredicateWrite,
    WriteAssignment,
)
from parallax.core.unit_work.instructions import (
    ExpectedTxStart,
    PreparedKeyedWrite,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    ChainedTemporalWrite,
    ComposedTemporalWrite,
    InsertionKeyedWrite,
    ReadlessPredicateWrite,
    readless_write,
)
from parallax.core.unit_work.retain import InsertionIdentity
from parallax.core.unit_work.write_planner import PendingWrites
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit.core.unit_work._temporal_targets_support import (
    APR,
    AUG,
    DEC,
    FEB,
    JAN,
    JUL,
    JUN,
    MAR,
    MAY,
    OBJECT,
    OCT,
    POSITION,
    RESTATED,
    SEP,
    START,
    T0,
    T1,
    WHOLE,
    addressed_write,
    observed_write,
)


def _pending(*writes: BufferItem) -> PendingWrites:
    pending = PendingWrites(POSITION)
    for write in writes:
        pending.add(write, OBJECT)
    return pending


# --------------------------------------------------------------------------- #
# Admission: one window, one starting state, no resurrection.                  #
# --------------------------------------------------------------------------- #
def test_a_target_and_observed_writes_of_its_starting_state_compose_over_one_window() -> None:
    pending = _pending(observed_write("updateUntil", START, acctNum="B"))
    target = addressed_write(value="150.00")
    assert pending.admits_temporal(target, OBJECT)
    pending.add(target, OBJECT)
    observed = observed_write("updateUntil", START, value="175.00")
    assert pending.admits_temporal(observed, OBJECT)
    pending.add(observed, OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert [contribution.condition for contribution in composed.contributions] == [
        None,
        ExpectedTxStart(T0),
        None,
    ]
    assert [contribution.claim for contribution in composed.contributions] == [
        START,
        None,
        START,
    ]
    (segment,) = composed.transform.segments
    assert dict(segment.assigned or {}) == {"acctNum": "B", "value": Decimal("175.00")}


def test_a_restated_caller_condition_is_kept_once_however_often_it_is_overwritten() -> None:
    pending = _pending(addressed_write(value="1.00"))
    for value in ("2.00", "3.00"):
        pending.add(addressed_write(value=value), OBJECT)
        pending.add(addressed_write(replaces=True, acctNum="Z", value=value), OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert [contribution.condition for contribution in composed.contributions] == [
        ExpectedTxStart(T0)
    ]
    (segment,) = composed.transform.segments
    assert segment.replaces
    assert dict(segment.assigned or {}) == {"acctNum": "Z", "value": Decimal("3.00")}


@pytest.mark.parametrize(
    "held",
    [
        pytest.param(
            lambda: observed_write("updateUntil", RESTATED, value="1.00"), id="another-state"
        ),
        pytest.param(lambda: addressed_write(tx_start=T1, value="1.00"), id="another-stated-start"),
        pytest.param(
            lambda: observed_write("updateUntil", START, until=JUN, value="1.00"),
            id="an-unequal-window",
        ),
        pytest.param(lambda: observed_write("terminateUntil", START), id="a-destruction"),
    ],
)
def test_a_target_beside_a_write_it_cannot_share_a_start_with_is_refused(held: object) -> None:
    pending = _pending(held())  # type: ignore[operator]
    assert not pending.admits_temporal(addressed_write(value="150.00"), OBJECT)
    assert not pending.admits_temporal(
        addressed_write(replaces=True, acctNum="Z", value="1.00"), OBJECT
    )


def test_a_destruction_of_a_targets_window_supersedes_it_and_nothing_follows() -> None:
    pending = _pending(addressed_write(replaces=True, acctNum="Z", value="1.00"))
    destruction = observed_write("terminateUntil", START)
    assert pending.admits_temporal(destruction, OBJECT)
    pending.add(destruction, OBJECT)
    assert not pending.admits_temporal(observed_write("updateUntil", START, value="2.00"), OBJECT)
    assert not pending.admits_temporal(addressed_write(value="2.00"), OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    assert not composed.assigns


def test_a_target_never_joins_a_write_an_insertion_authorized() -> None:
    authored = prepare_wire_write(
        KeyedWrite("updateUntil", "Position", ({"id": 1, "value": "1.00"},), MAR, SEP),
        POSITION,
    )
    assert isinstance(authored, PreparedKeyedWrite)
    pending = _pending(InsertionKeyedWrite(authored, InsertionIdentity(OBJECT)))
    assert not pending.admits_temporal(addressed_write(value="2.00"), OBJECT)


def test_an_observed_write_after_a_target_must_state_its_window_and_start() -> None:
    pending = _pending(addressed_write(value="150.00"))
    assert not pending.admits_temporal(
        observed_write("updateUntil", START, until=JUN, value="1.00"), OBJECT
    )
    assert not pending.admits_temporal(
        observed_write("updateUntil", RESTATED, value="1.00"), OBJECT
    )
    assert pending.admits_temporal(observed_write("updateUntil", START, value="1.00"), OBJECT)


def test_a_target_meeting_any_earlier_unequal_contribution_is_refused() -> None:
    # Pure observed writes compose over unequal windows; a target joining them
    # must agree with every one, not only the latest.
    earlier = _pending(
        observed_write("update", START, valid_from=JAN, until=None, value="1.00"),
        observed_write("updateUntil", START, value="2.00"),
    )
    assert not earlier.admits_temporal(addressed_write(value="3.00"), OBJECT)
    target_first = _pending(
        addressed_write(value="3.00"), observed_write("updateUntil", START, value="2.00")
    )
    assert not target_first.admits_temporal(
        observed_write("update", START, valid_from=JAN, until=None, value="1.00"), OBJECT
    )


# --------------------------------------------------------------------------- #
# Disjoint operations: separate windows of one object, each its own condition. #
# --------------------------------------------------------------------------- #

type _Write = Callable[[dt.datetime, dt.datetime], BufferItem]

_KINDS: dict[str, _Write] = {
    "P": lambda start, until: addressed_write(valid_from=start, until=until, value="150.00"),
    "R": lambda start, until: addressed_write(
        replaces=True, valid_from=start, until=until, acctNum="Z", value="9.00"
    ),
    "O": lambda start, until: observed_write(
        "updateUntil", WHOLE, valid_from=start, until=until, acctNum="O"
    ),
    "D": lambda start, until: observed_write(
        "terminateUntil", WHOLE, valid_from=start, until=until
    ),
}
_PAIRS = ["P-P", "P-R", "R-P", "R-R", "P-O", "O-P", "R-O", "O-R", "P-D", "D-P", "R-D", "D-R"]
_GEOMETRIES = {
    "separated": ((FEB, APR), (JUN, AUG)),
    "adjacent": ((FEB, APR), (APR, JUN)),
}


@pytest.mark.parametrize("windows", ["earlier-first", "later-first"])
@pytest.mark.parametrize("geometry", list(_GEOMETRIES))
@pytest.mark.parametrize("pair", _PAIRS)
def test_writes_over_disjoint_windows_of_one_original_stay_separate_operations(
    pair: str, geometry: str, windows: str
) -> None:
    first_window, second_window = _GEOMETRIES[geometry]
    if windows == "later-first":
        first_window, second_window = second_window, first_window
    first_kind, second_kind = pair.split("-")
    first = _KINDS[first_kind](*first_window)
    second = _KINDS[second_kind](*second_window)
    pending = _pending(first)
    assert pending.admits_temporal(second, OBJECT)  # type: ignore[arg-type]
    pending.add(second, OBJECT)
    (composed,) = pending.writes()
    assert isinstance(composed, ComposedTemporalWrite)
    # Each operation keeps its own window and its own condition: a caller's
    # stated start, or the rectangle its source observed.
    assert [c.valid_time_window for c in composed.contributions] == [
        TimeInterval(*first_window),
        TimeInterval(*second_window),
    ]
    assert [c.condition is not None for c in composed.contributions] == [
        kind in "PR" for kind in (first_kind, second_kind)
    ]
    destroyed = {
        segment.valid_time_window
        for segment in composed.transform.segments
        if segment.assigned is None
    }
    assert destroyed == {
        TimeInterval(*window)
        for kind, window in ((first_kind, first_window), (second_kind, second_window))
        if kind == "D"
    }


@pytest.mark.parametrize(
    ("held", "arriving"),
    [
        pytest.param(("P", FEB, JUN), ("P", APR, AUG), id="P-P"),
        pytest.param(("P", FEB, JUN), ("O", APR, AUG), id="P-O"),
        pytest.param(("O", APR, AUG), ("P", FEB, JUN), id="O-P"),
        pytest.param(("R", FEB, JUN), ("D", APR, AUG), id="R-D"),
        pytest.param(("D", APR, AUG), ("R", FEB, JUN), id="D-R"),
        pytest.param(("P", FEB, AUG), ("R", APR, JUN), id="P-R-inside"),
    ],
)
def test_a_target_overlapping_another_write_unequally_is_refused(
    held: tuple[str, dt.datetime, dt.datetime], arriving: tuple[str, dt.datetime, dt.datetime]
) -> None:
    kind, start, until = held
    pending = _pending(_KINDS[kind](start, until))
    kind, start, until = arriving
    assert not pending.admits_temporal(_KINDS[kind](start, until), OBJECT)  # type: ignore[arg-type]


def test_an_unbounded_window_overlaps_every_window_after_its_start() -> None:
    unbounded = _pending(addressed_write(valid_from=MAR, until=None, value="150.00"))
    assert not unbounded.admits_temporal(
        observed_write("updateUntil", WHOLE, valid_from=SEP, until=OCT, acctNum="O"), OBJECT
    )
    # A different stored rectangle at the later start does not make it disjoint.
    assert not unbounded.admits_temporal(
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="1.00"), OBJECT
    )
    before = _pending(observed_write("updateUntil", WHOLE, valid_from=FEB, until=MAR, acctNum="O"))
    assert before.admits_temporal(
        addressed_write(valid_from=MAR, until=None, value="150.00"), OBJECT
    )


def test_a_write_disjoint_from_the_latest_but_overlapping_an_earlier_one_is_refused() -> None:
    # Two observed writes may overlap each other; a target disjoint from both
    # joins them, and a later target is judged against every one of them.
    pending = _pending(
        observed_write("updateUntil", WHOLE, valid_from=MAR, until=JUN, acctNum="A1"),
        observed_write("updateUntil", WHOLE, valid_from=APR, until=AUG, acctNum="A2"),
    )
    disjoint = addressed_write(valid_from=SEP, until=OCT, value="150.00")
    assert pending.admits_temporal(disjoint, OBJECT)
    pending.add(disjoint, OBJECT)
    assert not pending.admits_temporal(
        addressed_write(valid_from=JUL, until=SEP, value="1.00"), OBJECT
    )
    assert not pending.admits_temporal(
        observed_write("terminateUntil", WHOLE, valid_from=MAY, until=SEP), OBJECT
    )


@pytest.mark.parametrize("order", ["observed-first", "target-first"])
def test_a_target_starting_inside_an_observed_rectangle_must_state_its_revision(
    order: str,
) -> None:
    observed = observed_write("updateUntil", WHOLE, valid_from=FEB, until=APR, acctNum="O")
    for tx_start, admitted in ((T0, True), (T1, False)):
        target = addressed_write(valid_from=JUN, until=AUG, tx_start=tx_start, value="150.00")
        held, arriving = (observed, target) if order == "observed-first" else (target, observed)
        assert _pending(held).admits_temporal(arriving, OBJECT) is admitted


def test_a_shared_token_names_whatever_rectangle_holds_each_start() -> None:
    # The source observed only [January, June); a caller stating the same
    # Transaction-Time start for September names whichever rectangle holds it.
    pending = _pending(observed_write("updateUntil", START, valid_from=FEB, until=APR, acctNum="O"))
    assert pending.admits_temporal(addressed_write(valid_from=SEP, until=OCT, value="1.00"), OBJECT)
    assert pending.admits_temporal(
        addressed_write(valid_from=SEP, until=OCT, tx_start=T1, value="1.00"), OBJECT
    )


# --------------------------------------------------------------------------- #
# Ordering barriers: an object's writes on each side compose apart.           #
# --------------------------------------------------------------------------- #
_WALLET = formed(corpus_records()["wallet"])


def _barrier() -> ReadlessPredicateWrite:
    prepared = prepare_wire_write(
        PredicateWrite(
            "update",
            PredicateSelection("Wallet", predicate_algebra.Comparison("eq", "Wallet.id", 1)),
            assignments=(WriteAssignment("Wallet.owner", "Q"),),
        ),
        _WALLET,
    )
    return readless_write(prepared)


def test_a_readless_predicate_write_separates_an_objects_writes_into_chained_compositions() -> None:
    pending = _pending(
        addressed_write(valid_from=FEB, until=APR, value="1.00"),
        _barrier(),
        addressed_write(valid_from=JUN, until=AUG, value="2.00"),
        observed_write("updateUntil", WHOLE, valid_from=SEP, until=OCT, acctNum="O"),
        _barrier(),
        observed_write("terminateUntil", WHOLE, valid_from=OCT, until=DEC),
    )
    first, _q1, middle, _q2, last = pending.writes()
    chain = [
        (type(write).__name__, write.leads, write.follows, len(write.contributions))
        for write in (first, middle, last)
        if isinstance(write, ChainedTemporalWrite)
    ]
    assert chain == [
        ("ChainedTemporalWrite", True, False, 1),
        ("ChainedTemporalWrite", True, True, 2),
        ("ChainedTemporalWrite", False, True, 1),
    ]


def test_admission_across_a_barrier_judges_every_write_of_the_object() -> None:
    pending = _pending(addressed_write(valid_from=FEB, until=APR, value="1.00"), _barrier())
    # Unequal overlap with the write before the barrier is refused there too.
    assert not pending.admits_temporal(
        observed_write("updateUntil", WHOLE, valid_from=MAR, until=JUN, acctNum="O"), OBJECT
    )
    # One window and one start compose, though they execute as two units.
    exact = observed_write("updateUntil", WHOLE, valid_from=FEB, until=APR, acctNum="O")
    assert pending.admits_temporal(exact, OBJECT)
    pending.add(exact, OBJECT)
    first, _barrier_write, second = pending.writes()
    assert isinstance(first, ChainedTemporalWrite) and first.leads
    assert isinstance(second, ChainedTemporalWrite) and second.follows


def test_a_pure_observed_composition_after_a_barrier_follows_the_earlier_one() -> None:
    pending = _pending(
        observed_write("updateUntil", WHOLE, valid_from=MAR, until=JUN, acctNum="A"),
        _barrier(),
        observed_write("updateUntil", WHOLE, valid_from=APR, until=AUG, acctNum="B"),
    )
    first, _barrier_write, second = pending.writes()
    assert isinstance(first, ChainedTemporalWrite) and (first.leads, first.follows) == (True, False)
    assert isinstance(second, ChainedTemporalWrite) and (second.leads, second.follows) == (
        False,
        True,
    )
