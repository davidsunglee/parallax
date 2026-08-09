"""The joined-transaction Execution Log stories against real Postgres
(m-execution-log, m-api-conformance).

`m-execution-log-007`'s portable oracle is a TERMINAL value graph, and the
boundary runner already grades it (`test_boundary_run.py`). What no terminal
oracle can express is the live half of the same lifecycle, which is what these
stories observe from inside the invocation: the log reachable and `active` before
anything completes, the joined result carrying the SAME log object, a trace
appearing on it as it closes, the seal falling at the outer boundary, and the two
intermediate states surfacing as two distinct refusals.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _support.corpus import case_fixtures
from parallax.conformance import case_format, engine, execution_log_stories
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.snapshot import connect

_CASE_ID = "m-execution-log-007"


def _account_db(provisioner: Any) -> Any:
    case = next(
        c for c in case_format.load_cases() if c.case_id == _CASE_ID
    )  # the story's own mirrored case supplies the model and its fixtures
    provisioner.reset(engine.load_case_metamodel(case), case_fixtures(case))
    return connect(provisioner.port, MODELS["account"])


def test_a_joined_unit_of_work_appends_to_the_outer_live_log(provisioner: Any) -> None:
    db = _account_db(provisioner)
    observed = execution_log_stories.a_joined_unit_of_work_appends_to_the_outer_live_log(db)

    # The live half, observed from inside the invocation.
    live = observed.live
    assert live.status_while_running == "active"
    assert live.shares_the_outer_log
    assert not live.sealed_while_running
    assert live.execution_refusal == "TransactionInProgressError"
    # The read's trace closed and was appended; the joined write is still buffered.
    assert (live.traces_before_join, live.traces_after_join) == (1, 1)

    # The terminal half the case's own oracle states, read off the same object:
    # ONE attempt, its traces spanning both bodies, sealed at the outer boundary.
    log = observed.result.execution_log
    assert log.is_sealed
    assert len(log.attempts) == 1
    attempt = observed.result.execution
    assert attempt.status == "committed"
    assert [type(trace).__name__ for trace in attempt.traces] == ["ReadTrace", "WriteBatchTrace"]
    assert log.round_trips == 2

    verify = connect(provisioner.port, MODELS["account"]).transact(
        lambda tx: tx.find(Account.where(Account.id == 2)).result()
    )
    assert verify.value.balance == Decimal("251.00")


def test_a_joined_result_of_a_rolled_back_transaction_has_no_execution(provisioner: Any) -> None:
    db = _account_db(provisioner)
    observed = execution_log_stories.a_joined_result_of_a_rolled_back_transaction_has_no_execution(
        db
    )

    # The SECOND of the two intermediate states, and a distinct refusal from the
    # first: the outer boundary terminated without committing.
    assert observed.refusal == "TransactionNotCommittedError"
    log = observed.joined.execution_log
    assert log.is_sealed
    assert log.committed_attempt is None
    assert log.final_attempt.status == "rolled_back"

    verify = connect(provisioner.port, MODELS["account"]).transact(
        lambda tx: tx.find(Account.where(Account.id == 2)).result()
    )
    assert verify.value.balance == Decimal("250.00"), "the aborted joined write never persisted"
