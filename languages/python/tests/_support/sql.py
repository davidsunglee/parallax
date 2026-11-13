"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from parallax.core.internal import concurrency, inheritance, read_planning
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.database_binding import ResolvedBinding
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.inheritance import InheritancePositionView
from parallax.core.internal.metamodel import CompiledEntity, EntityIdentity, Metamodel
from parallax.core.internal.navigate import (
    NoRootSelections,
    TemporallyResolvedPredicate,
    resolve_temporal_visibility,
)
from parallax.core.internal.object_query import (
    OrderKey,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.internal.object_query._nodes import TemporalDimension
from parallax.core.internal.object_query._resolved import ResolvedObjectQuery
from parallax.core.internal.predicate import PredicateNode, validate_predicate
from parallax.core.internal.predicate._resolved import ResolvedPredicate
from parallax.core.internal.sql_gen._compile import (
    CompiledPredicate,
    CompiledRead,
    CompiledTemplate,
)
from parallax.core.internal.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.internal.sql_gen._compile import compile_template as compile_entity_template
from parallax.core.internal.sql_gen._compile import (
    compile_write_predicate as compile_validated_write_predicate,
)
from tests._support.bindings import bound_model


def as_resolved(model: Metamodel | ResolvedBinding) -> ResolvedBinding:
    """``model`` itself if already resolved, else resolved under the test binding."""
    return model if isinstance(model, ResolvedBinding) else bound_model(model)


def compile_nonempty_read(
    query: read_planning.PlannedEntityQuery,
    model: Metamodel | ResolvedBinding,
    dialect: Dialect,
    *,
    result_form: Literal["row", "instance"] = "row",
    shared_lock: bool = False,
) -> CompiledRead:
    compiled = compile_entity_query(
        query, as_resolved(model), dialect, result_form=result_form, shared_lock=shared_lock
    )
    assert isinstance(compiled, CompiledRead)
    return compiled


def compile_nonempty_template(
    query: read_planning.PlannedEntityQuery,
    model: Metamodel | ResolvedBinding,
    dialect: Dialect,
    *,
    result_form: Literal["row", "instance"] = "row",
    shared_lock: bool = False,
) -> CompiledTemplate:
    compiled = compile_entity_template(
        query, as_resolved(model), dialect, result_form=result_form, shared_lock=shared_lock
    )
    assert isinstance(compiled, CompiledTemplate)
    return compiled


def compile_read(
    predicate: PredicateNode,
    bound: Metamodel | ResolvedBinding,
    dialect: Dialect,
    target: CompiledEntity,
    *,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
    order_by: tuple[OrderKey, ...] = (),
    limit: int | None = None,
    temporal: Mapping[TemporalDimension, TemporalSelection] | None = None,
    result_form: Literal["row", "instance"] = "row",
    preference: ConcurrencyPreference | None = None,
) -> CompiledRead:
    """Compile one root statement without applying delivery orchestration."""
    resolved = as_resolved(bound)
    model = resolved.meta
    query = _validated(
        predicate,
        model,
        target,
        narrow_to=narrow_to,
        order_by=order_by,
        limit=limit,
        temporal=temporal,
    )
    return compile_nonempty_read(
        read_planning.plan_root(
            query,
            model,
            projection=read_planning.ReadProjectionRequest("all", True)
            if result_form == "instance"
            else read_planning.ReadProjectionRequest("none", False),
        ),
        resolved,
        dialect,
        result_form=result_form,
        shared_lock=preference is not None
        and concurrency.concurrency_facet_of(model).effective_strategy(target.identity, preference)
        == "locking",
    )


def compile_projected_read(
    predicate: PredicateNode,
    bound: Metamodel | ResolvedBinding,
    dialect: Dialect,
    target: CompiledEntity,
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
    projection = read_planning.ReadProjectionRequest(value_objects, observe_structured_document)
    resolved = as_resolved(bound)
    model = resolved.meta
    return compile_nonempty_read(
        read_planning.plan_root(
            _validated(predicate, model, target, narrow_to=narrow_to, temporal=temporal),
            model,
            projection=projection,
        ),
        resolved,
        dialect,
        result_form=result_form,
    )


def _validated(
    predicate: PredicateNode,
    model: Metamodel,
    target: CompiledEntity,
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
    target: CompiledEntity,
    narrow_to: tuple[EntityIdentity, ...] | None = None,
) -> InheritancePositionView:
    """The inheritance owner's position for a hand-built read of ``target``:
    its own view, or the one ``narrow_to`` resolves to."""
    facet = inheritance.inheritance_facet_of(model)
    position = facet.entity(target.identity) if narrow_to is None else facet.position(narrow_to)
    assert position is not None
    return position


def compile_write_predicate(
    predicate: PredicateNode,
    bound: Metamodel | ResolvedBinding,
    dialect: Dialect,
    target: CompiledEntity,
) -> CompiledPredicate:
    """Elaborate an authored test predicate and resolve its temporal visibility
    as readless write lowering does before compiling it."""
    resolved = as_resolved(bound)
    model = resolved.meta
    return compile_validated_write_predicate(
        resolved_as_stated(validate_predicate(target, predicate, model), model, target),
        resolved,
        dialect,
        target,
    )


def resolved_as_stated(
    predicate: ResolvedPredicate, model: Metamodel, target: CompiledEntity
) -> TemporallyResolvedPredicate:
    """``predicate`` temporally resolved with its own root conditions kept, as
    specialized reads and readless writes resolve theirs."""
    return resolve_temporal_visibility(
        predicate, target=target, model=model, resolution=NoRootSelections()
    )
