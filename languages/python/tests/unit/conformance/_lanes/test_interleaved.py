"""The interleaved ``uow`` lane, driven database-free over two scripted
sessions: the optimistic-lock race end to end, each group lowering in its own
connection's dialect, the out-of-band statements applied before either group
starts, the conflict either group's last write may report, a group's non-last
write buffering without a flush, and the lane's own refusals — a step stating
relationship contents, an execution granting no termination trust, a second
session that will not open — each releasing every session it had opened.

The temporal race runs each group at its own instant and settles each temporal
write against its own group's reads, modeling no case state: what a group's
reads did not retain is refused rather than modeled.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
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
from parallax.core.base import INFINITY
from parallax.core.db_port import MappingRow, Row
from parallax.core.dialect import Dialect
from parallax.core.execution import DatabaseOptions
from parallax.snapshot import Database, ScopedDatabase
from tests._support.root_ownership import own_root
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
        options: DatabaseOptions | None = None,
        clock: Any = None,
        lifecycle_provider: Any = None,
        trusted: bool = True,
    ) -> None:
        self.port = port
        self.options = options
        self.trusted = trusted
        self.closed = False
        self.cancel_calls = 0
        self.terminate_calls = 0
        self._database = own_root(
            Database.connect(
                port, model, options=options, clock=clock, lifecycle_provider=lifecycle_provider
            )
        ).using_database_login()

    @property
    def database(self) -> ScopedDatabase:
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

    def __call__(
        self,
        model: Any,
        *,
        options: DatabaseOptions | None = None,
        clock: Any = None,
        lifecycle_provider: Any = None,
    ) -> Any:
        index = len(self.opened)
        if index == self._refuse_at:
            raise RuntimeError("this session could not be opened")
        execution = _ScriptedExecution(
            self._ports[index],
            model,
            options=options,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
            trusted=self._trusted[index],
        )
        self.opened.append(execution)
        return execution


def _wire_row(row: MappingRow) -> dict[str, object]:
    """One authored row as the Wire spelling a find step's own rows carry."""
    return {key: wire_value(value) for key, value in row.items()}


def _shortfalls(units: dict[str, dict[str, object]] | None) -> list[object]:
    """The Shortfall each group's flush failure names, in group order."""
    return [
        cast("dict[str, object]", fate["flushFailure"])["shortfall"]
        for fate in (units or {}).values()
        if "flushFailure" in fate
    ]


def test_run_interleaved_scenario_case_renders_the_conflict_and_discards_the_abort() -> None:
    # `m-opt-lock-012` end to end over two SCRIPTED fake connections (never a
    # real database): the `ours` group's own observing find (step 0) is stale
    # by the time it flushes (step 3) — the `concurrent` group (steps 1-2)
    # committed its own gated update first — so the doomed group's SECOND
    # write (the version-gated update) affects 0 rows, and the group's own
    # buffered insert (account 9) is discarded with it. The trailing
    # ungrouped verify find (step 4) observes no rows for it.
    case = _load_case("m-opt-lock-012")
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    executions = _ScriptedExecutions(ours_port, peer_port)

    run = run_interleaved_scenario_case(case, caller_port, executions)

    emissions = run.emissions
    assert run.round_trips == 6
    assert len(emissions) == 6
    assert run.units == {
        "ours": {
            "outcome": "rolledBack",
            "flushFailure": {
                "at": "commit",
                "entity": "parallax.compatibility.Account",
                "key": {"id": 2},
                "shortfall": "optimisticConflict",
            },
        },
        "concurrent": {"outcome": "committed"},
    }
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
    # Every find step's own `stepRows`, in scenario step order (0, 1, then the
    # trailing ungrouped verify at 4) — the doomed group's discarded insert leaves
    # account 9 absent. The rows are the Wire result re-keyed by column, so a
    # `decimal` reads as its canonical string exactly as the grader's own wire
    # space compares it.
    assert run.step_rows == [
        {"at": "/scenario/0", "rows": [_wire_row(row_v1)]},
        {"at": "/scenario/1", "rows": [_wire_row(row_v1)]},
        {"at": "/scenario/4", "rows": []},
    ]
    # The case states no final tables, so none are read back.
    assert run.table_state is None


def test_each_interleaved_group_lowers_in_its_own_connections_dialect() -> None:
    # The two groups run on two connections, so the emission a group reports is
    # spelled by the connection that executed it: the `concurrent` group's write
    # (step 2) is lowered through the peer session's dialect and the `ours`
    # group's (step 3) through the caller's port. A shared dialect taken off the
    # main port would make the concurrent group report DML the peer never ran,
    # which its own plan-versus-delivery reconciliation refuses outright.
    case = _load_case("m-opt-lock-012")
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(dialect=BACKTICKED, read_rows=[[row_v1]], write_affected=[1])

    emissions = run_interleaved_scenario_case(
        case, caller_port, _ScriptedExecutions(ours_port, peer_port)
    ).emissions

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
    row_v1: MappingRow = {
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
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[0])

    run = run_interleaved_scenario_case(
        case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    assert _shortfalls(run.units) == ["optimisticConflict"]


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
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    row3: MappingRow = {
        "id": 3,
        "owner": "Ada",
        "balance": decimal.Decimal("10.00"),
        "version": 1,
    }
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 1])
    peer_port = ScriptedPort(read_rows=[[row3]])

    run = run_interleaved_scenario_case(
        case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    assert _shortfalls(run.units) == []
    assert run.round_trips == 4
    assert len(ours_port.writes) == 2  # buffered together, flushed once at the group's last step
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/write",
        "/scenario/2/write",
        "/scenario/3/objectQuery",
    ]
    assert run.step_rows == [
        {"at": "/scenario/0", "rows": [_wire_row(row_v1)]},
        {"at": "/scenario/3", "rows": [_wire_row(row3)]},
    ]


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
    healthy_row: MappingRow = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
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
    # That entry point fills no `stepGraphs` channel, so an `expectGraph` authored
    # on an interleaved case would be an oracle nothing answers. It is refused
    # rather than left silent.
    case = _own_copy(_load_case("m-opt-lock-012"))
    when = cast("dict[str, Any]", case.document["when"])
    steps = cast("list[dict[str, Any]]", when["scenario"])
    steps[0]["expectGraph"] = {"Account": [{"id": 2}]}

    with pytest.raises(EngineError, match="fills no `stepGraphs` channel"):
        run_interleaved_scenario_case(
            case, ScriptedPort(), _ScriptedExecutions(ScriptedPort(), ScriptedPort())
        )


def _with_option_placement(
    placement: Mapping[str, Mapping[str, object]],
) -> case_format.Case:
    """`m-opt-lock-012` with each block of ``placement`` merged into its document."""
    case = _own_copy(_load_case("m-opt-lock-012"))
    document = cast("dict[str, Any]", case.document)
    for group, fields in placement.items():
        document[group] = {**cast("Mapping[str, Any]", document.get(group) or {}), **fields}
    return case


@pytest.mark.parametrize(
    ("placement", "bound"),
    [
        ({"given": {"databaseOptions": {"retryOptimisticConflicts": True}}}, 10),
        ({"when": {"uow": {"retryOptimisticConflicts": True, "maxRetries": 1}}}, 1),
    ],
)
def test_an_interleaved_case_resolving_the_conflict_retry_opt_in_is_refused_up_front(
    placement: Mapping[str, Mapping[str, object]], bound: int
) -> None:
    # Each group is one turnstile-sequenced production attempt; an opt-in the
    # groups would resolve — spelled on the root or on the invocation — under a
    # positive bound, the built-in or an authored one, would have production
    # re-run a conflicting group's steps against a turnstile that already
    # passed them. Refused before either session is asked for.
    case = _with_option_placement(placement)
    executions = _ScriptedExecutions(ScriptedPort(), ScriptedPort())

    with pytest.raises(EngineError, match=f"optimistic-conflict retry under a bound of {bound}"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)
    assert executions.opened == []


@pytest.mark.parametrize(
    "placement",
    [
        {"given": {"databaseOptions": {"retryOptimisticConflicts": True, "maxRetries": 0}}},
        {"when": {"uow": {"retryOptimisticConflicts": True, "maxRetries": 0}}},
    ],
)
def test_an_interleaved_case_whose_opt_in_is_bounded_at_zero_runs_each_group_once(
    placement: Mapping[str, Mapping[str, object]],
) -> None:
    # An opt-in under a bound of `0` cannot add an attempt (`m-auto-retry`: a
    # zero bound disables the loop), so the case runs as authored from either
    # placement: the doomed group's conflict surfaces after its one attempt,
    # and each session opens exactly one transaction.
    case = _with_option_placement(placement)
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    executions = _ScriptedExecutions(ours_port, peer_port)

    run = run_interleaved_scenario_case(case, caller_port, executions)

    assert run.round_trips == 6
    assert _shortfalls(run.units) == ["optimisticConflict"]
    assert len(ours_port.levels) == 1
    assert len(peer_port.levels) == 1
    assert len(ours_port.writes) == 2
    assert len(peer_port.writes) == 1


def test_each_interleaved_group_is_composed_over_the_cases_own_root_record() -> None:
    # The lane never connects a Database itself; it asks the factory for one
    # per group, and what it hands the factory is the case's root record — so a
    # root the case configures reaches both dedicated sessions' Handles, and
    # each group's transaction opens at the root's level while the request
    # carries only what `when.uow` authored.
    case = _load_case("m-opt-lock-012")
    document = dict(case.document)
    document["given"] = {
        **cast("Mapping[str, Any]", document.get("given") or {}),
        "databaseOptions": {"isolation": "serializable", "maxRetries": 0},
    }
    rooted = dataclasses.replace(case, document=document)
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])
    executions = _ScriptedExecutions(ours_port, peer_port)

    run_interleaved_scenario_case(rooted, caller_port, executions)

    expected = case_format.database_options(rooted)
    assert expected == DatabaseOptions(isolation="serializable", max_retries=0)
    assert [execution.options for execution in executions.opened] == [expected, expected]
    assert ours_port.levels == ["serializable"]
    assert peer_port.levels == ["serializable"]
    # The trailing ungrouped verify find runs on the caller's port through a
    # Handle of its own, connected with the same root.
    assert caller_port.levels == ["serializable"]


_FEB = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_SEP = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_OCT = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)


def _balance(key: int, *, in_z: dt.datetime, value: str = "200.00") -> MappingRow:
    """One current Transaction-Time-Only `Balance` milestone, as a find reads it."""
    return {
        "bal_id": key,
        "acct_num": "B",
        "val": decimal.Decimal(value),
        "in_z": in_z,
        "out_z": INFINITY,
    }


def _race(
    *,
    ours_reads: Sequence[list[MappingRow]] = ([_balance(2, in_z=_FEB)],),
    ours_affected: Sequence[int] = (0,),
    caller: ScriptedPort | None = None,
) -> tuple[Any, ScriptedPort, ScriptedPort]:
    """`m-temporal-read-010` over scripted sessions: ``ours`` finds balance 2,
    ``concurrent`` finds it, updates it and commits, then ``ours`` terminates it.
    """
    ours_port = ScriptedPort(read_rows=ours_reads, write_affected=ours_affected)
    peer_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]], write_affected=[1, 1])
    run = run_interleaved_scenario_case(
        _load_case("m-temporal-read-010"),
        caller if caller is not None else ScriptedPort(),
        _ScriptedExecutions(ours_port, peer_port),
    )
    return run, ours_port, peer_port


def test_a_temporal_race_reports_the_stale_close_as_the_losing_groups_conflict() -> None:
    run, ours_port, peer_port = _race()

    assert run.units == {
        "ours": {
            "outcome": "rolledBack",
            "flushFailure": {
                "at": "commit",
                "entity": "parallax.compatibility.Balance",
                "key": {"id": 2},
                "shortfall": "optimisticConflict",
            },
        },
        "concurrent": {"outcome": "committed"},
    }
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/1/objectQuery",
        "/scenario/2/write",
        "/scenario/2/write",
        "/scenario/3/write",
    ]
    assert run.round_trips == 5
    assert [sql.split(" ")[0] for sql, _binds in peer_port.writes] == ["update", "insert"]
    assert [sql.split(" ")[0] for sql, _binds in ours_port.writes] == ["update"]


def test_each_interleaved_group_runs_at_its_own_first_writes_instant() -> None:
    # The concurrent group's first write is `at` September and ours is `at`
    # October, so the two closes stamp two different instants: one Clock shared by
    # both sessions would stamp both with the same one.
    run, ours_port, peer_port = _race()

    (close, insert) = peer_port.writes
    assert close[1][0] == _SEP
    assert insert[1][3] == _SEP
    assert ours_port.writes[0][1][0] == _OCT
    assert [e.binds[0] for e in run.emissions if e.sql.startswith("update")] == [_SEP, _OCT]


def test_a_temporal_write_settles_against_its_own_groups_reading() -> None:
    # Ours read a milestone opened in March, the concurrent group one opened in
    # February. Each close gates on the start its own group read, which no
    # case-wide account of the fixtures could have answered for both.
    _run, ours_port, peer_port = _race(ours_reads=([_balance(2, in_z=_MAR)],))

    assert peer_port.writes[0][1][-1] == _FEB
    assert ours_port.writes[0][1][-1] == _MAR


def test_the_race_fate_follows_the_port_rather_than_any_model_of_the_other_session() -> None:
    # Nothing models the concurrent group's commit: the losing close is a
    # conflict only because the database answered zero rows. Answered one, both
    # groups commit.
    run, _ours_port, _peer_port = _race(ours_affected=(1,))

    assert run.units == {"ours": {"outcome": "committed"}, "concurrent": {"outcome": "committed"}}


class _TableReadPort(ScriptedPort):
    """A caller port recording how many writes each group session had delivered
    when the tables were read back."""

    def __init__(self, sessions: Sequence[ScriptedPort], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sessions = sessions
        self.delivered_at_read: list[list[int]] = []

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        self.delivered_at_read.append([len(session.writes) for session in self._sessions])
        return super().execute(sql, binds, document_reads)


def test_a_race_stating_its_final_tables_reads_them_once_after_both_groups_joined() -> None:
    ours_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]], write_affected=[0])
    peer_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]], write_affected=[1, 1])
    table = [_balance(2, in_z=_SEP, value="999.00")]
    caller = _TableReadPort((ours_port, peer_port), read_rows=[table])

    run = run_interleaved_scenario_case(
        _load_case("m-temporal-read-010"), caller, _ScriptedExecutions(ours_port, peer_port)
    )

    assert [sql.split(" from ")[1] for sql, _binds in caller.reads] == ["balance"]
    assert caller.delivered_at_read == [[1, 2]]
    assert run.table_state is not None
    assert [row["val"] for row in run.table_state["balance"]] == ["999.00"]


def _race_case(
    ours: Sequence[Mapping[str, object]],
    concurrent: Sequence[Mapping[str, object]],
    model: str = "models/balance.yaml",
) -> case_format.Case:
    """A two-group scenario over ``model``: ``ours``'s steps, then
    ``concurrent``'s, then ``ours``'s last step — so the groups interleave."""
    steps = [
        *({"uow": "ours", **step} for step in ours[:-1]),
        *({"uow": "concurrent", **step} for step in concurrent),
        {"uow": "ours", **ours[-1]},
    ]
    return case_format.Case(
        path=Path("m-temporal-read-999-synthetic.yaml"),
        case_id="m-temporal-read-999",
        shape="scenario",
        tags=("m-temporal-read", "slice-snapshot-1"),
        model=model,
        document={
            "model": model,
            "when": {"uow": {"concurrency": "optimistic"}, "scenario": steps},
            "then": {"roundTrips": 0},
        },
    )


def _find_balance(key: int) -> dict[str, object]:
    return {
        "objectQuery": {
            "target": "parallax.compatibility.Balance",
            "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": key}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    }


def _balance_write(mutation: str, row: Mapping[str, object], **fields: object) -> dict[str, object]:
    entry = {
        "mutation": mutation,
        "entity": "parallax.compatibility.Balance",
        "rows": [dict(row)],
        "at": "2024-10-01T00:00:00+00:00",
        **fields,
    }
    return {"write": [entry]}


@pytest.mark.parametrize(
    ("reference", "gate"),
    [({"on": 0}, _FEB), ({"on": 1}, _MAR), ({}, _MAR)],
    ids=["first-find-named", "second-find-named", "latest-reading"],
)
def test_a_grouped_temporal_write_settles_against_the_find_it_names_else_the_latest(
    reference: dict[str, object], gate: dt.datetime
) -> None:
    case = _race_case(
        [
            _find_balance(2),
            _find_balance(2),
            _balance_write("terminate", {"id": 2}, **reference),
        ],
        [_find_balance(1)],
    )
    ours_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)], [_balance(2, in_z=_MAR)]])
    peer_port = ScriptedPort(read_rows=[[_balance(1, in_z=_FEB)]])

    run_interleaved_scenario_case(case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port))

    ((_sql, binds),) = ours_port.writes
    assert binds[-1] == gate


def test_a_temporal_write_of_a_key_its_group_inserted_is_refused() -> None:
    # The group's own insert is the value the write would be handed, and it
    # carries no reading: what the write settles against is a buffered write.
    case = _race_case(
        [
            _balance_write("insert", {"id": 7, "acctNum": "G", "value": "1.00"}),
            _balance_write("terminate", {"id": 7}),
        ],
        [_find_balance(1)],
    )
    executions = _ScriptedExecutions(
        ScriptedPort(), ScriptedPort(read_rows=[[_balance(1, in_z=_FEB)]])
    )

    with pytest.raises(EngineError, match="composes onto the row its own `uow` group inserted"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)


def test_a_second_temporal_write_of_a_key_its_group_settled_is_refused() -> None:
    case = _race_case(
        [
            _find_balance(2),
            _balance_write("terminate", {"id": 2}, on=0),
            _balance_write("update", {"id": 2, "value": "5.00"}, on=0),
        ],
        [_find_balance(1)],
    )
    executions = _ScriptedExecutions(
        ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]]),
        ScriptedPort(read_rows=[[_balance(1, in_z=_FEB)]]),
    )

    with pytest.raises(EngineError, match="a second temporal write"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)


def test_a_temporal_write_needing_coverage_its_reading_does_not_hold_is_refused() -> None:
    # A plain terminate from the start of a BOUNDED rectangle reaches the
    # rectangle after it, which no read of the group observed: its flush would
    # read that coverage itself, and what it would find includes the other
    # session's commits, which this lane does not model.
    jan = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    jun = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    bounded: MappingRow = {
        "pos_id": 1,
        "acct_num": "A",
        "val": decimal.Decimal("100.00"),
        "from_z": jan,
        "thru_z": jun,
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }
    find = {
        "objectQuery": {
            "target": "parallax.compatibility.Position",
            "predicate": {"eq": {"attr": "parallax.compatibility.Position.id", "value": 1}},
            "temporal": {
                "valid-time": {"asOf": "2024-01-01T00:00:00.000000Z"},
                "transaction-time": {"asOf": "latest"},
            },
        }
    }
    terminate = {
        "write": [
            {
                "mutation": "terminate",
                "entity": "parallax.compatibility.Position",
                "rows": [{"id": 1}],
                "validFrom": "2024-01-01T00:00:00.000000Z",
                "at": "2024-10-01T00:00:00+00:00",
                "on": 0,
            }
        ]
    }
    case = _race_case([find, terminate], [find], "models/position.yaml")
    executions = _ScriptedExecutions(
        ScriptedPort(read_rows=[[bounded]]), ScriptedPort(read_rows=[[bounded]])
    )

    with pytest.raises(EngineError, match="tracks no case state to bind it to"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)
