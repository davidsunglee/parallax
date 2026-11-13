"""One class-backed model under one multi-location Database Binding, through the
public Typed and Wire verbs and the shipped PostgreSQL adapter.

Each story pairs with a family of corpus placement cases, which the descriptor
lane runs through Wire, and observes the same placement here through both
interfaces: what each verb answers, and what each bound table holds afterwards.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from contextlib import closing
from typing import Any, Final, Literal, cast

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    ONE_TO_MANY,
    ONE_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    attr,
    rel,
)
from parallax.core.internal.database_binding import PhysicalTable, ResolvedBinding
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import EntityIdentity, TablePerConcreteSubtype
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresTable
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root

_NS: Final = "placement.stories"
_DOCS: Final = "placement.stories.docs"


class Client(Entity, table="bps_client", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(optimistic_locking=True)
    orders: Rel[tuple[ClientOrder, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "client_id"))


class ClientOrder(Entity, table="bps_order", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    client_id: Attr[int]
    sku: Attr[str] = attr(max_length=16)
    client: Rel[Client | None] = rel(reverse_of="orders")


class SalesBook(Entity, table="bps_book", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    audit: Rel[AuditBook] = rel(cardinality=ONE_TO_ONE, join=("id", "id"))


class AuditBook(Entity, table="bps_book", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    note: Attr[str] = attr(max_length=16)


class Profile(Entity, table="bps_profile", namespace=_DOCS, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    display_name: Attr[str | None] = attr(max_length=32)
    score: Attr[int | None]


class Payment(
    Entity,
    table="bps_payment",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class Card(Payment, namespace=_NS, inheritance=ConcreteSubtype(tag_value="card")):
    network: Attr[str | None] = attr(max_length=16)


class Cash(Payment, namespace=_NS, inheritance=ConcreteSubtype(tag_value="cash")):
    tendered: Attr[int | None]


class Asset(Entity, namespace=_NS, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Truck(Asset, table="bps_asset", namespace=_NS, inheritance=ConcreteSubtype()):
    axles: Attr[int | None] = attr(type=Int32)


class Van(Asset, table="bps_asset", namespace=_NS, inheritance=ConcreteSubtype()):
    doors: Attr[int | None] = attr(type=Int32)


class Vault(TxTemporal, table="bps_vault", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Edge(Entity, table="bps_edge", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(
    Client, ClientOrder, SalesBook, AuditBook, Profile, Payment, Card, Cash, Asset, Truck, Van,
    Vault, Edge,
)  # fmt: skip
_EDGE_SCHEMA: Final = 'Px.Edge"q'
_BINDING: Final = PostgresBinding(
    default=PostgresLocation(schema="px"),
    namespaces={_DOCS: PostgresLocation(schema="px_docs")},
    entities={
        f"{_NS}.ClientOrder": PostgresTable(schema="px_crm"),
        f"{_NS}.AuditBook": PostgresTable(schema="px_audit"),
        f"{_NS}.Payment": PostgresTable(schema="px_billing"),
        f"{_NS}.Truck": PostgresTable(schema="px_eu"),
        f"{_NS}.Van": PostgresTable(schema="px_us"),
        f"{_NS}.Vault": PostgresTable(schema="px_hist", name="vault_live"),
        f"{_NS}.Edge": PostgresTable(schema=_EDGE_SCHEMA, name="order"),
    },
)

type _Representation = Literal["typed", "wire"]
_REPRESENTATIONS: Final = pytest.mark.parametrize("representation", ["typed", "wire"])
_JAN, _MAR, _MAY, _JUN = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 6))


def _connect(profile_run: Any, model: DomainModel = _MODEL, **options: Any) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, model, binding=_BINDING, **options)
    ).using_database_login()


def _provisioned(profile_run: Any, **options: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {}, _BINDING)
    return _connect(profile_run, **options)


def _rows(profile_run: Any, sql: str) -> list[tuple[object, ...]]:
    with closing(profile_run.control()) as control:
        return [tuple(row) for row in control.execute(sql, [])]


def _held(profile_run: Any, schema: str, table: str) -> bool:
    with closing(profile_run.control()) as control:
        ((held,),) = control.execute(
            "select count(*) from pg_tables where schemaname = ? and tablename = ?",
            [schema, table],
        )
    return held == 1


def _name(entity: type[Any]) -> str:
    return f"{_DOCS if entity is Profile else _NS}.{entity.__name__}"


def _members(nodes: Iterable[object], member: str) -> list[Any]:
    """Each Wire node's ``member``, sorted."""
    return sorted(cast("Mapping[str, Any]", node)[member] for node in nodes)


def _eq(entity: type[Any], member: str, value: object) -> dict[str, object]:
    return {"eq": {"path": f"{_name(entity)}.{member}", "value": value}}


# --------------------------------------------------------------------------- #
# Relationships across schemas: owner in `px`, target in `px_crm`.             #
# --------------------------------------------------------------------------- #
def _seed_clients(db: ScopedDatabase) -> None:
    def seed(tx: TxnContext) -> None:
        for key, name in ((1, "Ada"), (2, "Bob"), (3, "Cy")):
            tx.insert(Client(id=key, name=name))
        for key, client, sku in ((11, 1, "A-1"), (12, 1, "A-2"), (21, 2, "B-1")):
            tx.insert(ClientOrder(id=key, client_id=client, sku=sku))

    db.transact(seed)


def test_relationships_across_schemas_read_each_side_where_it_is_bound(profile_run: Any) -> None:
    db = _provisioned(profile_run)
    _seed_clients(db)
    assert _held(profile_run, "px_crm", "bps_order")
    assert not _held(profile_run, "px", "bps_order")

    with_orders = db.find(Client.where(Client.orders.any())).results()
    assert sorted(client.id for client in with_orders) == [1, 2]
    wire_with_orders = db.wire.find(
        {"target": _name(Client), "predicate": {"any": {"path": f"{_name(Client)}.orders"}}}
    ).results()
    assert _members(wire_with_orders, "id") == [1, 2]

    adas = db.find(
        ClientOrder.where(ClientOrder.client.exists() & (ClientOrder.client.name == "Ada"))
    ).results()
    assert sorted(order.id for order in adas) == [11, 12]
    wire_adas = db.wire.find(
        {
            "target": _name(ClientOrder),
            "predicate": {
                "and": {
                    "operands": [
                        {"exists": {"path": f"{_name(ClientOrder)}.client"}},
                        _eq(ClientOrder, "client.name", "Ada"),
                    ]
                }
            },
        }
    ).results()
    assert _members(wire_adas, "id") == [11, 12]


def test_a_streamed_include_across_schemas_joins_every_page(profile_run: Any) -> None:
    db = _provisioned(profile_run)
    _seed_clients(db)
    query = Client.where(Client.all).order_by(Client.id.asc()).include(Client.orders)
    with db.stream(query, batch_size=2) as stream:
        typed = {client.id: sorted(order.id for order in client.orders) for client in stream}
    with db.wire.stream(query, batch_size=2) as wire_stream:
        wire = {
            cast("Mapping[str, Any]", node)["id"]: _members(
                cast("Mapping[str, Any]", node)["orders"], "id"
            )
            for node in wire_stream
        }
    assert typed == wire == {1: [11, 12], 2: [21], 3: []}


# --------------------------------------------------------------------------- #
# Equal local names in two schemas never merge their owners.                   #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
def test_equal_local_names_keep_each_owners_rows_through_joins_and_writes(
    profile_run: Any, representation: _Representation
) -> None:
    db = _provisioned(profile_run)

    def seed(tx: TxnContext) -> None:
        for key in (1, 2):
            tx.insert(SalesBook(id=key, amount=key * 10))
        tx.insert(AuditBook(id=1, note="opened"))
        tx.insert(AuditBook(id=2, note="reviewed"))

    db.transact(seed)

    def revise(tx: TxnContext) -> None:
        if representation == "typed":
            sale = tx.find(SalesBook.where(SalesBook.id == 2)).result()
            tx.amend(sale, SalesBook.amount.set(25))
            tx.delete(tx.find(AuditBook.where(AuditBook.id == 1)).result())
        else:
            sale = tx.wire.find({"target": _name(SalesBook), "predicate": _eq(SalesBook, "id", 2)})
            tx.wire.amend(sale.result(), {"amount": 25})
            audit = tx.wire.find({"target": _name(AuditBook), "predicate": _eq(AuditBook, "id", 1)})
            tx.wire.delete(audit.result())

    db.transact(revise)
    assert _rows(profile_run, "select id, amount from px.bps_book order by id") == [
        (1, 10),
        (2, 25),
    ]
    assert _rows(profile_run, "select id, note from px_audit.bps_book") == [(2, "reviewed")]

    reviewed = db.find(
        SalesBook.where(SalesBook.audit.exists() & (SalesBook.audit.note == "reviewed")).include(
            SalesBook.audit
        )
    ).results()
    assert [(sale.id, sale.amount, sale.audit.note) for sale in reviewed] == [(2, 25, "reviewed")]
    (node,) = db.wire.find(
        {
            "target": _name(SalesBook),
            "predicate": {
                "and": {
                    "operands": [
                        {"exists": {"path": f"{_name(SalesBook)}.audit"}},
                        _eq(SalesBook, "audit.note", "reviewed"),
                    ]
                }
            },
            "includes": [{"segments": [{"rel": f"{_name(SalesBook)}.audit"}]}],
        }
    ).results()
    sale = cast("Mapping[str, Any]", node)
    assert (sale["id"], sale["amount"], sale["audit"]["note"]) == (2, 25, "reviewed")


# --------------------------------------------------------------------------- #
# A Document-layout Entity placed by its exact namespace default.              #
# --------------------------------------------------------------------------- #
def test_a_document_layout_in_a_namespace_schema_reads_and_writes_its_bound_table(
    profile_run: Any,
) -> None:
    db = _provisioned(profile_run)
    db.transact(lambda tx: tx.insert(Profile(id=1, display_name="Ada", score=7)))
    db.transact(
        lambda tx: tx.wire.insert(_name(Profile), {"id": 2, "displayName": "Bo", "score": 30})
    )
    db.transact(
        lambda tx: tx.amend(tx.find(Profile.where(Profile.id == 1)).result(), Profile.score.set(8))
    )
    db.transact(
        lambda tx: tx.wire.amend_where(
            {"entity": _name(Profile), "predicate": _eq(Profile, "id", 2)}, {"displayName": "Bea"}
        )
    )
    assert _rows(profile_run, "select id, payload from px_docs.bps_profile order by id") == [
        (1, {"displayName": "Ada", "score": 8}),
        (2, {"displayName": "Bea", "score": 30}),
    ]
    eager = db.find(Profile.where(Profile.score > 5).order_by(Profile.score.desc())).results()
    assert [profile.display_name for profile in eager] == ["Bea", "Ada"]
    with db.wire.stream(
        {
            "target": _name(Profile),
            "predicate": {"true": {}},
            "orderBy": [{"attr": f"{_name(Profile)}.id"}],
        },
        batch_size=1,
    ) as stream:
        assert [node["displayName"] for node in stream] == ["Ada", "Bea"]


# --------------------------------------------------------------------------- #
# Inheritance: a hierarchy placed by its root, concrete leaves by themselves.  #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
def test_a_hierarchy_table_and_concrete_leaf_tables_sit_where_their_owners_are_bound(
    profile_run: Any, representation: _Representation
) -> None:
    db = _provisioned(profile_run)

    def seed(tx: TxnContext) -> None:
        if representation == "typed":
            tx.insert(Card(id=1, amount=100, network="Visa"))
            tx.insert(Cash(id=2, amount=20, tendered=25))
            tx.insert(Truck(id=1, label="hauler", axles=3))
            tx.insert(Van(id=1, label="courier", doors=4))
        else:
            tx.wire.insert(_name(Card), {"id": 1, "amount": 100, "network": "Visa"})
            tx.wire.insert(_name(Cash), {"id": 2, "amount": 20, "tendered": 25})
            tx.wire.insert(_name(Truck), {"id": 1, "label": "hauler", "axles": 3})
            tx.wire.insert(_name(Van), {"id": 1, "label": "courier", "doors": 4})

    db.transact(seed)
    assert _rows(profile_run, "select id, kind from px_billing.bps_payment order by id") == [
        (1, "card"),
        (2, "cash"),
    ]
    assert _rows(profile_run, "select id, label from px_eu.bps_asset") == [(1, "hauler")]
    assert _rows(profile_run, "select id, label from px_us.bps_asset") == [(1, "courier")]

    cards = db.find(Card.where(Card.amount > 50)).results()
    assert [(card.id, card.network) for card in cards] == [(1, "Visa")]
    assets = db.find(Asset.where(Asset.all)).results()
    assert sorted((type(asset).__name__, asset.label) for asset in assets) == [
        ("Truck", "hauler"),
        ("Van", "courier"),
    ]
    wire_assets = db.wire.find({"target": _name(Asset), "predicate": {"true": {}}}).results()
    assert _members(wire_assets, "label") == ["courier", "hauler"]

    db.transact(lambda tx: tx.delete(tx.find(Van.where(Van.id == 1)).result()))
    assert _rows(profile_run, "select id from px_us.bps_asset") == []
    assert _rows(profile_run, "select id from px_eu.bps_asset") == [(1,)]


# --------------------------------------------------------------------------- #
# One unit of work spans two schemas and commits or rolls back whole.          #
# --------------------------------------------------------------------------- #
class _Abandoned(Exception):
    pass


def _across_schemas(representation: _Representation, *, abandon: bool):
    def work(tx: TxnContext) -> None:
        if representation == "typed":
            tx.insert(Client(id=9, name="Dee"))
            tx.amend_if(Client, Client.name.set("Ada L."), key=1, version=1)
            tx.insert(ClientOrder(id=91, client_id=9, sku="D-1"))
            tx.insert(ClientOrder(id=92, client_id=9, sku="D-2"))
            tx.amend_where(
                ClientOrder.where(ClientOrder.client.exists() & (ClientOrder.client.name == "Bob")),
                ClientOrder.sku.set("Z"),
            )
        else:
            tx.wire.insert(_name(Client), {"id": 9, "name": "Dee"})
            tx.wire.amend_if(_name(Client), {"id": 1, "name": "Ada L."}, version=1)
            tx.wire.insert(_name(ClientOrder), {"id": 91, "clientId": 9, "sku": "D-1"})
            tx.wire.insert(_name(ClientOrder), {"id": 92, "clientId": 9, "sku": "D-2"})
            tx.wire.amend_where(
                {
                    "entity": _name(ClientOrder),
                    "predicate": {
                        "and": {
                            "operands": [
                                {"exists": {"path": f"{_name(ClientOrder)}.client"}},
                                _eq(ClientOrder, "client.name", "Bob"),
                            ]
                        }
                    },
                },
                {"sku": "Z"},
            )
        if abandon:
            # Read back through the same transaction: every write has executed
            # in both schemas before the callback abandons the unit of work.
            assert tx.find(Client.where(Client.id == 9)).result().name == "Dee"
            moved = tx.find(ClientOrder.where(ClientOrder.sku == "Z")).results()
            assert [order.id for order in moved] == [21]
            raise _Abandoned

    return work


@_REPRESENTATIONS
def test_keyed_target_batched_and_predicate_writes_across_schemas_commit_or_roll_back_together(
    profile_run: Any, representation: _Representation
) -> None:
    db = _provisioned(profile_run)
    _seed_clients(db)
    before = (
        _rows(profile_run, "select id, name, version from px.bps_client order by id"),
        _rows(profile_run, "select id, sku from px_crm.bps_order order by id"),
    )
    with pytest.raises(_Abandoned):
        db.transact(_across_schemas(representation, abandon=True))
    assert (
        _rows(profile_run, "select id, name, version from px.bps_client order by id"),
        _rows(profile_run, "select id, sku from px_crm.bps_order order by id"),
    ) == before

    db.transact(_across_schemas(representation, abandon=False))
    assert _rows(profile_run, "select id, name, version from px.bps_client order by id") == [
        (1, "Ada L.", 2),
        (2, "Bob", 1),
        (3, "Cy", 1),
        (9, "Dee", 1),
    ]
    assert _rows(profile_run, "select id, sku from px_crm.bps_order order by id") == [
        (11, "A-1"),
        (12, "A-2"),
        (21, "Z"),
        (91, "D-1"),
        (92, "D-2"),
    ]


# --------------------------------------------------------------------------- #
# A temporal table outside the default schema, under a local-name override.    #
# --------------------------------------------------------------------------- #
_VAULT: Final = EntityIdentity(_NS, "Vault")
_MASKED_VAULT: Final[Any] = type(
    "Vault",
    (TxTemporal,),
    {
        "__module__": __name__,
        "__annotations__": {"id": Attr[int], "label": Attr[str]},
        "id": attr(primary_key=True),
        "label": attr(max_length=16),
    },
    table="bps_vault_archive",
    namespace=_NS,
)
_MASKED: Final = DomainModel(
    Client, ClientOrder, SalesBook, AuditBook, Profile, Payment, Card, Cash, Asset, Truck, Van,
    _MASKED_VAULT, Edge,
)  # fmt: skip
"""The model renaming Vault's declared table, which the binding's override masks."""


def _vault_rows(profile_run: Any) -> list[tuple[object, ...]]:
    return _rows(
        profile_run,
        "select in_z, case when out_z = 'infinity' then null else out_z end, label "
        "from px_hist.vault_live order by in_z",
    )


@_REPRESENTATIONS
@pytest.mark.parametrize("model", [_MODEL, _MASKED], ids=["declared", "masked-declared-rename"])
def test_a_temporal_conflict_in_another_schema_is_recognized_and_retried(
    profile_run: Any, representation: _Representation, model: DomainModel
) -> None:
    # The vault was known from January until its termination in May. A clock
    # at March reopens it inside that history, which the bound table's
    # exclusion refuses; the retry reopens it in June. Under the masked model
    # the declared name differs, yet the physical table and its derived names
    # do not, so the conflict is still recognized as the statement's own.
    profile_run.reset(model_of(_MODEL), {}, _BINDING)
    _connect(profile_run, clock=ScriptedClock([_JAN])).transact(
        lambda tx: tx.insert(Vault(id=1, label="seeded"))
    )
    _connect(profile_run, clock=ScriptedClock([_MAY])).transact(
        lambda tx: tx.terminate(tx.find(Vault.where(Vault.id == 1)).result())
    )
    attempts: list[None] = []

    def reopen(tx: TxnContext) -> None:
        attempts.append(None)
        if representation == "typed":
            vault = _MASKED_VAULT if model is _MASKED else Vault
            tx.insert(vault(id=1, label="again"))
        else:
            tx.wire.insert(_name(Vault), {"id": 1, "label": "again"})

    _connect(profile_run, model, clock=ScriptedClock([_MAR, _JUN])).transact(reopen)
    assert len(attempts) == 2
    assert _vault_rows(profile_run) == [(_JAN, _MAY, "seeded"), (_JUN, None, "again")]
    history = (
        _connect(profile_run, model).find(Vault.where(Vault.id == 1).as_of(tx_time=_MAR)).results()
    )
    assert [vault.label for vault in history] == ["seeded"]


def test_a_violation_in_another_schema_names_its_physical_table_and_resolved_constraint(
    profile_run: Any,
) -> None:
    db = _provisioned(profile_run, clock=ScriptedClock([_JAN, _JAN]))
    db.transact(lambda tx: tx.insert(Vault(id=1, label="seeded")))
    with pytest.raises(DatabaseError) as refused:
        db.transact(lambda tx: tx.wire.insert(_name(Vault), {"id": 1, "label": "again"}))
    constraints = ResolvedBinding(model_of(_MODEL), _BINDING).table(_VAULT).temporal_constraints
    assert constraints is not None
    assert refused.value.category == "uniqueViolation"
    assert refused.value.constraint_name == constraints.primary_key_name
    assert refused.value.constraint_table == PhysicalTable(("px_hist",), "vault_live")


# --------------------------------------------------------------------------- #
# Identifiers every component of which a dialect must quote on its own.        #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
def test_quoted_components_keep_their_identity_through_reads_and_writes(
    profile_run: Any, representation: _Representation
) -> None:
    db = _provisioned(profile_run)
    if representation == "typed":
        db.transact(lambda tx: tx.insert(Edge(id=1, label="a")))
        db.transact(
            lambda tx: tx.amend(tx.find(Edge.where(Edge.id == 1)).result(), Edge.label.set("b"))
        )
        (edge,) = db.find(Edge.where(Edge.label == "b")).results()
        assert edge.id == 1
    else:
        db.transact(lambda tx: tx.wire.insert(_name(Edge), {"id": 1, "label": "a"}))
        db.transact(
            lambda tx: tx.wire.amend_where(
                {"entity": _name(Edge), "predicate": _eq(Edge, "id", 1)}, {"label": "b"}
            )
        )
        (node,) = db.wire.find(
            {"target": _name(Edge), "predicate": _eq(Edge, "label", "b")}
        ).results()
        assert node["id"] == 1
    assert _held(profile_run, _EDGE_SCHEMA, "order")
    assert _rows(profile_run, 'select id, label from "Px.Edge""q"."order"') == [(1, "b")]
