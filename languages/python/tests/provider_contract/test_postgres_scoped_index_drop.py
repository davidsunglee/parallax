"""A generated index removal reaches its own table's schema whatever the search_path."""

from __future__ import annotations

from contextlib import closing
from typing import Any, Final

from parallax.core.internal.entity import model_of
from parallax.descriptor import domain_model_from_yaml
from parallax.evolution import UnilateralEvolution, evolve, schema_delta
from tests._support.bindings import TEST_BINDING, TEST_SCHEMA

_SHELF: Final = """
entity:
  name: Shelf
  namespace: scoped
  table: sid_shelf
  attributes:
    - {{ name: id, type: int64, primaryKey: true }}
    - {{ name: label, type: string, maxLength: 32 }}
{indices}
"""
_INDEXED: Final = domain_model_from_yaml(
    _SHELF.format(indices="  indices:\n    - { name: shelf_label, attributes: [label] }")
)
_UNINDEXED: Final = domain_model_from_yaml(_SHELF.format(indices=""))
_HELD: Final = (
    "select schemaname, indexname from pg_indexes "
    "where tablename = 'sid_shelf' and left(indexname, 4) = 'pxi_' order by schemaname"
)


def test_an_index_drop_reaches_the_bound_schema_past_a_same_named_decoy(profile_run: Any) -> None:
    profile_run.reset(model_of(_INDEXED), {}, TEST_BINDING)
    evolution = evolve(
        _INDEXED, _UNINDEXED, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING
    )
    assert isinstance(evolution, UnilateralEvolution)
    (drop,) = schema_delta(evolution).statements
    with closing(profile_run.control()) as control:
        ((schema, name),) = control.execute(_HELD, [])
        assert schema == TEST_SCHEMA
        assert drop == f"drop index {TEST_SCHEMA}.{name}"
        # A decoy schema first on the search_path holds a same-named table and
        # index, so an unqualified drop would remove the decoy's instead.
        control.execute_write("create table public.sid_shelf (id bigint, label text)", [])
        control.execute_write(f"create index {name} on public.sid_shelf (label)", [])
        control.execute_write("set search_path to public", [])
        control.execute_write(drop, [])
        assert control.execute(_HELD, []) == [("public", name)]
