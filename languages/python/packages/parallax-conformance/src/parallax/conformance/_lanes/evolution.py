from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from parallax.conformance import case_format, models
from parallax.conformance._mechanism.dialects import DIALECT_CATALOG, dialect_for
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.conformance._mechanism.model_facts import model_path
from parallax.conformance.bindings import binding_document
from parallax.conformance.evolution_wire import (
    evolution_observation,
    schema_cell,
    unsupported_cell,
)
from parallax.core.internal.database_binding import ResolvedBinding
from parallax.evolution.internal.model_evolution import (
    ABSENT,
    UnilateralEvolution,
    evolve_resolved,
)
from parallax.evolution.internal.schema_delta import UnsupportedSchemaEvolutionError, schema_delta
from parallax.postgres import PostgresBinding

__all__ = ["run_evolution_case"]


def run_evolution_case(case: case_format.Case) -> dict[str, Any]:
    """The observations an `evolution` case's two endpoints produce.

    `when.evolve.earlier` is a model descriptor path or the explicit
    fresh-provisioning sentinel `null`, which reaches `evolve_resolved` as `ABSENT` rather
    than as an empty model. Each present endpoint resolves under its own
    PostgreSQL binding: `when.evolve.earlierBinding` / `laterBinding`, else the
    case `binding`, else the corpus default. Both endpoints form through the same public door
    every other corpus model does, so a case cannot describe an evolution between
    models this implementation would not otherwise accept.

    A unilateral description additionally carries its Schema Delta for every
    Dialect the specification names, reported as one whole matrix rather than one
    cell per run: a Dialect this implementation ships no strategy for is an
    explicit exclusion naming its reason, never a silently absent key.

    The run touches no database and no port: describing the difference between
    two accepted models and lowering it to statements are both pure, which is
    what makes an evolution case cost zero Database Calls and carry no dialect of
    its own.
    """
    when = case.document.get("when")
    action = cast("Mapping[str, object]", when).get("evolve") if isinstance(when, Mapping) else None
    if not isinstance(action, Mapping):
        raise UnclassifiedEngineError(f"{case.path.name}: evolution case carries no `when.evolve`")
    named = cast("Mapping[str, object]", action)
    later_ref = named.get("later")
    if not isinstance(later_ref, str):
        raise UnclassifiedEngineError(
            f"{case.path.name}: `when.evolve.later` must be a string path"
        )
    earlier_ref = named.get("earlier")
    if earlier_ref is not None and not isinstance(earlier_ref, str):
        raise UnclassifiedEngineError(
            f"{case.path.name}: `when.evolve.earlier` is a string path or the null sentinel"
        )
    case_binding = case.document.get("binding")
    later = ResolvedBinding(
        models.load_model(model_path(later_ref)),
        _endpoint_binding(named.get("laterBinding"), case_binding),
    )
    evolution = (
        evolve_resolved(ABSENT, later)
        if earlier_ref is None
        else evolve_resolved(
            ResolvedBinding(
                models.load_model(model_path(earlier_ref)),
                _endpoint_binding(named.get("earlierBinding"), case_binding),
            ),
            later,
        )
    )
    observations: dict[str, Any] = {"evolution": evolution_observation(evolution)}
    if isinstance(evolution, UnilateralEvolution):
        observations["schema"] = _schema_matrix(evolution)
    return observations


def _endpoint_binding(endpoint: object, case_binding: object) -> PostgresBinding:
    return PostgresBinding.from_document(
        binding_document(endpoint, "postgres", inherited=case_binding)
    )


def _schema_matrix(evolution: UnilateralEvolution) -> dict[str, Any]:
    """One cell per Dialect the specification supports, in catalog order."""
    return {name: _schema_matrix_cell(evolution, name) for name in DIALECT_CATALOG}


def _schema_matrix_cell(evolution: UnilateralEvolution, name: str) -> dict[str, Any]:
    try:
        dialect = dialect_for(name)
    except ValueError:
        return {"excluded": {"reason": "no-dialect"}}
    if dialect.name != evolution.later.dialect.name:  # pragma: no cover - one shipped dialect
        return {"excluded": {"reason": "no-dialect"}}
    try:
        return schema_cell(schema_delta(evolution))
    except UnsupportedSchemaEvolutionError as refusal:
        return unsupported_cell(refusal)
