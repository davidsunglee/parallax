# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace

import pytest

from parallax.core import deep_fetch
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._read_plan import EmptyRead, ReadPlan, ReadPlanCache
from parallax.core.sql_gen._compile import CompiledRead
from tests._support.case_corpus import cases
from tests._support.sweep_goldens import assert_wire_binds, read_golden_statements
from tests.unit.core.read_delivery._read_plan_differential import (
    CorpusRead,
    corpus_read,
    key_sets,
    observed,
    varied,
)

_READ_CASES = [case for case in cases() if case.shape == "read"]
_CORPUS_READS = [corpus_read(case) for case in _READ_CASES]
_MARIADB = replace(POSTGRES, name="mariadb")
_DIALECTS = pytest.mark.parametrize("dialect", [POSTGRES, _MARIADB], ids=["postgres", "mariadb"])


def _plan(
    planner: ReadPlanCache,
    model: CatalogedModel,
    read: CorpusRead,
    query: ResolvedObjectQuery,
    dialect: Dialect,
) -> ReadPlan:
    return planner.plan(
        edition="edition-a",
        model=model,
        dialect=dialect,
        query=query,
        result_form=read.result_form,
        preference=None,
    )


def _root(plan: ReadPlan) -> CompiledRead | EmptyRead:
    root = plan.root_read()
    return root if isinstance(root, EmptyRead) else root[0]


def test_every_corpus_read_case_plans_a_root_or_an_empty_read() -> None:
    roots = [
        _root(_plan(ReadPlanCache(0), CatalogedModel(read.meta), read, read.query, POSTGRES))
        for read in _CORPUS_READS
    ]
    empty = [root for root in roots if isinstance(root, EmptyRead)]

    assert [read.case.case_id for read in _CORPUS_READS] == [case.case_id for case in _READ_CASES]
    assert empty and len(empty) < len(roots)
    assert all(isinstance(root, EmptyRead | CompiledRead) for root in roots)


def _assert_children_render_as_fresh_reads(
    plan: ReadPlan, cold: ReadPlan, query: ResolvedObjectQuery
) -> None:
    """Each child level ``plan`` retained renders ``query`` and two key sets
    exactly as ``cold``'s freshly compiled level does."""
    assert plan.fetch_count == cold.fetch_count
    for index in range(plan.fetch_count):
        prepared, fresh = plan.prepared_fetch(index), cold.prepared_fetch(index)
        if not isinstance(prepared, tuple):
            assert prepared == fresh
            continue
        assert isinstance(fresh, tuple)
        step = plan.fetch_step(index)
        assert isinstance(step, deep_fetch.QueryFetchStep)
        for keys in key_sets(step.related.member.type):
            rendered = prepared[0].render(list(keys), query=query)
            assert observed(rendered) == observed(fresh[0].render(list(keys), query=query))
            assert rendered.statement.execution_value_positions() == ()


@_DIALECTS
@pytest.mark.parametrize("read", _CORPUS_READS, ids=[read.case.case_id for read in _CORPUS_READS])
def test_a_read_rendered_from_a_template_seeded_by_other_values_is_its_cold_plan(
    read: CorpusRead, dialect: Dialect
) -> None:
    cache = ReadPlanCache()
    model = CatalogedModel(read.meta)
    seed = varied(read.query)

    seeded = _plan(cache, model, read, seed, dialect)
    rendered = _plan(cache, model, read, read.query, dialect)

    assert (cache._statistics().misses, cache._statistics().hits) == (1, 1)
    cold_plan, cold_seed_plan = (
        _plan(ReadPlanCache(0), model, read, query, dialect) for query in (read.query, seed)
    )
    _assert_children_render_as_fresh_reads(rendered, cold_plan, read.query)
    _assert_children_render_as_fresh_reads(seeded, cold_seed_plan, seed)
    cold, cold_seed = _root(cold_plan), _root(cold_seed_plan)
    root, seed_root = _root(rendered), _root(seeded)
    if isinstance(cold, EmptyRead):
        assert root is cold_seed is seed_root is cold
        assert not any(entry.root_template for entry in cache._entries.values())
        return
    assert not isinstance(root, EmptyRead)
    assert not isinstance(seed_root, EmptyRead)
    assert not isinstance(cold_seed, EmptyRead)
    assert observed(root) == observed(cold)
    assert observed(seed_root) == observed(cold_seed)
    assert root.statement.execution_value_positions() == ()
    if read.golden_applies and dialect is POSTGRES:
        ((golden_sql, golden_binds),) = read_golden_statements(read.case)
        assert root.statement.sql == golden_sql
        assert_wire_binds(read.meta, golden_sql, golden_binds, list(root.statement.wire_binds()))
