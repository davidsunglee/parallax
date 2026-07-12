"""API Conformance Suite machinery + Usage Guide generator unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance import api_suite, usage_guide
from parallax.conformance.api_suite import Example, Skip

pytestmark = pytest.mark.unit


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
