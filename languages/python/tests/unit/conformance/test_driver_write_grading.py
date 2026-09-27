"""Driver-write zero-sign grading over the writes a case's modeled work hands
its driver, apart from the statements the case authors verbatim."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format, engine
from tests._support.driver_writes import RecordingCaseDatabase, assert_driver_write_zero_signs
from tests._support.sweep_goldens import write_golden_statements
from tests.unit.conformance._recording_ports import FakeWritePort

_CASE = next(case for case in case_format.load_cases() if case.case_id == "m-core-010")
_GOLDEN = write_golden_statements(_CASE)


def _grade(port: RecordingCaseDatabase) -> None:
    model = engine.load_case_metamodel(_CASE)
    assert_driver_write_zero_signs(model, port.dialect, _GOLDEN, port.writes)


def _write_verbatim(port: RecordingCaseDatabase, binds: list[object]) -> None:
    ((sql, _binds),) = _GOLDEN
    port.execute_write(port.dialect.to_driver_sql(sql), binds)


def _write_modeled(port: RecordingCaseDatabase, binds: list[object]) -> None:
    ((sql, _binds),) = _GOLDEN
    port.transaction(
        lambda connection: connection.execute_write(connection.dialect.to_driver_sql(sql), binds)
    )


def test_a_verbatim_write_of_the_golden_statement_does_not_stand_in_for_the_modeled_one() -> None:
    port = RecordingCaseDatabase(FakeWritePort())
    _write_verbatim(port, [1, 0.0, 0.0])
    _write_modeled(port, [1, 0.0, -0.0])
    with pytest.raises(AssertionError, match=r"^driver bind 2: "):
        _grade(port)


def test_a_golden_write_only_a_verbatim_statement_spelled_is_refused() -> None:
    port = RecordingCaseDatabase(FakeWritePort())
    _write_verbatim(port, [1, 0.0, 0.0])
    with pytest.raises(AssertionError, match=r"^the driver writes are not the golden writes"):
        _grade(port)


def test_a_modeled_write_carrying_the_golden_zero_sign_passes() -> None:
    port = RecordingCaseDatabase(FakeWritePort())
    _write_verbatim(port, [1, 0.0, -0.0])
    _write_modeled(port, [1, 0.0, 0.0])
    _grade(port)
