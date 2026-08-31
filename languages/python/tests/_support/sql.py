"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from parallax.core import deep_fetch
from parallax.core.dialect import Dialect, LockMode
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.object_query import (
    OrderKey,
    TemporalDimension,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.predicate import PredicateNode, elaborate_predicate
from parallax.core.sql_gen._compile import CompiledPredicate, CompiledRead
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.sql_gen._compile import (
    compile_write_predicate as compile_validated_write_predicate,
)


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
    lock: LockMode | None = None,
    include_value_objects: bool | frozenset[str] = False,
) -> CompiledRead:
    """Compile ``predicate`` as the predicate of ``target``'s Entity Query."""
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
    validated = validate_object_query(target, query, model)
    requested: Literal["none", "all"] | frozenset[str]
    if result_form == "instance" or include_value_objects is True:
        requested = "all"
    elif isinstance(include_value_objects, frozenset):
        requested = include_value_objects
    else:
        requested = "none"
    projection = deep_fetch.ReadProjectionRequest(
        requested,
        result_form == "instance" or include_value_objects is True or bool(include_value_objects),
    )
    return compile_entity_query(
        deep_fetch.plan(validated, model, projection=projection).root,
        model,
        dialect,
        result_form=result_form,
        lock=lock,
    )


def compile_write_predicate(
    predicate: PredicateNode,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
) -> CompiledPredicate:
    """Elaborate an authored test predicate before private write lowering."""
    return compile_validated_write_predicate(
        elaborate_predicate(target, predicate, model), model, dialect, target
    )
