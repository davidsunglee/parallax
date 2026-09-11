"""The evolution lane, driven database-free: the refusal of a case whose
``when.evolve`` names no loadable endpoints, and the schema cell a Dialect's
refusal to render an operation is reported as, since no shipped dialect refuses
one and the arm has no corpus witness.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from pathlib import Path

import pytest

from parallax.conformance import case_format, sweep
from parallax.conformance._lanes import evolution
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.metamodel import EntityIdentity, Table
from parallax.evolution.model_evolution import EntityAdded
from parallax.evolution.schema_delta import (
    PhysicalLocation,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)


@functools.cache
def _reachable_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in sweep.reachable_cases(cases=case_format.load_cases())}


def _case(case_id: str) -> case_format.Case:
    return _reachable_by_id()[case_id]


def _evolution_case(document: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-model-evolution-999-synthetic.yaml"),
        case_id="m-model-evolution-999",
        shape="evolution",
        tags=("m-model-evolution", "slice-snapshot-1"),
        model="",
        document=document,
    )


def test_an_evolution_case_without_its_endpoints_is_rejected() -> None:
    with pytest.raises(EngineError, match=r"when\.evolve"):
        evolution.run_evolution_case(_evolution_case({"when": {}}))


def test_an_evolution_case_without_a_later_endpoint_is_rejected() -> None:
    with pytest.raises(EngineError, match=r"when\.evolve\.later"):
        evolution.run_evolution_case(_evolution_case({"when": {"evolve": {"earlier": None}}}))


def test_an_evolution_case_whose_earlier_endpoint_is_neither_a_path_nor_null_is_rejected() -> None:
    # `null` is the fresh-provisioning SENTINEL, so the member is a string path or
    # that one value; anything else names an endpoint nothing can load.
    bad = _evolution_case(
        {"when": {"evolve": {"earlier": 7, "later": "models/evolution-widget-v1.yaml"}}}
    )
    with pytest.raises(EngineError, match=r"when\.evolve\.earlier"):
        evolution.run_evolution_case(bad)


def test_a_dialect_that_cannot_render_an_operation_reports_an_unsupported_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Postgres renders every physical operation this algebra emits, so the arm
    # that turns a refusal into a cell has no corpus witness until a dialect that
    # refuses one ships. The engine must report the refusal AS the cell rather
    # than letting it escape as a run failure.
    def _refuse(evolution: object, dialect: object) -> object:
        del evolution, dialect
        raise UnsupportedSchemaEvolutionError(
            "postgres",
            (
                UnsupportedSchemaOperation(
                    kind="CreateIndex",
                    location=PhysicalLocation(table=Table(name="evolution_widget")),
                    reason="a refusing renderer",
                    caused_by=(
                        EntityAdded(entity=EntityIdentity("parallax.compatibility", "Widget")),
                    ),
                ),
            ),
        )

    monkeypatch.setattr(evolution, "schema_delta", _refuse)
    observations = evolution.run_evolution_case(_case("m-model-evolution-001"))
    assert observations["schema"]["postgres"] == {
        "unsupported": {
            "operations": [
                {
                    "kind": "CreateIndex",
                    "physicalLocation": {"table": "evolution_widget"},
                    "causedBy": [
                        {"kind": "EntityAdded", "entity": "parallax.compatibility.Widget"}
                    ],
                }
            ]
        }
    }
    assert observations["schema"]["mariadb"] == {"excluded": {"reason": "no-dialect"}}
