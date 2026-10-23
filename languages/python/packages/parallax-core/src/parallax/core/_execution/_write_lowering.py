from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Final, NamedTuple, cast

from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import (
    InsertStatementBuilder,
    StepPayload,
    compile_write_step,
    non_insert_parameter_ceiling,
)
from parallax.core.storage_layout import RelationalDocument
from parallax.core.write_plan.payload import (
    AssignmentPayload,
    PatchedDocument,
    RowPayload,
    WritePayloadPreparer,
)
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
    "GroupedInsert",
    "LoweringCursor",
    "lowered",
    "lowered_within",
    "ordered_parameter_ceiling",
    "stream_physical",
]

_GROUPED_INSERT_ROWS: Final = 64


class GroupedInsert(NamedTuple):
    """One statement inserting a run of single-entry inserts, and how the run
    ended: at ``following``, the step that could not join it, taken but neither
    prepared nor lowered; at ``failure``, raised ordinarily preparing or
    appending a later insert, the statement then holding exactly the entries
    appended before it; or at neither, where the statement reached its capacity
    or the steps ran out."""

    statement: LoweredStatement
    following: PlannedStep | None
    failure: Exception | None


class LoweringCursor:
    """``steps`` taken one at a time, each lowered only when asked, storing the
    payload its statement demands.

    Execution's route from a sequence of Planned Steps to statements: taking a
    step reads it and prepares nothing, so a step can be looked at before
    anything is prepared for it, and only preparing or lowering it can fail.

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
        "_steps",
    )

    def __init__(
        self,
        steps: tuple[PlannedStep, ...],
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
        *,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> None:
        self._steps = iter(steps)
        self._payloads = payloads
        self._meta = meta
        self._dialect = dialect
        self._capture_insert = capture_insert
        self._capture_revision = capture_revision

    def take(self) -> PlannedStep | None:
        """The next step, or ``None`` once the steps are exhausted."""
        return next(self._steps, None)

    def lowered(self, step: PlannedStep) -> LoweredStatement:
        return self._lowered(step)

    def ordered_parameter_ceiling(self, step: PlannedStep) -> int | None:
        return ordered_parameter_ceiling(step, self._dialect)

    def lowered_within(self, step: PlannedStep, parameter_ceiling: int) -> LoweredStatement:
        return _within(step, parameter_ceiling, self._lowered(step))

    def _lowered(self, step: PlannedStep) -> LoweredStatement:
        payload = _demanded(step, self._payloads)
        if self._capture_insert is not None or self._capture_revision is not None:
            self._capture(step, payload)
        return compile_write_step(step, payload, self._meta, self._dialect)

    def _capture(self, step: PlannedStep, payload: StepPayload) -> None:
        capture_insert = self._capture_insert
        if isinstance(step, PlannedInsert):
            if capture_insert is not None:
                for entry, prepared in zip(
                    step.entries, cast("tuple[RowPayload, ...]", payload), strict=True
                ):
                    capture_insert(entry, _stored_document(prepared))
            return
        capture_revision = self._capture_revision
        if isinstance(step, PlannedTemporalRevision) and capture_revision is not None:
            capture_revision(step, _document_patches(cast("AssignmentPayload", payload)))

    def _captured_row(self, entity: EntityIdentity, entry: WriteRow) -> RowPayload:
        payload = _row_payload(self._payloads, entity, entry)
        capture_insert = self._capture_insert
        if capture_insert is not None:
            capture_insert(entry, _stored_document(payload))
        return payload

    def grouped_insert_start(self, step: PlannedStep) -> PlannedInsert | None:
        """``step`` where it can begin a grouped insert — a single-entry insert
        holding no generated value — decided before its payload is demanded;
        ``None`` where it lowers alone."""
        if (
            isinstance(step, PlannedInsert)
            and len(step.entries) == 1
            and not _generates(step.entries[0])
        ):
            return step
        return None

    def lowered_grouped_insert(self, first: PlannedInsert) -> GroupedInsert:
        """``first`` and the compatible inserts following it, as one
        multi-row statement.

        Before another step is taken the statement must have room for one more
        entry within the internal entry cap and the dialect's bind limit, and
        before a taken step's payload is demanded the step must be a
        single-entry insert of the same Entity naming the same members and
        holding no generated value; values, origins, and audit values may
        differ. Each entry's payload is the backing it already carries, or the
        one prepared now. ``first`` failing raises, and a control-flow or fatal
        exception propagates with nothing returned.
        """
        (entry,) = first.entries
        entity = first.entity
        members = entry.row.members
        builder = InsertStatementBuilder(
            entity, entry, self._captured_row(entity, entry), self._meta, self._dialect
        )
        binds = self._dialect.max_bind_parameters
        following: PlannedStep | None = None
        while builder.has_capacity(_GROUPED_INSERT_ROWS, binds):
            following = self.take()
            joining = _joining(following, entity, members)
            if joining is None:
                break
            try:
                builder.append(joining, self._captured_row(entity, joining))
            except Exception as error:
                return GroupedInsert(builder.finish(), None, error)
            following = None
        return GroupedInsert(builder.finish(), following, None)


def stream_physical(
    steps: tuple[PlannedStep, ...],
    payloads: WritePayloadPreparer,
    meta: Metamodel,
    dialect: Dialect,
    *,
    capture_insert: Callable[[WriteRow, object | None], None] | None = None,
    capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
    | None = None,
) -> Iterator[LoweredStatement]:
    """Each statement ``steps`` execute as, in order: a run of compatible
    single-entry inserts as the one statement inserting them all, and every
    other step as the one statement it lowers to, each payload captured as
    :class:`LoweringCursor` captures it.

    The runs are selected and lowered by the very cursor operations execution
    selects and lowers them by, so the statements a dry traversal of settled
    steps answers are the statements their execution runs. A run ended by a
    later insert's failure answers the statement holding the inserts before
    it, then raises that failure.
    """
    cursor = LoweringCursor(
        steps,
        payloads,
        meta,
        dialect,
        capture_insert=capture_insert,
        capture_revision=capture_revision,
    )
    step = cursor.take()
    while step is not None:
        first = cursor.grouped_insert_start(step)
        if first is None:
            yield cursor.lowered(step)
            step = cursor.take()
            continue
        statement, following, failure = cursor.lowered_grouped_insert(first)
        yield statement
        if failure is not None:
            raise failure
        step = cursor.take() if following is None else following


def lowered(
    step: PlannedStep, payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """The one statement ``step`` lowers to, storing the payload its statement
    demands: backing settlement already prepared where an entry carries it, and
    otherwise what ``payloads`` prepares now."""
    return compile_write_step(step, _demanded(step, payloads), meta, dialect)


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


def _demanded(step: PlannedStep, payloads: WritePayloadPreparer) -> StepPayload:
    match step:
        case PlannedInsert(entity=entity, entries=(entry,)):
            return (payloads.row(entity, entry) if entry.prepared is None else entry.prepared,)
        case PlannedInsert(entity=entity, entries=entries):
            return tuple(
                payloads.row(entity, entry) if entry.prepared is None else entry.prepared
                for entry in entries
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


def _row_payload(
    payloads: WritePayloadPreparer, entity: EntityIdentity, entry: WriteRow
) -> RowPayload:
    return payloads.row(entity, entry) if entry.prepared is None else entry.prepared


def _stored_document(payload: RowPayload) -> object | None:
    """The complete Structured Column document ``payload`` stores, or ``None``
    where its Table has none."""
    for contributor, value in zip(payload.contributors, payload.values, strict=True):
        if isinstance(contributor, RelationalDocument):
            return value
    return None


def _document_patches(payload: AssignmentPayload) -> PatchedDocument | None:
    """The prepared patches ``payload`` applies to its row's Structured Column,
    ``None`` where it leaves the document as stored."""
    for value in payload.values:
        if isinstance(value, PatchedDocument):
            return value
    return None


def _generates(entry: WriteRow) -> bool:
    return any(isinstance(value, MaxPlusOne) for value in entry.row.attributes.values())


def _joining(
    step: PlannedStep | None,
    entity: EntityIdentity,
    members: frozenset[AttributeIdentity | ValueObjectIdentity],
) -> WriteRow | None:
    """``step``'s one entry where it can join a grouped insert of ``entity``
    whose entries name ``members``: placement follows the Entity and the
    members named, never the values held."""
    match step:
        case PlannedInsert(entity=other, entries=(entry,)) if (
            other == entity and entry.row.members == members and not _generates(entry)
        ):
            return entry
        case _:
            return None
