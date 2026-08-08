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
from parallax.conformance.story_models import ACCOUNT_MODEL, Account
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

    def fn(tx: Transaction) -> list[str | None]:
        return write_value_runner.graded_outcomes(tx, steps)

    outcomes = _db(port).transact(fn)
    assert outcomes == [step.expect_error for step in steps]
    # What reaches DML is derived from the case rather than assumed of the
    # corpus: an accepted `insert` step buffers a row the enclosing transaction
    # flushes, while a refusal buffers nothing and an accepted `update` carries
    # no change (this runner never edits the value it arranges). The recorded
    # operations are what makes either claim provable with no database at all.
    assert any(op[0] == "write" for op in port.ops) == any(
        step.expect_error is None and step.action == "insert" for step in steps
    )


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


@pytest.mark.parametrize(
    "provenance", ["unmanaged", "anotherSource"], ids=["unmanaged", "another-source"]
)
def test_a_value_needing_no_read_is_arranged_without_touching_the_adapter(
    provenance: str,
) -> None:
    def fn(tx: Transaction) -> Account:
        return write_value_runner.value_of(provenance, tx)

    value = Database.connect(NoIoPort(), ACCOUNT_MODEL, clock=FixedClock(FIXED)).transact(fn)
    assert isinstance(value, Account)


def test_a_case_mixing_a_keyed_write_step_with_another_step_is_loud() -> None:
    # Selection by containment, not by uniformity: a keyed write action step
    # that acquires a neighbour this runner cannot drive must not drop out of
    # the graded set silently.
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


def test_an_unrecognized_provenance_token_is_loud() -> None:
    port = RecordingPort(rows=[_TARGET_ROW])

    def fn(tx: Transaction) -> Account:
        return write_value_runner.value_of("invented", tx)

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

    def fn(tx: Transaction) -> str | None:
        return write_value_runner.grade_step(tx, step)

    with pytest.raises(AssertionError, match=message):
        _db(port).transact(fn)
