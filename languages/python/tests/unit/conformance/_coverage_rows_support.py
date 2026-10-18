"""The coverage a tracked case state answers through the unit of work's own
coverage consumer, and the member state of each row it answers."""

from __future__ import annotations

from collections.abc import Mapping

from parallax.conformance.simulated_temporal_store import SimulatedTemporalStore
from parallax.core._execution._unit_work.acquisition import CoverageReadRequest, consume_coverage
from parallax.core.metamodel import Metamodel
from parallax.core.write_plan import PredecessorRow, PredecessorRows

__all__ = ["coverage_members", "read_coverage"]


def read_coverage(
    store: SimulatedTemporalStore, model: Metamodel, request: CoverageReadRequest
) -> PredecessorRows | None:
    """What reading ``request`` over ``store`` seals as coverage evidence."""
    return store.acquisition(model)(request, consume_coverage)


def coverage_members(covered: PredecessorRows | None) -> list[Mapping[str, object]]:
    """Each covered row's members by declared name, in evidence order; none
    where the read found no row."""
    if covered is None:
        return []
    return [
        PredecessorRow.over_row(
            covered.selection, covered.rows[index], covered.document(index), covered.absent
        ).members
        for index in range(len(covered))
    ]
