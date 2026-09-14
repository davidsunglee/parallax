from __future__ import annotations

import gc
import types
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Literal, cast

import pytest

from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core import continuation
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.core.object_query._validated import ContinuationCoordinate, ValidatedObjectQuery
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle import _preparation
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._preparation import PreparationCache
from parallax.snapshot.handle._read import find
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
        if identity in seen or isinstance(value, atomic) or callable(value):
            continue
        seen.add(identity)
        pending.extend(gc.get_referents(value))
    return False


def _query(value: int = 1) -> ValidatedObjectQuery:
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


def _prepare(
    cache: PreparationCache,
    query: ValidatedObjectQuery,
    *,
    edition: str = "edition-a",
    model: CatalogedModel = _MODEL,
    result_form: Literal["row", "instance"] = "instance",
    preference: Concurrency | None = None,
) -> _preparation.PreparedDelivery:
    return cache.prepare(
        edition=edition,
        model=model,
        dialect=POSTGRES,
        query=query,
        result_form=result_form,
        preference=preference,
    )


def test_equal_query_values_share_one_preparation_but_result_forms_do_not() -> None:
    cache = PreparationCache()

    first = _prepare(cache, _query())
    equal_value = _prepare(cache, _query())
    row_form = _prepare(cache, _query(), result_form="row")

    assert equal_value is first
    assert row_form is not first
    assert cache.stats == _preparation.PreparationCacheStats(4, 2, 1, 2, 0, 0)


def test_query_key_freezing_normalizes_unordered_nested_values() -> None:
    frozen = cast("Callable[[object], object]", vars(_preparation)["_frozen_query_value"])

    assert frozen({"values": {3, 1, 2}}) == frozen({"values": frozenset((2, 3, 1))})


def test_effectively_equal_concurrency_preferences_share_one_entry() -> None:
    cache = PreparationCache()
    query = _query()

    standalone = _prepare(cache, query)
    locking = _prepare(cache, query, preference="locking")
    optimistic = _prepare(cache, query, preference="optimistic")

    assert standalone is not locking
    assert optimistic is locking
    assert cache.stats.size == 2


def test_continuation_values_share_one_null_pattern_template_without_stale_binds() -> None:
    cache = PreparationCache()
    pages = continuation.plan(_query(), _META)
    first = _prepare(cache, pages.first(limit=3))
    after_one = _prepare(cache, pages.after(ContinuationCoordinate((1,)), limit=3))
    after_two = _prepare(cache, pages.after(ContinuationCoordinate((2,)), limit=3))

    assert after_one.children is first.children
    assert after_two.children is first.children
    assert after_two.root_rows is after_one.root_rows
    assert after_two.root.statement.binds != after_one.root.statement.binds
    assert 1 in after_one.root.statement.binds
    assert 2 in after_two.root.statement.binds
    assert cache.stats.size == 2
    assert cache.stats.hits == 1
    assert cache.stats.misses == 2


def test_a_continuation_replans_its_template_for_a_new_effective_lock_variant() -> None:
    cache = PreparationCache()
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    standalone = _prepare(cache, continued)
    locking = _prepare(cache, continued, preference="locking")

    assert standalone is not locking
    assert 1 in standalone.root.statement.binds
    assert 1 in locking.root.statement.binds
    assert cache.stats.misses == 2


def test_continuation_preparation_rejects_a_compiler_that_drops_coordinate_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_read = cast("Callable[..., Any]", vars(_preparation)["compile_read"])

    def dropping_markers(*args: Any, **kwargs: Any) -> Any:
        compiled = compile_read(*args, **kwargs)
        binds = tuple(0 if type(value) is object else value for value in compiled.statement.binds)
        return replace(compiled, statement=replace(compiled.statement, binds=binds))

    monkeypatch.setattr(_preparation, "compile_read", dropping_markers)
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    with pytest.raises(ValueError, match="lost a non-null coordinate bind"):
        _prepare(PreparationCache(), continued)


def test_continuation_preparation_rejects_a_compiler_that_drops_the_limit_bind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compile_read = cast("Callable[..., Any]", vars(_preparation)["compile_read"])

    def dropping_limit(*args: Any, **kwargs: Any) -> Any:
        compiled = compile_read(*args, **kwargs)
        binds = list(compiled.statement.binds)
        marker_positions = [index for index, value in enumerate(binds) if type(value) is object]
        limit_marker = binds[marker_positions[-1]]
        binds = [0 if value is limit_marker else value for value in binds]
        return replace(compiled, statement=replace(compiled.statement, binds=tuple(binds)))

    monkeypatch.setattr(_preparation, "compile_read", dropping_limit)
    continued = continuation.plan(_query(), _META).after(ContinuationCoordinate((1,)), limit=3)

    with pytest.raises(ValueError, match="lost its page limit bind"):
        _prepare(PreparationCache(), continued)


def test_an_edition_or_model_change_invalidates_the_previous_scope() -> None:
    cache = PreparationCache()
    query = _query()

    first = _prepare(cache, query)
    next_edition = _prepare(cache, query, edition="edition-b")
    next_model = _prepare(cache, query, edition="edition-b", model=CatalogedModel(_META))

    assert next_edition is not first
    assert next_model is not next_edition
    assert cache.stats.size == 1
    assert cache.stats.invalidations == 2


def test_recent_use_controls_true_lru_eviction() -> None:
    cache = PreparationCache(capacity=2)
    one = _prepare(cache, _query(1))
    two = _prepare(cache, _query(2))

    assert _prepare(cache, _query(1)) is one
    _prepare(cache, _query(3))
    two_again = _prepare(cache, _query(2))

    assert two_again is not two
    assert cache.stats == _preparation.PreparationCacheStats(2, 2, 1, 4, 2, 0)


def test_concurrent_cold_callers_prepare_one_shared_value() -> None:
    cache = PreparationCache()
    query = _query()

    def prepare(_index: int) -> _preparation.PreparedDelivery:
        return _prepare(cache, query)

    with ThreadPoolExecutor(max_workers=8) as pool:
        prepared = tuple(pool.map(prepare, range(16)))

    assert all(value is prepared[0] for value in prepared)
    assert cache.stats.misses == 1
    assert cache.stats.hits == 15


def test_a_warm_hit_repeats_no_planning_compilation_or_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"plan": 0, "compile": 0, "bind": 0}
    deep_fetch_module = vars(_preparation)["deep_fetch"]
    plan = cast("Callable[..., Any]", deep_fetch_module.plan)
    compile_read = cast("Callable[..., Any]", vars(_preparation)["compile_read"])
    bind = cast("Callable[..., Any]", vars(_preparation)["bind"])

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
    monkeypatch.setattr(_preparation, "compile_read", counting_compile)
    monkeypatch.setattr(_preparation, "bind", counting_bind)
    cache = PreparationCache()

    cold = _prepare(cache, _query())
    warm = _prepare(cache, _query())

    assert warm is cold
    assert calls == {"plan": 1, "compile": 1, "bind": 1}


def test_database_transactions_share_preparation_across_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled = 0
    compile_read = cast("Callable[..., Any]", vars(_preparation)["compile_read"])

    def counting_compile(*args: Any, **kwargs: Any) -> Any:
        nonlocal compiled
        compiled += 1
        return compile_read(*args, **kwargs)

    monkeypatch.setattr(_preparation, "compile_read", counting_compile)
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

    with db_for(ORDERS_MODEL, adapter) as database:
        query = Order.where(Order.id == 1)
        database.transact(lambda transaction: transaction.find(query).result())
        database.transact(lambda transaction: transaction.find(query).result())

    assert adapter.acquisitions == 2
    assert compiled == 1


def test_preparation_retains_no_connection_rows_page_evidence_or_result() -> None:
    cache = PreparationCache()
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

    result = find(_query(), _MODEL, port, edition="edition-a", cache=cache)
    assert result.page.root_count == 1
    assert not _reaches(cache, port)
    assert not _reaches(cache, stored_row)
    assert not _reaches(cache, result)
    assert not _reaches(cache, result.page)
    assert not _reaches(cache, result.sources)
    del result, port
    gc.collect()

    assert retained() is None
    assert cache.stats.size == 1


@pytest.mark.parametrize("capacity", [True, 0, -1, 1.5])
def test_capacity_requires_a_positive_built_in_integer(capacity: object) -> None:
    with pytest.raises(ValueError, match="positive built-in int"):
        PreparationCache(cast("int", capacity))
