"""Stored Bitemporal milestones of one categorical Entity per storage layout.

Each Entity holds a scalar, a One Value Object nesting another One, and a Many,
under Columns or Relational Document Layout. A milestone is composed from its
key alone: as the driver answers it, keyed by physical column, or as a read
appends it to Predecessor Rows.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Final, Literal

from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    ValueObject,
    attr,
    temporal_read,
)
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.write_plan import PredecessorRows, PredecessorRowsBuilder
from tests.unit._positional_row_support import positional_row

__all__ = [
    "ENTITY_CLASSES",
    "LAYOUTS",
    "MODEL",
    "TX_START",
    "VALID_START",
    "Layout",
    "MilestoneColumns",
    "MilestoneDocument",
    "milestones",
    "stored_row",
]

type Layout = Literal["columns", "document"]

_NAMESPACE: Final = "milestone.rows"

TX_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
VALID_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class Geo(ValueObject):
    country: Attr[str]


class Address(ValueObject):
    city: Attr[str]
    geo: Attr[Geo]


class Tag(ValueObject):
    label: Attr[str]


class MilestoneColumns(Bitemporal, table="milestone_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class MilestoneDocument(
    Bitemporal,
    table="milestone_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


ENTITY_CLASSES: Final[tuple[type[Entity], ...]] = (MilestoneColumns, MilestoneDocument)
"""One Entity per storage layout, in :data:`LAYOUTS` order."""
LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
MODEL: Final = DomainModel(*ENTITY_CLASSES)

_PREPARED: Final = model_of(MODEL)


def _members(key: int) -> dict[str, object]:
    return {
        "title": f"title-{key:08d}",
        "address": {"city": f"city-{key:08d}", "geo": {"country": "NO"}},
        "tags": [{"label": f"tag-{key:08d}-a"}, {"label": f"tag-{key:08d}-b"}],
    }


_BOUNDS: Final[Mapping[str, object]] = {
    "from_z": VALID_START,
    "thru_z": INFINITY,
    "in_z": TX_START,
    "out_z": INFINITY,
}
"""Every stored row's milestone bounds: current, and open on both axes."""


def stored_row(layout: Layout, key: int) -> dict[str, object]:
    """One current milestone as the driver answers it, keyed by physical column."""
    if layout == "document":
        return {"id": key, **_BOUNDS, "payload": _members(key)}
    return {"id": key, **_members(key), **_BOUNDS}


def milestones(
    entity: type[Entity], *spans: tuple[dt.datetime, object]
) -> tuple[PredecessorRows, temporal_read.Bitemporal]:
    """One stored milestone of ``entity`` per Valid-Time ``(start, end)`` span,
    keyed from one, as a read appends them."""
    layout = LayoutCatalog(_PREPARED).entity(entity.identity)
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
            "txStart": TX_START,
            "txEnd": INFINITY,
        }
        builder.append(positional_row(selection.shape, cells, absent=ABSENT))
    evidence = builder.seal()
    shape = temporal_read.view(_PREPARED).shape(entity.identity)
    assert evidence is not None
    assert isinstance(shape, temporal_read.Bitemporal)
    return evidence, shape
