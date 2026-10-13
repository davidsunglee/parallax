"""PostgreSQL evidence for to-one traversal and relationship matching.

The executable workload manifest below owns every workload, its pairing, its
independent reference observation, the scales it runs at, and the final
campaign's matrix. Ordinary runs exercise only bounded semantic witnesses and
the evidence helpers; every diagnostic mode is opted into through
``PARALLAX_TO_ONE_PERFORMANCE_MODE`` and writes nowhere else:

- ``inventory`` compiles the paired workloads' production statements, with no
  database, into a fresh ``..._OUTPUT`` directory (``-k baseline_inventory``);
- ``list`` prints workload, variant, and scale ids (``-k workload_inventory -s``);
- ``compare`` replays the frozen ``..._BASELINE`` inventory beside the current
  statements on one freshly seeded Testcontainers PostgreSQL, for the exact
  ``..._SUITE`` / ``..._WORKLOADS`` selected (``-k diagnostic_capture``);
- ``validate`` checks the bundle ``..._EVIDENCE`` names, writing nothing
  (``-k evidence_bundle``).
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import constants
from parallax.conformance.provision import schema_statements
from parallax.core import (
    LATEST,
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    ObjectQuery,
    Predicate,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    index,
    rel,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import TablePerConcreteSubtype
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import PredicateSelection, PredicateWrite, WriteAssignment
from parallax.snapshot import ScopedDatabase, connect
from tests._support.lowering_probes import lower_instruction
from tests._support.query_probes import canonical_document, predicate_node, typed_resolved
from tests._support.repo import REPO_ROOT
from tests._support.root_ownership import own_root
from tests.api import _traversal_evidence as evidence

_NS: Final = "to.one.performance"


class Region(Entity, table="top_region", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str | None] = attr(max_length=16)


class Customer(Entity, table="top_customer", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)
    tier: Attr[str | None] = attr(max_length=8)
    region_id: Attr[int | None]
    region: Rel[Region | None] = rel(cardinality=MANY_TO_ONE, join=("region_id", "id"))


class Dealer(Entity, table="top_dealer", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)


class Vehicle(Entity, namespace=_NS, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)
    maker: Attr[str] = attr(max_length=16)
    dealer_id: Attr[int | None]
    dealer: Rel[Dealer | None] = rel(cardinality=MANY_TO_ONE, join=("dealer_id", "id"))


class Car(Vehicle, table="top_car", namespace=_NS, inheritance=ConcreteSubtype()):
    seats: Attr[int | None] = attr(type=Int32)


class Bike(Vehicle, table="top_bike", namespace=_NS, inheritance=ConcreteSubtype()):
    gears: Attr[int | None] = attr(type=Int32)


class Pet(
    Entity,
    table="top_pet",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)


class Dog(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="dog")):
    bark_volume: Attr[int | None] = attr(type=Int32)


class Cat(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="cat")):
    indoor: Attr[bool | None]


class Parcel(ValueObject):
    sku: Attr[str]
    qty: Attr[int] = attr(type=Int32)


class OrderNote(
    Entity,
    table="top_order_note",
    namespace=_NS,
    indices=(index("top_order_note_order", "order_id"),),
):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    kind: Attr[str] = attr(max_length=8)


class Invoice(
    Entity,
    table="top_invoice",
    namespace=_NS,
    indices=(index("top_invoice_order", "order_id", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    amount: Attr[int] = attr(type=Int32)


class Order(Entity, table="top_order", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)
    status: Attr[str | None] = attr(max_length=8)
    qty: Attr[int] = attr(type=Int32)
    customer_id: Attr[int | None]
    vehicle_id: Attr[int | None]
    pet_id: Attr[int | None]
    tags: Attr[tuple[str, ...]]
    parcels: Attr[tuple[Parcel, ...]]
    customer: Rel[Customer | None] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))
    vehicle: Rel[Vehicle | None] = rel(cardinality=MANY_TO_ONE, join=("vehicle_id", "id"))
    pet: Rel[Pet | None] = rel(cardinality=MANY_TO_ONE, join=("pet_id", "id"))
    notes: Rel[tuple[OrderNote, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "order_id"))
    invoice: Rel[Invoice] = rel(cardinality=ONE_TO_ONE, join=("id", "order_id"))


class Item(Entity, table="top_item", namespace=_NS, indices=(index("top_item_order", "order_id"),)):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int | None]
    sku: Attr[str] = attr(max_length=8)
    quantity: Attr[int] = attr(type=Int32)
    flagged: Attr[bool]
    order: Rel[Order | None] = rel(cardinality=MANY_TO_ONE, join=("order_id", "id"))


class Coverage(Bitemporal, table="top_coverage", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int] = attr(type=Int32)


class Claim(
    Bitemporal,
    table="top_claim",
    namespace=_NS,
    indices=(index("top_claim_coverage", "coverage_id"),),
):
    id: Attr[int] = attr(primary_key=True)
    coverage_id: Attr[int]
    reserve: Attr[int] = attr(type=Int32)
    coverage: Rel[Coverage] = rel(cardinality=MANY_TO_ONE, join=("coverage_id", "id"))


MODEL: Final = DomainModel(
    Region,
    Customer,
    Dealer,
    Vehicle,
    Car,
    Bike,
    Pet,
    Dog,
    Cat,
    OrderNote,
    Invoice,
    Order,
    Item,
    Coverage,
    Claim,
)
META: Final = model_of(MODEL)
_MARCH: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Scales and deterministic seeding                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Scale:
    """One seeded population: ``orders`` parents each referenced by
    ``items_per_order`` roots, one parent in ``match_every`` named ``Ada``, one
    root in ``absent_every`` (0 for none) with no parent, ``tags`` scalar
    elements and ``parcels`` Value Objects per order, and ``notes`` related
    notes on two of every three orders."""

    orders: int
    items_per_order: int
    match_every: int
    absent_every: int
    tags: int
    parcels: int
    notes: int
    rationale: str

    @property
    def items(self) -> int:
        return self.orders * self.items_per_order

    def parameters(self) -> dict[str, object]:
        return {
            "orders": self.orders,
            "itemsPerOrder": self.items_per_order,
            "matchEvery": self.match_every,
            "absentEvery": self.absent_every,
            "tags": self.tags,
            "parcels": self.parcels,
            "notes": self.notes,
            "customers": _customers(self),
            "vehicles": _vehicles(self),
            "pets": _pets(self),
            "coverages": _coverages(self),
            "claims": _claims(self),
            "rationale": self.rationale,
        }


SCALES: Final[Mapping[str, Scale]] = {
    "smoke": Scale(24, 3, 4, 5, 3, 3, 2, "bounded semantic smoke data, not a measurement"),
    "focused": Scale(
        20_000, 10, 100, 1_000, 8, 4, 2, "200,000 roots: iteration-sized, absences included"
    ),
    "ticket": Scale(
        100_000, 10, 100, 0, 8, 4, 2, "COR-211: 100,000 parents, 1,000,000 roots, 1% matching"
    ),
    "ticket-selective": Scale(
        100_000, 10, 4, 0, 8, 4, 2, "the ticket population with 25% of parents matching"
    ),
    "ticket-unshared": Scale(
        1_000_000, 1, 100, 0, 8, 4, 2, "1,000,000 roots each reaching its own parent"
    ),
    "collections-empty": Scale(
        100_000, 10, 100, 0, 0, 0, 0, "the ticket population with empty target collections"
    ),
    "collections-large": Scale(
        100_000, 10, 100, 0, 64, 16, 16, "the ticket population with larger target collections"
    ),
}


def _customers(scale: Scale) -> int:
    return max(scale.orders // 10, 1)


def _vehicles(scale: Scale) -> int:
    return max(scale.orders // 4, 2)


def _pets(scale: Scale) -> int:
    return max(scale.orders // 2, 1)


def _coverages(scale: Scale) -> int:
    return max(scale.orders // 10, scale.match_every)


def _claims(scale: Scale) -> int:
    return max(scale.items // 10, 1)


_TABLES: Final = (
    "top_region",
    "top_dealer",
    "top_customer",
    "top_car",
    "top_bike",
    "top_pet",
    "top_order",
    "top_order_note",
    "top_invoice",
    "top_item",
    "top_coverage",
    "top_claim",
)


def seed_statements(scale: Scale) -> list[str]:
    """The deterministic population of ``scale``, as plain SQL with no binds."""
    m, a = scale.match_every, scale.absent_every
    p, customers, vehicles, pets = scale.orders, _customers(scale), _vehicles(scale), _pets(scale)
    coverages, claims = _coverages(scale), _claims(scale)
    tags = (
        "'[]'::jsonb"
        if scale.tags == 0
        else "(select jsonb_agg(case when e > 1 then 't' || mod(g + e, 10) when mod(g, "
        f"{m}) = 0 then 'vip' else 't0' end order by e) "
        f"from generate_series(1, {scale.tags}) e)"
    )
    parcels = (
        "'[]'::jsonb"
        if scale.parcels == 0
        else "(select jsonb_agg(jsonb_build_object('sku', 's' || e, 'qty', mod(g + e, 7)) "
        f"order by e) from generate_series(1, {scale.parcels}) e)"
    )
    absent = "false" if a == 0 else f"mod(g, {a}) = 0"
    return [
        "insert into top_region (id, name) select g, case when g = 10 then null else 'R' || g "
        "end from generate_series(1, 10) g",
        "insert into top_dealer (id, name) select g, 'D' || g from generate_series(1, 100) g",
        "insert into top_customer (id, name, tier, region_id) select g, 'C' || g, "
        "case mod(g, 3) when 0 then null when 1 then 'gold' else 'silver' end, "
        "case when mod(g, 50) = 0 then null else mod(g, 10) + 1 end "
        f"from generate_series(1, {customers}) g",
        "insert into top_car (id, maker, dealer_id, seats) select g, case when mod(g, 8) = 1 "
        "then 'Volvo' else 'Saab' end, mod(g, 100) + 1, case when mod(g, 6) = 5 then null "
        f"else mod(g, 7) end from generate_series(1, {vehicles}) g where mod(g, 2) = 1",
        "insert into top_bike (id, maker, dealer_id, gears) select g, 'Trek', mod(g, 100) + 1, "
        f"mod(g, 21) from generate_series(1, {vehicles}) g where mod(g, 2) = 0",
        "insert into top_pet (id, kind, name, bark_volume, indoor) select g, case mod(g, 2) "
        "when 0 then 'dog' else 'cat' end, 'P' || g, case when mod(g, 2) = 0 and mod(g, 10) <> 0 "
        "then mod(g, 9) end, case when mod(g, 2) = 1 then mod(g, 4) = 1 end "
        f"from generate_series(1, {pets}) g",
        "insert into top_order (id, name, status, qty, customer_id, vehicle_id, pet_id, tags, "
        f"parcels) select g, case when mod(g, {m}) = 0 then 'Ada' else 'N' || g end, "
        "case mod(g, 7) when 0 then null when 1 then 'open' else 'closed' end, mod(g, 20), "
        f"case when mod(g, 97) = 0 then null else mod(g, {customers}) + 1 end, "
        f"case when mod(g, 89) = 0 then null else mod(g, {vehicles}) + 1 end, "
        f"case when mod(g, 11) = 0 then null else mod(g, {pets}) + 1 end, {tags}, {parcels} "
        f"from generate_series(1, {p}) g",
        "insert into top_order_note (id, order_id, kind) select g, mod(g - 1, "
        f"{p}) + 1, case when mod(g, 5) = 0 then 'urgent' else 'info' end "
        f"from generate_series(1, {p * scale.notes}) g where mod(mod(g - 1, {p}) + 1, 3) <> 0",
        "insert into top_invoice (id, order_id, amount) select g, g, mod(g, 1000) "
        f"from generate_series(1, {p}) g where mod(g, 13) <> 0",
        "insert into top_item (id, order_id, sku, quantity, flagged) select g, "
        f"case when {absent} then null else mod(g - 1, {p}) + 1 end, 'S' || mod(g, 100), "
        f"mod(g, 10), false from generate_series(1, {scale.items}) g",
        "insert into top_coverage (id, amount, from_z, thru_z, in_z, out_z) select g, "
        f"case when mod(g, {m}) = 0 then 500 else 50 end, timestamptz '2024-01-01', "
        "timestamptz 'infinity', timestamptz '2024-01-01', timestamptz '2024-04-01' "
        f"from generate_series(1, {coverages}) g",
        "insert into top_coverage (id, amount, from_z, thru_z, in_z, out_z) select g, "
        f"case when mod(g, {m}) = 0 then 600 else 100 end, timestamptz '2024-01-01', "
        "timestamptz '2024-06-01', timestamptz '2024-04-01', timestamptz 'infinity' "
        f"from generate_series(1, {coverages}) g",
        "insert into top_coverage (id, amount, from_z, thru_z, in_z, out_z) select g, "
        f"case when mod(g, {m}) = 0 then 700 else 200 end, timestamptz '2024-06-01', "
        "timestamptz 'infinity', timestamptz '2024-04-01', timestamptz 'infinity' "
        f"from generate_series(1, {coverages}) g",
        "insert into top_claim (id, coverage_id, reserve, from_z, thru_z, in_z, out_z) "
        f"select g, mod(g - 1, {coverages}) + 1, mod(g, 1000), timestamptz '2024-01-01', "
        "timestamptz 'infinity', timestamptz '2024-01-01', timestamptz 'infinity' "
        f"from generate_series(1, {claims}) g",
        "create table top_item_seed as table top_item",
    ]


_DISTRIBUTIONS: Final[Mapping[str, str]] = {
    "absentParents": "select count(*) from top_item where order_id is null",
    "matchingParents": "select count(*) from top_order where name = 'Ada'",
    "rootsOfMatchingParents": (
        "select count(*) from top_item i join top_order o on o.id = i.order_id where o.name = 'Ada'"
    ),
    "maxRootsPerParent": (
        "select coalesce(max(n), 0) from (select count(*) n from top_item "
        "where order_id is not null group by order_id) r"
    ),
    "tagElements": "select coalesce(sum(jsonb_array_length(tags)), 0) from top_order",
    "notes": "select count(*) from top_order_note",
}


# --------------------------------------------------------------------------- #
# The executable workload manifest                                             #
# --------------------------------------------------------------------------- #

_JOINED: Final = "from top_item i join top_order o on o.id = i.order_id"
_ADA_ORDERS: Final = "select o.id from top_order o where o.name = 'Ada'"
_HEADLINE: Final = ("ticket", "ticket-selective", "ticket-unshared")
_COLLECTION_SCALES: Final = ("ticket", "collections-empty", "collections-large", "ticket-unshared")


@dataclass(frozen=True, slots=True)
class Workload:
    """One measured query shape: the Typed query authoring it, the independent
    SQL reading of the roots it selects (or the rows it writes), and where it
    runs in the final campaign."""

    id: str
    pairing: evidence.Pairing
    description: str
    query: Callable[[], ObjectQuery[Any, Any]]
    reference: str
    kind: evidence.Kind = "read"
    observation: evidence.Observation = "multiset"
    final_scales: tuple[str, ...] = ("ticket",)
    variants: tuple[str, ...] = field(default=evidence.PRODUCTION_VARIANTS)

    @property
    def suite(self) -> evidence.Suite:
        return cast("evidence.Suite", self.id.partition(".")[0])

    def classification(self) -> evidence.Classification:
        variants = ("current",) if self.pairing == "current-only" else self.variants
        return evidence.Classification(
            self.id, self.suite, self.pairing, self.kind, self.observation, variants
        )


def _item(predicate: Callable[[], Predicate[Any]]) -> Callable[[], ObjectQuery[Any, Any]]:
    return lambda: Item.where(predicate())


def _ids(where: str) -> str:
    return f"select i.id {_JOINED} where {where}"


def _claims_where(coverage: str, claim: str) -> str:
    return (
        f"select c.id from top_claim c where {claim} and c.coverage_id in "
        f"(select v.id from top_coverage v where {coverage})"
    )


_LATEST_COVERAGE: Final = "v.thru_z = 'infinity' and v.out_z = 'infinity'"
_LATEST_CLAIM: Final = "c.thru_z = 'infinity' and c.out_z = 'infinity'"
_MARCH_VALID: Final = "{0}.from_z <= '2024-03-01' and {0}.thru_z > '2024-03-01'"
_MARCH_TX: Final = "{0}.in_z <= '2024-03-01' and {0}.out_z > '2024-03-01'"
_GUARDED_NEGATION: Final = (
    "select i.id from top_item i where i.order_id is null or i.order_id in "
    "(select o.id from top_order o where o.name <> 'Ada')"
)
_VIP: Final = "select o.id from top_order o where o.tags @> '[\"vip\"]'"


def _workloads() -> tuple[Workload, ...]:
    order = Item.order
    ada = order.name == "Ada"
    return (
        Workload(
            "reads.dotted-eq",
            "paired",
            "bare dotted equality: the ticket's positive query",
            _item(lambda: Item.order.name == "Ada"),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            final_scales=_HEADLINE,
        ),
        Workload(
            "reads.guarded-dotted-eq",
            "paired",
            "presence-guarded dotted equality (m-navigate-007)",
            _item(lambda: Item.order.exists() & (Item.order.name == "Ada")),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            final_scales=_HEADLINE,
        ),
        Workload(
            "reads.guarded-dotted-eq-negated",
            "paired",
            "complete negation of the guarded equality",
            _item(lambda: ~(Item.order.exists() & (Item.order.name == "Ada"))),
            _GUARDED_NEGATION,
            final_scales=_HEADLINE,
        ),
        Workload(
            "reads.dotted-eq-negated",
            "paired",
            "negated dotted equality keeps an absent parent unknown",
            _item(lambda: ~(Item.order.name == "Ada")),
            _ids("o.name <> 'Ada'"),
        ),
        Workload(
            "reads.dotted-nullable-negated",
            "paired",
            "negated nullable dotted equality keeps a null field unknown",
            _item(lambda: ~(Item.order.status == "open")),
            _ids("o.status <> 'open'"),
        ),
        Workload(
            "reads.repeated-fields",
            "paired",
            "two fields of one parent in a conjunction",
            _item(lambda: (Item.order.name == "Ada") & (Item.order.qty >= 10)),
            _ids("o.name = 'Ada' and o.qty >= 10"),
        ),
        Workload(
            "reads.repeated-fields-disjunction",
            "paired",
            "two fields of one parent in a disjunction with a null check",
            _item(lambda: (Item.order.name == "Ada") | Item.order.status.is_null()),
            "select i.id from top_item i left join top_order o on o.id = i.order_id "
            "where o.name = 'Ada' or o.status is null",
        ),
        Workload(
            "reads.multi-hop-prefix",
            "paired",
            "two suffixes sharing the parent-customer prefix",
            _item(
                lambda: (
                    (Item.order.customer.tier == "gold") & (Item.order.customer.region.name == "R2")
                )
            ),
            f"select i.id {_JOINED} join top_customer c on c.id = o.customer_id "
            "join top_region r on r.id = c.region_id where c.tier = 'gold' and r.name = 'R2'",
        ),
        Workload(
            "reads.multi-hop-null-check",
            "paired",
            "a null check three hops away sees every missing intermediate",
            _item(lambda: Item.order.customer.region.name.is_null()),
            "select i.id from top_item i left join top_order o on o.id = i.order_id "
            "left join top_customer c on c.id = o.customer_id "
            "left join top_region r on r.id = c.region_id where r.name is null",
        ),
        Workload(
            "reads.presence",
            "paired",
            "bare parent presence",
            _item(lambda: Item.order.exists()),
            "select i.id from top_item i where i.order_id in (select o.id from top_order o)",
        ),
        Workload(
            "reads.reverse-unique",
            "paired",
            "a one-to-one target reached through its unique foreign key",
            lambda: Order.where(Order.invoice.amount < 10),
            "select o.id from top_order o join top_invoice v on v.order_id = o.id "
            "where v.amount < 10",
        ),
        Workload(
            "reads.dotted-eq-paged",
            "paired",
            "dotted equality under an ordered page",
            lambda: Item.where(Item.order.name == "Ada").order_by(Item.id.asc()).limit(100),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS}) "
            "order by i.id limit 100",
            observation="ordered",
        ),
        Workload(
            "reads.match",
            "current-only",
            "relationship matching: a parent named Ada",
            _item(lambda: Item.order.exists(Order.name == "Ada")),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            final_scales=_HEADLINE,
        ),
        Workload(
            "reads.match-negated",
            "current-only",
            "no parent named Ada, absent parents included",
            _item(lambda: Item.order.not_exists(Order.name == "Ada")),
            _GUARDED_NEGATION,
            final_scales=_HEADLINE,
        ),
        Workload(
            "reads.match-nullable-compound",
            "current-only",
            "matching a compound operand over a nullable field",
            _item(lambda: Item.order.exists((Order.status == "open") | (Order.qty >= 15))),
            "select i.id from top_item i where i.order_id in "
            "(select o.id from top_order o where o.status = 'open' or o.qty >= 15)",
        ),
        Workload(
            "reads.match-nested",
            "current-only",
            "a parent match nesting a customer match",
            _item(lambda: Item.order.exists(Order.customer.exists(Customer.tier == "gold"))),
            "select i.id from top_item i where i.order_id in (select o.id from top_order o "
            "join top_customer c on c.id = o.customer_id where c.tier = 'gold')",
        ),
        Workload(
            "mixed.temporal-latest-dotted",
            "paired",
            "a dotted field across a bitemporal hop at Latest",
            lambda: Claim.where(Claim.coverage.amount == 700).as_of(
                tx_time=LATEST, valid_time=LATEST
            ),
            _claims_where(f"v.amount = 700 and {_LATEST_COVERAGE}", _LATEST_CLAIM),
        ),
        Workload(
            "mixed.temporal-finite-valid-dotted",
            "paired",
            "a dotted field at Latest Transaction Time and a finite Valid Time",
            lambda: Claim.where(Claim.coverage.amount == 600).as_of(
                tx_time=LATEST, valid_time=_MARCH
            ),
            _claims_where(
                f"v.amount = 600 and {_MARCH_VALID.format('v')} and v.out_z = 'infinity'",
                f"{_MARCH_VALID.format('c')} and c.out_z = 'infinity'",
            ),
        ),
        Workload(
            "mixed.temporal-historical-dotted",
            "paired",
            "a dotted field at finite historical coordinates on both axes",
            lambda: Claim.where(Claim.coverage.amount == 500).as_of(
                tx_time=_MARCH, valid_time=_MARCH
            ),
            _claims_where(
                f"v.amount = 500 and {_MARCH_VALID.format('v')} and {_MARCH_TX.format('v')}",
                f"{_MARCH_VALID.format('c')} and {_MARCH_TX.format('c')}",
            ),
        ),
        Workload(
            "mixed.temporal-match",
            "current-only",
            "matching across a bitemporal hop at Latest",
            lambda: Claim.where(Claim.coverage.exists(Coverage.amount == 700)).as_of(
                tx_time=LATEST, valid_time=LATEST
            ),
            _claims_where(f"v.amount = 700 and {_LATEST_COVERAGE}", _LATEST_CLAIM),
        ),
        Workload(
            "mixed.narrow-tph-operand",
            "paired",
            "a narrowed table-per-hierarchy target behind the parent",
            _item(lambda: Item.order.pet.is_a(Dog, where=Dog.bark_volume > 5)),
            f"select i.id {_JOINED} join top_pet p on p.id = o.pet_id "
            "where p.kind = 'dog' and p.bark_volume > 5",
        ),
        Workload(
            "mixed.narrow-tpcs-operand",
            "paired",
            "a narrowed table-per-concrete-subtype target behind the parent",
            _item(lambda: Item.order.vehicle.is_a(Car, where=Car.seats > 2)),
            f"select i.id {_JOINED} join top_car c on c.id = o.vehicle_id where c.seats > 2",
        ),
        Workload(
            "mixed.unsafe-middle-hop",
            "paired",
            "an eligible parent, a multi-table vehicle, and an eligible dealer",
            _item(lambda: Item.order.vehicle.dealer.name == "D2"),
            f"select i.id {_JOINED} join (select id, dealer_id from top_car union all "
            "select id, dealer_id from top_bike) v on v.id = o.vehicle_id "
            "join top_dealer d on d.id = v.dealer_id where d.name = 'D2'",
        ),
        Workload(
            "mixed.unsafe-terminal-field",
            "paired",
            "a field of a multi-table vehicle behind the parent",
            _item(lambda: Item.order.vehicle.maker == "Volvo"),
            f"select i.id {_JOINED} join (select id, maker from top_car union all "
            "select id, maker from top_bike) v on v.id = o.vehicle_id where v.maker = 'Volvo'",
        ),
        Workload(
            "collections.scalar-any",
            "paired",
            "a parent's scalar collection holds vip (m-predicate-080)",
            _item(lambda: Item.order.tags.any(Item.order.tags.element == "vip")),
            f"select i.id from top_item i where i.order_id in ({_VIP})",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.scalar-none-bare",
            "paired",
            "a parent's scalar collection is empty or absent (m-predicate-081)",
            _item(lambda: Item.order.tags.none()),
            "select i.id from top_item i left join top_order o on o.id = i.order_id "
            "where o.id is null or jsonb_array_length(o.tags) = 0",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.scalar-all",
            "paired",
            "strict universal truth over a parent's scalar collection",
            _item(lambda: Item.order.tags.all(Item.order.tags.element.starts_with("t"))),
            "select i.id from top_item i left join top_order o on o.id = i.order_id "
            "where o.id is null or not exists (select 1 from jsonb_array_elements_text(o.tags) "
            "e(v) where left(v, 1) <> 't')",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.scalar-independent-any",
            "paired",
            "two independent quantifiers over one parent collection",
            _item(
                lambda: (
                    Item.order.tags.any(Item.order.tags.element == "vip")
                    & Item.order.tags.any(Item.order.tags.element == "t3")
                )
            ),
            "select i.id from top_item i where i.order_id in (select o.id from top_order o "
            "where o.tags @> '[\"vip\"]' and o.tags @> '[\"t3\"]')",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.scalar-same-element",
            "paired",
            "one quantifier whose conjunction binds one element",
            _item(
                lambda: Item.order.tags.any(
                    (Item.order.tags.element >= "t1") & (Item.order.tags.element < "t2")
                )
            ),
            "select i.id from top_item i where i.order_id in (select o.id from top_order o "
            "where exists (select 1 from jsonb_array_elements_text(o.tags) e(v) "
            "where v >= 't1' and v < 't2'))",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.value-object-any",
            "paired",
            "a parent's many Value Object holds a large parcel",
            _item(lambda: Item.order.parcels.any(Parcel.qty > 3)),
            "select i.id from top_item i where i.order_id in (select o.id from top_order o "
            "where exists (select 1 from jsonb_array_elements(o.parcels) e "
            "where (e ->> 'qty')::int > 3))",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.related-any",
            "paired",
            "a parent's related notes include an urgent one",
            _item(lambda: Item.order.notes.any(OrderNote.kind == "urgent")),
            "select i.id from top_item i where i.order_id in "
            "(select n.order_id from top_order_note n where n.kind = 'urgent')",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.related-none-bare",
            "paired",
            "a parent has no related notes, or there is no parent",
            _item(lambda: Item.order.notes.none()),
            "select i.id from top_item i where i.order_id is null or i.order_id not in "
            "(select n.order_id from top_order_note n)",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "collections.guarded-occupancy",
            "paired",
            "a present parent whose scalar collection is occupied",
            _item(lambda: Item.order.exists() & Item.order.tags.any()),
            "select i.id from top_item i where i.order_id in "
            "(select o.id from top_order o where jsonb_array_length(o.tags) > 0)",
            final_scales=_COLLECTION_SCALES,
        ),
        Workload(
            "writes.update-dotted-eq",
            "paired",
            "readless UPDATE selected by dotted equality",
            _item(lambda: ada),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            kind="update",
            observation="affected",
            final_scales=("ticket", "ticket-selective"),
        ),
        Workload(
            "writes.delete-dotted-eq",
            "paired",
            "readless DELETE selected by dotted equality",
            _item(lambda: ada),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            kind="delete",
            observation="affected",
        ),
        Workload(
            "writes.update-guarded-negated",
            "paired",
            "readless UPDATE selected by the complete guarded negation",
            _item(lambda: ~(order.exists() & (order.name == "Ada"))),
            _GUARDED_NEGATION,
            kind="update",
            observation="affected",
        ),
        Workload(
            "writes.update-collection-through-to-one",
            "paired",
            "readless UPDATE selected by a parent's scalar collection",
            _item(lambda: Item.order.tags.any(Item.order.tags.element == "vip")),
            f"select i.id from top_item i where i.order_id in ({_VIP})",
            kind="update",
            observation="affected",
        ),
        Workload(
            "writes.update-match",
            "current-only",
            "readless UPDATE selected by relationship matching",
            _item(lambda: Item.order.exists(Order.name == "Ada")),
            f"select i.id from top_item i where i.order_id in ({_ADA_ORDERS})",
            kind="update",
            observation="affected",
        ),
    )


WORKLOADS: Final[tuple[Workload, ...]] = _workloads()
_BY_ID: Final[Mapping[str, Workload]] = {workload.id: workload for workload in WORKLOADS}
CLASSIFICATIONS: Final = tuple(workload.classification() for workload in WORKLOADS)
FINAL_MATRIX: Final[tuple[tuple[str, str], ...]] = tuple(
    (workload.id, scale) for workload in WORKLOADS for scale in workload.final_scales
)
_FLAG: Final = f"{Item.identity.canonical}.flagged"


def compile_statement(workload: Workload) -> LoweredStatement:
    """The production statement ``workload`` executes: the eager instance read a
    Typed find plans, or the readless predicate write a Typed ``_where`` verb
    lowers to."""
    query = workload.query()
    if workload.kind == "read":
        plan = UNCACHED_READ_PLANNER.plan(
            edition="to-one-evidence",
            model=CatalogedModel(META),
            dialect=POSTGRES,
            query=typed_resolved(query, MODEL),
            result_form="instance",
            preference=None,
        )
        return plan.root_read()[0].statement
    write = PredicateWrite(
        "amend" if workload.kind == "update" else "delete",
        PredicateSelection(Item.identity.canonical, predicate_node(query, MODEL)),
        assignments=(WriteAssignment(attr=_FLAG, value=True),) if workload.kind == "update" else (),
    )
    (statement,) = lower_instruction(write, META)
    return statement


def _statement_document(statement: LoweredStatement) -> dict[str, object]:
    return {"sql": statement.sql, "binds": evidence.encode_binds(statement.binds)}


def _parameters(workload: Workload) -> dict[str, object]:
    return {
        "objectQuery": canonical_document(workload.query(), MODEL),
        "reference": workload.reference,
        "assignment": {_FLAG: True} if workload.kind == "update" else None,
        "finalScales": list(workload.final_scales),
    }


def _driver_files() -> list[Path]:
    here = Path(__file__)
    return [here, here.with_name("_traversal_evidence.py")]


def _schema_text() -> str:
    return "\n".join(schema_statements(META))


def _seed_text() -> str:
    return "\n".join(
        f"-- {name}\n" + "\n".join(seed_statements(scale)) for name, scale in SCALES.items()
    )


def _provenance(kind: str, capture_id: str) -> dict[str, object]:
    return {
        "manifestVersion": evidence.MANIFEST_VERSION,
        "kind": kind,
        "captureId": capture_id,
        "createdAt": evidence.now(),
        "command": evidence.command_record(),
        "compiler": evidence.compiler_state(REPO_ROOT),
        "driver": {
            "files": evidence.file_digests(_driver_files(), REPO_ROOT),
            "digest": evidence.sha256_text(
                "".join(path.read_text(encoding="utf-8") for path in _driver_files())
            ),
        },
        "schema": {"digest": evidence.sha256_text(_schema_text())},
        "seed": {"digest": evidence.sha256_text(_seed_text())},
        "python": sys.version.split()[0],
    }


def write_inventory(directory: Path) -> Path:
    """Freeze every paired workload's production statement and provenance; no
    database is reached and no execution is claimed."""
    writer = evidence.BundleWriter(directory, "evidence-baseline")
    for suite in evidence.SUITES:
        members = [workload for workload in WORKLOADS if workload.suite == suite]
        writer.write(
            f"{suite}-statements",
            {
                "suite": suite,
                "parameters": {workload.id: _parameters(workload) for workload in members},
                "statements": {
                    workload.id: _statement_document(compile_statement(workload))
                    for workload in members
                    if workload.pairing == "paired"
                },
            },
        )
    return writer.finish(
        {
            **_provenance("inventory", "baseline"),
            "scales": {name: scale.parameters() for name, scale in SCALES.items()},
            "finalMatrix": [list(point) for point in FINAL_MATRIX],
            "workloads": [
                {
                    "id": workload.id,
                    "suite": workload.suite,
                    "pairing": workload.pairing,
                    "kind": workload.kind,
                    "observation": workload.observation,
                    "description": workload.description,
                }
                for workload in WORKLOADS
            ],
        }
    )


def frozen_statements(manifest: Path) -> dict[str, LoweredStatement]:
    """The inventory's statements, replayed exactly as they were frozen."""
    document = evidence.load(manifest)
    frozen: dict[str, LoweredStatement] = {}
    for entry in cast("list[Mapping[str, Any]]", document["files"]):
        content = evidence.load(manifest.parent / str(entry["path"]))
        for name, statement in cast("Mapping[str, Any]", content.get("statements", {})).items():
            frozen[name] = LoweredStatement(
                str(statement["sql"]), evidence.decode_binds(statement["binds"])
            )
    return frozen


# --------------------------------------------------------------------------- #
# Live execution                                                               #
# --------------------------------------------------------------------------- #

_SETTINGS: Final = (
    "server_version",
    "shared_buffers",
    "work_mem",
    "effective_cache_size",
    "jit",
    "max_parallel_workers_per_gather",
    "random_page_cost",
)


class _Server:
    """The control session statements, references, and plans run on."""

    def __init__(self, control: Any) -> None:
        self._control = control

    def rows(self, sql: str, binds: Sequence[object] = ()) -> list[Any]:
        return cast("list[Any]", self._control.execute(POSTGRES.to_driver_sql(sql), binds))

    def write(self, sql: str) -> None:
        self._control.execute_write(sql, [])

    def ids(self, sql: str, binds: Sequence[object] = ()) -> list[int]:
        return [int(row[0]) for row in self.rows(sql, binds)]

    def affected(self, workload: Workload, statement: LoweredStatement) -> tuple[int, list[int]]:
        """Run a mutation and read back what it changed, then roll both back."""
        with self._control.native.transaction(force_rollback=True):
            count = self._control.execute_write(
                POSTGRES.to_driver_sql(statement.sql), statement.binds
            )
            changed = self.ids(_changed_rows(workload))
        self.write("vacuum top_item")
        return int(count), changed

    def timed(self, workload: Workload, statement: LoweredStatement) -> int:
        driver = POSTGRES.to_driver_sql(statement.sql)
        if workload.kind == "read":
            started = time.perf_counter_ns()
            self._control.execute(driver, statement.binds)
            return time.perf_counter_ns() - started
        with self._control.native.transaction(force_rollback=True):
            started = time.perf_counter_ns()
            self._control.execute_write(driver, statement.binds)
            elapsed = time.perf_counter_ns() - started
        self.write("vacuum top_item")
        return elapsed

    def explained(self, workload: Workload, statement: LoweredStatement) -> Mapping[str, Any]:
        sql = POSTGRES.to_driver_sql(f"explain (analyze, buffers, format json) {statement.sql}")
        if workload.kind == "read":
            document = self._control.execute(sql, statement.binds)[0][0]
        else:
            with self._control.native.transaction(force_rollback=True):
                document = self._control.execute(sql, statement.binds)[0][0]
            self.write("vacuum top_item")
        plans = cast("list[Mapping[str, Any]]", document)
        return plans[0]

    def settings(self) -> dict[str, str]:
        return {name: str(self.rows(f"show {name}")[0][0]) for name in _SETTINGS}

    def counts(self) -> dict[str, int]:
        return {table: int(self.rows(f"select count(*) from {table}")[0][0]) for table in _TABLES}

    def distributions(self) -> dict[str, int]:
        return {name: int(self.rows(sql)[0][0]) for name, sql in _DISTRIBUTIONS.items()}

    def seed_digest(self) -> list[int]:
        return [
            int(value)
            for value in self.rows(
                "select count(*), coalesce(sum(id), 0), count(*) filter (where flagged) "
                "from top_item"
            )[0]
        ]


def _changed_rows(workload: Workload) -> str:
    if workload.kind == "update":
        return "select id from top_item where flagged"
    return (
        "select s.id from top_item_seed s where not exists "
        "(select 1 from top_item i where i.id = s.id)"
    )


def _restore(server: _Server, workload: Workload) -> None:
    if workload.kind == "update":
        server.write("update top_item set flagged = false where flagged")
    else:
        server.write(
            "insert into top_item select * from top_item_seed s where not exists "
            "(select 1 from top_item i where i.id = s.id)"
        )
    server.write("vacuum analyze top_item")


def _seeded(profile_run: Any, scale: Scale) -> tuple[ScopedDatabase, _Server, Any]:
    profile_run.reset(META, {})
    db = own_root(connect(profile_run.port, MODEL)).using_database_login()
    control = profile_run.control()
    server = _Server(control)
    for statement in seed_statements(scale):
        server.write(statement)
    for table in (*_TABLES, "top_item_seed"):
        server.write(f"vacuum analyze {table}")
    return db, server, control


def _public(db: ScopedDatabase, server: _Server, workload: Workload) -> list[int]:
    """The roots a Typed read delivers, or the rows a committed Typed write
    changed — restored before returning."""
    query = workload.query()
    if workload.kind == "read":
        with db.stream(query, batch_size=10_000) as roots:
            return [root.id for root in roots]
    if workload.kind == "update":
        db.transact(lambda tx: tx.amend_where(query, Item.flagged.set(True)))
    else:
        db.transact(lambda tx: tx.delete_where(query))
    changed = server.ids(_changed_rows(workload))
    _restore(server, workload)
    return changed


@dataclass(frozen=True, slots=True)
class _Observed:
    reference: dict[str, object]
    statements: dict[str, dict[str, object]]
    public: dict[str, object]
    affected: dict[str, int]

    @property
    def parity(self) -> bool:
        expected = self.reference["digest"]
        return (
            all(observed["digest"] == expected for observed in self.statements.values())
            and self.public["digest"] == expected
            and all(count == self.reference["count"] for count in self.affected.values())
        )


def observe(
    db: ScopedDatabase,
    server: _Server,
    workload: Workload,
    statements: Mapping[str, LoweredStatement],
) -> _Observed:
    """Every independent observation of one workload: its reference reading,
    each variant statement, and the public Typed execution."""
    reference_ids = server.ids(workload.reference)
    if workload.observation == "affected":
        reference = evidence.observed(reference_ids, "multiset")
    else:
        reference = evidence.observed(reference_ids, workload.observation)
    observed: dict[str, dict[str, object]] = {}
    affected: dict[str, int] = {}
    for variant, statement in statements.items():
        if workload.kind == "read":
            observed[variant] = evidence.observed(
                server.ids(statement.sql, statement.binds), workload.observation
            )
        else:
            count, changed = server.affected(workload, statement)
            affected[variant] = count
            observed[variant] = evidence.observed(changed, "multiset")
    assert server.seed_digest()[2] == 0, "a mutation observation left a row changed"
    public_ids = _public(db, server, workload)
    public_form = "multiset" if workload.observation == "affected" else workload.observation
    public = evidence.observed(public_ids, public_form)
    if workload.observation == "ordered":
        reference = {**reference, "count": len(reference_ids)}
    return _Observed(reference, observed, public, affected)


def measure(
    server: _Server,
    workload: Workload,
    statements: Mapping[str, LoweredStatement],
    selection: evidence.Selection,
) -> dict[str, dict[str, object]]:
    """Warm each variant, then take ordinary and EXPLAIN samples in rounds that
    alternate which variant goes first."""
    order = list(statements)
    for _ in range(selection.warmups):
        for variant in order:
            server.timed(workload, statements[variant])
            server.explained(workload, statements[variant])
    ordinary: dict[str, list[int]] = {variant: [] for variant in order}
    plans: dict[str, list[Mapping[str, Any]]] = {variant: [] for variant in order}
    for round_ in range(selection.samples):
        for variant in order if round_ % 2 == 0 else reversed(order):
            ordinary[variant].append(server.timed(workload, statements[variant]))
    for round_ in range(selection.explains):
        for variant in order if round_ % 2 == 0 else reversed(order):
            plans[variant].append(server.explained(workload, statements[variant]))
    return {
        variant: {
            "ordinaryNs": ordinary[variant],
            "ordinary": evidence.timing_summary(ordinary[variant]),
            "explain": plans[variant],
            "summary": evidence.plan_summary(plans[variant]),
        }
        for variant in order
    }


def capture(
    profile_run: Any,
    selection: evidence.Selection,
    directory: Path,
    *,
    baseline: Path | None,
    capture_id: str,
) -> Path:
    """Seed each selected scale once, observe and measure its selected points,
    and write one capture bundle."""
    writer = evidence.BundleWriter(directory, f"evidence-{capture_id}")
    frozen = {} if baseline is None else frozen_statements(baseline)
    points = _points(selection)
    scales: dict[str, object] = {}
    entries: list[dict[str, object]] = []
    server_record: dict[str, object] = {}
    written: set[str] = set()
    for scale_name in dict.fromkeys(scale for _, scale in points):
        scale = SCALES[scale_name]
        started = time.perf_counter()
        db, server, control = _seeded(profile_run, scale)
        try:
            scales[scale_name] = {
                "parameters": scale.parameters(),
                "seedSeconds": time.perf_counter() - started,
                "counts": server.counts(),
                "distributions": server.distributions(),
            }
            server_record = {
                "image": constants.POSTGRES_IMAGE,
                "version": str(server.rows("select version()")[0][0]),
                "settings": server.settings(),
                "container": "Testcontainers defaults: no CPU or memory limit is set",
                "host": {"platform": platform.platform(), "cpus": os.cpu_count()},
            }
            for workload_id, point_scale in points:
                if point_scale != scale_name:
                    continue
                workload = _BY_ID[workload_id]
                statements = _variant_statements(workload, selection, frozen)
                files: dict[str, str] = {}
                for variant, statement in statements.items():
                    suffix = f"{workload.id}-{variant}-statement"
                    if suffix not in written:
                        writer.write(suffix, _statement_document(statement))
                        written.add(suffix)
                    files[variant] = f"{writer.prefix}-{suffix}.json"
                observed = observe(db, server, workload, statements)
                assert observed.parity, (workload.id, observed)
                measured = measure(server, workload, statements, selection)
                variants = [
                    {
                        "variant": variant,
                        "statement": files[variant],
                        "samples": writer.write(
                            f"{workload.id}-{scale_name}-{variant}-samples", measured[variant]
                        ),
                    }
                    for variant in statements
                ]
                comparison = (
                    evidence.compare_summaries(
                        cast("Mapping[str, Any]", measured["baseline"]["summary"]),
                        cast("Mapping[str, Any]", measured["current"]["summary"]),
                    )
                    if set(measured) >= set(evidence.PRODUCTION_VARIANTS)
                    else None
                )
                entries.append(
                    {
                        "id": workload.id,
                        "scale": scale_name,
                        "pairing": workload.pairing,
                        "kind": workload.kind,
                        "variants": variants,
                        "comparison": comparison,
                        "observations": {
                            "parity": observed.parity,
                            "reference": observed.reference,
                            "statements": observed.statements,
                            "public": observed.public,
                            "affectedRows": observed.affected,
                        },
                    }
                )
        finally:
            control.close()
    provenance = _provenance("capture", capture_id)
    return writer.finish(
        {
            **provenance,
            "baseline": None
            if baseline is None
            else {
                "manifest": str(baseline),
                "digest": evidence.sha256_bytes(baseline.read_bytes()),
            },
            "server": server_record,
            "seed": {**cast("Mapping[str, object]", provenance["seed"]), "scales": scales},
            "selection": {
                "suite": selection.suite,
                "campaign": selection.campaign,
                "workloads": list(selection.workloads),
                "variants": list(selection.variants),
                "scale": selection.scale,
                "points": [list(point) for point in points],
            },
            "protocol": {
                "warmups": selection.warmups,
                "samples": selection.samples,
                "explains": selection.explains,
                "order": "variants alternate first place each round; ordinary rounds precede "
                "EXPLAIN rounds; a mutation runs in a rolled-back transaction and its table is "
                "vacuumed after every execution",
                "ordinaryTiming": "client wall clock of execution plus full result transfer",
                "explainTiming": "server-reported planning and execution time",
            },
            "workloads": entries,
        }
    )


def _points(selection: evidence.Selection) -> list[tuple[str, str]]:
    if selection.campaign == "final":
        return [point for point in FINAL_MATRIX if point[0] in selection.workloads]
    return [(name, selection.scale) for name in selection.workloads]


def _variant_statements(
    workload: Workload,
    selection: evidence.Selection,
    frozen: Mapping[str, LoweredStatement],
) -> dict[str, LoweredStatement]:
    statements: dict[str, LoweredStatement] = {}
    for variant in evidence.variants_for(workload.classification(), selection):
        if variant == "baseline":
            if workload.id not in frozen:
                raise evidence.EvidenceError(f"{workload.id} has no frozen baseline statement")
            statements[variant] = frozen[workload.id]
        elif variant == "current":
            statements[variant] = compile_statement(workload)
        else:
            raise evidence.EvidenceError(f"{workload.id} renders no {variant!r} statement")
    return statements


# --------------------------------------------------------------------------- #
# Diagnostic entrypoints                                                       #
# --------------------------------------------------------------------------- #


def _require_mode(mode: evidence.Mode) -> None:
    if evidence.selected_mode() != mode:
        pytest.skip(f"diagnostic: set PARALLAX_TO_ONE_PERFORMANCE_MODE={mode} to run")


def test_baseline_inventory() -> None:
    _require_mode("inventory")
    manifest = write_inventory(evidence.required_path("OUTPUT"))
    evidence.assert_valid(evidence.validate_inventory(manifest, CLASSIFICATIONS))


def test_workload_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    listing = list(_listing())
    assert len({workload.id for workload in WORKLOADS}) == len(WORKLOADS)
    assert {workload.suite for workload in WORKLOADS} == set(evidence.SUITES)
    assert {scale for _, scale in FINAL_MATRIX} <= set(SCALES)
    for population in ("tags", "parcels", "notes"):
        sizes = {getattr(SCALES[name], population) for name in _COLLECTION_SCALES}
        assert 0 in sizes and len(sizes) >= 3, (population, sizes)
    if evidence.selected_mode() == "list":
        with capsys.disabled():
            print("\n".join(listing))


def _listing() -> Iterator[str]:
    yield "scales: " + ", ".join(SCALES)
    for workload in WORKLOADS:
        variants = ",".join(workload.classification().variants)
        scales = ",".join(workload.final_scales)
        yield (
            f"{workload.id}  {workload.pairing}  {workload.kind}  variants={variants}  "
            f"final={scales}  {workload.description}"
        )


# Admitted before fixture setup, so an unselected capture never starts a container.
@pytest.mark.skipif(
    evidence.environment("MODE") != "compare",
    reason="diagnostic: set PARALLAX_TO_ONE_PERFORMANCE_MODE=compare to run",
)
def test_diagnostic_capture(profile_run: Any) -> None:
    selection = evidence.select(CLASSIFICATIONS, tuple(SCALES), default_scale="focused")
    baseline_path = None
    if any(_BY_ID[name].pairing == "paired" for name in selection.workloads):
        baseline_path = evidence.required_path("BASELINE")
        evidence.assert_valid(evidence.validate_inventory(baseline_path, CLASSIFICATIONS))
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dt%H%M%S")
    capture_id = "final" if selection.campaign == "final" else f"{selection.suite}-{stamp}"
    manifest = capture(
        profile_run,
        selection,
        evidence.required_path("OUTPUT"),
        baseline=baseline_path,
        capture_id=capture_id,
    )
    evidence.assert_valid(evidence.validate_capture(manifest, CLASSIFICATIONS, FINAL_MATRIX))


def test_evidence_bundle() -> None:
    _require_mode("validate")
    path = evidence.required_path("EVIDENCE")
    document = evidence.load(path)
    if document.get("kind") == "inventory":
        problems = evidence.validate_inventory(path, CLASSIFICATIONS)
    else:
        problems = evidence.validate_capture(path, CLASSIFICATIONS, FINAL_MATRIX)
    evidence.assert_valid(problems)


# --------------------------------------------------------------------------- #
# Bounded witnesses run by every ordinary selection                           #
# --------------------------------------------------------------------------- #


def test_diagnostic_modes_stay_inert_without_an_explicit_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [name for name in os.environ if name.startswith(evidence.ENVIRONMENT_PREFIX)]:
        monkeypatch.delenv(name)
    assert evidence.selected_mode() is None
    with pytest.raises(evidence.EvidenceError, match="names exact workloads"):
        evidence.select(
            CLASSIFICATIONS,
            tuple(SCALES),
            {f"{evidence.ENVIRONMENT_PREFIX}SUITE": "reads"},
            default_scale="focused",
        )


def test_the_inventory_freezes_every_paired_statement(tmp_path: Path) -> None:
    manifest = write_inventory(tmp_path)
    evidence.assert_valid(evidence.validate_inventory(manifest, CLASSIFICATIONS))
    frozen = frozen_statements(manifest)
    paired = [workload for workload in WORKLOADS if workload.pairing == "paired"]
    assert set(frozen) == {workload.id for workload in paired}
    for workload in paired:
        replayed, current = frozen[workload.id], compile_statement(workload)
        assert replayed.sql == current.sql
        assert [(type(bind), bind) for bind in replayed.binds] == [
            (type(bind), bind) for bind in current.binds
        ]
    with pytest.raises(evidence.EvidenceError, match="already holds"):
        write_inventory(tmp_path)


def test_seeding_and_references_spell_no_driver_placeholder() -> None:
    for scale in SCALES.values():
        for statement in seed_statements(scale):
            assert "?" not in statement and "%" not in statement
    for workload in WORKLOADS:
        assert "?" not in workload.reference and "%" not in workload.reference


_SMOKE_WORKLOADS: Final = (
    "reads.guarded-dotted-eq-negated",
    "reads.repeated-fields-disjunction",
    "reads.multi-hop-null-check",
    "reads.dotted-eq-paged",
    "reads.match-negated",
    "mixed.temporal-historical-dotted",
    "mixed.unsafe-middle-hop",
    "collections.scalar-all",
    "collections.value-object-any",
    "writes.delete-dotted-eq",
    "writes.update-match",
)


def test_every_workload_agrees_with_its_reference_on_smoke_data(profile_run: Any) -> None:
    db, server, control = _seeded(profile_run, SCALES["smoke"])
    try:
        stored = db.find(Order.where(Order.id == 4)).result()
        assert stored.tags == ("vip", "t6", "t7")
        assert stored.parcels == (
            Parcel(sku="s1", qty=5),
            Parcel(sku="s2", qty=6),
            Parcel(sku="s3", qty=0),
        )
        for workload in WORKLOADS:
            observed = observe(db, server, workload, {"current": compile_statement(workload)})
            assert observed.parity, (workload.id, observed)
            assert observed.reference["count"], workload.id
    finally:
        control.close()


def test_a_bounded_capture_replays_and_validates(profile_run: Any, tmp_path: Path) -> None:
    inventory = tmp_path / "inventory"
    inventory.mkdir()
    baseline = write_inventory(inventory)
    selection = evidence.select(
        CLASSIFICATIONS,
        tuple(SCALES),
        {
            f"{evidence.ENVIRONMENT_PREFIX}SUITE": "all",
            f"{evidence.ENVIRONMENT_PREFIX}WORKLOADS": ",".join(_SMOKE_WORKLOADS),
            f"{evidence.ENVIRONMENT_PREFIX}SCALE": "smoke",
            f"{evidence.ENVIRONMENT_PREFIX}WARMUPS": "0",
            f"{evidence.ENVIRONMENT_PREFIX}SAMPLES": "2",
            f"{evidence.ENVIRONMENT_PREFIX}EXPLAINS": "1",
        },
        default_scale="focused",
    )
    manifest = capture(profile_run, selection, tmp_path, baseline=baseline, capture_id="smoke")
    evidence.assert_valid(evidence.validate_capture(manifest, CLASSIFICATIONS, FINAL_MATRIX))
    document = evidence.load(manifest)
    paired = [entry for entry in document["workloads"] if entry["pairing"] == "paired"]
    assert paired and all(entry["comparison"] for entry in paired)
    assert Counter(entry["pairing"] for entry in document["workloads"])["current-only"] == 2
    damaged = tmp_path / "damaged"
    damaged.mkdir()
    for path in tmp_path.glob("evidence-smoke-*"):
        (damaged / path.name).write_bytes(path.read_bytes())
    entry = next(entry for entry in document["workloads"] if entry["pairing"] == "current-only")
    samples = damaged / entry["variants"][0]["samples"]
    samples.write_text(samples.read_text(encoding="utf-8").replace('"ordinaryNs"', '"lost"'))
    problems = evidence.validate_capture(damaged / manifest.name, CLASSIFICATIONS, FINAL_MATRIX)
    assert any("does not match its digest" in problem for problem in problems)
    _a_damaged_capture_names_every_defect(manifest, tmp_path / "contradicted")
    _a_current_only_capture_never_reads_its_baseline(manifest, tmp_path / "current-only")


def _copied(manifest: Path, directory: Path) -> Path:
    directory.mkdir()
    for path in manifest.parent.glob(manifest.name.removesuffix("manifest.json") + "*"):
        (directory / path.name).write_bytes(path.read_bytes())
    return directory / manifest.name


def _a_damaged_capture_names_every_defect(manifest: Path, directory: Path) -> None:
    copy = _copied(manifest, directory)
    workloads = evidence.load(copy)["workloads"]
    contradicted, unobserved = workloads[0], workloads[1]
    measured = next(entry for entry in workloads if entry["pairing"] == "current-only")
    variant = measured["variants"][0]
    samples, statement = directory / variant["samples"], directory / variant["statement"]
    content = evidence.load(samples)
    content["ordinaryNs"] = [None for _ in content["ordinaryNs"]]
    content["explain"] = [{"Plan": {}, "Execution Time": None} for _ in content["explain"]]
    samples.write_text(evidence.dumps(content), encoding="utf-8")
    content = evidence.load(statement)
    content["binds"] = []
    statement.write_text(evidence.dumps(content), encoding="utf-8")

    def damage(document: dict[str, Any]) -> None:
        _redigested(document, directory)
        del document["driver"]["files"]
        del document["command"]["environment"]
        del document["protocol"]["order"]
        del document["seed"]["scales"]["smoke"]["distributions"]
        document["selection"].update(campaign="final", suite="nonexistent")
        observations = document["workloads"][0]["observations"]
        observations["public"].update(count=observations["public"]["count"] + 1)
        del document["workloads"][1]["observations"]["statements"]["current"]

    problems = evidence.validate_capture(_rewritten(copy, damage), CLASSIFICATIONS, FINAL_MATRIX)
    label = f"{measured['id']}/smoke/current"
    expected = (
        "the driver files are not recorded",
        "the command environment is not recorded",
        "the protocol order is not recorded",
        "scale smoke records no seeded counts, distributions, and parameters",
        "the selected suite 'nonexistent' is unknown",
        "the selected points are not those of its workloads",
        f"{contradicted['id']}/smoke lacks semantic parity",
        f"{unobserved['id']}/smoke does not observe every variant",
        f"{label} lacks ordinary samples",
        f"{label} holds a sample that is not an executed plan",
    )
    for problem in expected:
        assert problem in problems, problems
    assert any(problem.startswith(f"{label} binds 0 values to ") for problem in problems)


def _a_current_only_capture_never_reads_its_baseline(manifest: Path, directory: Path) -> None:
    copy = _copied(manifest, directory)

    def keep_current_only(document: dict[str, Any]) -> None:
        kept = [entry for entry in document["workloads"] if entry["pairing"] == "current-only"]
        document["workloads"] = kept
        document["selection"]["workloads"] = [entry["id"] for entry in kept]
        document["selection"]["points"] = [[entry["id"], entry["scale"]] for entry in kept]
        document["baseline"] = {"manifest": str(directory / "absent.json"), "digest": "0" * 64}

    evidence.assert_valid(
        evidence.validate_capture(
            _rewritten(copy, keep_current_only), CLASSIFICATIONS, FINAL_MATRIX
        )
    )


def _rewritten(manifest: Path, change: Callable[[dict[str, Any]], None]) -> Path:
    document = evidence.load(manifest)
    change(document)
    manifest.write_text(evidence.dumps(document), encoding="utf-8")
    return manifest


def _redigested(document: dict[str, Any], directory: Path) -> None:
    for file in document["files"]:
        file["sha256"] = evidence.sha256_bytes((directory / file["path"]).read_bytes())


def test_inventory_validation_names_every_defect(tmp_path: Path) -> None:
    manifest = write_inventory(tmp_path)
    statements = tmp_path / "evidence-baseline-reads-statements.json"
    content = evidence.load(statements)
    content["statements"]["reads.dotted-eq"]["binds"] = [{"t": "datetime", "v": "nope"}]
    content["statements"]["reads.guarded-dotted-eq"]["binds"] = []
    del content["statements"]["reads.presence"]
    content["statements"]["reads.match"] = {"sql": "select 1", "binds": []}
    content["parameters"]["reads.repeated-fields"]["objectQuery"] = {}
    statements.write_text(evidence.dumps(content), encoding="utf-8")

    def corrupt(document: dict[str, Any]) -> None:
        _redigested(document, tmp_path)
        document["compiler"]["sha"] = "HEAD"
        del document["driver"]["files"]
        workloads = document["workloads"]
        workloads[:] = [entry for entry in workloads if entry["id"] != "writes.delete-dotted-eq"]
        workloads[0]["pairing"] = "current-only"

    problems = evidence.validate_inventory(_rewritten(manifest, corrupt), CLASSIFICATIONS)
    expected = (
        "the compiler SHA is not recorded",
        "reads.dotted-eq changed pairing",
        "reads.dotted-eq's binds are not losslessly replayable",
        "reads.guarded-dotted-eq binds 0 values to 1 placeholders",
        "reads.repeated-fields has no complete parameters",
        "the driver files are not recorded",
        "reads.presence froze no statement",
        "reads.match is current-only but froze a statement",
        "paired workloads ['writes.delete-dotted-eq'] have no inventory entry",
    )
    for problem in expected:
        assert problem in problems, problems


def test_a_bind_without_a_lossless_spelling_is_refused() -> None:
    with pytest.raises(evidence.EvidenceError, match="naive timestamp"):
        evidence.encode_binds((dt.datetime(2024, 1, 1),))
    with pytest.raises(evidence.EvidenceError, match="no lossless spelling"):
        evidence.encode_binds((object(),))
    carriers = (None, True, 1, 1.5, "a", _MARCH, _MARCH.date(), (1, "b"), [2])
    assert evidence.decode_binds(evidence.encode_binds(carriers)) == carriers


@pytest.mark.parametrize(
    ("variables", "refusal"),
    [
        pytest.param({"SUITE": "everything"}, "is not one of", id="suite"),
        pytest.param({"SUITE": "reads", "CAMPAIGN": "huge"}, "is not 'final'", id="campaign"),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "writes.delete-dotted-eq"},
            "not 'reads'",
            id="suite-member",
        ),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "reads.match,reads.match"}, "repeat", id="repeat"
        ),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "reads.match", "VARIANTS": "baseline"},
            "declares none",
            id="current-only-baseline",
        ),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "reads.match", "VARIANTS": "current,global"},
            "declared by no",
            id="variant",
        ),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "reads.match", "SCALE": "huge"}, "SCALE", id="scale"
        ),
        pytest.param(
            {"SUITE": "reads", "WORKLOADS": "reads.match", "SAMPLES": "0"}, "SAMPLES", id="samples"
        ),
        pytest.param({"MODE": "measure"}, "MODE", id="mode"),
    ],
)
def test_a_capture_selection_is_refused_unless_stated_exactly(
    variables: dict[str, str], refusal: str
) -> None:
    environ = {evidence.ENVIRONMENT_PREFIX + name: value for name, value in variables.items()}
    with pytest.raises(evidence.EvidenceError, match=refusal):
        evidence.selected_mode(environ)
        evidence.select(CLASSIFICATIONS, tuple(SCALES), environ, default_scale="focused")


def test_only_the_final_campaign_selects_a_whole_suite() -> None:
    environ = {
        f"{evidence.ENVIRONMENT_PREFIX}SUITE": "writes",
        f"{evidence.ENVIRONMENT_PREFIX}CAMPAIGN": "final",
    }
    selection = evidence.select(CLASSIFICATIONS, tuple(SCALES), environ, default_scale="focused")
    assert set(selection.workloads) == {w.id for w in WORKLOADS if w.suite == "writes"}
    assert set(_points(selection)) == {
        point for point in FINAL_MATRIX if point[0].startswith("writes.")
    }
