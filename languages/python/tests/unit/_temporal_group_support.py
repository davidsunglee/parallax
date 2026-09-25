"""Materialized Write Groups authored from the rows their resolving read matched.

Exported without a leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    ChunkedColumnBuilder,
    MaterializedWriteGroup,
    PredecessorColumns,
    PredecessorShape,
    PredicateWrite,
    TemporalColumns,
    whole,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write

__all__ = ["temporal_group"]


def temporal_group(
    mutation: PredicateWrite,
    model: Metamodel,
    predecessors: Sequence[Mapping[str, object]],
    *,
    key_name: str = "id",
) -> MaterializedWriteGroup:
    """The Materialized Write Group ``mutation`` settles to once its resolving
    read matched ``predecessors``: each row keyed by its ``key_name`` member and
    retained whole as its Predecessor Row."""
    prepared = prepare_typed_write(mutation, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    names = tuple(predecessors[0])
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    members = {name: ChunkedColumnBuilder[object]() for name in names}
    for row in predecessors:
        keys.append(row[key_name])
        for name in names:
            members[name].append(row[name])
    return MaterializedWriteGroup(
        mutation=prepared,
        key_attributes=(key_name,),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(
            predecessors=PredecessorColumns(
                shape=PredecessorShape(attributes=names),
                attribute_columns=tuple(whole(members[name].build()) for name in names),
            )
        ),
    )
