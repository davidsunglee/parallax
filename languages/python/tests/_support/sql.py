"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from parallax.core import deep_fetch
from parallax.core.dialect import Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.object_query import (
    OrderKey,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.object_query._nodes import TemporalDimension
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.predicate import PredicateNode, validate_predicate
from parallax.core.sql_gen._compile import CompiledPredicate, CompiledRead
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.sql_gen._compile import (
    compile_write_predicate as compile_validated_write_predicate,
)
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle._read_plan import UNCACHED_READ_PLANNER


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
    compiled, _rows = UNCACHED_READ_PLANNER.plan(
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
    return compiled


def compile_projected_read(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
    *,
    include_value_objects: Literal[True] | frozenset[str],
) -> CompiledRead:
    """Compile a row-form read of ``target`` widened to ``include_value_objects``,
    a projection no read plan requests: every declared member, as a materializing
    predicate write's resolving read takes it, or a named subset."""
    projection = deep_fetch.ReadProjectionRequest(
        "all" if include_value_objects is True else include_value_objects,
        include_value_objects is True,
    )
    return compile_entity_query(
        deep_fetch.plan(_validated(predicate, model, target), model, projection=projection).root,
        model,
        dialect,
        result_form="row",
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
) -> ValidatedObjectQuery:
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


def compile_write_predicate(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
) -> CompiledPredicate:
    """Elaborate an authored test predicate before private write lowering."""
    return compile_validated_write_predicate(
        validate_predicate(target, predicate, model), model, dialect, target
    )
