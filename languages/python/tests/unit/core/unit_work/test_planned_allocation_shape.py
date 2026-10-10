"""Materialization constructs no per-row wrapper, whatever the row count.

The design's own accepted regression check (`docs/architecture/parallax-
write-planner-design.md` "Compact Python representation"): a materializing
predicate write used to build a `list[KeyedWrite]` and a parallel `pending`
list of `(ObjectKey, WriteObservation)` pairs, both sized by the resolving
read's own result count — "a million input wrappers" the design names as the
avoidable cost. The unit of work's selection consumer
(:func:`~parallax.core.unit_work.acquisition.consume_selection`) streams each
selected row's key and observation values directly into bounded column
builders and constructs no `KeyedWrite` at all while buffering, so a selection
of five rows and one of eight hundred rows both construct exactly zero
`KeyedWrite` instances during materialization — independent of the selected-row
count, following `test_storage_layout_facet.py`'s own retained-size regression
precedent.

`KeyedWrite` is a real, transient wrapper `WritePlanner` still constructs —
one at a time, discarded once its step is settled — when a Materialized Write
Group's own row is later lowered; that happens only once the unit of work
flushes. Counting constructions once the write is buffered, with no flush
behind it, is what isolates materialization's own share of the count.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal

import pytest

from parallax.conformance import models
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.execution._planning import build_write_planner
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    PredicateSelection,
    PredicateWrite,
    TransactionSettings,
    UnitOfWork,
    WriteAssignment,
)
from parallax.core.unit_work.instructions import prepare_typed_write
from parallax.core.write_plan import PredecessorRow, WritePlan
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core.unit_work._acquired_rows_support import HeldRows

_ACCOUNT = models.load_models()["account"]


def _selected_rows(count: int) -> list[PredecessorRow]:
    return [
        PredecessorRow(
            members={
                "id": index,
                "owner": f"Owner{index}",
                "balance": Decimal("100.00"),
                "version": 1,
            }
        )
        for index in range(count)
    ]


def _unflushed(
    plan: WritePlan, *, trigger: object, bind_deferred: object, completed: object
) -> None:  # pragma: no cover - nothing flushes
    del plan, trigger, bind_deferred, completed
    raise AssertionError("materialization flushes nothing")


def test_materialization_constructs_no_keyed_write_regardless_of_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[object] = []
    original_init = KeyedWrite.__init__

    def counting_init(
        self: KeyedWrite,
        mutation: KeyedMutation,
        entity: str,
        rows: tuple[Mapping[str, object], ...],
        valid_from: dt.datetime | None = None,
        until: dt.datetime | None = None,
    ) -> None:
        constructed.append(self)
        original_init(self, mutation, entity, rows, valid_from, until)

    prepared = prepare_typed_write(
        PredicateWrite(
            "amend",
            PredicateSelection(
                "Account",
                predicate_algebra.Comparison(
                    "lessThan", predicate_algebra.FieldSubject("Account.balance"), "1000000.00"
                ),
            ),
            (WriteAssignment("Account.balance", Decimal("0.00")),),
        ),
        _ACCOUNT,
    )
    monkeypatch.setattr(KeyedWrite, "__init__", counting_init)

    during_materialization: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        selected = HeldRows(_ACCOUNT, _selected_rows(row_count))
        uow = UnitOfWork(
            settings=TransactionSettings(concurrency="optimistic"),
            clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
            meta=_ACCOUNT,
            flush_executor=_unflushed,
            acquire_rows=selected,
            planner=build_write_planner(_ACCOUNT),
            actor_identity=TEST_ACTOR_IDENTITY,
            evidence_policy_for=opt_lock.view(_ACCOUNT).required_key,
        )
        uow.buffer_predicate(prepared)
        assert len(selected.requests) == 1
        during_materialization[row_count] = len(constructed)

    assert during_materialization == {5: 0, 800: 0}
