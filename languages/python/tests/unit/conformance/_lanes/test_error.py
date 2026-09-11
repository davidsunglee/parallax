"""The error lane's trigger parsing, driven against a fake in-memory
``m-db-port`` (no Docker): what an authored ``then.statements`` trigger reaches
the port as, and the refusal of a case that authors none. The classification
the lane reports, and its other refusals, are graded through the adapter
(`test_adapter.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import case_format
from parallax.conformance._lanes import error
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.db_error import DatabaseError
from tests.unit.conformance._recording_ports import FakeWritePort


def _error_case(document: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-db-error-999-synthetic.yaml"),
        case_id="m-db-error-999",
        shape="error",
        tags=("m-db-error", "slice-snapshot-1"),
        model="models/error-cases.yaml",
        document={"model": "models/error-cases.yaml", **document},
    )


def _unique_violation() -> DatabaseError:
    return DatabaseError(category="uniqueViolation", native_code="23505", message="dup key")


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"then": {"errorClass": "uniqueViolation"}},
        {"then": {"statements": []}},
        {"then": {"statements": "insert into widget(id) values (1)"}},
    ],
)
def test_run_error_case_refuses_a_case_authoring_no_trigger(document: dict[str, object]) -> None:
    # The trigger is the case's own `then.statements`, so a case carrying none —
    # no `then` at all, a `then` without the member, an empty list, or a member
    # that is not a list — has nothing to run and is refused by name before any
    # statement reaches the port.
    port = FakeWritePort()
    with pytest.raises(EngineError, match=r"m-db-error-999-synthetic\.yaml.*`then\.statements`"):
        error.run_error_case(_error_case(document), port)
    assert port.writes == []


def test_run_error_case_reaches_the_port_with_the_dialects_own_spelling_and_binds() -> None:
    # A statement's `sql` is either one spelling or one per dialect, and `binds`
    # is optional: the lane issues the spelling of the port's own dialect,
    # translated to driver text, with the authored binds or none.
    case = _error_case(
        {
            "then": {
                "statements": [
                    {"sql": "delete from widget"},
                    {
                        "sql": {
                            "postgres": "insert into widget(id, label) values (?, ?)",
                            "mariadb": "insert into widget(id, label) values (?, ?)",
                        },
                        "binds": [1, "dup"],
                    },
                ]
            }
        }
    )
    port = FakeWritePort(parameterized_write_failure=_unique_violation())
    emissions, error_class, native_code, round_trips = error.run_error_case(case, port)
    assert port.writes == [
        ("delete from widget", []),
        ("insert into widget(id, label) values (%s, %s)", [1, "dup"]),
    ]
    assert [(emission.sql, emission.binds) for emission in emissions] == [
        ("delete from widget", ()),
        ("insert into widget(id, label) values (?, ?)", (1, "dup")),
    ]
    assert (error_class, native_code, round_trips) == ("uniqueViolation", "23505", 2)
