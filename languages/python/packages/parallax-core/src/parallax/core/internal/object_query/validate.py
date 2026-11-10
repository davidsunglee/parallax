from __future__ import annotations

import datetime as dt
from typing import Final, Literal, cast

from parallax.core.internal import inheritance
from parallax.core.internal.base import ManagedValue, NeutralType, UsageError
from parallax.core.internal.metamodel import (
    AsOfAxisMetadata,
    CompiledEntity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    entity_by_name,
)
from parallax.core.internal.metamodel import (
    TemporalDimension as AxisKind,
)
from parallax.core.internal.object_query._nodes import (
    AsOfRange,
    History,
    IncludePathNode,
    InterpretedQuery,
    QueryClauses,
    QueryInput,
    TemporalDimension,
)
from parallax.core.internal.object_query._resolved import (
    ResolvedAsOfSelection,
    ResolvedHistorySelection,
    ResolvedIncludePath,
    ResolvedIncludeSegment,
    ResolvedLatestSelection,
    ResolvedObjectQuery,
    ResolvedOrderTerm,
    ResolvedRangeSelection,
    ResolvedTemporalSelection,
)
from parallax.core.internal.predicate import (
    NARROW_EMPTY_EFFECTIVE_SET,
    NARROW_OUTSIDE_RELATIONSHIP_TARGET,
    QUERY_CLAUSE_INVALID,
    PositionScope,
    canonical_interpretation,
    check_attribute_reference,
    effective_set,
    relationship_direction,
    relationship_target,
    require_single_scalar,
    resolve_subtype_selection,
    root_position,
    validate_narrow,
)
from parallax.core.internal.relationship import is_back_reference
from parallax.core.internal.wire import WireValue, decode_wire, located_refusal

__all__ = [
    "DEEP_FETCH_PAST_BACK_REFERENCE",
    "DEEP_FETCH_VALUE_OBJECT_SEGMENT",
    "TEMPORAL_READ_DIMENSION_SELECTION_CARDINALITY",
    "ObjectQueryRejectionCode",
    "validate_include_path",
    "validate_object_query",
]

type ObjectQueryRejectionCode = Literal[
    "deep-fetch-past-back-reference",
    "deep-fetch-value-object-segment",
    "temporal-read-dimension-selection-cardinality",
]
"""The model-aware rules an Object Query's own clauses break, beside the
predicate rules its predicate, narrowing and Sort Keys are held to.
``temporal-read-dimension-selection-cardinality`` is this binding's own; the
others are core ``rejectedRule`` spellings."""

DEEP_FETCH_PAST_BACK_REFERENCE: Final = "deep-fetch-past-back-reference"
DEEP_FETCH_VALUE_OBJECT_SEGMENT: Final = "deep-fetch-value-object-segment"
TEMPORAL_READ_DIMENSION_SELECTION_CARDINALITY: Final = (
    "temporal-read-dimension-selection-cardinality"
)


def validate_object_query(
    root: CompiledEntity, query: QueryInput, model: Metamodel
) -> ResolvedObjectQuery:
    """Validate ``query`` against ``model``, raising a model-aware refusal.

    ``root`` is the queried position, already resolved to accepted Metadata by
    the caller from the query's own ``target``. The clause rules run in the order
    the canonical document fixes: temporal completeness, then result narrowing —
    whose resolved position the predicate and the Sort Keys are both measured
    against — then Includes, measured against the unnarrowed queried position.
    A canonical query's predicate is validated where an interpreted query's
    predicate adapter is invoked, once, at that same position; its Include adapter
    is invoked once, at the Includes step.
    """
    clauses: QueryClauses
    if isinstance(query, InterpretedQuery):
        clauses, interpret = query.clauses, query.predicate
    else:
        clauses, interpret = query, canonical_interpretation(query.predicate, model)
    temporal = _validate_temporal_selections(root, clauses, model)
    queried = root_position(model, root)
    result = _narrowed_position(clauses, queried, model)
    predicate = interpret(root, result)
    order_terms: list[ResolvedOrderTerm] = []
    for key in clauses.order_by:
        member = check_attribute_reference(key.attr, model, result)
        if member is None:
            raise ValueError(f"{key.attr!r} names no declared ordering attribute")
        require_single_scalar(key.attr, member)
        order_terms.append(ResolvedOrderTerm(member, key.direction or "asc", key.nulls or "last"))
    paths = query.includes() if isinstance(query, InterpretedQuery) else query.includes
    includes = tuple(validate_include_path(path, model, queried) for path in paths)
    narrowed = (
        None
        if clauses.narrow_to is None
        else tuple(
            entity for entity in model.entities if entity.identity.canonical in result.effective
        )
    )
    return ResolvedObjectQuery(
        root=root,
        predicate=predicate,
        temporal=temporal,
        order_by=tuple(order_terms),
        includes=includes,
        narrow_to=narrowed,
        limit=clauses.limit,
    )


def _narrowed_position(
    query: QueryClauses, queried: PositionScope, model: Metamodel
) -> PositionScope:
    if query.narrow_to is None:
        return queried
    return validate_narrow(query.narrow_to, queried, model)


def validate_include_path(
    path: IncludePathNode, model: Metamodel, queried: PositionScope
) -> ResolvedIncludePath:
    """Resolve ``path`` relative to the model's active queried position.

    The source guard is constrained by ``queried`` and each segment is resolved
    from the preceding relationship target. Narrowing, wrong-kind, and
    past-back-reference violations raise a
    :class:`~parallax.core.internal.base.UsageError` with their shared rule code. A relationship
    direction that is unresolved, undeclared, or disconnected from the preceding
    target raises ``ValueError`` because accepted metadata supplies no direction
    to return from that position.
    """
    source_scope = (
        queried if path.applies_to is None else validate_narrow(path.applies_to, queried, model)
    )
    source = _scope_identities(model, source_scope)
    segments: list[ResolvedIncludeSegment] = []
    active_scope = source_scope
    arrival = None
    at_back_reference = False
    for segment in path.segments:
        target = relationship_target(
            segment.rel, model, wrong_kind_rule=DEEP_FETCH_VALUE_OBJECT_SEGMENT
        )
        class_name, dot, member_name = segment.rel.rpartition(".")
        declaring = entity_by_name(model, class_name) if dot else None
        if declaring is None:
            raise ValueError(f"{segment.rel!r} names no resolved relationship direction")
        if not active_scope.effective <= effective_set(model, declaring):
            raise ValueError(
                f"{segment.rel!r} does not resolve from the active Include Path position "
                f"{sorted(active_scope.effective)}"
            )
        if at_back_reference:
            raise UsageError(
                DEEP_FETCH_PAST_BACK_REFERENCE,
                f"{segment.rel!r} continues past a back-reference level, which ends its path",
            )
        direction = RelationshipIdentity(declaring.identity, member_name)
        metadata = relationship_direction(model, direction)
        at_back_reference = metadata is not None and is_back_reference(metadata, arrival)
        arrival = metadata
        target_scope = PositionScope(effective=effective_set(model, target))
        if segment.narrow_to:
            resolved = resolve_subtype_selection(segment.narrow_to, model)
            if not resolved:
                raise UsageError(
                    NARROW_EMPTY_EFFECTIVE_SET,
                    f"include segment narrowTo {list(segment.narrow_to)} resolves to the empty "
                    "concrete-subtype set",
                )
            if not resolved <= target_scope.effective:
                raise UsageError(
                    NARROW_OUTSIDE_RELATIONSHIP_TARGET,
                    f"include segment narrowTo {list(segment.narrow_to)} resolves to "
                    f"{sorted(resolved)}, which is not a subset of "
                    f"{target.identity.name}'s effective concrete set "
                    f"{sorted(target_scope.effective)}",
                )
            target_scope = PositionScope(effective=resolved)
        segments.append(
            ResolvedIncludeSegment(
                direction,
                target,
                _scope_identities(model, target_scope),
                bool(segment.narrow_to),
            )
        )
        active_scope = target_scope
    return ResolvedIncludePath(source, tuple(segments))


def _scope_identities(model: Metamodel, scope: PositionScope) -> tuple[EntityIdentity, ...]:
    return tuple(
        entity.identity for entity in model.entities if entity.identity.canonical in scope.effective
    )


def _validate_temporal_selections(
    root: CompiledEntity, query: QueryClauses, model: Metamodel
) -> tuple[ResolvedTemporalSelection, ...]:
    # `m-object-query` cannot reach the Temporal Facet, so the family's axes are
    # read from its root's accepted declaration.
    declarer = inheritance.root_metadata(
        inheritance.inheritance_facet_of(model), model, root.identity
    )
    declared: dict[TemporalDimension, AsOfAxisMetadata] = {
        "valid-time" if axis.dimension is AxisKind.VALID_TIME else "transaction-time": axis
        for axis in declarer.declared_as_of_axes
    }
    selected = set(query.temporal)
    missing = sorted(set(declared) - selected)
    undeclared = sorted(selected - set(declared))
    if missing or undeclared:
        details = "; ".join(
            detail
            for detail in (
                f"missing {missing}" if missing else "",
                f"undeclared {undeclared}" if undeclared else "",
            )
            if detail
        )
        raise UsageError(
            TEMPORAL_READ_DIMENSION_SELECTION_CARDINALITY,
            f"{root.identity.canonical}: temporal read selections are invalid ({details}); "
            "a canonical Object Query names exactly one selection per declared dimension",
        )
    products: list[ResolvedTemporalSelection] = []
    for dimension, axis in sorted(declared.items(), key=lambda item: item[1].dimension.value):
        selection = query.temporal[dimension]
        start = declarer.attribute(axis.start_attribute.name)
        if start is None:
            raise ValueError(f"{axis.start_attribute} names no declared temporal Attribute")
        where = f"{root.identity.canonical}.{dimension}"
        if isinstance(selection, History):
            product = ResolvedHistorySelection(axis)
        elif isinstance(selection, AsOfRange):
            managed_start = cast("dt.datetime", _decoded(start.type, selection.start, where))
            managed_end = cast("dt.datetime", _decoded(start.type, selection.end, where))
            if managed_start >= managed_end:
                raise UsageError(
                    QUERY_CLAUSE_INVALID, f"{where}: asOfRange scans [start, end), so start < end"
                )
            product = ResolvedRangeSelection(axis, managed_start, managed_end)
        elif selection.coordinate == "latest":
            product = ResolvedLatestSelection(axis)
        else:
            product = ResolvedAsOfSelection(axis, _decoded(start.type, selection.coordinate, where))
        products.append(product)
    return tuple(products)


def _decoded(neutral_type: NeutralType, value: WireValue, where: str) -> ManagedValue:
    try:
        return decode_wire(neutral_type, value)
    except UsageError as error:
        raise located_refusal(error, where) from error
