"""API Conformance Suite machinery + Usage Guide generator unit tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parallax.conformance import api_suite, case_format, usage_guide
from parallax.conformance.api_suite import Example, Skip
from parallax.conformance.graph_stories import GRAPH_STORIES, graph_story_snippet
from parallax.conformance.read_stories import READ_STORIES, read_story_snippet

# A leading-underscore identifier (never a legitimate public-API token): the
# Usage Guide's rendered read/graph story snippets must never expose one (the
# m-inheritance-100 story once leaked `_temporal_as_of_axes`, a
# framework-internal, in a comment). Scoped to the read/graph snippets — the
# write stories' own local `_as_rows` helper is a separate cleanup.
_PRIVATE_NAME = re.compile(r"(?<![\w.])_[A-Za-z][A-Za-z0-9_]*")


def _case(case_id: str, module: str) -> case_format.Case:
    return case_format.Case(
        path=Path(f"{case_id}.yaml"),
        case_id=case_id,
        shape="read",
        tags=(module, "slice-snapshot-1"),
        model="",
        document={},
    )


def test_active_slice_is_non_empty_and_all_snapshot_tagged() -> None:
    active = api_suite.active_slice()
    assert len(active) > 100
    assert all("slice-snapshot-1" in case.tags for case in active)


def test_build_skips_covers_cases_without_examples() -> None:
    # With one synthetic example, the registries cover every other active case
    # EXCEPT cases whose module carries no broad bucket entry AND whose own id
    # the case-scoped registry does not name: a bucket-free module's cases are
    # covered only by a real example or their own case-scoped skip, never a
    # generic module reason.
    active = api_suite.active_slice()
    examples = [Example(active[0].case_id, "t", "snippet")]
    skips = api_suite.build_skips(active, examples)
    skipped_ids = {skip.case_id for skip in skips}
    assert active[0].case_id not in skipped_ids
    assert all(skip.reason for skip in skips)
    uncovered = {
        case.case_id
        for case in active
        if case.case_id != active[0].case_id and case.case_id not in skipped_ids
    }
    assert uncovered == {
        case.case_id
        for case in active
        if case.primary_module not in api_suite.SKIP_REASONS
        and case.case_id not in api_suite.CASE_SKIP_REASONS
        and case.case_id != active[0].case_id
    }


def test_partition_report_is_a_clean_full_partition() -> None:
    report = api_suite.partition_report()
    assert report.ok, report.errors
    # Every registered example counts as exercised.
    assert {e.case_id for e in api_suite.EXAMPLES} <= report.exercised
    assert report.exercised | report.skipped == report.active


def test_build_skips_uses_the_reviewed_registry_reason() -> None:
    active = [_case("m-predicate-900", "m-predicate")]
    skips = api_suite.build_skips(active, [], {"m-predicate": "reviewed reason"})
    assert skips == [Skip("m-predicate-900", "reviewed reason")]


def test_unclassified_active_case_is_not_silently_skipped() -> None:
    # A case whose module is absent from the registry gets no skip, so the
    # partition flags it as covered-by-neither — forcing a human to classify it
    # rather than minting a generic reason.
    active = [_case("m-ghost-900", "m-ghost")]
    skips = api_suite.build_skips(active, [], {"m-predicate": "r"})
    assert skips == []
    report = api_suite.compute_partition(frozenset({"m-ghost-900"}), [], skips)
    assert not report.ok
    assert any("covered by neither" in error for error in report.errors)


def test_stale_registry_entry_absent_from_slice_is_flagged() -> None:
    active = [_case("m-predicate-900", "m-predicate")]
    stale = api_suite.stale_skip_reasons(active, [], {"m-predicate": "r", "m-gone": "r2"})
    assert any("m-gone" in error for error in stale)
    assert not any("m-predicate" in error for error in stale)


def test_fully_exercised_module_makes_its_registry_entry_stale() -> None:
    active = [_case("m-predicate-900", "m-predicate")]
    examples = [Example("m-predicate-900", "t", "s")]
    stale = api_suite.stale_skip_reasons(active, examples, {"m-predicate": "r"})
    assert any("m-predicate" in error for error in stale)


# Modules with NO broad SKIP_REASONS bucket: every one of their active cases is
# covered case-scoped only (a real example or its own CASE_SKIP_REASONS entry),
# never a generic module-wide reason — m-unit-work, m-navigate/m-deep-fetch/
# m-snapshot-read/m-value-object/m-inheritance (each a reasoned, case-scoped
# entry rather than a blanket module bucket),
# m-read-lock (its runtime object-find pair -002/-005 are real idiomatic
# read-story examples; its harness-lane and two-session proofs
# -001/-006/-007/-010/-011 are case-scoped — no case needs a generic
# module-wide reason), m-metamodel (its one
# primary-module case is a foundational model reject, reasoned case-scoped), and
# m-execution-lifecycle (its joined case is a real idiomatic story and the other
# five name the grader that runs them, so no case needs a module-wide reason).
_BUCKET_FREE_MODULES: frozenset[str] = frozenset(
    {
        "m-execution-lifecycle",
        "m-unit-work",
        "m-navigate",
        "m-deep-fetch",
        "m-snapshot-read",
        "m-value-object",
        "m-inheritance",
        "m-read-lock",
        "m-metamodel",
    }
)


def test_registry_classifies_every_active_module_without_stale_entries() -> None:
    # The committed registries are reconciled against the live corpus: every
    # active module is covered by the module registry except the bucket-free
    # modules above, and no entry names nothing.
    active = api_suite.active_slice()
    modules = {case.primary_module for case in active}
    assert modules - set(api_suite.SKIP_REASONS) == _BUCKET_FREE_MODULES
    exercised = {example.case_id for example in api_suite.EXAMPLES}
    for case in active:
        if case.primary_module in _BUCKET_FREE_MODULES:
            assert case.case_id in exercised or case.case_id in api_suite.CASE_SKIP_REASONS, (
                case.case_id
            )
    assert api_suite.stale_skip_reasons(active, api_suite.EXAMPLES) == []


def test_partition_report_surfaces_stale_registry_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tampered = {**api_suite.SKIP_REASONS, "m-not-in-slice": "bogus reason"}
    monkeypatch.setattr(api_suite, "SKIP_REASONS", tampered)
    report = api_suite.partition_report()
    assert not report.ok
    assert any("m-not-in-slice" in error for error in report.errors)


def test_compute_partition_happy_path() -> None:
    active = frozenset({"m-a-001", "m-b-002"})
    report = api_suite.compute_partition(
        active,
        [Example("m-a-001", "t", "s")],
        [Skip("m-b-002", "reason")],
    )
    assert report.ok
    assert report.exercised == {"m-a-001"}
    assert report.skipped == {"m-b-002"}


def test_compute_partition_flags_stale_exercised() -> None:
    report = api_suite.compute_partition(
        frozenset({"m-a-001"}), [Example("m-ghost-999", "t", "s")], [Skip("m-a-001", "r")]
    )
    assert any("stale exercised" in error for error in report.errors)


def test_compute_partition_flags_stale_skipped() -> None:
    report = api_suite.compute_partition(
        frozenset({"m-a-001"}),
        [Example("m-a-001", "t", "s")],
        [Skip("m-ghost-999", "r")],
    )
    assert any("stale skipped" in error for error in report.errors)


def test_compute_partition_flags_empty_reason() -> None:
    report = api_suite.compute_partition(frozenset({"m-a-001"}), [], [Skip("m-a-001", "   ")])
    assert any("empty skip reason" in error for error in report.errors)


def test_compute_partition_flags_overlap() -> None:
    report = api_suite.compute_partition(
        frozenset({"m-a-001"}),
        [Example("m-a-001", "t", "s")],
        [Skip("m-a-001", "r")],
    )
    assert any("both exercised and skipped" in error for error in report.errors)


def test_compute_partition_flags_uncovered_case() -> None:
    report = api_suite.compute_partition(frozenset({"m-a-001", "m-b-002"}), [], [])
    assert not report.ok
    assert any("covered by neither" in error for error in report.errors)


def test_render_usage_guide_empty() -> None:
    text = api_suite.render_usage_guide([])
    assert "No idiomatic examples yet" in text
    assert text.startswith("<!-- GENERATED")


def test_render_usage_guide_with_examples() -> None:
    text = api_suite.render_usage_guide(
        [Example("m-predicate-002", "Point read", "Order.where(Order.all)")]
    )
    assert "## Point read" in text
    assert "`m-predicate-002`" in text
    assert "Order.where(Order.all)" in text


@pytest.mark.parametrize(
    "examples",
    [
        pytest.param([], id="empty"),
        pytest.param(
            [Example("m-predicate-002", "Point read", "Order.where(Order.all)")], id="populated"
        ),
    ],
)
def test_render_usage_guide_is_markdownlint_clean(examples: list[Example]) -> None:
    # Guards the MD012 (no consecutive blank lines) and single-trailing-newline
    # invariants the committed guide is linted against, so drift is caught in
    # the database-free test class and not only by the pre-commit markdownlint hook.
    text = api_suite.render_usage_guide(examples)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "\n\n\n" not in text


def test_read_and_graph_story_snippets_render_no_private_name() -> None:
    # Regression guard: a read/graph
    # story's rendered Usage Guide source is the SAME public surface the suite
    # executes — it must never leak a framework-internal `_`-prefixed name.
    for story in READ_STORIES:
        assert not _PRIVATE_NAME.search(read_story_snippet(story)), story.case_id
    for story in GRAPH_STORIES:
        assert not _PRIVATE_NAME.search(graph_story_snippet(story)), story.case_id


def test_read_story_snippet_single_sources_the_concurrency_mode() -> None:
    # Review remediation finding 2: `m-read-lock-002` (locking) and `-005`
    # (optimistic) run the SAME `db.find` expression under DIFFERENT
    # Concurrency Preferences — the entire point of the pair. The rendered
    # snippet must show the mode (never render the two identically), and it
    # must be the SAME mode the story's own `concurrency` field drives
    # execution with (`test_story_run.py`'s generic runner branches on that
    # SAME field) — single-sourced, not a second, independently-typed string.
    by_id = {story.case_id: story for story in READ_STORIES}
    locking = by_id["m-read-lock-002"]
    optimistic = by_id["m-read-lock-005"]
    assert locking.concurrency == "locking"
    assert optimistic.concurrency == "optimistic"
    locking_snippet = read_story_snippet(locking)
    optimistic_snippet = read_story_snippet(optimistic)
    assert locking_snippet != optimistic_snippet
    assert 'concurrency="locking"' in locking_snippet
    assert 'concurrency="optimistic"' in optimistic_snippet
    assert "db.transact(" in locking_snippet
    # A story with no declared concurrency renders its bare `snippet` only —
    # no transactional wrapper appears for the non-participating majority.
    plain = by_id["m-predicate-002"]
    assert plain.concurrency is None
    assert read_story_snippet(plain) == plain.snippet
    assert "db.transact(" not in read_story_snippet(plain)


def test_generate_matches_render_of_registered_examples_and_recipes() -> None:
    assert usage_guide.generate() == api_suite.render_usage_guide(
        api_suite.EXAMPLES, api_suite.RECIPES
    )
    # The recipes render as their own case-free section (checkpoint-4 Spec
    # finding 2) — present in the generated guide, absent when omitted.
    assert "## Recipes" in usage_guide.generate()
    assert "## Recipes" not in api_suite.render_usage_guide(api_suite.EXAMPLES)


def test_guide_path_points_at_docs() -> None:
    assert usage_guide.guide_path().name == "usage-guide.md"
    assert usage_guide.guide_path().parent.name == "docs"


def test_usage_guide_main_write_then_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "docs" / "usage-guide.md"
    monkeypatch.setattr(usage_guide, "guide_path", lambda: target)

    assert usage_guide.main([]) == 0
    assert target.read_text(encoding="utf-8") == usage_guide.generate()
    assert usage_guide.main(["--check"]) == 0


def test_usage_guide_main_check_detects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "docs" / "usage-guide.md"
    monkeypatch.setattr(usage_guide, "guide_path", lambda: target)
    # Missing file is drift.
    assert usage_guide.main(["--check"]) == 1
    # A stale file is drift too.
    target.parent.mkdir(parents=True)
    target.write_text("stale content", encoding="utf-8")
    assert usage_guide.main(["--check"]) == 1


def test_dropping_a_write_example_fails_the_partition() -> None:
    # m-unit-work has
    # no broad module bucket, so a case that loses its example is covered by
    # NEITHER registry and the partition fails — never silently reclassified
    # under a coalescing-witness reason. m-unit-work-001 (unlike -005/-006/-009)
    # carries no CASE_SKIP_REASONS entry of its own, so dropping IT is the
    # honest regression probe.
    slimmed = [example for example in api_suite.EXAMPLES if example.case_id != "m-unit-work-001"]
    report = api_suite.partition_report(examples=slimmed)
    assert not report.ok
    assert any(
        "covered by neither" in error and "m-unit-work-001" in error for error in report.errors
    )


def test_pk_gen_reasons_name_the_durable_blocker() -> None:
    # Regression guard: both pk-generated-column skips must say why no idiomatic
    # story CAN exist — a caller cannot honestly construct a fresh instance
    # naming a server-computed id — never a delivery increment, which goes stale
    # the moment it passes and tells a reader nothing about the surface.
    reason = api_suite.CASE_SKIP_REASONS["m-pk-gen-014"]
    module_reason = api_suite.SKIP_REASONS["m-pk-gen"]
    assert "increment" not in reason, reason
    assert "increment" not in module_reason, module_reason
    assert "no idiomatic story exists" in reason, reason
    assert "server-computed id" in module_reason, module_reason
