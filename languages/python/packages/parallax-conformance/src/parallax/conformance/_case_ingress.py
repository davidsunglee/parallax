from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast, overload

from parallax.conformance._case_literal import normalize_case_bound, normalize_case_literal
from parallax.core import inheritance, predicate, temporal_read
from parallax.core.base import (
    INFINITY,
    INFINITY_LITERAL,
    NeutralType,
    Timestamp,
    coerce_neutral_input,
    matches_neutral_type,
)
from parallax.core.document_codec._authoring import MAPPING_SOURCE_ACCESS, prepare_authoring
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityMetadata,
    Leaf,
    Multiplicity,
    OccurrenceMetadata,
    TemporalDimension,
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
    PreparedTargetWrite,
    PreparedWrite,
    TargetWrite,
    WriteAssignment,
    WriteInstruction,
)
from parallax.core.wire import WireDecodingError, WireValue, decode_wire
from parallax.core.write_plan.columns import freeze_retained_value

__all__ = ["decode_case_row", "normalize_case_query", "prepare_case_write"]

type _ScalarMember = AttributeMetadata | ValueObjectAttributeMetadata


@overload
def prepare_case_write(
    instruction: TargetWrite, model: AcceptedMetamodel
) -> PreparedTargetWrite: ...
@overload
def prepare_case_write(
    instruction: KeyedWrite | PredicateWrite, model: AcceptedMetamodel
) -> PreparedWrite: ...
@overload
def prepare_case_write(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> PreparedWrite | PreparedTargetWrite: ...
def prepare_case_write(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> PreparedWrite | PreparedTargetWrite:
    """Normalize one case-format instruction and invoke strict Wire preparation.

    Synthetic conformance cases may carry values already in their managed Python
    form. This seam encodes only those, using the declared member type; authored
    JSON values, structural defects, and semantic defects reach
    ``prepare_wire_write`` unchanged for it to decode, classify, validate, freeze,
    and retain in its prepared result.
    """
    return instructions.prepare_wire_write(_normalize_instruction(instruction, model), model)


def decode_case_row(
    row: Mapping[str, object], model: AcceptedMetamodel, entity: EntityMetadata
) -> Mapping[str, object]:
    """One case-format row of ``entity`` state as managed members, judging
    nothing.

    For state a case states rather than a write it authors — seeded fixtures,
    and the members an edit assigns its copy. A stored row holds the open bound
    in its axis ends, so a declared Transaction-Time or Valid-Time end spelled
    ``infinity`` is the managed :data:`~parallax.core.base.INFINITY`; every other
    Timestamp leaf stays finite-only. A ``WireDecodingError`` surfaces as the
    :class:`~parallax.core.unit_work.instructions.InstructionRejectedError` Wire
    preparation raises for it.

    A logical member name the family-effective selection does not declare is
    refused rather than dropped: the row is the whole persisted state a later
    write carries forward. Keys inside a Structured Column value are the
    document's own and are not judged here.
    """
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - every accepted Entity has a view
        raise ValueError(f"{entity.identity.canonical}: no inheritance position")
    shape = position.member_selection.shape
    undeclared = sorted(name for name in row if shape.position(name) is None)
    if undeclared:
        raise ValueError(
            f"{entity.identity.canonical}: a case row names {undeclared!r}, which the "
            "Entity's family declares no member of"
        )
    return prepare_authoring(
        shape,
        row,
        source_access=MAPPING_SOURCE_ACCESS,
        normalize_leaf=_CaseRowLeaves(_temporal_ends(model, entity)).normalize,
        path=entity.identity.canonical,
        fill_missing_many=False,
        allow_root_markers=True,
    ).value


def _temporal_ends(model: AcceptedMetamodel, entity: EntityMetadata) -> tuple[Leaf, ...]:
    """The canonical definitions of ``entity``'s declared axis ends.

    Each end is resolved on the Entity that declares it, so a leaf of the
    family-effective member shape is an axis end exactly when it IS one of these
    definitions: inheritance selections reuse the declaration-owned objects
    (`m-inheritance`), while a nested leaf merely named or typed like one is a
    different object.
    """
    temporal = temporal_read.view(model)
    ends: list[Leaf] = []
    for dimension in TemporalDimension:
        axis = temporal.axis(entity.identity, dimension)
        if axis is None:
            continue
        identity = axis.end_attribute
        declaring = model.entity(identity.entity)
        attribute = None if declaring is None else declaring.attribute(identity.name)
        if attribute is None:  # pragma: no cover - an accepted axis names a declared end
            raise ValueError(f"{identity.entity.canonical}: no declared axis end {identity.name}")
        ends.append(attribute.definition)
    return tuple(ends)


@dataclass(frozen=True, slots=True)
class _CaseRowLeaves:
    ends: tuple[Leaf, ...]

    def normalize(self, leaf: Leaf, value: object, path: str) -> tuple[object, bool]:
        if (value is INFINITY or value == INFINITY_LITERAL) and any(
            leaf is end for end in self.ends
        ):
            return INFINITY, True
        neutral_type = leaf.type
        if isinstance(neutral_type, Timestamp) and isinstance(value, dt.datetime):
            managed = coerce_neutral_input(value, neutral_type)
            if matches_neutral_type(managed, neutral_type):
                return managed, True
        try:
            decoded = decode_wire(
                neutral_type, cast("WireValue", normalize_case_literal(neutral_type, value))
            )
        except WireDecodingError as error:
            raise instructions.InstructionRejectedError(
                f"neutral-literal-{error.reason}", f"{path}: {error}"
            ) from error
        return freeze_retained_value(decoded), True


def normalize_case_query(query: ObjectQueryNode, model: AcceptedMetamodel) -> ObjectQueryNode:
    """Normalize case-format carriers without performing query validation.

    Synthetic conformance queries may carry managed Python values, such as
    ``datetime`` temporal bounds, where canonical Wire has a string. This ingress
    encodes only those, by declared type; authored JSON values pass through
    unchanged. Core preflight still owns model-aware validation, classification,
    and lowering of the returned canonical query.
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
        return replace(selection, coordinate=normalize_case_bound(selection.coordinate))
    if isinstance(selection, AsOfRange):
        return replace(
            selection,
            start=normalize_case_bound(selection.start),
            end=normalize_case_bound(selection.end),
        )
    return selection


def _normalize_instruction(
    instruction: WriteInstruction, model: AcceptedMetamodel
) -> WriteInstruction:
    target_name = (
        instruction.target.entity if isinstance(instruction, PredicateWrite) else instruction.entity
    )
    entity = entity_by_name(model, target_name)
    if entity is None:
        return instruction
    if isinstance(instruction, TargetWrite):
        members = _entity_members(model, entity)
        return replace(
            instruction,
            row={
                name: _normalize_member(members[name], value) if name in members else value
                for name, value in instruction.row.items()
            },
        )
    if isinstance(instruction, KeyedWrite):
        members = _entity_members(model, entity)
        rows = tuple(
            {
                name: _normalize_member(members[name], value) if name in members else value
                for name, value in row.items()
            }
            for row in instruction.rows
        )
        return KeyedWrite(
            instruction.mutation,
            instruction.entity,
            rows,
            instruction.valid_from,
            instruction.until,
        )

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
    predicate_node = instruction.target.predicate
    assert isinstance(predicate_node, predicate.PredicateNode)  # a case states canonical input
    selection = PredicateSelection(
        instruction.target.entity,
        _normalize_predicate(predicate_node, model),
    )
    return PredicateWrite(
        instruction.mutation,
        selection,
        assignments,
        instruction.valid_from,
        instruction.until,
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
        return normalize_case_literal(member.type, value)
    return _normalize_occurrence(member, value)


def _normalize_occurrence(occurrence: OccurrenceMetadata, value: object) -> object:
    if occurrence.multiplicity is Multiplicity.MANY:
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            return value
        return [_normalize_document(occurrence, item) for item in cast("Sequence[object]", value)]
    return _normalize_document(occurrence, value)


def _normalize_document(container: OccurrenceMetadata, value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    attributes = {member.identity.name: member for member in container.attributes}
    occurrences = {member.identity.path[-1]: member for member in container.value_objects}
    return {
        name: (
            normalize_case_literal(attribute.type, nested)
            if nested is not None and (attribute := attributes.get(name)) is not None
            else _normalize_occurrence(occurrence, nested)
            if nested is not None and (occurrence := occurrences.get(name)) is not None
            else nested
        )
        for name, nested in cast("Mapping[str, object]", value).items()
    }


def _normalize_predicate(
    node: predicate.PredicateNode,
    model: AcceptedMetamodel,
    element_container: OccurrenceMetadata | None = None,
) -> predicate.PredicateNode:
    match node:
        case (
            predicate.Comparison(attr=reference)
            | predicate.Between(attr=reference)
            | predicate.Membership(attr=reference)
        ):
            return _normalize_literals(node, _attribute_type(model, reference))
        case (
            predicate.NestedComparison(path=reference)
            | predicate.NestedRange(path=reference)
            | predicate.NestedMembership(path=reference)
        ):
            return _normalize_literals(
                node, _nested_attribute_type(model, element_container, reference)
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


type _LiteralNode = (
    predicate.Comparison
    | predicate.Between
    | predicate.Membership
    | predicate.NestedComparison
    | predicate.NestedRange
    | predicate.NestedMembership
)


def _normalize_literals(node: _LiteralNode, neutral_type: NeutralType | None) -> _LiteralNode:
    if neutral_type is None:
        return node
    match node:
        case predicate.Comparison(value=value) | predicate.NestedComparison(value=value):
            return replace(node, value=normalize_case_literal(neutral_type, value))
        case (
            predicate.Between(lower=lower, upper=upper)
            | predicate.NestedRange(lower=lower, upper=upper)
        ):
            return replace(
                node,
                lower=normalize_case_literal(neutral_type, lower),
                upper=normalize_case_literal(neutral_type, upper),
            )
        case predicate.Membership(values=values) | predicate.NestedMembership(values=values):
            return replace(
                node,
                values=tuple(normalize_case_literal(neutral_type, value) for value in values),
            )


def _attribute_type(model: AcceptedMetamodel, reference: str) -> NeutralType | None:
    entity_name, path = split_reference(reference)
    if entity_name is None or len(path) != 1:
        return None
    entity = entity_by_name(model, entity_name)
    if entity is None:
        return None
    member = _entity_members(model, entity).get(path[0])
    return member.type if isinstance(member, AttributeMetadata) else None


def _nested_attribute_type(
    model: AcceptedMetamodel,
    element_container: OccurrenceMetadata | None,
    reference: str,
) -> NeutralType | None:
    leaf = (
        _relative_leaf(element_container, reference.split("."))
        if element_container is not None
        else _predicate_nested_leaf(model, reference)
    )
    return None if leaf is None else leaf.type


def _predicate_nested_leaf(
    model: AcceptedMetamodel, reference: str
) -> ValueObjectAttributeMetadata | None:
    entity_name, path = split_reference(reference)
    if entity_name is None or len(path) < 2:
        return None
    container = _top_level_occurrence(model, entity_name, path[0])
    return None if container is None else _relative_leaf(container, path[1:])


def _predicate_container(model: AcceptedMetamodel, reference: str) -> OccurrenceMetadata | None:
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
    container: OccurrenceMetadata | None, path: Sequence[str]
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
