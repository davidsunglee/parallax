from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.conformance.read_models import Balance
from parallax.conformance.vo_models import Branch
from parallax.core import LATEST, Edge
from parallax.core.unit_work import Concurrency
from parallax.snapshot import ScopedDatabase, Transaction, edge_of

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
        tx.amend(current.edit(**fields))

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
    """SUBMIT time (bitemporal): read the object where the correction takes
    effect — Valid Time pinned at ``valid_from``, the mutation's own instant `B`
    (the everyday "this correction takes effect from B onward" idiom), which an
    observed write takes from its source's pin — with Transaction Time left at
    its latest default, so the read answers the current milestone of the
    rectangle holding `B`. Refuse the submit unless that is the displayed
    rectangle at the transported milestone — the same Valid-Time start and the
    same Transaction-Time start — then apply ``fields`` via ``edit`` and issue a
    PLAIN (unbounded) bitemporal correction, which applies from `B` across all
    current coverage. A concurrent split between this read and the flush
    leaves the observed row's ``in_z`` stale — the gated close still addresses
    the displayed rectangle by its own Valid-Time end, but its gate matches zero
    rows, ``OptimisticLockConflictError``."""

    def fn(tx: Transaction) -> None:
        current = tx.find(Branch.where(Branch.id == id).as_of(valid_time=valid_from)).result()
        current_edge = edge_of(current)
        if current_edge != edge:
            raise StaleMilestoneError(
                f"branch {id} was superseded before this submit: the form displayed the "
                f"rectangle starting {edge.valid_time.isoformat()} at the milestone starting "
                f"{edge.tx_time.isoformat()}, but {valid_from.isoformat()} now falls in the one "
                f"starting {current_edge.valid_time.isoformat()} at "
                f"{current_edge.tx_time.isoformat()}"
            )
        tx.amend(current.edit(**fields))

    db.transact(fn, concurrency=concurrency)
