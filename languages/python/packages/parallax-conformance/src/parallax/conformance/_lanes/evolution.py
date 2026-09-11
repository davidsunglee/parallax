"""The evolution lane: an `evolution`-shape case's two model endpoints
described as the difference between them, and a unilateral description
lowered to its Schema Delta for every Dialect the specification names.

The lane touches no database, builds no Handle, and carries no dialect of its
own: both endpoints form through the public descriptor door every corpus
model does, describing the difference is pure, and so is lowering it, which is
why an evolution case costs zero round trips. What comes back is the
observation document — the evolution's corpus spelling and, for a unilateral
description, one schema cell per catalogued Dialect, a Dialect this
implementation ships no strategy for reported as an explicit exclusion.
Grading it against ``then`` is the adapter's.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from parallax.conformance import case_format, models
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.model_facts import model_path
from parallax.conformance.evolution_wire import (
    evolution_observation,
    schema_cell,
    unsupported_cell,
)
from parallax.core.dialect import DIALECT_CATALOG, dialect_for
from parallax.evolution.model_evolution import ABSENT, UnilateralEvolution, evolve
from parallax.evolution.schema_delta import UnsupportedSchemaEvolutionError, schema_delta

__all__ = ["run_evolution_case"]


def run_evolution_case(case: case_format.Case) -> dict[str, Any]:
    """The observations an `evolution` case's two endpoints produce.

    `when.evolve.earlier` is a model descriptor path or the explicit
    fresh-provisioning sentinel `null`, which reaches `evolve` as `ABSENT` rather
    than as an empty model. Both endpoints form through the same public door
    every other corpus model does, so a case cannot describe an evolution between
    models this implementation would not otherwise accept.

    A unilateral description additionally carries its Schema Delta for every
    Dialect the specification names, reported as one whole matrix rather than one
    cell per run: a Dialect this implementation ships no strategy for is an
    explicit exclusion naming its reason, never a silently absent key.

    The run touches no database and no port: describing the difference between
    two accepted models and lowering it to statements are both pure, which is
    what makes an evolution case cost zero round trips and carry no dialect of
    its own.
    """
    when = case.document.get("when")
    action = cast("Mapping[str, object]", when).get("evolve") if isinstance(when, Mapping) else None
    if not isinstance(action, Mapping):
        raise EngineError(f"{case.path.name}: evolution case carries no `when.evolve`")
    named = cast("Mapping[str, object]", action)
    later_ref = named.get("later")
    if not isinstance(later_ref, str):
        raise EngineError(f"{case.path.name}: `when.evolve.later` must be a string path")
    earlier_ref = named.get("earlier")
    if earlier_ref is not None and not isinstance(earlier_ref, str):
        raise EngineError(
            f"{case.path.name}: `when.evolve.earlier` is a string path or the null sentinel"
        )
    earlier = ABSENT if earlier_ref is None else models.load_model(model_path(earlier_ref))
    evolution = evolve(earlier, models.load_model(model_path(later_ref)))
    observations: dict[str, Any] = {"evolution": evolution_observation(evolution)}
    if isinstance(evolution, UnilateralEvolution):
        observations["schema"] = _schema_matrix(evolution)
    return observations


def _schema_matrix(evolution: UnilateralEvolution) -> dict[str, Any]:
    """One cell per Dialect the specification supports, in catalog order."""
    return {name: _schema_matrix_cell(evolution, name) for name in DIALECT_CATALOG}


def _schema_matrix_cell(evolution: UnilateralEvolution, name: str) -> dict[str, Any]:
    try:
        dialect = dialect_for(name)
    except ValueError:
        return {"excluded": {"reason": "no-dialect"}}
    try:
        return schema_cell(schema_delta(evolution, dialect))
    except UnsupportedSchemaEvolutionError as refusal:
        return unsupported_cell(refusal)
