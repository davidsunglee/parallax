"""How one object's settlement merges the rows it produces (`m-temporal-write`
*Merging produced successors*): which adjacent produced rows are one row, which
never are, how owned predecessors are realized against the merged rows, and
what each original and insertion contributes to them."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.execution._write_lowering import lowered
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import NO_TRANSFORM, CoverageTransform
from parallax.core.temporal_write.expansion import (
    ExpansionRole,
    PredecessorExpander,
    RowAudit,
    TemporalFacts,
)
from parallax.core.unit_work.strategy import NO_AUDIT, AuditDecoration
from parallax.core.wire._json import loads
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import ObjectKey, PredecessorRow
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.payload import RowPayload
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    DerivedRow,
    OwnedEndpoint,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    ChangedFrom,
    Finite,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
    WriteRow,
    adopt_planned_row,
)
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._ownership_support import OpenedRows

_COLUMNS = model("buffered-sequence-layout-twin-columns")
_DOCUMENT = model("buffered-sequence-layout-twin-document")
_SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_NOW = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 8)
)
_LAYOUTS = pytest.mark.parametrize("meta", [_COLUMNS, _DOCUMENT], ids=["columns", "document"])


def _facts(meta: Metamodel) -> TemporalFacts:
    metadata = meta.entity(_SPAN)
    view = inheritance.view(meta).entity(_SPAN)
    shape = temporal_read.view(meta).shape(_SPAN)
    assert metadata is not None and view is not None
    assert isinstance(shape, temporal_read.Bitemporal)
    return TemporalFacts(entity=metadata, view=view, shape=shape, instant=_NOW)


@dataclass
class _CountingPayloads:
    """The model's real preparer, counting the complete rows it prepares."""

    real: LayoutPayloadPreparer
    rows: list[WriteRow] = field(default_factory=list[WriteRow])

    def assignments(self, entity: EntityIdentity, assignments: PlannedAssignments) -> Any:
        return self.real.assignments(entity, assignments)

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        self.rows.append(write_row)
        return self.real.row(entity, write_row)

    def proven_unequal_non_interval(
        self, entity: EntityIdentity, left: WriteRow, right: WriteRow
    ) -> bool:
        return self.real.proven_unequal_non_interval(entity, left, right)

    def equal_non_interval(self, left: RowPayload, right: RowPayload) -> bool:
        return self.real.equal_non_interval(left, right)

    def rebound(self, payload: RowPayload, write_row: WriteRow) -> RowPayload:
        return self.real.rebound(payload, write_row)


def _expansion(
    meta: Metamodel,
    transform: CoverageTransform,
    *,
    gated: bool = True,
    guards: bool = True,
    derives: bool = False,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    audit: RowAudit | None = None,
    payloads: _CountingPayloads | None = None,
) -> PredecessorExpander:
    facts = _facts(meta)
    return PredecessorExpander(
        facts,
        transform,
        key_attribute=facts.view.primary_key.identity,
        key_value=1,
        gated=gated,
        guards=guards,
        derives=derives,
        ownership=ownership,
        audit=audit or AuditDecoration(NO_AUDIT, TEST_ACTOR_IDENTITY, inert_instant(), ()),
        payloads=payloads or _CountingPayloads(LayoutPayloadPreparer(meta)),
    )


def _span(
    meta: Metamodel,
    start: dt.datetime,
    end: object,
    amount: int,
    label: str = "a",
    *,
    tx_start: dt.datetime = _T0,
    document: str | None = None,
) -> PredecessorRow:
    """Span 1's stored row over ``[start, end)``; under Document layout its
    retained document is ``document`` where given, else the one its members
    spell."""
    members: dict[str, object] = {
        "id": 1,
        "amount": amount,
        "label": label,
        "memo": None,
        "validStart": start,
        "validEnd": end,
        "txStart": tx_start,
        "txEnd": INFINITY,
    }
    if meta is _COLUMNS:
        return PredecessorRow(members=members)
    stored = (
        loads(document)
        if document is not None
        else {"amount": amount, "label": label, "memo": None}
    )
    return PredecessorRow(members=members, document=stored)


def _settle(
    expansion: PredecessorExpander,
    meta: Metamodel,
    *predecessors: PredecessorRow,
    role: ExpansionRole = "coverage",
) -> BoundRange:
    facts = _facts(meta)
    return expansion.settle(
        tuple(
            (
                predecessor,
                role,
                _state(facts, predecessor),
                temporal_read.valid_time_coverage(facts.shape, predecessor, None),
            )
            for predecessor in predecessors
        )
    )


def _state(facts: TemporalFacts, predecessor: PredecessorRow) -> TemporalStateKey:
    return TemporalStateKey(
        ObjectKey(facts.entity.identity, (("id", 1),)),
        temporal_read.milestone_edge(facts.shape, predecessor, None),
    )


def _amending(
    window: TimeInterval, assigned: Mapping[str, object], *, replaces: bool = False
) -> CoverageTransform:
    return NO_TRANSFORM.followed_by(window, assigned, replaces=replaces)


def _windows(steps: Iterable[PlannedWrite]) -> list[tuple[object, object, object, object]]:
    windows: list[tuple[object, object, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append(
                (cells["validStart"], cells["validEnd"], cells["amount"], cells["label"])
            )
    return windows


def _kinds(steps: Iterable[PlannedWrite]) -> list[type[PlannedWrite]]:
    return [type(step) for step in steps]


def _endpoint(end: object) -> OwnedEndpoint:
    ends = OPEN_BITEMPORAL_ENDS if end is INFINITY else (Finite(instant=end), OPEN_END)
    return OwnedEndpoint(_SPAN, (1,), ends)


# --------------------------------------------------------------------------- #
# Which adjacent produced rows are one row.                                    #
# --------------------------------------------------------------------------- #
@_LAYOUTS
def test_equal_changed_parts_of_two_originals_open_as_one_row(meta: Metamodel) -> None:
    first, second = _span(meta, _JAN, _APR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150})), meta, first, second
    )
    # Both originals are closed under their own gates before anything opens.
    closes = [step for step in settled.steps if isinstance(step, PlannedClose)]
    assert [close.concurrency.observed_start for close in closes] == [_T0, _T0]  # type: ignore[union-attr]
    assert _kinds(settled.steps) == [PlannedClose, PlannedClose] + [PlannedInsert] * 3
    assert _windows(settled.steps) == [
        (_JAN, _FEB, 100, "a"),
        (_FEB, _JUN, 150, "a"),
        (_JUN, _JUL, 200, "a"),
    ]
    facts = _facts(meta)
    assert tuple(settled.changed) == (_state(facts, first), _state(facts, second))
    assert tuple(settled.opened.fresh) == (_endpoint(_FEB), _endpoint(_JUN), _endpoint(_JUL))


@_LAYOUTS
def test_parts_differing_in_a_member_the_amendment_does_not_assign_stay_apart(
    meta: Metamodel,
) -> None:
    first, second = _span(meta, _JAN, _APR, 100, "A"), _span(meta, _APR, _JUL, 200, "B")
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150})), meta, first, second
    )
    assert _windows(settled.steps) == [
        (_JAN, _FEB, 100, "A"),
        (_FEB, _APR, 150, "A"),
        (_APR, _JUN, 150, "B"),
        (_JUN, _JUL, 200, "B"),
    ]


@_LAYOUTS
def test_a_uniform_replacement_opens_its_extent_as_one_row(meta: Metamodel) -> None:
    first, second = _span(meta, _JAN, _APR, 100, "A"), _span(meta, _APR, _JUL, 200, "B")
    replacing = _amending(
        TimeInterval(_FEB, _JUN), {"amount": 150, "label": "R", "memo": None}, replaces=True
    )
    settled = _settle(_expansion(meta, replacing), meta, first, second)
    assert _windows(settled.steps) == [
        (_JAN, _FEB, 100, "A"),
        (_FEB, _JUN, 150, "R"),
        (_JUN, _JUL, 200, "B"),
    ]


def test_unknown_content_outside_the_replaced_members_keeps_the_parts_apart() -> None:
    meta = _DOCUMENT
    first = _span(meta, _JAN, _APR, 100, document='{"amount": 100, "label": "a", "ledger": 1}')
    second = _span(meta, _APR, _JUL, 200, document='{"amount": 200, "label": "a", "ledger": 2}')
    payloads = _CountingPayloads(LayoutPayloadPreparer(meta))
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), payloads=payloads),
        meta,
        first,
        second,
    )
    assert _windows(settled.steps) == [
        (_JAN, _FEB, 100, "a"),
        (_FEB, _APR, 150, "a"),
        (_APR, _JUN, 150, "a"),
        (_JUN, _JUL, 200, "a"),
    ]
    # Equal direct cells left only the documents to tell the changed parts
    # apart: both were prepared whole, and what lowering stores is those cells.
    (head, left, right, tail) = (step for step in settled.steps if isinstance(step, PlannedInsert))
    assert (head.entries[0].prepared, tail.entries[0].prepared) == (None, None)
    assert left.entries[0].prepared is not None and right.entries[0].prepared is not None
    assert [row.row.attributes for row in payloads.rows] == [
        left.entries[0].row.attributes,
        right.entries[0].row.attributes,
    ]


@pytest.mark.parametrize(
    ("left", "right", "merged"),
    [
        ('{"x": true}', '{"x": 1}', False),
        ('{"x": 1}', '{"x": 1.0}', True),
        ('{"x": 0.1}', '{"x": 0.10000000000000001}', False),
        ("{}", '{"x": null}', False),
        ('{"x": [1, 2]}', '{"x": [2, 1]}', False),
        ('{"x": {"a": 1, "b": 2}}', '{"x": {"b": 2, "a": 1}}', True),
    ],
    ids=["kind", "numeric-meaning", "exact-number", "presence", "array-order", "member-order"],
)
def test_stored_document_content_decides_whether_parts_merge(
    left: str, right: str, merged: bool
) -> None:
    meta = _DOCUMENT
    first = _span(meta, _JAN, _APR, 100, document=f'{{"amount": 100, "label": "a", "u": {left}}}')
    second = _span(meta, _APR, _JUL, 200, document=f'{{"amount": 200, "label": "a", "u": {right}}}')
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150})), meta, first, second
    )
    changed = [window for window in _windows(settled.steps) if window[2] == 150]
    assert changed == (
        [(_FEB, _JUN, 150, "a")] if merged else [(_FEB, _APR, 150, "a"), (_APR, _JUN, 150, "a")]
    )


@_LAYOUTS
def test_a_cheap_difference_on_one_side_leaves_the_other_side_to_merge(meta: Metamodel) -> None:
    payloads = _CountingPayloads(LayoutPayloadPreparer(meta))
    first, second = _span(meta, _JAN, _APR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(
            meta, _amending(TimeInterval(_FEB, INFINITY), {"amount": 150}), payloads=payloads
        ),
        meta,
        first,
        second,
    )
    assert _windows(settled.steps) == [(_JAN, _FEB, 100, "a"), (_FEB, _JUL, 150, "a")]
    # The head differs from its neighbour in a direct cell and is never
    # prepared; the two changed parts are prepared once each to be compared,
    # and the merged row stores those prepared cells.
    head, merged = (step for step in settled.steps if isinstance(step, PlannedInsert))
    assert head.entries[0].prepared is None
    assert len(payloads.rows) == 2
    prepared = merged.entries[0].prepared
    assert prepared is not None and prepared.prepared_from(merged.entries[0])


@_LAYOUTS
def test_nothing_merges_across_a_gap_an_amendment_leaves(meta: Metamodel) -> None:
    first, second = _span(meta, _JAN, _MAR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150})), meta, first, second
    )
    assert _windows(settled.steps) == [
        (_JAN, _FEB, 100, "a"),
        (_FEB, _MAR, 150, "a"),
        (_APR, _JUN, 150, "a"),
        (_JUN, _JUL, 200, "a"),
    ]


@_LAYOUTS
def test_a_kept_neighbour_is_no_part_of_a_merge(meta: Metamodel) -> None:
    # [January, March) already holds 150, so it keeps its milestone under a
    # guard; the changed [March, June) beside it holds the same state, but a
    # kept milestone is not a row this write produced.
    kept, changed = _span(meta, _JAN, _MAR, 150), _span(meta, _MAR, _JUN, 100)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_JAN, _JUN), {"amount": 150})), meta, kept, changed
    )
    assert _kinds(settled.steps) == [PlannedTemporalGuard, PlannedClose, PlannedInsert]
    assert _windows(settled.steps) == [(_MAR, _JUN, 150, "a")]


@dataclass
class _StampingAudit:
    """An audit stamping each produced row's label with what ``stamp`` answers
    for its Valid-Time start."""

    label: AttributeIdentity
    start: AttributeIdentity
    stamp: Callable[[dt.datetime], str]
    rows: int = 0

    @property
    def neutral(self) -> bool:
        return False

    def finalize_row(self, write_row: WriteRow, /) -> WriteRow:
        self.rows += 1
        row = write_row.row
        start = row.attributes[self.start]
        assert isinstance(start, dt.datetime)  # every produced Bitemporal row has a start
        value = self.stamp(start)
        return WriteRow(
            row=adopt_planned_row({**row.attributes, self.label: value}, row.value_objects),
            origin=write_row.origin,
            executed=(*write_row.executed, self.label)
            if self.label not in write_row.executed
            else write_row.executed,
        )

    def decorate_close(self, close: PlannedClose, /) -> PlannedClose:
        return close


def _identity(meta: Metamodel, name: str) -> AttributeIdentity:
    facts = _facts(meta)
    return next(
        attribute.identity
        for attribute in facts.view.member_selection.attributes
        if attribute.identity.name == name
    )


def _constant(start: dt.datetime) -> str:
    del start
    return "audited"


def _by_month(start: dt.datetime) -> str:
    return f"at-{start.month}"


@_LAYOUTS
@pytest.mark.parametrize("equal", [True, False], ids=["equal-audits", "unequal-audits"])
def test_final_audit_values_take_part_in_the_comparison(meta: Metamodel, equal: bool) -> None:
    audit = _StampingAudit(
        _identity(meta, "label"),
        _identity(meta, "validStart"),
        _constant if equal else _by_month,
    )
    first, second = _span(meta, _JAN, _APR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), audit=audit),
        meta,
        first,
        second,
    )
    # Every produced row is finalized once, whether or not it then merges.
    assert audit.rows == 4
    changed = [window[:2] for window in _windows(settled.steps) if window[2] == 150]
    assert changed == ([(_FEB, _JUN)] if equal else [(_FEB, _APR), (_APR, _JUN)])


@dataclass
class _TransactionTimeAudit:
    """A raw row audit that moves one produced row's Transaction-Time start,
    which only a broken audit could do: settlement must not merge across it."""

    start: AttributeIdentity
    valid_start: AttributeIdentity
    moved: dt.datetime

    @property
    def neutral(self) -> bool:
        return False

    def finalize_row(self, write_row: WriteRow, /) -> WriteRow:
        row = write_row.row
        if row.attributes[self.valid_start] != _APR:
            return write_row
        return replace(
            write_row,
            row=adopt_planned_row({**row.attributes, self.start: self.moved}, row.value_objects),
        )

    def decorate_close(self, close: PlannedClose, /) -> PlannedClose:
        return close


@_LAYOUTS
def test_unequal_transaction_time_bounds_never_merge(meta: Metamodel) -> None:
    audit = _TransactionTimeAudit(_identity(meta, "txStart"), _identity(meta, "validStart"), _T1)
    first, second = _span(meta, _JAN, _APR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), audit=audit),
        meta,
        first,
        second,
    )
    changed = [window[:2] for window in _windows(settled.steps) if window[2] == 150]
    assert changed == [(_FEB, _APR), (_APR, _JUN)]


# --------------------------------------------------------------------------- #
# Realizing merged rows against the rows the attempt opened.                   #
# --------------------------------------------------------------------------- #
@_LAYOUTS
def test_the_owned_row_ending_a_merged_run_is_revised_into_it_and_the_other_removed(
    meta: Metamodel,
) -> None:
    owned = OpenedRows(frozenset({_endpoint(_APR), _endpoint(_JUN)}))
    first = _span(meta, _FEB, _APR, 100, tx_start=_NOW)
    second = _span(meta, _APR, _JUN, 200, tx_start=_NOW)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), ownership=owned),
        meta,
        first,
        second,
    )
    removal, revision = settled.steps
    assert isinstance(removal, PlannedTemporalRemoval)
    assert removal.target.end_values == (Finite(instant=_APR), OPEN_END)
    assert isinstance(revision, PlannedTemporalRevision)
    assert revision.target.end_values == (Finite(instant=_JUN), OPEN_END)
    # The revision is the right edge's own program — its executed amount —
    # with its Valid-Time start moved to the merged row's.
    assigned = {identity.name: value for identity, value in revision.assignments.attributes.items()}
    assert assigned == {"amount": 150, "validStart": _FEB}
    facts = _facts(meta)
    assert tuple(settled.changed) == (_state(facts, first), _state(facts, second))
    assert tuple(settled.removed) == (_endpoint(_APR),)
    # The revised row is named again under its own address with its new extent.
    assert tuple(settled.opened.fresh) == (_endpoint(_JUN),)


@_LAYOUTS
def test_an_owned_row_merged_with_a_later_stored_rows_part_is_removed_and_the_run_opened(
    meta: Metamodel,
) -> None:
    owned = OpenedRows(frozenset({_endpoint(_APR)}))
    first = _span(meta, _FEB, _APR, 100, tx_start=_NOW)
    second = _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), ownership=owned),
        meta,
        first,
        second,
    )
    assert _kinds(settled.steps) == [
        PlannedTemporalRemoval,
        PlannedClose,
        PlannedInsert,
        PlannedInsert,
    ]
    assert _windows(settled.steps) == [(_FEB, _JUN, 150, "a"), (_JUN, _JUL, 200, "a")]
    (merged, _tail) = (step for step in settled.steps if isinstance(step, PlannedInsert))
    assert isinstance(merged.entries[0].origin, ChangedFrom)
    assert tuple(settled.removed) == (_endpoint(_APR),)
    assert tuple(settled.opened.fresh) == (_endpoint(_JUN), _endpoint(_JUL))


# --------------------------------------------------------------------------- #
# Contributions: what each original and insertion contributed.                 #
# --------------------------------------------------------------------------- #
@_LAYOUTS
def test_each_original_derives_only_its_own_part_of_a_merged_row(meta: Metamodel) -> None:
    first, second = _span(meta, _JAN, _APR, 100), _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), derives=True),
        meta,
        first,
        second,
    )
    merged = TimeInterval(_FEB, _JUN)
    one, two = settled.derived
    assert one.rows == (
        DerivedRow(_endpoint(_FEB), TimeInterval(_JAN, _FEB), TimeInterval(_JAN, _FEB)),
        DerivedRow(_endpoint(_JUN), merged, TimeInterval(_FEB, _APR)),
    )
    assert two.rows == (
        DerivedRow(_endpoint(_JUN), merged, TimeInterval(_APR, _JUN)),
        DerivedRow(_endpoint(_JUL), TimeInterval(_JUN, _JUL), TimeInterval(_JUN, _JUL)),
    )


@_LAYOUTS
def test_a_pending_insertion_continues_only_into_its_own_part_of_a_merged_row(
    meta: Metamodel,
) -> None:
    facts = _facts(meta)
    key = facts.view.primary_key.identity
    attributes: dict[AttributeIdentity, object] = {
        key: 1,
        _identity(meta, "amount"): 100,
        _identity(meta, "label"): "a",
    }
    seed: tuple[dict[AttributeIdentity, object], dict[ValueObjectIdentity, object]] = (
        attributes,
        {},
    )
    replacing = _amending(
        TimeInterval(_JAN, _JUN), {"amount": 300, "label": "r", "memo": None}, replaces=True
    )
    stored = _span(meta, _MAY, _JUL, 200, "b")
    expansion = _expansion(meta, replacing)
    gaps = replacing.gaps(iter((TimeInterval(_JAN, _APR), TimeInterval(_MAY, _JUL))))
    settled = expansion.settle(
        (
            (
                stored,
                "coverage",
                _state(facts, stored),
                TimeInterval(_MAY, _JUL),
            ),
        ),
        lineage=(seed, TimeInterval(_JAN, _APR)),
        gaps=gaps,
    )
    # The opening's part, the gap after it, and the stored row's replaced part
    # are one row, which continues the insertion over its own part alone.
    assert _windows(settled.steps) == [(_JAN, _JUN, 300, "r"), (_JUN, _JUL, 200, "b")]
    assert tuple(settled.opened.continued) == ()
    assert tuple(settled.opened.shared) == ((_endpoint(_JUN), (TimeInterval(_JAN, _APR),)),)
    assert tuple(settled.opened.fresh) == (_endpoint(_JUL),)


@_LAYOUTS
def test_a_merged_row_an_insertion_contributed_part_of_is_shared_over_that_part(
    meta: Metamodel,
) -> None:
    facts = _facts(meta)
    replacing = _amending(
        TimeInterval(_JAN, _JUN), {"amount": 300, "label": "r", "memo": None}, replaces=True
    )
    # The insertion's own row, flushed and tagged, and a later stored row.
    inserted = _span(meta, _JAN, _APR, 100, tx_start=_NOW)
    stored = _span(meta, _MAY, _JUL, 200, "b")
    owned = OpenedRows(frozenset({_endpoint(_APR)}), inserted=frozenset({_endpoint(_APR)}))
    expansion = _expansion(meta, replacing, ownership=owned)
    settled = expansion.settle(
        (
            (inserted, "coverage", _state(facts, inserted), TimeInterval(_JAN, _APR)),
            (stored, "coverage", _state(facts, stored), TimeInterval(_MAY, _JUL)),
        ),
        gaps=replacing.gaps(iter((TimeInterval(_JAN, _APR), TimeInterval(_MAY, _JUL)))),
    )
    assert _kinds(settled.steps) == [
        PlannedTemporalRemoval,
        PlannedClose,
        PlannedInsert,
        PlannedInsert,
    ]
    assert _windows(settled.steps) == [(_JAN, _JUN, 300, "r"), (_JUN, _JUL, 200, "b")]
    assert tuple(settled.opened.continued) == ()
    assert tuple(settled.opened.shared) == ((_endpoint(_JUN), (TimeInterval(_JAN, _APR),)),)
    assert tuple(settled.opened.fresh) == (_endpoint(_JUL),)


# --------------------------------------------------------------------------- #
# What lowering stores agrees with what the unit publishes.                     #
# --------------------------------------------------------------------------- #
@_LAYOUTS
def test_the_merged_rows_statements_store_the_addresses_its_effects_name(
    meta: Metamodel,
) -> None:
    owned = OpenedRows(frozenset({_endpoint(_APR)}))
    payloads = _CountingPayloads(LayoutPayloadPreparer(meta))
    first = _span(meta, _FEB, _APR, 100, tx_start=_NOW)
    second = _span(meta, _APR, _JUL, 200)
    settled = _settle(
        _expansion(
            meta,
            _amending(TimeInterval(_FEB, _JUN), {"amount": 150}),
            ownership=owned,
            payloads=payloads,
        ),
        meta,
        first,
        second,
    )
    prepared = len(payloads.rows)
    statements = [lowered(step, payloads, meta, POSTGRES) for step in settled.steps]
    removal, close, merged, tail = statements
    # The removal and the close address the rows the unit removes and closes.
    assert removal.sql.startswith("delete from")
    assert _APR in removal.binds
    assert close.sql.startswith("update") and _JUL in close.binds
    # The merged row's insert stores the merged extent, under the address the
    # unit registers, from the cells its comparison already prepared.
    assert _FEB in merged.binds and _JUN in merged.binds
    assert tuple(settled.opened.fresh) == (_endpoint(_JUN), _endpoint(_JUL))
    assert tuple(settled.removed) == (_endpoint(_APR),)
    assert len(payloads.rows) == prepared + 1  # only the tail, prepared now
    assert _JUL in tail.binds


@dataclass(frozen=True)
class _PartlyInserted(OpenedRows):
    """An attempt whose admitted insertion contributed only ``parts`` of the
    rows it tags."""

    parts: tuple[TimeInterval, ...] = ()

    def insertion_coverage(
        self, endpoint: OwnedEndpoint, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        return self.parts if endpoint in self.inserted else ()


@_LAYOUTS
def test_a_row_revised_in_place_takes_the_parts_of_an_insertion_its_new_extent_keeps(
    meta: Metamodel,
) -> None:
    # The owned row [January, June) holds an insertion's [January, April); an
    # amendment from February revises it into [February, June), which keeps
    # [February, April) of it, while its new head keeps [January, February).
    owned = _endpoint(_JUN)
    ownership = _PartlyInserted(
        frozenset({owned}), frozenset({owned}), parts=(TimeInterval(_JAN, _APR),)
    )
    row = _span(meta, _JAN, _JUN, 100, tx_start=_NOW)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_FEB, _JUN), {"amount": 150}), ownership=ownership),
        meta,
        row,
    )
    assert _kinds(settled.steps) == [PlannedTemporalRevision, PlannedInsert]
    assert tuple(settled.opened.continued) == (_endpoint(_FEB),)
    assert tuple(settled.opened.shared) == ((owned, (TimeInterval(_FEB, _APR),)),)
    assert tuple(settled.opened.fresh) == ()


@_LAYOUTS
def test_a_row_revised_whole_keeps_the_parts_of_an_insertion_it_holds(meta: Metamodel) -> None:
    owned = _endpoint(_JUN)
    ownership = _PartlyInserted(
        frozenset({owned}), frozenset({owned}), parts=(TimeInterval(_JAN, _APR),)
    )
    row = _span(meta, _JAN, _JUN, 100, tx_start=_NOW)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_JAN, _JUN), {"amount": 150}), ownership=ownership),
        meta,
        row,
    )
    assert _kinds(settled.steps) == [PlannedTemporalRevision]
    assert tuple(settled.opened.shared) == ((owned, (TimeInterval(_JAN, _APR),)),)
    assert tuple(settled.opened.continued) == tuple(settled.opened.fresh) == ()


@_LAYOUTS
def test_rows_revised_apart_each_keep_their_own_parts_of_an_insertion(meta: Metamodel) -> None:
    first, second = _endpoint(_APR), _endpoint(_JUL)
    ownership = _PartlyInserted(
        frozenset({first, second}),
        frozenset({first, second}),
        parts=(TimeInterval(_JAN, _FEB), TimeInterval(_MAY, _JUN)),
    )
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_JAN, _JUL), {"amount": 150}), ownership=ownership),
        meta,
        _span(meta, _JAN, _APR, 100, "a", tx_start=_NOW),
        _span(meta, _APR, _JUL, 200, "b", tx_start=_NOW),
    )
    assert _kinds(settled.steps) == [PlannedTemporalRevision, PlannedTemporalRevision]
    assert tuple(settled.opened.shared) == (
        (first, (TimeInterval(_JAN, _FEB),)),
        (second, (TimeInterval(_MAY, _JUN),)),
    )


@_LAYOUTS
def test_an_original_derives_its_own_part_of_a_row_merged_with_an_insertions(
    meta: Metamodel,
) -> None:
    facts = _facts(meta)
    seed: tuple[dict[AttributeIdentity, object], dict[ValueObjectIdentity, object]] = (
        {facts.view.primary_key.identity: 1, _identity(meta, "amount"): 100},
        {},
    )
    replacing = _amending(
        TimeInterval(_JAN, _JUN), {"amount": 300, "label": "r", "memo": None}, replaces=True
    )
    stored = _span(meta, _APR, _JUL, 200, "b")
    settled = _expansion(meta, replacing, derives=True).settle(
        ((stored, "coverage", _state(facts, stored), TimeInterval(_APR, _JUL)),),
        lineage=(seed, TimeInterval(_JAN, _APR)),
    )
    (derivation,) = settled.derived
    assert derivation.rows == (
        DerivedRow(_endpoint(_JUN), TimeInterval(_JAN, _JUN), TimeInterval(_APR, _JUN)),
        DerivedRow(_endpoint(_JUL), TimeInterval(_JUN, _JUL), TimeInterval(_JUN, _JUL)),
    )


@_LAYOUTS
def test_a_guarded_unchanged_original_derives_nothing(meta: Metamodel) -> None:
    kept, changed = _span(meta, _JAN, _MAR, 150), _span(meta, _MAR, _JUN, 100)
    settled = _settle(
        _expansion(meta, _amending(TimeInterval(_JAN, _JUN), {"amount": 150}), derives=True),
        meta,
        kept,
        changed,
    )
    (derivation,) = settled.derived
    assert derivation.original == _state(_facts(meta), changed)
