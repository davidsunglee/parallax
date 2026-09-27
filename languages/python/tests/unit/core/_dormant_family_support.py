"""A family whose nested dormant branch contributes to its declaration stream.

``ZDormant`` and its abstract child ``ADormantChild`` reach no concrete, so both
are dormant, and the child's identity sorts first: the canonical suffix places
it before its parent. The child declares its Attributes out of alphabetical
order, so local declaration order stays distinguishable from any sort. Every
participant declares Attributes and a top-level Value Object whose shape holds
one leaf, so placement reaches inside an occurrence too.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore.
"""

from __future__ import annotations

from typing import Final, Literal

from parallax.core.base import STRING
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    Column,
    ConcreteSubtype,
    ExactEntityReference,
    StorageLayout,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    default_column_name,
)
from tests.unit._metamodel_support import Declaration, Source, attribute, identity, key, source

__all__ = ["DORMANT", "DORMANT_CHILD", "LIVE", "ROOT", "dormant_family"]

ROOT: Final = identity("Record")
LIVE: Final = identity("Live")
DORMANT: Final = identity("ZDormant")
DORMANT_CHILD: Final = identity("ADormantChild")


def _occurrence(name: str) -> ValueObjectOccurrenceDeclaration:
    return ValueObjectOccurrenceDeclaration(
        name=name,
        storage=Column(default_column_name(name)),
        shape=ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=(ValueObjectAttributeDeclaration("label", type=STRING),),
        ),
    )


def dormant_family(
    strategy: Literal["tph", "tpcs"], *, layout: StorageLayout | None = None
) -> Source:
    """The family under ``strategy``, its root declaring ``layout``."""
    shared = strategy == "tph"
    return source(
        Declaration(
            identity=ROOT,
            container=Table("record") if shared else None,
            layout=layout,
            attributes=(key(ROOT), attribute(ROOT, "title", type=STRING)),
            value_objects=(_occurrence("summary"),),
            inheritance=AbstractRoot(
                TablePerHierarchy("kind") if shared else TablePerConcreteSubtype()
            ),
        ),
        Declaration(
            identity=LIVE,
            container=None if shared else Table("live"),
            attributes=(attribute(LIVE, "liveValue", type=STRING),),
            value_objects=(_occurrence("liveDetail"),),
            inheritance=ConcreteSubtype(ExactEntityReference(ROOT), "live" if shared else None),
        ),
        Declaration(
            identity=DORMANT,
            attributes=(attribute(DORMANT, "dormantValue", type=STRING),),
            value_objects=(_occurrence("dormantDetail"),),
            inheritance=AbstractSubtype(ExactEntityReference(ROOT)),
        ),
        Declaration(
            identity=DORMANT_CHILD,
            attributes=(
                attribute(DORMANT_CHILD, "childZeta", type=STRING),
                attribute(DORMANT_CHILD, "childAlpha", type=STRING),
            ),
            value_objects=(_occurrence("childDetail"),),
            inheritance=AbstractSubtype(ExactEntityReference(DORMANT)),
        ),
    )
