"""Case-driven API-suite write-value runner (m-unit-work *Write value
provenance*, m-api-conformance).

ONE parametrized test over EVERY reachable keyed-write-value corpus case
(m-case-format *Keyed write action steps*): drives the REAL developer verbs
inside a real `db.transact` against the provisioned database through the shipped
`parallax-postgres` adapter, and grades each step's `expectError`. These cases
are `lane: api-conformance` because what they observe is a property of a live
client-held value, which no wire harness can construct — this suite is the
adapter that holds the implementation to them.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from _support.corpus import case_fixtures
from parallax.conformance import case_format, engine, write_value_runner
from parallax.conformance.another_source import AnotherSource
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction

_CASES = write_value_runner.reachable_write_value_cases()
_CASE_IDS = [case.case_id for case in _CASES]


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_write_value_case_runs_through_the_shipped_verbs(
    case: case_format.Case, provisioner: Any
) -> None:
    provisioner.reset(engine.load_case_metamodel(case), case_fixtures(case))
    model = MODELS[Path(case.model).stem]
    db = connect(provisioner.port, model)
    # A `anotherSource` value is read through this second managed source, which
    # materializes and recognizes its own independently of the Snapshot lifecycle
    # the verbs under test write through.
    another = AnotherSource(model, provisioner.port)
    steps = write_value_runner.write_value_steps(case)

    def fn(tx: Transaction) -> list[str | None]:
        return write_value_runner.graded_outcomes(tx, steps, another)

    result = db.transact(fn)
    assert result.value == [step.expect_error for step in steps]
    # The case's `then.roundTrips` graded against what the transaction actually
    # did (`m-execution-log`), never against a count this suite kept. The count is
    # the steps' own verbs, so the WRITE calls are what it names: a read that
    # arranges a value of the stated provenance is the adapter's own affair and
    # is not the case's cost (:func:`write_value_runner.declared_round_trips`),
    # and the Database Call's own kind is what separates the two.
    executed_writes = sum(
        1
        for attempt in result.execution_log.attempts
        for call in attempt.calls
        if call.kind == "write"
    )
    assert executed_writes == write_value_runner.declared_round_trips(case)
    # The durable end state beside it: a statement that ran would have left an
    # effect on one of the only two rows a keyed write here can address. The
    # fixture row stands exactly as loaded (a flushed `update` would bump
    # `version` even carrying no change), and `UNMANAGED_ID` — outside the
    # fixture range precisely so a value no managed read produced cannot address
    # a row one did — holds no row at all.
    stored, unmanaged = db.transact(
        lambda tx: (
            tx.find(Account.where(Account.id == write_value_runner.TARGET_ID)).result(),
            tx.find(Account.where(Account.id == write_value_runner.UNMANAGED_ID)).results(),
        )
    ).value
    assert (stored.owner, stored.balance, stored.version) == ("Linus", Decimal("250.00"), 1)
    assert unmanaged == []


def test_reachable_write_value_cases_cover_the_closed_vocabulary() -> None:
    # Never a hand list at the RUNNER level (the corpus itself drives `_CASES`);
    # this is a coverage assertion that the three codes each have a witness and
    # that the accepted half is witnessed beside them.
    assert set(_CASE_IDS) == {
        "m-unit-work-017",
        "m-unit-work-018",
        "m-unit-work-019",
        "m-unit-work-020",
    }
