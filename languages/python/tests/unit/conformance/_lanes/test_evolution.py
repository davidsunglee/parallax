"""The evolution lane, driven database-free: the schema cell a Dialect's refusal
to render an operation is reported as, since no shipped dialect refuses one and
the case has no corpus witness.
"""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance._lanes import evolution
from parallax.core.metamodel import EntityIdentity, Table
from parallax.evolution.model_evolution import EntityAdded
from parallax.evolution.schema_delta import (
    PhysicalLocation,
    UnsupportedSchemaEvolutionError,
    UnsupportedSchemaOperation,
)
from tests._support.case_corpus import case as corpus_case


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


def test_a_dialect_that_cannot_render_an_operation_reports_an_unsupported_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Postgres renders every physical operation this algebra emits, so the case
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
