# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import gc
import threading
import time
import types
import weakref
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from typing import Any, Final, Literal, cast

import pytest

from parallax.conformance.dormant_position_models import DORMANT_POSITION_COLUMNS
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core import continuation, deep_fetch
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.navigate import (
    NoRootSelections,
    PropagatedRootSelections,
    resolve_temporal_visibility,
)
from parallax.core.object_query import deserialize
from parallax.core.object_query._resolved import ContinuationCoordinate, ResolvedObjectQuery
from parallax.core.predicate._execution_values import ExecutionValueSources
from parallax.core.predicate._resolved import ResolvedAnd, ResolvedComparison
from parallax.core.read_delivery import _read_plan
from parallax.core.read_delivery._delivery import find
from parallax.core.read_delivery._page_reader import EMPTY_PAGE_ORIGIN_COLLECTOR
from parallax.core.read_delivery._read_plan import EMPTY_READ, EmptyRead, ReadPlanCache
from parallax.core.read_delivery._row_converter import ReadRowConverter
from parallax.core.sql_gen import _compile as _compile_module
from parallax.core.sql_gen._compile import (
    CompiledRead,
    CompiledTemplate,
    compile_read,
    compile_write_predicate,
)
from parallax.core.sql_gen._context import LoweredStatement, StatementBuilder
from parallax.core.sql_gen._inheritance import ReadResultContract
from parallax.core.unit_work import Concurrency
from parallax.descriptor._records import Entity as DescriptorEntity
from parallax.descriptor._records import Inheritance
from parallax.snapshot import Database
from tests._support.db_port import Read, ScriptedAdapter, Transact
from tests.unit import _read_projection_support as projection_support
from tests.unit._corpus_model_support import formed, records
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._transact_support import db_for

_META = model_of(ORDERS_MODEL)
_MODEL = CatalogedModel(_META)


def _reaches(root: object, target: object) -> bool:
    return _reaching(root, lambda value: value is target)


def _reaching(root: object, found: Callable[[object], bool]) -> bool:
    atomic = (str, bytes, int, float, bool, type(None), type, types.ModuleType)
    pending = [root]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if found(value):
            return True
        identity = id(value)
        if identity in seen or isinstance(value, atomic):
            continue
        seen.add(identity)
        if isinstance(value, types.FunctionType):
            for cell in value.__closure__ or ():
                with contextlib.suppress(ValueError):
                    pending.append(cell.cell_contents)
            continue
        pending.extend(gc.get_referents(value))
    return False


def _query(value: object = 1) -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize(
            {
                "target": "Order",
                "predicate": {"eq": {"path": "Order.id", "value": value}},
            }
        ),
        model=_META,
        form="graph",
    )


def _name_query(value: str) -> ResolvedObjectQuery:
    query = resolve_read_query(
        deserialize(
            {
                "target": "Order",
                "predicate": {"eq": {"path": "Order.name", "value": value}},
            }
        ),
        model=_META,
        form="graph",
    )
    # Decoding yields a plain `str`; the caller's own carrier is kept instead,
    # so a probe observes exactly what the key and the plan retain of it.
    assert isinstance(query.predicate, ResolvedComparison)
    return replace(query, predicate=replace(query.predicate, value=value))


def _plan(
    planner: ReadPlanCache,
    query: ResolvedObjectQuery,
    *,
    edition: str = "edition-a",
    model: CatalogedModel = _MODEL,
    dialect: Dialect = POSTGRES,
    result_form: Literal["row", "instance"] = "instance",
    preference: Concurrency | None = None,
) -> _read_plan.ReadPlan:
    return planner.plan(
        edition=edition,
        model=model,
        dialect=dialect,
        query=query,
        result_form=result_form,
        preference=preference,
    )


def _forbidden_concrete_root(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("a cached root compiles as a template")


def _root(plan: _read_plan.ReadPlan) -> tuple[CompiledRead, ReadRowConverter]:
    root = plan.root_read()
    assert not isinstance(root, EmptyRead)
    return root


def _shares_preparation(rendered: _read_plan.ReadPlan, prepared: _read_plan.ReadPlan) -> bool:
    """Whether ``rendered`` reuses everything ``prepared`` prepared but its root."""
    return (
        _root(rendered)[1] is _root(prepared)[1]
        and rendered._schema is prepared._schema
        and rendered._fetches is prepared._fetches
        and rendered._fetch_rows is prepared._fetch_rows
        and rendered._correlations is prepared._correlations
        and rendered._query_plan is prepared._query_plan
    )


def test_different_query_values_share_one_read_plan_but_result_forms_do_not() -> None:
    planner = ReadPlanCache()

    first = _plan(planner, _query(1))
    other_value = _plan(planner, _query(2))
    row_form = _plan(planner, _query(1), result_form="row")

    assert _shares_preparation(other_value, first)
    assert (_root(first)[0].statement.binds, _root(other_value)[0].statement.binds) == ((1,), (2,))
    assert _root(row_form)[1] is not _root(first)[1]
    assert planner._statistics() == _read_plan._ReadPlanCacheStatistics(16, 2, 1, 2, 0)


def _match_query(name: str) -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize(
            {
                "target": "OrderItem",
                "predicate": {
                    "exists": {
                        "path": "OrderItem.order",
                        "where": {"eq": {"path": "name", "value": name}},
                    }
                },
            }
        ),
        model=_META,
        form="graph",
    )


def test_matches_with_different_operands_on_one_relationship_share_one_template() -> None:
    planner = ReadPlanCache()

    ada = _plan(planner, _match_query("Ada"))
    bob = _plan(planner, _match_query("Bob"))

    assert _shares_preparation(bob, ada)
    (ada_read, _), (bob_read, _) = _root(ada), _root(bob)
    assert ada_read.statement.sql == bob_read.statement.sql
    assert (ada_read.statement.binds, bob_read.statement.binds) == (("Ada",), ("Bob",))
    assert planner._statistics() == _read_plan._ReadPlanCacheStatistics(16, 1, 1, 1, 0)


def test_equal_dialect_values_with_distinct_identities_do_not_share_a_read_plan() -> None:
    planner = ReadPlanCache()
    equivalent_dialect = replace(POSTGRES)

    first = _plan(planner, _query(), dialect=POSTGRES)
    second = _plan(planner, _query(), dialect=equivalent_dialect)

    assert equivalent_dialect == POSTGRES
    assert equivalent_dialect is not POSTGRES
    assert second is not first
    assert planner._statistics().misses == 2


def test_operand_key_material_keeps_exact_types_and_decimal_exponents_but_not_values() -> None:
    operand_key = cast("Callable[[object], object]", vars(_read_plan)["_operand_key"])

    assert operand_key(True) != operand_key(1)
    assert operand_key(1) != operand_key(1.0)
    assert operand_key(Decimal("1.5")) != operand_key(Decimal("1.50"))
    assert operand_key(Decimal("1.50")) == operand_key(Decimal("2.75"))
    assert operand_key(1) == operand_key(2)
    assert operand_key("1") == operand_key("2")


_ORDERS = corpus_model("orders")
_CUSTOMER = corpus_model("customer")
_ANIMAL = corpus_model("animal")
_BALANCE = corpus_model("balance")
_LATEST: dict[str, object] = {"transaction-time": {"asOf": "latest"}}


def _resolved_key(meta: Metamodel, document: Mapping[str, object]) -> object:
    query_key = cast("Callable[[object], object]", vars(_read_plan)["_query_key"])
    return query_key(resolve_read_query(deserialize(dict(document)), model=meta, form="graph"))


def _order_query(predicate: Mapping[str, object], **clauses: object) -> dict[str, object]:
    return {"target": "Order", "predicate": predicate} | clauses


def _customer_query(predicate: Mapping[str, object], **clauses: object) -> dict[str, object]:
    return {"target": "Customer", "predicate": predicate} | clauses


def _animal_query(predicate: Mapping[str, object], **clauses: object) -> dict[str, object]:
    return {"target": "Animal", "predicate": predicate} | clauses


def _balance_query(temporal: Mapping[str, object]) -> dict[str, object]:
    return {"target": "Balance", "predicate": {"true": {}}, "temporal": temporal}


_PHONE_HOME = {"eq": {"path": "type", "value": "home"}}
_ID_ONE = {"eq": {"path": "Order.id", "value": 1}}
_NAMED_A = {"eq": {"path": "Order.name", "value": "A"}}
_NAMED_LOCAL_A = {"eq": {"path": "name", "value": "A"}}
_ACTIVE_LOCAL = {"eq": {"path": "active", "value": True}}

# Pairs of resolved queries that compile to different SQL or binds: each pair
# differs in exactly one SQL-relevant fact, so a key that ignored it would share
# one cached plan between them.
_DISTINCT_QUERIES: tuple[tuple[str, Metamodel, dict[str, object], dict[str, object]], ...] = (
    ("constant", _ORDERS, _order_query({"true": {}}), _order_query({"false": {}})),
    (
        "comparison-operator",
        _ORDERS,
        _order_query({"eq": {"path": "Order.qty", "value": 1}}),
        _order_query({"lessThan": {"path": "Order.qty", "value": 1}}),
    ),
    (
        "comparison-member",
        _ORDERS,
        _order_query({"eq": {"path": "Order.qty", "value": 1}}),
        _order_query({"eq": {"path": "Order.id", "value": 1}}),
    ),
    (
        "range-member",
        _ORDERS,
        _order_query({"between": {"path": "Order.qty", "lower": 1, "upper": 5}}),
        _order_query({"between": {"path": "Order.id", "lower": 1, "upper": 5}}),
    ),
    (
        "membership-width",
        _ORDERS,
        _order_query({"in": {"path": "Order.id", "values": [1, 2]}}),
        _order_query({"in": {"path": "Order.id", "values": [1, 2, 3]}}),
    ),
    (
        "affix-escape",
        _ORDERS,
        _order_query({"startsWith": {"path": "Order.name", "value": "ab"}}),
        _order_query({"startsWith": {"path": "Order.name", "value": "a_b"}}),
    ),
    (
        "affix-operator",
        _ORDERS,
        _order_query({"startsWith": {"path": "Order.name", "value": "ab"}}),
        _order_query({"endsWith": {"path": "Order.name", "value": "ab"}}),
    ),
    (
        "operand-position",
        _ORDERS,
        _order_query({"and": {"operands": [_ID_ONE, _NAMED_A]}}),
        _order_query({"and": {"operands": [_NAMED_A, _ID_ONE]}}),
    ),
    (
        "membership-polarity",
        _ORDERS,
        _order_query({"in": {"path": "Order.id", "values": [1, 2]}}),
        _order_query({"notIn": {"path": "Order.id", "values": [1, 2]}}),
    ),
    (
        "string-folding",
        _ORDERS,
        _order_query({"startsWith": {"path": "Order.name", "value": "A"}}),
        _order_query({"startsWith": {"path": "Order.name", "value": "A", "caseInsensitive": True}}),
    ),
    (
        "null-check",
        _CUSTOMER,
        _customer_query({"isNull": {"path": "Customer.address.geo.elevation"}}),
        _customer_query({"isNotNull": {"path": "Customer.address.geo.elevation"}}),
    ),
    (
        "boolean-connective",
        _ORDERS,
        _order_query({"and": {"operands": [_ID_ONE, _NAMED_A]}}),
        _order_query({"or": {"operands": [_ID_ONE, _NAMED_A]}}),
    ),
    (
        "grouping",
        _ORDERS,
        _order_query({"not": {"operand": _ID_ONE}}),
        _order_query({"group": {"operand": _ID_ONE}}),
    ),
    (
        "predicate-narrowing",
        _ANIMAL,
        _animal_query({"narrow": {"to": ["Dog"], "operand": {"true": {}}}}),
        _animal_query({"narrow": {"to": ["Cat"], "operand": {"true": {}}}}),
    ),
    (
        "quantifier-kind",
        _CUSTOMER,
        _customer_query({"any": {"path": "Customer.address.phones"}}),
        _customer_query({"none": {"path": "Customer.address.phones"}}),
    ),
    (
        "universal-kind",
        _CUSTOMER,
        _customer_query({"any": {"path": "Customer.address.phones", "where": _PHONE_HOME}}),
        _customer_query({"all": {"path": "Customer.address.phones", "where": _PHONE_HOME}}),
    ),
    (
        "quantifier-scope",
        _CUSTOMER,
        _customer_query({"any": {"path": "Customer.address.phones"}}),
        _customer_query({"any": {"path": "Customer.address.phones", "where": _PHONE_HOME}}),
    ),
    (
        "relationship-quantifier-kind",
        _CUSTOMER,
        _customer_query({"any": {"path": "Customer.locations"}}),
        _customer_query({"none": {"path": "Customer.locations"}}),
    ),
    (
        "relationship-quantifier-interior",
        _CUSTOMER,
        _customer_query({"any": {"path": "Customer.locations"}}),
        _customer_query(
            {
                "any": {
                    "path": "Customer.locations",
                    "where": {"eq": {"path": "label", "value": "home"}},
                }
            }
        ),
    ),
    (
        "presence-polarity",
        _CUSTOMER,
        _customer_query({"exists": {"path": "Customer.address.geo"}}),
        _customer_query({"notExists": {"path": "Customer.address.geo"}}),
    ),
    (
        "match-operand",
        _ORDERS,
        {
            "target": "OrderItem",
            "predicate": {"exists": {"path": "OrderItem.order", "where": _NAMED_LOCAL_A}},
        },
        {
            "target": "OrderItem",
            "predicate": {"exists": {"path": "OrderItem.order", "where": _ACTIVE_LOCAL}},
        },
    ),
    (
        "match-versus-presence",
        _ORDERS,
        {"target": "OrderItem", "predicate": {"exists": {"path": "OrderItem.order"}}},
        {
            "target": "OrderItem",
            "predicate": {"exists": {"path": "OrderItem.order", "where": _NAMED_LOCAL_A}},
        },
    ),
    (
        "reached-position",
        _ORDERS,
        {
            "target": "OrderStatus",
            "predicate": {"eq": {"path": "OrderStatus.order.name", "value": "A"}},
        },
        {
            "target": "OrderStatus",
            "predicate": {"eq": {"path": "OrderStatus.orderItem.order.name", "value": "A"}},
        },
    ),
    (
        "element-operator",
        corpus_model("predicate-collections"),
        {
            "target": "Basket",
            "predicate": {"any": {"path": "Basket.tags", "where": {"eq": {"value": "a"}}}},
        },
        {
            "target": "Basket",
            "predicate": {"any": {"path": "Basket.tags", "where": {"notEq": {"value": "a"}}}},
        },
    ),
    (
        "narrowed-target",
        _ANIMAL,
        _animal_query({"narrow": {"to": ["Dog"], "operand": {"true": {}}}}),
        _animal_query(
            {"narrow": {"path": "Animal.owner", "to": ["Person"], "operand": {"true": {}}}}
        ),
    ),
    (
        "temporal-selection",
        _BALANCE,
        _balance_query(_LATEST),
        _balance_query({"transaction-time": {"history": {}}}),
    ),
    (
        "temporal-coordinate",
        _BALANCE,
        _balance_query({"transaction-time": {"asOf": "2024-06-15T00:00:00.000000Z"}}),
        _balance_query({"transaction-time": {"asOf": "2024-06-16T00:00:00.000000Z"}}),
    ),
    (
        "temporal-window",
        _BALANCE,
        _balance_query(
            {
                "transaction-time": {
                    "asOfRange": {
                        "start": "2024-06-15T00:00:00.000000Z",
                        "end": "2024-07-01T00:00:00.000000Z",
                    }
                }
            }
        ),
        _balance_query(
            {
                "transaction-time": {
                    "asOfRange": {
                        "start": "2024-06-15T00:00:00.000000Z",
                        "end": "2024-07-02T00:00:00.000000Z",
                    }
                }
            }
        ),
    ),
    (
        "ordering",
        _ORDERS,
        _order_query({"true": {}}, orderBy=[{"attr": "Order.id", "direction": "asc"}]),
        _order_query({"true": {}}, orderBy=[{"attr": "Order.id", "direction": "desc"}]),
    ),
    (
        "includes",
        _CUSTOMER,
        _customer_query({"true": {}}),
        _customer_query({"true": {}}, includes=[{"segments": [{"rel": "Customer.locations"}]}]),
    ),
    (
        "result-narrowing",
        _ANIMAL,
        _animal_query({"true": {}}),
        _animal_query({"true": {}}, narrowTo=["Dog"]),
    ),
)


@pytest.mark.parametrize(
    ("meta", "first", "second"),
    [case[1:] for case in _DISTINCT_QUERIES],
    ids=[case[0] for case in _DISTINCT_QUERIES],
)
def test_query_keys_separate_every_sql_relevant_resolved_fact(
    meta: Metamodel, first: dict[str, object], second: dict[str, object]
) -> None:
    key = _resolved_key(meta, first)

    assert key == _resolved_key(meta, first)
    assert hash(key) == hash(_resolved_key(meta, first))
    assert key != _resolved_key(meta, second)


# Pairs of resolved queries differing only in execution values: one template
# renders both.
_SHARED_QUERIES: tuple[tuple[str, Metamodel, dict[str, object], dict[str, object]], ...] = (
    (
        "comparison-value",
        _ORDERS,
        _order_query({"eq": {"path": "Order.qty", "value": 1}}),
        _order_query({"eq": {"path": "Order.qty", "value": 2}}),
    ),
    (
        "range-bound",
        _ORDERS,
        _order_query({"between": {"path": "Order.qty", "lower": 1, "upper": 5}}),
        _order_query({"between": {"path": "Order.qty", "lower": 1, "upper": 6}}),
    ),
    (
        "membership-values",
        _ORDERS,
        _order_query({"in": {"path": "Order.id", "values": [1, 2]}}),
        _order_query({"in": {"path": "Order.id", "values": [1, 3]}}),
    ),
    (
        "unescaped-affixes",
        _ORDERS,
        _order_query({"startsWith": {"path": "Order.name", "value": "ab"}}),
        _order_query({"startsWith": {"path": "Order.name", "value": "cd"}}),
    ),
    (
        "escaped-affixes",
        _ORDERS,
        _order_query({"contains": {"path": "Order.name", "value": "a_b"}}),
        _order_query({"contains": {"path": "Order.name", "value": "c%d"}}),
    ),
    (
        "verbatim-patterns",
        _ORDERS,
        _order_query({"like": {"path": "Order.name", "value": "ab"}}),
        _order_query({"like": {"path": "Order.name", "value": "c_%"}}),
    ),
    (
        "element-operand",
        corpus_model("predicate-collections"),
        {
            "target": "Basket",
            "predicate": {"any": {"path": "Basket.tags", "where": {"eq": {"value": "a"}}}},
        },
        {
            "target": "Basket",
            "predicate": {"any": {"path": "Basket.tags", "where": {"eq": {"value": "b"}}}},
        },
    ),
)


@pytest.mark.parametrize(
    ("meta", "first", "second"),
    [case[1:] for case in _SHARED_QUERIES],
    ids=[case[0] for case in _SHARED_QUERIES],
)
def test_query_keys_share_queries_differing_only_in_execution_values(
    meta: Metamodel, first: dict[str, object], second: dict[str, object]
) -> None:
    assert _resolved_key(meta, first) == _resolved_key(meta, second)


def test_equal_quantifiers_key_alike_however_they_were_spelled() -> None:
    qualified = _customer_query(
        {"any": {"path": "parallax.compatibility.Customer.address.phones", "where": _PHONE_HOME}}
    )
    bare = _customer_query({"any": {"path": "Customer.address.phones", "where": _PHONE_HOME}})

    assert _resolved_key(_CUSTOMER, qualified) == _resolved_key(_CUSTOMER, bare)


class _HashCountingType(type):
    """Counts hashes of the classes it makes, which an operand key holds."""

    hashes = 0

    def __hash__(cls) -> int:
        _HashCountingType.hashes += 1
        return type.__hash__(cls)


class _HashCountingString(str, metaclass=_HashCountingType):
    pass


def _key(query: ResolvedObjectQuery, **fields: Any) -> _read_plan._ReadPlanKey:
    values: dict[str, Any] = {
        "edition": "edition-a",
        "model": _MODEL,
        "dialect": POSTGRES,
        "query": query,
        "result_form": "instance",
        "preference": None,
    }
    return _read_plan._read_plan_key(**(values | fields))


def _counting_query_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    query_key = cast("Callable[[object], object]", vars(_read_plan)["_query_key"])
    counts = {"projected": 0}

    def counting(value: object) -> object:
        counts["projected"] += 1
        return query_key(value)

    monkeypatch.setattr(_read_plan, "_query_key", counting)
    return counts


def _counting_family_comparisons(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    same_family = _read_plan._ReadPlanKey.same_family
    verdicts: list[bool] = []

    def counting(self: _read_plan._ReadPlanKey, other: _read_plan._ReadPlanKey) -> bool:
        verdict = same_family(self, other)
        verdicts.append(verdict)
        return verdict

    monkeypatch.setattr(_read_plan._ReadPlanKey, "same_family", counting)
    return verdicts


def test_a_read_plan_key_hashes_its_query_key_once() -> None:
    literal = _HashCountingString("counted")
    selected = _name_query(literal)
    _HashCountingType.hashes = 0

    key = _key(selected)
    constructed = _HashCountingType.hashes
    lookups = {key: 1}
    for _ in range(4):
        assert lookups[key] == 1
        hash(key)

    assert constructed == 1
    assert _HashCountingType.hashes == 1


def test_same_family_ignores_only_the_delivery_discriminator() -> None:
    pages = continuation.plan(_query(), _META)
    unpaged = _key(_query())
    first = _key(pages.first(limit=3))
    after = _key(pages.after(ContinuationCoordinate((1,)), limit=3))
    null_after = _key(pages.after(ContinuationCoordinate((None,)), limit=3))

    assert len({first, after, null_after}) == 3
    assert first.same_family(after)
    assert after.same_family(null_after)
    assert null_after.same_family(first)
    assert unpaged.same_family(_key(_query()))
    assert unpaged == _key(_query(2))
    for distinct in (
        _key(_name_query("order-1")),
        _key(_query(), edition="edition-b"),
        _key(_query(), model=CatalogedModel(_META)),
        _key(_query(), dialect=replace(POSTGRES)),
        _key(_query(), result_form="row"),
        _key(_query(), preference="locking"),
    ):
        assert not unpaged.same_family(distinct)
        assert not distinct.same_family(unpaged)


def test_an_unpaged_query_keeps_its_authored_limit_in_its_family() -> None:
    def selected(**clauses: object) -> ResolvedObjectQuery:
        authored = {"target": "Order", "predicate": {"eq": {"path": "Order.id", "value": 1}}}
        return resolve_read_query(deserialize(authored | clauses), model=_META, form="graph")

    assert not _key(selected(limit=3)).same_family(_key(selected()))
    assert not _key(selected(limit=3)).same_family(_key(selected(limit=5)))
    assert _key(selected(limit=3)) == _key(selected(limit=3))


@pytest.mark.parametrize("paged", [False, True])
def test_hits_and_cold_builds_project_the_resolved_query_once_per_lookup(
    monkeypatch: pytest.MonkeyPatch,
    paged: bool,
) -> None:
    selected = (
        continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)
        if paged
        else _query()
    )
    counts = _counting_query_keys(monkeypatch)
    cache = ReadPlanCache()

    _plan(cache, selected)
    assert counts["projected"] == 1
    _plan(cache, selected)
    assert counts["projected"] == 2
    assert cache._statistics().hits == 1


def test_a_warm_hit_hashes_its_query_key_only_at_key_construction() -> None:
    cache = ReadPlanCache()
    _plan(cache, _name_query(_HashCountingString("counted")))
    warm = _name_query(_HashCountingString("counted"))
    _HashCountingType.hashes = 0

    _plan(cache, warm)

    assert cache._statistics().hits == 1
    assert _HashCountingType.hashes == 1


def test_only_an_elected_builder_scans_for_its_family_most_recent_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verdicts = _counting_family_comparisons(monkeypatch)
    cache = ReadPlanCache()
    pages = continuation.plan(_query(), _META)
    first = _plan(cache, pages.first(limit=3))
    _plan(cache, _query(2))
    assert verdicts == [False]

    _plan(cache, _query(2))
    assert verdicts == [False]

    after = _plan(cache, pages.after(ContinuationCoordinate((1,)), limit=3))

    assert verdicts == [False, False, True]
    assert _root(after)[1] is not _root(first)[1]
    assert after._schema is first._schema
    assert after._fetches is first._fetches


def test_concurrent_waiters_compare_no_family_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    started = threading.Event()
    release = threading.Event()
    callers = threading.Barrier(8)

    def delayed_build(**kwargs: Any) -> Any:
        started.set()
        assert release.wait(timeout=2)
        return uncached(**kwargs)

    cache = ReadPlanCache()
    _plan(cache, _name_query("order-2"))
    verdicts = _counting_family_comparisons(monkeypatch)
    monkeypatch.setattr(_read_plan, "_plan_uncached", delayed_build)
    query = _query()

    def plan(_index: int) -> _read_plan.ReadPlan:
        callers.wait()
        return _plan(cache, query)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(pool.submit(plan, index) for index in range(8))
        assert started.wait(timeout=2)
        time.sleep(0.05)
        release.set()
        prepared = tuple(future.result() for future in futures)

    assert all(_shares_preparation(value, prepared[0]) for value in prepared)
    assert verdicts == [False]
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(16, 2, 7, 2, 0)


def test_equal_coordinate_values_of_distinct_exact_types_keep_cold_and_warm_binds() -> None:
    cache = ReadPlanCache(capacity=4)
    pages = continuation.plan(_query(), _META)
    with_boolean = pages.after(ContinuationCoordinate((True,)), limit=3)
    with_integer = pages.after(ContinuationCoordinate((1,)), limit=3)

    cold = _plan(cache, with_boolean)
    warm = _plan(cache, with_integer)

    assert warm is not cold
    cold_root, cold_rows = _root(cold)
    warm_root, warm_rows = _root(warm)
    assert warm_rows is cold_rows
    assert any(type(value) is bool and value is True for value in cold_root.statement.binds)
    assert any(type(value) is int and value == 1 for value in warm_root.statement.binds)
    assert not any(type(value) is bool for value in warm_root.statement.binds)
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(4, 1, 1, 1, 0)


def test_capacity_zero_uses_the_uncached_read_planning_seam() -> None:
    selected = _query()
    planner = ReadPlanCache(capacity=0)

    first = planner.plan(
        edition="edition-a",
        model=_MODEL,
        dialect=POSTGRES,
        query=selected,
        result_form="instance",
        preference=None,
    )
    second = planner.plan(
        edition="edition-a",
        model=_MODEL,
        dialect=POSTGRES,
        query=selected,
        result_form="instance",
        preference=None,
    )

    assert second is not first
    assert _root(second)[0].statement == _root(first)[0].statement
    assert planner._statistics() == _read_plan._ReadPlanCacheStatistics(0, 0, 0, 0, 0)


class _Untouchable:
    __slots__ = ()

    def __getattribute__(self, name: str) -> Any:
        raise AssertionError(f"capacity zero touched cache state through {name}")


def test_capacity_zero_does_no_key_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("capacity zero performed key work")

    for name in (
        "_read_plan_key",
        "_ReadPlanKey",
        "_QueryKey",
        "_Identity",
        "_query_key",
        "continuation_pattern",
        "compile_template",
    ):
        monkeypatch.setattr(_read_plan, name, reject)
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    received: list[frozenset[str]] = []

    def recording(**kwargs: Any) -> Any:
        received.append(frozenset(kwargs))
        return uncached(**kwargs)

    monkeypatch.setattr(_read_plan, "_plan_uncached", recording)
    planner = ReadPlanCache(capacity=0)
    planner._entries = cast("Any", _Untouchable())
    planner._pending = cast("Any", _Untouchable())
    planner._lock = cast("Any", _Untouchable())
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    planned = _plan(planner, continued)

    assert 1 in _root(planned)[0].statement.binds
    assert _root(planned)[0].statement.execution_value_positions() == ()
    assert received == [
        frozenset({"model", "dialect", "query", "result_form", "preference"}),
    ]


def test_concurrency_preferences_have_independent_entries() -> None:
    cache = ReadPlanCache()
    query = _query()

    standalone = _plan(cache, query)
    locking = _plan(cache, query, preference="locking")
    optimistic = _plan(cache, query, preference="optimistic")

    assert standalone is not locking
    assert optimistic is not locking
    assert cache._statistics().size == 3


def test_continuation_values_share_one_null_pattern_template_without_stale_binds() -> None:
    cache = ReadPlanCache()
    pages = continuation.plan(_query(), _META)
    first = _plan(cache, pages.first(limit=3))
    after_one = _plan(cache, pages.after(ContinuationCoordinate((1,)), limit=3))
    after_two = _plan(cache, pages.after(ContinuationCoordinate((2,)), limit=3))

    after_one_root, after_one_rows = _root(after_one)
    after_two_root, after_two_rows = _root(after_two)
    assert _root(first)[1] is not after_one_rows
    assert after_two_rows is after_one_rows
    assert after_two_root.statement.binds != after_one_root.statement.binds
    assert 1 in after_one_root.statement.binds
    assert 2 in after_two_root.statement.binds
    assert cache._statistics().size == 2
    assert cache._statistics().hits == 1
    assert cache._statistics().misses == 2


def test_first_page_limits_share_one_template_without_stale_binds() -> None:
    cache = ReadPlanCache()
    pages = continuation.plan(_query(), _META)

    three = _plan(cache, pages.first(limit=3))
    five = _plan(cache, pages.first(limit=5))

    three_root, _ = _root(three)
    five_root, _ = _root(five)
    assert three_root.statement.binds != five_root.statement.binds
    assert 3 in three_root.statement.binds
    assert 5 in five_root.statement.binds
    assert cache._statistics().hits == 1
    assert cache._statistics().misses == 1


def test_continuation_null_patterns_use_distinct_templates() -> None:
    cache = ReadPlanCache()
    pages = continuation.plan(_query(), _META)

    non_null = _plan(cache, pages.after(ContinuationCoordinate((1,)), limit=3))
    null = _plan(cache, pages.after(ContinuationCoordinate((None,)), limit=3))

    assert null is not non_null
    assert cache._statistics().misses == 2


def test_a_continuation_replans_its_template_for_a_new_effective_lock_variant() -> None:
    cache = ReadPlanCache()
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    standalone = _plan(cache, continued)
    locking = _plan(cache, continued, preference="locking")

    assert standalone is not locking
    assert 1 in _root(standalone)[0].statement.binds
    assert 1 in _root(locking)[0].statement.binds
    assert cache._statistics().misses == 2


def _after(carrier: object) -> ResolvedObjectQuery:
    return continuation.plan(_query(), _META).after(ContinuationCoordinate((carrier,)), limit=3)


def _blocking_renders(
    monkeypatch: pytest.MonkeyPatch, *, hold: Callable[[], object]
) -> list[CompiledTemplate]:
    """Make every root render run ``hold`` first, recording each template."""
    render = CompiledTemplate.render
    rendering: list[CompiledTemplate] = []

    def held(
        self: CompiledTemplate, keys: list[Any] | None = None, *, query: Any = None
    ) -> CompiledRead:
        if query is not None:
            rendering.append(self)
            hold()
        return render(self, keys, query=query)

    monkeypatch.setattr(CompiledTemplate, "render", held)
    return rendering


_VALUED: Final[Mapping[str, Callable[[int], ResolvedObjectQuery]]] = {
    "continuation": lambda value: _after(value),
    "predicate": lambda value: _query(value),
}


@pytest.mark.parametrize("valued", _VALUED.values(), ids=_VALUED.keys())
def test_cache_hits_render_their_own_values_outside_the_cache_lock(
    monkeypatch: pytest.MonkeyPatch, valued: Callable[[int], ResolvedObjectQuery]
) -> None:
    cache = ReadPlanCache()
    _plan(cache, valued(1))
    together = threading.Barrier(2, timeout=2)
    rendering = _blocking_renders(monkeypatch, hold=together.wait)

    def plan(value: int) -> _read_plan.ReadPlan:
        return _plan(cache, valued(value))

    with ThreadPoolExecutor(max_workers=2) as pool:
        plans = tuple(pool.map(plan, (2, 3)))

    assert len(rendering) == 2 and rendering[0] is rendering[1]
    uncached = ReadPlanCache(0)
    for value, delivered in zip((2, 3), plans, strict=True):
        statement = _root(delivered)[0].statement
        assert statement == _root(_plan(uncached, valued(value)))[0].statement
        assert value in statement.binds
        assert statement.execution_value_positions() == ()
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(16, 1, 2, 1, 0)


def test_a_hit_renders_after_its_entry_is_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = ReadPlanCache(capacity=1)
    cached = _plan(cache, _after(1))
    looked_up = threading.Event()
    evicted = threading.Event()

    def hold() -> None:
        looked_up.set()
        assert evicted.wait(timeout=2)

    _blocking_renders(monkeypatch, hold=hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        hit = pool.submit(_plan, cache, _after(2))
        assert looked_up.wait(timeout=2)
        monkeypatch.undo()
        _plan(cache, _query(2))
        evicted.set()
        rendered = hit.result()

    assert _read_plan._ReadPlanCacheStatistics(1, 1, 1, 2, 1) == cache._statistics()
    assert _root(rendered)[0].statement == _root(_plan(ReadPlanCache(0), _after(2)))[0].statement
    assert rendered._fetches is cached._fetches


@pytest.mark.parametrize("valued", _VALUED.values(), ids=_VALUED.keys())
def test_callers_of_one_pending_key_each_render_their_own_values(
    monkeypatch: pytest.MonkeyPatch, valued: Callable[[int], ResolvedObjectQuery]
) -> None:
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    started = threading.Event()
    release = threading.Event()
    callers = threading.Barrier(4)

    def delayed_build(**kwargs: Any) -> Any:
        started.set()
        assert release.wait(timeout=2)
        return uncached(**kwargs)

    monkeypatch.setattr(_read_plan, "_plan_uncached", delayed_build)
    cache = ReadPlanCache()

    def plan(value: int) -> _read_plan.ReadPlan:
        callers.wait()
        return _plan(cache, valued(value))

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = tuple(pool.submit(plan, value) for value in (10, 20, 30, 40))
        assert started.wait(timeout=2)
        time.sleep(0.05)
        release.set()
        plans = tuple(future.result() for future in futures)

    uncached_planner = ReadPlanCache(0)
    for value, delivered in zip((10, 20, 30, 40), plans, strict=True):
        expected = _root(_plan(uncached_planner, valued(value)))[0].statement
        assert _root(delivered)[0].statement == expected
    assert len({id(delivered._schema) for delivered in plans}) == 1
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(16, 1, 3, 1, 0)


def test_capacity_zero_compiles_its_root_concretely_and_defers_only_child_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _recording_preparation(monkeypatch)
    pages = continuation.plan(_with_items(), _META)

    plan = _plan(ReadPlanCache(0), pages.after(ContinuationCoordinate((1,)), limit=2))

    assert sorted(prepared) == ["bind", "bind", "compile_read", "compile_template"]
    assert _root(plan)[0].statement.execution_value_positions() == ()
    template = cast("CompiledTemplate", _child_work(plan))
    assert [group.source for group in template.compiled.statement.execution_value_positions()] == [
        ("keys",)
    ]


def test_editions_and_exact_models_are_isolated_without_invalidating_each_other() -> None:
    cache = ReadPlanCache()
    query = _query()

    first = _plan(cache, query)
    next_edition = _plan(cache, query, edition="edition-b")
    next_model = _plan(cache, query, edition="edition-b", model=CatalogedModel(_META))

    assert _root(next_edition)[1] is not _root(first)[1]
    assert _root(next_model)[1] is not _root(next_edition)[1]
    assert _shares_preparation(_plan(cache, query), first)
    assert cache._statistics().size == 3
    assert cache._statistics().hits == 1


def _member_query(member: str, value: object) -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize(
            {"target": "Order", "predicate": {"eq": {"path": f"Order.{member}", "value": value}}}
        ),
        model=_META,
        form="graph",
    )


def test_recent_use_controls_true_lru_eviction() -> None:
    cache = ReadPlanCache(capacity=2)
    one = _plan(cache, _member_query("id", 1))
    two = _plan(cache, _member_query("qty", 2))

    assert _shares_preparation(_plan(cache, _member_query("id", 4)), one)
    _plan(cache, _member_query("name", "three"))
    two_again = _plan(cache, _member_query("qty", 5))

    assert _root(two_again)[1] is not _root(two)[1]
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(2, 2, 1, 4, 2)


def test_concurrent_cold_callers_plan_one_shared_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    started = threading.Event()
    release = threading.Event()
    callers = threading.Barrier(8)
    builds = 0

    def delayed_build(**kwargs: Any) -> Any:
        nonlocal builds
        builds += 1
        started.set()
        assert release.wait(timeout=2)
        return uncached(**kwargs)

    monkeypatch.setattr(_read_plan, "_plan_uncached", delayed_build)
    cache = ReadPlanCache()
    query = _query()

    def plan(_index: int) -> _read_plan.ReadPlan:
        callers.wait()
        return _plan(cache, query)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(pool.submit(plan, index) for index in range(8))
        assert started.wait(timeout=2)
        time.sleep(0.05)
        release.set()
        prepared = tuple(future.result() for future in futures)

    assert builds == 1
    assert all(_shares_preparation(value, prepared[0]) for value in prepared)
    assert cache._statistics().misses == 1
    assert cache._statistics().hits == 7


def test_a_back_reference_has_no_executable_child_read() -> None:
    plan = replace(_plan(ReadPlanCache(), _query()), _fetches=(None,), _fetch_rows=(None,))

    assert plan.prepared_fetch(0) is None


def test_mixed_cold_keys_and_editions_build_without_global_lock_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    lock = threading.Lock()
    both_building = threading.Event()
    active = 0
    maximum = 0

    def overlapping_builds(**kwargs: Any) -> Any:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active >= 2:
                both_building.set()
        if not both_building.wait(timeout=2):
            raise AssertionError("unrelated cold plans were serialized")
        try:
            return uncached(**kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(_read_plan, "_plan_uncached", overlapping_builds)
    cache = ReadPlanCache(capacity=4)
    requests: tuple[tuple[str, str], ...] = (
        ("edition-a", "id"),
        ("edition-a", "qty"),
        ("edition-b", "id"),
        ("edition-b", "qty"),
    )

    def plan_request(item: tuple[str, str]) -> _read_plan.ReadPlan:
        edition, member = item
        return _plan(cache, _member_query(member, 1), edition=edition)

    with ThreadPoolExecutor(max_workers=4) as pool:
        prepared = tuple(pool.map(plan_request, requests))

    assert maximum >= 2
    assert len({id(value) for value in prepared}) == 4
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(4, 4, 0, 4, 0)


def test_concurrent_failed_planning_is_shared_and_a_later_call_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uncached = cast("Callable[..., Any]", vars(_read_plan)["_plan_uncached"])
    failure = RuntimeError("planning failed")
    started = threading.Event()
    release = threading.Event()
    callers = threading.Barrier(8)
    builds = 0

    def failing_build(**kwargs: Any) -> Any:
        nonlocal builds
        del kwargs
        builds += 1
        started.set()
        assert release.wait(timeout=2)
        raise failure

    def attempt(_index: int) -> BaseException:
        callers.wait()
        try:
            _plan(cache, query)
        except BaseException as exc:
            return exc
        raise AssertionError("the failing plan unexpectedly succeeded")

    monkeypatch.setattr(_read_plan, "_plan_uncached", failing_build)
    cache = ReadPlanCache(capacity=4)
    query = _query()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(pool.submit(attempt, index) for index in range(8))
        assert started.wait(timeout=2)
        time.sleep(0.05)
        release.set()
        failures = tuple(future.result() for future in futures)

    assert builds == 1
    assert all(exc is failure for exc in failures)
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(4, 0, 0, 1, 0)

    monkeypatch.setattr(_read_plan, "_plan_uncached", uncached)
    _plan(cache, query)
    assert cache._statistics() == _read_plan._ReadPlanCacheStatistics(4, 1, 0, 2, 0)


def test_a_warm_hit_repeats_no_planning_compilation_or_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"plan": 0, "compile": 0, "bind": 0}
    deep_fetch_module = vars(_read_plan)["deep_fetch"]
    plan = cast("Callable[..., Any]", deep_fetch_module.plan)
    compile_template = cast("Callable[..., Any]", vars(_read_plan)["compile_template"])
    bind = cast("Callable[..., Any]", vars(_read_plan)["bind"])

    def counting_plan(*args: Any, **kwargs: Any) -> Any:
        calls["plan"] += 1
        return plan(*args, **kwargs)

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        calls["compile"] += 1
        return compile_template(*args, **kwargs)

    def counting_bind(*args: Any, **kwargs: Any) -> Any:
        calls["bind"] += 1
        return bind(*args, **kwargs)

    monkeypatch.setattr(deep_fetch_module, "plan", counting_plan)
    monkeypatch.setattr(_read_plan, "compile_read", _forbidden_concrete_root)
    monkeypatch.setattr(_read_plan, "compile_template", counting_compile)
    monkeypatch.setattr(_read_plan, "bind", counting_bind)
    cache = ReadPlanCache()

    cold = _plan(cache, _query(1))
    warm = _plan(cache, _query(2))

    assert _shares_preparation(warm, cold)
    assert warm.include_tree() is cold.include_tree()
    assert calls == {"plan": 1, "compile": 1, "bind": 1}


@pytest.mark.parametrize("result_form", ["row", "instance"])
def test_each_compiled_read_is_bound_under_the_projection_its_query_resolved(
    result_form: Literal["row", "instance"], monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = projection_support.MATRIX_FAMILIES[("tph", "document")]["Holder"]
    included = holder.where(holder.all).include(holder.members)
    query = projection_support.resolved(
        included if result_form == "instance" else holder.where(holder.all),
        form="graph" if result_form == "instance" else "rows",
    )
    bind = cast("Callable[..., Any]", vars(_read_plan)["bind"])
    bound: list[object] = []

    def recording_bind(model: object, contract: object, projection: object, **kwargs: Any) -> Any:
        bound.append(projection)
        return bind(model, contract, projection, **kwargs)

    monkeypatch.setattr(_read_plan, "bind", recording_bind)
    plan = _plan(
        ReadPlanCache(0),
        query,
        model=CatalogedModel(projection_support.MATRIX_META),
        result_form=result_form,
    )

    root, _converter = _root(plan)
    compiled = (
        root,
        *(
            cast("Any", prepared)[0].compiled
            for index in range(plan.fetch_count)
            if isinstance(prepared := plan.prepared_fetch(index), tuple)
        ),
    )
    assert sorted(map(id, bound)) == sorted(id(read.projection) for read in compiled)
    assert root.projection == deep_fetch.ResolvedReadProjection((), result_form == "instance")
    if result_form == "instance":
        (child,) = compiled[1:]
        assert [
            (member.identity.entity.name, member.identity.path[-1])
            for member in child.projection.value_objects
        ] == [("Root", "origin"), ("Left", "home"), ("Right", "home")]
        assert child.projection.observe_structured_document


def _with_items() -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize(
            {
                "target": "Order",
                "predicate": {"true": {}},
                "includes": [{"segments": [{"rel": "Order.items"}]}],
            }
        ),
        model=_META,
        form="graph",
    )


def _child_work(plan: _read_plan.ReadPlan) -> object:
    prepared = plan.prepared_fetch(0)
    assert isinstance(prepared, tuple)
    return prepared[0]


def test_retained_child_work_is_resolved_and_compiled_once_per_plan_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"root": 0, "child": 0, "compile": 0}
    compile_template = cast("Callable[..., Any]", vars(_read_plan)["compile_template"])
    for name in ("resolve_temporal_visibility", "resolve_sourced_temporal_visibility"):
        resolve = cast("Callable[..., Any]", vars(deep_fetch)[name])

        def counting_resolve(*args: Any, _resolve: Any = resolve, **kwargs: Any) -> Any:
            propagated = isinstance(kwargs["resolution"], PropagatedRootSelections)
            calls["child" if propagated else "root"] += 1
            return _resolve(*args, **kwargs)

        monkeypatch.setattr(deep_fetch, name, counting_resolve)

    def counting_child(query: deep_fetch.PlannedEntityQuery, *args: Any, **kwargs: Any) -> Any:
        if query.entity.identity.name == "OrderItem":
            calls["compile"] += 1
        return compile_template(query, *args, **kwargs)

    monkeypatch.setattr(_read_plan, "compile_template", counting_child)
    cache = ReadPlanCache()
    pages = continuation.plan(_with_items(), _META)

    first = _plan(cache, pages.first(limit=2))
    assert calls == {"root": 1, "child": 1, "compile": 1}
    assert _plan(cache, pages.first(limit=3)).fetch_step(0) is first.fetch_step(0)
    assert calls == {"root": 1, "child": 1, "compile": 1}

    after = _plan(cache, pages.after(ContinuationCoordinate((1,)), limit=2))
    assert calls == {"root": 2, "child": 1, "compile": 1}
    assert after.fetch_step(0) is first.fetch_step(0)
    assert after.include_tree() is first.include_tree()
    assert _child_work(after) is _child_work(first)


def test_a_delivered_child_level_renders_its_retained_template_into_its_one_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = ReadPlanCache()
    query = _with_items()
    prepared = _plan(cache, query).prepared_fetch(0)
    assert isinstance(prepared, tuple)
    template, _converter = prepared

    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("delivery must reuse the prepared child read")

    for name in ("compile_read", "compile_template", "bind"):
        monkeypatch.setattr(_read_plan, name, forbidden)
    monkeypatch.setattr(ReadResultContract, "__init__", forbidden)
    rendered: list[tuple[CompiledTemplate, CompiledRead]] = []
    render = CompiledTemplate.render

    def recording_render(
        self: CompiledTemplate, keys: list[Any] | None = None, *, query: Any = None
    ) -> CompiledRead:
        rendered.append((self, render(self, keys, query=query)))
        return rendered[-1][1]

    monkeypatch.setattr(CompiledTemplate, "render", recording_render)
    order = {
        "id": 1,
        "name": "order-1",
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }

    result = find(
        query,
        _MODEL,
        ScriptedAdapter(Read(rows=[order]), Read(rows=[])),
        origin_collector=EMPTY_PAGE_ORIGIN_COLLECTOR,
        edition="edition-a",
        planner=cache,
    )

    assert result.page.root_count == 1
    (root_template, root), (used, child) = rendered
    assert root is root_template.compiled
    assert used is template
    assert child.statement is not template.compiled.statement
    assert child.result_contract is template.compiled.result_contract
    assert child.projection is template.compiled.projection
    assert child.document_reads is template.compiled.document_reads


def test_database_transactions_share_read_plans_across_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = 0
    compile_template = cast("Callable[..., Any]", vars(_read_plan)["compile_template"])

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        nonlocal compiled
        compiled += 1
        return compile_template(*args, **kwargs)

    monkeypatch.setattr(_read_plan, "compile_read", _forbidden_concrete_root)
    monkeypatch.setattr(_read_plan, "compile_template", counting_compile)
    row = {
        "id": 1,
        "name": "order-1",
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }
    adapter = ScriptedAdapter(Transact(Read(rows=[row])), Transact(Read(rows=[row])))

    database = db_for(ORDERS_MODEL, adapter)
    query = Order.where(Order.id == 1)
    database.transact(lambda transaction: transaction.find(query).result())
    database.transact(lambda transaction: transaction.find(query).result())

    assert adapter.acquisitions == 2
    assert compiled == 1


@pytest.mark.parametrize(
    ("capacity", "expected_compilation"), [(0, "compile_read"), (16, "compile_template")]
)
def test_public_capacity_zero_disables_cross_delivery_reuse_without_bypassing_planning(
    monkeypatch: pytest.MonkeyPatch,
    capacity: int,
    expected_compilation: str,
) -> None:
    compiled: list[str] = []
    for name in ("compile_read", "compile_template"):
        original = cast("Callable[..., Any]", vars(_read_plan)[name])

        def counting_compile(*args: Any, _name: str = name, _run: Any = original, **kw: Any) -> Any:
            compiled.append(_name)
            return _run(*args, **kw)

        monkeypatch.setattr(_read_plan, name, counting_compile)
    row = {
        "id": 1,
        "name": "order-1",
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }
    adapter = ScriptedAdapter(Read(rows=[row]), Read(rows=[row]))

    with Database.connect(
        adapter,
        ORDERS_MODEL,
        read_plan_cache_capacity=capacity,
    ) as root:
        database = root.using_database_login()
        database.find(Order.where(Order.id == 1)).result()
        database.find(Order.where(Order.id == 1)).result()

    assert compiled == [expected_compilation] * (2 if capacity == 0 else 1)


@pytest.mark.parametrize("capacity", [True, -1, 1.5])
def test_public_capacity_validation_precedes_adapter_runtime_open(capacity: object) -> None:
    class MustNotOpen:
        opened = False

        def open(self) -> None:
            self.opened = True
            raise AssertionError("invalid capacity must be refused before runtime open")

    adapter = MustNotOpen()
    with pytest.raises(ValueError, match="nonnegative built-in int"):
        Database.connect(
            cast("Any", adapter),
            ORDERS_MODEL,
            read_plan_cache_capacity=cast("Any", capacity),
        )
    assert not adapter.opened


def test_read_plan_cache_retains_no_connection_rows_page_evidence_or_result() -> None:
    cache = ReadPlanCache()
    stored_row = {
        "id": 1,
        "name": "order-1",
        "sku": "A-100",
        "qty": 5,
        "price": 10,
        "active": True,
        "ordered_on": None,
    }
    port = ScriptedAdapter(Read(rows=[stored_row]))
    retained = weakref.ref(port)

    result = find(
        _query(),
        _MODEL,
        port,
        origin_collector=EMPTY_PAGE_ORIGIN_COLLECTOR,
        edition="edition-a",
        planner=cache,
    )
    assert result.page.root_count == 1
    assert not _reaches(cache, port)
    assert not _reaches(cache, stored_row)
    assert not _reaches(cache, result)
    assert not _reaches(cache, result.page)
    assert not _reaches(cache, result.origins)
    del result, port
    gc.collect()

    assert retained() is None
    assert cache._statistics().size == 1


class _TrackedString(str):
    pass


@pytest.mark.parametrize("release_by", ["cache-closure", "eviction"])
def test_cached_query_literals_are_collectable_after_cache_closure_or_eviction(
    release_by: str,
) -> None:
    cache = ReadPlanCache(capacity=1)
    literal = _TrackedString("tracked")
    retained = weakref.ref(literal)
    selected = _name_query(literal)
    _plan(cache, selected)
    del literal, selected

    if release_by == "eviction":
        _plan(cache, _name_query("replacement"))
    else:
        del cache
    gc.collect()

    assert retained() is None


@pytest.mark.parametrize("capacity", [True, -1, 1.5])
def test_capacity_requires_a_nonnegative_built_in_integer(capacity: object) -> None:
    with pytest.raises(ValueError, match="nonnegative built-in int"):
        ReadPlanCache(cast("int", capacity))


_DORMANT_META = model_of(DORMANT_POSITION_COLUMNS)
_DORMANT = CatalogedModel(_DORMANT_META)
_TO_EMPTY_ANCESTRY: Final[Mapping[str, object]] = {
    "target": "Prototype",
    "predicate": {"true": {}},
    "includes": [{"segments": [{"rel": "Prototype.workbenches"}, {"rel": "Workbench.prototype"}]}],
}
_WORKBENCHES: Final[Mapping[str, object]] = {
    "target": "Workbench",
    "predicate": {"true": {}},
    "includes": [
        {"segments": [{"rel": "Workbench.prototypes"}]},
        {"segments": [{"rel": "Workbench.prototype"}]},
        {"segments": [{"rel": "Workbench.gadgets"}]},
    ],
}


def _dormant_query(
    document: Mapping[str, object], meta: Metamodel = _DORMANT_META
) -> ResolvedObjectQuery:
    return resolve_read_query(deserialize(document), model=meta, form="graph")


def _recording_preparation(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every statement compilation and converter binding the planner runs."""
    prepared: list[str] = []
    for name in ("compile_read", "compile_template", "bind"):
        original = cast("Callable[..., Any]", vars(_read_plan)[name])

        def recording(*args: Any, _name: str = name, _run: Any = original, **kwargs: Any) -> Any:
            prepared.append(_name)
            return _run(*args, **kwargs)

        monkeypatch.setattr(_read_plan, name, recording)
    return prepared


def _gadget_member(name: str) -> AttributeIdentity:
    return AttributeIdentity(EntityIdentity("parallax.compatibility", "Gadget"), name)


def test_a_dormant_root_prepares_no_statement_converter_or_child_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _recording_preparation(monkeypatch)

    plan = _plan(ReadPlanCache(), _dormant_query(_TO_EMPTY_ANCESTRY), model=_DORMANT)

    assert isinstance(plan.root_read(), EmptyRead)
    # The back-reference beneath the empty level is empty work too, not the
    # reachable-reference state that would attach from converted rows.
    assert [plan.prepared_fetch(index) for index in range(plan.fetch_count)] == [
        EMPTY_READ,
        EMPTY_READ,
    ]
    assert isinstance(plan.fetch_step(1), deep_fetch.BackReferenceFetchStep)
    assert plan._correlations == ((), (), ())
    assert prepared == []


def test_an_empty_include_target_prepares_no_child_work_or_routing_demand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _recording_preparation(monkeypatch)

    plan = _plan(ReadPlanCache(), _dormant_query(_WORKBENCHES), model=_DORMANT)

    root, _rows = _root(plan)
    # The to-one's owner key stays an ordinary projected member, judged at
    # publication; only its routing demand is gone.
    assert "t0.prototype_id" in root.statement.sql
    by_view = {
        _view_name(plan, index): (plan.prepared_fetch(index), plan._correlations[index + 1])
        for index in range(plan.fetch_count)
    }
    assert by_view.keys() == {"gadgets", "prototype", "prototypes"}
    assert by_view["prototypes"] == (EMPTY_READ, ())
    assert by_view["prototype"] == (EMPTY_READ, ())
    live, live_correlations = by_view["gadgets"]
    assert isinstance(live, tuple)
    assert live_correlations == (_gadget_member("workbenchId"),)
    workbench_id = AttributeIdentity(EntityIdentity("parallax.compatibility", "Workbench"), "id")
    assert plan._correlations[0] == (workbench_id,)
    assert sorted(prepared) == ["bind", "bind", "compile_template", "compile_template"]


def _view_name(plan: _read_plan.ReadPlan, index: int) -> str:
    view = plan.include_tree().position(plan.fetch_step(index).position).view
    assert view is not None
    return view.relationship.name


def test_a_dormant_page_carries_no_root_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _recording_preparation(monkeypatch)
    cache = ReadPlanCache()
    pages = continuation.plan(_dormant_query(_TO_EMPTY_ANCESTRY), _DORMANT_META)

    first = _plan(cache, pages.first(limit=3), model=_DORMANT)
    after = _plan(cache, pages.after(ContinuationCoordinate((1,)), limit=3), model=_DORMANT)

    assert isinstance(first.root_read(), EmptyRead)
    assert isinstance(after.root_read(), EmptyRead)
    assert after is not first
    assert after._fetches is first._fetches
    assert after._fetch_rows is first._fetch_rows
    assert after._correlations is first._correlations
    assert after._schema is first._schema
    assert [entry.root_template for entry in cache._entries.values()] == [None, None]
    assert _plan(cache, pages.first(limit=5), model=_DORMANT) is first
    assert prepared == []


def test_cached_and_uncached_dormant_plans_agree() -> None:
    query = _dormant_query(_WORKBENCHES)

    cached = _plan(ReadPlanCache(), query, model=_DORMANT)
    uncached = _plan(ReadPlanCache(0), query, model=_DORMANT)

    assert uncached is not cached
    assert _root(uncached)[0].statement == _root(cached)[0].statement
    assert [uncached.fetch_step(index) for index in range(uncached.fetch_count)] == [
        cached.fetch_step(index) for index in range(cached.fetch_count)
    ]
    assert uncached._correlations == cached._correlations
    assert [type(uncached.prepared_fetch(index)) for index in range(uncached.fetch_count)] == [
        type(cached.prepared_fetch(index)) for index in range(cached.fetch_count)
    ]


def test_a_model_composing_a_concrete_under_the_position_plans_it_apart() -> None:
    dormant = records("dormant-position-layout-twin-columns")
    mockup = DescriptorEntity(
        name="Mockup",
        namespace="parallax.compatibility",
        inheritance=Inheritance(
            role="concrete-subtype", parent="parallax.compatibility.Prototype", tag_value="mockup"
        ),
    )
    later_meta = formed(replace(dormant, entities=(*dormant.entities, mockup)))
    later = CatalogedModel(later_meta)
    document: Mapping[str, object] = {"target": "Prototype", "predicate": {"true": {}}}
    cache = ReadPlanCache()

    earlier_plan = _plan(cache, _dormant_query(document), model=_DORMANT)
    later_plan = _plan(cache, _dormant_query(document, later_meta), model=later)

    assert isinstance(earlier_plan.root_read(), EmptyRead)
    assert "where t0.kind = ?" in _root(later_plan)[0].statement.sql
    assert cache._statistics().size == 2


_DOCUMENT = corpus_model("document")
_DOCUMENT_LAYOUT = corpus_model("document-layout")


def _carriers(binds: tuple[object, ...]) -> list[tuple[object, ...]]:
    return [
        (type(bind), bind, bind.as_tuple()) if isinstance(bind, Decimal) else (type(bind), bind)
        for bind in binds
    ]


def _in_order(expected: list[tuple[object, ...]], carriers: list[tuple[object, ...]]) -> bool:
    remaining = iter(carriers)
    return all(any(carrier == wanted for carrier in remaining) for wanted in expected)


def _seeded_render(
    meta: Metamodel, seed: ResolvedObjectQuery, current: ResolvedObjectQuery
) -> tuple[CompiledRead, CompiledRead, ReadPlanCache]:
    """``current`` rendered from a cache ``seed`` prepared, and planned cold."""
    model = CatalogedModel(meta)
    cache = ReadPlanCache()
    _plan(cache, seed, model=model)
    rendered = _root(_plan(cache, current, model=model))[0]
    cold = _root(_plan(ReadPlanCache(0), current, model=model))[0]
    return rendered, cold, cache


def _statement_facts(read: CompiledRead) -> tuple[object, ...]:
    statement = read.statement
    return (
        read,
        _carriers(statement.binds),
        statement.typed_bind_spans,
        statement.wire_bind_overrides,
        statement.wire_binds(),
    )


_D = Decimal
# Each seed renders the current read of the same structure; the authored
# operands' carriers appear in the current statement in this order.
_RENDERED_OPERANDS: tuple[
    tuple[str, Metamodel, str, dict[str, object], dict[str, object], list[tuple[object, ...]]],
    ...,
] = (
    (
        "comparison",
        _ORDERS,
        "Order",
        {"eq": {"path": "Order.qty", "value": 1}},
        {"eq": {"path": "Order.qty", "value": 2}},
        [(int, 2)],
    ),
    (
        "decimal",
        _ORDERS,
        "Order",
        {"eq": {"path": "Order.price", "value": "1.50"}},
        {"eq": {"path": "Order.price", "value": "2.25"}},
        [(_D, _D("2.25"), _D("2.25").as_tuple())],
    ),
    (
        "range",
        _ORDERS,
        "Order",
        {"between": {"path": "Order.qty", "lower": 1, "upper": 5}},
        {"between": {"path": "Order.qty", "lower": 3, "upper": 7}},
        [(int, 3), (int, 7)],
    ),
    (
        "membership",
        _ORDERS,
        "Order",
        {"in": {"path": "Order.id", "values": [1, 2]}},
        {"in": {"path": "Order.id", "values": [5, 6]}},
        [(int, 5), (int, 6)],
    ),
    (
        "unescaped-affix",
        _ORDERS,
        "Order",
        {"startsWith": {"path": "Order.name", "value": "ab"}},
        {"startsWith": {"path": "Order.name", "value": "cd"}},
        [(str, "cd%")],
    ),
    (
        "escaped-affix",
        _ORDERS,
        "Order",
        {"contains": {"path": "Order.name", "value": "a_b"}},
        {"contains": {"path": "Order.name", "value": "c%d"}},
        [(str, "%c\\%d%"), (str, "\\")],
    ),
    (
        "folded-affix",
        _ORDERS,
        "Order",
        {"endsWith": {"path": "Order.name", "value": "AB", "caseInsensitive": True}},
        {"endsWith": {"path": "Order.name", "value": "Cd", "caseInsensitive": True}},
        [(str, "%cd")],
    ),
    (
        "verbatim-pattern",
        _ORDERS,
        "Order",
        {"like": {"path": "Order.name", "value": "a%"}},
        {"like": {"path": "Order.name", "value": "b_"}},
        [(str, "b_")],
    ),
    (
        "constants-in-connectives",
        _ORDERS,
        "Order",
        {
            "and": {
                "operands": [
                    {"true": {}},
                    _ID_ONE,
                    {
                        "or": {
                            "operands": [{"false": {}}, {"eq": {"path": "Order.qty", "value": 2}}]
                        }
                    },
                ]
            }
        },
        {
            "and": {
                "operands": [
                    {"true": {}},
                    {"eq": {"path": "Order.id", "value": 3}},
                    {
                        "or": {
                            "operands": [{"false": {}}, {"eq": {"path": "Order.qty", "value": 4}}]
                        }
                    },
                ]
            }
        },
        [(int, 3), (int, 4)],
    ),
    (
        "document-collection",
        _CUSTOMER,
        "Customer",
        {"any": {"path": "Customer.address.phones", "where": _PHONE_HOME}},
        {
            "any": {
                "path": "Customer.address.phones",
                "where": {"eq": {"path": "type", "value": "work"}},
            }
        },
        [(str, "work")],
    ),
    (
        "relationship-quantifier",
        _CUSTOMER,
        "Customer",
        {"any": {"path": "Customer.locations", "where": {"eq": {"path": "label", "value": "a"}}}},
        {"any": {"path": "Customer.locations", "where": {"eq": {"path": "label", "value": "b"}}}},
        [(str, "b")],
    ),
    (
        "shared-relationship",
        _ORDERS,
        "OrderStatus",
        {"eq": {"path": "OrderStatus.order.name", "value": "A"}},
        {"eq": {"path": "OrderStatus.order.name", "value": "B"}},
        [(str, "B")],
    ),
    (
        "match-operand",
        _ORDERS,
        "OrderItem",
        {"exists": {"path": "OrderItem.order", "where": _NAMED_LOCAL_A}},
        {"exists": {"path": "OrderItem.order", "where": {"eq": {"path": "name", "value": "B"}}}},
        [(str, "B")],
    ),
    (
        "narrowed-operand",
        _ANIMAL,
        "Animal",
        {"narrow": {"to": ["Dog"], "operand": {"eq": {"path": "Dog.name", "value": "rex"}}}},
        {"narrow": {"to": ["Dog"], "operand": {"eq": {"path": "Dog.name", "value": "fido"}}}},
        [(str, "fido")],
    ),
    (
        "repeated-inheritance-branches",
        _DOCUMENT,
        "Document",
        {"eq": {"path": "Document.title", "value": "a"}},
        {"eq": {"path": "Document.title", "value": "b"}},
        [(str, "b"), (str, "b"), (str, "b")],
    ),
    (
        "comparison-text",
        _DOCUMENT_LAYOUT,
        "Traveler",
        {"eq": {"path": "Traveler.joinedOn", "value": "2024-01-01"}},
        {"eq": {"path": "Traveler.joinedOn", "value": "2024-01-02"}},
        [(str, "2024-01-02")],
    ),
    (
        "cast-document-member",
        _DOCUMENT_LAYOUT,
        "Traveler",
        {"eq": {"path": "Traveler.score", "value": 1}},
        {"eq": {"path": "Traveler.score", "value": 2}},
        [(int, 2)],
    ),
)


@pytest.mark.parametrize(
    ("meta", "target", "seed", "current", "expected"),
    [case[1:] for case in _RENDERED_OPERANDS],
    ids=[case[0] for case in _RENDERED_OPERANDS],
)
def test_a_seeded_template_renders_the_current_reads_own_operands(
    meta: Metamodel,
    target: str,
    seed: dict[str, object],
    current: dict[str, object],
    expected: list[tuple[object, ...]],
) -> None:
    def resolved(predicate: dict[str, object]) -> ResolvedObjectQuery:
        document = {"target": target, "predicate": predicate}
        return resolve_read_query(deserialize(document), model=meta, form="graph")

    rendered, cold, cache = _seeded_render(meta, resolved(seed), resolved(current))

    assert (cache._statistics().misses, cache._statistics().hits) == (1, 1)
    assert _statement_facts(rendered) == _statement_facts(cold)
    assert _in_order(expected, _carriers(rendered.statement.binds))
    assert rendered.statement.execution_value_positions() == ()


def test_repeated_uses_of_one_predicate_node_render_their_own_operands() -> None:
    comparison = _query(1).predicate
    assert isinstance(comparison, ResolvedComparison)
    seed = replace(_query(), predicate=ResolvedAnd((comparison, comparison)))
    current = replace(
        _query(),
        predicate=ResolvedAnd((replace(comparison, value=2), replace(comparison, value=3))),
    )

    rendered, cold, cache = _seeded_render(_META, seed, current)

    assert (cache._statistics().misses, cache._statistics().hits) == (1, 1)
    assert _statement_facts(rendered) == _statement_facts(cold)
    assert _carriers(rendered.statement.binds)[-2:] == [(int, 2), (int, 3)]


@pytest.mark.parametrize(
    ("first", "second"),
    [(Decimal("1.5"), Decimal("1.50")), (True, 1), (1, 1.0)],
    ids=["decimal-exponent", "boolean-integer", "integer-float"],
)
def test_operands_of_distinct_exact_types_or_exponents_plan_apart_and_keep_their_carriers(
    first: object, second: object
) -> None:
    def priced(value: object) -> ResolvedObjectQuery:
        query = _member_query("price", "1.50")
        assert isinstance(query.predicate, ResolvedComparison)
        return replace(query, predicate=replace(query.predicate, value=value))

    cache = ReadPlanCache()
    one, other = _plan(cache, priced(first)), _plan(cache, priced(second))

    assert cache._statistics().misses == 2
    assert _carriers(_root(one)[0].statement.binds) == _carriers((first,))
    assert _carriers(_root(other)[0].statement.binds) == _carriers((second,))


def test_the_cache_retains_neither_later_render_inputs_nor_source_associations() -> None:
    cache = ReadPlanCache()
    _plan(cache, _name_query(_TrackedString("cold")))
    later = _TrackedString("later")
    retained = weakref.ref(later)

    rendered = _plan(cache, _name_query(later))

    assert cache._statistics().hits == 1
    assert later in _root(rendered)[0].statement.binds
    assert not _reaches(cache, later)
    assert not _reaching(cache, lambda value: isinstance(value, ExecutionValueSources))
    del later, rendered
    gc.collect()
    assert retained() is None


def test_direct_compilation_and_write_reads_prepare_no_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a concrete statement prepared template state")

    for owner, name in (
        (ExecutionValueSources, "authored"),
        (ExecutionValueSources, "within"),
        (ExecutionValueSources, "moved"),
        (LoweredStatement, "execution_value_positions"),
        (LoweredStatement, "with_execution_values"),
        (StatementBuilder, "bind_deferred"),
        (_compile_module, "_template"),
    ):
        monkeypatch.setattr(owner, name, forbidden)
    order = _CORPUS_ORDERS.entity(EntityIdentity("parallax.compatibility", "Order"))
    assert order is not None
    paged = continuation.plan(
        _corpus_query(_CORPUS_ORDERS, "Order", {"in": {"path": "Order.id", "values": [1, 2]}}),
        _CORPUS_ORDERS,
    ).after(ContinuationCoordinate((1,)), limit=2)

    direct = compile_read(
        deep_fetch.plan(paged, _CORPUS_ORDERS, projection=_ROW_PROJECTION).root,
        _CORPUS_ORDERS,
        POSTGRES,
    )
    target = compile_read(
        deep_fetch.plan_target_read(order, model=_CORPUS_ORDERS, key="id", key_value=7),
        _CORPUS_ORDERS,
        POSTGRES,
        result_form="row",
        lock="locking",
    )
    written = compile_write_predicate(
        resolve_temporal_visibility(
            paged.predicate,
            target=order,
            model=_CORPUS_ORDERS,
            resolution=NoRootSelections(),
        ),
        _CORPUS_ORDERS,
        POSTGRES,
        order,
    )

    assert direct.statement.binds == (1, 2, 1, 1, 2, 1, 2, 2, 2)
    assert 7 in target.statement.binds
    assert written.binds == (1, 2)


_CORPUS_ORDERS = corpus_model("orders")
_ROW_PROJECTION = deep_fetch.ReadProjectionRequest("none", False)


def _corpus_query(
    meta: Metamodel, target: str, predicate: Mapping[str, object]
) -> ResolvedObjectQuery:
    return resolve_read_query(
        deserialize({"target": target, "predicate": dict(predicate)}), model=meta, form="rows"
    )
