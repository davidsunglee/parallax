"""Test convenience for compiling predicate trees as flat Entity Queries."""

from __future__ import annotations

from typing import Literal

from parallax.core.dialect import Dialect, LockMode
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.object_query import EntityQuery, OrderKey
from parallax.core.predicate import PredicateNode
from parallax.core.sql_gen import CompiledRead
from parallax.core.sql_gen import compile_read as compile_entity_query


def compile_read(
    operation: PredicateNode,
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
    """Compile ``operation`` as the predicate of ``target``'s Entity Query."""
    query = EntityQuery(
        target=target.identity,
        predicate=operation,
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
