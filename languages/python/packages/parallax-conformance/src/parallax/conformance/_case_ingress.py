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
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Leaf,
    Multiplicity,
    OccurrenceMetadata,
    RelationshipDeclaration,
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


@dataclass(frozen=True, slots=True)
class _Field:
    """A scalar member a path reaches; its element type, for a collection."""

    neutral_type: NeutralType


@dataclass(frozen=True, slots=True)
class _Container:
    """A Value Object occurrence a path reaches, or the element it binds."""

    occurrence: OccurrenceMetadata


@dataclass(frozen=True, slots=True)
class _Related:
    """An Entity position: the queried one, or one a relationship reaches."""

    entity: EntityMetadata | None


type _Reached = _Field | _Container | _Related


def _normalize_predicate(
    node: predicate.PredicateNode, model: AcceptedMetamodel, scope: _Reached | None = None
) -> predicate.PredicateNode:
    """``node`` with each typed literal in its case-ingress canonical spelling,
    typed by the member its scope and path reach; a literal whose member does
    not resolve is left for validation to judge."""
    at: _Reached = _Related(None) if scope is None else scope
    match node:
        case predicate.Comparison() | predicate.Range() | predicate.Membership():
            return _normalize_literals(node, _subject_type(model, at, node.subject))
        case predicate.And(operands=operands) | predicate.Or(operands=operands):
            return replace(
                node, operands=tuple(_normalize_predicate(child, model, at) for child in operands)
            )
        case predicate.Not(operand=operand) | predicate.Group(operand=operand):
            return replace(node, operand=_normalize_predicate(operand, model, at))
        case predicate.Narrow(operand=operand, path=path):
            inner = at if path is None else _reach(model, at, path)
            return (
                node
                if inner is None
                else replace(node, operand=_normalize_predicate(operand, model, inner))
            )
        case predicate.Quantifier(path=path, where=where) if where is not None:
            inner = _reach(model, at, path)
            return (
                node
                if inner is None
                else replace(node, where=_normalize_predicate(where, model, inner))
            )
        case _:
            return node


type _LiteralNode = predicate.Comparison | predicate.Range | predicate.Membership


def _normalize_literals(node: _LiteralNode, neutral_type: NeutralType | None) -> _LiteralNode:
    if neutral_type is None:
        return node
    match node:
        case predicate.Comparison(value=value):
            return replace(node, value=normalize_case_literal(neutral_type, value))
        case predicate.Range(lower=lower, upper=upper):
            return replace(
                node,
                lower=normalize_case_literal(neutral_type, lower),
                upper=normalize_case_literal(neutral_type, upper),
            )
        case predicate.Membership(values=values):
            return replace(
                node,
                values=tuple(normalize_case_literal(neutral_type, value) for value in values),
            )


def _subject_type(
    model: AcceptedMetamodel, scope: _Reached, subject: predicate.ScalarSubject
) -> NeutralType | None:
    reached = (
        scope
        if isinstance(subject, predicate.CurrentScalarElement)
        else _reach(model, scope, subject.path)
    )
    return reached.neutral_type if isinstance(reached, _Field) else None


def _reach(model: AcceptedMetamodel, scope: _Reached, path: str) -> _Reached | None:
    """What ``path`` reaches from ``scope``, or ``None`` where it does not resolve."""
    entity_name, names = split_reference(path)
    current: _Reached | None = (
        scope if entity_name is None else _Related(entity_by_name(model, entity_name))
    )
    for name in names:
        current = None if current is None else _member(model, current, name)
    return current


def _member(model: AcceptedMetamodel, owner: _Reached, name: str) -> _Reached | None:
    match owner:
        case _Field():
            return None
        case _Container(occurrence=container):
            leaf = container.attribute(name)
            if leaf is not None:
                return _Field(leaf.type)
            nested = container.value_object(name)
            return None if nested is None else _Container(nested)
        case _Related(entity=entity):
            if entity is None:
                return None
            member = _family_members(model, entity).get(name)
            if isinstance(member, AttributeMetadata):
                return _Field(member.type)
            if member is not None:
                return _Container(member)
            for candidate in _family(model, entity):
                declaration = candidate.relationship(name)
                if declaration is not None:
                    return _Related(model.entity(_relationship_target(model, declaration)))
            return None


def _family(model: AcceptedMetamodel, entity: EntityMetadata) -> list[EntityMetadata]:
    families = inheritance.view(model)
    view = families.entity(entity.identity)
    root = entity.identity if view is None else view.root
    return [
        candidate
        for candidate in model.entities
        if (candidate_view := families.entity(candidate.identity)) is not None
        and candidate_view.root == root
    ]


def _family_members(
    model: AcceptedMetamodel, entity: EntityMetadata
) -> dict[str, AttributeMetadata | ValueObjectMetadata]:
    members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
    for candidate in _family(model, entity):
        members.update(_entity_members(model, candidate))
    return members


def _relationship_target(
    model: AcceptedMetamodel, declaration: RelationshipDeclaration
) -> EntityIdentity:
    del model
    if isinstance(declaration, DefiningRelationshipDeclaration):
        return declaration.join.target.entity
    return declaration.reverse_of.source_entity
