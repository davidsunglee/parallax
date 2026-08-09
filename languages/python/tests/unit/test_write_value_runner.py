"""The case-driven write-value runner, Docker-free (m-unit-work *Write value
provenance*, m-case-format *Keyed write action steps*).

ONE parametrized test over EVERY reachable keyed-write-value corpus case, driven
through the REAL `db.transact` over the recording fake port the transaction
suites share — so each case's stated provenance is arranged by the shipped
runner, graded by the production validator, and refused (or accepted) before any
DML. The fake port is what makes that grading provable with no database at all:
the recorded operations are the proof no case reached one.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from _transact_support import FIXED, NoIoPort, RecordingPort

from parallax.conformance import case_format, write_value_runner
from parallax.conformance.another_source import AnotherSource
from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Account, Order
from parallax.core.db_port import Row
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

_CASES = write_value_runner.reachable_write_value_cases()
_CASE_IDS = [case.case_id for case in _CASES]

_TARGET_ROW: Row = {
    "id": write_value_runner.TARGET_ID,
    "owner": "Linus",
    "balance": Decimal("250.00"),
    "version": 1,
}


def _db(port: RecordingPort) -> Database:
    return connect(port, ACCOUNT_MODEL, clock=FixedClock(FIXED))


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_every_write_value_case_is_graded_through_the_shipped_verbs(
    case: case_format.Case,
) -> None:
    steps = write_value_runner.write_value_steps(case)
    port = RecordingPort(rows=[_TARGET_ROW])
    another = AnotherSource(ACCOUNT_MODEL, port)

    def fn(tx: Transaction) -> list[str | None]:
        return write_value_runner.graded_outcomes(tx, steps, another)

    outcomes = _db(port).transact(fn)
    assert outcomes == [step.expect_error for step in steps]
    # The case's own round-trip oracle, graded against the DML the enclosing
    # transaction actually flushed: a refusal reaches no statement and an
    # accepted step here materializes nothing (m-case-format *Keyed write action
    # steps*), so the count the case declares is the count the port recorded.
    # The recorded operations are what makes that provable with no database at
    # all.
    flushed = [op for op in port.ops if op[0] == "write"]
    assert len(flushed) == write_value_runner.declared_round_trips(case)


def test_the_corpus_witnesses_every_code_of_the_closed_vocabulary() -> None:
    graded = {
        step.expect_error
        for case in _CASES
        for step in write_value_runner.write_value_steps(case)
        if step.expect_error is not None
    }
    assert graded == {
        "write-value-not-stored",
        "write-value-already-stored",
        "write-value-foreign-lifecycle",
    }


def test_the_value_no_read_produced_is_arranged_without_touching_the_adapter() -> None:
    # `unmanaged` is the one provenance no managed read produces, so arranging it
    # reaches no port at all. The other two are reads, each through the source
    # whose provenance the token names.
    unreachable = AnotherSource(ACCOUNT_MODEL, NoIoPort())

    def fn(tx: Transaction) -> Account:
        return write_value_runner.value_of("unmanaged", tx, unreachable)

    value = Database.connect(NoIoPort(), ACCOUNT_MODEL, clock=FixedClock(FIXED)).transact(fn)
    assert isinstance(value, Account)


def test_the_second_source_materializes_from_a_read_and_recognizes_its_own() -> None:
    # The two halves of what `m-unit-work` calls a framework-managed source: it
    # materializes values from reads, and it attaches the state by which it later
    # recognizes its own. A sibling source over the same store claims nothing of
    # this one's, which is what makes recognition per-source rather than a test
    # for managed-ness in general.
    port = RecordingPort(rows=[_TARGET_ROW])
    another = AnotherSource(ACCOUNT_MODEL, port)

    (value,) = another.find(Account.where(Account.id == write_value_runner.TARGET_ID))

    assert [op[0] for op in port.ops] == ["read"]
    assert (value.id, value.owner, value.balance) == (
        write_value_runner.TARGET_ID,
        "Linus",
        Decimal("250.00"),
    )
    assert another.produced(value)
    assert not AnotherSource(ACCOUNT_MODEL, port).produced(value)
    assert not another.produced(Account(id=1, owner="Unmanaged", balance=Decimal("0.00")))


def test_the_second_source_refuses_a_deep_fetch_before_reading() -> None:
    # It populates no relationship view, so a query asking for one is refused at
    # the query rather than read and then answered without its levels — and the
    # raising port proves the refusal precedes the read.
    another = AnotherSource(ORDERS_MODEL, NoIoPort())

    with pytest.raises(ValueError, match="flat graphs only"):
        another.find(Order.where(Order.id == 1).include(Order.items))


def test_a_case_mixing_a_keyed_write_step_with_another_step_is_loud() -> None:
    # The schema admits no such case, so this document is one that never
    # validated; selection is still by containment rather than by uniformity, so
    # the keyed step cannot drop out of the graded set silently on the way to
    # the executor that is the case's only one.
    steps: list[dict[str, Any]] = [
        {"action": "update", "value": "unmanaged", "roundTrips": 0},
        {"find": {}, "targetEntity": "parallax.compatibility.Account", "roundTrips": 1},
    ]
    mixed = case_format.Case(
        path=Path("m-unit-work-999-mixed.yaml"),
        case_id="m-unit-work-999",
        shape="scenario",
        tags=("m-unit-work",),
        model="models/account.yaml",
        document={"when": {"scenario": steps}},
    )

    with pytest.raises(ValueError, match="graded neither whole nor in part"):
        write_value_runner.reachable_write_value_cases([mixed])


def test_a_case_whose_total_disagrees_with_its_steps_is_loud() -> None:
    # A scenario's `then.roundTrips` is the sum of its steps' own counts, and
    # this suite is where that is checked at all: the compatibility harness
    # executes no api-conformance case.
    miscounted = case_format.Case(
        path=Path("m-unit-work-999-miscounted.yaml"),
        case_id="m-unit-work-999",
        shape="scenario",
        tags=("m-unit-work",),
        model="models/account.yaml",
        document={
            "when": {"scenario": [{"action": "update", "value": "unmanaged", "roundTrips": 0}]},
            "then": {"roundTrips": 1},
        },
    )

    with pytest.raises(ValueError, match="sum of its steps"):
        write_value_runner.declared_round_trips(miscounted)


def test_an_unrecognized_provenance_token_is_loud() -> None:
    port = RecordingPort(rows=[_TARGET_ROW])
    another = AnotherSource(ACCOUNT_MODEL, port)

    def fn(tx: Transaction) -> Account:
        return write_value_runner.value_of("invented", tx, another)

    with pytest.raises(ValueError, match="unrecognized value provenance"):
        _db(port).transact(fn)


@pytest.mark.parametrize(
    ("step", "message"),
    [
        (
            write_value_runner.WriteValueStep("update", "unmanaged", "write-value-already-stored"),
            "but the step declares expectError",
        ),
        (
            write_value_runner.WriteValueStep("update", "thisSource", "write-value-not-stored"),
            "verb accepted the value",
        ),
    ],
    ids=["wrong-code", "refusal-that-never-came"],
)
def test_a_graded_mismatch_is_loud_in_either_direction(
    step: write_value_runner.WriteValueStep, message: str
) -> None:
    port = RecordingPort(rows=[_TARGET_ROW])
    another = AnotherSource(ACCOUNT_MODEL, port)

    def fn(tx: Transaction) -> str | None:
        return write_value_runner.grade_step(tx, step, another)

    with pytest.raises(AssertionError, match=message):
        _db(port).transact(fn)
