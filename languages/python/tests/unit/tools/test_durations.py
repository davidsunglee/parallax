from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from durations import SCHEMA_VERSION, SCOPES, Span, Spans, render


class _Clocks:
    """A monotonic clock and a wall clock that advance only when told to."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.wall = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
        self.wall += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return self.wall


def _recorder() -> tuple[Spans, _Clocks]:
    clocks = _Clocks()
    return Spans(clock=clocks.monotonic, now=clocks.now), clocks


def test_a_span_records_its_start_and_elapsed_time_from_the_injected_clocks() -> None:
    spans, clocks = _recorder()
    clocks.advance(5.0)
    with spans.span("member", "write-lowering", member="write-lowering"):
        clocks.advance(2.5)
    assert spans.spans == (
        Span(
            "member",
            "write-lowering",
            {"member": "write-lowering"},
            datetime(2026, 9, 18, 12, 0, 5, tzinfo=UTC),
            2.5,
        ),
    )


def test_nested_spans_are_included_in_their_parent_and_recorded_innermost_first() -> None:
    spans, clocks = _recorder()
    with spans.span("collection", "python-report-cost"):
        with spans.span("member", "snapshot-delivery"):
            clocks.advance(3.0)
        clocks.advance(1.0)
        with spans.span("member", "write-lowering"):
            clocks.advance(2.0)
    assert [(span.scope, span.name, span.seconds) for span in spans.spans] == [
        ("member", "snapshot-delivery", 3.0),
        ("member", "write-lowering", 2.0),
        ("collection", "python-report-cost", 6.0),
    ]


def test_a_failed_operation_still_has_its_span() -> None:
    spans, clocks = _recorder()
    with pytest.raises(RuntimeError, match="the child died"), spans.span("case", "plain.changed"):
        clocks.advance(4.0)
        raise RuntimeError("the child died")
    assert [(span.name, span.seconds) for span in spans.spans] == [("plain.changed", 4.0)]


def test_a_scope_outside_the_vocabulary_is_refused_before_any_work_runs() -> None:
    spans, _clocks = _recorder()
    with (
        pytest.raises(ValueError, match="span scope 'runtime' is not one of"),
        spans.span("runtime", "3.13"),
    ):
        raise AssertionError("the block must not run")
    with pytest.raises(ValueError, match="span scope 'child'"):
        spans.missing("child", "x", "never asked")
    assert sorted(SCOPES) == ["case", "collection", "member", "scenario", "setup", "workload"]


def test_the_sidecar_round_trips_through_its_versioned_document(tmp_path: Path) -> None:
    spans, clocks = _recorder()
    with spans.span("workload", "conventional-fanout", member="snapshot-delivery", runtime="3.13"):
        clocks.advance(1.25)
    spans.missing("member", "lifecycle-overhead", "wrote nothing")
    sidecar = tmp_path / "nested" / "durations.json"
    spans.write(sidecar)
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    assert document == {
        "schemaVersion": SCHEMA_VERSION,
        "spans": [
            {
                "scope": "workload",
                "name": "conventional-fanout",
                "labels": {"member": "snapshot-delivery", "runtime": "3.13"},
                "startedAt": "2026-09-18T12:00:00+00:00",
                "seconds": 1.25,
            }
        ],
        "unavailable": [
            {"scope": "member", "name": "lifecycle-overhead", "reason": "wrote nothing"}
        ],
    }
    loaded = Spans.load(sidecar)
    assert loaded.spans == spans.spans
    assert loaded.unavailable == spans.unavailable
    assert loaded.document() == document


def _document(**overrides: Any) -> dict[str, Any]:
    span: dict[str, Any] = {
        "scope": "member",
        "name": "write-lowering",
        "labels": {},
        "startedAt": "2026-09-18T12:00:00+00:00",
        "seconds": 1.0,
    }
    span.update(overrides)
    return {"schemaVersion": SCHEMA_VERSION, "spans": [span], "unavailable": []}


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "does not hold a durations document"),
        ({"schemaVersion": 2, "spans": []}, "has schemaVersion 2, expected 1"),
        ({"schemaVersion": 1, "spans": {}}, "spans is not a list"),
        ({"schemaVersion": 1, "spans": ["x"]}, "spans entry 'x' is not an object"),
        (_document(scope="runtime"), "span scope 'runtime' is not one of"),
        (_document(name=""), "span name '' is not a non-empty string"),
        (_document(labels=["member"]), "span labels .* are not an object"),
        (_document(labels={"roots": 200}), "span labels .* are not all strings"),
        (_document(startedAt="2026-09-18T12:00:00"), "carries no timezone"),
        (_document(startedAt="yesterday"), "Invalid isoformat string"),
        (_document(seconds=True), "span seconds True is not a number"),
        (_document(seconds=-1.0), "not a non-negative finite number"),
        (_document(seconds=float("inf")), "not a non-negative finite number"),
        (
            {"schemaVersion": 1, "spans": [], "unavailable": [{"scope": "member"}]},
            "span name None is not a non-empty string",
        ),
    ],
)
def test_a_malformed_sidecar_names_the_first_way_it_is_not_one(
    tmp_path: Path, document: object, message: str
) -> None:
    sidecar = tmp_path / "durations.json"
    sidecar.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        Spans.load(sidecar)


def test_a_sidecar_that_is_not_json_is_a_value_error(tmp_path: Path) -> None:
    sidecar = tmp_path / "durations.json"
    sidecar.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        Spans.load(sidecar)


def test_extending_a_recorder_folds_in_spans_and_unavailable_telemetry() -> None:
    outer, clocks = _recorder()
    inner, _ = _recorder()
    with inner.span("case", "plain.changed", runtime="3.14"):
        clocks.advance(1.0)
    inner.missing("scenario", "wide", "no child was run")
    outer.extend(inner)
    assert outer.spans == inner.spans
    assert outer.unavailable == inner.unavailable


def test_rendering_names_the_critical_path_and_orders_spans_outermost_first() -> None:
    spans, clocks = _recorder()
    with spans.span("collection", "python-report-cost"):
        with spans.span("member", "snapshot-delivery", member="snapshot-delivery"):
            with spans.span("setup", "provision", member="snapshot-delivery", roots="200"):
                clocks.advance(0.5)
            with spans.span("workload", "conventional-fanout", runtime="3.13", member="s"):
                clocks.advance(2.0)
        with spans.span("member", "lifecycle-overhead", member="lifecycle-overhead"):
            clocks.advance(1.0)
    spans.missing("member", "lifecycle-overhead", "the member wrote no durations sidecar")
    rendered = render(spans)
    lines = rendered.splitlines()
    assert lines[0] == "## Durations"
    assert (
        "Critical path: 3.500 s, the `python-report-cost` collection span. "
        "Nested spans are included in their parents and are never summed." in lines
    )
    rows = [line for line in lines if line.startswith("| ") and not line.startswith("| Scope")]
    assert rows == [
        "| collection | python-report-cost | - | 2026-09-18T12:00:00+00:00 | 3.500 |",
        "| member | snapshot-delivery | member=snapshot-delivery | 2026-09-18T12:00:00+00:00 "
        "| 2.500 |",
        "| setup | provision | member=snapshot-delivery, roots=200 | 2026-09-18T12:00:00+00:00 "
        "| 0.500 |",
        "| workload | conventional-fanout | member=s, runtime=3.13 | "
        "2026-09-18T12:00:00.500000+00:00 | 2.000 |",
        "| member | lifecycle-overhead | member=lifecycle-overhead | "
        "2026-09-18T12:00:02.500000+00:00 | 1.000 |",
    ]
    assert lines[-1] == ("- member `lifecycle-overhead`: the member wrote no durations sidecar")


def test_rendering_an_empty_recorder_says_so() -> None:
    assert render(Spans()) == "## Durations\n\nNo durations were recorded.\n"
