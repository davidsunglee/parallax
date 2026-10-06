"""The member state of each row a tracked coverage read answers."""

from __future__ import annotations

from collections.abc import Mapping

from parallax.core.write_plan import PredecessorRow, PredecessorRows

__all__ = ["coverage_members"]


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
