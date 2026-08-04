"""The frontend-neutral temporal convention table and derived temporal structure.

Both frontends reach the `m-metamodel` seam carrying the same structure, so the
conventions that decide it live here once rather than once per frontend: the
canonical name and physical column of each As-Of Axis endpoint, the As-Of Axes a
Temporality Profile derives, and the unique primary-key Index every Entity that
declares a primary key carries.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from parallax.core.metamodel._identities import EntityIdentity, IndexIdentity
from parallax.core.metamodel._naming import default_column_name
from parallax.core.metamodel._values import (
    AsOfAxisMetadata,
    AttributeMetadata,
    IndexMetadata,
    PrimaryKey,
    StorageContainer,
    Table,
    TemporalDimension,
)

__all__ = [
    "CONVENTIONAL_TEMPORAL_NAMES",
    "NONTEMPORAL",
    "TEMPORALITY_PROFILES",
    "TEMPORAL_MEMBERS",
    "DerivedAxis",
    "TemporalEndpoint",
    "derive_primary_key_index",
    "derive_temporal_structure",
    "primary_key_index_name",
    "temporality_profile",
]

NONTEMPORAL: Final[str] = "nontemporal"
"""The Temporality Profile an Entity that declares none falls back to."""


@dataclass(frozen=True, slots=True)
class TemporalEndpoint:
    """One As-Of Axis endpoint's canonical member name over its fixed Column."""

    name: str
    column: str


@dataclass(frozen=True, slots=True)
class DerivedAxis:
    """One As-Of Axis a Temporality Profile derives, endpoints included."""

    dimension: TemporalDimension
    start: TemporalEndpoint
    end: TemporalEndpoint


TEMPORAL_MEMBERS: Final[Mapping[TemporalDimension, tuple[TemporalEndpoint, TemporalEndpoint]]] = (
    MappingProxyType(
        {
            TemporalDimension.VALID_TIME: (
                TemporalEndpoint("validStart", "from_z"),
                TemporalEndpoint("validEnd", "thru_z"),
            ),
            TemporalDimension.TRANSACTION_TIME: (
                TemporalEndpoint("txStart", "in_z"),
                TemporalEndpoint("txEnd", "out_z"),
            ),
        }
    )
)
"""Each Temporal Dimension's start and end endpoint, in canonical axis order.

The Columns are framework-fixed rather than derived: ``defaultColumn("txStart")``
is ``tx_start``, not ``in_z``, so no naming operation can produce them.
"""

CONVENTIONAL_TEMPORAL_NAMES: Final[Mapping[TemporalDimension, tuple[str, str]]] = MappingProxyType(
    {dimension: (start.name, end.name) for dimension, (start, end) in TEMPORAL_MEMBERS.items()}
)
"""The Attribute names each Temporal Dimension reserves once an Entity declares
that dimension. Only the axis's own start and end Attributes may bear them."""

TEMPORALITY_PROFILES: Final[Mapping[str, tuple[TemporalDimension, ...]]] = MappingProxyType(
    {
        NONTEMPORAL: (),
        "transaction-time": (TemporalDimension.TRANSACTION_TIME,),
        "bitemporal": (TemporalDimension.VALID_TIME, TemporalDimension.TRANSACTION_TIME),
    }
)
"""Each Temporality Profile's Temporal Dimensions in canonical axis order.

Valid-Time-Only has no profile: `m-validtime-only` is deferred, so the shape is
unspellable rather than rejected, and activating it later adds one member here.
"""


def derive_temporal_structure(temporality: str | None) -> tuple[DerivedAxis, ...]:
    """The As-Of Axes a Temporality Profile derives, in canonical axis order.

    ``None`` is an Entity that declares no profile and derives nothing, exactly
    as ``nontemporal`` does; the two differ only to whoever asks what an Entity
    declared, which is a family question rather than a derivation one.

    Every endpoint is a Timestamp Attribute over the framework-fixed Column of
    :data:`TEMPORAL_MEMBERS`, placed after every domain Attribute in Valid-Time
    then Transaction-Time order, which is the ``from_z, thru_z, in_z, out_z``
    projection order a Bitemporal Entity carries.
    """
    profile = NONTEMPORAL if temporality is None else temporality
    dimensions = TEMPORALITY_PROFILES.get(profile)
    if dimensions is None:
        raise ValueError(f"{profile!r} is not a temporality profile")
    return tuple(DerivedAxis(dimension, *TEMPORAL_MEMBERS[dimension]) for dimension in dimensions)


def temporality_profile(dimensions: Iterable[TemporalDimension]) -> str:
    """The Temporality Profile whose derivation yields exactly ``dimensions``.

    The inverse of :func:`derive_temporal_structure`, for a consumer holding
    resolved axes that needs the profile an author would have written. A
    dimension set no profile derives — a lone Valid Time above all — has no
    spelling and is refused rather than approximated.
    """
    declared = frozenset(dimensions)
    for profile, derived in TEMPORALITY_PROFILES.items():
        if frozenset(derived) == declared:
            return profile
    spelled = ", ".join(sorted(dimension.name for dimension in declared))
    raise ValueError(f"no temporality profile derives {{{spelled}}}")


def primary_key_index_name(entity: EntityIdentity, container: StorageContainer | None) -> str:
    """The derived primary-key Index's name for one Entity.

    An Entity that owns a Table names the Index after it. A tableless
    table-per-concrete-subtype root owns the family's key and axes but no Table,
    so its Index takes the Entity's own name folded to the same lowercase shape a
    Table name carries.
    """
    stem = (
        container.name
        if isinstance(container, Table)
        else default_column_name(entity.name[:1].lower() + entity.name[1:])
    )
    return f"{stem}_pk"


def derive_primary_key_index(
    *,
    entity: EntityIdentity,
    container: StorageContainer | None,
    attributes: Sequence[AttributeMetadata],
    as_of_axes: Sequence[AsOfAxisMetadata],
) -> IndexMetadata | None:
    """The Entity's unique primary-key Index, or absence when it declares no key.

    The Index is derived on the Entity that *declares* the primary key rather
    than the one that owns the Table, because every Index component is a distinct
    local Attribute of the Index's Entity and Indices are not inherited: under
    ``table-per-concrete-subtype`` the concrete subtype declares neither the key
    nor the axes. Storage consumers resolve each component through the applicable
    layout's contributor lookup, which reaches a root-declared Attribute from
    every concrete Table.

    Components are the local primary-key Attributes in declaration order followed
    by each declared axis's **end** Attribute in canonical dimension order. The
    end Attributes are what a Latest predicate and a milestone close both pin, so
    keying the physical row identity on them makes both a key hit. They are
    distinct by construction: each dimension derives its own endpoints, and no
    other Attribute may bear one of their names.

    The derivation is local and reference-free: it reads one declaration and
    resolves nothing across the model.
    """
    components = [
        attribute.identity
        for attribute in attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    if not components:
        return None
    components.extend(
        axis.end_attribute for axis in sorted(as_of_axes, key=lambda axis: axis.dimension.value)
    )
    return IndexMetadata(
        identity=IndexIdentity(entity, primary_key_index_name(entity, container)),
        attributes=tuple(components),
        unique=True,
    )
