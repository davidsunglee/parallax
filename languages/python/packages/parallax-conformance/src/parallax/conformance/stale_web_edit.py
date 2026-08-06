"""The specification's Transaction-Time-Only and Bitemporal stale-web-edit recipes.

The idiom (`python.md` §3): a web form displays one temporal milestone, the
user edits it offline (across a real HTTP round-trip), and submits later.
Render time captures the displayed milestone's
:class:`~parallax.core.temporal_read.Edge` — every declared axis's finite
from-instant, the only coordinate that identifies the milestone exactly (never
the :data:`~parallax.core.temporal_read.LATEST` sentinel, which is not a
coordinate at all and re-resolves to whatever is current at submit time;
never a wall-clock display instant, which need not equal the displayed
milestone's own coordinate, because Transaction-Time instants order by
assignment rather than by commit). Submit time reads the **current**
milestone, compares its edge against the transported one, and refuses the
submit as stale when they differ; on a match it applies the caller's form
fields via ``edit`` and issues ``tx.update``.

The comparison, not a pin, is what asserts the displayed milestone is still
current. Transporting a Transaction-Time coordinate and pinning the re-fetch
at it would select the displayed milestone whether or not it is still current,
so the assertion has to be made in application code — and a finite
Transaction-Time pin is read-only, because the Transaction-Time past is never
rewritten. The Bitemporal variant still pins Valid Time at the transported
coordinate: a finite Valid-Time pin is the writable retroactive correction,
and it genuinely selects which rectangle was displayed rather than asserting
anything about currency.

Staleness therefore surfaces at two distinct points. A writer who chained a
replacement **before** the submit read is caught by the edge comparison,
``StaleMilestoneError``. A writer who chains one **between** the submit read
and the flush leaves the observed row's ``in_z`` stale, so the gated close
matches zero rows — ``OptimisticLockConflictError``.

Either concurrency mode is legal, for different reasons: ``locking`` takes a
shared read lock on the current row at read time, so once the comparison
passes nothing can supersede it before the flush; ``optimistic`` takes no
lock, and the observed-``in_z`` gate covers exactly that window.

This is Reladomo's own answer with the detach removed (`docs/research/
reladomo/10-object-lifecycle.md:32-39` — a detached copy carries the
milestone's ``IN_Z`` offline and the merge-back gate binds that carried
coordinate; transport, never reconstruction). The idiom requires **no
detached objects**: the ``Edge`` (two plain, JSON-serializable ``datetime``
values) is everything a real form need transport, and the public verb
surface (``db.find`` / ``edge_of`` / ``edit`` / ``tx.update``) is
everything it needs to replay.

Two variants, one shape each — Transaction-Time-Only (a single Transaction-Time dimension,
:class:`~parallax.conformance.read_models.Balance`) and bitemporal (both
axes, :class:`~parallax.conformance.vo_models.Branch`) — split into a
RENDER half (a plain, non-transactional ``db.find`` capturing the edge) and
a SUBMIT half (the re-read + comparison + edit + update), so a caller can
interleave a real "form round trip" (a concurrent writer, a persisted edge,
whatever else happens between render and submit) between the two calls
exactly like a real web request would.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.conformance.read_models import Balance
from parallax.conformance.vo_models import Branch
from parallax.core import Edge
from parallax.core.unit_work import Concurrency
from parallax.snapshot import edge_of
from parallax.snapshot.handle import Database, Transaction

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


def render_balance_milestone(db: Database, *, id: int) -> tuple[Balance, Edge]:
    """RENDER time (Transaction-Time-Only): a plain, non-transactional find — the
    displayed milestone plus its edge (the Transaction-Time dimension's own from-instant,
    ``in_z``), the whole of what the form needs to transport."""
    node = db.find(Balance.where(Balance.id == id)).result()
    return node, edge_of(node)


def submit_balance_edit(
    db: Database,
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


def render_branch_milestone(db: Database, *, id: int) -> tuple[Branch, Edge]:
    """RENDER time (bitemporal): a plain, non-transactional find — the
    displayed rectangle plus its edge on BOTH declared axes (Valid Time and
    Transaction Time)."""
    node = db.find(Branch.where(Branch.id == id)).result()
    return node, edge_of(node)


def submit_branch_edit(
    db: Database,
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
