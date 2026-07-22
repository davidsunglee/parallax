"""The spec §3 stale-web-edit recipe, both variants, against real Postgres.

The scenarios exercise the `HistoricalObservationError` locking-mode rule in
`python.md` §5 as well as the render-then-submit recipe in §3.

Neither variant maps to a single active corpus case one-to-one (every
`m-opt-lock`/`m-bitemp-write` `conflict`-shape case that touches this same
optimistic-gate machinery is a SYNTHETIC, single-connection injection —
`given.apply` / `when.observedTxStart` — already graded end-to-end by the
compile/run conformance lanes; none of them expresses the genuine two-read
render-then-submit developer choreography this recipe is), so these stay
standalone Docker-backed proofs (`parallax.conformance.stale_web_edit`) rather
than case-keyed `api_suite.EXAMPLES` entries — force-registering under a
borrowed case id would misrepresent what that case's own goldens grade. The
Usage Guide renders both variants through the case-free `api_suite.RECIPES`
section instead, citing spec §3 plus these tests as the grading surface — one
source for both guide and grading.

Every `Database` here connects with a :class:`~parallax.conformance.
scripted_clock.ScriptedClock`: the system clock's microsecond resolution is not
always distinct across two back-to-back `db.transact` calls. Two equal instants
would collide on a temporal entity's `(pk, from_z, in_z)` uniqueness, so one
deterministic instant per flushing transaction removes that flakiness.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import models
from parallax.conformance.read_models import Balance
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.stale_web_edit import (
    render_balance_milestone,
    render_branch_milestone,
    submit_balance_edit,
    submit_branch_edit,
)
from parallax.conformance.vo_models import Address, Branch, Geo
from parallax.core import opt_lock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

pytestmark = pytest.mark.api_conformance

_BALANCE = models.load_models()["balance"]
_BRANCH = models.load_models()["branch"]

_I1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_I2 = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_I3 = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _seed_balance(db: Database, *, id: int = 1) -> None:
    db.transact(lambda tx: tx.insert(Balance(id=id, acct_num="A", value=Decimal("100.00"))))


def _seed_branch(db: Database, *, id: int = 1) -> None:
    db.transact(
        lambda tx: tx.insert(
            Branch(
                id=id,
                name="Central Branch",
                address=Address(street="1 Main St", city="Helsinki", geo=Geo(country="FI")),
            ),
            valid_from=_I1,
        )
    )


# --------------------------------------------------------------------------- #
# The AUDIT-ONLY variant (Balance — a single Transaction-Time dimension).                #
# --------------------------------------------------------------------------- #
def test_audit_only_stale_web_edit_updates_the_displayed_milestone(provisioner: Any) -> None:
    provisioner.reset(_BALANCE, {})
    db = connect(provisioner.port, _BALANCE, clock=ScriptedClock([_I1, _I2]))
    _seed_balance(db)

    node, edge = render_balance_milestone(db, id=1)  # RENDER time
    assert node.value == Decimal("100.00")

    submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("150.00")})  # SUBMIT time

    current = db.find(Balance.where(Balance.id == 1)).result()
    assert current.value == Decimal("150.00")
    assert current.acct_num == "A"  # the merge preserves untouched fields


def test_audit_only_stale_web_edit_raises_historical_observation_in_locking_mode(
    provisioner: Any,
) -> None:
    # An edge-pinned observation is NEVER latest-pinned (`python.md` §5): a
    # locking-mode write over it raises before any DML, even with no
    # concurrent writer at all — the shared read lock would protect the
    # WRONG milestone once one exists.
    provisioner.reset(_BALANCE, {})
    db = connect(provisioner.port, _BALANCE, clock=ScriptedClock([_I1, _I2]))
    _seed_balance(db)
    _node, edge = render_balance_milestone(db, id=1)

    def fn(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1).as_of(tx_time=edge.tx_time)).result()
        tx.update(current.model_copy(update={"value": Decimal("150.00")}))

    with pytest.raises(opt_lock.HistoricalObservationError, match="latest-pinned"):
        db.transact(fn)  # locking is the default concurrency — never submit this way
    current = db.find(Balance.where(Balance.id == 1)).result()
    assert current.value == Decimal("100.00")  # nothing was written


# --------------------------------------------------------------------------- #
# The BITEMPORAL variant (Branch — both axes transported).                    #
# --------------------------------------------------------------------------- #
def test_bitemporal_stale_web_edit_updates_the_displayed_rectangle(provisioner: Any) -> None:
    provisioner.reset(_BRANCH, {})
    db = connect(provisioner.port, _BRANCH, clock=ScriptedClock([_I1, _I2]))
    _seed_branch(db)

    node, edge = render_branch_milestone(db, id=1)  # RENDER time
    assert node.name == "Central Branch"

    # SUBMIT time — the correction takes effect from I2 onward, distinct from
    # the displayed rectangle's own Valid-Time start (I1): a `valid_from`
    # equal to the rectangle's own `from_z` degenerates the head interval.
    submit_branch_edit(db, id=1, edge=edge, fields={"name": "Renamed Branch"}, valid_from=_I2)

    current = db.find(Branch.where(Branch.id == 1)).result()
    assert current.name == "Renamed Branch"
    assert current.address is not None  # the untouched VO document survives the merge


def test_bitemporal_stale_web_edit_optimistic_conflict_surfaces(provisioner: Any) -> None:
    # A concurrent writer chains a replacement rectangle BETWEEN the render
    # and the submit: the transported edge's own `in_z` is now stale, so the
    # submit's gated close matches zero rows -- the conflict, surfaced
    # through the PUBLIC verb, never a detached object's own merge-back.
    provisioner.reset(_BRANCH, {})
    db = connect(provisioner.port, _BRANCH, clock=ScriptedClock([_I1, _I3]))
    _seed_branch(db)

    _node, edge = render_branch_milestone(db, id=1)  # RENDER time — the stale edge

    # An independent second connection commits a REAL chaining update first.
    peer_port = provisioner.peer()
    peer_db = connect(peer_port, _BRANCH, clock=ScriptedClock([_I2]))

    def concurrent_write(tx: Transaction) -> None:
        current = tx.find(Branch.where(Branch.id == 1)).result()
        tx.update(current.model_copy(update={"name": "Renamed By Someone Else"}), valid_from=_I2)

    peer_db.transact(concurrent_write)

    with pytest.raises(opt_lock.OptimisticLockConflictError):
        # SUBMIT time — the correction was never applied (the close never
        # affects any row), so its own `valid_from` value is immaterial to
        # the conflict; any instant distinct from the rectangle's own start.
        submit_branch_edit(db, id=1, edge=edge, fields={"name": "My Stale Edit"}, valid_from=_I3)

    current = db.find(Branch.where(Branch.id == 1)).result()
    assert current.name == "Renamed By Someone Else"  # the stale edit never landed
