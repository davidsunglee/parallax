"""The frontend-neutral temporal convention table and derived primary-key Index.

Both frontends reach the `m-metamodel` seam carrying the same structure, so the
conventions that decide it live here once rather than once per frontend: the
canonical name and physical column of each As-Of Axis endpoint, and the unique
primary-key Index every Entity that declares a primary key carries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from parallax.core.metamodel._identities import (
    AttributeIdentity,
    EntityIdentity,
    IndexIdentity,
)
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
    "TEMPORAL_MEMBERS",
    "TemporalEndpoint",
    "derive_primary_key_index",
    "primary_key_index_name",
]


@dataclass(frozen=True, slots=True)
class TemporalEndpoint:
    """One As-Of Axis endpoint's canonical member name over its fixed Column."""

    name: str
    column: str


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
    keying the physical row identity on them makes both a key hit.

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
    seen: set[AttributeIdentity] = set(components)
    for axis in sorted(as_of_axes, key=lambda axis: axis.dimension.value):
        if axis.end_attribute in seen:
            continue
        seen.add(axis.end_attribute)
        components.append(axis.end_attribute)
    return IndexMetadata(
        identity=IndexIdentity(entity, primary_key_index_name(entity, container)),
        attributes=tuple(components),
        unique=True,
    )
