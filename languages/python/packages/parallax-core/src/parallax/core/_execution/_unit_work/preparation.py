from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from parallax.core import inheritance
from parallax.core.base import typed_converter
from parallax.core.document_codec._plan import (
    BORROWED_DOCUMENTS,
    MAPPING_DOCUMENTS,
    AuthoringCatalog,
    AuthoringLane,
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

__all__ = ["TYPED_LANE", "WIRE_LANE", "EntityPreparation", "WritePreparation"]

TYPED_LANE: Final = 0
"""The authoring lane of a developer's native carriers."""
WIRE_LANE: Final = 1
"""The authoring lane of serialized Wire literals."""
_LANES: Final = (
    AuthoringLane(typed_converter, BORROWED_DOCUMENTS),
    AuthoringLane(wire_converter, MAPPING_DOCUMENTS),
)


@dataclass(frozen=True, slots=True)
class EntityPreparation:
    """What every write of one Entity is prepared against.

    ``plan`` walks the Entity's member shape against each lane's converters,
    and ``key`` is its primary key's position there. ``insert_required`` marks
    the members an opening row must state with a value, ``framework_owned`` the
    members the framework supplies, which a Typed row never authors, and
    ``read_only`` the members outside the key that are immutable once inserted.
    A replacement must state each member in ``replace_required``, and writes
    one in ``replace_nulled`` it leaves unstated as null.
    ``typed_class`` is the Entity Class whose instances hold their members in
    ``selection``'s order, proven so when the model was prepared, or ``None``
    where no class was.
    """

    selection: RowSelection
    plan: AuthoringPlan
    key: int
    insert_required: int
    framework_owned: int
    read_only: int
    replace_required: int
    replace_nulled: int
    typed_class: type | None


class WritePreparation:
    """One model's write preparation products, every Entity's derived at
    construction.

    ``absent`` is the marker the model's accepted Entity State spells an
    omitted member with; every row selection and nested occurrence cell the
    plans author carries that same object. ``positional`` names, by Entity,
    the class each one's instances are proven to hold their members in member
    order.
    """

    __slots__ = ("_entities", "absent", "meta")

    def __init__(
        self,
        meta: Metamodel,
        *,
        absent: object,
        positional: Mapping[EntityIdentity, type] | None = None,
    ) -> None:
        self.meta = meta
        self.absent = absent
        families = inheritance.view(meta)
        catalog = AuthoringCatalog(_LANES, absent=absent)
        entities: dict[EntityIdentity, EntityPreparation] = {}
        for entity in meta.entities:
            view = families.entity(entity.identity)
            if view is None:  # pragma: no cover - the facet covers every accepted Entity
                raise ValueError(f"{entity.identity.canonical}: no Inheritance Facet view")
            entities[entity.identity] = _entity_preparation(
                view,
                catalog,
                absent,
                None if positional is None else positional.get(entity.identity),
            )
        self._entities: Mapping[EntityIdentity, EntityPreparation] = entities

    def entity(self, identity: EntityIdentity) -> EntityPreparation:
        return self._entities[identity]


def _entity_preparation(
    view: inheritance.InheritanceEntityView,
    catalog: AuthoringCatalog,
    absent: object,
    typed_class: type | None,
) -> EntityPreparation:
    selection = view.member_selection
    key = selection.index[view.primary_key.identity]
    required = 0
    framework_owned = 0
    read_only = 0
    replaced = 0
    for position, member in enumerate(selection.bindings):
        bit = 1 << position
        attribute = member if isinstance(member, AttributeMetadata) else None
        if attribute is not None and attribute.framework_owned:
            framework_owned |= bit
        elif not member.nullable and member.multiplicity is Multiplicity.ONE:
            required |= bit
        if attribute is not None and attribute.read_only and position != key:
            read_only |= bit
        if member.multiplicity is Multiplicity.ONE and position != key:
            replaced |= bit
    replaced &= ~(framework_owned | read_only)
    return EntityPreparation(
        selection=RowSelection(selection, absent),
        plan=catalog.plan(selection.shape),
        key=key,
        insert_required=required,
        framework_owned=framework_owned,
        read_only=read_only,
        replace_required=replaced & required,
        replace_nulled=replaced & ~required,
        typed_class=typed_class,
    )
