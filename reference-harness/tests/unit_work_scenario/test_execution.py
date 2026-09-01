"""What a Scenario asks a database for, and on which connection.

The provider double is an adapter at the same seam Postgres and MariaDB satisfy,
so which sessions a run opened, what ran on each, and when each committed are
behaviour *of* the one export rather than internals of it. No test here reaches
inside the package; the chronology is the whole observation.

Real in-transaction correctness — that a grouped find genuinely sees its group's
uncommitted writes, that a rollback genuinely discards them — is
``test_compatibility.py``'s, against real containers on both dialects.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.unit_work_scenario import assert_unit_work_scenario

from .conftest import (
    COMPATIBILITY_ROOT,
    Affected,
    Committed,
    Ddl,
    Executed,
    Fixtures,
    Opened,
    Queried,
    Reset,
    RolledBack,
    Rows,
    ScriptedProvider,
)


def _observed(case: Case) -> list[Rows]:
    """One scripted answer per read the case's own steps declare they observed."""
    return [Rows(tuple(step["expectRows"])) for step in case.scenario if "expectRows" in step]


# --- provisioning, and where it sits relative to the first step -------------


def test_a_scenario_provisions_before_its_first_step(corpus_case) -> None:
    case = corpus_case("m-unit-work-005-ryow-update.yaml")
    with ScriptedProvider(script=[*_observed(case)[:1], Affected(1), *_observed(case)[1:]]) as db:
        assert_unit_work_scenario(case, db)

    # Schema and fixtures first, then the group's session — a step never runs
    # against a database the case's own `given` has not finished describing.
    assert db.chronology[:4] == [Reset(), Ddl(1), Fixtures("account"), Opened(0)]


# --- grouped execution ------------------------------------------------------


def test_a_group_shares_one_session_and_commits_after_its_last_step(corpus_case) -> None:
    # m-unit-work-005: one `uow` group spans all three steps (observe find,
    # versioned write, dependent find). Exactly ONE session opens for the whole
    # group, every step's SQL runs on IT, and it COMMITS once, after its own last
    # step.
    case = corpus_case("m-unit-work-005-ryow-update.yaml")
    observe, dependent = _observed(case)
    with ScriptedProvider(script=[observe, Affected(1), dependent]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 1
    assert [call for call in db.chronology if not isinstance(call, (Reset, Ddl, Fixtures))] == [
        Opened(0),
        Queried(0, *_pair(case, 0)),
        Executed(0, *_pair(case, 1)),
        Queried(0, *_pair(case, 2)),
        Committed(0),
    ]


def test_a_doomed_group_rolls_back_and_the_post_abort_find_leaves_it(corpus_case) -> None:
    # m-unit-work-002: steps 0-1 share the doomed `doomed-update` group (the write
    # declares `rollback: true`); step 2, the post-abort find, is UNGROUPED. The
    # group's session ROLLS BACK, never commits, and the re-resolve runs on the
    # provider's own connection instead — exactly the abort contract's promise that
    # the aborted group's connection never serves it.
    case = corpus_case("m-unit-work-002-rollback-discards-writes.yaml")
    observe, restored = _observed(case)
    with ScriptedProvider(script=[observe, Affected(1), restored]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 1
    assert [call for call in db.chronology if not isinstance(call, (Reset, Ddl, Fixtures))] == [
        Opened(0),
        Queried(0, *_pair(case, 0)),
        Executed(0, *_pair(case, 1)),
        RolledBack(0),
        Queried(None, *_pair(case, 2)),
    ]


def test_interleaved_groups_hold_two_independent_sessions(corpus_case) -> None:
    # m-opt-lock-012's optimistic-lock race: `ours` owns steps {0, 3} and
    # `concurrent` steps {1, 2}, genuinely interleaved. Two sessions open, in the
    # order their labels are first seen; the concurrent group's session is used and
    # committed entirely BETWEEN the first group's two steps, while that group's own
    # session stays open across the whole span and closes only at ITS last step.
    case = corpus_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    ours, concurrent, after = _observed(case)
    script = [ours, concurrent, Affected(1), Affected(1), Affected(0), after]
    with ScriptedProvider(script=script) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 2
    assert [call for call in db.chronology if not isinstance(call, (Reset, Ddl, Fixtures))] == [
        Opened(0),
        Queried(0, *_pair(case, 0)),
        Opened(1),
        Queried(1, *_pair(case, 1)),
        Executed(1, *_pair(case, 2)),
        Committed(1),
        Executed(0, *_pair(case, 3, 0)),
        Executed(0, *_pair(case, 3, 1)),
        RolledBack(0),
        Queried(None, *_pair(case, 4)),
    ]


def test_a_grouped_finds_reference_sql_oracle_runs_on_the_held_session() -> None:
    # A grouped find's independent `referenceSql` oracle must run on the SAME held
    # session as its golden read, not the provider's autocommit connection: after an
    # uncommitted grouped write the two connections would observe DIFFERENT states,
    # silently breaking the "independent-but-equivalent" contract.
    case = _uncommitted_write_then_reference_sql_case()
    rows = Rows(({"id": 2, "owner": "Linus", "balance": Decimal("249.00"), "version": 1},))
    with ScriptedProvider(script=[Affected(1), rows, rows]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 1
    assert [call.session for call in db.chronology if isinstance(call, (Queried, Executed))] == [
        0,
        0,
        0,
    ], "the referenceSql oracle must not touch the provider's own connection"


# --- ungrouped execution ----------------------------------------------------


def test_an_ungrouped_committed_write_applies_on_the_providers_own_connection(
    corpus_case,
) -> None:
    # A committed write between finds (read-your-own-writes / cache invalidation):
    # no session is opened at all, and a later find observes the committed state.
    case = corpus_case("m-unit-work-001-read-your-own-writes.yaml")
    script: list[Any] = []
    for step in case.scenario:
        script += [Rows(tuple(step["expectRows"]))] if "expectRows" in step else [Affected(1)]
    with ScriptedProvider(script=script) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 0
    assert all(
        call.session is None for call in db.chronology if isinstance(call, (Queried, Executed))
    )


def test_an_ungrouped_rolled_back_write_opens_its_own_single_step_session(corpus_case) -> None:
    # m-unit-work-011: the write lands in the atomic scope the abort discards, so it
    # gets a session of its OWN, rolled back at the end of that one step, while the
    # find that follows re-resolves on the provider's connection.
    case = corpus_case("m-unit-work-011-rollback-discards-insert.yaml")
    (observed,) = _observed(case)
    with ScriptedProvider(script=[Affected(1), observed]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 1
    assert [call for call in db.chronology if not isinstance(call, (Reset, Ddl, Fixtures))] == [
        Opened(0),
        Executed(0, *_pair(case, 0)),
        RolledBack(0),
        Queried(None, *_pair(case, 1)),
    ]


def test_a_boundary_action_commits_its_dml_on_the_providers_own_connection(corpus_case) -> None:
    # The schema forbids `uow` on an action step, so a `flush` never runs on a held
    # session however the steps around it are grouped.
    # m-identity-map-006: a buffered write that issues nothing, the `flush` that
    # emits its INSERT, and the find that observes the interned row.
    case = corpus_case("m-identity-map-006-app-assigned-key-interns-on-buffer.yaml")
    (interned,) = _observed(case)
    with ScriptedProvider(script=[Affected(1), interned]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 0
    assert [call for call in db.chronology if isinstance(call, (Queried, Executed))] == [
        Executed(None, *_pair(case, 1)),
        Queried(None, *_pair(case, 2)),
    ]


def test_an_unresolved_list_step_issues_nothing(corpus_case) -> None:
    # m-op-list-001: the construction of a query-backed list costs zero round trips
    # and makes no call at all; the observation is deferred to the later step that
    # accesses it, and the re-access after that issues nothing either.
    case = corpus_case("m-op-list-001-construction-first-access-reaccess.yaml")
    (resolved,) = _observed(case)
    with ScriptedProvider(script=[resolved]) as db:
        assert_unit_work_scenario(case, db)

    assert db.sessions == 0
    assert [call for call in db.chronology if isinstance(call, (Queried, Executed))] == [
        Queried(None, *_pair(case, 1))
    ]


# --- the conflict-abort proof a doomed group is closed under ----------------
#
# A rolled-back unit of work must be the CONSEQUENCE of a detected optimistic-lock
# conflict, not a vacuous abort. Each degradation below moves exactly one term of
# that proof on the real m-opt-lock-012 case, so `concurrency`, `then.affectedRows`,
# the root entity, and the version column all resolve authentically.


def _conflict_abort_script(case: Case, gated_affected: int) -> list[Any]:
    """m-opt-lock-012's own chronology, with the doomed group's gated write
    reporting *gated_affected* rows."""
    ours, concurrent, after = _observed(case)
    return [ours, concurrent, Affected(1), Affected(1), Affected(gated_affected), after]


def test_a_doomed_group_accepts_the_authored_conflict(corpus_case) -> None:
    # The genuine conflict: the stale-version gate matched nothing, which is
    # `then.affectedRows` 0. The rejections below therefore bite the corruptions
    # rather than everything.
    case = corpus_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    with ScriptedProvider(script=_conflict_abort_script(case, 0)) as db:
        assert_unit_work_scenario(case, db)
    assert RolledBack(0) in db.chronology


def test_a_gated_write_affecting_one_row_is_no_conflict(damaged_case) -> None:
    case = damaged_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    with pytest.raises(CaseFailure, match="a gated write affecting 1 row is NO conflict"):
        assert_unit_work_scenario(case, ScriptedProvider(script=_conflict_abort_script(case, 1)))


def test_an_abort_with_no_gated_write_detected_no_conflict(damaged_case) -> None:
    # The doomed group's writes list no version-gated statement at all, so nothing
    # in it ever detected a conflict and the rollback is vacuous.
    case = damaged_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    gated = case.when["scenario"][3]["statements"][1]
    gated["sql"]["postgres"] = "update account set balance = ?, version = ? where id = ?"
    gated["binds"] = [300.00, 2, 2]
    with pytest.raises(CaseFailure, match="exactly one version-gated write"):
        assert_unit_work_scenario(case, ScriptedProvider(script=_conflict_abort_script(case, 0)))


def test_a_conflict_abort_needs_the_version_gate_the_unit_of_work_declares(damaged_case) -> None:
    case = damaged_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    case.when["uow"]["concurrency"] = "locking"
    with pytest.raises(CaseFailure, match="requires the version gate"):
        assert_unit_work_scenario(case, ScriptedProvider(script=_conflict_abort_script(case, 0)))


def test_affected_rows_of_one_is_not_a_conflict_signal(damaged_case) -> None:
    case = damaged_case("m-opt-lock-012-conflict-aborts-uow.yaml")
    case.then["affectedRows"] = 1
    with pytest.raises(CaseFailure, match="which is NOT a conflict"):
        assert_unit_work_scenario(case, ScriptedProvider(script=_conflict_abort_script(case, 1)))


# --- what a failed step leaves behind ---------------------------------------


def test_a_step_that_fails_an_observable_stops_the_scenario_where_it_stands(
    damaged_case,
) -> None:
    """Publication is the LAST thing a step does, so a step that failed an
    observable published nothing.

    From outside, that is visible as where the run stops: the failure names the
    failing step, and the steps after it — including the one that would have read
    what it published — issue nothing at all. A later step can therefore never be
    answered with rows nobody graded.
    """
    case = damaged_case("m-unit-work-005-ryow-update.yaml")
    case.when["scenario"][0]["expectRows"] = [{"id": 1, "owner": "Ada", "balance": "1.00"}]
    observed = Rows(({"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1},))
    db = ScriptedProvider(script=[observed])

    with pytest.raises(CaseFailure, match=r"scenario\[0\]"):
        assert_unit_work_scenario(case, db)

    assert [call for call in db.chronology if isinstance(call, (Queried, Executed))] == [
        Queried(0, *_pair(case, 0))
    ]
    assert Committed(0) not in db.chronology


# --- helpers ----------------------------------------------------------------


def _pair(case: Case, index: int, statement: int = 0) -> tuple[str, tuple[Any, ...]]:
    """The (sql, binds) a step's own golden authors for postgres."""
    from reference_harness.case import entry_pairs

    sql, binds = entry_pairs(case.scenario[index].get("statements"), "postgres")[statement]
    return sql, tuple(binds)


def _uncommitted_write_then_reference_sql_case() -> Case:
    """One `uow` group that applies an UNCOMMITTED write then a mid-group find
    carrying ``referenceSql``.

    The read-your-own-writes oracle shape, which the corpus authors only inside a
    streamed delivery: both the golden read and the independent oracle MUST observe
    the same in-transaction state, so both MUST run on the group's own session.
    """
    from reference_harness.case import load_model

    find = "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?"
    raw: dict[str, Any] = {
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
                            "binds": ["249.00", 2],
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
                    "statements": [{"sql": {"postgres": find}, "binds": [2]}],
                    "referenceSql": "select * from account where id = 2",
                },
            ]
        },
        "then": {"roundTrips": 2},
    }
    return Case(
        path=Path("m-unit-work-998-synthetic.yaml"),
        raw=raw,
        model=load_model(COMPATIBILITY_ROOT, "models/account.yaml"),
    )
