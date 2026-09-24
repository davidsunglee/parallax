from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.conformance.read_models import Balance
from parallax.conformance.vo_models import Branch
from parallax.core import LATEST, Edge
from parallax.core.unit_work import Concurrency
from parallax.snapshot import edge_of
from parallax.snapshot.handle import ScopedDatabase, Transaction

__all__ = [
    "StaleMilestoneError",
    "render_balance_milestone",
    "render_branch_milestone",
    "submit_balance_edit",
    "submit_branch_edit",
]


class StaleMilestoneError(RuntimeError):
    """The displayed milestone was superseded before the submit read.

    Application-owned, not framework-owned: it is the answer this recipe's own
    edge comparison gives, and it means the same thing under either
    concurrency mode.
    """


def render_balance_milestone(db: ScopedDatabase, *, id: int) -> tuple[Balance, Edge]:
    """RENDER time (Transaction-Time-Only): a plain, non-transactional find — the
    displayed milestone plus its edge (the Transaction-Time dimension's own from-instant,
    ``in_z``), the whole of what the form needs to transport."""
    node = db.find(Balance.where(Balance.id == id)).result()
    return node, edge_of(node)


def submit_balance_edit(
    db: ScopedDatabase,
    *,
    id: int,
    edge: Edge,
    fields: Mapping[str, Any],
    concurrency: Concurrency = "optimistic",
) -> None:
    """SUBMIT time (Transaction-Time-Only): read the CURRENT milestone, refuse
    the submit when its edge is not the transported one (a writer chained a
    replacement before this read), then apply ``fields`` via ``edit`` and
    update. Legal under either concurrency mode: ``locking``'s shared read lock
    holds the compared row until the flush, and ``optimistic``'s
    observed-``in_z`` gate closes zero rows —
    ``OptimisticLockConflictError`` — if one is chained after it."""

    def fn(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == id)).result()
        current_edge = edge_of(current)
        if current_edge.tx_time != edge.tx_time:
            raise StaleMilestoneError(
                f"balance {id} was superseded before this submit: the form displayed the "
                f"milestone starting {edge.tx_time.isoformat()}, but the current one starts "
                f"{current_edge.tx_time.isoformat()}"
            )
        tx.update(current.edit(**fields))

    db.transact(fn, concurrency=concurrency)


def render_branch_milestone(db: ScopedDatabase, *, id: int) -> tuple[Branch, Edge]:
    """RENDER time (bitemporal): a non-transactional current-rectangle find —
    the displayed rectangle plus its edge on BOTH declared axes (Valid Time and
    Transaction Time)."""
    node = db.find(Branch.where(Branch.id == id).as_of(valid_time=LATEST)).result()
    return node, edge_of(node)


def submit_branch_edit(
    db: ScopedDatabase,
    *,
    id: int,
    edge: Edge,
    fields: Mapping[str, Any],
    valid_from: dt.datetime,
    concurrency: Concurrency = "optimistic",
) -> None:
    """SUBMIT time (bitemporal): re-read the displayed RECTANGLE — Valid Time
    pinned at the transported coordinate (`as_of(valid_time=...)`, which
    selects which rectangle was displayed; a finite Valid-Time pin is the
    writable retroactive correction), Transaction Time left at its latest
    default so the read answers the rectangle's current milestone. Refuse the
    submit when that milestone's edge is not the transported one, then apply
    ``fields`` via ``edit`` and issue a PLAIN (unbounded) bitemporal
    correction effective from ``valid_from`` (the mutation's OWN Valid-Time
    instant `B` — the everyday "this correction takes effect from B onward"
    idiom, `m-bitemp-write-006`; independent of the displayed edge's own
    Valid-Time coordinate, which only selects the rectangle: ``valid_from``
    equal to the displayed rectangle's own `from_z` degenerates the head
    interval to empty and is a build-time caller error, out of this recipe's
    scope). A concurrent split between this read and the flush leaves the
    observed row's ``in_z`` stale — the gated close still addresses the
    displayed rectangle by its own Valid-Time end, but its gate matches zero
    rows, ``OptimisticLockConflictError``."""

    def fn(tx: Transaction) -> None:
        current = tx.find(Branch.where(Branch.id == id).as_of(valid_time=edge.valid_time)).result()
        current_edge = edge_of(current)
        if current_edge.tx_time != edge.tx_time:
            raise StaleMilestoneError(
                f"branch {id} was superseded before this submit: the form displayed the "
                f"rectangle's milestone starting {edge.tx_time.isoformat()}, but the current "
                f"one starts {current_edge.tx_time.isoformat()}"
            )
        tx.update(current.edit(**fields), valid_from=valid_from)

    db.transact(fn, concurrency=concurrency)
