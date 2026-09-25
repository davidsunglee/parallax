# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import gc
import threading
import time
import types
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Literal, cast

import pytest

from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core import continuation
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.core.object_query._validated import ContinuationCoordinate, ValidatedObjectQuery
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle import Database, _read_plan
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import find
from parallax.snapshot.handle._read_plan import ReadPlanCache
from tests._support.db_port import Read, ScriptedAdapter, Transact
from tests.unit._transact_support import db_for

_META = model_of(ORDERS_MODEL)
_MODEL = CatalogedModel(_META)


def _reaches(root: object, target: object) -> bool:
    atomic = (str, bytes, int, float, bool, type(None), type, types.ModuleType)
    pending = [root]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if value is target:
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


def _query(value: object = 1) -> ValidatedObjectQuery:
    return preflight(
        deserialize(
            {
                "target": "Order",
                "predicate": {"eq": {"attr": "Order.id", "value": value}},
            }
        ),
        model=_META,
        form="graph",
    )


def _name_query(value: str) -> ValidatedObjectQuery:
    return preflight(
        deserialize(
            {
                "target": "Order",
                "predicate": {"eq": {"attr": "Order.name", "value": value}},
            }
        ),
        model=_META,
        form="graph",
    )


def _plan(
    planner: ReadPlanCache,
    query: ValidatedObjectQuery,
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


def test_equal_query_values_share_one_read_plan_but_result_forms_do_not() -> None:
    planner = ReadPlanCache()

    first = _plan(planner, _query())
    equal_value = _plan(planner, _query())
    row_form = _plan(planner, _query(), result_form="row")

    assert equal_value is first
    assert row_form is not first
    assert planner._statistics() == _read_plan._ReadPlanCacheStatistics(16, 2, 1, 2, 0)


def test_equal_dialect_values_with_distinct_identities_do_not_share_a_read_plan() -> None:
    planner = ReadPlanCache()
    equivalent_dialect = replace(POSTGRES)

    first = _plan(planner, _query(), dialect=POSTGRES)
    second = _plan(planner, _query(), dialect=equivalent_dialect)

    assert equivalent_dialect == POSTGRES
    assert equivalent_dialect is not POSTGRES
    assert second is not first
    assert planner._statistics().misses == 2


def test_query_key_freezing_normalizes_order_without_erasing_container_types() -> None:
    frozen = cast("Callable[[object], object]", vars(_read_plan)["_frozen_query_value"])

    assert frozen({"values": {3, 1, 2}}) == frozen({"values": {2, 3, 1}})
    assert frozen({"values": {3, 1, 2}}) != frozen({"values": frozenset((2, 3, 1))})
    assert frozen([1, 2]) != frozen((1, 2))
    assert frozen(True) != frozen(1)
    assert frozen(1) != frozen(1.0)


class _HashCountingString(str):
    hashes = 0

    def __hash__(self) -> int:
        type(self).hashes += 1
        return str.__hash__(self)


def _key(query: ValidatedObjectQuery, **fields: Any) -> _read_plan._ReadPlanKey:
    values: dict[str, Any] = {
        "edition": "edition-a",
        "model": _MODEL,
        "dialect": POSTGRES,
        "query": query,
        "result_form": "instance",
        "preference": None,
    }
    return _read_plan._read_plan_key(**(values | fields))


def _counting_authored_freezes(
    monkeypatch: pytest.MonkeyPatch, authored_type: type
) -> dict[str, int]:
    frozen = cast("Callable[[object], object]", vars(_read_plan)["_frozen_query_value"])
    counts = {"authored": 0}

    def counting(value: object) -> object:
        if type(value) is authored_type:
            counts["authored"] += 1
        return frozen(value)

    monkeypatch.setattr(_read_plan, "_frozen_query_value", counting)
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


def test_a_read_plan_key_hashes_its_frozen_query_once() -> None:
    literal = _HashCountingString("counted")
    selected = _name_query(literal)
    _HashCountingString.hashes = 0

    key = _key(selected)
    constructed = _HashCountingString.hashes
    lookups = {key: 1}
    for _ in range(4):
        assert lookups[key] == 1
        hash(key)

    assert constructed == 1
    assert _HashCountingString.hashes == 1


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
    for distinct in (
        _key(_query(2)),
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
    def selected(**clauses: object) -> ValidatedObjectQuery:
        authored = {"target": "Order", "predicate": {"eq": {"attr": "Order.id", "value": 1}}}
        return preflight(deserialize(authored | clauses), model=_META, form="graph")

    assert not _key(selected(limit=3)).same_family(_key(selected()))
    assert not _key(selected(limit=3)).same_family(_key(selected(limit=5)))
    assert _key(selected(limit=3)) == _key(selected(limit=3))


@pytest.mark.parametrize("paged", [False, True])
def test_hits_and_cold_builds_freeze_the_authored_query_once_per_lookup(
    monkeypatch: pytest.MonkeyPatch,
    paged: bool,
) -> None:
    selected = (
        continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)
        if paged
        else _query()
    )
    counts = _counting_authored_freezes(monkeypatch, type(selected.authored))
    cache = ReadPlanCache()

    _plan(cache, selected)
    assert counts["authored"] == 1
    _plan(cache, selected)
    assert counts["authored"] == 2
    assert cache._statistics().hits == 1


def test_a_warm_hit_hashes_its_frozen_query_only_at_key_construction() -> None:
    cache = ReadPlanCache()
    _plan(cache, _name_query(_HashCountingString("counted")))
    warm = _name_query(_HashCountingString("counted"))
    _HashCountingString.hashes = 0

    _plan(cache, warm)

    assert cache._statistics().hits == 1
    assert _HashCountingString.hashes == 1


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
    assert after.root_read()[1] is not first.root_read()[1]
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
    _plan(cache, _query(2))
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

    assert all(value is prepared[0] for value in prepared)
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
    cold_root, cold_rows = cold.root_read()
    warm_root, warm_rows = warm.root_read()
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
    assert second.root_read()[0].statement == first.root_read()[0].statement
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
        "_FrozenQuery",
        "_Identity",
        "_frozen_query_value",
        "null_pattern",
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

    assert 1 in planned.root_read()[0].statement.binds
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

    after_one_root, after_one_rows = after_one.root_read()
    after_two_root, after_two_rows = after_two.root_read()
    assert first.root_read()[1] is not after_one_rows
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

    three_root, _ = three.root_read()
    five_root, _ = five.root_read()
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
    assert 1 in standalone.root_read()[0].statement.binds
    assert 1 in locking.root_read()[0].statement.binds
    assert cache._statistics().misses == 2


def test_continuation_planning_rejects_a_compiler_that_drops_coordinate_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_read = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])

    def dropping_markers(*args: Any, **kwargs: Any) -> Any:
        compiled = compile_read(*args, **kwargs)
        binds = tuple(0 if type(value) is object else value for value in compiled.statement.binds)
        return replace(compiled, statement=replace(compiled.statement, binds=binds))

    monkeypatch.setattr(_read_plan, "compile_read", dropping_markers)
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    with pytest.raises(ValueError, match="lost a non-null coordinate bind"):
        _plan(ReadPlanCache(), continued)


def test_continuation_planning_rejects_a_compiler_that_drops_the_limit_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_read = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])

    def dropping_limit(*args: Any, **kwargs: Any) -> Any:
        compiled = compile_read(*args, **kwargs)
        binds = list(compiled.statement.binds)
        marker_positions = [index for index, value in enumerate(binds) if type(value) is object]
        limit_marker = binds[marker_positions[-1]]
        binds = [0 if value is limit_marker else value for value in binds]
        return replace(compiled, statement=replace(compiled.statement, binds=tuple(binds)))

    monkeypatch.setattr(_read_plan, "compile_read", dropping_limit)
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    with pytest.raises(ValueError, match="lost its page limit bind"):
        _plan(ReadPlanCache(), continued)


def test_editions_and_exact_models_are_isolated_without_invalidating_each_other() -> None:
    cache = ReadPlanCache()
    query = _query()

    first = _plan(cache, query)
    next_edition = _plan(cache, query, edition="edition-b")
    next_model = _plan(cache, query, edition="edition-b", model=CatalogedModel(_META))

    assert next_edition is not first
    assert next_model is not next_edition
    assert _plan(cache, query) is first
    assert cache._statistics().size == 3


def test_recent_use_controls_true_lru_eviction() -> None:
    cache = ReadPlanCache(capacity=2)
    one = _plan(cache, _query(1))
    two = _plan(cache, _query(2))

    assert _plan(cache, _query(1)) is one
    _plan(cache, _query(3))
    two_again = _plan(cache, _query(2))

    assert two_again is not two
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
    assert all(value is prepared[0] for value in prepared)
    assert cache._statistics().misses == 1
    assert cache._statistics().hits == 7


def test_a_back_reference_has_no_executable_child_read() -> None:
    plan = replace(_plan(ReadPlanCache(), _query()), _fetches=(None,))

    with pytest.raises(ValueError, match="executable fetch step"):
        plan.fetch_read(0, ())


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
    requests: tuple[tuple[str, int], ...] = (
        ("edition-a", 1),
        ("edition-a", 2),
        ("edition-b", 1),
        ("edition-b", 2),
    )

    def plan_request(item: tuple[str, int]) -> _read_plan.ReadPlan:
        edition, value = item
        return _plan(cache, _query(value), edition=edition)

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
    compile_read = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])
    bind = cast("Callable[..., Any]", vars(_read_plan)["bind"])

    def counting_plan(*args: Any, **kwargs: Any) -> Any:
        calls["plan"] += 1
        return plan(*args, **kwargs)

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        calls["compile"] += 1
        return compile_read(*args, **kwargs)

    def counting_bind(*args: Any, **kwargs: Any) -> Any:
        calls["bind"] += 1
        return bind(*args, **kwargs)

    monkeypatch.setattr(deep_fetch_module, "plan", counting_plan)
    monkeypatch.setattr(_read_plan, "compile_read", counting_compile)
    monkeypatch.setattr(_read_plan, "bind", counting_bind)
    cache = ReadPlanCache()

    cold = _plan(cache, _query())
    warm = _plan(cache, _query())

    assert warm is cold
    assert warm.include_tree() is cold.include_tree()
    assert calls == {"plan": 1, "compile": 1, "bind": 1}


def test_database_transactions_share_read_plans_across_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = 0
    compile_read = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        nonlocal compiled
        compiled += 1
        return compile_read(*args, **kwargs)

    monkeypatch.setattr(_read_plan, "compile_read", counting_compile)
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


@pytest.mark.parametrize(("capacity", "expected_compilations"), [(0, 2), (16, 1)])
def test_public_capacity_zero_disables_cross_delivery_reuse_without_bypassing_planning(
    monkeypatch: pytest.MonkeyPatch,
    capacity: int,
    expected_compilations: int,
) -> None:
    compiled = 0
    compile_read = cast("Callable[..., Any]", vars(_read_plan)["compile_read"])

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        nonlocal compiled
        compiled += 1
        return compile_read(*args, **kwargs)

    monkeypatch.setattr(_read_plan, "compile_read", counting_compile)
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

    assert compiled == expected_compilations


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

    result = find(_query(), _MODEL, port, edition="edition-a", planner=cache)
    assert result.page.root_count == 1
    assert not _reaches(cache, port)
    assert not _reaches(cache, stored_row)
    assert not _reaches(cache, result)
    assert not _reaches(cache, result.page)
    assert not _reaches(cache, result.sources)
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
