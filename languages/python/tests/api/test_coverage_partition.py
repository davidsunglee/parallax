"""API Conformance Suite coverage partition + Usage Guide drift (m-api-conformance).

The coverage partition asserts that exercised and reasoned-skipped cases
together equal the active slice (no stale IDs, no empty reasons); the Usage
Guide drift check fails on any divergence from generated output. Both hold at
every point in the implementation, including one where nothing is exercised yet
and the guide renders no example.
"""

from __future__ import annotations

from parallax.conformance import api_suite, usage_guide


def test_coverage_partition_is_exact_over_the_active_slice() -> None:
    report = api_suite.partition_report()
    assert report.ok, report.errors
    assert report.exercised | report.skipped == report.active


def test_usage_guide_has_no_drift() -> None:
    assert usage_guide.main(["--check"]) == 0
