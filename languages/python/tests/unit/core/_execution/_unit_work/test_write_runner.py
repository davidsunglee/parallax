"""The current rows a running Write Group captures as the payloads of its
steps are demanded."""

from __future__ import annotations

from parallax.core._execution._unit_work.write_runner import (
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the capture a running group builds
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    CurrentRowOutput,
    SettledWrite,
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


def test_a_capture_stages_only_the_emitters_its_outputs_describe() -> None:
    described, other = revision(1), revision(2)
    output = _output(1, described)
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(other, None)
    capture.capture_insert(output.row, None)
    assert capture.take_rows((output,)) == ()
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ((output, {"key": 1}),)
    assert capture.take_rows((output,)) == ()


def test_each_write_takes_its_own_rows_by_emitter_whatever_the_group_order() -> None:
    first, second = revision(1), revision(2)
    (entry,) = insert(3).entries
    outputs = (_output(1, first), _output(2, second), _output(3, entry))
    writes = (
        SettledWrite(current_outputs=outputs[:1]),
        SettledWrite(current_outputs=outputs[1:]),
    )
    capture = _CurrentRowCapture.for_writes(writes)
    assert capture is not None
    capture.capture_insert(entry, {"stored": 3})
    capture.capture_revision(second, None)
    capture.capture_revision(first, None)
    assert capture.take_rows(writes[1].current_outputs) == (
        (outputs[1], {"key": 2}),
        (outputs[2], {"stored": 3}),
    )
    assert capture.take_rows(writes[0].current_outputs) == ((outputs[0], {"key": 1}),)


def test_writes_describing_no_output_build_no_capture() -> None:
    assert _CurrentRowCapture.for_writes((SettledWrite(), SettledWrite())) is None


def test_a_write_taking_its_rows_releases_their_descriptions() -> None:
    described = revision(1)
    output = _output(1, described)
    capture = _CurrentRowCapture((output,))
    assert capture.take_rows((output,)) == ()
    assert not reaches([capture], output)
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ()


def test_release_drops_every_description_and_staged_document_never_taken() -> None:
    output = _output(1, revision(1))
    (entry,) = insert(2).entries
    inserted = _output(2, entry)
    document = {"stored": 2}
    capture = _CurrentRowCapture((output, inserted))
    capture.capture_insert(entry, document)
    capture.release()
    assert not reaches([capture], document)
    assert not reaches([capture], output)
    assert capture.take_rows((inserted,)) == ()
