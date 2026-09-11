"""The conformance compile/run engine — binding the corpus to the spine.

The adapter path compiles and runs a compatibility case against the class-free
production spine (no dynamic class synthesis): the case's model YAML is ingested
through the ``m-descriptor`` deserializer and its ``when.objectQuery`` through the
``m-object-query`` deserializer. ``compile`` lowers that query through ``m-sql``;
``run`` routes it through the production read seams — the public Wire read for a
graph, the values lane for rows — which own planning, compilation, execution,
conversion, classification, and row materialization before the adapter builds the
observation envelope around what they published. Compile eligibility
(``m-case-format`` ``compileEligibility``) is read from the case; the run-only
minority is never compiled.

This module is the façade the adapter and the CLI consume: every entry point
is defined in a lane under :mod:`~parallax.conformance._lanes` over the
mechanism under :mod:`~parallax.conformance._mechanism`, and re-exported here
under its unchanged name. The one decision the façade makes itself is which
scenario lane a case belongs to: a scenario carrying an action step is the
snapshot lane's, and every other scenario is the keyed unit-of-work lane's.
"""

from __future__ import annotations

from parallax.conformance import case_format
from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._lanes import scenario, snapshot
from parallax.conformance._lanes.error import run_error_case
from parallax.conformance._lanes.evolution import run_evolution_case
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
    run_interleaved_scenario_case,
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
