from __future__ import annotations

from parallax.conformance import case_format
from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._lanes import scenario, snapshot
from parallax.conformance._lanes.error import run_error_case
from parallax.conformance._lanes.evolution import run_evolution_case
from parallax.conformance._lanes.interleaved import run_interleaved_scenario_case
from parallax.conformance._lanes.reads import (
    case_database,
    compile_read_case,
    run_graph_case,
    run_graphs_case,
    run_read_case,
    run_stream_case,
    run_streamed_graphs_case,
)
from parallax.conformance._lanes.rejected import run_rejected_case
from parallax.conformance._lanes.scenario import (
    compile_write_sequence_case,
    read_table_state,
    run_conflict_case,
    run_write_sequence_case,
)
from parallax.conformance._lifecycle_observation import LifecycleRun, lifecycle_run
from parallax.conformance._mechanism import case_document
from parallax.conformance._mechanism.case_document import RunOnly, eligibility
from parallax.conformance._mechanism.envelope import Emission, EngineError, ScenarioRun
from parallax.conformance._mechanism.model_facts import (
    case_edition,
    case_serving_model,
    load_case_domain_model,
    load_case_metamodel,
)

__all__ = [
    "Emission",
    "EngineError",
    "RunOnly",
    "ScenarioRun",
    "case_database",
    "case_edition",
    "case_serving_model",
    "compile_read_case",
    "compile_scenario_case",
    "compile_write_sequence_case",
    "eligibility",
    "load_case_domain_model",
    "load_case_metamodel",
    "read_table_state",
    "run_conflict_case",
    "run_error_case",
    "run_evolution_case",
    "run_graph_case",
    "run_graphs_case",
    "run_interleaved_scenario_case",
    "run_read_case",
    "run_rejected_case",
    "run_scenario_case",
    "run_stream_case",
    "run_streamed_graphs_case",
    "run_write_sequence_case",
]


def compile_scenario_case(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    """Compile a scenario case to its ordered per-step emissions and round-trip
    count, on whichever scenario lane the case's steps select."""
    steps = case_document.scenario_steps(case)
    if case_document.has_action_step(steps):
        return snapshot.compile_scenario(case, dialect_name, steps)
    return scenario.compile_scenario_case(case, dialect_name)


def run_scenario_case(
    case: case_format.Case,
    port: CaseDatabase,
    lifecycle: LifecycleRun | None = None,
) -> ScenarioRun:
    """Run a scenario case and report its observations as a :class:`ScenarioRun`,
    on whichever scenario lane the case's steps select."""
    steps = case_document.scenario_steps(case)
    if case_document.has_action_step(steps):
        return snapshot.run_scenario(case, port, steps, lifecycle_run(lifecycle))
    return scenario.run_scenario_case(case, port, lifecycle)
