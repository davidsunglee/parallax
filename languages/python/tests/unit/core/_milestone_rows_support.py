"""Stored Bitemporal milestones as a resolving read appends them to Predecessor Rows.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from parallax.core import Entity, temporal_read
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.write_plan import PredecessorRows, PredecessorRowsBuilder
from tests.unit import _predicate_acquisition_support as acquisition
from tests.unit._positional_row_support import positional_row

__all__ = ["LAYOUT_ENTITIES", "LAYOUT_IDS", "milestones"]

LAYOUT_ENTITIES: Final[tuple[type[Entity], ...]] = (
    acquisition.AcquisitionColumns,
    acquisition.AcquisitionDocument,
)
LAYOUT_IDS: Final[tuple[str, ...]] = ("columns", "document")

_MODEL = model_of(acquisition.MODEL)


def milestones(
    entity: type[Entity], *spans: tuple[dt.datetime, object]
) -> tuple[PredecessorRows, temporal_read.Bitemporal]:
    """One stored milestone of ``entity`` per Valid-Time ``(start, end)`` span,
    keyed from one, as a resolving read appends them."""
    layout = LayoutCatalog(_MODEL).entity(entity.identity)
    selection = layout.member_selection
    builder = PredecessorRowsBuilder(
        selection, key_position=layout.primary_key[0], absent=ABSENT, documents=False
    )
    for key, (start, end) in enumerate(spans, 1):
        cells = {
            "id": key,
            "title": "Ada",
            "validStart": start,
            "validEnd": end,
            "txStart": acquisition.TX_START,
            "txEnd": INFINITY,
        }
        builder.append(positional_row(selection.shape, cells, absent=ABSENT))
    evidence = builder.seal()
    shape = temporal_read.view(_MODEL).shape(entity.identity)
    assert evidence is not None
    assert isinstance(shape, temporal_read.Bitemporal)
    return evidence, shape
