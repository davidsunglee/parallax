from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import NamedTuple, cast

from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    EntityIdentity,
    Metamodel,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import (
    GroupedEffectBuilder,
    InsertStatementBuilder,
    StepPayload,
    compile_write_step,
    non_insert_parameter_ceiling,
)
from parallax.core.write_plan.payload import (
    AssignmentPayload,
    EffectSlots,
    InsertPayload,
    PatchedDocument,
    RowSlots,
    WritePayloadPreparer,
)
from parallax.core.write_plan.plan import EffectSpan
from parallax.core.write_plan.steps import (
    ExactCount,
    KeyTarget,
    MaxPlusOne,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = [
    "GroupedEffect",
    "GroupedInsert",
    "LoweringCursor",
    "lowered",
    "lowered_within",
    "ordered_parameter_ceiling",
    "stream_physical",
]


class GroupedInsert(NamedTuple):
    """One statement inserting a run of single-entry inserts, and how the run
    ended: at ``following``, the step that could not join it, taken but neither
    prepared nor lowered; at ``failure``, raised ordinarily preparing or
    appending a later insert, the statement then holding exactly the entries
    appended before it; or at neither, where the steps ran out."""

    statement: LoweredStatement
    following: PlannedStep | None
    failure: Exception | None


class GroupedEffect(NamedTuple):
    """One statement applying the effects of one effect span, and how its
    lowering ended: with every effect of the span in ``steps``, or at
    ``failure``, raised ordinarily preparing or appending a later effect, the
    statement then holding exactly the effects in ``steps``. Source ordinal
    ``i`` of the statement's result is ``steps[i - 1]``."""

    statement: LoweredStatement
    steps: tuple[PlannedStep, ...]
    failure: Exception | None


class LoweringCursor:
    """``steps`` taken one at a time, each lowered only when asked, storing the
    payload its statement demands.

    Execution's route from a sequence of Planned Steps to statements: taking a
    step reads it and prepares nothing, so a step can be looked at before
    anything is prepared for it, and only preparing or lowering it can fail.

    ``effect_spans`` are the grouped effects among ``steps``, which a dialect
    binding arrays presents as one statement each; a dialect binding none
    reads none of them.

    Each insert entry's payload, as it is demanded, hands ``capture_insert``
    the entry and the Structured Column document it stores — ``None`` where it
    stores none — and each temporal revision's hands ``capture_revision`` the
    revision and the patches it applies to that document — ``None`` where it
    applies none — where they are given.
    """

    __slots__ = (
        "_capture_insert",
        "_capture_revision",
        "_dialect",
        "_meta",
        "_payloads",
        "_position",
        "_span",
        "_span_slots",
        "_spans",
        "_steps",
    )

    def __init__(
        self,
        steps: tuple[PlannedStep, ...],
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
        *,
        effect_spans: tuple[EffectSpan, ...] = (),
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> None:
        self._steps = steps
        self._position = -1
        self._spans = iter(effect_spans if dialect.binds_arrays else ())
        self._span: EffectSpan | None = next(self._spans, None)
        self._span_slots: EffectSlots | None = None
        self._payloads = payloads
        self._meta = meta
        self._dialect = dialect
        self._capture_insert = capture_insert
        self._capture_revision = capture_revision

    def take(self) -> PlannedStep | None:
        """The next step, or ``None`` once the steps are exhausted."""
        steps = self._steps
        position = self._position + 1
        if position >= len(steps):
            self._position = len(steps)
            return None
        self._position = position
        return steps[position]

    def lowered(self, step: PlannedStep) -> LoweredStatement:
        return self._lowered(step)

    def ordered_parameter_ceiling(self, step: PlannedStep) -> int | None:
        return ordered_parameter_ceiling(step, self._dialect)

    def lowered_within(self, step: PlannedStep, parameter_ceiling: int) -> LoweredStatement:
        return _within(step, parameter_ceiling, self._lowered(step))

    def _lowered(self, step: PlannedStep) -> LoweredStatement:
        return compile_write_step(step, self._demanded_payload(step), self._meta, self._dialect)

    def _demanded_payload(self, step: PlannedStep) -> StepPayload:
        payload = _demanded_payload(step, self._payloads)
        if self._capture_insert is not None or self._capture_revision is not None:
            self._capture(step, payload)
        return payload

    def grouped_effect_start(self, step: PlannedStep) -> EffectSpan | None:
        """The effect span ``step``, the step last taken, opens, where its
        statement fits the dialect's parameter limit; ``None`` where ``step``
        opens none and lowers as it would alone. Decided before any payload is
        demanded, and answered alike however often it is asked."""
        span = self._span
        position = self._position
        while span is not None and span.start < position:
            span = self._span = next(self._spans, None)
            self._span_slots = None
        if span is None or span.start != position or self._steps[position] is not step:
            return None
        slots = self._span_slots
        if slots is None:
            slots = self._span_slots = self._payloads.effect_slots(step.entity, span.shape)
        return span if slots.parameter_count <= self._dialect.max_bind_parameters else None

    def lowered_grouped_effect(self, first: PlannedStep, span: EffectSpan) -> GroupedEffect:
        """``first`` and every later effect of ``span``, taken in order, as one
        statement whose source binds one array per source column.

        The span already says which steps the statement holds, so nothing
        beyond it is taken. ``first`` failing raises; a later effect failing
        ordinarily to be prepared or appended ends the statement before it;
        and a control-flow or fatal exception propagates with nothing
        returned.
        """
        slots = self._span_slots
        if slots is None or self._span is not span:
            raise SqlGenError(f"{first.entity.canonical}: a grouped effect opens at its own span")
        builder = GroupedEffectBuilder(slots, self._meta, self._dialect)
        builder.append(first, self._demanded_payload(first))
        steps = [first]
        for _ in range(span.stop - span.start - 1):
            step = cast("PlannedStep", self.take())
            try:
                builder.append(step, self._demanded_payload(step))
            except Exception as error:
                return GroupedEffect(builder.finish(), tuple(steps), error)
            steps.append(step)
        return GroupedEffect(builder.finish(), tuple(steps), None)

    def _capture(self, step: PlannedStep, payload: StepPayload) -> None:
        capture_insert = self._capture_insert
        if isinstance(step, PlannedInsert):
            if capture_insert is not None:
                inserted = cast("InsertPayload", payload)
                for entry, cells in zip(step.entries, inserted.rows, strict=True):
                    capture_insert(entry, _stored_document(inserted.slots, cells))
            return
        capture_revision = self._capture_revision
        if isinstance(step, PlannedTemporalRevision) and capture_revision is not None:
            capture_revision(step, _document_patches(cast("AssignmentPayload", payload)))

    def _captured_cells(
        self, entity: EntityIdentity, slots: RowSlots, entry: WriteRow
    ) -> tuple[object, ...]:
        cells = _entry_cells(entity, slots, entry)
        capture_insert = self._capture_insert
        if capture_insert is not None:
            capture_insert(entry, _stored_document(slots, cells))
        return cells

    def grouped_insert_start(self, step: PlannedStep) -> PlannedInsert | None:
        """``step`` where it can begin a grouped insert — a single-entry insert
        holding no generated value, on a dialect binding the column arrays a
        multi-row insert takes — decided before its payload is demanded;
        ``None`` where it lowers alone."""
        if (
            self._dialect.binds_arrays
            and isinstance(step, PlannedInsert)
            and len(step.entries) == 1
            and not _generates(step.entries[0])
        ):
            return step
        return None

    def lowered_grouped_insert(self, first: PlannedInsert) -> GroupedInsert:
        """``first`` and every compatible insert following it, as one
        multi-row statement.

        Its column arrays bind one parameter per cell slot however many entries
        join, so no entry count or bind limit ends the run. Before a taken
        step's payload is demanded the step must be a single-entry insert of
        the same Entity naming the same members and holding no generated
        value; values, origins, and audit values may differ. Every entry stores
        the Row Slots ``first`` selects, and each entry's cells are the backing
        it already carries, or the ones gathered now. ``first`` failing raises,
        and a control-flow or fatal exception propagates with nothing returned.
        """
        (entry,) = first.entries
        entity = first.entity
        presence = entry.row.presence
        slots = _entry_slots(self._payloads, entity, entry)
        builder = InsertStatementBuilder(
            slots, self._captured_cells(entity, slots, entry), self._meta, self._dialect
        )
        while True:
            following = self.take()
            joining = _joining(following, entity, presence)
            if joining is None:
                break
            try:
                builder.append(self._captured_cells(entity, slots, joining))
            except Exception as error:
                return GroupedInsert(builder.finish(), None, error)
        return GroupedInsert(builder.finish(), following, None)


def stream_physical(
    steps: tuple[PlannedStep, ...],
    payloads: WritePayloadPreparer,
    meta: Metamodel,
    dialect: Dialect,
    *,
    effect_spans: tuple[EffectSpan, ...] = (),
    capture_insert: Callable[[WriteRow, object | None], None] | None = None,
    capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
    | None = None,
) -> Iterator[LoweredStatement]:
    """Each statement ``steps`` execute as, in order: the effects of one of
    ``effect_spans`` as the one grouped effect applying them all, a run of
    compatible single-entry inserts as the one statement inserting them all,
    and every other step as the one statement it lowers to, each payload
    captured as :class:`LoweringCursor` captures it.

    The statements are selected and lowered by the very cursor operations
    execution selects and lowers them by, so the statements a dry traversal of
    settled steps answers are the statements their execution runs. A grouped
    effect or run ended by a later step's failure answers the statement
    holding the steps before it, then raises that failure.
    """
    cursor = LoweringCursor(
        steps,
        payloads,
        meta,
        dialect,
        effect_spans=effect_spans,
        capture_insert=capture_insert,
        capture_revision=capture_revision,
    )
    step = cursor.take()
    while step is not None:
        span = cursor.grouped_effect_start(step)
        if span is not None:
            grouped = cursor.lowered_grouped_effect(step, span)
            yield grouped.statement
            if grouped.failure is not None:
                raise grouped.failure
            step = cursor.take()
            continue
        first = cursor.grouped_insert_start(step)
        if first is None:
            yield cursor.lowered(step)
            step = cursor.take()
            continue
        statement, following, failure = cursor.lowered_grouped_insert(first)
        yield statement
        if failure is not None:
            raise failure
        step = following


def lowered(
    step: PlannedStep, payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """The one statement ``step`` lowers to, storing the payload its statement
    demands: backing settlement already prepared where an entry carries it, and
    otherwise what ``payloads`` prepares now."""
    return compile_write_step(step, _demanded_payload(step, payloads), meta, dialect)


def ordered_parameter_ceiling(step: PlannedStep, dialect: Dialect) -> int | None:
    """A conservative upper bound on the SQL parameters ``step``'s statement
    carries where ordered write transport can present it, computed before its
    payload is demanded; ``None`` where the step must run alone.

    Only a count-only non-insert step on one row qualifies — a temporal close, guard,
    revision, or removal, or a Non-Temporal update or delete of one key that
    expects an exact count — and only one whose ceiling fits the dialect's
    configured parameter limit. Every other step, and one whose ceiling exceeds
    that limit, runs alone.
    """
    match step:
        case (
            PlannedClose()
            | PlannedTemporalRevision()
            | PlannedTemporalRemoval()
            | PlannedTemporalGuard()
            | PlannedUpdate(target=KeyTarget(key_values=(_,)), affected_rows=ExactCount())
            | PlannedDelete(target=KeyTarget(key_values=(_,)), affected_rows=ExactCount())
        ):
            ceiling = non_insert_parameter_ceiling(step)
            return ceiling if ceiling <= dialect.max_bind_parameters else None
        case _:
            return None


def lowered_within(
    step: PlannedStep,
    parameter_ceiling: int,
    payloads: WritePayloadPreparer,
    meta: Metamodel,
    dialect: Dialect,
) -> LoweredStatement:
    """``step``'s one statement, which carries no more SQL parameters than the
    ``parameter_ceiling`` its shape promised before its payload was demanded.

    A statement exceeding its promise is refused as a lowering failure rather
    than presented to transport selected on the strength of that promise.
    """
    return _within(step, parameter_ceiling, lowered(step, payloads, meta, dialect))


def _within(
    step: PlannedStep, parameter_ceiling: int, statement: LoweredStatement
) -> LoweredStatement:
    binds = len(statement.binds)
    if binds > parameter_ceiling:
        raise SqlGenError(
            f"{step.entity.canonical}: a statement carrying {binds} binds exceeds the "
            f"{parameter_ceiling} its shape promised before its payload was prepared"
        )
    return statement


def _demanded_payload(step: PlannedStep, payloads: WritePayloadPreparer) -> StepPayload:
    match step:
        case PlannedInsert(entity=entity, entries=entries):
            slots = _entry_slots(payloads, entity, entries[0])
            return InsertPayload(
                slots, tuple([_entry_cells(entity, slots, entry) for entry in entries])
            )
        case PlannedTemporalRevision():
            return _predictable_revision(step, payloads.assignments(step.entity, step.assignments))
        case PlannedUpdate() | PlannedClose():
            return payloads.assignments(step.entity, step.assignments)
        case _:
            return None


def _predictable_revision(
    step: PlannedTemporalRevision, payload: AssignmentPayload
) -> AssignmentPayload:
    if not step.predecessor_document_is_object and any(
        isinstance(value, PatchedDocument) for value in payload.values
    ):
        raise SqlGenError(
            f"{step.entity.canonical}: a revision patches the Structured Column of a row "
            "whose stored document is not known to be an object"
        )
    return payload


def _entry_slots(
    payloads: WritePayloadPreparer, entity: EntityIdentity, entry: WriteRow
) -> RowSlots:
    """The Row Slots ``entry`` stores: those of the backing it carries, or the
    ones its presence selects."""
    prepared = entry.prepared
    if prepared is None:
        return payloads.row_slots(entity, entry.row.presence)
    return prepared.slots


def _entry_cells(entity: EntityIdentity, slots: RowSlots, entry: WriteRow) -> tuple[object, ...]:
    """``entry``'s cells under ``slots``: the backing settlement already
    prepared from it, else gathered now.

    Backing prepared from other inputs than ``entry``'s own, or storing other
    cells than ``slots`` places, is a broken caller contract.
    """
    prepared = entry.prepared
    if prepared is None:
        return slots.cells(entry)
    if not prepared.prepared_from(entry) or prepared.entity != entity:
        raise SqlGenError(f"{entity.canonical}: a prepared Row Payload belongs to another entry")
    if prepared.slots is not slots and prepared.slots.contributors != slots.contributors:
        raise SqlGenError(f"{entity.name!r}: every entry of one insert stores the same cells")
    return prepared.values


def _stored_document(slots: RowSlots, cells: tuple[object, ...]) -> object | None:
    """The complete Structured Column document ``cells`` store, or ``None``
    where their Table has none."""
    index = slots.shared_document
    return None if index is None else cells[index]


def _document_patches(payload: AssignmentPayload) -> PatchedDocument | None:
    """The prepared patches ``payload`` applies to its row's Structured Column,
    ``None`` where it leaves the document as stored."""
    for value in payload.values:
        if isinstance(value, PatchedDocument):
            return value
    return None


def _generates(entry: WriteRow) -> bool:
    return any(isinstance(value, MaxPlusOne) for value in entry.row.cells)


def _joining(step: PlannedStep | None, entity: EntityIdentity, presence: int) -> WriteRow | None:
    """``step``'s one entry where it can join a grouped insert of ``entity``
    whose entries state the members ``presence`` names: placement follows the
    Entity and the members stated, never the values held."""
    match step:
        case PlannedInsert(entity=other, entries=(entry,)) if (
            other == entity and entry.row.presence == presence and not _generates(entry)
        ):
            return entry
        case _:
            return None
