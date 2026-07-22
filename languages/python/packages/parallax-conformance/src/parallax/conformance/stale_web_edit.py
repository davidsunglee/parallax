"""``parallax.conformance.stale_web_edit`` — the spec §3 stale-web-edit recipe,
both variants (COR-3 Phase 8 increment 7 completion round).

The idiom (`python.md` §3 `:429-461`; the locking-mode-vs-optimistic rule and
WHY the recipe runs optimistic, §5 `:602-617`): a web form displays one
temporal milestone, the user edits it offline (across a real HTTP
round-trip), and submits later. Render time captures the displayed
milestone's :class:`~parallax.core.temporal_read.Edge` — every declared
axis's finite from-instant (never the :data:`~parallax.core.temporal_read.
LATEST` sentinel, which re-resolves at submit time and would silently let a
stale edit "succeed" against whatever is current then; never a wall-clock
display instant, which is racy against assignment-ordered processing
instants). Submit time re-fetches **with every declared axis pinned at the
transported edge** inside an **optimistic** ``db.transact`` (never
``locking``: an edge-pinned observation is never latest-pinned, so a
locking-mode write over it raises ``HistoricalObservationError`` before any
DML — the observed-``in_z`` gate optimistic mode adds is what actually
detects a concurrent supersession), applies the caller's form fields via
``model_copy``, and issues ``tx.update``. A concurrent writer who has since
chained a replacement milestone leaves the observed row's ``in_z`` stale, so
the gated close matches zero rows — ``OptimisticLockConflictError``; an
untouched row's gate matches, and the edit lands.

This is Reladomo's own answer with the detach removed (`docs/research/
reladomo/10-object-lifecycle.md:32-39` — a detached copy carries the
milestone's ``IN_Z`` offline and the merge-back gate binds that carried
coordinate; transport, never reconstruction). The idiom requires **no
detached objects**: the ``Edge`` (two plain, JSON-serializable ``datetime``
values) is everything a real form need transport, and the public verb
surface (``db.find`` / ``edge_of`` / ``model_copy`` / ``tx.update``) is
everything it needs to replay.

Two variants, one shape each — audit-only (a single Transaction-Time dimension,
:class:`~parallax.conformance.read_models.Balance`) and bitemporal (both
axes, :class:`~parallax.conformance.vo_models.Branch`) — split into a
RENDER half (a plain, non-transactional ``db.find`` capturing the edge) and
a SUBMIT half (the optimistic re-fetch + edit + update), so a caller can
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
from parallax.core import Edge, edge_of
from parallax.snapshot.handle import Database, Transaction

__all__ = [
    "render_balance_milestone",
    "render_branch_milestone",
    "submit_balance_edit",
    "submit_branch_edit",
]


def render_balance_milestone(db: Database, *, id: int) -> tuple[Balance, Edge]:
    """RENDER time (audit-only): a plain, non-transactional find — the
    displayed milestone plus its edge (the Transaction-Time dimension's own from-instant,
    ``in_z``), the whole of what the form needs to transport."""
    node = db.find(Balance.where(Balance.id == id)).result()
    return node, edge_of(node)


def submit_balance_edit(db: Database, *, id: int, edge: Edge, fields: Mapping[str, Any]) -> None:
    """SUBMIT time (audit-only): re-fetch pinned at the transported edge,
    inside an OPTIMISTIC transaction (`python.md` §5: an edge-pinned
    observation is never latest-pinned, so a locking-mode write over it
    raises ``HistoricalObservationError`` before any DML), apply ``fields``
    via ``model_copy``, and update. A concurrent chain since the render
    leaves the observed row's ``in_z`` stale — the gated close matches zero
    rows, ``OptimisticLockConflictError``; an untouched row's gate matches,
    and the edit lands."""

    def fn(tx: Transaction) -> None:
        current = tx.find(
            Balance.where(Balance.id == id).as_of(transaction_time=edge.transaction_time)
        ).result()
        tx.update(current.model_copy(update=dict(fields)))

    db.transact(fn, concurrency="optimistic")


def render_branch_milestone(db: Database, *, id: int) -> tuple[Branch, Edge]:
    """RENDER time (bitemporal): a plain, non-transactional find — the
    displayed rectangle plus its edge on BOTH declared axes (business AND
    processing)."""
    node = db.find(Branch.where(Branch.id == id)).result()
    return node, edge_of(node)


def submit_branch_edit(
    db: Database, *, id: int, edge: Edge, fields: Mapping[str, Any], valid_from: dt.datetime
) -> None:
    """SUBMIT time (bitemporal): re-fetch with EVERY declared axis pinned at
    the transported edge (`as_of(transaction_time=..., valid_time=...)` — the DISPLAY
    coordinate, licensing the optimistic re-fetch) inside an OPTIMISTIC
    transaction, apply ``fields`` via ``model_copy``, and issue a PLAIN
    (unbounded) bitemporal correction effective from ``valid_from`` (the
    mutation's OWN Valid-Time instant `B` — the everyday "this correction takes
    effect from B onward" idiom, `m-bitemp-write-006`; independent of the
    displayed edge's own Valid-Time coordinate, which only licenses the
    re-fetch: ``valid_from`` equal to the displayed rectangle's own
    `from_z` degenerates the head interval to empty and is a build-time
    caller error, out of this recipe's scope). A concurrent split since the
    render leaves the observed row's ``in_z`` stale (and, when the key's
    current rows share an ``in_z``, the business discriminator too) — the
    gated close matches zero rows, ``OptimisticLockConflictError``; an
    untouched rectangle's gate matches, and the edit lands."""

    def fn(tx: Transaction) -> None:
        current = tx.find(
            Branch.where(Branch.id == id).as_of(
                transaction_time=edge.transaction_time, valid_time=edge.valid_time
            )
        ).result()
        tx.update(current.model_copy(update=dict(fields)), valid_from=valid_from)

    db.transact(fn, concurrency="optimistic")
