"""The evidence a deferred range's coverage read answers, built from Predecessor
Rows through the production evidence builder."""

from __future__ import annotations

from collections.abc import Sequence

from parallax.core import inheritance
from parallax.core.entity._construction_input import ABSENT
from parallax.core.metamodel import Metamodel
from parallax.core.write_plan import PredecessorRow, PredecessorRows, PredecessorRowsBuilder
from parallax.core.write_plan.plan import RangeAcquisition
from tests.unit._positional_row_support import positional_row

__all__ = ["acquired"]


def acquired(
    model: Metamodel, acquisition: RangeAcquisition, rows: Sequence[PredecessorRow]
) -> PredecessorRows | None:
    """What reading ``acquisition``'s coverage answers where the database holds
    ``rows``: each row positional over its target's members, its document
    beside it where any row has one, and ``None`` where there is no row."""
    view = inheritance.view(model).entity(acquisition.entity.identity)
    assert view is not None
    selection = view.member_selection
    key = selection.shape.position(acquisition.key_attribute.name)
    assert key is not None
    documents = any(row.document is not None for row in rows)
    evidence = PredecessorRowsBuilder(
        selection, key_position=key, absent=ABSENT, documents=documents
    )
    for row in rows:
        evidence.append(positional_row(selection.shape, row.members, absent=ABSENT), row.document)
    return evidence.seal()
