"""The interleaved ``uow`` lane over two scripted sessions: its refusals, the
sessions it releases, and what the interleaved run sweep leaves ungraded — each
step's exact pointer, an interleaved group's `stepAffectedRows`, a fate taken
from the database rather than the case, the tables read once both groups have
joined, and a forced flush's coverage read kept off the find that forced it.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import decimal
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance._database_control import TerminationReport
from parallax.conformance._lanes.interleaved import run_interleaved_scenario_case
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.core.base import INFINITY
from parallax.core.db_port import MappingRow, Row
from parallax.core.dialect import Dialect
from parallax.core.execution import RetryPolicy, TxnOptions
from parallax.snapshot import ScopedDatabase
from tests._support.case_corpus import case as corpus_case
from tests._support.root_ownership import own_root
from tests.unit.conformance._lanes._scripted_port import ScriptedPort
from tests.unit.conformance._wire_value_support import wire_value


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of sweep
    # reachability: these lane-level tests exercise
    # `run_interleaved_scenario_case` on its own terms, never gated on whether
    # the case has ALSO been flipped visible in the sweep.
    return corpus_case(case_id)


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
        observation: LifecycleObservation,
        options: TxnOptions | None = None,
        clock: Any = None,
        trusted: bool = True,
    ) -> None:
        self.port = port
        self.options = options
        self.trusted = trusted
        self.closed = False
        self.cancel_calls = 0
        self.terminate_calls = 0
        self._database = own_root(
            observation.connect(port, model, options=options, clock=clock)
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
        observation: LifecycleObservation,
        options: TxnOptions | None = None,
        clock: Any = None,
    ) -> Any:
        index = len(self.opened)
        if index == self._refuse_at:
            raise RuntimeError("this session could not be opened")
        execution = _ScriptedExecution(
            self._ports[index],
            model,
            observation=observation,
            options=options,
            clock=clock,
            trusted=self._trusted[index],
        )
        self.opened.append(execution)
        return execution


def _wire_row(row: MappingRow) -> dict[str, object]:
    """One authored row as the Wire spelling a find step's own rows carry."""
    return {key: wire_value(value) for key, value in row.items()}


def test_run_interleaved_scenario_case_renders_the_conflict_and_discards_the_abort() -> None:
    # `m-concurrency-012` end to end over two SCRIPTED fake connections (never a
    # real database): the `ours` group's own observing find (step 0) is stale
    # by the time it flushes (step 3) — the `concurrent` group (steps 1-2)
    # committed its own gated update first — so the doomed group's SECOND
    # write (the version-gated update) affects 0 rows, and the group's own
    # buffered insert (account 9) is discarded with it. The trailing
    # ungrouped verify find (step 4) observes no rows for it.
    case = _load_case("m-concurrency-012")
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
    assert run.database_calls == 6
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


def test_each_interleaved_groups_predicate_write_reports_the_count_its_verb_returned() -> None:
    case = dataclasses.replace(
        _synthetic_write(
            "scenario",
            {
                "model": "models/wallet.yaml",
                "when": {
                    "uow": {"concurrency": "optimistic"},
                    "scenario": [
                        {
                            "uow": "x",
                            "write": [
                                {
                                    "mutation": "insert",
                                    "entity": "Wallet",
                                    "rows": [{"id": 9, "owner": "Turing", "balance": "5.00"}],
                                }
                            ],
                        },
                        {
                            "uow": "x",
                            "write": {
                                "mutation": "amend",
                                "target": {
                                    "entity": "Wallet",
                                    "predicate": {
                                        "lessThan": {"path": "Wallet.balance", "value": "100.00"}
                                    },
                                },
                                "assignments": [{"attr": "Wallet.owner", "value": "Ada"}],
                            },
                            "expectAffectedRows": 2,
                        },
                        {
                            "uow": "y",
                            "write": {
                                "mutation": "delete",
                                "target": {
                                    "entity": "Wallet",
                                    "predicate": {
                                        "lessThan": {"path": "Wallet.balance", "value": "0.00"}
                                    },
                                },
                            },
                            "expectAffectedRows": 0,
                        },
                    ],
                },
                "then": {"databaseCalls": 3},
            },
        ),
        model="models/wallet.yaml",
    )
    ours_port = ScriptedPort(write_affected=[1, 2])
    peer_port = ScriptedPort(write_affected=[0])

    run = run_interleaved_scenario_case(
        case, ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    # The insert's statement ran in the same Flush, but the count is the
    # predicate statement's own.
    assert [sql.split(" ")[0] for sql, _ in ours_port.writes] == ["insert", "update"]
    assert run.step_affected_rows == [
        {"at": "/scenario/1", "affectedRows": 2},
        {"at": "/scenario/2", "affectedRows": 0},
    ]


def test_run_interleaved_scenario_case_reraises_an_unexpected_worker_failure() -> None:
    # A worker thread's own UNEXPECTED defect (never a witnessed path) must
    # surface loudly on the main thread rather than hang the choreography —
    # `Turnstile.release_all` unsticks the partner thread (blocked on
    # `wait_for` a later step that now never arrives) so `thread.join()`
    # itself never hangs either.
    case = _load_case("m-concurrency-012")
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
    case = _load_case("m-concurrency-012")
    healthy_row: MappingRow = {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
    ours_port = ScriptedPort(read_rows=[[healthy_row]])
    peer_port = ScriptedPort(read_rows=[[healthy_row]])
    executions = _ScriptedExecutions(ours_port, peer_port, trusted=trusted)

    with pytest.raises(UnclassifiedEngineError, match="refuses to start") as raised:
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
    case = _load_case("m-concurrency-012")
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
    case = _own_copy(_load_case("m-concurrency-012"))
    when = cast("dict[str, Any]", case.document["when"])
    steps = cast("list[dict[str, Any]]", when["scenario"])
    steps[0]["expectGraph"] = {"Account": [{"id": 2}]}

    with pytest.raises(UnclassifiedEngineError, match="fills no `stepGraphs` channel"):
        run_interleaved_scenario_case(
            case, ScriptedPort(), _ScriptedExecutions(ScriptedPort(), ScriptedPort())
        )


def _with_option_placement(
    placement: Mapping[str, Mapping[str, object]],
) -> case_format.Case:
    """`m-concurrency-012` with each block of ``placement`` merged into its document."""
    case = _own_copy(_load_case("m-concurrency-012"))
    document = cast("dict[str, Any]", case.document)
    for group, fields in placement.items():
        document[group] = {**cast("Mapping[str, Any]", document.get(group) or {}), **fields}
    return case


_OPTIMISTIC_ONLY: Final = {"concurrency": "optimistic"}


@pytest.mark.parametrize(
    ("placement", "bound"),
    [
        ({"when": {"uow": _OPTIMISTIC_ONLY}}, 10),
        ({"when": {"uow": {**_OPTIMISTIC_ONLY, "retry": {"maxRetries": 1}}}}, 1),
        (
            {
                "given": {"databaseOptions": {"retry": {"maxRetries": 3}}},
                "when": {"uow": _OPTIMISTIC_ONLY},
            },
            3,
        ),
    ],
)
def test_an_interleaved_case_grading_a_conflict_abort_under_a_positive_bound_is_refused(
    placement: Mapping[str, Mapping[str, object]], bound: int
) -> None:
    # Each group is one turnstile-sequenced production attempt, and production
    # replays an optimistic conflict within a positive bound — the built-in or
    # one the root or the invocation names — so the abort the case grades
    # would never be its group's fate. Refused before either session is asked
    # for.
    case = _with_option_placement(placement)
    executions = _ScriptedExecutions(ScriptedPort(), ScriptedPort())

    with pytest.raises(UnclassifiedEngineError, match=f"under `maxRetries: {bound}`"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)
    assert executions.opened == []


def test_a_case_grading_a_group_rolled_back_before_its_peers_last_step_is_refused() -> None:
    # `m-concurrency-012` with the two groups' writes swapped: the rolled-back
    # group's last step now comes before the concurrent group's write, and
    # nothing would hand that write its turn once the group rolled back. Refused
    # before either session is asked for.
    case = _own_copy(_load_case("m-concurrency-012"))
    when = cast("dict[str, Any]", case.document["when"])
    steps = cast("list[dict[str, Any]]", when["scenario"])
    steps[2], steps[3] = steps[3], steps[2]
    executions = _ScriptedExecutions(ScriptedPort(), ScriptedPort())

    with pytest.raises(UnclassifiedEngineError, match=r"'ours' is graded rolled back.*\[3\]"):
        run_interleaved_scenario_case(case, ScriptedPort(), executions)
    assert executions.opened == []


def test_a_group_production_replays_fails_rather_than_re_running_its_steps() -> None:
    # A group whose conflict the case does not grade, under a bound that
    # admits a replay: production enters the group's callback a second time,
    # past a turnstile that already passed its steps, and the lane refuses that
    # attempt instead of waiting on it.
    case = _with_option_placement(
        {"when": {"uow": {**_OPTIMISTIC_ONLY, "retry": {"maxRetries": 1}}}}
    )
    then = cast("dict[str, Any]", case.document["then"])
    then["units"] = {}
    row_v1: MappingRow = {
        "id": 2,
        "owner": "Linus",
        "balance": decimal.Decimal("250.00"),
        "version": 1,
    }
    caller_port = ScriptedPort(read_rows=[[]])
    ours_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1, 0])
    peer_port = ScriptedPort(read_rows=[[row_v1]], write_affected=[1])

    with pytest.raises(
        UnclassifiedEngineError, match="production replayed an interleaved `uow` group"
    ):
        run_interleaved_scenario_case(case, caller_port, _ScriptedExecutions(ours_port, peer_port))
    assert len(ours_port.levels) == 2


def test_each_interleaved_group_is_composed_over_the_cases_own_root_record() -> None:
    # The lane never connects a Database itself; it asks the factory for one
    # per group, and what it hands the factory is the case's root record — so a
    # root the case configures reaches both dedicated sessions' Handles, and
    # each group's transaction opens at the root's level while the request
    # carries only what `when.uow` authored.
    case = _load_case("m-concurrency-012")
    document = dict(case.document)
    document["given"] = {
        **cast("Mapping[str, Any]", document.get("given") or {}),
        "databaseOptions": {"isolation": "serializable", "retry": {"maxRetries": 0}},
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
    assert expected == TxnOptions(isolation="serializable", retry=RetryPolicy(max_retries=0))
    assert [execution.options for execution in executions.opened] == [expected, expected]
    assert ours_port.levels == ["serializable"]
    assert peer_port.levels == ["serializable"]
    assert caller_port.levels == []


_FEB = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_JUN = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_SEP = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _balance(key: int, *, in_z: dt.datetime, value: str = "200.00") -> MappingRow:
    """One current Transaction-Time-Only `Balance` milestone, as a find reads it."""
    return {
        "bal_id": key,
        "acct_num": "B",
        "val": decimal.Decimal(value),
        "in_z": in_z,
        "out_z": INFINITY,
    }


def test_the_race_fate_follows_the_port_rather_than_any_model_of_the_other_session() -> None:
    # `m-temporal-read-010` states the losing close rolled back, but a group's
    # fate is what the database answered: answered one row, both groups commit.
    ours_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]], write_affected=[1])
    peer_port = ScriptedPort(read_rows=[[_balance(2, in_z=_FEB)]], write_affected=[1, 1])

    run = run_interleaved_scenario_case(
        _load_case("m-temporal-read-010"), ScriptedPort(), _ScriptedExecutions(ours_port, peer_port)
    )

    assert run.units == {"ours": {"outcome": "committed"}, "concurrent": {"outcome": "committed"}}


class _TableReadPort(ScriptedPort):
    """A caller port recording how many writes each group session had delivered
    when the tables were read back."""

    def __init__(self, sessions: Sequence[ScriptedPort], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sessions = sessions
        self.delivered_at_read: list[list[int]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        self.delivered_at_read.append([len(session.writes) for session in self._sessions])
        return super().execute(sql, binds, document_reads, read_only=read_only)


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
    model: str,
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
            "then": {"databaseCalls": 0},
        },
    )


_BOUNDED: Final[MappingRow] = {
    "pos_id": 1,
    "acct_num": "A",
    "val": decimal.Decimal("100.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": _JUN,
    "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}
_FOLLOWING: Final[MappingRow] = {
    **_BOUNDED,
    "val": decimal.Decimal("200.00"),
    "from_z": _JUN,
    "thru_z": INFINITY,
}
_POSITION_FIND: Final[dict[str, object]] = {
    "objectQuery": {
        "target": "parallax.compatibility.Position",
        "predicate": {"eq": {"path": "parallax.compatibility.Position.id", "value": 1}},
        "temporal": {
            "valid-time": {"asOf": "2024-01-01T00:00:00.000000Z"},
            "transaction-time": {"asOf": "latest"},
        },
    }
}
# A plain terminate from the start of a BOUNDED rectangle reaches the rectangle
# after it, which no read of the group observed.
_UNBOUNDED_TERMINATE: Final[dict[str, object]] = {
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


def _coverage_race(ours: Sequence[Mapping[str, object]]) -> tuple[Any, ScriptedPort]:
    ours_port = ScriptedPort(read_rows=[[_BOUNDED], [_FOLLOWING], [_BOUNDED]])
    run = run_interleaved_scenario_case(
        _race_case(ours, [_POSITION_FIND], "models/position.yaml"),
        ScriptedPort(),
        _ScriptedExecutions(ours_port, ScriptedPort(read_rows=[[_BOUNDED]])),
    )
    return run, ours_port


def _closed_ends(run: Any) -> list[tuple[str, object]]:
    return [(e.case_pointer, e.binds[2]) for e in run.emissions if e.sql.startswith("update")]


def test_a_finds_force_flush_reads_coverage_it_never_reports_as_the_finds_own() -> None:
    run, ours_port = _coverage_race([_POSITION_FIND, _UNBOUNDED_TERMINATE, _POSITION_FIND])

    assert len(ours_port.reads) == 3
    assert _closed_ends(run) == [("/scenario/1/write", _JUN), ("/scenario/1/write", "infinity")]
    finds = [(e.case_pointer, e.sql) for e in run.emissions if e.sql.startswith("select")]
    assert [pointer for pointer, _sql in finds] == [
        "/scenario/0/objectQuery",
        "/scenario/2/objectQuery",
        "/scenario/3/objectQuery",
    ]
    assert len({sql for _pointer, sql in finds}) == 1
    assert run.database_calls == 6
