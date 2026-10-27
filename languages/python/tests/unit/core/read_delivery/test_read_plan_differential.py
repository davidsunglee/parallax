# pyright: reportPrivateUsage=false

from __future__ import annotations

import pytest

from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._read_plan import EmptyRead, ReadPlan, ReadPlanCache
from parallax.core.sql_gen._compile import CompiledRead
from tests._support.case_corpus import cases
from tests._support.sweep_goldens import assert_wire_binds, read_golden_statements
from tests.unit.core.read_delivery._read_plan_differential import (
    CorpusRead,
    corpus_read,
    observed,
    selects_a_finite_instant,
    varied,
)

_CORPUS_READS = [corpus_read(case) for case in cases() if case.shape == "read"]
# Finite temporal selections still key their plans by value, so a variant of
# one would plan apart rather than render from the seeded template.
_READS = [read for read in _CORPUS_READS if not selects_a_finite_instant(read.query)]


def _plan(
    planner: ReadPlanCache, model: CatalogedModel, read: CorpusRead, query: ResolvedObjectQuery
) -> ReadPlan:
    return planner.plan(
        edition="edition-a",
        model=model,
        dialect=POSTGRES,
        query=query,
        result_form=read.result_form,
        preference=None,
    )


def _root(plan: ReadPlan) -> CompiledRead | EmptyRead:
    root = plan.root_read()
    return root if isinstance(root, EmptyRead) else root[0]


def test_every_corpus_read_resolves_and_is_selected_unless_it_selects_a_finite_instant() -> None:
    selected = {read.case.case_id for read in _READS}
    temporal = {read.case.case_id for read in _CORPUS_READS if read.case.case_id not in selected}

    assert len(_CORPUS_READS) == len({case.case_id for case in cases() if case.shape == "read"})
    assert selected and temporal
    assert all(
        selects_a_finite_instant(read.query)
        for read in _CORPUS_READS
        if read.case.case_id in temporal
    )


@pytest.mark.parametrize("read", _READS, ids=[read.case.case_id for read in _READS])
def test_a_read_rendered_from_a_template_seeded_by_other_values_is_its_cold_plan(
    read: CorpusRead,
) -> None:
    cache = ReadPlanCache()
    model = CatalogedModel(read.meta)
    seed = varied(read.query)

    seeded = _plan(cache, model, read, seed)
    rendered = _plan(cache, model, read, read.query)

    assert (cache._statistics().misses, cache._statistics().hits) == (1, 1)
    cold, cold_seed = (
        _root(_plan(ReadPlanCache(0), model, read, query)) for query in (read.query, seed)
    )
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
    if read.golden_applies:
        ((golden_sql, golden_binds),) = read_golden_statements(read.case)
        assert root.statement.sql == golden_sql
        assert_wire_binds(read.meta, golden_sql, golden_binds, list(root.statement.wire_binds()))
