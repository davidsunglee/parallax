"""What a Scenario's own document must say, and what it costs to say it wrong.

Every refusal here is asserted against a provider that raises on any call at all,
so each test proves two things at once: the case is refused, and the refusal cost
zero database access. Those are the two claims a document-settled rule makes, and
there is nothing else to inspect — a rule the read oracle owns is refused during
execution instead, and is graded there, while a rule about what the document says
of itself is asked of the whole corpus before any executor runs, and is graded in
`tests/test_scenario_document.py`.
"""

from __future__ import annotations

import pytest

from reference_harness.case_assertions import CaseFailure
from reference_harness.unit_work_scenario import assert_unit_work_scenario

from .conftest import DatabaseRefused, RefusingProvider, assert_judged


# The api-conformance lane is schema-validated but never executed by the wire
# harness, so `run_case` returns before it would reach this package at all; a
# corpus sweep that included those cases would be asserting about a call the
# runner never makes.
def _executed(cases):
    return [case for case in cases if case.lane != "api-conformance"]


# --- what the corpus authors ------------------------------------------------


def test_scenario_cases_are_discovered_and_self_describe(scenario_cases) -> None:
    assert scenario_cases, "no scenario cases discovered"
    for case in scenario_cases:
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


def test_every_authored_scenario_is_judged_clean_before_any_database(scenario_cases) -> None:
    # The whole executed corpus, graded against its own document on both dialects
    # without a container: normalization, round-trip accounting, settled-write
    # cross-checks, and `on` references.
    for case in _executed(scenario_cases):
        for dialect in ("postgres", "mariadb"):
            try:
                assert_unit_work_scenario(case, RefusingProvider(dialect))
            except DatabaseRefused:
                pass  # judged clean, then asked for a database


def test_cache_hit_scenario_has_a_zero_round_trip_step(corpus_case) -> None:
    case = corpus_case("m-process-cache-001-hit.yaml")
    assert "cache-hit" in case.tags
    # A cache-hit scenario must contain a step that costs zero round trips and
    # lists no golden SQL (it is served from the query cache).
    hits = [step for step in case.scenario if step["roundTrips"] == 0]
    assert hits, "cache-hit scenario has no zero-round-trip (hit) step"
    for hit in hits:
        assert not hit.get("statements"), "a cache-hit step must list no golden SQL"
    assert_judged(case)


def test_rollback_scenario_step_is_discovered_and_self_describes(corpus_case) -> None:
    case = corpus_case("m-unit-work-002-rollback-discards-writes.yaml")
    rollback_steps = [step for step in case.scenario if step.get("rollback")]
    assert rollback_steps, "no rollback scenario step discovered"
    for step in rollback_steps:
        # An ABORTED write step is still a write step that lists golden DML (it is
        # applied then rolled back) and declares its round trips (the DML executes).
        assert "write" in step
        assert step.get("statements"), "a rollback write step must list golden DML"
        assert step["roundTrips"] >= 1
    # The rolled-back step's statements are counted as round trips exactly like a
    # committed write, so the count-consistency check MUST still hold.
    assert_judged(case)


def test_no_op_write_scenario_step_is_discovered_and_self_describes(corpus_case) -> None:
    case = corpus_case("m-opt-lock-001-no-op-update-no-dml.yaml")
    no_ops = [step for step in case.scenario if "write" in step and step["roundTrips"] == 0]
    assert no_ops, "no no-op-write scenario step discovered"
    for step in no_ops:
        # A NO-OP write (a versioned UPDATE that changes no attribute, m-opt-lock) issues
        # NO DML: it lists no golden SQL and costs zero round trips, mirroring a
        # cache-hit read step.
        assert not step.get("statements"), "a no-op write step must list no golden DML"
    # The zero-round-trip write step keeps the count-consistency check green.
    assert_judged(case)


def test_read_your_own_writes_update_scenario_flushes_before_dependent_find(corpus_case) -> None:
    # m-unit-work-005: an OBSERVING find, then a committed UPDATE that advances from
    # that observation, then a dependent find that MUST observe the new value
    # (read-your-own-writes for UPDATE; `m-opt-lock`'s prior-observation rule).
    case = corpus_case("m-unit-work-005-ryow-update.yaml")
    observe, write, find = case.scenario
    assert observe["expectRows"] == [{"id": 1, "owner": "Ada", "balance": "100.00", "version": 1}]
    # The write step carries the structured keyed buffer: a single keyed UPDATE of
    # account 1 (no row-carried version — the advance derives from the observing
    # find), its golden SQL unchanged.
    (instruction,) = write["write"]
    assert instruction["mutation"] == "update"
    assert instruction["entity"] == "parallax.compatibility.Account"
    assert instruction["rows"] == [{"id": 1, "balance": "175.00"}]
    assert write["statements"][0]["sql"]["postgres"].startswith("update account set")
    assert "objectQuery" in find
    # The dependent find asserts the flushed new balance/version (the RYOW observable).
    assert find["expectRows"] == [{"id": 1, "owner": "Ada", "balance": "175.00", "version": 2}]
    assert_judged(case)


def test_read_your_own_writes_delete_scenario_observes_absence(corpus_case) -> None:
    # m-unit-work-006: an OBSERVING find, then a committed DELETE of that observed
    # row, then a dependent find that MUST observe the row's ABSENCE
    # (read-your-own-writes for DELETE; `m-opt-lock`'s prior-observation rule).
    case = corpus_case("m-unit-work-006-ryow-delete.yaml")
    observe, write, find = case.scenario
    assert observe["expectRows"] == [{"id": 3, "owner": "Grace", "balance": "10.00", "version": 1}]
    # The keyed DELETE of account 3 is gated on the observed version under the
    # case's default preference (the observation licenses the write; the gate
    # follows the target's own Effective Concurrency Strategy).
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
    assert_judged(case)


def test_insert_update_combining_scenario_emits_exactly_one_insert(corpus_case) -> None:
    # m-unit-work-008: a buffered insert + a buffered update of the same new object
    # COMBINE into exactly ONE INSERT with the final values — no intervening UPDATE.
    case = corpus_case("m-unit-work-008-insert-update-combining.yaml")
    write = case.scenario[0]
    assert "write" in write
    (statement,) = write["statements"]
    sql = statement["sql"]["postgres"]
    assert sql.startswith("insert into account") and "update" not in sql
    # The single INSERT carries the FINAL (post-combine) balance, not the initial one.
    assert statement["binds"] == [8, "Turing", "99.00", 1]
    assert_judged(case)


# --- refusals, every one of them before a database exists -------------------


def test_a_scenario_with_no_steps_is_refused(damaged_case) -> None:
    case = damaged_case("m-unit-work-005-ryow-update.yaml")
    case.when["scenario"] = []
    with pytest.raises(CaseFailure, match="has no steps"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_step_round_trip_mismatch_is_refused(damaged_case) -> None:
    # Corrupt a step's declared roundTrips so it no longer matches the golden SQL
    # statement count it lists.
    case = damaged_case("m-unit-work-005-ryow-update.yaml")
    case.when["scenario"][0]["roundTrips"] += 1
    with pytest.raises(CaseFailure, match="declares roundTrips"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_case_level_round_trip_mismatch_is_refused(damaged_case) -> None:
    case = damaged_case("m-unit-work-005-ryow-update.yaml")
    case.then["roundTrips"] += 1
    with pytest.raises(CaseFailure, match="scenario steps total"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_step_golden_must_be_canonical(damaged_case) -> None:
    case = damaged_case("m-opt-lock-003-versioned-set-based-materialize-optimistic.yaml")
    case.when["scenario"][0]["statements"][0]["sql"]["postgres"] = "SELECT t0.id FROM account t0"
    with pytest.raises(CaseFailure, match="not canonical"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_step_on_reference_must_name_an_earlier_step(damaged_case) -> None:
    # `on` names EARLIER steps on every kind of step that carries one, so the bound
    # is decided before execution rather than by whichever owner reached the step.
    case = damaged_case("m-snapshot-read-010-mutation-has-no-writeback.yaml")
    mutate = next(step for step in case.scenario if step.get("action") == "mutate")
    mutate["on"] = len(case.scenario)
    with pytest.raises(CaseFailure, match="not a real EARLIER step"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_settling_writes_on_reference_is_bounded_by_the_same_rule(damaged_case) -> None:
    # A write's `on` is the find it settles against, which is still an index into
    # the steps before it: the bound is one rule over every kind of step, and
    # compilation must not address a step the case never authored. WHICH find it
    # may name is the document's own rule, asked of the whole corpus elsewhere.
    case = damaged_case(
        "m-unit-work-015-close-settles-against-the-milestone-its-own-find-observed.yaml"
    )
    case.when["scenario"][2]["on"] = len(case.scenario)
    with pytest.raises(CaseFailure, match="not a real EARLIER step"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_read_verbs_on_reference_must_name_an_earlier_step(damaged_case) -> None:
    # A `load` walks a relationship from the object an earlier step named. The
    # oracle that walks it resolves that reference rather than bounding it, so a
    # forward or self index is refused here, before a container exists — the rule
    # has one owner however many readers follow the reference afterwards.
    case = damaged_case("m-op-list-002-deep-fetch-population-stable.yaml")
    case.when["scenario"][1]["on"] = 1
    with pytest.raises(CaseFailure, match="not a real EARLIER step"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_reuse_naming_a_step_that_is_not_earlier_is_refused(damaged_case) -> None:
    # The other half of the same rule: a zero-round-trip cache hit / re-access
    # names its source with `sameObjectAs`, and an empty reuse would let the
    # step's own identity and `expectRows` assertions pass against nothing.
    # Whether the step it names PUBLISHED anything only a run can answer, and the
    # read oracle answers it there.
    case = damaged_case("m-op-list-002-deep-fetch-population-stable.yaml")
    case.when["scenario"][2]["sameObjectAs"] = 2
    with pytest.raises(CaseFailure, match=r"sameObjectAs=2 is not a real EARLIER step"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_coordinate_grouped_on_names_each_source_once(damaged_case) -> None:
    case = damaged_case("m-snapshot-read-010-mutation-has-no-writeback.yaml")
    mutate = next(step for step in case.scenario if step.get("action") == "mutate")
    mutate["on"] = [0, 0]
    with pytest.raises(CaseFailure, match="DUPLICATE source"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_non_read_action_step_declaring_a_row_observable_is_refused(damaged_case) -> None:
    """A verb that publishes nothing has nothing to compare, so a claim about its
    rows is refused rather than skipped.

    Grading one would mean reading what an earlier read retained, which belongs to
    the read oracle and never crosses back. Refusing it keeps that boundary from
    being reintroduced by a future case rather than only by today's corpus, in
    which every observable-bearing action step is a read verb.
    """
    case = damaged_case("m-snapshot-read-010-mutation-has-no-writeback.yaml")
    source = case.scenario[0]
    mutate = next(step for step in case.scenario if step.get("action") == "mutate")
    mutate["expectRows"] = list(source["expectRows"])
    with pytest.raises(CaseFailure, match="only the read verbs"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_an_observable_a_verb_may_not_declare_is_refused_before_its_anchor_is_bounded(
    damaged_case,
) -> None:
    """A step told which observables its verb admits is not also told that one of
    them names the wrong step.

    Whether a key belongs on this kind of step at all precedes whether its value
    is in range: bounding the anchor first would answer a question the step was
    never entitled to ask, and hide the defect that makes the other moot.
    """
    case = damaged_case("m-snapshot-read-010-mutation-has-no-writeback.yaml")
    mutate = next(step for step in case.scenario if step.get("action") == "mutate")
    mutate["sameObjectAs"] = len(case.scenario)
    with pytest.raises(CaseFailure, match="only the read verbs"):
        assert_unit_work_scenario(case, RefusingProvider())
