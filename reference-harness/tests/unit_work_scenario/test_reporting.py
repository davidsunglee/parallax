"""What a caller is told when a Scenario fails, and in which order.

Three guarantees, each of them part of the one export's interface rather than a
property of its messages: an authored failure names the case path and the
authored step position exactly once, a native driver exception arrives unchanged,
and a case broken in more than one place reports the defect its earliest phase
found.
"""

from __future__ import annotations

import copy

import pytest

from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import run_case
from reference_harness.unit_work_scenario import assert_unit_work_scenario

from .conftest import Affected, RefusingProvider, Rows, ScriptedProvider

_SETTLED = "m-unit-work-015-close-settles-against-the-milestone-its-own-find-observed.yaml"
_RYOW = "m-unit-work-005-ryow-update.yaml"
_ABORT = "m-opt-lock-012-conflict-aborts-uow.yaml"


def _named_once(failure: CaseFailure, case_name: str, step: int) -> None:
    message = str(failure)
    assert message.startswith(f"{case_name}: "), message
    assert message.count(case_name) == 1, message
    assert message.count("scenario[") == 1, message
    assert f"scenario[{step}]" in message, message


# --- the position, added once, wherever the refusal came from ---------------


def test_a_compile_phase_refusal_names_its_step_once(damaged_case) -> None:
    case = damaged_case(_SETTLED)
    case.when["scenario"][2]["on"] = 1000
    with pytest.raises(CaseFailure) as raised:
        assert_unit_work_scenario(case, RefusingProvider())
    _named_once(raised.value, case.path.name, 2)


def test_a_judge_phase_refusal_names_its_step_once(damaged_case) -> None:
    case = damaged_case(_SETTLED)
    case.when["scenario"][2]["statements"][0]["binds"][2] = "infinity"
    with pytest.raises(CaseFailure) as raised:
        assert_unit_work_scenario(case, RefusingProvider())
    _named_once(raised.value, case.path.name, 2)


def test_an_execution_refusal_from_this_package_names_its_step_once(damaged_case) -> None:
    # The conflict-abort proof is authored as local detail; the position is the
    # step boundary's to add, and it is added exactly once.
    case = damaged_case(_ABORT)
    ours, concurrent, after = (
        Rows(tuple(step["expectRows"])) for step in case.scenario if "expectRows" in step
    )
    script = [ours, concurrent, Affected(1), Affected(1), Affected(1), after]
    with pytest.raises(CaseFailure) as raised:
        assert_unit_work_scenario(case, ScriptedProvider(script=script))
    _named_once(raised.value, case.path.name, 3)


def test_an_execution_refusal_from_the_read_oracle_names_its_step_once(damaged_case) -> None:
    # The oracle authors its own position, which this boundary must not add a
    # second time.
    case = damaged_case(_RYOW)
    case.when["scenario"][0]["expectRows"] = [{"id": 1, "owner": "Ada", "balance": 1.0}]
    observed = Rows(({"id": 1, "owner": "Ada", "balance": 100.0, "version": 1},))
    with pytest.raises(CaseFailure) as raised:
        assert_unit_work_scenario(case, ScriptedProvider(script=[observed]))
    _named_once(raised.value, case.path.name, 0)


# --- what is not an authored failure ----------------------------------------


def test_a_driver_exception_arrives_unchanged(corpus_case) -> None:
    # A native driver exception is not a verdict about the case, so nothing wraps,
    # re-raises, or reclassifies it — the caller receives the very object the
    # driver raised.
    case = corpus_case(_RYOW)
    driver_failure = RuntimeError("connection reset by peer")
    with pytest.raises(RuntimeError) as raised:
        assert_unit_work_scenario(case, ScriptedProvider(script=[driver_failure]))
    assert raised.value is driver_failure


# --- which defect a doubly-broken case reports ------------------------------


def test_the_callers_shared_checks_precede_this_packages_own(corpus_case) -> None:
    """A Scenario case broken in two places reports its serialization or
    equivalent-encoding defect ahead of its Scenario-structural one.

    Those checks belong to the caller and run before it delegates, so this is the
    order the pipeline states rather than an accident of where a call happened to
    sit. m-identity-map-003 declares an equivalent encoding on step 0; this breaks
    that encoding AND the step's own round-trip accounting, and the encoding is
    what surfaces.
    """
    case = copy.deepcopy(corpus_case("m-identity-map-003-omitted-vs-explicit-latest.yaml"))
    case.when["scenario"][0]["equivalentEncodings"][0]["target"] = "parallax.compatibility.Nope"
    case.when["scenario"][0]["roundTrips"] += 1

    with pytest.raises(CaseFailure, match="does not canonicalize to the step query"):
        run_case(case, RefusingProvider())


def test_a_structural_defect_precedes_a_dialect_keyed_one(damaged_case) -> None:
    # Compilation is dialect-free and runs on every dialect; the cross-checks that
    # read golden SQL run only where the executing dialect carries one. A case
    # broken in both places therefore reports the structural defect, and reports it
    # identically on every dialect.
    case = damaged_case(_SETTLED)
    case.when["scenario"][2]["on"] = 1000
    case.when["scenario"][2]["roundTrips"] += 1

    for dialect in ("postgres", "mariadb"):
        with pytest.raises(CaseFailure, match="not a real EARLIER step"):
            assert_unit_work_scenario(case, RefusingProvider(dialect))
