"""The interleaved ``uow`` lane, driven database-free over two scripted
sessions: the optimistic-lock race end to end, each group lowering in its own
connection's dialect, the out-of-band statements applied before either group
starts, the conflict either group's last write may report, a group's non-last
write buffering without a flush, and the lane's own refusals — a step stating
relationship contents, an execution granting no termination trust, a second
session that will not open — each releasing every session it had opened.
"""

from __future__ import annotations

import copy
import dataclasses
import decimal
import functools
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance._database_control import TerminationReport
from parallax.conformance._lanes.interleaved import run_interleaved_scenario_case
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.db_port import Row
from parallax.core.dialect import Dialect
from parallax.snapshot import handle
from tests.unit._second_dialect import BACKTICKED
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._wire_value_support import wire_value


@functools.cache
def _corpus_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in case_format.load_cases()}


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these lane-level tests exercise
    # `run_interleaved_scenario_case` on its own terms, never gated on whether
    # the case has ALSO been flipped visible in the sweep.
    return _corpus_by_id()[case_id]


def _own_copy(case: case_format.Case) -> case_format.Case:
    return dataclasses.replace(case, document=copy.deepcopy(case.document))


def _synthetic_write(shape: str, document: dict[str, object]) -> case_format.Case:
    document.setdefault("model", "models/account.yaml")
    return case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape=shape,
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


class _ScriptedExecution:
    """One interleaved group's dedicated execution, over a scripted port.

    It declares the termination contract truthfully by default: every call into
    a `ScriptedPort` is a plain synchronous in-memory one that never blocks on
    real I/O, so there is nothing for the ladder to unblock. `trusted=False` is
    the refusal shape — an execution that grants nothing, which the lane must
    refuse before either worker thread starts.
    """

    def __init__(
        self,
        port: ScriptedPort,
        model: Any,
        *,
        clock: Any = None,
        lifecycle_provider: Any = None,
        trusted: bool = True,
    ) -> None:
        self.port = port
        self.trusted = trusted
        self.closed = False
        self.cancel_calls = 0
        self.terminate_calls = 0
        self._database = handle.Database.connect(
            port, model, clock=clock, lifecycle_provider=lifecycle_provider
        )

    @property
    def database(self) -> handle.Database:
        return self._database

    @property
    def dialect(self) -> Dialect:
        return self.port.dialect

    @property
    def termination_ladder_trusted(self) -> bool:
        return self.trusted

    def cancel_active(self) -> None:  # pragma: no cover - the entry-point pins never time out
        self.cancel_calls += 1

    def terminate_active(self) -> TerminationReport:  # pragma: no cover - same
        self.terminate_calls += 1
        return TerminationReport(terminated=True)

    def close(self) -> None:
        self.closed = True
        self.port.close()


class _ScriptedExecutions:
    """The lane's own execution factory, handing out one scripted execution per
    group in the order the groups are declared.

    ``trusted`` states each group's own declaration, and ``refuse_at`` makes the
    n-th open FAIL — the shape that proves the lane releases what it had already
    opened rather than leaking it.
    """

    def __init__(
        self,
        *ports: ScriptedPort,
        trusted: Sequence[bool] = (),
        refuse_at: int | None = None,
    ) -> None:
        self._ports = ports
        self._trusted = tuple(trusted) if trusted else (True,) * len(ports)
        self._refuse_at = refuse_at
        self.opened: list[_ScriptedExecution] = []

    def __call__(self, model: Any, *, clock: Any = None, lifecycle_provider: Any = None) -> Any:
        index = len(self.opened)
        if index == self._refuse_at:
            raise RuntimeError("this session could not be opened")
        execution = _ScriptedExecution(
            self._ports[index],
            model,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
            trusted=self._trusted[index],
        )
        self.opened.append(execution)
        return execution


def _wire_row(row: Row) -> dict[str, object]:
    """One authored row as the Wire spelling a find step's own rows carry."""
    return {key: wire_value(value) for key, value in row.items()}


def test_run_interleaved_scenario_case_renders_the_conflict_and_discards_the_abort() -> None:
    # `m-opt-lock-012` end to end over two SCRIPTED fake connections (never a
    # real database): the `ours` group's own observing find (step 0) is stale
    # by the time it flushes (step 3) — the `concurrent` group (steps 1-2)
    # committed its own gated update first — so the doomed group's SECOND
    # write (the version-gated update) affects 0 rows, and the group's own
    # buffered insert (account 9) is discarded with it. The trailing
    # ungrouped verify find (step 4) observes no rows for it.
    case = _load_case("m-opt-lock-012")
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    executions = _ScriptedExecutions(ours_port, peer_port)

    emissions, round_trips, conflict_actual, find_rows = run_interleaved_scenario_case(
        case, caller_port, executions
    )

    assert round_trips == 6
    assert len(emissions) == 6
    assert conflict_actual == 0
    # Both dedicated sessions are released by the lane that opened them.
    assert [execution.closed for execution in executions.opened] == [True, True]
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/objectQuery",
        "/scenario/2/write",
        "/scenario/3/write",
        "/scenario/3/write",
        "/scenario/4/objectQuery",
    ]
    assert emissions[3].sql.startswith("insert into account")
    assert emissions[4].sql.startswith("update account set")
    assert len(ours_port.writes) == 2  # the doomed group's insert + gated update
    assert len(peer_port.writes) == 1  # the concurrent group's own gated update
    # Every find step's own observed rows, in
    # scenario step order (0, 1, then the trailing ungrouped verify at 4) —
    # the doomed group's discarded insert leaves account 9 absent. The rows are
    # the Wire result re-keyed by column, so a `decimal` reads as its canonical
    # string exactly as the grader's own wire space compares it.
    assert find_rows == [[_wire_row(row_v1)], [_wire_row(row_v1)], []]


def test_each_interleaved_group_lowers_in_its_own_connections_dialect() -> None:
    # The two groups run on two connections, so the emission a group reports is
    # spelled by the connection that executed it: the `concurrent` group's write
    # (step 2) is lowered through the peer session's dialect and the `ours`
    # group's (step 3) through the caller's port. A shared dialect taken off the
    # main port would make the concurrent group report DML the peer never ran,
    # which its own plan-versus-delivery reconciliation refuses outright.
    case = _load_case("m-opt-lock-012")
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(dialect=BACKTICKED, read_rows=[[row_v1]], write_affected=[1])

    emissions, _round_trips, _conflict_actual, _find_rows = run_interleaved_scenario_case(
        case, caller_port, _ScriptedExecutions(ours_port, peer_port)
    )

    concurrent_write = next(e for e in emissions if e.case_pointer == "/scenario/2/write")
    ours_writes = [e for e in emissions if e.case_pointer == "/scenario/3/write"]
    assert "`version`" in concurrent_write.sql
    assert all("`" not in emission.sql for emission in ours_writes)
    assert all('"' not in emission.sql for emission in ours_writes)


def test_run_interleaved_scenario_case_applies_out_of_band_statements_before_the_groups() -> None:
    # The interleaved executor owes the same `given.apply` setup the other scenario
    # executors do: applied on the caller's own port after the fixtures and before
    # either worker starts, so both groups race against the state it left. Its own
    # first write lands after it in `writes` order, which is what pins the ordering.
    case = _load_case("m-opt-lock-012")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"fixtures": True, "apply": [{"sql": "update account set balance = ?"}]},
        },
    )
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]], write_affected=[0])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])

    run_interleaved_scenario_case(
        with_apply, caller_port, _ScriptedExecutions(ours_port, peer_port)
    )

    assert caller_port.writes[0][0] == "update account set balance = %s"
    assert len(caller_port.writes) == 1  # the out-of-band statement, and nothing else
    assert len(ours_port.writes) == 2  # the doomed group's own two


def test_run_interleaved_scenario_case_reports_the_second_groups_own_conflict_too() -> None:
    # The conflict-rendering fallback is symmetric: whichever group's own
    # last write conflicts, its `actual` affected-row count surfaces —
    # `m-opt-lock-012`'s own corpus witness always dooms the FIRST-labeled
    # (`ours`) group, but the engine's own logic does not assume that. A
    # synthetic two-group scenario (never `m-opt-lock-012` itself: its own
    # fixed step order makes the SECOND group's conflict turnstile-unsafe —
    # something downstream always waits on its final `advance()`) pins the
    # fallback: the SECOND group's own last step is also the scenario's
    # OVERALL last grouped step, so nothing waits on its advance either way.
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "uow": {"concurrency": "optimistic"},
                "scenario": [
                    {
                        "uow": "x",
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": "260.00"}],
                            }
                        ],
                    },
                    {
                        "uow": "y",
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
                    },
                    {
                        "uow": "y",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": "270.00"}],
                            }
                        ],
                    },
                ],
            },
            "then": {"roundTrips": 4},
        },
    )
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[0])

    _emissions, _round_trips, conflict_actual, _find_rows = run_interleaved_scenario_case(
        case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    assert conflict_actual == 0


def test_run_interleaved_group_buffers_a_non_last_write_without_flushing() -> None:
    # A group's own write step that is NOT its last step buffers without
    # forcing a flush (mirroring the keyed unit-of-work lane's own per-step
    # buffering for a contiguous span, `_run_interleaved_group`'s own
    # generalization of the SAME machinery) — unwitnessed by `m-opt-lock-012`
    # itself (whose own two groups each carry exactly one write, always last).
    case = _synthetic_write(
        "scenario",
        {
            "when": {
                "uow": {"concurrency": "optimistic"},
                "scenario": [
                    {
                        "uow": "x",
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                        },
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "insert",
                                "entity": "Account",
                                "rows": [
                                    {"id": 90, "owner": "Noether", "balance": "5.00", "version": 1}
                                ],
                            }
                        ],
                    },
                    {
                        "uow": "x",
                        "write": [
                            {
                                "mutation": "update",
                                "entity": "Account",
                                "rows": [{"id": 2, "balance": "260.00"}],
                            }
                        ],
                    },
                    {
                        "uow": "y",
                        "objectQuery": {
                            "target": "Account",
                            "predicate": {"eq": {"attr": "Account.id", "value": 3}},
                        },
                    },
                ],
            },
            "then": {"roundTrips": 4},
        },
    )
    row_v1: Row = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    row3: Row = {
        "id": 3,
        "owner": "Ada",
        "balance": decimal.Decimal("10.00"),
        "version": 1,
    }
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 1])
    peer_port = ScriptedPort(read_rows=[[row3]])

    emissions, round_trips, conflict_actual, find_rows = run_interleaved_scenario_case(
        case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    assert conflict_actual is None
    assert round_trips == 4
    assert len(ours_port.writes) == 2  # buffered together, flushed once at the group's last step
    assert [e.case_pointer for e in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/write",
        "/scenario/3/objectQuery",
    ]
    assert find_rows == [[_wire_row(row_v1)], [_wire_row(row3)]]


def test_run_interleaved_scenario_case_reraises_an_unexpected_worker_failure() -> None:
    # A worker thread's own UNEXPECTED defect (never a witnessed path) must
    # surface loudly on the main thread rather than hang the choreography —
    # `_Turnstile.release_all` unsticks the partner thread (blocked on
    # `wait_for` a later step that now never arrives) so `thread.join()`
    # itself never hangs either.
    case = _load_case("m-opt-lock-012")
    failure = RuntimeError("a worker thread's own unexpected defect")
    ours_port = ScriptedPort(raise_on_read=failure)
    peer_port = ScriptedPort(
        read_rows=[
            [{"id": 2, "owner": "Linus", "balance": decimal.Decimal("250.00"), "version": 1}]
        ]
    )
    executions = _ScriptedExecutions(ours_port, peer_port)

    with pytest.raises(RuntimeError, match="unexpected defect"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)
    assert [execution.closed for execution in executions.opened] == [True, True]


@pytest.mark.parametrize(
    "trusted, expected_labels",
    [
        ((False, True), ("uow-ours",)),
        ((True, False), ("uow-concurrent",)),
        ((False, False), ("uow-ours", "uow-concurrent")),
    ],
)
def test_run_interleaved_scenario_case_refuses_an_execution_granting_no_termination_trust(
    trusted: tuple[bool, bool], expected_labels: tuple[str, ...]
) -> None:
    # The lane's post-termination join is unbounded, so an execution that grants
    # nothing must be refused BEFORE either worker thread starts — every defect
    # named at once rather than first-failure-only, and the refusal must still
    # release both sessions it had already opened. Nothing ran: neither scripted
    # port ever saw a statement.
    case = _load_case("m-opt-lock-012")
    healthy_row: Row = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    ours_port = ScriptedPort(read_rows=[[healthy_row]])
    peer_port = ScriptedPort(read_rows=[[healthy_row]])
    executions = _ScriptedExecutions(ours_port, peer_port, trusted=trusted)

    with pytest.raises(EngineError, match="refuses to start") as raised:
        run_interleaved_scenario_case(case, ScriptedPort(), executions)

    message = str(raised.value)
    for label in expected_labels:
        assert label in message
    assert [execution.closed for execution in executions.opened] == [True, True]
    assert ours_port.reads == []
    assert peer_port.reads == []


def test_run_interleaved_scenario_case_releases_the_first_when_the_second_will_not_open() -> None:
    # Incremental ownership: a second session that cannot be opened must not
    # leak the first. The failure surfaces as itself — never masked by the
    # release — and the session already opened is closed on the way out.
    case = _load_case("m-opt-lock-012")
    ours_port = ScriptedPort()
    peer_port = ScriptedPort()
    executions = _ScriptedExecutions(ours_port, peer_port, refuse_at=1)

    with pytest.raises(RuntimeError, match="could not be opened"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)

    assert [execution.closed for execution in executions.opened] == [True]
    assert ours_port.reads == []


def test_run_interleaved_scenario_case_refuses_a_step_stating_relationship_contents() -> None:
    # That entry point reports emissions, round trips and find rows and carries no
    # `stepGraphs` channel, so an `expectGraph` authored on an interleaved case
    # would be an oracle nothing answers. It is refused rather than left silent.
    case = _own_copy(_load_case("m-opt-lock-012"))
    when = cast("dict[str, Any]", case.document["when"])
    steps = cast("list[dict[str, Any]]", when["scenario"])
    steps[0]["expectGraph"] = {"Account": [{"id": 2}]}

    with pytest.raises(EngineError, match="carries no `stepGraphs` channel"):
        run_interleaved_scenario_case(
            case, ScriptedPort(), _ScriptedExecutions(ScriptedPort(), ScriptedPort())
        )
