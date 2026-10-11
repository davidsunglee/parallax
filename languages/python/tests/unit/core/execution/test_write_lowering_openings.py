"""Grouped temporal openings through execution's shared physical lowering
(`m-sql` *Requested ranges*, `m-execution` *Flush execution*).

A run of contiguous single-entry openings of one temporal Entity that name the
same members and hold no generated value compiles, one entry at a time, into
one multi-row insert carrying exactly the binds and bind metadata the openings'
own statements carry, in order. The run ends untouched at a step that cannot
join it, and at its capacity before another step is even taken; a later
opening's ordinary failure leaves the statement holding exactly the openings
before it. A dry traversal of settled steps answers the statements execution
runs, through the same cursor operations.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance.class_models import MODELS
from parallax.core import Attr, Bitemporal, Document, DomainModel, ValueObject, attr
from parallax.core.base import INFINITY as OPEN
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._model import model_of
from parallax.core.execution._write_lowering import (
    LoweredOpening,
    LoweringCursor,
    lowered,
    stream_physical,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._context import (
    _RepeatedTypedBindSpan,  # pyright: ignore[reportPrivateUsage]
)
from parallax.core.unit_work import KeyedWrite
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import PredecessorRow, TemporalObservation
from parallax.core.write_plan.payload import RowPayload
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
    PlannedRow,
    RowOrigin,
    WriteRow,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep
from tests._support.clock_probes import instant_at
from tests._support.lowering_probes import lower_instruction, lower_instruction_steps, lowered_steps
from tests.unit._corpus_model_support import corpus_records, formed

_OPENINGS: Final = "parallax.core.execution._write_lowering._OPENING_ENTRY_CAP"
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
) -> PlannedRow:
    return PlannedRow(
        attributes={
            _attr("id"): key,
            _attr("acctNum"): account,
            _attr("value"): value,
            _attr("validStart"): start,
            _attr("validEnd"): end,
            _attr("txStart"): _AT,
            _attr("txEnd"): OPEN,
        }
    )


def _opening(row: PlannedRow, origin: RowOrigin = NEW_LINEAGE) -> PlannedInsert:
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

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        failure = self.failing.get(id(write_row))
        if failure is not None:
            raise failure
        self.prepared.append(write_row)
        return super().row(entity, write_row)


@dataclass
class _Taken:
    """``steps`` handed out one at a time, counting how many were taken and
    raising ``failure`` instead of handing out the step at ``failing``."""

    steps: tuple[PlannedStep, ...]
    failing: int | None = None
    failure: BaseException | None = None
    taken: int = 0

    def __iter__(self) -> Iterator[PlannedStep]:
        for index, step in enumerate(self.steps):
            self.taken += 1
            if index == self.failing and self.failure is not None:
                raise self.failure
            yield step


def _cursor(
    taken: _Taken, preparer: LayoutPayloadPreparer | None = None, dialect: Dialect = POSTGRES
) -> LoweringCursor:
    return LoweringCursor(
        taken, LayoutPayloadPreparer(_META) if preparer is None else preparer, _META, dialect
    )


def _grouped(cursor: LoweringCursor) -> LoweredOpening:
    first = cursor.opening(_first(cursor))
    assert first is not None
    return cursor.lowered_opening(first)


def _first(cursor: LoweringCursor) -> PlannedStep:
    step = cursor.take()
    assert step is not None
    return step


def _alone(step: PlannedStep, meta: Metamodel = _META) -> LoweredStatement:
    return lowered(step, LayoutPayloadPreparer(meta), meta, POSTGRES)


def _joined(*steps: PlannedStep, meta: Metamodel = _META) -> tuple[str, tuple[object, ...]]:
    """The multi-row statement ``steps``' own statements spell together: the
    first's column list, one value tuple per step, and every step's binds in
    order."""
    statements = [_alone(step, meta) for step in steps]
    head, values = statements[0].sql.split(" values ")
    for statement in statements:
        assert statement.sql == statements[0].sql
    return (
        f"{head} values {', '.join([values] * len(steps))}",
        tuple(bind for statement in statements for bind in statement.binds),
    )


def _wire(*steps: PlannedStep, meta: Metamodel = _META) -> tuple[object, ...]:
    return tuple(bind for step in steps for bind in _alone(step, meta).wire_binds())


# --------------------------------------------------------------------------- #
# Which steps begin a grouped opening.                                         #
# --------------------------------------------------------------------------- #


def test_a_temporal_single_entry_insert_without_generated_values_begins_a_grouped_opening() -> None:
    (opening,) = _openings(1)
    assert _cursor(_Taken(())).opening(opening) is opening


def test_every_other_step_lowers_alone() -> None:
    account_meta = model_of(MODELS["account"])
    account = entity_by_name(account_meta, "Account")
    assert account is not None
    non_temporal = PlannedInsert(
        entity=account.identity,
        entries=(
            WriteRow(
                row=PlannedRow(
                    attributes={
                        _attr("id", account.identity): 1,
                        _attr("owner", account.identity): "Ada",
                        _attr("balance", account.identity): Decimal(5),
                    }
                ),
                origin=NEW_LINEAGE,
            ),
        ),
    )
    (opening,) = _openings(1)
    generated = _opening(
        PlannedRow(attributes={**opening.entries[0].row.attributes, _attr("id"): MAX_PLUS_ONE})
    )
    logical = PlannedInsert(entity=_POSITION, entries=(*opening.entries, *_openings(2)[1].entries))
    account_cursor = LoweringCursor((), LayoutPayloadPreparer(account_meta), account_meta, POSTGRES)
    assert account_cursor.opening(non_temporal) is None
    cursor = _cursor(_Taken(()))
    for step in (generated, logical, _close(1)):
        assert cursor.opening(step) is None


# --------------------------------------------------------------------------- #
# One statement for a compatible run.                                          #
# --------------------------------------------------------------------------- #


def test_a_run_of_openings_is_one_statement_of_every_entry_in_order() -> None:
    steps = _openings(4)
    preparer = _Preparer()
    taken = _Taken(steps)
    statement, following, failure = _grouped(_cursor(taken, preparer))
    assert (statement.sql, statement.binds) == _joined(*steps)
    assert statement.wire_binds() == _wire(*steps)
    assert statement.is_compiler_proven
    assert (following, failure, taken.taken) == (None, None, 4)
    assert preparer.prepared == [step.entries[0] for step in steps]


def test_entries_of_one_signature_share_repeated_bind_metadata() -> None:
    statement, _following, _failure = _grouped(_cursor(_Taken(_openings(3))))
    spans = statement.typed_bind_spans
    assert spans
    assert all(isinstance(span, _RepeatedTypedBindSpan) and span.repetitions == 3 for span in spans)


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
    statement, _following, _failure = _grouped(_cursor(_Taken(steps), preparer))
    assert preparer.prepared == []
    assert (statement.sql, statement.binds) == _joined(*plain)


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
        "other-members": _opening(PlannedRow(attributes=other_members)),
        "generated": _opening(PlannedRow(attributes={**attributes, _attr("id"): MAX_PLUS_ONE})),
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
    taken = _Taken(steps)
    statement, following, failure = _grouped(_cursor(taken, preparer))
    assert following is boundary
    assert failure is None
    assert (statement.sql, statement.binds) == _joined(*steps[:2])
    assert taken.taken == len(run) + 1
    assert preparer.prepared == [step.entries[0] for step in run]


def test_another_objects_opening_of_the_same_shape_joins_the_run() -> None:
    steps = (*_openings(1), _opening(_row(2, _JUN)))
    statement, following, _failure = _grouped(_cursor(_Taken(steps)))
    assert following is None
    assert (statement.sql, statement.binds) == _joined(*steps)


def test_the_entry_cap_ends_a_run_before_another_step_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_OPENINGS, 2)
    steps = _openings(5)
    taken = _Taken(steps)
    cursor = _cursor(taken)
    first = _grouped(cursor)
    assert (first.statement.sql, first.statement.binds) == _joined(*steps[:2])
    assert (first.following, first.failure, taken.taken) == (None, None, 2)
    second = _grouped(cursor)
    assert (second.statement.sql, second.statement.binds) == _joined(*steps[2:4])
    third = _grouped(cursor)
    assert (third.statement.sql, third.statement.binds) == _joined(steps[4])
    assert taken.taken == 5


def test_the_dialects_bind_limit_bounds_every_statement_of_a_run() -> None:
    steps = _openings(5)
    width = len(_alone(steps[0]).binds)
    cursor = _cursor(_Taken(steps), dialect=replace(POSTGRES, max_bind_parameters=2 * width + 1))
    assert [
        (opening.statement.sql, opening.statement.binds)
        for opening in (_grouped(cursor), _grouped(cursor), _grouped(cursor))
    ] == [_joined(*steps[:2]), _joined(*steps[2:4]), _joined(steps[4])]


def test_an_opening_wider_than_the_bind_limit_alone_still_inserts_alone() -> None:
    steps = _openings(2)
    width = len(_alone(steps[0]).binds)
    taken = _Taken(steps)
    statement, following, failure = _grouped(
        _cursor(taken, dialect=replace(POSTGRES, max_bind_parameters=width - 1))
    )
    assert (statement.sql, statement.binds) == _joined(steps[0])
    assert (following, failure, taken.taken) == (None, None, 1)


# --------------------------------------------------------------------------- #
# A later opening's ordinary failure leaves the prefix exactly as appended.    #
# --------------------------------------------------------------------------- #


def _prefix_after(steps: tuple[PlannedStep, ...], cursor: LoweringCursor) -> LoweredOpening:
    opening = _grouped(cursor)
    assert opening.following is None
    assert (opening.statement.sql, opening.statement.binds) == _joined(*steps[:2])
    assert opening.statement.wire_binds() == _wire(*steps[:2])
    assert (
        opening.statement.typed_bind_spans
        == _grouped(_cursor(_Taken(steps[:2]))).statement.typed_bind_spans
    )
    return opening


def test_a_later_preparation_failure_ends_the_run_with_the_prefix_unchanged() -> None:
    steps = _openings(4)
    failure = ValueError("the third row cannot be prepared")
    preparer = _Preparer(failing={id(steps[2].entries[0]): failure})
    assert _prefix_after(steps, _cursor(_Taken(steps), preparer)).failure is failure


def test_a_later_typed_cell_refusal_ends_the_run_with_the_prefix_unchanged() -> None:
    steps = _openings(2)
    wrong = _opening(_row(1, _MAR, _JUN, value="not a decimal"))
    opening = _prefix_after((*steps, wrong), _cursor(_Taken((*steps, wrong, *_openings(1)))))
    assert isinstance(opening.failure, SqlGenError)


def test_a_later_entry_storing_other_cells_than_its_shape_promised_ends_the_run() -> None:
    steps = _openings(3)
    narrowed = LayoutPayloadPreparer(_META).row(_POSITION, steps[2].entries[0])
    promise_broken = RowPayload(
        entity=_POSITION,
        source=steps[2].entries[0],
        contributors=narrowed.contributors[1:],
        values=narrowed.values[1:],
    )
    broken = replace(steps[2], entries=(replace(steps[2].entries[0], prepared=promise_broken),))
    opening = _prefix_after((*steps[:2], broken), _cursor(_Taken((*steps[:2], broken))))
    assert isinstance(opening.failure, SqlGenError)
    assert "same cells" in str(opening.failure)


def test_a_later_step_failing_to_be_taken_ends_the_run_with_the_prefix_unchanged() -> None:
    steps = _openings(4)
    failure = RuntimeError("the third step cannot be rebuilt")
    opening = _prefix_after(steps, _cursor(_Taken(steps, failing=2, failure=failure)))
    assert opening.failure is failure


def test_the_first_openings_failure_raises_with_no_statement() -> None:
    steps = _openings(2)
    failure = ValueError("the first row cannot be prepared")
    preparer = _Preparer(failing={id(steps[0].entries[0]): failure})
    taken = _Taken(steps)
    with pytest.raises(ValueError) as raised:
        _grouped(_cursor(taken, preparer))
    assert raised.value is failure
    assert taken.taken == 1


def test_a_control_flow_exception_preparing_a_later_opening_propagates() -> None:
    steps = _openings(3)
    preparer = _Preparer(failing={id(steps[1].entries[0]): KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        _grouped(_cursor(_Taken(steps), preparer))


# --------------------------------------------------------------------------- #
# A dry traversal answers what execution runs.                                 #
# --------------------------------------------------------------------------- #


def test_a_dry_traversal_groups_each_run_in_place_and_never_transposes_objects() -> None:
    first, second = _openings(2), (_opening(_row(2, _JAN)), _opening(_row(2, _MAR)))
    steps = (_close(1), *first, _close(2), *second)
    statements = list(stream_physical(steps, LayoutPayloadPreparer(_META), _META, POSTGRES))
    assert [(statement.sql, statement.binds) for statement in statements] == [
        (_alone(steps[0]).sql, _alone(steps[0]).binds),
        _joined(*first),
        (_alone(steps[3]).sql, _alone(steps[3]).binds),
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
    assert [(statement.sql, statement.binds) for statement in answered] == [
        (_alone(steps[0]).sql, _alone(steps[0]).binds),
        _joined(*steps[1:3]),
    ]


_CORPUS: Final = corpus_records()


def test_a_settled_range_keeps_its_logical_steps_and_groups_only_its_openings() -> None:
    # m-temporal-write-017: one close, then head, middle, and tail successors.
    model = formed(_CORPUS["position"])
    instruction = KeyedWrite(
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
    assert [(statement.sql, statement.binds) for statement in physical] == [
        (raw[0].sql, raw[0].binds),
        _joined(*steps[1:], meta=model),
    ]
    assert physical[1].wire_binds() == tuple(
        bind for statement in raw[1:] for bind in statement.wire_binds()
    )
    assert [
        (statement.sql, statement.binds)
        for _step, statement in lowered_steps(steps, LayoutPayloadPreparer(model), model, POSTGRES)
    ] == [(statement.sql, statement.binds) for statement in raw]


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
                    row=PlannedRow(
                        attributes={
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
                        value_objects={ValueObjectIdentity(identity, ("legs",)): legs},
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
    taken = _Taken(steps)
    cursor = LoweringCursor(
        taken,
        LayoutPayloadPreparer(_SPANS),
        _SPANS,
        replace(POSTGRES, max_bind_parameters=2 * width),
    )
    runs = [_grouped(cursor), _grouped(cursor)]
    assert [(run.statement.sql, run.statement.binds) for run in runs] == [
        _joined(*steps[:2], meta=_SPANS),
        _joined(*steps[2:], meta=_SPANS),
    ]
    assert [run.statement.wire_binds() for run in runs] == [
        _wire(*steps[:2], meta=_SPANS),
        _wire(*steps[2:], meta=_SPANS),
    ]
