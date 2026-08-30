"""The pipeline one Unit Work Scenario is graded by, in order."""

from __future__ import annotations

from ..case import Case
from ..providers import DatabaseProvider
from ..provisioning import apply_given, provision
from .compile import compile_scenario
from .execute import execute_scenario
from .judge import judge_document

__all__ = ["assert_unit_work_scenario"]


def assert_unit_work_scenario(case: Case, db: DatabaseProvider) -> None:
    """Grade *case*'s Unit Work Scenario against *db*.

    Compilation runs on every dialect, because everything it decides is a
    property of the document. The cross-checks that follow read the golden SQL,
    so a dialect the case lists none for has nothing here to grade and nothing to
    execute — exactly as a step's own golden is what says whether it is
    executable at all.
    """
    scenario = compile_scenario(case)
    if not scenario.has_golden(db.dialect):
        return
    judge_document(scenario, db.dialect)
    provision(case, db)
    # The out-of-band setup puts state into a row no authored member could produce
    # — a Structured Column key the model declares nowhere included.
    apply_given(case, db)
    execute_scenario(scenario, db)
