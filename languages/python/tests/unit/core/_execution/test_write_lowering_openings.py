"""Grouped inserts through execution's shared physical lowering (`m-sql`
*Requested ranges* and *Batched insert / update*, `m-execution` *Flush
execution*), taken here mostly through temporal openings.

A run of contiguous single-entry inserts of one Entity that name the same
members and hold no generated value compiles, one entry at a time, into one
multi-row insert binding one array per Column, each holding the bind the
inserts' own statements carry at its position, in order. The run ends untouched
at a step that cannot join it, and at no entry count or bind limit; a later
opening's ordinary failure leaves the statement holding exactly the openings
before it. A dialect binding no arrays groups nothing. A dry traversal of
settled steps answers the statements execution runs, through the same cursor
operations.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance.class_models import MODELS
from parallax.core import Attr, Bitemporal, Document, DomainModel, ValueObject, attr
from parallax.core._execution._write_lowering import (
    GroupedInsert,
    LoweringCursor,
    lowered,
    stream_physical,
)
from parallax.core.base import INFINITY as OPEN
from parallax.core.db_port import ArrayBind, JsonDocument
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.unit_work import KeyedWriteInstruction
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import PredecessorRow, TemporalObservation
from parallax.core.write_plan.managed_row import ManagedRow
from parallax.core.write_plan.payload import RowPayload, RowSlots
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    ExactCount,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
    RowOrigin,
    WriteRow,
)
from tests._support.clock_probes import instant_at
from tests._support.lowering_probes import lower_instruction, lower_instruction_steps, lowered_steps
from tests._support.managed_rows import managed_row_of
from tests._support.row_slots import observed_slots
from tests.unit._corpus_model_support import corpus_records, formed

_META: Final = model_of(MODELS["position"])
_ENTITY = entity_by_name(_META, "Position")
assert _ENTITY is not None
_POSITION: Final = _ENTITY.identity
_JAN, _MAR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9))
_AT: Final = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)


def _attr(name: str, entity: EntityIdentity = _POSITION) -> AttributeIdentity:
    return AttributeIdentity(entity, name)


def _row(
    key: int,
    start: dt.datetime,
    end: object = OPEN,
    *,
    value: object = Decimal("1.00"),
    account: object = "A-1",
) -> ManagedRow:
    return managed_row_of(
        _META,
        {
            _attr("id"): key,
            _attr("acctNum"): account,
            _attr("value"): value,
            _attr("validStart"): start,
            _attr("validEnd"): end,
            _attr("txStart"): _AT,
            _attr("txEnd"): OPEN,
        },
    )


def _opening(row: ManagedRow, origin: RowOrigin = NEW_LINEAGE) -> PlannedInsert:
    executed = (_attr("value"),) if isinstance(origin, ChangedFrom) else ()
    return PlannedInsert(
        entity=_POSITION, entries=(WriteRow(row=row, origin=origin, executed=executed),)
    )


_PREDECESSOR: Final = PredecessorRow(
    members={"id": 1, "acctNum": "A-1", "value": Decimal("1.00"), "validStart": _JAN}
)


def _openings(count: int) -> tuple[PlannedInsert, ...]:
    """``count`` adjacent openings of object 1 from January, a month each, of
    every origin in turn and of differing values."""
    origins: tuple[RowOrigin, ...] = (
        CarriedFrom(_PREDECESSOR),
        ChangedFrom(_PREDECESSOR),
        NEW_LINEAGE,
    )
    return tuple(
        _opening(
            _row(
                1,
                dt.datetime(2024, 1 + index, 1, tzinfo=dt.UTC),
                dt.datetime(2024, 2 + index, 1, tzinfo=dt.UTC),
                value=Decimal(index + 1),
            ),
            origins[index % len(origins)],
        )
        for index in range(count)
    )


def _close(key: int) -> PlannedClose:
    return PlannedClose(
        entity=_POSITION,
        target=MilestoneTarget(
            key_attributes=(_attr("id"),),
            key_values=(key,),
            end_attributes=(_attr("validEnd"), _attr("txEnd")),
            end_values=(OPEN_END, OPEN_END),
        ),
        assignments=PlannedAssignments(attributes={_attr("txEnd"): _AT}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


class _Preparer(LayoutPayloadPreparer):
    """The model's own preparer, recording every row it prepares and failing
    with ``failing``'s exception for the rows it names."""

    __slots__ = ("failing", "prepared")

    def __init__(
        self, meta: Metamodel = _META, failing: Mapping[int, BaseException] | None = None
    ) -> None:
        super().__init__(meta)
        self.prepared: list[WriteRow] = []
        self.failing = dict(failing or {})

    def row_slots(self, entity: EntityIdentity, presence: int) -> RowSlots:
        return observed_slots(super().row_slots(entity, presence), self._prepare)

    def _prepare(self, write_row: WriteRow) -> None:
        failure = self.failing.get(id(write_row))
        if failure is not None:
            raise failure
        self.prepared.append(write_row)


def _cursor(
    steps: tuple[PlannedStep, ...],
    preparer: LayoutPayloadPreparer | None = None,
    dialect: Dialect = POSTGRES,
) -> LoweringCursor:
    return LoweringCursor(
        steps, LayoutPayloadPreparer(_META) if preparer is None else preparer, _META, dialect
    )


def _remaining(cursor: LoweringCursor) -> list[PlannedStep]:
    rest: list[PlannedStep] = []
    while (step := cursor.take()) is not None:
        rest.append(step)
    return rest


def _grouped(cursor: LoweringCursor) -> GroupedInsert:
    first = cursor.grouped_insert_start(_first(cursor))
    assert first is not None
    return cursor.lowered_grouped_insert(first)


def _first(cursor: LoweringCursor) -> PlannedStep:
    step = cursor.take()
    assert step is not None
    return step


def _alone(step: PlannedStep, meta: Metamodel = _META) -> LoweredStatement:
    return lowered(step, LayoutPayloadPreparer(meta), meta, POSTGRES)


_ARRAY_ELEMENTS: Final[Mapping[str, tuple[str, ...]]] = {
    "position": ("bigint", "text", "decimal", *("timestamptz",) * 4),
    "opn_columns_span": ("bigint", *("timestamptz",) * 4, "jsonb", "jsonb"),
    "opn_document_span": ("bigint", *("timestamptz",) * 4, "jsonb"),
}
"""Each test Table's Columns' array element types, in Table Layout order."""


def _spelled(statement: LoweredStatement) -> tuple[str, tuple[object, ...]]:
    """``statement``'s text and binds, each array bind as its elements."""
    return statement.sql, tuple(
        bind.values if isinstance(bind, ArrayBind) else bind for bind in statement.binds
    )


def _joined(*steps: PlannedStep, meta: Metamodel = _META) -> tuple[str, tuple[object, ...]]:
    """What ``steps``' own statements spell together: one step's own text and
    binds, or the first's column list over one array per Column, each holding
    every step's bind at its position, in order, a document as itself."""
    statements = [_alone(step, meta) for step in steps]
    for statement in statements:
        assert statement.sql == statements[0].sql
    if len(statements) == 1:
        return _spelled(statements[0])
    head, _values = statements[0].sql.split(" values ")
    table = head.removeprefix("insert into ").split("(")[0]
    arrays = ", ".join(f"cast(? as {element}[])" for element in _ARRAY_ELEMENTS[table])
    return f"{head} select * from unnest({arrays})", tuple(
        [bind.value if isinstance(bind, JsonDocument) else bind for bind in column]
        for column in zip(*(statement.binds for statement in statements), strict=True)
    )


def _wire(*steps: PlannedStep, meta: Metamodel = _META) -> tuple[object, ...]:
    """What ``steps``' own statements project together: one step's own Wire
    binds, or one list per Column of every step's Wire bind there, in order."""
    projected = [_alone(step, meta).wire_binds() for step in steps]
    if len(projected) == 1:
        return projected[0]
    return tuple(list(column) for column in zip(*projected, strict=True))


# --------------------------------------------------------------------------- #
# Which steps begin a grouped insert.                                          #
# --------------------------------------------------------------------------- #


def test_any_single_entry_insert_without_generated_values_begins_a_grouped_insert() -> None:
    (opening,) = _openings(1)
    assert _cursor(()).grouped_insert_start(opening) is opening
    account_meta = model_of(MODELS["account"])
    account = entity_by_name(account_meta, "Account")
    assert account is not None
    non_temporal = PlannedInsert(
        entity=account.identity,
        entries=(
            WriteRow(
                row=managed_row_of(
                    account_meta,
                    {
                        _attr("id", account.identity): 1,
                        _attr("owner", account.identity): "Ada",
                        _attr("balance", account.identity): Decimal(5),
                    },
                ),
                origin=NEW_LINEAGE,
            ),
        ),
    )
    account_cursor = LoweringCursor((), LayoutPayloadPreparer(account_meta), account_meta, POSTGRES)
    assert account_cursor.grouped_insert_start(non_temporal) is non_temporal


def test_every_other_step_lowers_alone() -> None:
    (opening,) = _openings(1)
    generated = _opening(
        managed_row_of(_META, {**opening.entries[0].row.attributes, _attr("id"): MAX_PLUS_ONE})
    )
    logical = PlannedInsert(entity=_POSITION, entries=(*opening.entries, *_openings(2)[1].entries))
    cursor = _cursor(())
    for step in (generated, logical, _close(1)):
        assert cursor.grouped_insert_start(step) is None


def test_no_insert_begins_a_grouped_insert_on_a_dialect_binding_no_arrays() -> None:
    (opening,) = _openings(1)
    expanding = replace(POSTGRES, name="mariadb", binds_arrays=False)
    steps = _openings(3)
    assert _cursor((), dialect=expanding).grouped_insert_start(opening) is None
    statements = list(stream_physical(steps, LayoutPayloadPreparer(_META), _META, expanding))
    assert [_spelled(statement) for statement in statements] == [_joined(step) for step in steps]


# --------------------------------------------------------------------------- #
# One statement for a compatible run.                                          #
# --------------------------------------------------------------------------- #


def test_a_run_of_openings_is_one_statement_of_every_entry_in_order() -> None:
    steps = _openings(4)
    preparer = _Preparer()
    cursor = _cursor(steps, preparer)
    statement, following, failure = _grouped(cursor)
    assert _spelled(statement) == _joined(*steps)
    assert statement.wire_binds() == _wire(*steps)
    assert statement.is_compiler_proven
    assert (following, failure, _remaining(cursor)) == (None, None, [])
    assert preparer.prepared == [step.entries[0] for step in steps]


def test_a_runs_arrays_name_their_element_types_and_need_no_span_metadata() -> None:
    statement, _following, _failure = _grouped(_cursor(_openings(3)))
    assert [type(bind) for bind in statement.binds] == [ArrayBind] * 7
    assert (statement.typed_bind_spans, statement.wire_bind_overrides) == ((), ())
    assert statement.wire_binds()[6] == ["infinity"] * 3


def test_backing_an_entry_already_carries_is_inserted_without_preparing_it_again() -> None:
    plain = _openings(3)
    backing = LayoutPayloadPreparer(_META)
    steps = tuple(
        replace(
            step,
            entries=(step.entries[0].with_prepared(backing.row(_POSITION, step.entries[0])),),
        )
        for step in plain
    )
    preparer = _Preparer()
    statement, _following, _failure = _grouped(_cursor(steps, preparer))
    assert preparer.prepared == []
    assert _spelled(statement) == _joined(*plain)


# --------------------------------------------------------------------------- #
# Where a run ends.                                                            #
# --------------------------------------------------------------------------- #


def _incompatible() -> dict[str, PlannedStep]:
    (opening,) = _openings(1)
    attributes = dict(opening.entries[0].row.attributes)
    other_members = {key: value for key, value in attributes.items() if key != _attr("acctNum")}
    other_object = _opening(_row(2, _JUN))
    return {
        "effect": _close(1),
        "other-members": _opening(managed_row_of(_META, other_members)),
        "generated": _opening(managed_row_of(_META, {**attributes, _attr("id"): MAX_PLUS_ONE})),
        "logical-multi-entry": replace(
            other_object, entries=(*other_object.entries, *other_object.entries)
        ),
    }


@pytest.mark.parametrize("kind", sorted(_incompatible()))
def test_a_step_that_cannot_join_ends_the_run_taken_but_unprepared(kind: str) -> None:
    boundary = _incompatible()[kind]
    run = _openings(2)
    steps = (*run, boundary, *_openings(1))
    preparer = _Preparer()
    cursor = _cursor(steps, preparer)
    statement, following, failure = _grouped(cursor)
    assert following is boundary
    assert failure is None
    assert _spelled(statement) == _joined(*steps[:2])
    assert _remaining(cursor) == list(steps[len(run) + 1 :])
    assert preparer.prepared == [step.entries[0] for step in run]


def test_another_objects_opening_of_the_same_shape_joins_the_run() -> None:
    steps = (*_openings(1), _opening(_row(2, _JUN)))
    statement, following, _failure = _grouped(_cursor(steps))
    assert following is None
    assert _spelled(statement) == _joined(*steps)


def test_no_entry_count_ends_a_run() -> None:
    steps = tuple(_opening(_row(key, _JAN)) for key in range(1, 71))
    cursor = _cursor(steps)
    statement, following, failure = _grouped(cursor)
    assert _spelled(statement) == _joined(*steps)
    assert (following, failure, _remaining(cursor)) == (None, None, [])


def test_a_bind_limit_the_columns_fit_never_splits_a_run() -> None:
    steps = _openings(5)
    width = len(_alone(steps[0]).binds)
    cursor = _cursor(steps, dialect=replace(POSTGRES, max_bind_parameters=width))
    statement, following, failure = _grouped(cursor)
    assert _spelled(statement) == _joined(*steps)
    assert (following, failure, _remaining(cursor)) == (None, None, [])


# --------------------------------------------------------------------------- #
# A later opening's ordinary failure leaves the prefix exactly as appended.    #
# --------------------------------------------------------------------------- #


def _prefix_after(steps: tuple[PlannedStep, ...], cursor: LoweringCursor) -> GroupedInsert:
    opening = _grouped(cursor)
    assert opening.following is None
    assert _spelled(opening.statement) == _joined(*steps[:2])
    assert opening.statement.wire_binds() == _wire(*steps[:2])
    assert (
        opening.statement.typed_bind_spans
        == _grouped(_cursor(steps[:2])).statement.typed_bind_spans
    )
    return opening


def test_a_later_preparation_failure_ends_the_run_with_the_prefix_unchanged() -> None:
    steps = _openings(4)
    failure = ValueError("the third row cannot be prepared")
    preparer = _Preparer(failing={id(steps[2].entries[0]): failure})
    assert _prefix_after(steps, _cursor(steps, preparer)).failure is failure


def test_a_later_entry_storing_other_cells_than_its_shape_promised_ends_the_run() -> None:
    steps = _openings(3)
    preparer = LayoutPayloadPreparer(_META)
    entry = steps[2].entries[0]
    narrower = preparer.row_slots(_POSITION, entry.row.presence & ~1)
    promise_broken = RowPayload(
        slots=narrower, source=entry, values=preparer.row(_POSITION, entry).values[1:]
    )
    broken = replace(steps[2], entries=(replace(steps[2].entries[0], prepared=promise_broken),))
    opening = _prefix_after((*steps[:2], broken), _cursor((*steps[:2], broken)))
    assert isinstance(opening.failure, SqlGenError)
    assert "same cells" in str(opening.failure)


def test_the_first_openings_failure_raises_with_no_statement() -> None:
    steps = _openings(2)
    failure = ValueError("the first row cannot be prepared")
    preparer = _Preparer(failing={id(steps[0].entries[0]): failure})
    cursor = _cursor(steps, preparer)
    with pytest.raises(ValueError) as raised:
        _grouped(cursor)
    assert raised.value is failure
    assert _remaining(cursor) == list(steps[1:])


def test_a_control_flow_exception_preparing_a_later_opening_propagates() -> None:
    steps = _openings(3)
    preparer = _Preparer(failing={id(steps[1].entries[0]): KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        _grouped(_cursor(steps, preparer))


# --------------------------------------------------------------------------- #
# A dry traversal answers what execution runs.                                 #
# --------------------------------------------------------------------------- #


def test_a_dry_traversal_groups_each_run_in_place_and_never_transposes_objects() -> None:
    first, second = _openings(2), (_opening(_row(2, _JAN)), _opening(_row(2, _MAR)))
    steps = (_close(1), *first, _close(2), *second)
    statements = list(stream_physical(steps, LayoutPayloadPreparer(_META), _META, POSTGRES))
    assert [_spelled(statement) for statement in statements] == [
        _joined(steps[0]),
        _joined(*first),
        _joined(steps[3]),
        _joined(*second),
    ]


def test_a_dry_traversal_answers_the_prefix_then_raises_a_later_openings_failure() -> None:
    openings = _openings(3)
    steps = (_close(1), *openings)
    failure = ValueError("the third opening cannot be prepared")
    preparer = _Preparer(failing={id(openings[2].entries[0]): failure})
    answered: list[LoweredStatement] = []
    with pytest.raises(ValueError) as raised:
        answered.extend(stream_physical(steps, preparer, _META, POSTGRES))
    assert raised.value is failure
    assert [_spelled(statement) for statement in answered] == [
        _joined(steps[0]),
        _joined(*steps[1:3]),
    ]


_CORPUS: Final = corpus_records()


def test_a_settled_range_keeps_its_logical_steps_and_groups_only_its_openings() -> None:
    # m-temporal-write-017: one close, then head, middle, and tail successors.
    model = formed(_CORPUS["position"])
    instruction = KeyedWriteInstruction(
        "amendUntil",
        "Position",
        ({"id": 1, "value": Decimal("200.00")},),
        valid_from=_MAR,
        until=_SEP,
    )
    observation = TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": 1,
                "acctNum": "A",
                "value": Decimal("100.00"),
                "txStart": _JAN,
                "txEnd": OPEN,
                "validStart": _JAN,
                "validEnd": OPEN,
            }
        )
    )
    at = instant_at("2024-02-15T00:00:00+00:00")
    settled = lower_instruction_steps(
        instruction, model, POSTGRES, "locking", at, observation=observation
    )
    steps = tuple(step for step, _statement in settled)
    assert [type(step) for step in steps] == [PlannedClose, *[PlannedInsert] * 3]
    raw = lower_instruction(instruction, model, POSTGRES, "locking", at, observation=observation)
    physical = list(stream_physical(steps, LayoutPayloadPreparer(model), model, POSTGRES))
    assert [_spelled(statement) for statement in physical] == [
        _spelled(raw[0]),
        _joined(*steps[1:], meta=model),
    ]
    assert physical[1].wire_binds() == _wire(*steps[1:], meta=model)
    assert [
        _spelled(statement)
        for _step, statement in lowered_steps(steps, LayoutPayloadPreparer(model), model, POSTGRES)
    ] == [_spelled(statement) for statement in raw]


# --------------------------------------------------------------------------- #
# Collections bind one document each, however many elements they hold.        #
# --------------------------------------------------------------------------- #


class Leg(ValueObject):
    stops: Attr[tuple[str, ...]] = attr()


class ColumnsSpan(Bitemporal, table="opn_columns_span", namespace="lowering.openings"):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


class DocumentSpan(
    Bitemporal, table="opn_document_span", namespace="lowering.openings", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


_SPANS: Final = model_of(DomainModel(ColumnsSpan, DocumentSpan))

_COLLECTIONS: Final[tuple[tuple[tuple[str, ...], tuple[Mapping[str, object], ...]], ...]] = (
    ((), ()),
    (("a", "a", "b"), ({"stops": ("x", "x")},)),
    (("n",), ({"stops": ()}, {"stops": ("p", "q", "p")})),
    (tuple(f"t{index}" for index in range(500)), tuple({"stops": ("s",) * 50} for _ in range(40))),
)


def _span_openings(name: str) -> tuple[PlannedInsert, ...]:
    entity = entity_by_name(_SPANS, name)
    assert entity is not None
    identity = entity.identity
    return tuple(
        PlannedInsert(
            entity=identity,
            entries=(
                WriteRow(
                    row=managed_row_of(
                        _SPANS,
                        {
                            _attr("id", identity): 1,
                            _attr("tags", identity): tags,
                            _attr("validStart", identity): dt.datetime(
                                2024, 1 + index, 1, tzinfo=dt.UTC
                            ),
                            _attr("validEnd", identity): dt.datetime(
                                2024, 2 + index, 1, tzinfo=dt.UTC
                            ),
                            _attr("txStart", identity): _AT,
                            _attr("txEnd", identity): OPEN,
                        },
                        {ValueObjectIdentity(identity, ("legs",)): legs},
                    ),
                    origin=NEW_LINEAGE,
                ),
            ),
        )
        for index, (tags, legs) in enumerate(_COLLECTIONS)
    )


@pytest.mark.parametrize("name", ["ColumnsSpan", "DocumentSpan"], ids=["columns", "document"])
def test_a_collection_binds_as_one_document_and_its_elements_widen_no_entry(name: str) -> None:
    steps = _span_openings(name)
    widths = {len(_alone(step, _SPANS).binds) for step in steps}
    assert len(widths) == 1
    (width,) = widths
    cursor = LoweringCursor(
        steps,
        LayoutPayloadPreparer(_SPANS),
        _SPANS,
        replace(POSTGRES, max_bind_parameters=width),
    )
    statement, following, failure = _grouped(cursor)
    assert (following, failure) == (None, None)
    assert _spelled(statement) == _joined(*steps, meta=_SPANS)
    assert statement.wire_binds() == _wire(*steps, meta=_SPANS)
