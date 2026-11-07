"""A write taking its captured rows lets go of them before its group ends, which
only a reachability check can see; what a group captures is graded at the unit
of work's seam."""

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
from tests.unit.core._execution._reach_support import reaches
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


def test_a_write_taking_its_rows_releases_their_documents_and_descriptions() -> None:
    described = revision(1)
    output = _output(1, described)
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ((output, {"key": 1}),)
    assert not reaches([capture], output)
    assert capture.take_rows((output,)) == ()
