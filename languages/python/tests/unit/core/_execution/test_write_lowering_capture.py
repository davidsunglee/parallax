"""What execution's lowering hands the current-row capture hooks as each
payload is demanded (execution's lowering seam, `m-unit-work` *Write Groups
complete before later work runs*).

Each insert entry is handed over with the document its payload stores as that
payload is prepared or reused, a run of grouped inserts included, and each
temporal revision with the patches its payload applies; nothing is prepared
for a capture, and a payload that fails to prepare is never handed over.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

import pytest

from parallax.core import Attr, Bitemporal, Document, DomainModel, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._write_lowering import stream_physical
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.base import INFINITY as OPEN
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, Metamodel, entity_by_name
from parallax.core.write_plan.payload import PatchedDocument
from parallax.core.write_plan.steps import (
    INFINITY,
    NEW_LINEAGE,
    STALE_WRITE,
    UNGATED,
    ExactCount,
    MilestoneTarget,
    PlannedAssignments,
    PlannedInsert,
    PlannedRow,
    PlannedStep,
    PlannedTemporalRevision,
    WriteRow,
)
from tests._support.db_port import ScriptedAdapter, Write
from tests.unit.core._execution._write_step_support import (
    POSITION,
    POSITION_META,
    T0,
    T1,
    RecordingPreparer,
    close,
    insert,
    open_flush,
    revision,
)


class _Captures:
    """Every capture handed over, in order, beside how many payloads
    ``preparer`` had prepared by then."""

    def __init__(self, preparer: RecordingPreparer | None = None) -> None:
        self.preparer = preparer
        self.seen: list[tuple[str, object, object | None, int]] = []

    def _prepared(self) -> int:
        return -1 if self.preparer is None else len(self.preparer.prepared)

    def insert(self, entry: WriteRow, document: object | None) -> None:
        self.seen.append(("insert", entry, document, self._prepared()))

    def revision(self, step: PlannedTemporalRevision, patched: PatchedDocument | None) -> None:
        self.seen.append(("revision", step, patched, self._prepared()))


def _streamed(
    steps: tuple[PlannedStep, ...],
    preparer: Any,
    captures: _Captures | None,
    meta: Metamodel = POSITION_META,
    *,
    inserts: bool = True,
) -> int:
    hooks: dict[str, Any] = {}
    if captures is not None:
        hooks["capture_revision"] = captures.revision
        if inserts:
            hooks["capture_insert"] = captures.insert
    return sum(1 for _ in stream_physical(steps, preparer, meta, POSTGRES, **hooks))


def test_each_grouped_insert_entry_is_handed_over_as_its_payload_is_prepared() -> None:
    steps = (insert(1), insert(2), insert(3))
    preparer = RecordingPreparer(ScriptedAdapter(), steps)
    captures = _Captures(preparer)
    assert _streamed(steps, preparer, captures) == 1
    # A Table with no Structured Column stores no document.
    assert captures.seen == [
        ("insert", step.entries[0], None, position + 1) for position, step in enumerate(steps)
    ]


def test_a_reused_payload_is_handed_over_without_preparing_anything() -> None:
    planned = insert(1)
    (entry,) = planned.entries
    reused = entry.with_prepared(build_write_planner(POSITION_META).payloads.row(POSITION, entry))
    steps = (type(planned)(entity=POSITION, entries=(reused,)),)
    preparer = RecordingPreparer(ScriptedAdapter(), steps)
    captures = _Captures(preparer)
    _streamed(steps, preparer, captures)
    assert captures.seen == [("insert", reused, None, 0)]
    assert preparer.prepared == []


def test_a_revision_is_handed_over_with_the_patches_its_payload_applies() -> None:
    steps = (close(1), revision(2), insert(3))
    preparer = RecordingPreparer(ScriptedAdapter(), steps)
    captures = _Captures(preparer)
    _streamed(steps, preparer, captures)
    # A close stores no current row; a revision of a Table with no Structured
    # Column applies no patch.
    assert [(kind, subject, payload) for kind, subject, payload, _ in captures.seen] == [
        ("revision", steps[1], None),
        ("insert", steps[2].entries[0], None),
    ]


def test_a_payload_that_fails_to_prepare_is_never_handed_over() -> None:
    steps = (insert(1), insert(2), insert(3))
    preparer = RecordingPreparer(
        ScriptedAdapter(), steps, failing=1, failure=RuntimeError("refused")
    )
    captures = _Captures(preparer)
    with pytest.raises(RuntimeError, match="refused"):
        _streamed(steps, preparer, captures)
    assert [subject for _kind, subject, _payload, _ in captures.seen] == [steps[0].entries[0]]


def test_lowering_without_hooks_prepares_exactly_what_it_did_with_them() -> None:
    steps = (close(1), revision(2), insert(3), insert(4))
    without = RecordingPreparer(ScriptedAdapter(), steps)
    with_hooks = RecordingPreparer(ScriptedAdapter(), steps)
    _streamed(steps, without, None)
    _streamed(steps, with_hooks, _Captures(with_hooks))
    assert without.positions == with_hooks.positions


def test_the_executor_relays_the_hooks_to_the_statements_it_executes() -> None:
    steps = (revision(2), insert(3))
    port = ScriptedAdapter(Write(), Write())
    captures = _Captures()
    executor = WriteStepExecutor(
        port, payloads=build_write_planner(POSITION_META).payloads, meta=POSITION_META
    )
    with open_flush() as flush:
        assert (
            executor.execute(
                steps,
                allocates=False,
                flush=flush,
                capture_insert=captures.insert,
                capture_revision=captures.revision,
            )
            == ()
        )
    assert [(kind, subject) for kind, subject, _payload, _ in captures.seen] == [
        ("revision", steps[0]),
        ("insert", steps[1].entries[0]),
    ]


def test_every_entry_of_an_insert_lowered_alone_is_handed_over() -> None:
    entries = (*insert(1).entries, *insert(2).entries)
    steps = (PlannedInsert(entity=POSITION, entries=entries),)
    captures = _Captures()
    assert _streamed(steps, build_write_planner(POSITION_META).payloads, captures) == 1
    assert [subject for _kind, subject, _payload, _ in captures.seen] == list(entries)


def test_inserts_are_not_handed_over_where_only_revisions_are_captured() -> None:
    steps = (insert(1), revision(3))
    captures = _Captures()
    _streamed(steps, build_write_planner(POSITION_META).payloads, captures, inserts=False)
    assert [(kind, subject) for kind, subject, _payload, _ in captures.seen] == [
        ("revision", steps[1])
    ]


class Note(Bitemporal, table="capture_note", namespace="parallax.capture", layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_NOTES: Final = model_of(DomainModel(Note))
_FOUND = entity_by_name(_NOTES, "Note")
assert _FOUND is not None
_NOTE: Final = _FOUND.identity


def _note(name: str) -> AttributeIdentity:
    return AttributeIdentity(_NOTE, name)


def test_a_structured_column_document_is_handed_over_whole_and_a_revision_with_its_patches() -> (
    None
):
    row = PlannedRow(
        attributes={
            _note("id"): 1,
            _note("label"): "opened",
            _note("validStart"): T0,
            _note("validEnd"): OPEN,
            _note("txStart"): T1,
            _note("txEnd"): OPEN,
        }
    )
    opened = PlannedInsert(entity=_NOTE, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))
    revised = PlannedTemporalRevision(
        entity=_NOTE,
        target=MilestoneTarget(
            key_attributes=(_note("id"),),
            key_values=(2,),
            end_attributes=(_note("validEnd"), _note("txEnd")),
            end_values=(INFINITY, INFINITY),
        ),
        assignments=PlannedAssignments(attributes={_note("label"): "revised"}),
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
        predecessor_document_is_object=True,
    )
    captures = _Captures()
    _streamed((opened, revised), build_write_planner(_NOTES).payloads, captures, _NOTES)
    (inserted, document, _), (revision_kind, patched, _) = (
        (kind, payload, prepared) for kind, _subject, payload, prepared in captures.seen
    )
    assert inserted == "insert"
    assert isinstance(document, Mapping)
    assert cast("Mapping[str, object]", document)["label"] == "opened"
    assert revision_kind == "revision"
    assert isinstance(patched, PatchedDocument)
    assert patched.patches
