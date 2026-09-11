"""The observation envelope every conformance lane reports through, and the
errors it classifies.

A lane's observation is what :mod:`parallax.conformance.adapter` grades against
a case's ``then``: the compiled statement emissions, the scenario channels, and
the graph roots a published result renders to. What this module owns is the
envelope itself — the emission and scenario-run records, the engine's own
refusal class, the read failures a lane translates into it, the reconciliation
of a planned statement with the one the lifecycle delivered, and the rendering
of a published root as a `then.graph` value under the key it is graded by.
Nothing here executes; every lane hands in what it ran and what it planned.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.db_port import Row
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.metamodel import entity_by_name
from parallax.core.predicate import CanonicalDocumentError, ModelRejectedError
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.temporal_read import TemporalReadError
from parallax.snapshot import handle

__all__ = [
    "READ_ERRORS",
    "Emission",
    "EngineError",
    "ScenarioRun",
    "delivered",
    "driver_binds",
    "emissions",
    "graph_root",
    "graph_root_key",
]


class EngineError(ValueError):
    """The engine cannot compile or run a case (unsupported shape or bad reference)."""


READ_ERRORS = (
    CanonicalDocumentError,
    ModelRejectedError,
    SqlGenError,
    TemporalReadError,
    handle.QueryTargetError,
    KeyError,
    ValueError,
)
"""The failures a read lane translates into an :class:`EngineError` naming the case."""


@dataclass(frozen=True, slots=True)
class Emission:
    """One compiled statement emission (an entry of the adapter ``emissions`` array)."""

    case_pointer: str
    statement: LoweredStatement

    @property
    def sql(self) -> str:
        return self.statement.sql

    @property
    def binds(self) -> tuple[object, ...]:
        return self.statement.binds

    def to_json(self) -> dict[str, object]:
        return {
            "casePointer": self.case_pointer,
            "sql": self.statement.sql,
            "binds": list(self.statement.wire_binds()),
        }


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    """What running one scenario case observed, by channel
    (:func:`~parallax.conformance.engine.run_scenario_case`).

    A scenario reports several observation channels of the SAME shape, so each is
    named rather than placed: ``errors`` holds one entry per `expectError` step
    whose verb raised its declared application-lifecycle error, and is filled by
    the snapshot action-step lane alone; ``step_rows`` one per read step the run
    itself drove plus each row-observing `mutate`, carrying the values that step published
    (`m-conformance-adapter`); ``step_graphs`` one per step declaring
    `expectGraph`, from either placement of that observable — an `access` step's
    retained view on the snapshot lane, a find step's own materialized graph on
    both. All three are in step order.
    """

    emissions: list[Emission]
    round_trips: int
    errors: list[dict[str, object]]
    step_rows: list[dict[str, object]]
    step_graphs: list[dict[str, object]]


def delivered(
    planned: Sequence[LoweredStatement], observed: Sequence[LoweredStatement], where: str
) -> tuple[LoweredStatement, ...]:
    """``planned``, once the lifecycle has confirmed it is what ran.

    A write lane reports the plan rather than the delivered statement, because
    `then.statements` is graded on BOTH lanes and only one of them executes: the
    compile lane has no delivery to read, so an emission sourced from one would
    make the two lanes report different spellings of one oracle. The plan is a
    SECOND derivation of the same statements, though, and a second derivation is
    exactly what can drift — which is what this closes. Every statement the unit
    put on the wire is reconciled with the plan it came from, so what the case
    grades is the plan only where the plan is what the database saw.

    Binds are reconciled through each statement's compiler-owned Wire projection,
    so carrier differences are admitted only where typed metadata or an explicit
    Wire override declares them.
    """
    if len(planned) != len(observed):
        raise EngineError(
            f"{where}: the plan holds {len(planned)} statement(s) but the lifecycle delivered "
            f"{len(observed)}; the emission a case grades is the plan, so a plan the execution "
            f"did not follow would report DML nobody ran"
        )
    for index, (plan, ran) in enumerate(zip(planned, observed, strict=True)):
        if plan.sql != ran.sql:
            raise EngineError(
                f"{where}: statement {index} is planned as {plan.sql!r} but the lifecycle "
                f"delivered {ran.sql!r}"
            )
        if not _same_wire_binds(plan.wire_binds(), ran.wire_binds()):
            raise EngineError(
                f"{where}: statement {index} is planned with binds (canonical Wire) "
                f"{plan.wire_binds()!r} but the lifecycle delivered {ran.wire_binds()!r}"
            )
    return tuple(planned)


def _same_wire_binds(left: tuple[object, ...], right: tuple[object, ...]) -> bool:
    if len(left) != len(right):
        return False
    return all(
        json.dumps(one, sort_keys=True, separators=(",", ":"))
        == json.dumps(other, sort_keys=True, separators=(",", ":"))
        for one, other in zip(left, right, strict=True)
    )


def driver_binds(binds: Sequence[object]) -> list[object]:
    return list(binds)


def emissions(
    pointer_statements: Sequence[tuple[str, Sequence[LoweredStatement]]],
) -> list[Emission]:
    return [
        Emission(pointer, statement)
        for pointer, statements in pointer_statements
        for statement in statements
    ]


def graph_root(root: object) -> Row | None:
    """One published result position as the value `then.graph` grades.

    A conforming root IS the graph node. A classified root publishes its record
    instead, carrying the hydrated node when the collapse produced one and
    nothing when no value could be produced without inventing it — and the graph
    position then carries ``null``, because a record is graded through
    `then.storedDataIssues` rather than rendered as though it were a node.
    """
    if isinstance(root, handle.InvalidData):
        return cast("Row | None", cast("handle.InvalidData[object]", root).data)
    return cast("Row", root)


# The wire spelling each pinned as-of axis is emitted under in a milestone-set
# graph's pin entry. The coordinate itself is structured everywhere above this seam.
def graph_root_key(target: str, model: AcceptedMetamodel) -> str:
    """The `then.graph` root key the query's own ``target`` denotes.

    Result vocabulary is LOCAL where an addressing reference is exact
    (`m-case-format`), so the authored spelling is resolved and the Entity's own
    local name answers — the same key a bare spelling produced before every
    reference position became canonical.
    """
    entity = entity_by_name(model, target)
    if entity is None:  # pragma: no cover - the read already resolved this target
        raise EngineError(f"{target!r} names no entity the accepted model declares")
    return entity.identity.name
