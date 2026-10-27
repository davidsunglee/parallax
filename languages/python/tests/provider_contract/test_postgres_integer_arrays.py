"""Integer arrays bound as binary ``int8[]`` against Int32 and Int64 columns.

An authored membership and a child level's gathered keys each bind one integer
list. The adapter binds every such list as a binary ``int8[]`` whatever its
magnitudes, on every way a connection comes into existence, and the statement's
array cast compares it in the column's own type. The keys sit at and near both
ends of each column's range, so a narrowing or a sign error would lose rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Final, cast

import pytest
from psycopg.adapt import PyFormat, Transformer
from psycopg.pq import Format

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._postgres_control import PostgresControl
from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Int32, Rel, attr, rel
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.sql_gen import LoweredStatement
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.postgres._connection import adapt_binds
from parallax.snapshot import connect
from tests._support.root_ownership import own_root

_NAMESPACE = "integer.arrays"


class WideHolder(Entity, table="ia_wide_holder", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    items: Rel[tuple[WideItem, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "holder_id"))


class WideItem(Entity, table="ia_wide_item", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    holder_id: Attr[int]


class NarrowHolder(Entity, table="ia_narrow_holder", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True, type=Int32)
    items: Rel[tuple[NarrowItem, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "holder_id"))


class NarrowItem(Entity, table="ia_narrow_item", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True, type=Int32)
    holder_id: Attr[int] = attr(type=Int32)


_MODEL = DomainModel(WideHolder, WideItem, NarrowHolder, NarrowItem)

_INT64_KEYS: Final = (-(2**63), -(2**63) + 1, -(2**31) - 1, -7, 0, 5, 2**31, 2**63 - 2, 2**63 - 1)
_INT32_KEYS: Final = (-(2**31), -(2**31) + 1, -7, 0, 5, 2**31 - 2, 2**31 - 1)

_CASES: Final = [
    pytest.param(WideHolder, WideItem, _INT64_KEYS, "bigint", id="int64"),
    pytest.param(NarrowHolder, NarrowItem, _INT32_KEYS, "int", id="int32"),
]


@pytest.fixture(scope="module")
def control(profile_run: Any) -> Iterator[PostgresControl]:
    control = cast("PostgresControl", profile_run.control())
    try:
        yield control
    finally:
        control.close()


def _delivered(
    profile_run: Any, holder: type[Any], item: type[Any], keys: tuple[int, ...]
) -> list[LoweredStatement]:
    """Every read statement a membership read with its children, and its
    negation, deliver over ``keys``, after their rows are checked."""
    profile_run.reset(model_of(_MODEL), {})
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()

    def seed(tx: Any) -> None:
        for ordinal, key in enumerate(keys):
            tx.insert(holder(id=key))
            tx.insert(item(id=ordinal, holder_id=key))

    db.transact(seed)
    mark = len(observation.calls)
    chosen = [*keys[:2], *keys[-2:], keys[len(keys) // 2]]
    found = db.find(holder.where(holder.id.in_(chosen)).include(holder.items)).results()
    assert sorted((each.id, [child.holder_id for child in each.items]) for each in found) == sorted(
        (key, [key]) for key in chosen
    )
    rest = db.find(holder.where(holder.id.not_in(chosen))).results()
    assert sorted(each.id for each in rest) == sorted(set(keys) - set(chosen))
    return [call.statement for call in observation.calls[mark:] if call.kind == "read"]


def _integer_arrays(statements: list[LoweredStatement], element: str) -> list[list[int]]:
    """Each statement's one array bind, checked against the cast it compares under."""
    arrays: list[list[int]] = []
    for statement in statements:
        assert f"= any(cast(? as {element}[]))" in statement.sql
        (array,) = (
            cast("list[object]", bind) for bind in statement.binds if isinstance(bind, list)
        )
        assert {type(value) for value in array} == {int}
        arrays.append(cast("list[int]", array))
    return arrays


@pytest.mark.parametrize(("holder", "item", "keys", "element"), _CASES)
def test_authored_and_gathered_integer_arrays_select_their_rows_at_the_column_bounds(
    profile_run: Any, holder: type[Any], item: type[Any], keys: tuple[int, ...], element: str
) -> None:
    statements = _delivered(profile_run, holder, item, keys)

    root, level, negated = statements
    assert "t0.id = any(" in root.sql
    assert "t0.holder_id = any(" in level.sql
    assert negated.sql.count("not t0.id = any(") == 1
    assert len(_integer_arrays(statements, element)) == 3


@pytest.mark.parametrize(("holder", "item", "keys", "element"), _CASES)
def test_every_connection_path_binds_an_integer_array_as_binary_int8(
    profile_run: Any,
    control: PostgresControl,
    holder: type[Any],
    item: type[Any],
    keys: tuple[int, ...],
    element: str,
) -> None:
    statements = _delivered(profile_run, holder, item, keys)
    arrays = _integer_arrays(statements, element)

    for array in arrays:
        transformer = Transformer(control.native)
        transformer.dump_sequence(adapt_binds([array]), [PyFormat.AUTO])
        assert (transformer.types, transformer.formats) == ((1016,), [Format.BINARY])

    runtimes = [
        profile_run.configured(pool=pool).open()
        for pool in (PoolOptions(min_size=1, max_size=1), OnDemandOptions(max_size=1))
    ]
    try:
        for runtime in runtimes:
            with runtime.login_execution().new_context() as connection:
                for statement, array in zip(statements, arrays, strict=True):
                    assert connection.execute("select pg_typeof(%s)::text", [array]) == [
                        ("bigint[]",)
                    ]
                    rows = connection.execute(
                        POSTGRES.to_driver_sql(statement.sql), list(statement.binds)
                    )
                    assert rows
        assert control.execute("select pg_typeof(%s)::text", [arrays[0]]) == [("bigint[]",)]
    finally:
        for runtime in runtimes:
            runtime.close()
