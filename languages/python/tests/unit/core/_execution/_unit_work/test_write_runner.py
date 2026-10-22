"""The current rows a running group or bound range captures as the payloads
of its steps are demanded."""

from __future__ import annotations

from parallax.core._execution._unit_work.write_runner import (
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the capture a running group builds
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    CurrentRowOutput,
    TemporalRowCoordinates,
)
from tests.unit.core._execution._write_step_support import POSITION, insert, revision


def test_a_capture_stages_only_the_emitters_its_outputs_describe() -> None:
    described, other = revision(1), revision(2)
    (entry,) = insert(1).entries
    output = CurrentRowOutput(
        coordinates=TemporalRowCoordinates(POSITION, (1,), OPEN_BITEMPORAL_ENDS),
        valid_time_coverage=None,
        row=entry,
        emitter=described,
    )
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(other, None)
    capture.capture_insert(entry, None)
    assert capture.take_rows((output,)) == ()
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ((output, None),)
    assert capture.take_rows((output,)) == ()
