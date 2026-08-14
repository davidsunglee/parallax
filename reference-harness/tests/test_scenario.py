"""Unit tests for the m-unit-work scenario machinery (no database).

These pin the DB-free invariants of a cache / identity scenario case: the
per-step round-trip / golden-SQL count consistency (each step's declared
roundTrips equals the golden SQL statements it lists; the steps total the
case-level roundTrips), and that a cache-hit step lists no golden SQL. The full
execute-and-assert behavior (cache-hit reuse, identity, read-lock, batched write)
is exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, Entity, discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_action_on,
    _assert_scenario,
    _assert_scenario_count_consistency,
    _assert_scenario_normalization,
    _assert_scenario_reference_sql,
    _assert_scenario_settled_write,
    _assert_scenario_source_finds,
    _assert_scenario_sql_bookkeeping,
    _assert_settled_version_binds,
    _relationship_path_target,
    _reuse_prior_rows,
    _scenario_step_read_entity,
    _scenario_uow_groups,
    _uow_group_is_doomed,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _scenario_cases():
    return [c for c in discover_cases(COMPATIBILITY_ROOT) if c.is_scenario]


def test_scenario_cases_are_discovered_and_self_describe() -> None:
    cases = _scenario_cases()
    assert cases, "no scenario cases discovered"
    for case in cases:
        # Each carries a scenario (ordered steps) and no top-level query.
        assert case.scenario
        assert "objectQuery" not in case.when
        for step in case.scenario:
            assert "roundTrips" in step
            # A step is EXACTLY ONE of a read step (carries `objectQuery`), a write
            # step (carries `write`), or a lifecycle-action step (carries `action`,
            # m-case-format).
            kinds = ("objectQuery" in step) + ("write" in step) + ("action" in step)
            assert kinds == 1, "a scenario step is exactly one of objectQuery / write / action"
            if "write" in step:
                # A committed / rolled-back write lists golden DML; a NO-OP write
                # (a versioned UPDATE that changes no attribute, m-opt-lock) issues no DML,
                # so it declares roundTrips 0 and lists none — like a cache hit.
                if step["roundTrips"] == 0:
                    assert not step.get("statements"), "a no-op write step lists no golden DML"
                else:
                    assert step.get("statements"), (
                        "a write step with round trips must list golden DML"
                    )


def test_cache_hit_scenario_has_a_zero_round_trip_step() -> None:
    case = next(c for c in _scenario_cases() if "cache-hit" in c.tags)
    # A cache-hit scenario must contain a step that costs zero round trips and
    # lists no golden SQL (it is served from the query cache).
    hits = [s for s in case.scenario if s["roundTrips"] == 0]
    assert hits, "cache-hit scenario has no zero-round-trip (hit) step"
    for hit in hits:
        assert not hit.get("statements"), "a cache-hit step must list no golden SQL"


def test_rollback_scenario_step_is_discovered_and_self_describes() -> None:
    case = next(
        (c for c in _scenario_cases() if any(step.get("rollback") for step in c.scenario)),
        None,
    )
    assert case is not None, "no rollback scenario case discovered (m-unit-work-002)"
    rollback_steps = [step for step in case.scenario if step.get("rollback")]
    for step in rollback_steps:
        # An ABORTED write step is still a write step that lists golden DML (it is
        # applied then rolled back) and declares its round trips (the DML executes).
        assert "write" in step
        assert step.get("statements"), "a rollback write step must list golden DML"
        assert step["roundTrips"] >= 1
    # The rolled-back step's statements are counted as round trips exactly like a
    # committed write, so the count-consistency check MUST still hold.
    _assert_scenario_count_consistency(case, "postgres")


def test_no_op_write_scenario_step_is_discovered_and_self_describes() -> None:
    case = next(
        (
            c
            for c in _scenario_cases()
            if any("write" in step and step["roundTrips"] == 0 for step in c.scenario)
        ),
        None,
    )
    assert case is not None, "no no-op-write scenario case discovered (m-opt-lock-001)"
    no_op_steps = [s for s in case.scenario if "write" in s and s["roundTrips"] == 0]
    for step in no_op_steps:
        # A NO-OP write (a versioned UPDATE that changes no attribute, m-opt-lock) issues
        # NO DML: it lists no golden SQL and costs zero round trips, mirroring a
        # cache-hit read step.
        assert not step.get("statements"), "a no-op write step must list no golden DML"
    # The zero-round-trip write step keeps the count-consistency check green.
    _assert_scenario_count_consistency(case, "postgres")


def _scenario_by_id(prefix: str):
    return next(c for c in _scenario_cases() if c.path.stem.startswith(prefix))


def test_read_your_own_writes_update_scenario_flushes_before_dependent_find() -> None:
    # m-unit-work-005: an OBSERVING find, then a committed UPDATE that advances from
    # that observation, then a dependent find that MUST observe the new value
    # (read-your-own-writes for UPDATE; `m-opt-lock`'s prior-observation rule).
    case = _scenario_by_id("m-unit-work-005")
    observe, write, find = case.scenario
    assert observe["expectRows"] == [{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}]
    # The write step carries the structured keyed buffer (D-3 migration): a single
    # keyed UPDATE of account 1 (no row-carried version — the advance derives from
    # the observing find), its golden SQL unchanged.
    (instruction,) = write["write"]
    assert instruction["mutation"] == "update"
    assert instruction["entity"] == "parallax.compatibility.Account"
    assert instruction["rows"] == [{"id": 1, "balance": 175.00}]
    update_sql = write["statements"][0]["sql"]["postgres"]
    assert update_sql.startswith("update account set")
    assert "objectQuery" in find
    # The dependent find asserts the flushed new balance/version (the RYOW observable).
    assert find["expectRows"] == [{"id": 1, "owner": "Ada", "balance": 175.00, "version": 2}]
    _assert_scenario_count_consistency(case, "postgres")


def test_read_your_own_writes_delete_scenario_observes_absence() -> None:
    # m-unit-work-006: an OBSERVING find, then a committed DELETE of that observed
    # row, then a dependent find that MUST observe the row's ABSENCE
    # (read-your-own-writes for DELETE; `m-opt-lock`'s prior-observation rule).
    case = _scenario_by_id("m-unit-work-006")
    observe, write, find = case.scenario
    assert observe["expectRows"] == [{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}]
    # The write step carries the structured keyed buffer (D-3 migration): a single
    # keyed DELETE of account 3, gated on the observed version under the case's
    # default preference (the observation licenses the write; the gate follows the
    # target's own Effective Concurrency Strategy).
    (instruction,) = write["write"]
    assert instruction["mutation"] == "delete"
    assert instruction["entity"] == "parallax.compatibility.Account"
    assert instruction["rows"] == [{"id": 3}]
    assert (
        write["statements"][0]["sql"]["postgres"]
        == "delete from account where id = ? and version = ?"
    )
    # The dependent find returns ZERO rows — the deletion is visible.
    assert find["expectRows"] == []
    _assert_scenario_count_consistency(case, "postgres")


def test_insert_update_combining_scenario_emits_exactly_one_insert() -> None:
    # m-unit-work-008: a buffered insert + a buffered update of the same new object
    # COMBINE into exactly ONE INSERT with the final values — no intervening UPDATE.
    case = _scenario_by_id("m-unit-work-008")
    write = case.scenario[0]
    assert "write" in write
    statements = write["statements"]
    assert len(statements) == 1, "combining must emit exactly one statement"
    sql = statements[0]["sql"]["postgres"]
    assert sql.startswith("insert into account") and "update" not in sql
    # The single INSERT carries the FINAL (post-combine) balance, not the initial one.
    assert statements[0]["binds"] == [8, "Turing", 99.00, 1]
    _assert_scenario_count_consistency(case, "postgres")


def test_scenario_count_consistency_holds_for_authored_cases() -> None:
    for case in _scenario_cases():
        # Must not raise: per-step counts match the golden SQL and total roundTrips.
        _assert_scenario_count_consistency(case, "postgres")


def test_scenario_step_count_mismatch_is_rejected() -> None:
    case = copy.deepcopy(next(iter(_scenario_cases())))
    # Corrupt a step's declared roundTrips so it no longer matches the golden SQL
    # statement count it lists; the consistency check MUST fail.
    case.when["scenario"][0]["roundTrips"] += 1
    with pytest.raises(CaseFailure):
        _assert_scenario_count_consistency(case, "postgres")


def test_scenario_total_mismatch_is_rejected() -> None:
    case = copy.deepcopy(next(iter(_scenario_cases())))
    # Corrupt the case-level roundTrips so it no longer equals the per-step sum.
    case.then["roundTrips"] += 1
    with pytest.raises(CaseFailure):
        _assert_scenario_count_consistency(case, "postgres")


# --- per-scenario read reference SQL -----------------------------------------


class _ReferenceDb:
    dialect = "postgres"

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[object]]] = []

    def query(self, statement: str, binds: Sequence[object] = ()) -> list[dict[str, object]]:
        self.calls.append((statement, list(binds)))
        return self.rows


def test_scenario_read_reference_sql_is_a_bind_free_naive_oracle() -> None:
    case = copy.deepcopy(_scenario_by_id("m-opt-lock-003"))
    step = case.scenario[0]
    step["referenceSql"] = "select id from account where balance < 200.00"
    expected = [{"id": 1}, {"id": 3}]
    db = _ReferenceDb(expected)

    _assert_scenario_reference_sql(case, db, 0, step, expected)  # type: ignore[arg-type]

    assert db.calls == [("select id from account where balance < 200.00", [])]


def test_scenario_read_reference_sql_mismatch_fails_loudly() -> None:
    case = copy.deepcopy(_scenario_by_id("m-opt-lock-003"))
    step = case.scenario[0]
    step["referenceSql"] = "select id from account where balance < 200.00"

    with pytest.raises(CaseFailure, match="referenceSql rows != golden rows"):
        _assert_scenario_reference_sql(
            case,
            _ReferenceDb([]),  # type: ignore[arg-type]
            0,
            step,
            [{"id": 1}],
        )


def test_scenario_reference_sql_map_must_cover_its_golden_dialects() -> None:
    case = copy.deepcopy(_scenario_by_id("m-opt-lock-003"))
    case.scenario[0]["referenceSql"] = {"mariadb": "select id from account"}

    with pytest.raises(CaseFailure, match="referenceSql map keys"):
        _assert_scenario_sql_bookkeeping(case)


def test_scenario_read_golden_sql_must_be_canonical() -> None:
    case = copy.deepcopy(_scenario_by_id("m-opt-lock-003"))
    case.scenario[0]["statements"][0]["sql"]["postgres"] = "SELECT t0.id FROM account t0"

    with pytest.raises(CaseFailure, match="not canonical"):
        _assert_scenario_normalization(case, "postgres")


# --- zero-round-trip reuse: loud failure vs the ONE legitimate empty case -------
#
# `_reuse_prior_rows` must fail LOUDLY when a zero-round-trip step names a source
# that does not resolve (an empty reuse would let its identity / expectRows
# assertion pass vacuously), while still permitting the query-backed list
# CONSTRUCTION that has not resolved yet (m-op-list-001 step 0 — no named source,
# no non-empty assertion).


def _any_case():
    """A discovered case whose `path.name` the reuse / on helpers cite in errors."""
    return next(iter(_scenario_cases()))


def test_reuse_prior_rows_permits_unresolved_construction() -> None:
    # A construction step (m-op-list-001 step 0): roundTrips 0, no golden SQL, no
    # named source, and asserts nothing — it reuses the empty set until first access.
    construction = {
        "objectQuery": {"target": "Order", "predicate": {"all": {}}},
        "roundTrips": 0,
    }
    assert _reuse_prior_rows(_any_case(), construction, 0, []) == []


def test_reuse_prior_rows_raises_on_unresolved_named_source() -> None:
    # A re-access whose `on` names a step that does not exist yet: the pre-refactor
    # loud failure, restored — never a silent empty reuse.
    step = {"action": "access", "on": 5, "roundTrips": 0}
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 1, [[{"id": 1}]])


def test_reuse_prior_rows_raises_on_forward_same_object_as() -> None:
    # `sameObjectAs` pointing at the current (or a later) step cannot resolve to an
    # EARLIER result; the reuse MUST fail loudly rather than return [].
    step = {"action": "access", "on": 0, "sameObjectAs": 2, "roundTrips": 0}
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 2, [[{"id": 1}], []])


def test_reuse_prior_rows_rejects_construction_asserting_rows() -> None:
    # A no-source zero-round-trip step that asserts NON-EMPTY rows is not a valid
    # construction — a construction resolves no rows yet, so this fails loudly.
    step = {
        "objectQuery": {"target": "Order", "predicate": {"all": {}}},
        "roundTrips": 0,
        "expectRows": [{"id": 1}],
    }
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 0, [])


# --- action `on` validation: earlier, in-range, unique --------------------------


def test_assert_action_on_accepts_earlier_unique_indices() -> None:
    # A coordinate-grouped load over two earlier sources, one statement group each.
    step = {"action": "load", "on": [0, 1], "path": "lines", "roundTrips": 2}
    pairs = [("select ...", [1]), ("select ...", [2])]
    _assert_action_on(_any_case(), 2, step, pairs)  # must not raise


def test_assert_action_on_rejects_forward_or_self_index() -> None:
    # `on` must name an EARLIER step — a self / forward index is an authoring error.
    step = {"action": "load", "on": 2, "path": "items", "roundTrips": 1}
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, [("select ...", [])])


def test_assert_action_on_rejects_duplicate_index() -> None:
    # The array form is unique — a source is referenced at most once.
    step = {"action": "load", "on": [0, 0], "path": "lines", "roundTrips": 1}
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, [("select ...", [])])


def test_assert_action_on_rejects_more_groups_than_sources() -> None:
    # A coordinate-grouped load must not run MORE statement groups than the sources
    # it references — every executed group is accounted for by a referenced source.
    step = {"action": "load", "on": [0, 1], "path": "lines", "roundTrips": 3}
    pairs = [("select ...", [1]), ("select ...", [2]), ("select ...", [3])]
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, pairs)


# --- per-step read-entity resolution (value-object decode uses the RIGHT entity) ---
#
# `_assert_scenario` decodes each step's rows with the entity that step actually
# read — a find's own query `target`, a load / access path's terminal entity, a
# path-less query-backed-list access's source entity — so a value-object-bearing child
# materializes with its OWN composite schema, never the scenario root's. These pin
# the resolver on the real corpus scenarios that exercise each shape.


def test_relationship_path_target_walks_each_hop() -> None:
    # A single hop lands on the relationship's target; a dotted multi-hop path walks
    # each hop to the terminal entity whose value-object schema decodes the rows.
    case = _scenario_by_id("m-deep-fetch-015")
    order = case.model.entity("Order")
    assert _relationship_path_target(case, order, "items").name == "OrderItem"
    assert _relationship_path_target(case, order, "items.statuses").name == "OrderStatus"


def test_scenario_find_step_read_entity_is_its_own_query_target() -> None:
    # A read step decodes with its query's own `target`, not the scenario root.
    case = _scenario_by_id("m-deep-fetch-015")
    entity = _scenario_step_read_entity(case, case.scenario[0], [])
    assert entity is not None and entity.name == "Order"


def test_scenario_load_step_read_entity_walks_the_relationship_path() -> None:
    # m-deep-fetch-015 step 1: `load` of `items.statuses` from the step-0 orders ->
    # the terminal OrderStatus, whose value-object schema decodes its rows.
    case = _scenario_by_id("m-deep-fetch-015")
    entity = _scenario_step_read_entity(case, case.scenario[1], [case.model.entity("Order")])
    assert entity is not None and entity.name == "OrderStatus"


def test_scenario_coordinate_grouped_load_resolves_from_first_source() -> None:
    # m-deep-fetch-014 step 2: `load` of `lines` over an ARRAY `on: [0, 1]` (two
    # pinned invoice views) -> the terminal InvoiceLine, resolved from the first
    # source (the grouped coordinates share one source entity).
    case = _scenario_by_id("m-deep-fetch-014")
    invoice = case.model.entity("Invoice")
    entity = _scenario_step_read_entity(case, case.scenario[2], [invoice, invoice])
    assert entity is not None and entity.name == "InvoiceLine"


def test_scenario_operation_list_access_resolves_the_list_entity() -> None:
    # m-op-list-001 step 1: a path-LESS `access` of the step-0 constructed list ->
    # the list's own (source) entity, Order.
    case = _scenario_by_id("m-op-list-001")
    entity = _scenario_step_read_entity(case, case.scenario[1], [case.model.entity("Order")])
    assert entity is not None and entity.name == "Order"


def test_scenario_non_read_action_step_reads_no_entity() -> None:
    # A boundary / DML action (flush / commit / mutate) observes no rows, so it
    # resolves no read entity and decodes nothing.
    case = _any_case()
    assert _scenario_step_read_entity(case, {"action": "flush", "roundTrips": 0}, []) is None


# --- `uow` scenario-step grouping --------------------------------------------
#
# The DB-free bookkeeping (:func:`_scenario_uow_groups` / :func:`_uow_group_is_
# doomed`) is pinned directly on the corpus's own re-authored cases; the
# EXECUTION semantics (grouped read-your-own-writes visibility, group
# rollback, interleaved groups) are pinned against a FAKE `DatabaseProvider`
# whose `open_session()` yields canned, call-recording sessions — no database,
# but the SAME `_assert_scenario` the real Postgres/MariaDB suite drives. Real
# in-transaction correctness (the five re-authored `m-unit-work` cases plus
# `m-opt-lock-012`, on BOTH dialects) is `test_compatibility.py`'s job.


def test_scenario_uow_groups_finds_the_five_reauthored_spans() -> None:
    # The grouped m-unit-work cases cover -002's
    # doomed pair, -005/-006's three-step commit spans, -009's four-step span,
    # -012's doomed triple (its post-abort find stays UNGROUPED).
    assert _scenario_uow_groups(_scenario_by_id("m-unit-work-002")) == {"doomed-update": [0, 1]}
    assert _scenario_uow_groups(_scenario_by_id("m-unit-work-005")) == {
        "observed-update": [0, 1, 2]
    }
    assert _scenario_uow_groups(_scenario_by_id("m-unit-work-006")) == {
        "observed-delete": [0, 1, 2]
    }
    assert _scenario_uow_groups(_scenario_by_id("m-unit-work-009")) == {"mixed-flush": [0, 1, 2, 3]}
    groups = _scenario_uow_groups(_scenario_by_id("m-unit-work-012"))
    assert groups == {"doomed-delete": [0, 1, 2]}
    assert 3 not in groups["doomed-delete"]  # the post-abort find stays ungrouped


def test_scenario_uow_groups_ignores_ungrouped_cases() -> None:
    # A case authoring no `uow` key anywhere (the vast majority) reports no
    # groups at all — the opt-in guarantee: no existing case's meaning changes.
    assert _scenario_uow_groups(_scenario_by_id("m-unit-work-001")) == {}


def test_scenario_uow_groups_reports_interleaved_labels_non_contiguous() -> None:
    # m-opt-lock-012's classic optimistic-lock race: `ours` = {0, 3}, `concurrent`
    # = {1, 2} — genuinely interleaved (not sorted/merged), the shape a grouped
    # execution must open TWO independent sessions to honor.
    groups = _scenario_uow_groups(_scenario_by_id("m-opt-lock-012"))
    assert groups == {"ours": [0, 3], "concurrent": [1, 2]}


def test_uow_group_is_doomed_true_only_for_a_rollback_write_in_the_group() -> None:
    case = _scenario_by_id("m-unit-work-002")
    assert _uow_group_is_doomed(case, [0, 1]) is True  # step 1 declares rollback: true
    case5 = _scenario_by_id("m-unit-work-005")
    assert _uow_group_is_doomed(case5, [0, 1, 2]) is False  # commits; no rollback step


class _FakeSession:
    """A canned, call-recording grouped session — the surface `_PgTxSession` /
    `_MariaTxSession` expose (`dialect` / `execute` / `query` / `commit` /
    `rollback`), with pre-programmed `query()` responses so a grouped find's
    read-your-own-writes visibility (including its `referenceSql`
    oracle) is asserted by the TEST, not a real database."""

    dialect = "postgres"

    def __init__(self, query_responses: Sequence[list[dict[str, Any]]] = ()) -> None:
        self._query_responses = list(query_responses)
        self.calls: list[tuple[str, str, list[Any]]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        self.calls.append(("execute", sql, list(binds)))
        return 1

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.calls.append(("query", sql, list(binds)))
        return self._query_responses.pop(0) if self._query_responses else []

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _FakeGroupedDb:
    """A fake `DatabaseProvider` exposing just the surface `_assert_scenario`'s
    grouped path calls (`dialect`, `open_session`) plus the ungrouped path's
    top-level `query`/`execute`, so a scenario mixing grouped and ungrouped
    steps runs end-to-end with NO real database. `open_session()` hands out
    pre-built :class:`_FakeSession` instances in CALL order — proving groups
    open independent sessions exactly when the bookkeeping says they should
    (once per label, on FIRST use; never re-opened for a later step of the
    SAME label).
    """

    dialect = "postgres"

    def __init__(
        self,
        session_responses: Sequence[Sequence[list[dict[str, Any]]]] = (),
        top_responses: Sequence[list[dict[str, Any]]] = (),
    ) -> None:
        self._session_queue = [_FakeSession(r) for r in session_responses]
        self.sessions: list[_FakeSession] = []
        self._top_responses = list(top_responses)
        self.top_calls: list[tuple[str, str, list[Any]]] = []

    @contextmanager
    def open_session(self) -> Iterator[_FakeSession]:
        session = self._session_queue.pop(0)
        self.sessions.append(session)
        yield session

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        self.top_calls.append(("execute", sql, list(binds)))
        return 1

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.top_calls.append(("query", sql, list(binds)))
        return self._top_responses.pop(0) if self._top_responses else []


def test_grouped_scenario_reads_and_writes_on_one_session_then_commits() -> None:
    # m-unit-work-005: one `uow` group spans all three steps (observe find,
    # versioned write, dependent find). The GROUPED find's read-your-own-writes
    # visibility is not asserted here (that needs a real DB — `test_
    # compatibility.py`'s job); this proves the MECHANICS: exactly ONE session
    # opens for the whole group, every step's SQL runs on IT (never the
    # top-level `db`), and it COMMITS once, after its own last step.
    case = _scenario_by_id("m-unit-work-005")
    observe_rows = [{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}]
    dependent_rows = [{"id": 1, "owner": "Ada", "balance": 175.00, "version": 2}]
    db = _FakeGroupedDb(session_responses=[[observe_rows, dependent_rows]])

    _assert_scenario(case, db)  # type: ignore[arg-type]

    assert len(db.sessions) == 1, "the whole group shares ONE session"
    session = db.sessions[0]
    assert [call[0] for call in session.calls] == ["query", "execute", "query"]
    assert session.committed is True
    assert session.rolled_back is False
    assert db.top_calls == [], "no step in a fully-grouped scenario touches the top-level db"


def test_grouped_scenario_doomed_group_rolls_back_the_shared_session() -> None:
    # m-unit-work-002: steps 0-1 share the doomed `doomed-update` group (the
    # write declares `rollback: true`); step 2 (the post-abort find) is
    # UNGROUPED. Proves: ONE session for the doomed pair, it ROLLS BACK (never
    # commits), and the ungrouped post-abort find runs on the top-level `db`
    # instead — a DIFFERENT connection, exactly the abort contract's promise
    # that the aborted group's own connection never serves the re-resolve.
    case = _scenario_by_id("m-unit-work-002")
    observe_rows = [{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}]
    restored_rows = [{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}]
    db = _FakeGroupedDb(session_responses=[[observe_rows]], top_responses=[restored_rows])

    _assert_scenario(case, db)  # type: ignore[arg-type]

    assert len(db.sessions) == 1
    session = db.sessions[0]
    assert [call[0] for call in session.calls] == ["query", "execute"]
    assert session.committed is False
    assert session.rolled_back is True
    assert [call[0] for call in db.top_calls] == ["query"], "the post-abort find is UNGROUPED"


def test_grouped_scenario_interleaved_groups_open_two_independent_sessions() -> None:
    # A synthetic scenario mirroring m-opt-lock-012's shape (the classic
    # optimistic-lock race) WITHOUT its conflict-abort assertion (isolating
    # JUST the interleaving mechanics): group `a` = steps {0, 3}, group `b` =
    # steps {1, 2} — genuinely interleaved. Proves: TWO sessions open, in the
    # order their labels are FIRST seen (`a` then `b`); `b`'s session is used
    # (and closes, committing) entirely BETWEEN `a`'s two steps, while `a`'s
    # own session stays open across that whole span, closing (rolling back)
    # only at ITS OWN last step.
    case = _interleaved_synthetic_case()
    rows_a = [{"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}]
    rows_b = [{"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}]
    db = _FakeGroupedDb(session_responses=[[rows_a], [rows_b]], top_responses=[[]])

    _assert_scenario(case, db)  # type: ignore[arg-type]

    assert len(db.sessions) == 2, "two independent sessions, one per interleaved label"
    session_a, session_b = db.sessions
    assert [call[0] for call in session_a.calls] == ["query", "execute"]
    assert [call[0] for call in session_b.calls] == ["query", "execute"]
    assert session_b.committed is True and session_b.rolled_back is False
    assert session_a.committed is False and session_a.rolled_back is True
    assert [call[0] for call in db.top_calls] == ["query"], "step 4 is ungrouped"


def _interleaved_synthetic_case() -> Case:
    """A minimal scenario case (Account model) whose two `uow` groups
    interleave — the SAME shape `m-opt-lock-012` authors, stripped of
    `then.affectedRows` so `_assert_scenario_conflict_abort` never engages:
    this test isolates the interleaving MECHANICS, not the conflict proof
    (already pinned end-to-end against real Postgres/MariaDB by `test_
    compatibility.py`)."""
    base = _scenario_by_id("m-unit-work-001")

    def find_step(uow: str, value: int) -> dict[str, Any]:
        return {
            "uow": uow,
            "objectQuery": {
                "target": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": value}},
            },
            "roundTrips": 1,
            "statements": [
                {
                    "sql": {
                        "postgres": "select t0.id, t0.owner, t0.balance, t0.version "
                        "from account t0 where t0.id = ?"
                    },
                    "binds": [value],
                }
            ],
        }

    def write_step(uow: str, *, rollback: bool = False) -> dict[str, Any]:
        return {
            "uow": uow,
            "write": [{"mutation": "update", "entity": "Account", "rows": [{"id": 2}]}],
            "rollback": rollback,
            "roundTrips": 1,
            "statements": [
                {
                    "sql": {"postgres": "update account set balance = ? where id = ?"},
                    "binds": [1.0, 2],
                }
            ],
        }

    raw = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                find_step("a", 2),
                find_step("b", 2),
                write_step("b"),
                write_step("a", rollback=True),
                {
                    "objectQuery": {
                        "target": "Account",
                        "predicate": {"eq": {"attr": "Account.id", "value": 9}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "select t0.id, t0.owner, t0.balance, t0.version "
                                "from account t0 where t0.id = ?"
                            },
                            "binds": [9],
                        }
                    ],
                    "expectRows": [],
                },
            ]
        },
        "then": {"roundTrips": 5},
    }
    return Case(
        path=base.path.with_name("m-unit-work-999-synthetic.yaml"), raw=raw, model=base.model
    )


def test_grouped_scenario_reference_sql_oracle_runs_on_the_held_session() -> None:
    # A GROUPED find's `referenceSql`
    # independent oracle must run on the SAME held session as its golden read,
    # not the top-level autocommit `db` — after an uncommitted grouped write the
    # two connections would otherwise observe DIFFERENT states, silently
    # breaking the "independent-but-equivalent" contract. This group applies an
    # UNCOMMITTED write, then a mid-group find carrying `referenceSql`: both the
    # golden read and the oracle draw from the session's OWN queued rows, and
    # the top-level `db` is never touched.
    case = _uncommitted_write_then_reference_sql_synthetic_case()
    rows = [{"id": 2, "owner": "Linus", "balance": 249.00, "version": 1}]
    db = _FakeGroupedDb(session_responses=[[rows, rows]])

    _assert_scenario(case, db)  # type: ignore[arg-type]

    assert len(db.sessions) == 1
    session = db.sessions[0]
    assert [call[0] for call in session.calls] == ["execute", "query", "query"]
    assert session.committed is True
    assert session.rolled_back is False
    assert db.top_calls == [], "the referenceSql oracle must not touch the top-level db"


def _uncommitted_write_then_reference_sql_synthetic_case() -> Case:
    """A minimal scenario case (Account model) whose ONE `uow` group applies an
    UNCOMMITTED write then a mid-group find carrying `referenceSql` — the
    read-your-own-writes oracle shape: both the golden read and
    the independent oracle MUST observe the SAME (uncommitted) in-transaction
    state, so both MUST run on the group's own held session."""
    base = _scenario_by_id("m-unit-work-001")
    raw = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "uow": "g",
                    "write": [{"mutation": "update", "entity": "Account", "rows": [{"id": 2}]}],
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "update account set balance = ? where id = ?"},
                            "binds": [249.00, 2],
                        }
                    ],
                },
                {
                    "uow": "g",
                    "objectQuery": {
                        "target": "Account",
                        "predicate": {"eq": {"attr": "Account.id", "value": 2}},
                    },
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "select t0.id, t0.owner, t0.balance, t0.version "
                                "from account t0 where t0.id = ?"
                            },
                            "binds": [2],
                        }
                    ],
                    "referenceSql": "select * from account where id = 2",
                },
            ]
        },
        "then": {"roundTrips": 2},
    }
    return Case(
        path=base.path.with_name("m-unit-work-998-synthetic.yaml"), raw=raw, model=base.model
    )


# --- settling against a grouped find (m-case-format) ---------------------------
#
# The harness's own arm of the reference: `_assert_scenario_source_finds` decides
# structurally whether a write step may settle against a find at all, and
# `_assert_scenario_settled_write` cross-checks the golden each profile emits —
# a temporal close's address and gate, a versioned write's gate and version
# advance — against the state that find's `expectRows` declare. The second is what
# makes the corpus state the settled observation in two independent places, so
# each degradation below moves ONE of those places and requires the check to
# notice.
#
# Two degradations of the harness ITSELF discriminate the cross-checks. Emptying
# `_assert_scenario_settled_write` must fail every one of them and nothing else.
# Resolving `_settled_milestone` from the group's LAST find instead of the named
# one — the identity-keying mistake the whole reference exists to catch — must
# fail the authored case's own cross-check while letting the wrong-rectangle
# golden pass; that pair is what shows the check reads the find the write named
# rather than any find.


def _settled_case():
    return copy.deepcopy(_scenario_by_id("m-unit-work-015"))


def test_settled_close_cross_check_holds_for_the_authored_case() -> None:
    # Must not raise: the golden close's address and gate agree with the milestone
    # the named find's `expectRows` declare.
    _assert_scenario_settled_write(_settled_case(), "postgres")


def test_settled_close_binding_the_other_current_rectangle_is_rejected() -> None:
    # The degradation the whole reference exists to catch: id 1 holds TWO current
    # rectangles, and this close addresses the one the named find did NOT return
    # (R3's Valid-Time end, `infinity`, instead of R2's 2024-06-01). An
    # implementation keying observations by identity alone renders exactly this
    # golden, so a cross-check that passed it would grade nothing.
    case = _settled_case()
    binds = case.when["scenario"][2]["statements"][0]["binds"]
    binds[2] = "infinity"
    with pytest.raises(CaseFailure):
        _assert_scenario_settled_write(case, "postgres")


def test_settled_close_binding_another_milestones_gate_is_rejected() -> None:
    # The optimistic gate is derived from the SAME observed row as the address, so
    # a gate taken from anywhere else fails even while the address still agrees.
    case = _settled_case()
    binds = case.when["scenario"][2]["statements"][0]["binds"]
    binds[4] = "2024-01-01T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_scenario_settled_write(case, "postgres")


def test_settled_close_moving_the_observed_milestone_is_rejected() -> None:
    # The other independent place: move what the named find declares it observed,
    # and the unchanged golden close no longer matches it. This is the half that
    # proves the cross-check reads the find's own result rather than re-deriving
    # the close from the golden it is comparing against.
    case = _settled_case()
    case.when["scenario"][0]["expectRows"][0]["thru_z"] = "2024-05-01T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_scenario_settled_write(case, "postgres")


def test_settled_close_against_a_find_that_observed_another_key_is_rejected() -> None:
    # The named find MUST have observed a row of the write's own key; a reference
    # to a find that observed none names evidence that does not exist.
    case = _settled_case()
    case.when["scenario"][0]["expectRows"][0]["pos_id"] = 2
    with pytest.raises(CaseFailure, match="observed 0 row"):
        _assert_scenario_settled_write(case, "postgres")


def test_settled_write_source_finds_hold_for_authored_cases() -> None:
    for case in _scenario_cases():
        _assert_scenario_source_finds(case)  # must not raise


def test_settled_write_must_declare_its_uow_group() -> None:
    case = _settled_case()
    del case.when["scenario"][2]["uow"]
    with pytest.raises(CaseFailure, match="declares no `uow` group"):
        _assert_scenario_source_finds(case)


def test_settled_write_names_one_earlier_find_of_its_own_group() -> None:
    case = _settled_case()
    case.when["scenario"][2]["on"] = 1000
    with pytest.raises(CaseFailure, match="not a real EARLIER step"):
        _assert_scenario_source_finds(case)


def test_settled_write_must_be_the_buffered_keyed_form() -> None:
    # A legacy string label carries no instruction for the named observation to
    # reach, so the reference would name evidence nothing consumes.
    case = _settled_case()
    case.when["scenario"][2]["write"] = "correct the position"
    with pytest.raises(CaseFailure, match="not the buffered keyed form"):
        _assert_scenario_source_finds(case)


def test_a_settled_versioned_writes_gate_binds_the_named_generation() -> None:
    # A versioned Non-Temporal key holds one ROW but one observed GENERATION per
    # read, so the reference names which reading a write settled against and the
    # optimistic gate is where the difference lands. A golden binding a version
    # the named find never returned is the misresolution this catches.
    case = _versioned_settled_case(version=2)
    _assert_scenario_settled_write(case, "postgres")

    stale = _versioned_settled_case(version=1)
    with pytest.raises(CaseFailure, match="observed version 2"):
        _assert_scenario_settled_write(stale, "postgres")


def test_a_settled_versioned_writes_advance_is_graded_under_locking() -> None:
    # Locking emits no gate, but the version advance is framework-computed from
    # the SAME observation under either strategy, so a locking golden still states
    # which generation the write settled against and is still cross-checked. The
    # advance is located by the version column's position in the golden's own SET
    # clause, never by assuming where a writer put it.
    case = _versioned_settled_case(version=2, concurrency="locking")
    _assert_scenario_settled_write(case, "postgres")

    stale = _versioned_settled_case(version=1, concurrency="locking")
    with pytest.raises(CaseFailure, match="advances the version to 2"):
        _assert_scenario_settled_write(stale, "postgres")


def test_a_settled_versioned_write_resolves_the_generation_of_its_own_key() -> None:
    # The named find MUST have observed a row of the WRITE's own key. A find that
    # returned several keys still answers for the one written — reducing its rows
    # to a version set would refuse this outright — while a find that returned
    # none of that key names evidence that does not exist, however many other
    # rows it carried at the matching version.
    observed = [
        {"id": 1, "owner": "Ada", "balance": "125.00", "version": 2},
        {"id": 2, "owner": "Grace", "balance": "10.00", "version": 7},
    ]
    several = _versioned_settled_case(version=2, observed=observed)
    _assert_scenario_settled_write(several, "postgres")

    unobserved = [{"id": 2, "owner": "Grace", "balance": "10.00", "version": 2}]
    case = _versioned_settled_case(version=2, observed=unobserved)
    with pytest.raises(CaseFailure, match="observed 0 row"):
        _assert_scenario_settled_write(case, "postgres")


def test_a_settled_step_grades_each_object_against_its_own_statement() -> None:
    # The buffer that expresses a coalescing pair equally expresses a mixed
    # multi-object flush (`m-unit-work`), whose objects emit one statement each.
    # Each is graded against the generation the named find observed of ITS OWN
    # key, so a golden gating one object on the other's version is refused.
    _assert_scenario_settled_write(_multi_object_settled_case(), "postgres")

    stale = _multi_object_settled_case(second_version=2)
    with pytest.raises(CaseFailure, match="observed version 5"):
        _assert_scenario_settled_write(stale, "postgres")


def test_a_settled_steps_goldens_need_not_follow_its_entries_own_order() -> None:
    # A flush dependency-orders its surviving writes (`m-unit-work`), so the
    # statement order a legal buffer produces is the object graph's rather than
    # the author's — a parent's write may precede or follow the child's whichever
    # order the entries were written in. Each object is still graded against its
    # own statement, so reversing the golden list changes no verdict.
    case = _multi_object_settled_case()
    case.when["scenario"][1]["statements"].reverse()
    _assert_scenario_settled_write(case, "postgres")

    stale = _multi_object_settled_case(second_version=2)
    stale.when["scenario"][1]["statements"].reverse()
    with pytest.raises(CaseFailure, match="observed version 5"):
        _assert_scenario_settled_write(stale, "postgres")


def test_a_settled_steps_object_is_the_key_its_golden_addresses() -> None:
    # The object a statement settles is the key its identity predicate binds, not
    # any bind that happens to equal one: here the second UPDATE addresses account
    # 1 — which the first already settles — while carrying account 2's observed
    # generation, so it advances the version to the very 2 a search over its whole
    # bind row would take for account 2's key.
    case = _multi_object_settled_case()
    case.when["scenario"][0]["expectRows"][1]["version"] = 1
    case.when["scenario"][1]["statements"][1]["binds"] = ["60.00", 2, 1, 1]
    with pytest.raises(CaseFailure, match="2 existing-row statements addressing"):
        _assert_scenario_settled_write(case, "postgres")


def test_a_settled_step_carries_one_existing_row_golden_per_object() -> None:
    case = _multi_object_settled_case()
    del case.when["scenario"][1]["statements"][1]
    with pytest.raises(CaseFailure, match="no existing-row statement"):
        _assert_scenario_settled_write(case, "postgres")

    extra = _multi_object_settled_case()
    extra.when["scenario"][1]["write"] = extra.when["scenario"][1]["write"][:1]
    with pytest.raises(CaseFailure, match="addressing an object no entry"):
        _assert_scenario_settled_write(extra, "postgres")


def test_a_settled_steps_golden_must_open_its_predicate_with_a_bound_key() -> None:
    # The address is read at a POSITION — the predicate's first placeholder — so a
    # golden that opens with anything else states no object for its binds to be
    # read against, and is refused rather than silently offering some other bind
    # as its key. Here the key is inlined as a literal, so the leading predicate
    # binds nothing at all.
    case = _multi_object_settled_case()
    case.when["scenario"][1]["statements"][1]["sql"]["postgres"] = (
        "update account set balance = ?, version = ? where id = 2 and version = ?"
    )
    case.when["scenario"][1]["statements"][1]["binds"] = ["60.00", 6, 5]
    with pytest.raises(CaseFailure, match="does not open with a bound key equality"):
        _assert_scenario_settled_write(case, "postgres")


def test_a_settled_writes_binds_are_read_for_the_executing_dialect() -> None:
    # `binds` carries the same dialect-keyed polymorphism `sql` does, so a golden
    # whose hole structure diverges answers with the executing dialect's own array
    # rather than with the keys of the map (m-case-format).
    _assert_scenario_settled_write(
        _versioned_settled_case(version=2, dialect_keyed_binds=True), "postgres"
    )

    stale = _versioned_settled_case(version=1, dialect_keyed_binds=True)
    with pytest.raises(CaseFailure, match="observed version 2"):
        _assert_scenario_settled_write(stale, "postgres")


def test_a_settled_versioned_writes_version_column_is_located_by_its_rendered_spelling() -> None:
    # A `column=` override may name a reserved physical column, which every
    # rendering quotes (python.md, m-dialect). Locating the advance by the model's
    # own unquoted name would report the framework version absent from a golden
    # that assigns it.
    entity = _entity_with_version_column("order")
    origin = {"expectRows": [{"id": 1, "order": 2}]}
    statement = 'update ledger set balance = ?, "order" = ? where id = ? and "order" = ?'
    _assert_settled_version_binds(
        _settled_case(), entity, 1, origin, 1, ["175.00", 3, 1, 2], statement, "postgres"
    )

    with pytest.raises(CaseFailure, match="advances the version to 9"):
        _assert_settled_version_binds(
            _settled_case(), entity, 1, origin, 1, ["175.00", 9, 1, 2], statement, "postgres"
        )


def _entity_with_version_column(column: str) -> Entity:
    """A versioned entity whose optimistic-lock Attribute is stored in *column*."""
    return Entity(
        definition={
            "name": "Ledger",
            "table": "ledger",
            "attributes": [
                {"name": "id", "column": "id", "type": "int", "primaryKey": True},
                {"name": "balance", "column": "balance", "type": "decimal(12,2)"},
                {"name": "revision", "column": column, "type": "int", "optimisticLocking": True},
            ],
        }
    )


def _multi_object_settled_case(*, second_version: int = 5) -> Case:
    """A `uow` group whose one find observes Accounts 1 and 2, and whose write
    step buffers an update of each — the mixed multi-object flush the buffered
    keyed form equally expresses, settling both against that one find."""
    update = "update account set balance = ?, version = ? where id = ? and version = ?"
    raw: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                {
                    "uow": "two-objects",
                    "objectQuery": {"target": "parallax.compatibility.Account"},
                    "roundTrips": 1,
                    "expectRows": [
                        {"id": 1, "owner": "Ada", "balance": "100.00", "version": 2},
                        {"id": 2, "owner": "Grace", "balance": "50.00", "version": 5},
                    ],
                },
                {
                    "uow": "two-objects",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 1, "balance": "175.00"}],
                        },
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 2, "balance": "60.00"}],
                        },
                    ],
                    "roundTrips": 2,
                    "statements": [
                        {"sql": {"postgres": update}, "binds": ["175.00", 3, 1, 2]},
                        {
                            "sql": {"postgres": update},
                            "binds": ["60.00", second_version + 1, 2, second_version],
                        },
                    ],
                },
            ],
        },
        "then": {"roundTrips": 3},
    }
    return Case(
        path=COMPATIBILITY_ROOT / "cases" / "m-unit-work-995-synthetic.yaml",
        raw=raw,
        model=load_model(COMPATIBILITY_ROOT, "models/account.yaml"),
    )


def _versioned_settled_case(
    *,
    version: int,
    concurrency: str = "optimistic",
    observed: list[dict[str, Any]] | None = None,
    dialect_keyed_binds: bool = False,
) -> Case:
    """A `uow` group that observes Account 1 at version 2 and then updates it,
    with the golden advancing from — and, under optimistic concurrency, gating
    on — *version*."""
    gated = concurrency == "optimistic"
    sql = "update account set balance = ?, version = ? where id = ?"
    binds: Any = ["175.00", version + 1, 1, version] if gated else ["175.00", version + 1, 1]
    if dialect_keyed_binds:
        binds = {"postgres": binds, "mariadb": binds}
    raw: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": concurrency},
            "scenario": [
                {
                    "uow": "generations",
                    "objectQuery": {
                        "target": "parallax.compatibility.Account",
                        "predicate": {
                            "eq": {"attr": "parallax.compatibility.Account.id", "value": 1}
                        },
                    },
                    "roundTrips": 1,
                    "expectRows": (
                        [{"id": 1, "owner": "Ada", "balance": "125.00", "version": 2}]
                        if observed is None
                        else observed
                    ),
                },
                {
                    "uow": "generations",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 1, "balance": "175.00"}],
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": f"{sql} and version = ?" if gated else sql},
                            "binds": binds,
                        }
                    ],
                },
            ],
        },
        "then": {"roundTrips": 2},
    }
    return Case(
        path=COMPATIBILITY_ROOT / "cases" / "m-unit-work-996-synthetic.yaml",
        raw=raw,
        model=load_model(COMPATIBILITY_ROOT, "models/account.yaml"),
    )


def _transaction_time_only_settled_case(*, on: int) -> Case:
    """A `uow` group that reads a Transaction-Time-Only key's CURRENT milestone,
    reads the SAME key as of an earlier Transaction-Time instant, then closes the
    milestone step *on* returned.

    The Transaction-Time-Only shape of the reference: only one of Balance id 1's
    milestones is current, but both reads are evidence, and the golden close's gate
    binds the observed milestone's own ``in_z``. Its address carries no Valid-Time
    half — a Transaction-Time-Only close addresses the key plus the invariant open
    bound — so the gate is the whole of what states which milestone was settled
    against.
    """
    raw = {
        "model": "models/balance.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                _balance_find(1, "2024-04-01T00:00:00+00:00", "infinity", 100.00),
                _balance_find(1, "2024-01-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00", 90.00),
                {
                    "uow": "observe-then-close",
                    "on": on,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Balance",
                            "rows": [{"id": 1, "value": 150.00}],
                            "at": "2024-10-01T00:00:00+00:00",
                        }
                    ],
                    "roundTrips": 2,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update balance set out_z = ? where bal_id = ? "
                                "and out_z = ? and in_z = ?"
                            },
                            "binds": [
                                "2024-10-01T00:00:00+00:00",
                                1,
                                "infinity",
                                "2024-04-01T00:00:00+00:00",
                            ],
                        }
                    ],
                },
            ],
        },
        "then": {"roundTrips": 4},
    }
    return Case(
        path=Path("m-unit-work-997-synthetic.yaml"),
        raw=raw,
        model=load_model(COMPATIBILITY_ROOT, "models/balance.yaml"),
    )


def _balance_find(pk: int, tx_start: str, tx_end: Any, value: float) -> dict[str, Any]:
    return {
        "uow": "observe-then-close",
        "objectQuery": {
            "target": "Balance",
            "predicate": {"eq": {"attr": "Balance.id", "value": pk}},
        },
        "roundTrips": 1,
        "statements": [
            {
                "sql": {
                    "postgres": "select t0.bal_id, t0.acct_num, t0.val, t0.in_z, t0.out_z "
                    "from balance t0 where t0.bal_id = ?"
                },
                "binds": [pk],
            }
        ],
        "expectRows": [
            {
                "bal_id": pk,
                "acct_num": "A",
                "val": value,
                "in_z": tx_start,
                "out_z": tx_end,
            }
        ],
    }


def test_settled_write_admits_a_transaction_time_only_target() -> None:
    # The arm an "is it temporal?" test cannot reach and a Bitemporal-only
    # restriction would deny. A Transaction-Time-Only key is read at as-of
    # Transaction-Time coordinates resolving to milestones of any age, so this
    # group holds two pieces of evidence about one key and the close settles
    # against the one its named find returned. Naming the OTHER find — the
    # historical milestone an identity-keyed store would leave in the single slot —
    # leaves the same golden gate binding a milestone the write was not handed.
    case = _transaction_time_only_settled_case(on=0)
    _assert_scenario_source_finds(case)
    _assert_scenario_settled_write(case, "postgres")

    with pytest.raises(CaseFailure):
        _assert_scenario_settled_write(_transaction_time_only_settled_case(on=1), "postgres")
