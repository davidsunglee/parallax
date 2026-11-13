"""Recognizing a recoverable temporal conflict where a statement failed (`m-execution`,
`m-auto-retry`).

A statement failure is a recoverable conflict exactly when the dialect reports
an exclusion violation naming the exclusion its own Table's layout compiled.
The executor hands such a failure to the attempt and lets it propagate
unchanged; every other failure — a check, a key, a lock wait, an unnamed or
foreign exclusion — is handed nowhere.
"""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core._execution._write_step_executor import recoverable_conflict
from parallax.core.internal import storage_layout
from parallax.core.internal.database_binding import PhysicalTable
from parallax.core.internal.db_error import Category, DatabaseError
from parallax.core.internal.db_port import (
    OrderedWriteResultComplete,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.write_plan.steps import PlannedStep
from tests._support.bindings import bound_model
from tests._support.db_port import Ordered, ScriptedAdapter, Write
from tests.unit.core._execution._write_step_support import (
    POSITION,
    POSITION_META,
    close,
    open_flush,
    opening,
    step_executor,
)

_VIEW = storage_layout.storage_layout_facet_of(POSITION_META).entity(POSITION)
assert _VIEW is not None
_TABLE = bound_model(POSITION_META).table(_VIEW.layout.mapping_owner)
_CONSTRAINTS = _TABLE.temporal_constraints
assert _CONSTRAINTS is not None
_EXCLUSION: Final = _CONSTRAINTS.exclusion_name
_CHECK: Final = _CONSTRAINTS.transaction_check_name


def _violation(
    code: str,
    name: str | None,
    category: Category | None,
    table: PhysicalTable | None = _TABLE.physical,
) -> DatabaseError:
    return DatabaseError(
        category=category,
        native_code=code,
        message="violation",
        constraint_name=name,
        constraint_table=table,
    )


def _exclusion(
    name: str = _EXCLUSION, table: PhysicalTable | None = _TABLE.physical
) -> DatabaseError:
    return _violation("23P01", name, "constraintViolation", table)


def _executed(
    port: ScriptedAdapter, *steps: PlannedStep
) -> tuple[BaseException, list[DatabaseError]]:
    recognized: list[DatabaseError] = []
    with pytest.raises(DatabaseError) as raised, open_flush() as flush:
        step_executor(port, recognized=recognized).execute(steps, allocates=False, flush=flush)
    return raised.value, recognized


def test_a_violation_of_the_tables_own_exclusion_is_recognized_and_raised_unchanged() -> None:
    failure = _exclusion()
    raised, recognized = _executed(ScriptedAdapter(Write(raises=failure)), opening(3))
    assert raised is failure
    assert recognized == [failure]
    assert recognized[0] is failure


def test_an_ordered_statement_failure_is_recognized_against_its_own_step() -> None:
    failure = _exclusion()
    result = OrderedWriteResultComplete((1, StatementFailed(failure), StatementNotExecuted()))
    raised, recognized = _executed(
        ScriptedAdapter(Ordered(result), ordered=True), close(1), close(2), close(3)
    )
    assert raised is failure
    assert recognized == [failure]


@pytest.mark.parametrize(
    "failure",
    [
        _violation("23514", _CHECK, "constraintViolation"),
        _violation("23514", _EXCLUSION, "constraintViolation"),
        _violation("23505", _CONSTRAINTS.primary_key_name, "uniqueViolation"),
        _violation("55P03", None, "lockWaitTimeout"),
        _exclusion("pxc_excl_elsewhere_00000000000000000000000000000000"),
        _exclusion(_EXCLUSION.upper()),
        _violation("23P01", None, "constraintViolation"),
        _exclusion(table=PhysicalTable(("elsewhere",), _TABLE.physical.name)),
        _exclusion(table=None),
    ],
    ids=[
        "check",
        "check-kind-under-the-exclusion-name",
        "primary-key",
        "lock-wait-timeout",
        "another-tables-exclusion",
        "not-the-exact-name",
        "unnamed-exclusion",
        "the-same-name-on-another-schemas-table",
        "no-reported-table",
    ],
)
def test_any_other_failure_is_left_to_its_category(failure: DatabaseError) -> None:
    raised, recognized = _executed(ScriptedAdapter(Write(raises=failure)), opening(3))
    assert raised is failure
    assert recognized == []
    assert not recoverable_conflict(opening(3), failure, bound_model(POSITION_META), POSTGRES)
