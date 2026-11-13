"""A same-named decoy table first on the PostgreSQL search_path never supplies
modeled data, receives modeled writes, or captures a generated index removal:
every modeled table is named in the schema its binding places it in."""

from __future__ import annotations

from contextlib import closing
from typing import Any, Final

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity import model_of
from parallax.descriptor import domain_model_from_yaml
from parallax.evolution import UnilateralEvolution, evolve, schema_delta
from parallax.snapshot import connect
from tests._support.bindings import TEST_BINDING, TEST_SCHEMA
from tests._support.root_ownership import own_root

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


class Crate(Entity, table="spd_crate", namespace="search.path"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_CRATES: Final = DomainModel(Crate)
_DECOY: Final = "public"


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


def _decoyed(profile_run: Any) -> Any:
    """Provision the crates in the bound schema, a same-named decoy table the
    case login may read and write first on the search_path, and the
    configuration whose every connection prefers the decoy."""
    profile_run.reset(model_of(_CRATES), {}, TEST_BINDING)
    role = POSTGRES.quote(profile_run.default_role.name)
    with closing(profile_run.control()) as control:
        control.execute_write(
            f"create table {_DECOY}.spd_crate (id bigint primary key, label text)", []
        )
        control.execute_write(f"insert into {_DECOY}.spd_crate values (1, 'decoy')", [])
        control.execute_write(f"grant usage on schema {_DECOY} to {role}", [])
        control.execute_write(
            f"grant select, insert, update, delete on {_DECOY}.spd_crate to {role}", []
        )
        control.execute_write(f"insert into {TEST_SCHEMA}.spd_crate values (1, 'modeled')", [])
    configuration = profile_run.configured(settings={"search_path": _DECOY})
    runtime = configuration.open()
    try:
        with runtime.login_source().new_context("writer_only") as connection:
            # The decoy is what an unqualified name finds on these connections.
            assert connection.execute("select label from spd_crate", []) == [("decoy",)]
    finally:
        runtime.close()
    return configuration


def _labels(profile_run: Any, schema: str) -> list[tuple[object, ...]]:
    with closing(profile_run.control()) as control:
        return [
            tuple(row)
            for row in control.execute(f"select id, label from {schema}.spd_crate order by id", [])
        ]


def test_a_decoy_first_on_the_search_path_never_supplies_modeled_rows(profile_run: Any) -> None:
    db = own_root(
        connect(_decoyed(profile_run), _CRATES, binding=TEST_BINDING)
    ).using_database_login()
    assert db.find(Crate.where(Crate.id == 1)).result().label == "modeled"
    (node,) = db.wire.find({"target": "search.path.Crate", "predicate": {"true": {}}}).results()
    assert node["label"] == "modeled"


def test_a_decoy_first_on_the_search_path_never_receives_modeled_writes(profile_run: Any) -> None:
    db = own_root(
        connect(_decoyed(profile_run), _CRATES, binding=TEST_BINDING)
    ).using_database_login()
    db.transact(lambda tx: tx.insert(Crate(id=2, label="typed")))
    db.transact(lambda tx: tx.wire.insert("search.path.Crate", {"id": 3, "label": "wire"}))
    db.transact(
        lambda tx: tx.amend(tx.find(Crate.where(Crate.id == 1)).result(), Crate.label.set("kept"))
    )
    db.transact(
        lambda tx: tx.wire.delete_where(
            {
                "entity": "search.path.Crate",
                "predicate": {"eq": {"path": "search.path.Crate.id", "value": 3}},
            }
        )
    )
    assert _labels(profile_run, TEST_SCHEMA) == [(1, "kept"), (2, "typed")]
    assert _labels(profile_run, _DECOY) == [(1, "decoy")]
