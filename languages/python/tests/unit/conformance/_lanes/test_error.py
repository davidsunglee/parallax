"""The error lane's trigger parsing, driven against a fake in-memory
``m-db-port`` (no Docker): what an authored ``then.statements`` trigger reaches
the port as, including the omitted ``binds`` no corpus error case authors. The
classification the lane reports, and its refusals of a trigger that misbehaves,
are graded through the adapter (`test_adapter.py`).
"""

from __future__ import annotations

from pathlib import Path

from parallax.conformance import case_format
from parallax.conformance._lanes import error
from parallax.core.internal.db_error import DatabaseError
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


def test_run_error_case_reaches_the_port_with_the_dialects_own_spelling_and_binds() -> None:
    # A statement's `sql` has one spelling per dialect, and `binds` is optional:
    # the lane issues the spelling of the port's own dialect, translated to
    # driver text, with the authored binds or none.
    case = _error_case(
        {
            "then": {
                "statements": [
                    {"sql": {"postgres": "delete from widget", "mariadb": "delete from widget"}},
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
    emissions, error_class, native_code, database_calls = error.run_error_case(case, port)
    assert port.writes == [
        ("delete from widget", []),
        ("insert into widget(id, label) values (%s, %s)", [1, "dup"]),
    ]
    assert [(emission.sql, emission.binds) for emission in emissions] == [
        ("delete from widget", ()),
        ("insert into widget(id, label) values (?, ?)", (1, "dup")),
    ]
    assert (error_class, native_code, database_calls) == ("uniqueViolation", "23505", 2)
