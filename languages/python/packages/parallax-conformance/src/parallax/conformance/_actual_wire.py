"""Canonical compatibility observations projected from accepted Metadata.

This module is the production-side oracle for values that do not already cross
the public Wire read boundary.  Every typed value is paired with its declared
Neutral Type before it reaches :mod:`parallax.core.wire`; Python carrier classes
never select a type here.  A ``json`` Attribute is one recursively normalized
value, while a Value Object is walked by its recursively declared leaf types.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core import inheritance, storage_layout
from parallax.core.base import INFINITY_LITERAL, JSON, ManagedValue, NeutralType, TemporalBound
from parallax.core.db_port import Row
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    TemporalDimension,
    ValueObjectIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.storage_layout import RelationalDocument, TableLayout
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey
from parallax.core.wire import (
    WireDecodingError,
    WireEncodingError,
    WireValue,
    decode_canonical_wire,
    encode_wire,
)

__all__ = ["ActualWireProjection"]

type _ValueObject = ValueObjectMetadata | NestedValueObjectMetadata


class ActualWireProjection:
    """Project managed production values into canonical Wire observations.

    The accepted model is retained because physical rows, logical published
    rows, Object Keys, and create/change payloads each name metadata differently.
    The public methods hide those lookups and converge on :meth:`scalar`.
    """

    __slots__ = ("_model",)

    def __init__(self, model: Metamodel) -> None:
        self._model = model

    def scalar(self, member: AttributeMetadata, value: object) -> WireValue:
        """One Attribute value in canonical Wire form; null is enclosing presence."""
        if value is None:
            return None
        if self._is_temporal_end(member) and (
            isinstance(value, TemporalBound) or value == INFINITY_LITERAL
        ):
            return INFINITY_LITERAL
        return self._typed(member.type, value)

    def published_row(self, query: ObjectQueryNode, row: Mapping[str, object]) -> Row:
        """A row-form query result, resolved from its projected physical columns."""
        attributes, value_objects = self._query_members(query)
        by_column: dict[str, AttributeMetadata | ValueObjectMetadata] = {
            member.storage.name: member for member in (*attributes, *value_objects)
        }
        projected: Row = {}
        for name, value in row.items():
            if name == "familyVariant":
                projected[name] = value
                continue
            member = by_column.get(name)
            if isinstance(member, AttributeMetadata):
                projected[name] = self.scalar(member, value)
            elif member is not None:
                projected[name] = self.value_object(member, value)
            else:
                raise ValueError(
                    f"{query.target.canonical}: no projected member owns column {name!r}"
                )
        return projected

    def entity_values(
        self, entity: EntityMetadata, values: Mapping[str, object], *, omit_framework: bool = False
    ) -> dict[str, object]:
        """Logical member-named values for a public Wire create/change payload."""
        view = inheritance.view(self._model).entity(entity.identity)
        if view is None:  # pragma: no cover - every accepted Entity has a view
            raise ValueError(f"{entity.identity.canonical}: no inheritance position")
        attributes = {member.identity.name: member for member in view.applicable_attributes}
        value_objects = {
            member.identity.path[-1]: member for member in view.applicable_value_objects
        }
        projected: dict[str, object] = {}
        for name, value in values.items():
            attribute = attributes.get(name)
            if attribute is not None:
                if omit_framework and attribute.framework_owned:
                    continue
                projected[name] = self.scalar(attribute, value)
                continue
            occurrence = value_objects.get(name)
            if occurrence is not None:
                projected[name] = self.value_object(occurrence, value)
                continue
            raise ValueError(f"{entity.identity.canonical}: no applicable member {name!r}")
        return projected

    def value_object(self, occurrence: _ValueObject, value: object) -> object:
        """One Value Object occurrence with every declared leaf projected recursively."""
        if value is None:
            return None
        if occurrence.multiplicity is Multiplicity.MANY:
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
                raise ValueError(
                    f"{occurrence.identity.path}: a many occurrence requires a sequence"
                )
            source = cast("Sequence[object]", value)
            return [self._value_object_element(occurrence, item) for item in source]
        return self._value_object_element(occurrence, value)

    def table_row(self, layout: TableLayout, row: Mapping[str, object]) -> Row:
        """One complete physical table row in its compiled slot sequence."""
        projected: Row = {}
        for slot in layout.columns:
            name = slot.column.name
            value = row.get(name)
            contributor = slot.contributor
            if isinstance(contributor, AttributeIdentity):
                projected[name] = self.scalar(self._attribute(contributor), value)
            elif isinstance(contributor, ValueObjectIdentity):
                projected[name] = self.value_object(self._value_object(contributor), value)
            elif isinstance(contributor, RelationalDocument):
                projected[name] = self._relational_document(layout, value)
            else:
                projected[name] = value
        return projected

    def object_key(self, key: ObjectKey) -> dict[str, object]:
        """One Object Key with each primary-key value resolved to its declaration."""
        entity = self._entity(key.entity)
        return {
            "entity": key.entity.canonical,
            "key": {
                name: self.scalar(self._applicable_attribute(entity, name), value)
                for name, value in key.primary_key
            },
        }

    def pin(self, pin: Pin) -> dict[str, object]:
        """One milestone pin with each present axis encoded as Timestamp."""
        from parallax.core.base import TIMESTAMP

        coordinates = (
            ("valid-time", pin.valid_time),
            ("transaction-time", pin.tx_time),
        )
        return {
            name: self._typed(TIMESTAMP, value) for name, value in coordinates if value is not None
        }

    def _typed(self, neutral_type: NeutralType, value: object) -> WireValue:
        """Encode a managed value, accepting an already-canonical Wire value idempotently."""
        try:
            return encode_wire(neutral_type, cast("ManagedValue", value))
        except WireEncodingError as encoding_failure:
            try:
                managed = decode_canonical_wire(neutral_type, cast("WireValue", value))
            except WireDecodingError as decoding_failure:
                raise encoding_failure from decoding_failure
            return encode_wire(neutral_type, managed)

    def _value_object_element(self, occurrence: _ValueObject, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(
                f"{occurrence.identity.path}: a value-object element requires a mapping"
            )
        source = cast("Mapping[str, object]", value)
        attributes = {member.identity.name: member for member in occurrence.attributes}
        nested = {member.identity.path[-1]: member for member in occurrence.value_objects}
        projected: dict[str, object] = {}
        for name, item in source.items():
            leaf = attributes.get(name)
            if leaf is not None:
                projected[name] = None if item is None else self._typed(leaf.type, item)
                continue
            child = nested.get(name)
            if child is not None:
                projected[name] = self.value_object(child, item)
                continue
            projected[name] = self._typed(JSON, item)
        return projected

    def _query_members(
        self, query: ObjectQueryNode
    ) -> tuple[tuple[AttributeMetadata, ...], tuple[ValueObjectMetadata, ...]]:
        entity = self._entity_by_name(query.target.canonical)
        facet = inheritance.view(self._model)
        view = facet.entity(entity.identity)
        if view is None:  # pragma: no cover
            raise ValueError(entity.identity.canonical)
        if query.narrow_to:
            narrowed = facet.position(
                [self._entity_by_name(spelling).identity for spelling in query.narrow_to]
            )
            if narrowed is None:
                raise ValueError(f"{query.target.canonical}: narrowing resolves no position")
            return tuple(narrowed.superset_attributes), tuple(narrowed.superset_value_objects)
        if isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype)):
            return tuple(view.superset_attributes), tuple(view.superset_value_objects)
        return tuple(view.applicable_attributes), tuple(view.applicable_value_objects)

    def _relational_document(self, layout: TableLayout, value: object) -> WireValue:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            return self._typed(JSON, value)
        members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
        for entity in self._model.entities:
            view = inheritance.view(self._model).entity(entity.identity)
            if view is None:
                continue
            for attribute in view.applicable_attributes:
                placement = layout.placement(attribute.identity)
                if isinstance(placement, storage_layout.DocumentPath):
                    members.setdefault(attribute.identity.name, attribute)
            for occurrence in view.applicable_value_objects:
                placement = layout.placement(occurrence.identity)
                if isinstance(placement, storage_layout.DocumentPath):
                    members.setdefault(occurrence.identity.path[-1], occurrence)
        projected: dict[str, object] = {}
        for name, item in cast("Mapping[str, object]", value).items():
            member = members.get(name)
            if isinstance(member, AttributeMetadata):
                projected[name] = self.scalar(member, item)
            elif member is not None:
                projected[name] = self.value_object(member, item)
            else:
                projected[name] = self._typed(JSON, item)
        return cast("WireValue", projected)

    def _entity_by_name(self, name: str) -> EntityMetadata:
        entity = entity_by_name(self._model, name)
        if entity is None:
            raise ValueError(f"{name!r}: no such Entity")
        return entity

    def _entity(self, identity: EntityIdentity) -> EntityMetadata:
        entity = self._model.entity(identity)
        if entity is None:
            raise ValueError(f"{identity.canonical!r}: no such Entity")
        return entity

    def _attribute(self, identity: AttributeIdentity) -> AttributeMetadata:
        entity = self._entity(identity.entity)
        attribute = entity.attribute(identity.name)
        if attribute is None:
            raise ValueError(f"{identity.entity.canonical}: no Attribute {identity.name!r}")
        return attribute

    def _applicable_attribute(self, entity: EntityMetadata, name: str) -> AttributeMetadata:
        view = inheritance.view(self._model).entity(entity.identity)
        attribute = None if view is None else view.applicable_attribute(name)
        if attribute is None:
            raise ValueError(f"{entity.identity.canonical}: no applicable Attribute {name!r}")
        return attribute

    def _is_temporal_end(self, member: AttributeMetadata) -> bool:
        entity = self._entity(member.identity.entity)
        for dimension in TemporalDimension:
            axis = entity.as_of_axis(dimension)
            if axis is not None and axis.end_attribute == member.identity:
                return True
        return False

    def _value_object(self, identity: ValueObjectIdentity) -> ValueObjectMetadata:
        entity = self._entity(identity.entity)
        view = inheritance.view(self._model).entity(entity.identity)
        occurrence = None if view is None else view.applicable_value_object(identity.path[-1])
        if occurrence is None:
            raise ValueError(f"{identity.entity.canonical}: no Value Object {identity.path[-1]!r}")
        return occurrence
