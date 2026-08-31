"""Case-format carrier normalization before strict core semantic ingresses."""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import cast

from parallax.core import inheritance, predicate
from parallax.core.base import TIMESTAMP, ManagedValue, NeutralType, matches_neutral_type
from parallax.core.base import Decimal as DecimalType
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
    split_reference,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import AsOf, AsOfRange, ObjectQueryNode, TemporalSelection
from parallax.core.unit_work import instructions
from parallax.core.unit_work.instructions import (
    KeyedWrite,
    PredicateSelection,
    PredicateWrite,
    PreparedWrite,
    WriteAssignment,
    WriteInstruction,
)
from parallax.core.wire import encode_wire
from parallax.core.wire._json import authored_token

__all__ = ["normalize_case_query", "prepare_case_write"]

type _Occurrence = ValueObjectMetadata | NestedValueObjectMetadata
type _ScalarMember = AttributeMetadata | ValueObjectAttributeMetadata


def prepare_case_write(instruction: WriteInstruction, model: AcceptedMetamodel) -> PreparedWrite:
    """Normalize one case-format instruction and invoke strict Wire preparation.

    Case YAML represents Decimal values as JSON numbers even though canonical
    Wire represents them as fixed-scale strings. Synthetic conformance cases may
    also carry values already in their managed Python form. This seam converts
    only those carrier differences, using the declared member type; structural
    and semantic defects remain unchanged for ``prepare_wire_write`` to classify,
    validate, freeze, and retain in its ``PreparedWrite`` result.
    """
    return instructions.prepare_wire_write(_normalize_instruction(instruction, model), model)


def normalize_case_query(query: ObjectQueryNode, model: AcceptedMetamodel) -> ObjectQueryNode:
    """Normalize case-format carriers without performing query validation.

    Compatibility YAML uses JSON numbers for Decimal operands and accepts ISO
    timestamp spellings that are broader than canonical Wire. This ingress
    rewrites only those declared-type carrier differences. Core preflight still
    owns model-aware validation, classification, and lowering of the returned
    canonical query.
    """
    temporal = {
        dimension: _normalize_temporal_selection(selection)
        for dimension, selection in query.temporal.items()
    }
    return replace(
        query,
        predicate=_normalize_predicate(query.predicate, model),
        temporal=MappingProxyType(temporal),
    )


def _normalize_temporal_selection(selection: TemporalSelection) -> TemporalSelection:
    if isinstance(selection, AsOf) and selection.coordinate != "latest":
        return replace(selection, coordinate=_wire_bound(selection.coordinate))
    if isinstance(selection, AsOfRange):
        return replace(
            selection,
            start=_wire_bound(selection.start),
            end=_wire_bound(selection.end),
        )
    return selection


def _normalize_instruction(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> WriteInstruction:
    target_name = (
        instruction.entity if isinstance(instruction, KeyedWrite) else instruction.target.entity
    )
    entity = entity_by_name(model, target_name)
    if entity is None:
        return instruction
    valid_from = _wire_bound(instruction.valid_from)
    until = _wire_bound(instruction.until)
    if isinstance(instruction, KeyedWrite):
        members = _entity_members(model, entity)
        rows = tuple(
            {
                name: _normalize_member(members[name], value) if name in members else value
                for name, value in row.items()
            }
            for row in instruction.rows
        )
        return KeyedWrite(instruction.mutation, instruction.entity, rows, valid_from, until)

    members = _entity_members(model, entity)
    assignments = tuple(
        WriteAssignment(
            assignment.attr,
            _normalize_member(member, assignment.value)
            if (member := members.get(assignment.attr.rpartition(".")[2])) is not None
            else assignment.value,
        )
        for assignment in instruction.assignments
    )
    selection = PredicateSelection(
        instruction.target.entity,
        _normalize_predicate(instruction.target.predicate, model),
    )
    return PredicateWrite(
        instruction.mutation,
        selection,
        assignments,
        valid_from,
        until,
    )


def _entity_members(
    model: AcceptedMetamodel, entity: EntityMetadata
) -> dict[str, AttributeMetadata | ValueObjectMetadata]:
    position = inheritance.view(model).entity(entity.identity)
    if position is None:
        return {}
    return {
        **{member.identity.name: member for member in position.applicable_attributes},
        **{member.identity.path[-1]: member for member in position.applicable_value_objects},
    }


def _normalize_member(member: AttributeMetadata | ValueObjectMetadata, value: object) -> object:
    if value is None:
        return None
    if isinstance(member, AttributeMetadata):
        return _wire_leaf(member.type, value)
    return _normalize_occurrence(member, value)


def _normalize_occurrence(occurrence: _Occurrence, value: object) -> object:
    if occurrence.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            return value
        return [_normalize_document(occurrence, item) for item in cast("Sequence[object]", value)]
    return _normalize_document(occurrence, value)


def _normalize_document(container: _Occurrence, value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    attributes = {member.identity.name: member for member in container.attributes}
    occurrences = {member.identity.path[-1]: member for member in container.value_objects}
    return {
        name: (
            _wire_leaf(attribute.type, nested)
            if nested is not None and (attribute := attributes.get(name)) is not None
            else _normalize_occurrence(occurrence, nested)
            if nested is not None and (occurrence := occurrences.get(name)) is not None
            else nested
        )
        for name, nested in cast("Mapping[str, object]", value).items()
    }


def _wire_leaf(neutral_type: NeutralType, value: object | None) -> object | None:
    if value is None:
        return None
    if matches_neutral_type(value, neutral_type):
        return encode_wire(neutral_type, cast("ManagedValue", value))
    if neutral_type == TIMESTAMP and isinstance(value, str):
        try:
            instant = dt.datetime.fromisoformat(value)
        except ValueError:
            return value
        if matches_neutral_type(instant, TIMESTAMP):
            return encode_wire(TIMESTAMP, instant)
        return value
    if (
        isinstance(neutral_type, DecimalType)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return _case_decimal(value, neutral_type)
    return value


def _wire_bound(value: str | dt.datetime | None) -> str | None:
    normalized = _wire_leaf(TIMESTAMP, value)
    return None if normalized is None else cast("str", normalized)


def _case_decimal(value: int | float, neutral_type: DecimalType) -> object:
    try:
        number = decimal.Decimal(authored_token(value) or str(value))
    except decimal.InvalidOperation:
        return value
    sign, digits, exponent = number.as_tuple()
    if not isinstance(exponent, int):
        return value
    original_exponent = exponent
    last = len(digits)
    while last and digits[last - 1] == 0:
        last -= 1
        exponent += 1
    if exponent < -neutral_type.scale:
        return value
    if number and abs(number.adjusted()) > neutral_type.precision + neutral_type.scale:
        return value
    normalized = decimal.Decimal((sign, digits, original_exponent))
    return format(normalized, f".{neutral_type.scale}f")


def _normalize_predicate(
    node: predicate.PredicateNode,
    model: AcceptedMetamodel,
    element_container: _Occurrence | None = None,
) -> predicate.PredicateNode:
    match node:
        case predicate.Comparison(attr=attr, value=value):
            return replace(node, value=_predicate_leaf(model, attr, value))
        case predicate.Between(attr=attr, lower=lower, upper=upper):
            return replace(
                node,
                lower=_predicate_leaf(model, attr, lower),
                upper=_predicate_leaf(model, attr, upper),
            )
        case predicate.Membership(attr=attr, values=values):
            return replace(
                node,
                values=tuple(_predicate_leaf(model, attr, value) for value in values),
            )
        case predicate.NestedComparison(path=path, value=value):
            return replace(
                node,
                value=_nested_predicate_leaf(model, element_container, path, value),
            )
        case predicate.NestedRange(path=path, lower=lower, upper=upper):
            return replace(
                node,
                lower=_nested_predicate_leaf(model, element_container, path, lower),
                upper=_nested_predicate_leaf(model, element_container, path, upper),
            )
        case predicate.NestedMembership(path=path, values=values):
            return replace(
                node,
                values=tuple(
                    _nested_predicate_leaf(model, element_container, path, value)
                    for value in values
                ),
            )
        case predicate.And(operands=operands) | predicate.Or(operands=operands):
            return replace(
                node,
                operands=tuple(
                    _normalize_predicate(operand, model, element_container) for operand in operands
                ),
            )
        case (
            predicate.Not(operand=operand)
            | predicate.Group(operand=operand)
            | predicate.Narrow(operand=operand)
        ):
            return replace(
                node,
                operand=_normalize_predicate(operand, model, element_container),
            )
        case (
            predicate.NestedExists(path=path, where=where)
            | predicate.NestedNotExists(path=path, where=where)
        ):
            container = _predicate_container(model, path)
            return (
                node
                if where is None or container is None
                else replace(node, where=_normalize_predicate(where, model, container))
            )
        case (
            predicate.Navigate(op=inner)
            | predicate.Exists(op=inner)
            | predicate.NotExists(op=inner)
        ):
            return node if inner is None else replace(node, op=_normalize_predicate(inner, model))
        case _:
            return node


def _predicate_leaf(model: AcceptedMetamodel, reference: str, value: object) -> object:
    entity_name, path = split_reference(reference)
    if entity_name is None or len(path) != 1:
        return value
    entity = entity_by_name(model, entity_name)
    if entity is None:
        return value
    member = _entity_members(model, entity).get(path[0])
    return _wire_leaf(member.type, value) if isinstance(member, AttributeMetadata) else value


def _nested_predicate_leaf(
    model: AcceptedMetamodel,
    element_container: _Occurrence | None,
    reference: str,
    value: object,
) -> object:
    leaf = (
        _relative_leaf(element_container, reference.split("."))
        if element_container is not None
        else _predicate_nested_leaf(model, reference)
    )
    return _wire_leaf(leaf.type, value) if leaf is not None else value


def _predicate_nested_leaf(
    model: AcceptedMetamodel, reference: str
) -> ValueObjectAttributeMetadata | None:
    entity_name, path = split_reference(reference)
    if entity_name is None or len(path) < 2:
        return None
    container = _top_level_occurrence(model, entity_name, path[0])
    return None if container is None else _relative_leaf(container, path[1:])


def _predicate_container(model: AcceptedMetamodel, reference: str) -> _Occurrence | None:
    entity_name, path = split_reference(reference)
    if entity_name is None or not path:
        return None
    container = _top_level_occurrence(model, entity_name, path[0])
    for name in path[1:]:
        if container is None:
            return None
        container = container.value_object(name)
    return container


def _top_level_occurrence(
    model: AcceptedMetamodel, entity_name: str, member: str
) -> ValueObjectMetadata | None:
    entity = entity_by_name(model, entity_name)
    if entity is None:
        return None
    value = _entity_members(model, entity).get(member)
    if value is None or isinstance(value, AttributeMetadata):
        return None
    return value


def _relative_leaf(
    container: _Occurrence | None, path: Sequence[str]
) -> ValueObjectAttributeMetadata | None:
    if container is None or not path:
        return None
    current = container
    for name in path[:-1]:
        nested = current.value_object(name)
        if nested is None:
            return None
        current = nested
    return current.attribute(path[-1])
