from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core import inheritance
from parallax.core.base import typed_converter
from parallax.core.document_codec._plan import (
    BORROWED_DOCUMENTS,
    MAPPING_DOCUMENTS,
    AuthoringCatalog,
    AuthoringPlan,
)
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    Multiplicity,
)
from parallax.core.wire._codec import wire_converter
from parallax.core.write_plan.managed_row import RowSelection

__all__ = ["EntityPreparation", "WritePreparation"]


@dataclass(frozen=True, slots=True)
class EntityPreparation:
    """What every write of one Entity is prepared against.

    ``typed`` and ``wire`` walk the Entity's member shape against each lane's
    converters. ``insert_required`` marks the members an opening row must
    state with a value, and ``framework_owned`` the members the framework
    supplies, which a Typed row never authors.
    """

    selection: RowSelection
    typed: AuthoringPlan
    wire: AuthoringPlan
    insert_required: int
    framework_owned: int


class WritePreparation:
    """One model's write preparation products, every Entity's derived at
    construction.

    ``absent`` is the marker the model's accepted Entity State spells an
    omitted member with; every row selection and nested occurrence cell the
    plans author carries that same object.
    """

    __slots__ = ("_entities", "absent", "meta")

    def __init__(self, meta: Metamodel, *, absent: object) -> None:
        self.meta = meta
        self.absent = absent
        families = inheritance.view(meta)
        typed = AuthoringCatalog(typed_converter, BORROWED_DOCUMENTS, absent=absent)
        wire = AuthoringCatalog(wire_converter, MAPPING_DOCUMENTS, absent=absent)
        entities: dict[EntityIdentity, EntityPreparation] = {}
        for entity in meta.entities:
            view = families.entity(entity.identity)
            if view is None:  # pragma: no cover - the facet covers every accepted Entity
                raise ValueError(f"{entity.identity.canonical}: no Inheritance Facet view")
            entities[entity.identity] = _entity_preparation(view, typed, wire, absent)
        self._entities: Mapping[EntityIdentity, EntityPreparation] = MappingProxyType(entities)

    def entity(self, identity: EntityIdentity) -> EntityPreparation:
        return self._entities[identity]


def _entity_preparation(
    view: inheritance.InheritanceEntityView,
    typed: AuthoringCatalog,
    wire: AuthoringCatalog,
    absent: object,
) -> EntityPreparation:
    selection = view.member_selection
    required = 0
    framework_owned = 0
    for position, member in enumerate(selection.bindings):
        owned = isinstance(member, AttributeMetadata) and member.framework_owned
        if owned:
            framework_owned |= 1 << position
        elif not member.nullable and member.multiplicity is Multiplicity.ONE:
            required |= 1 << position
    return EntityPreparation(
        selection=RowSelection(selection, absent),
        typed=typed.plan(selection.shape),
        wire=wire.plan(selection.shape),
        insert_required=required,
        framework_owned=framework_owned,
    )
