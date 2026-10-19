from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core import read_delivery
from parallax.core.db_port import MappingRow
from parallax.core.execution import QueryTargetError
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.metamodel import entity_by_name
from parallax.core.predicate import CanonicalDocumentError, ModelRejectedError
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.temporal_read import TemporalReadError

__all__ = [
    "READ_ERRORS",
    "Emission",
    "EngineError",
    "ScenarioRun",
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
    QueryTargetError,
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
    the snapshot action-step lane and by each refused submission of a
    state-graded group; ``step_rows`` one per read step the run
    itself drove plus each row-observing `mutate`, carrying the values that step published
    (`m-conformance-adapter`); ``step_graphs`` one per step declaring
    `expectGraph`, from either placement of that observable — an `access` step's
    retained view on the snapshot lane, a find step's own materialized graph on
    both. All three are in step order. ``units`` holds each `uow` group's fate by
    label, and ``table_state`` the tables read back once every step ran, where
    the case states them.
    """

    emissions: list[Emission]
    database_calls: int
    errors: list[dict[str, object]]
    step_rows: list[dict[str, object]]
    step_graphs: list[dict[str, object]]
    units: dict[str, dict[str, object]] | None = None
    table_state: dict[str, list[MappingRow]] | None = None


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


def graph_root(root: object) -> MappingRow | None:
    """One published result position as the value `then.graph` grades.

    A conforming root IS the graph node. A classified root publishes its record
    instead, carrying the hydrated node when the collapse produced one and
    nothing when no value could be produced without inventing it — and the graph
    position then carries ``null``, because a record is graded through
    `then.storedDataIssues` rather than rendered as though it were a node.
    """
    if isinstance(root, read_delivery.InvalidData):
        return cast("MappingRow | None", cast("read_delivery.InvalidData[object]", root).data)
    return cast("MappingRow", root)


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
