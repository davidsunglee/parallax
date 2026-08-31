"""Model-aware Object Query validation (m-object-query).

A schema-valid Object Query can still be **structurally invalid** against a
specific metamodel: a ``narrowTo`` that broadens past the queried position, a
Sort Key over an attribute the narrowed result does not carry, an Include Path
guarded by a selection outside the queried position or hopping through a value
object, or a Temporal Selection naming a dimension the target does not declare.
``m-case-format``'s ``rejected`` case shape requires these refusals to happen
**before any SQL is emitted**.

This module owns exactly the clause rules; the predicate's own rules stay in
``m-predicate``, which this walk enters once, with the position the query's own
narrowing resolved. That split is what keeps one rule in one place: the
narrowing rule is ``m-inheritance``'s, stated once in the Predicate validator
and applied here to the three clause positions that carry the same shared
Subtype Selection.

Rule provenance beyond ``m-predicate``'s own list:

- ``narrow-outside-position`` / ``narrow-empty-effective-set`` — result narrowing
  and an Include Path's source guard resolve inside the QUERIED position, which
  is the query's own ``target``. An Include Path is measured against the queried
  position rather than the narrowed result: narrowing decides which objects come
  back, not which sources a path may start from.
- ``narrow-outside-relationship-target`` — an Include Segment's ``narrowTo``
  resolves inside that hop's relationship target's effective concrete set.
- ``deep-fetch-value-object-segment`` — ``m-value-object`` contract 4: a value
  object carries no correlation columns and is never an Include Segment.
- ``subtype-attribute-outside-narrow-scope`` / ``attribute-outside-active-position``
  — a Sort Key addresses the RESULT position, which ``narrowTo`` moves.
- ``temporal-read-dimension-selection-cardinality`` — ``m-temporal-read``: a
  canonical query names exactly one selection for every family-effective declared
  dimension and none for an undeclared dimension. Transaction-Time omission is
  normalized by an authoring surface before this model-aware boundary; Valid Time
  has no omission default.
"""

from __future__ import annotations

import datetime as dt
from typing import cast

from parallax.core import inheritance
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    RelationshipIdentity,
    entity_by_name,
)
from parallax.core.metamodel import (
    TemporalDimension as AxisKind,
)
from parallax.core.object_query._nodes import (
    AsOfRange,
    History,
    IncludePath,
    ObjectQueryNode,
    TemporalDimension,
)
from parallax.core.object_query._validated import (
    ValidatedAsOfSelection,
    ValidatedHistorySelection,
    ValidatedIncludePath,
    ValidatedIncludeSegment,
    ValidatedLatestSelection,
    ValidatedObjectQuery,
    ValidatedOrderTerm,
    ValidatedRangeSelection,
    ValidatedTemporalSelection,
)
from parallax.core.predicate import (
    ModelRejectedError,
    PositionScope,
    check_attribute_reference,
    effective_set,
    referenced_entities,
    relationship_target,
    resolve_subtype_selection,
    root_position,
    validate_narrow,
    validate_predicate,
)
from parallax.core.wire import WireDecodingError, decode_wire

__all__ = ["query_entities", "validate_object_query"]


def validate_object_query(
    root: EntityMetadata, query: ObjectQueryNode, model: Metamodel
) -> ValidatedObjectQuery:
    """Validate ``query`` against ``model``, raising :class:`ModelRejectedError`.

    ``root`` is the queried position, already resolved to accepted Metadata by
    the caller from the query's own ``target``. The clause rules run in the order
    the canonical document fixes: temporal completeness, then result narrowing —
    whose resolved position the predicate and the Sort Keys are both measured
    against — then Includes, measured against the unnarrowed queried position.
    """
    temporal = _validate_temporal_selections(root, query, model)
    queried = root_position(model, root)
    result = _narrowed_position(query, queried, model)
    predicate = validate_predicate(root, query.predicate, model, position=result)
    order_terms: list[ValidatedOrderTerm] = []
    for key in query.order_by:
        member = check_attribute_reference(key.attr, model, result)
        if member is None:
            raise ValueError(f"{key.attr!r} names no declared ordering attribute")
        order_terms.append(ValidatedOrderTerm(member, key.direction or "asc", key.nulls or "last"))
    includes = tuple(_validate_include_path(path, model, queried) for path in query.includes)
    narrowed = (
        None
        if query.narrow_to is None
        else tuple(
            entity for entity in model.entities if entity.identity.canonical in result.effective
        )
    )
    return ValidatedObjectQuery(
        authored=query,
        root=root,
        predicate=predicate,
        temporal=temporal,
        order_by=tuple(order_terms),
        includes=includes,
        narrow_to=narrowed,
        limit=query.limit,
    )


def query_entities(query: ObjectQueryNode) -> frozenset[str]:
    """Every Entity spelling ``query`` names anywhere, exactly as authored.

    A caller assembling a coherent model to validate ``query`` against needs each
    of them, not only the queried target: an Include Path or a navigation names a
    target the root's family does not otherwise reach.
    """
    names = {query.target.canonical, *referenced_entities(query.predicate)}
    names.update(query.narrow_to or ())
    for key in query.order_by:
        entity, _, _member = key.attr.rpartition(".")
        names.add(entity)
    for path in query.includes:
        names.update(path.applies_to or ())
        for segment in path.segments:
            entity, _, _member = segment.rel.rpartition(".")
            names.add(entity)
            names.update(segment.narrow_to)
    return frozenset(names)


def _narrowed_position(
    query: ObjectQueryNode, queried: PositionScope, model: Metamodel
) -> PositionScope:
    if query.narrow_to is None:
        return queried
    return validate_narrow(query.narrow_to, queried, model)


def _validate_include_path(
    path: IncludePath, model: Metamodel, queried: PositionScope
) -> ValidatedIncludePath:
    source_scope = (
        queried if path.applies_to is None else validate_narrow(path.applies_to, queried, model)
    )
    source = _scope_identities(model, source_scope)
    segments: list[ValidatedIncludeSegment] = []
    for segment in path.segments:
        target = relationship_target(
            segment.rel, model, wrong_kind_rule="deep-fetch-value-object-segment"
        )
        class_name, dot, member_name = segment.rel.rpartition(".")
        declaring = entity_by_name(model, class_name) if dot else None
        if declaring is None:
            raise ValueError(f"{segment.rel!r} names no resolved relationship direction")
        direction = RelationshipIdentity(declaring.identity, member_name)
        target_scope = PositionScope(effective=effective_set(model, target))
        if segment.narrow_to:
            resolved = resolve_subtype_selection(segment.narrow_to, model)
            if not resolved:
                raise ModelRejectedError(
                    "narrow-empty-effective-set",
                    f"include segment narrowTo {list(segment.narrow_to)} resolves to the empty "
                    "concrete-subtype set",
                )
            if not resolved <= target_scope.effective:
                raise ModelRejectedError(
                    "narrow-outside-relationship-target",
                    f"include segment narrowTo {list(segment.narrow_to)} resolves to "
                    f"{sorted(resolved)}, which is not a subset of "
                    f"{target.identity.name}'s effective concrete set "
                    f"{sorted(target_scope.effective)}",
                )
            target_scope = PositionScope(effective=resolved)
        segments.append(
            ValidatedIncludeSegment(
                direction,
                target,
                _scope_identities(model, target_scope),
                bool(segment.narrow_to),
            )
        )
    return ValidatedIncludePath(source, tuple(segments))


def _scope_identities(model: Metamodel, scope: PositionScope) -> tuple[EntityIdentity, ...]:
    return tuple(
        entity.identity for entity in model.entities if entity.identity.canonical in scope.effective
    )


def _validate_temporal_selections(
    root: EntityMetadata, query: ObjectQueryNode, model: Metamodel
) -> tuple[ValidatedTemporalSelection, ...]:
    family = inheritance.view(model).entity(root.identity)
    declarer = None if family is None else model.entity(family.root)
    if declarer is None:
        return ()
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
        raise ModelRejectedError(
            "temporal-read-dimension-selection-cardinality",
            f"{root.identity.canonical}: temporal read selections are invalid ({details}); "
            "a canonical Object Query names exactly one selection per declared dimension",
        )
    products: list[ValidatedTemporalSelection] = []
    for dimension, axis in sorted(declared.items(), key=lambda item: item[1].dimension.value):
        selection = query.temporal[dimension]
        start = declarer.attribute(axis.start_attribute.name)
        if start is None:
            raise ValueError(f"{axis.start_attribute} names no declared temporal Attribute")
        try:
            if isinstance(selection, History):
                product = ValidatedHistorySelection(axis)
            elif isinstance(selection, AsOfRange):
                managed_start = cast("dt.datetime", decode_wire(start.type, selection.start))
                managed_end = cast("dt.datetime", decode_wire(start.type, selection.end))
                if managed_start >= managed_end:
                    raise ModelRejectedError(
                        "query-clause-invalid",
                        f"{root.identity.canonical}.{dimension}: asOfRange scans [start, end), "
                        "so start < end",
                    )
                product = ValidatedRangeSelection(
                    axis,
                    managed_start,
                    managed_end,
                )
            elif selection.coordinate == "latest":
                product = ValidatedLatestSelection(axis)
            else:
                product = ValidatedAsOfSelection(
                    axis, decode_wire(start.type, selection.coordinate)
                )
        except WireDecodingError as error:
            raise ModelRejectedError(
                f"neutral-literal-{error.reason}",
                f"{root.identity.canonical}.{dimension}: {error}",
            ) from error
        products.append(product)
    return tuple(products)
