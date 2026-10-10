"""Scalar collections on inherited owners under both strategies and layouts.

A collection the root, an abstract subtype, or a concrete subtype declares is
stored for exactly the concretes it applies to: under table-per-hierarchy one
shared table carries every applicable collection, and under
table-per-concrete-subtype each concrete table carries its own. Abstract reads
publish each row's own concrete with every collection it holds, and writes
through any concrete assign them whole. Expected stored arrays are spelled
independently here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

import pytest

from parallax.core import (
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.metamodel import TablePerConcreteSubtype
from parallax.core.object_query import deserialize
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

type Strategy = Literal["tph", "tpcs"]
type Layout = Literal["columns", "document"]


class Badge(ValueObject):
    codes: Attr[tuple[int, ...]] = attr(type=Int32)


def _family(strategy: Strategy, layout: Layout) -> tuple[Any, ...]:
    namespace = f"scalar.collection.{strategy}.{layout}"
    hierarchy = strategy == "tph"
    options: dict[str, Any] = {"layout": Document()} if layout == "document" else {}
    table = f"sci_{strategy}_{layout}"
    root: Any = type(
        "Asset",
        (Entity,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int], "tags": Attr[tuple[str, ...]]},
            "id": attr(primary_key=True),
            "tags": attr(),
        },
        namespace=namespace,
        inheritance=AbstractRoot(
            TablePerHierarchy("kind") if hierarchy else TablePerConcreteSubtype()
        ),
        **({"table": table} if hierarchy else {}),
        **options,
    )
    device: Any = type(
        "Device",
        (root,),
        {
            "__module__": __name__,
            "__annotations__": {"ports": Attr[tuple[int, ...]]},
            "ports": attr(type=Int32),
        },
        namespace=namespace,
        inheritance=AbstractSubtype,
    )
    phone: Any = type(
        "Phone",
        (device,),
        {
            "__module__": __name__,
            "__annotations__": {
                "numbers": Attr[tuple[str, ...]],
                "keys": Attr[tuple[bytes, ...]],
                "badge": Attr[Badge | None],
            },
            "numbers": attr(),
            "keys": attr(),
            "badge": attr(),
        },
        namespace=namespace,
        inheritance=ConcreteSubtype(tag_value="phone") if hierarchy else ConcreteSubtype(),
        **({} if hierarchy else {"table": f"{table}_phone"}),
    )
    tablet: Any = type(
        "Tablet",
        (device,),
        {"__module__": __name__, "__annotations__": {"label": Attr[str]}},
        namespace=namespace,
        inheritance=ConcreteSubtype(tag_value="tablet") if hierarchy else ConcreteSubtype(),
        **({} if hierarchy else {"table": f"{table}_tablet"}),
    )
    desk: Any = type(
        "Desk",
        (root,),
        {
            "__module__": __name__,
            "__annotations__": {"legs": Attr[tuple[str, ...]]},
            "legs": attr(),
        },
        namespace=namespace,
        inheritance=ConcreteSubtype(tag_value="desk") if hierarchy else ConcreteSubtype(),
        **({} if hierarchy else {"table": f"{table}_desk"}),
    )
    return root, device, phone, tablet, desk


_FAMILIES = {
    (strategy, layout): _family(strategy, layout)
    for strategy in ("tph", "tpcs")
    for layout in ("columns", "document")
}
_MODEL = DomainModel(*(cls for family in _FAMILIES.values() for cls in family))
_AXES = pytest.mark.parametrize(
    ("strategy", "layout"),
    list(_FAMILIES),
    ids=[f"{strategy}-{layout}" for strategy, layout in _FAMILIES],
)


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _seed(db: ScopedDatabase, strategy: Strategy, layout: Layout) -> None:
    _root, _device, phone, tablet, desk = _FAMILIES[(strategy, layout)]
    db.transact(
        lambda tx: [
            tx.insert(
                phone(
                    id=1,
                    tags=("a", "a"),
                    ports=(1, 2),
                    numbers=("555",),
                    keys=(b"\x01\xff",),
                    badge=Badge(codes=(7, 7)),
                )
            ),
            tx.insert(tablet(id=2, tags=(), ports=(3,), label="t")),
            tx.insert(desk(id=3, tags=("d",), legs=("l", "r"))),
        ]
    )


def _shape(row: Any) -> tuple[object, ...]:
    return (
        type(row).__name__,
        row.tags,
        getattr(row, "ports", None),
        getattr(row, "numbers", None),
        getattr(row, "badge", None),
        getattr(row, "legs", None),
    )


@_AXES
def test_abstract_and_concrete_reads_publish_each_applicable_collection(
    profile_run: Any, strategy: Strategy, layout: Layout
) -> None:
    db = _served(profile_run)
    _seed(db, strategy, layout)
    root, device, phone, _tablet, desk = _FAMILIES[(strategy, layout)]

    rows = db.find(root.where(root.id >= 1).order_by(root.id.asc())).results()
    assert [_shape(row) for row in rows] == [
        ("Phone", ("a", "a"), (1, 2), ("555",), Badge(codes=(7, 7)), None),
        ("Tablet", (), (3,), None, None, None),
        ("Desk", ("d",), None, None, None, ("l", "r")),
    ]
    devices = db.find(device.where(device.id >= 1).order_by(device.id.asc())).results()
    assert [_shape(row) for row in devices] == [_shape(row) for row in rows[:2]]
    assert _shape(db.find(phone.where(phone.id == 1)).result()) == _shape(rows[0])
    assert _shape(db.find(desk.where(desk.id == 3)).result()) == _shape(rows[2])
    assert rows[0].keys == (b"\x01\xff",)

    namespace = f"scalar.collection.{strategy}.{layout}"
    wire = db.wire.find(
        {
            "target": f"{namespace}.Asset",
            "predicate": {"true": {}},
            "orderBy": [{"attr": f"{namespace}.Asset.id", "direction": "asc"}],
        }
    ).results()
    assert [
        {key: node[key] for key in ("tags", "ports", "numbers", "badge", "legs") if key in node}
        for node in wire
    ] == [
        {"tags": ["a", "a"], "ports": [1, 2], "numbers": ["555"], "badge": {"codes": [7, 7]}},
        {"tags": [], "ports": [3]},
        {"tags": ["d"], "legs": ["l", "r"]},
    ]


@_AXES
def test_a_stream_of_an_abstract_target_publishes_the_same_collections(
    profile_run: Any, strategy: Strategy, layout: Layout
) -> None:
    db = _served(profile_run)
    _seed(db, strategy, layout)
    root = _FAMILIES[(strategy, layout)][0]
    query = root.where(root.id >= 1).order_by(root.id.asc())

    with db.stream(query, batch_size=2) as streamed:
        streamed_rows = [_shape(row) for row in streamed]

    assert streamed_rows == [_shape(row) for row in db.find(query).results()]


@_AXES
def test_writes_through_each_concrete_assign_inherited_and_own_collections(
    profile_run: Any, strategy: Strategy, layout: Layout
) -> None:
    db = _served(profile_run)
    _seed(db, strategy, layout)
    root, _device, phone, tablet, desk = _FAMILIES[(strategy, layout)]

    def fn(tx: Transaction) -> None:
        phone_row = tx.find(phone.where(phone.id == 1)).result()
        tx.amend(phone_row.edit(tags=("b",), ports=(), numbers=("1", "1")))
        tx.amend(
            tx.find(desk.where(desk.id == 3)).result(), desk.legs.set(()), desk.tags.set(("e", "d"))
        )
        tx.replace_if(tablet(id=2, label="u"), unversioned=True)

    db.transact(fn)
    rows = db.find(root.where(root.id >= 1).order_by(root.id.asc())).results()
    assert [_shape(row) for row in rows] == [
        ("Phone", ("b",), (), ("1", "1"), Badge(codes=(7, 7)), None),
        ("Tablet", (), (), None, None, None),
        ("Desk", ("e", "d"), None, None, None, ()),
    ]


@_AXES
def test_a_row_form_read_of_an_abstract_target_carries_each_collection(
    profile_run: Any, strategy: Strategy, layout: Layout
) -> None:
    db = _served(profile_run)
    _seed(db, strategy, layout)
    namespace = f"scalar.collection.{strategy}.{layout}"
    query = deserialize(
        {
            "target": f"{namespace}.Asset",
            "predicate": {"true": {}},
            "orderBy": [{"attr": f"{namespace}.Asset.id", "direction": "asc"}],
        }
    )

    rows = cast("Sequence[Mapping[str, object]]", db.read_rows(query).rows)

    assert [
        tuple(row[name] for name in ("familyVariant", "tags", "ports", "numbers", "keys", "legs"))
        for row in rows
    ] == [
        ("Phone", ("a", "a"), (1, 2), ("555",), (b"\x01\xff",), None),
        ("Tablet", (), (3,), None, None, None),
        ("Desk", ("d",), None, None, None, ("l", "r")),
    ]
