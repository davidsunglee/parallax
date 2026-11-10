"""The preservation a workload digest restatement owes a capture, checked over
before-and-after projections of its files, so a synthetic restatement and a
committed one are held to the same assertions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cost_report
from durations import Spans

_DERIVED_SUMMARY = "summary.md"


def capture_files(capture: Path) -> dict[str, bytes]:
    """Every file directly inside ``capture``, by name."""
    return {path.name: path.read_bytes() for path in capture.iterdir() if path.is_file()}


def assert_redigest_preserved(
    before: Mapping[str, bytes], capture: Path, restated: Mapping[str, str]
) -> None:
    """Hold that a restatement of ``capture``, whose files were ``before``,
    changed only each ``restated`` member's workload digest to the digest it
    names, the adjustment it disclosed, and the summary derived from them."""
    after = capture_files(capture)
    assert set(after) - {_DERIVED_SUMMARY} == set(before) - {_DERIVED_SUMMARY}
    for name in set(before) - {"portfolio.json", cost_report.CONDITIONS_FILE, _DERIVED_SUMMARY}:
        assert after[name] == before[name], name
    old: dict[str, Any] = json.loads(before["portfolio.json"])
    new: dict[str, Any] = json.loads(after["portfolio.json"])
    assert {member["subject"] for member in old["members"]} >= set(restated)
    assert new == {
        **old,
        "members": [
            {
                **member,
                "provenance": {
                    **member["provenance"],
                    "workloadDigest": restated.get(
                        member["subject"], member["provenance"]["workloadDigest"]
                    ),
                },
            }
            for member in old["members"]
        ],
    }
    conditions: dict[str, Any] = json.loads(after[cost_report.CONDITIONS_FILE])
    adjustment = conditions.pop(cost_report.ADJUSTMENT_FIELD)
    assert conditions == json.loads(before[cost_report.CONDITIONS_FILE])
    assert set(adjustment) == {"schemaVersion", "date", "redigested"}
    assert adjustment["redigested"]["members"] == sorted(restated)
    durations = capture / cost_report.DURATIONS_FILE
    summary = cost_report._summary(  # pyright: ignore[reportPrivateUsage] - renderer seam
        new, Spans.load(durations) if durations.exists() else None
    )
    assert after[_DERIVED_SUMMARY].decode("utf-8") == summary
