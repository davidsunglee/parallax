"""API Conformance Suite machinery + Usage Guide generator unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import api_suite, case_format, usage_guide
from parallax.conformance.api_suite import Example, Skip

pytestmark = pytest.mark.unit


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
    active = api_suite.active_slice()
    examples = [Example(active[0].case_id, "t", "snippet")]
    skips = api_suite.build_skips(active, examples)
    skipped_ids = {skip.case_id for skip in skips}
    assert active[0].case_id not in skipped_ids
    assert all(skip.reason for skip in skips)
    assert len(skips) == len(active) - 1


def test_partition_report_is_a_clean_full_partition() -> None:
    report = api_suite.partition_report()
    assert report.ok, report.errors
    assert report.exercised == frozenset()  # no examples registered yet
    assert report.exercised | report.skipped == report.active


def test_build_skips_uses_the_reviewed_registry_reason() -> None:
    active = [_case("m-op-algebra-900", "m-op-algebra")]
    skips = api_suite.build_skips(active, [], {"m-op-algebra": "reviewed reason"})
    assert skips == [Skip("m-op-algebra-900", "reviewed reason")]


def test_unclassified_active_case_is_not_silently_skipped() -> None:
    # A case whose module is absent from the registry gets no skip, so the
    # partition flags it as covered-by-neither — forcing a human to classify it
    # rather than minting a generic reason.
    active = [_case("m-ghost-900", "m-ghost")]
    skips = api_suite.build_skips(active, [], {"m-op-algebra": "r"})
    assert skips == []
    report = api_suite.compute_partition(frozenset({"m-ghost-900"}), [], skips)
    assert not report.ok
    assert any("covered by neither" in error for error in report.errors)


def test_stale_registry_entry_absent_from_slice_is_flagged() -> None:
    active = [_case("m-op-algebra-900", "m-op-algebra")]
    stale = api_suite.stale_skip_reasons(active, [], {"m-op-algebra": "r", "m-gone": "r2"})
    assert any("m-gone" in error for error in stale)
    assert not any("m-op-algebra" in error for error in stale)


def test_fully_exercised_module_makes_its_registry_entry_stale() -> None:
    active = [_case("m-op-algebra-900", "m-op-algebra")]
    examples = [Example("m-op-algebra-900", "t", "s")]
    stale = api_suite.stale_skip_reasons(active, examples, {"m-op-algebra": "r"})
    assert any("m-op-algebra" in error for error in stale)


def test_registry_classifies_every_active_module_without_stale_entries() -> None:
    # The committed registry is reconciled against the live corpus: it covers
    # every module in the active slice and carries no entry that names none.
    active = api_suite.active_slice()
    modules = {case.primary_module for case in active}
    assert modules <= set(api_suite.SKIP_REASONS)
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
        [Example("m-op-algebra-002", "Point read", "Order.where()")]
    )
    assert "## Point read" in text
    assert "`m-op-algebra-002`" in text
    assert "Order.where()" in text


@pytest.mark.parametrize(
    "examples",
    [
        pytest.param([], id="empty"),
        pytest.param([Example("m-op-algebra-002", "Point read", "Order.where()")], id="populated"),
    ],
)
def test_render_usage_guide_is_markdownlint_clean(examples: list[Example]) -> None:
    # Guards the MD012 (no consecutive blank lines) and single-trailing-newline
    # invariants the committed guide is linted against, so drift is caught in
    # `pytest -m unit` and not only by the pre-commit markdownlint hook.
    text = api_suite.render_usage_guide(examples)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "\n\n\n" not in text


def test_generate_matches_render_of_registered_examples() -> None:
    assert usage_guide.generate() == api_suite.render_usage_guide(api_suite.EXAMPLES)


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
