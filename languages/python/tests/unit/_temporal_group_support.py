"""Materialized Write Groups authored from the rows their resolving read matched.

Exported without a leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core import inheritance
from parallax.core.entity._construction_input import ABSENT
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    MaterializedWriteGroup,
    PredecessorRowsBuilder,
    PredicateWrite,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite, prepare_typed_write
from tests.unit._positional_row_support import positional_row

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
    retained whole, positional over its target's members, as its Predecessor
    Row."""
    prepared = prepare_typed_write(mutation, model)
    assert isinstance(prepared, PreparedPredicateWrite)
    view = inheritance.view(model).entity(prepared.selection.target.identity)
    assert view is not None
    selection = view.member_selection
    key = selection.shape.position(key_name)
    assert key is not None
    evidence = PredecessorRowsBuilder(selection, key_position=key, absent=ABSENT, documents=False)
    for row in predecessors:
        evidence.append(positional_row(selection.shape, row, absent=ABSENT))
    sealed = evidence.seal()
    assert sealed is not None
    return MaterializedWriteGroup(mutation=prepared, evidence=sealed)
