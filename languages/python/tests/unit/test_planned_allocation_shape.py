"""Materialization constructs no per-row wrapper, whatever the row count.

The design's own accepted regression check (`docs/architecture/parallax-
write-planner-design.md` "Compact Python representation"): a materializing
predicate write used to build a `list[KeyedWrite]` and a parallel `pending`
list of `(ObjectKey, WriteObservation)` pairs, both sized by the resolving
read's own result count — "a million input wrappers" the design names as the
avoidable cost. `_materialize_predicate_write`
(`parallax.snapshot.handle._predicate_writes`) now streams each resolved
row's key and observation values directly into bounded column builders and
constructs no `KeyedWrite` at all while buffering, so a resolving read
matching five rows and one matching eight hundred rows both construct exactly
zero `KeyedWrite` instances during materialization — independent of the
resolved-row count, following `test_storage_layout_facet.py`'s own retained-
size regression precedent.

`KeyedWrite` is a real, transient wrapper `WritePlanner` still constructs —
one at a time, discarded once its step is settled — when a Materialized Write
Group's own row is later lowered; that happens only once `transact` unwinds
and flushes. Snapshotting the construction count from *inside* the verb call
that buffers, before that flush runs, is what isolates materialization's own
share of the count.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest
from _transact_support import RecordingPort, account_db

from _support import mirrored_models as mm
from parallax.core.unit_work import KeyedMutation, KeyedWrite
from parallax.snapshot.handle import Transaction


def _resolved_rows(count: int) -> list[dict[str, object]]:
    return [
        {"id": index, "owner": f"Owner{index}", "balance": Decimal("100.00"), "version": 1}
        for index in range(count)
    ]


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
        valid_from: str | None = None,
        until: str | None = None,
    ) -> None:
        constructed.append(self)
        original_init(self, mutation, entity, rows, valid_from, until)

    monkeypatch.setattr(KeyedWrite, "__init__", counting_init)

    during_materialization: dict[int, int] = {}
    for row_count in (5, 800):
        constructed.clear()
        port = RecordingPort(rows=_resolved_rows(row_count))

        def fn(tx: Transaction, row_count: int = row_count) -> None:
            tx.update_where(
                mm.Account.where(mm.Account.balance < 1_000_000.00),
                mm.Account.balance.set(Decimal("0.00")),
            )
            # `update_where` resolves and buffers synchronously; the flush
            # that later lowers each buffered row happens only once
            # `transact` unwinds at scope exit, so this snapshot — taken
            # before this callback returns — is materialization's own count,
            # untouched by anything the eventual flush constructs.
            during_materialization[row_count] = len(constructed)

        account_db(port).transact(fn, concurrency="optimistic")

    assert during_materialization == {5: 0, 800: 0}
