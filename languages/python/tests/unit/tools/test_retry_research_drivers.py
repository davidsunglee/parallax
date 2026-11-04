"""The transaction-isolation research drivers' public retry surface.

Each driver is driven through its own functions against a scripted transaction
receiver, so these pin the keyword a driver passes and what it reports. The
drivers' database path is what their smoke commands exercise, and
``check_retry_reports.py``'s functions are graded here over synthetic reports.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from parallax.core.execution import AdaptiveBackoff, RetryPolicy

_SCRIPTS = Path(__file__).resolve().parents[5] / "docs/research/transaction-isolation/scripts"


def _script(name: str) -> Any:
    sys.path.insert(0, str(_SCRIPTS))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(_SCRIPTS))


_support = _script("_support")
contention = _script("contention")
guard_wal = _script("guard_wal")
lock_snapshot_trace = _script("lock_snapshot_trace")
predicate_in_place = _script("predicate_in_place")
reports = _script("check_retry_reports")

_BUILT_IN_BACKOFF = {"baseDelay": 0.008, "maxDelay": 1.0}
_DISABLED: dict[str, object] = {"maxRetries": 0, "backoff": _BUILT_IN_BACKOFF}
_DEFAULT: dict[str, object] = {"maxRetries": 10, "backoff": _BUILT_IN_BACKOFF}


class _Receiver:
    """The public ``transact`` surface, recording each call's keywords."""

    def __init__(self) -> None:
        self.keywords: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def transact(self, body: Callable[[Any], object], /, **keywords: object) -> None:
        del body
        with self._lock:
            self.keywords.append(keywords)


@pytest.fixture
def receiver() -> _Receiver:
    return _Receiver()


@pytest.fixture
def scripted_environment(monkeypatch: pytest.MonkeyPatch, receiver: _Receiver) -> list[str]:
    """Each driver's provisioning helpers over ``receiver``, recording every reset."""

    @contextmanager
    def scoped(_adapter: object) -> Generator[_Receiver]:
        yield receiver

    class _Latency:
        def take(self) -> dict[str, object]:
            return {"roundTrips": 0.0, "meanRoundTripMs": None}

    def pooled(_run: object, _size: int) -> object:
        return object()

    def delayed(_adapter: object, _environment: object) -> tuple[object, _Latency]:
        return object(), _Latency()

    resets: list[str] = []

    def reset(_run: object, _rows: object) -> None:
        resets.append("reset")

    for driver in (contention, guard_wal):
        monkeypatch.setattr(driver, "pooled", pooled)
        monkeypatch.setattr(driver, "delayed", delayed)
        monkeypatch.setattr(driver, "reset", reset)
        monkeypatch.setattr(driver, "scoped", scoped)
    return resets


# --------------------------------------------------------------------------- #
# The keyword each driver passes, and the policy it reports.                   #
# --------------------------------------------------------------------------- #
def test_the_driver_policies_are_the_disabled_and_the_built_in_ones() -> None:
    assert RetryPolicy(max_retries=0) == _support.DISABLED_POLICY
    assert RetryPolicy() == _support.DEFAULT_POLICY
    assert list(_support.REPLAY_POLICIES) == ["disabled", "default"]


def test_a_policy_is_reported_whole_in_the_portable_spelling() -> None:
    tuned = RetryPolicy(max_retries=2, backoff=AdaptiveBackoff(base_delay=0.002, max_delay=0.05))
    assert _support.reported_policy(tuned) == {
        "maxRetries": 2,
        "backoff": {"baseDelay": 0.002, "maxDelay": 0.05},
    }


def test_contention_passes_its_policy_through_the_public_keyword(receiver: _Receiver) -> None:
    policy = RetryPolicy(max_retries=4)

    run = contention.run_mode(receiver, 2, 3, "hot", "tuned", policy, "read_committed")

    assert all(
        keywords == {"isolation": "read_committed", "retry": policy}
        for keywords in receiver.keywords
    )
    assert all(keywords["retry"] is policy for keywords in receiver.keywords)
    assert len(receiver.keywords) == 6
    assert (run["keys"], run["policy"]) == ("hot", "tuned")
    assert run["retry"] == _support.reported_policy(policy)
    assert "maxRetries" not in run
    assert "backoff" not in run
    assert len(run["samples"]) == 6


def test_the_grid_is_nine_adaptive_public_policies_under_the_default_bound() -> None:
    candidates = contention.adaptive_policies()

    assert list(candidates) == [
        "adaptive-0.5/25",
        "adaptive-0.5/100",
        "adaptive-0.5/400",
        "adaptive-2/25",
        "adaptive-2/100",
        "adaptive-2/400",
        "adaptive-8/25",
        "adaptive-8/100",
        "adaptive-8/400",
    ]
    assert candidates["adaptive-2/100"] == RetryPolicy(
        backoff=AdaptiveBackoff(base_delay=0.002, max_delay=0.1)
    )


@pytest.mark.parametrize(
    ("grid", "expected"),
    [(False, ["disabled", "default"]), (True, ["disabled", *contention.adaptive_policies()])],
    ids=["normal", "grid"],
)
def test_contention_measures_each_mode_s_policies_in_order(grid: bool, expected: list[str]) -> None:
    assert list(contention.measured_policies(grid)) == expected


def test_contention_runs_both_policies_and_key_modes_in_an_environment(
    receiver: _Receiver, scripted_environment: list[str]
) -> None:
    environment = _support.ENVIRONMENTS[2]

    runs = contention.environment_runs(object(), {}, 2, 1, "read_committed", environment)

    assert [(run["policy"], run["keys"]) for run in runs] == [
        ("disabled", "hot"),
        ("disabled", "disjoint"),
        ("default", "hot"),
        ("default", "disjoint"),
    ]
    assert [run["retry"] for run in runs] == [_DISABLED, _DISABLED, _DEFAULT, _DEFAULT]
    assert all(run["environment"] == environment.name for run in runs)
    assert all("replayWaits" not in run for run in runs)
    assert scripted_environment == ["reset"] * 4
    assert receiver.keywords[0]["retry"] is _support.DISABLED_POLICY


def test_the_guard_replay_passes_its_policy_through_the_public_keyword(
    receiver: _Receiver,
) -> None:
    policy = RetryPolicy(max_retries=4)

    run = guard_wal.guard_replay(receiver, 2, 3, "repeatable_read", "tuned", policy)

    assert all(
        keywords == {"isolation": "repeatable_read", "retry": policy}
        for keywords in receiver.keywords
    )
    assert run["policy"] == "tuned"
    assert run["retry"] == _support.reported_policy(policy)
    assert len(run["samples"]) == 6


def test_the_guard_replays_both_policies_in_every_environment(
    receiver: _Receiver, scripted_environment: list[str]
) -> None:
    runs = guard_wal.environment_replays(object(), {}, 2, 1, "repeatable_read")

    assert [(run["environment"], run["policy"]) for run in runs] == [
        (environment.name, policy)
        for environment in _support.ENVIRONMENTS
        for policy in ("disabled", "default")
    ]
    assert all("replayWaits" not in run for run in runs)
    assert len(scripted_environment) == 7, "one reset for the warm-up and one per replay"


@pytest.mark.parametrize(
    ("policy", "keywords"),
    [
        (
            _support.DISABLED_POLICY,
            {"isolation": "serializable", "retry": _support.DISABLED_POLICY},
        ),
        (None, {"isolation": "serializable"}),
    ],
    ids=["explicit-disabled", "omitted-default"],
)
def test_the_trace_keeps_explicit_disabled_and_omitted_default_apart(
    receiver: _Receiver, policy: RetryPolicy | None, keywords: dict[str, object]
) -> None:
    def body(_tx: object) -> None:
        return None

    run = lock_snapshot_trace._transaction(receiver, body, policy, "serializable")

    run()

    assert receiver.keywords == [keywords]


def test_statement_extraction_stays_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    receiver = _Receiver()

    @contextmanager
    def scoped(_adapter: object) -> Generator[_Receiver]:
        yield receiver

    class _Recording:
        def take(self) -> list[dict[str, object]]:
            return [{"kind": "write", "sql": "delete", "binds": []}]

    class _Run:
        port = object()

    def recorded(_port: object) -> tuple[object, _Recording]:
        return object(), _Recording()

    monkeypatch.setattr(predicate_in_place, "recorded", recorded)
    monkeypatch.setattr(predicate_in_place, "scoped", scoped)

    predicate_in_place.emitted(_Run(), "delete", "own")

    assert receiver.keywords == [{"retry": _support.DISABLED_POLICY}]


# --------------------------------------------------------------------------- #
# The report checks, over synthetic reports.                                   #
# --------------------------------------------------------------------------- #
def _run(policy: dict[str, object], **fields: object) -> dict[str, object]:
    return {
        "retry": policy,
        "summary": {"invocations": 6},
        "samples": [{"attempts": 1, "outcome": "committed"} for _ in range(6)],
        **fields,
    }


def _adaptive(base: float, cap: float) -> dict[str, object]:
    return {"maxRetries": 10, "backoff": {"baseDelay": base / 1000, "maxDelay": cap / 1000}}


def _contention_conditions() -> dict[str, object]:
    return {"workload": {"workers": 2, "invocationsPerWorker": 3}}


def _guard_conditions() -> dict[str, object]:
    return {"workload": {"writers": 2, "invocationsPerWriter": 3, "balances": 3}}


_ENVIRONMENTS = ("local", "rtt-2ms", "rtt-5ms+think")
_KEYS = ("hot", "disjoint")


def _grid() -> dict[str, Any]:
    candidates = {
        f"adaptive-{base:g}/{cap:g}": _adaptive(base, cap)
        for base in (0.5, 2, 8)
        for cap in (25, 100, 400)
    }
    return {
        "driver": "contention",
        "conditions": _contention_conditions(),
        "runs": [
            _run(policy, keys=keys) | {"policy": label}
            for label, policy in {"disabled": _DISABLED, **candidates}.items()
            for keys in _KEYS
        ],
    }


def _environments() -> dict[str, Any]:
    return {
        "driver": "contention",
        "conditions": _contention_conditions(),
        "runs": [
            _run(policy, environment=environment, keys=keys) | {"policy": label}
            for environment in _ENVIRONMENTS
            for label, policy in (("disabled", _DISABLED), ("default", _DEFAULT))
            for keys in _KEYS
        ],
    }


def _guard_normal() -> dict[str, Any]:
    return {
        "driver": "guard_wal",
        "conditions": _guard_conditions(),
        "wal": [{"mode": mode, "summary": {"writes": 3}} for mode in ("a", "b", "c")],
        "replay": [
            _run(_DISABLED) | {"policy": "disabled"},
            _run(_DEFAULT) | {"policy": "default"},
        ],
    }


def _guard_environments() -> dict[str, Any]:
    return {
        "driver": "guard_wal",
        "conditions": _guard_conditions(),
        "wal": [],
        "replay": [
            _run(policy, environment=environment) | {"policy": label}
            for environment in _ENVIRONMENTS
            for label, policy in (("disabled", _DISABLED), ("default", _DEFAULT))
        ],
    }


_VALID: dict[str, Callable[[], dict[str, Any]]] = {
    "grid.json": _grid,
    "environments.json": _environments,
    "guard-normal.json": _guard_normal,
    "guard-environments.json": _guard_environments,
}


def _runs(report: dict[str, Any]) -> list[dict[str, Any]]:
    return report["runs"] if "runs" in report else report["replay"]


@pytest.mark.parametrize("name", sorted(_VALID))
def test_a_valid_report_has_no_problem(name: str) -> None:
    assert reports.CHECKS[name](_VALID[name]()) == []


def test_the_grid_is_twenty_runs_and_the_environments_twelve_and_six() -> None:
    assert len(_grid()["runs"]) == 20
    assert len(_environments()["runs"]) == 12
    assert len(_guard_environments()["replay"]) == 6


@pytest.mark.parametrize("name", sorted(_VALID))
def test_a_missing_run_breaks_the_matrix(name: str) -> None:
    report = _VALID[name]()
    _runs(report).pop()
    assert any("expected" in problem for problem in reports.CHECKS[name](report))


@pytest.mark.parametrize("name", sorted(_VALID))
def test_a_run_may_not_state_a_partial_policy(name: str) -> None:
    report = _VALID[name]()
    _runs(report)[0]["retry"] = {"maxRetries": 0}
    assert any("retry must state" in problem for problem in reports.CHECKS[name](report))


@pytest.mark.parametrize(
    "backoff",
    [
        {"baseDelay": 0.008},
        {"baseDelay": 0.0, "maxDelay": 1.0},
        {"baseDelay": 2.0, "maxDelay": 1.0},
        {"baseDelay": float("inf"), "maxDelay": 1.0},
    ],
    ids=["missing-maximum", "zero-base", "inverted", "infinite"],
)
def test_a_run_may_not_state_an_invalid_backoff(backoff: dict[str, float]) -> None:
    report = _grid()
    report["runs"][0]["retry"] = {"maxRetries": 0, "backoff": backoff}
    assert any("run 0" in problem for problem in reports.check_grid(report))


def test_a_run_may_not_differ_from_the_policy_its_label_names() -> None:
    report = _grid()
    report["runs"][0]["retry"] = _DEFAULT
    assert any("expected" in problem for problem in reports.check_grid(report))


@pytest.mark.parametrize("field", ["maxRetries", "backoff", "replayWaits"])
def test_a_run_may_not_state_what_the_driver_no_longer_observes(field: str) -> None:
    report = _environments()
    report["runs"][0][field] = "immediate"
    assert any(field in problem for problem in reports.check_environments(report))


def test_a_run_holds_exactly_the_smokes_samples() -> None:
    report = _guard_environments()
    report["replay"][0]["samples"].pop()
    problems = reports.check_guard_environments(report)
    assert any("holds 5 samples" in problem for problem in problems)
    assert any("summary" in problem for problem in problems)


def test_an_attempt_past_its_policys_bound_is_a_failure() -> None:
    report = _environments()
    report["runs"][0]["samples"][0]["attempts"] = 2
    assert any("past the bound 0" in problem for problem in reports.check_environments(report))


@pytest.mark.parametrize("attempts", [0, "1", None, True], ids=["zero", "string", "none", "bool"])
def test_a_sample_states_a_positive_attempt_count(attempts: object) -> None:
    report = _grid()
    report["runs"][0]["samples"][0]["attempts"] = attempts
    assert any("attempts must be" in problem for problem in reports.check_grid(report))


@pytest.mark.parametrize("failure", ["TypeError", "ValueError", "AttributeError"])
def test_a_drivers_own_api_failure_is_a_failure(failure: str) -> None:
    report = _guard_normal()
    report["replay"][1]["samples"][0]["outcome"] = {"type": failure}
    assert any(failure in problem for problem in reports.check_guard_normal(report))


def test_a_conflict_the_workload_provokes_is_no_failure() -> None:
    report = _guard_normal()
    report["replay"][0]["samples"][0]["outcome"] = {"type": "DatabaseError"}
    assert reports.check_guard_normal(report) == []


def test_the_normal_guard_report_keeps_its_wal_workload() -> None:
    report = _guard_normal()
    report["wal"].pop()
    assert any("WAL modes" in problem for problem in reports.check_guard_normal(report))
    report = _guard_normal()
    report["wal"][0]["summary"]["writes"] = 2
    assert any("wrote 2" in problem for problem in reports.check_guard_normal(report))


def test_the_environment_guard_report_runs_no_wal_workload() -> None:
    report = _guard_environments()
    report["wal"] = _guard_normal()["wal"]
    assert any("WAL workload" in problem for problem in reports.check_guard_environments(report))


def test_a_report_of_another_load_or_driver_is_refused() -> None:
    report = _grid()
    report["driver"] = "guard_wal"
    report["conditions"]["workload"]["workers"] = 8
    problems = reports.check_grid(copy.deepcopy(report))
    assert any("driver is" in problem for problem in problems)
    assert any("workers" in problem for problem in problems)


def _write_reports(directory: Path) -> None:
    for name, report in _VALID.items():
        (directory / name).write_text(json.dumps(report()))


def test_the_smoke_directory_checks_all_four_fixed_names(tmp_path: Path) -> None:
    _write_reports(tmp_path)
    assert reports.check_smoke_dir(tmp_path) == []


def test_an_absent_or_malformed_report_is_a_problem(tmp_path: Path) -> None:
    _write_reports(tmp_path)
    (tmp_path / "grid.json").unlink()
    (tmp_path / "environments.json").write_text("{")
    problems = reports.check_smoke_dir(tmp_path)
    assert [problem.split(":")[0] for problem in problems] == ["grid.json", "environments.json"]


def test_the_command_exits_nonzero_on_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_retry_reports.py", "--smoke-dir", str(tmp_path)])

    with pytest.raises(SystemExit) as exited:
        reports.main()

    assert exited.value.code == 1
    assert "grid.json" in capsys.readouterr().err


def test_the_command_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_reports(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_retry_reports.py", "--smoke-dir", str(tmp_path)])

    reports.main()

    assert "4 reports OK" in capsys.readouterr().out
