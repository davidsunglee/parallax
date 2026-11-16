"""The pooled primary-key live diagnostic, and the refusals that keep its readings honest.

The database-backed test runs every frozen case. Without an output file it runs
each case once and grades it; ``tools/pooled_primary_key_diagnostic.py`` names
an output file, which makes the same test take the capture protocol and write
its readings there. Either way a case that tallies other calls or acquisitions
than it expects, or stores anything but its own inserts, fails.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from parallax.core.execution_lifecycle import (
    AcquisitionFinished,
    AcquisitionStarted,
    ConnectionAcquired,
    DatabaseCallFinished,
    DatabaseCallNotExecuted,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    ExecutionEvent,
)
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.snapshot import connect
from tests._support.bindings import TEST_BINDING
from tests._support.pooled_key_diagnostic import (
    MODE_VARIABLE,
    OUT_VARIABLE,
    DiagnosticRefused,
    requested,
    write_readings,
)
from tests._support.root_ownership import own_root
from tests.api._pooled_primary_key_diagnostic_support import (
    CASES,
    CHECK,
    MODEL,
    CallCounter,
    Case,
    CaseReading,
    Protocol,
    Tally,
    capture_protocol,
    check_stored,
    readings_document,
    run_case,
)


def _server_version(profile_run: Any) -> str:
    control = profile_run.control()
    try:
        ((version,),) = control.execute("show server_version", [])
    finally:
        control.close()
    return str(version)


def _graded(profile_run: Any, case: Case, protocol: Protocol) -> CaseReading:
    """``case`` run on a fresh root over freshly provisioned tables, then
    graded by what it stored."""
    profile_run.reset(model_of(MODEL), {}, TEST_BINDING)
    counter = CallCounter()
    root = own_root(
        connect(profile_run.port, MODEL, binding=TEST_BINDING, lifecycle_provider=counter)
    )
    reading = run_case(root.using_database_login(), counter, case, protocol)
    root.close()
    check_stored(profile_run, case, 1 + protocol.warmup + protocol.repeats)
    return reading


def test_every_frozen_case_tallies_and_stores_only_its_inserts(profile_run: Any) -> None:
    # A capture first runs every case once unrecorded, so no case's first
    # reading pays for warming the process rather than for its own root.
    mode, out = requested()
    if out is None:
        readings = [_graded(profile_run, case, CHECK) for case in CASES]
    else:
        for case in CASES:
            _graded(profile_run, case, CHECK)
        readings = [_graded(profile_run, case, capture_protocol(case)) for case in CASES]
    document = readings_document(mode, readings, _server_version(profile_run))
    if out is not None:
        write_readings(out, "live", document)


# --------------------------------------------------------------------------- #
# Refusals: a counter, a case, or an output the readings cannot be trusted     #
# through.                                                                     #
# --------------------------------------------------------------------------- #

_EXECUTION = uuid.uuid4()
_STATEMENT = LoweredStatement("select 1")


def _counted(*events: ExecutionEvent) -> CallCounter:
    counter = CallCounter()
    handler = counter.open(None)  # pyright: ignore[reportArgumentType] - the counter reads no descriptor
    assert handler is not None
    for event in events:
        handler.handle(event)
    return counter


def _call_started(activity: int) -> DatabaseCallStarted:
    return DatabaseCallStarted(_EXECUTION, activity, activity, 1, "t", "read", _STATEMENT)


def _call_finished(activity: int, outcome: Any) -> DatabaseCallFinished:
    return DatabaseCallFinished(_EXECUTION, activity + 1, activity, 1, _STATEMENT, 0, outcome)


def _acquisition(activity: int) -> tuple[AcquisitionStarted, AcquisitionFinished]:
    return (
        AcquisitionStarted(_EXECUTION, activity, activity, 1, "writer_only"),
        AcquisitionFinished(
            _EXECUTION, activity + 1, activity, 1, 0, ConnectionAcquired("writer", None)
        ),
    )


def test_the_counter_tallies_completed_calls_and_acquisitions() -> None:
    counter = _counted(
        *_acquisition(2), _call_started(4), _call_finished(4, DatabaseReadCompleted(0))
    )
    assert counter.take() == Tally(acquisitions=1, reads=1)


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        ((_call_started(4),), "database call 4 never finished"),
        ((_call_finished(4, DatabaseReadCompleted(0)),), "database call 4 finished unstarted"),
        (
            (_call_started(4), _call_finished(4, DatabaseCallNotExecuted())),
            "database call 4 did not complete",
        ),
        ((_acquisition(2)[0],), "acquisition 2 never finished"),
        ((_acquisition(2)[1],), "acquisition 2 finished unstarted"),
    ],
    ids=[
        "unfinished-call",
        "unstarted-call",
        "incomplete-call",
        "unfinished-acquisition",
        "unstarted-acquisition",
    ],
)
def test_the_counter_refuses_what_did_not_complete(
    events: tuple[ExecutionEvent, ...], reason: str
) -> None:
    with pytest.raises(DiagnosticRefused, match=reason):
        _counted(*events).take()


class _Idle:
    """A database whose transactions run nothing, so they tally nothing."""

    def transact(self, body: object) -> None:
        del body


def test_a_case_tallying_other_work_than_it_expects_is_refused() -> None:
    (case, *_rest) = CASES
    with pytest.raises(DiagnosticRefused, match=f"{case.id} made Tally"):
        run_case(_Idle(), CallCounter(), case, CHECK)


class _Stored:
    def __init__(self, count: int, least: int, greatest: int, labels: list[str]) -> None:
        self._answers: list[list[tuple[object, ...]]] = [
            [(count, least, greatest)],
            [(label,) for label in labels],
        ]

    def execute(self, sql: str, binds: list[object]) -> list[tuple[object, ...]]:
        return self._answers.pop(0)


class _Run:
    def __init__(self, port: _Stored) -> None:
        self.port = port


@pytest.mark.parametrize(
    "stored",
    [
        _Stored(2, 1, 2, ["inserted"]),
        _Stored(3, 1, 4, ["inserted"]),
        _Stored(3, 1, 3, ["inserted", "amended"]),
    ],
    ids=["missing-rows", "unexpected-keys", "unexpected-label"],
)
def test_a_case_storing_anything_but_its_inserts_is_refused(stored: _Stored) -> None:
    (case, *_rest) = CASES
    check_stored(_Run(_Stored(3, 1, 3, ["inserted"])), case, 3)
    with pytest.raises(DiagnosticRefused, match=f"{case.id} stored"):
        check_stored(_Run(stored), case, 3)


def test_readings_missing_a_frozen_case_are_refused() -> None:
    (case, *_rest) = CASES
    reading = CaseReading(case, CHECK, 0, 0, [0], [0])
    with pytest.raises(DiagnosticRefused, match="not every frozen case"):
        readings_document("assigned", [reading], "18")


def test_an_unknown_mode_or_a_missing_output_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(MODE_VARIABLE, "unpooled")
    with pytest.raises(DiagnosticRefused, match="mode 'unpooled'"):
        requested()
    monkeypatch.setenv(MODE_VARIABLE, "assigned")
    monkeypatch.setenv(OUT_VARIABLE, str(tmp_path / "absent"))
    with pytest.raises(DiagnosticRefused, match="does not exist"):
        requested()
    monkeypatch.setenv(OUT_VARIABLE, str(tmp_path))
    assert requested() == ("assigned", tmp_path)
