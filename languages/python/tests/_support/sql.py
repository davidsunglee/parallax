"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from parallax.core import deep_fetch, inheritance
from parallax.core.dialect import Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.inheritance import InheritancePositionView
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.navigate import (
    NoRootSelections,
    TemporallyResolvedPredicate,
    resolve_temporal_visibility,
)
from parallax.core.object_query import (
    OrderKey,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._nodes import TemporalDimension
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.predicate import PredicateNode, validate_predicate
from parallax.core.predicate._resolved import ResolvedPredicate
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, EmptyRead
from parallax.core.sql_gen._compile import CompiledPredicate, CompiledRead
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.sql_gen._compile import (
    compile_write_predicate as compile_validated_write_predicate,
)
from parallax.core.unit_work import Concurrency


def compile_read(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
    *,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
    order_by: tuple[OrderKey, ...] = (),
    limit: int | None = None,
    temporal: Mapping[TemporalDimension, TemporalSelection] | None = None,
    result_form: Literal["row", "instance"] = "row",
    preference: Concurrency | None = None,
) -> CompiledRead:
    """Compile ``predicate`` as the predicate of ``target``'s Entity Query,
    planned as production plans every read."""
    root = UNCACHED_READ_PLANNER.plan(
        edition="test",
        model=CatalogedModel(model),
        dialect=dialect,
        query=_validated(
            predicate,
            model,
            target,
            narrow_to=narrow_to,
            order_by=order_by,
            limit=limit,
            temporal=temporal,
        ),
        result_form=result_form,
        preference=preference,
    ).root_read()
    assert not isinstance(root, EmptyRead)
    return root[0]


def compile_projected_read(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
    *,
    value_objects: Literal["none", "all"] | frozenset[str],
    observe_structured_document: bool,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
    result_form: Literal["row", "instance"] = "row",
    temporal: Mapping[TemporalDimension, TemporalSelection] | None = None,
) -> CompiledRead:
    """Compile ``target``'s read under an explicit internal projection request,
    planned as deep fetch plans the root and published in ``result_form``,
    neither of which widens the other: every declared member, as a predecessor
    read takes it, a named subset, or none."""
    projection = deep_fetch.ReadProjectionRequest(value_objects, observe_structured_document)
    return compile_entity_query(
        deep_fetch.plan_root(
            _validated(predicate, model, target, narrow_to=narrow_to, temporal=temporal),
            model,
            projection=projection,
        ),
        model,
        dialect,
        result_form=result_form,
    )


def _validated(
    predicate: PredicateNode,
    model: Metamodel,
    target: EntityMetadata,
    *,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
    order_by: tuple[OrderKey, ...] = (),
    limit: int | None = None,
    temporal: Mapping[TemporalDimension, TemporalSelection] | None = None,
) -> ResolvedObjectQuery:
    query = object_query(
        target.identity,
        predicate,
        narrow_to=(
            None if narrow_to is None else tuple(identity.canonical for identity in narrow_to)
        ),
        temporal=temporal,
        order_by=order_by,
        limit=limit,
    )
    return validate_object_query(target, query, model)


def read_position(
    model: Metamodel,
    target: EntityMetadata,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
) -> InheritancePositionView:
    """The inheritance owner's position for a hand-built read of ``target``:
    its own view, or the one ``narrow_to`` resolves to."""
    facet = inheritance.view(model)
    position = facet.entity(target.identity) if narrow_to is None else facet.position(narrow_to)
    assert position is not None
    return position


def compile_write_predicate(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
) -> CompiledPredicate:
    """Elaborate an authored test predicate and resolve its temporal visibility
    as readless write lowering does before compiling it."""
    return compile_validated_write_predicate(
        resolved_as_stated(validate_predicate(target, predicate, model), model, target),
        model,
        dialect,
        target,
    )


def resolved_as_stated(
    predicate: ResolvedPredicate, model: Metamodel, target: EntityMetadata
) -> TemporallyResolvedPredicate:
    """``predicate`` temporally resolved with its own root conditions kept, as
    specialized reads and readless writes resolve theirs."""
    return resolve_temporal_visibility(
        predicate, target=target, model=model, resolution=NoRootSelections()
    )
