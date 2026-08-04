"""The Temporality Profile and the temporal structure it derives (m-descriptor).

A descriptor spells one temporal fact — ``temporality`` — and phase 3 of
ingestion derives the rest: each As-Of Axis, its two endpoint Attributes, and
their framework-fixed physical columns. The endpoints are appended to the
entity's own attributes once, where a descriptor is read, so every consumer
downstream sees the members the profile implies; the axes themselves are read
back from the profile wherever a consumer needs them, so the derived structure
has no second, storable spelling.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

__all__ = [
    "TEMPORALITY_PROFILES",
    "TEMPORAL_DIMENSION_RANK",
    "TEMPORAL_MEMBERS",
    "Axis",
    "Endpoint",
    "derive_temporal_structure",
    "temporal_axes",
]


@dataclass(frozen=True)
class Endpoint:
    """One As-Of Axis endpoint's canonical attribute name over its fixed column."""

    name: str
    column: str


@dataclass(frozen=True)
class Axis:
    """One As-Of Axis a Temporality Profile derives, endpoints included."""

    dimension: str
    start: Endpoint
    end: Endpoint


TEMPORAL_MEMBERS: Mapping[str, tuple[Endpoint, Endpoint]] = MappingProxyType(
    {
        "valid-time": (Endpoint("validStart", "from_z"), Endpoint("validEnd", "thru_z")),
        "transaction-time": (Endpoint("txStart", "in_z"), Endpoint("txEnd", "out_z")),
    }
)
"""Each temporal dimension's start and end endpoint, in canonical axis order.

The columns are framework-fixed rather than derived: ``defaultColumn("txStart")``
is ``tx_start``, not ``in_z``, so no naming operation can produce them.
"""

TEMPORALITY_PROFILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "nontemporal": (),
        "transaction-time": ("transaction-time",),
        "bitemporal": ("valid-time", "transaction-time"),
    }
)
"""Each Temporality Profile's dimensions in canonical axis order — Valid Time
before Transaction Time, the ``from_z, thru_z, in_z, out_z`` projection order."""

TEMPORAL_DIMENSION_RANK: Mapping[str, int] = MappingProxyType(
    {dimension: rank for rank, dimension in enumerate(TEMPORALITY_PROFILES["bitemporal"])}
)
"""The canonical order of the As-Of Axis dimensions, the bitemporal profile's own.

Every ordered per-axis sequence follows it — the physical primary key's temporal
end slots, and a milestone close's one exclusive upper bound per axis.
"""


def temporal_axes(definition: Mapping[str, Any]) -> tuple[Axis, ...]:
    """The As-Of Axes ``definition``'s own Temporality Profile derives.

    An entity that declares no profile derives nothing, which is what an omitted
    ``temporality`` means. This is a LOCAL view: an inheritance descendant's own
    profile is the family-wide one only after
    :func:`~reference_harness.inheritance.resolve_effective_definition` has
    flattened the root's onto it.
    """
    profile = definition.get("temporality") or "nontemporal"
    return tuple(
        Axis(dimension, *TEMPORAL_MEMBERS[dimension]) for dimension in TEMPORALITY_PROFILES[profile]
    )


def derive_temporal_structure(descriptor: Any) -> Any:
    """``descriptor`` with each entity's derived endpoint attributes appended.

    A deep copy, so the authored document is left as written. Every endpoint is a
    non-nullable Timestamp over its framework-fixed column, placed after every
    domain attribute in canonical axis order.
    """
    derived = copy.deepcopy(descriptor)
    if not isinstance(derived, dict):
        return derived
    entities = derived.get("entities")
    definitions = entities if isinstance(entities, list) else [derived.get("entity")]
    for definition in definitions:
        if isinstance(definition, dict):
            _append_endpoints(definition)
    return derived


def _append_endpoints(definition: dict[str, Any]) -> None:
    endpoints = [
        {"name": endpoint.name, "type": "timestamp", "column": endpoint.column}
        for axis in temporal_axes(definition)
        for endpoint in (axis.start, axis.end)
    ]
    if endpoints:
        definition["attributes"] = [*definition.get("attributes", []), *endpoints]
