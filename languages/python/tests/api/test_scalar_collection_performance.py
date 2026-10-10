"""PostgreSQL executor cost of scalar-element kind guards and to-one predicates.

Each scalar quantifier's production statement — compiled by the production read
planner from the canonical predicate the Typed query resolves to — is executed
beside an otherwise identical diagnostic statement whose element projection
drops its JSON-kind ``CASE`` guard. Both run over the same canonical stored
arrays, so they must select the same roots, and the public read must select
those roots as well. Every statement is also run under
``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)``: each variant is warmed, then
measured in alternating guarded/unguarded pairs. Multi-hop dotted traversal, a
quantifier reached through a to-one hop, and target-local subtype tests are
measured the same way without a diagnostic twin.

The readings are diagnostic: nothing here asserts a duration. When
``PARALLAX_SCALAR_COLLECTION_PERFORMANCE_OUTPUT`` names a directory, the
statements, plans, and server timings are written there as JSON.
"""

from __future__ import annotations

import json
import os
import re
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, cast

from parallax.core import (
    MANY_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Predicate,
    Rel,
    attr,
    rel,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel, TablePerConcreteSubtype
from parallax.core.predicate import PredicateNode
from parallax.core.predicate import deserialize as deserialize_predicate
from parallax.snapshot import ScopedDatabase, connect
from tests._support.root_ownership import own_root
from tests._support.sql import compile_read

_NS: Final = "scalar.collection.performance"
_OUTPUT_VARIABLE: Final = "PARALLAX_SCALAR_COLLECTION_PERFORMANCE_OUTPUT"
_ROOTS: Final = 128
_SIZES: Final = (0, 8, 128)
_TRAVERSAL_SIZE: Final = 8
_WARMUPS: Final = 3
_PAIRS: Final = 9
_KIND_GUARD: Final = re.compile(r"case when jsonb_typeof\((t\d+)\.value\) = \? then (.+?) end")


class Team(Entity, table="scp_team", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)


class Person(Entity, table="scp_person", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    team_id: Attr[int | None]
    labels: Attr[tuple[str, ...]]
    team: Rel[Team | None] = rel(cardinality=MANY_TO_ONE, join=("team_id", "id"))


class Vehicle(Entity, namespace=_NS, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)


class Car(Vehicle, table="scp_car", namespace=_NS, inheritance=ConcreteSubtype()):
    seats: Attr[int | None] = attr(type=Int32)


class Bike(Vehicle, table="scp_bike", namespace=_NS, inheritance=ConcreteSubtype()):
    gears: Attr[int | None] = attr(type=Int32)


class Holder(Entity, table="scp_holder", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int | None]
    vehicle_id: Attr[int | None]
    ints: Attr[tuple[int, ...]]
    texts: Attr[tuple[str, ...]]
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=12, scale=2)
    owner: Rel[Person | None] = rel(cardinality=MANY_TO_ONE, join=("owner_id", "id"))
    vehicle: Rel[Vehicle | None] = rel(cardinality=MANY_TO_ONE, join=("vehicle_id", "id"))


_MODEL: Final = DomainModel(Team, Person, Vehicle, Car, Bike, Holder)
_HOLDER: Final = Holder.identity.canonical

type ElementType = Literal["integer", "string", "decimal"]
type Workload = Literal["existential-early-match", "universal-full-scan"]
_TYPES: Final[tuple[ElementType, ...]] = ("integer", "string", "decimal")
_WORKLOADS: Final[tuple[Workload, ...]] = ("existential-early-match", "universal-full-scan")
_MEMBERS: Final[Mapping[ElementType, str]] = {
    "integer": "ints",
    "string": "texts",
    "decimal": "amounts",
}


def _elements(size: int) -> dict[ElementType, tuple[object, ...]]:
    return {
        "integer": tuple(range(1, size + 1)),
        "string": tuple(f"v{position:04d}" for position in range(1, size + 1)),
        "decimal": tuple(Decimal(f"{position}.00") for position in range(1, size + 1)),
    }


_FIRST: Final[Mapping[ElementType, tuple[object, object]]] = {
    "integer": (1, 1),
    "string": ("v0001", "v0001"),
    "decimal": ("1.00", Decimal("1.00")),
}
"""Each type's first stored element, as a Wire literal and as a Typed operand."""

_BELOW: Final[Mapping[ElementType, tuple[object, object]]] = {
    "integer": (0, 0),
    "string": ("v", "v"),
    "decimal": ("0.00", Decimal("0.00")),
}
"""A bound every stored element of each type exceeds."""


def _canonical(element_type: ElementType, workload: Workload) -> PredicateNode:
    path = f"{_HOLDER}.{_MEMBERS[element_type]}"
    if workload == "existential-early-match":
        where = {"eq": {"value": _FIRST[element_type][0]}}
        return deserialize_predicate({"any": {"path": path, "where": where}})
    where = {"greaterThan": {"value": _BELOW[element_type][0]}}
    return deserialize_predicate({"all": {"path": path, "where": where}})


def _typed(element_type: ElementType, workload: Workload) -> Predicate[Any]:
    collection = getattr(Holder, _MEMBERS[element_type])
    if workload == "existential-early-match":
        return collection.any(collection.element == _FIRST[element_type][1])
    return collection.all(collection.element > _BELOW[element_type][1])


@dataclass(frozen=True, slots=True)
class _Statement:
    sql: str
    binds: tuple[object, ...]


def _production(model: Metamodel, predicate: PredicateNode) -> _Statement:
    target = next(entity for entity in model.entities if entity.identity == Holder.identity)
    compiled = compile_read(predicate, model, POSTGRES, target, result_form="instance")
    return _Statement(compiled.statement.sql, tuple(compiled.statement.binds))


def _unguarded(statement: _Statement) -> _Statement:
    """``statement`` with its element projection's kind guard removed: the
    projection itself stays, and the guard's kind bind is dropped."""
    found = _KIND_GUARD.search(statement.sql)
    assert found is not None, statement.sql
    kind_bind = statement.sql[: found.start()].count("?")
    binds = (*statement.binds[:kind_bind], *statement.binds[kind_bind + 1 :])
    sql = f"{statement.sql[: found.start()]}{found.group(2)}{statement.sql[found.end() :]}"
    assert _KIND_GUARD.search(sql) is None, sql
    return _Statement(sql, binds)


class _Server:
    """The control session statements and their plans are executed on."""

    def __init__(self, control: Any) -> None:
        self._control = control

    def ids(self, statement: _Statement) -> frozenset[int]:
        rows = self._control.execute(POSTGRES.to_driver_sql(statement.sql), statement.binds)
        return frozenset(int(row[0]) for row in rows)

    def explained(self, statement: _Statement) -> Mapping[str, Any]:
        sql = POSTGRES.to_driver_sql(f"explain (analyze, buffers, format json) {statement.sql}")
        rows = self._control.execute(sql, statement.binds)
        document = rows[0][0]
        plans = cast(
            "list[Mapping[str, Any]]",
            json.loads(document) if isinstance(document, str) else document,
        )
        return plans[0]

    def analyze(self) -> None:
        for table in ("scp_team", "scp_person", "scp_car", "scp_bike", "scp_holder"):
            self._control.execute_write(f"analyze {table}", [])


def _topology(plan: Mapping[str, Any]) -> list[str]:
    node = cast("Mapping[str, Any]", plan["Plan"]) if "Plan" in plan else plan
    spelled = str(node["Node Type"])
    for name in ("Relation Name", "Function Name", "Subplan Name"):
        if name in node:
            spelled += f"[{node[name]}]"
    children = cast("Sequence[Mapping[str, Any]]", node.get("Plans", ()))
    return [spelled, *(entry for child in children for entry in _topology(child))]


def _summary(samples: Sequence[float]) -> dict[str, float]:
    return {
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
    }


def _reading(plans: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    executed = [float(plan["Execution Time"]) for plan in plans]
    planned = [float(plan["Planning Time"]) for plan in plans]
    root = cast("Mapping[str, Any]", plans[-1]["Plan"])
    return {
        "executionMs": executed,
        "planningMs": planned,
        "execution": _summary(executed),
        "planning": _summary(planned),
        "sharedHitBlocks": root.get("Shared Hit Blocks"),
        "sharedReadBlocks": root.get("Shared Read Blocks"),
        "topology": _topology(plans[-1]),
        "plan": plans[-1],
    }


def _measure_pair(server: _Server, guarded: _Statement, unguarded: _Statement) -> dict[str, object]:
    for _ in range(_WARMUPS):
        server.explained(guarded)
        server.explained(unguarded)
    guarded_plans: list[Mapping[str, Any]] = []
    unguarded_plans: list[Mapping[str, Any]] = []
    for pair in range(_PAIRS):
        if pair % 2 == 0:
            guarded_plans.append(server.explained(guarded))
            unguarded_plans.append(server.explained(unguarded))
        else:
            unguarded_plans.append(server.explained(unguarded))
            guarded_plans.append(server.explained(guarded))
    with_guard = _reading(guarded_plans)
    without_guard = _reading(unguarded_plans)
    guarded_median = cast("dict[str, float]", with_guard["execution"])["median"]
    unguarded_median = cast("dict[str, float]", without_guard["execution"])["median"]
    overhead = guarded_median - unguarded_median
    return {
        "guarded": {
            "sql": guarded.sql,
            "binds": [repr(bind) for bind in guarded.binds],
            **with_guard,
        },
        "unguarded": {
            "sql": unguarded.sql,
            "binds": [repr(bind) for bind in unguarded.binds],
            **without_guard,
        },
        "overheadMs": overhead,
        "overheadRelative": overhead / unguarded_median if unguarded_median else None,
        "sameTopology": with_guard["topology"] == without_guard["topology"],
    }


def _measure_alone(server: _Server, statement: _Statement) -> dict[str, object]:
    for _ in range(_WARMUPS):
        server.explained(statement)
    plans = [server.explained(statement) for _ in range(_PAIRS)]
    return {
        "sql": statement.sql,
        "binds": [repr(bind) for bind in statement.binds],
        **_reading(plans),
    }


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _owner_of(key: int) -> int | None:
    return None if key % 10 == 0 else key % 16 + 1


def _seed(db: ScopedDatabase, size: int) -> None:
    elements = _elements(size)

    def body(tx: Any) -> None:
        for key in range(1, 5):
            tx.insert(Team(id=key, name=f"t{key}"))
        for key in range(1, 17):
            labels = ("x",) if key % 2 == 0 else ()
            tx.insert(Person(id=key, team_id=key % 4 + 1, labels=labels))
        for key in range(1, 5):
            tx.insert(Car(id=key, seats=key))
        for key in range(5, 9):
            tx.insert(Bike(id=key, gears=key))
        for key in range(1, _ROOTS + 1):
            tx.insert(
                Holder(
                    id=key,
                    owner_id=_owner_of(key),
                    vehicle_id=key % 8 + 1,
                    ints=cast("tuple[int, ...]", elements["integer"]),
                    texts=cast("tuple[str, ...]", elements["string"]),
                    amounts=cast("tuple[Decimal, ...]", elements["decimal"]),
                )
            )

    db.transact(body)


def _public_ids(db: ScopedDatabase, predicate: Predicate[Any]) -> frozenset[int]:
    return frozenset(
        cast("Any", holder).id for holder in db.find(Holder.where(predicate)).results()
    )


_EVERY: Final = frozenset(range(1, _ROOTS + 1))


def _expected(size: int, workload: Workload) -> frozenset[int]:
    if workload == "existential-early-match":
        return _EVERY if size else frozenset()
    return _EVERY


@dataclass(frozen=True, slots=True)
class _Traversal:
    name: str
    canonical: Callable[[], PredicateNode]
    typed: Callable[[], Predicate[Any]]
    expected: frozenset[int]


def _traversals() -> tuple[_Traversal, ...]:
    owned = {key: _owner_of(key) for key in range(1, _ROOTS + 1)}
    vehicle = {key: key % 8 + 1 for key in range(1, _ROOTS + 1)}
    return (
        _Traversal(
            "dotted-two-hops",
            lambda: deserialize_predicate(
                {"eq": {"path": f"{_HOLDER}.owner.team.name", "value": "t1"}}
            ),
            lambda: Holder.owner.team.name == "t1",
            frozenset(
                key for key, owner in owned.items() if owner is not None and owner % 4 + 1 == 1
            ),
        ),
        _Traversal(
            "quantifier-through-to-one",
            lambda: deserialize_predicate(
                {"any": {"path": f"{_HOLDER}.owner.labels", "where": {"eq": {"value": "x"}}}}
            ),
            lambda: Holder.owner.labels.any(Holder.owner.labels.element == "x"),
            frozenset(key for key, owner in owned.items() if owner is not None and owner % 2 == 0),
        ),
        _Traversal(
            "target-local-subtype-membership",
            lambda: deserialize_predicate(
                {
                    "narrow": {
                        "path": f"{_HOLDER}.vehicle",
                        "to": [Car.identity.canonical],
                        "operand": {"true": {}},
                    }
                }
            ),
            lambda: Holder.vehicle.is_a(Car),
            frozenset(key for key, target in vehicle.items() if target <= 4),
        ),
        _Traversal(
            "target-local-narrow-operand",
            lambda: deserialize_predicate(
                {
                    "narrow": {
                        "path": f"{_HOLDER}.vehicle",
                        "to": [Car.identity.canonical],
                        "operand": {"greaterThan": {"path": "seats", "value": 2}},
                    }
                }
            ),
            lambda: Holder.vehicle.is_a(Car, where=Car.seats > 2),
            frozenset(key for key, target in vehicle.items() if 2 < target <= 4),
        ),
    )


def test_kind_guards_and_to_one_predicates_select_the_same_roots_on_the_server(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    model = model_of(_MODEL)
    control = profile_run.control()
    server = _Server(control)
    guards: list[dict[str, object]] = []
    traversals: list[dict[str, object]] = []
    try:
        for size in _SIZES:
            if size != _SIZES[0]:
                db = _served(profile_run)
            _seed(db, size)
            server.analyze()
            for element_type in _TYPES:
                for workload in _WORKLOADS:
                    guarded = _production(model, _canonical(element_type, workload))
                    unguarded = _unguarded(guarded)
                    expected = _expected(size, workload)
                    assert server.ids(guarded) == expected
                    assert server.ids(unguarded) == expected
                    assert _public_ids(db, _typed(element_type, workload)) == expected
                    guards.append(
                        {
                            "elementType": element_type,
                            "size": size,
                            "workload": workload,
                            "roots": _ROOTS,
                            "expectedRoots": len(expected),
                            **_measure_pair(server, guarded, unguarded),
                        }
                    )
            if size != _TRAVERSAL_SIZE:
                continue
            for traversal in _traversals():
                statement = _production(model, traversal.canonical())
                assert server.ids(statement) == traversal.expected
                assert _public_ids(db, traversal.typed()) == traversal.expected
                traversals.append(
                    {
                        "name": traversal.name,
                        "roots": _ROOTS,
                        "expectedRoots": len(traversal.expected),
                        **_measure_alone(server, statement),
                    }
                )
    finally:
        control.close()
    output = os.environ.get(_OUTPUT_VARIABLE)
    if output:
        document = {
            "server": _server_settings(profile_run),
            "warmups": _WARMUPS,
            "pairs": _PAIRS,
            "guards": guards,
            "traversals": traversals,
        }
        Path(output, "scalar-collection-performance.json").write_text(
            json.dumps(document, indent=1, sort_keys=True, default=str), encoding="utf-8"
        )


def _server_settings(profile_run: Any) -> dict[str, str]:
    control = profile_run.control()
    try:
        return {
            name: str(control.execute(f"show {name}", [])[0][0])
            for name in (
                "server_version",
                "shared_buffers",
                "work_mem",
                "jit",
                "max_parallel_workers_per_gather",
                "random_page_cost",
            )
        }
    finally:
        control.close()
