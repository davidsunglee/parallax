"""A write taking its captured rows receives each, once, with the document its
execution stored; what a group captures is graded at the unit of work's seam."""

from __future__ import annotations

from parallax.core._execution._unit_work.write_runner import (
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the capture a running group builds
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    CurrentRowOutput,
    TemporalRowCoordinates,
)
from parallax.core.write_plan.steps import PlannedTemporalRevision, WriteRow
from tests.unit.core._execution._write_step_support import POSITION, insert, revision


def _output(key: int, emitter: WriteRow | PlannedTemporalRevision) -> CurrentRowOutput:
    (entry,) = insert(key).entries
    return CurrentRowOutput(
        coordinates=TemporalRowCoordinates(POSITION, (key,), OPEN_BITEMPORAL_ENDS),
        valid_time_coverage=None,
        row=entry,
        emitter=emitter,
        predecessor_document={"key": key},
    )


def test_a_write_takes_each_row_once_with_the_document_its_execution_stored() -> None:
    described = revision(1)
    output = _output(1, described)
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ((output, {"key": 1}),)
    assert capture.take_rows((output,)) == ()
