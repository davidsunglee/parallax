"""A delivered child level's key array, as the server plans it.

The level binds its gathered keys as one array carrier of the key's declared
type, and its statement casts that array to the key column's type. Each level is
planned by the server with the binds the read delivered, and again with the
cast removed, which shows that the bound array already arrives in the key's own
type rather than one its magnitudes would choose.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Int32, Rel, attr, rel
from parallax.core.base import INT32, INT64, NeutralType
from parallax.core.db_port import ArrayBind
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import connect
from tests._support.root_ownership import own_root

_NAMESPACE = "child.key.arrays"


class WideHolder(Entity, table="cka_wide_holder", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    items: Rel[tuple[WideItem, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "holder_id"))


class WideItem(Entity, table="cka_wide_item", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    holder_id: Attr[int]


class NarrowHolder(Entity, table="cka_narrow_holder", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True, type=Int32)
    items: Rel[tuple[NarrowItem, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "holder_id"))


class NarrowItem(Entity, table="cka_narrow_item", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True, type=Int32)
    holder_id: Attr[int] = attr(type=Int32)


_MODEL = DomainModel(WideHolder, WideItem, NarrowHolder, NarrowItem)


def _child_level(profile_run: Any, holder: type[Any]) -> LoweredStatement:
    """The one child statement a read of two holders with small keys delivers."""
    profile_run.reset(model_of(_MODEL), {})
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()
    item = WideItem if holder is WideHolder else NarrowItem

    def seed(tx: Any) -> None:
        for key in (1, 2):
            tx.insert(holder(id=key))
            tx.insert(item(id=key, holder_id=key))

    db.transact(seed)
    mark = len(observation.calls)
    holders = db.find(holder.where(holder.id.in_([1, 2])).include(holder.items)).results()
    assert sorted((found.id, len(found.items)) for found in holders) == [(1, 1), (2, 1)]
    _root, level = (call.statement for call in observation.calls[mark:] if call.kind == "read")
    return level


def _planned_array(profile_run: Any, sql: str, binds: tuple[object, ...]) -> str:
    rows = profile_run.port.execute(f"explain {POSTGRES.to_driver_sql(sql)}", list(binds))
    plan = " ".join(str(row[0]) for row in rows)
    start = plan.index("ANY (")
    return plan[start : plan.index(")", start) + 1]


@pytest.mark.parametrize(
    ("holder", "declared", "element", "planned"),
    [
        pytest.param(WideHolder, INT64, "bigint", "::bigint[])", id="int64"),
        pytest.param(NarrowHolder, INT32, "int", "::integer[])", id="int32"),
    ],
)
def test_a_child_level_compares_small_keys_as_an_array_of_the_key_type(
    profile_run: Any, holder: type[Any], declared: NeutralType, element: str, planned: str
) -> None:
    statement = _child_level(profile_run, holder)
    cast_array = f"cast(? as {element}[])"
    assert f"t0.holder_id = any({cast_array})" in statement.sql
    (keys,) = statement.binds
    assert isinstance(keys, ArrayBind)
    assert keys.element_type == declared
    assert sorted(cast("list[int]", keys.values)) == [1, 2]

    assert _planned_array(profile_run, statement.sql, statement.binds).endswith(planned)
    uncast = statement.sql.replace(cast_array, "?")
    assert _planned_array(profile_run, uncast, statement.binds).endswith(planned)
