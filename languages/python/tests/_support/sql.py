"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from typing import Literal

from parallax.core.deep_fetch import ValidatedEntityQuery
from parallax.core.dialect import Dialect, LockMode
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.object_query import OrderKey
from parallax.core.predicate import (
    PredicateNode,
    elaborate_predicate,
    root_position,
    validate_narrow,
)
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
    result_form: Literal["row", "instance"] = "row",
    lock: LockMode | None = None,
    include_value_objects: bool | frozenset[str] = False,
) -> CompiledRead:
    """Compile ``predicate`` as the predicate of ``target``'s Entity Query."""
    position = root_position(model, target)
    if narrow_to is not None:
        position = validate_narrow(
            tuple(identity.canonical for identity in narrow_to), position, model
        )
    query = ValidatedEntityQuery(
        target=target.identity,
        entity=target,
        validated_predicate=elaborate_predicate(
            target, predicate, model, position=position
        ),
        narrow_to=narrow_to,
        order_by=order_by,
        limit=limit,
    )
    return compile_entity_query(
        query,
        model,
        dialect,
        result_form=result_form,
        lock=lock,
        include_value_objects=include_value_objects,
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
