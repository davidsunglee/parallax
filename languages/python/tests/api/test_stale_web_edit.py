"""The spec §3 stale-web-edit recipe, both variants, against real Postgres.

Every submit runs twice, once per concurrency mode: the recipe reads the
current milestone and asserts currency by comparing edges in its own code, so
it is legal under both. A separate closure written out by hand — never the
recipe — replays the transported edge as a PIN instead, which is what proves
the alternative the recipe rejects is not merely inferior but refused: a view
pinned in the Transaction-Time past is read-only, in either mode.

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

from parallax.conformance.class_models import MODELS
from parallax.conformance.read_models import Balance
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.stale_web_edit import (
    StaleMilestoneError,
    render_balance_milestone,
    render_branch_milestone,
    submit_balance_edit,
    submit_branch_edit,
)
from parallax.conformance.vo_models import Address, Branch, Geo
from parallax.core.entity._model import model_of
from parallax.core.unit_work import Concurrency
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction, TransactionTimePinReadOnlyError

_BALANCE = MODELS["balance"]
_BRANCH = MODELS["branch"]

_I1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_I2 = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_I3 = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

# Both modes grade every submit. They protect the window between the submit
# read and the flush differently -- `locking` holds a shared read lock on the
# compared row, `optimistic` gates the close on the observed `in_z` -- and the
# recipe depends on neither, so its outcome is the same under each.
_MODES: tuple[Concurrency, ...] = ("optimistic", "locking")


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
@pytest.mark.parametrize("concurrency", _MODES)
def test_audit_only_stale_web_edit_updates_the_displayed_milestone(
    provisioner: Any, concurrency: Concurrency
) -> None:
    provisioner.reset(model_of(_BALANCE), {})
    db = connect(provisioner.port, _BALANCE, clock=ScriptedClock([_I1, _I2]))
    _seed_balance(db)

    node, edge = render_balance_milestone(db, id=1)  # RENDER time
    assert node.value == Decimal("100.00")

    submit_balance_edit(  # SUBMIT time
        db, id=1, edge=edge, fields={"value": Decimal("150.00")}, concurrency=concurrency
    )

    current = db.find(Balance.where(Balance.id == 1)).result()
    assert current.value == Decimal("150.00")
    assert current.acct_num == "A"  # the merge preserves untouched fields


@pytest.mark.parametrize("concurrency", _MODES)
def test_audit_only_stale_web_edit_refuses_a_superseded_milestone(
    provisioner: Any, concurrency: Concurrency
) -> None:
    # A concurrent writer chains a replacement BETWEEN the render and the
    # submit, so the submit's own read of the CURRENT milestone answers an edge
    # the form never displayed. The recipe's comparison catches that before it
    # authors anything -- the earlier of the two points staleness surfaces at,
    # and the one no gate and no lock can cover, because it happened before the
    # transaction started.
    provisioner.reset(model_of(_BALANCE), {})
    db = connect(provisioner.port, _BALANCE, clock=ScriptedClock([_I1, _I3]))
    _seed_balance(db)

    _node, edge = render_balance_milestone(db, id=1)  # RENDER time -- the stale edge

    peer_db = connect(provisioner.peer(), _BALANCE, clock=ScriptedClock([_I2]))

    def concurrent_write(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.update(current.edit(value=Decimal("200.00")))

    peer_db.transact(concurrent_write)

    with pytest.raises(StaleMilestoneError, match="superseded"):
        submit_balance_edit(
            db, id=1, edge=edge, fields={"value": Decimal("150.00")}, concurrency=concurrency
        )

    current = db.find(Balance.where(Balance.id == 1)).result()
    assert current.value == Decimal("200.00")  # the stale edit never landed


@pytest.mark.parametrize("concurrency", _MODES)
def test_a_submit_that_pins_the_transported_edge_is_read_only(
    provisioner: Any, concurrency: Concurrency
) -> None:
    # Why the recipe compares rather than pins, written out by hand because no
    # recipe does this: a submit that REPLAYS the transported edge as a pin reads
    # a milestone whose Transaction-Time coordinate is finite, and that view is
    # read-only in either mode. The copy derived from it carries the same pin, so
    # the refusal lands at the verb, before any DML.
    provisioner.reset(model_of(_BALANCE), {})
    db = connect(provisioner.port, _BALANCE, clock=ScriptedClock([_I1, _I2]))
    _seed_balance(db)
    _node, edge = render_balance_milestone(db, id=1)

    def fn(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1).as_of(tx_time=edge.tx_time)).result()
        tx.update(current.edit(value=Decimal("150.00")))

    with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
        db.transact(fn, concurrency=concurrency)
    current = db.find(Balance.where(Balance.id == 1)).result()
    assert current.value == Decimal("100.00")  # nothing was written


# --------------------------------------------------------------------------- #
# The BITEMPORAL variant (Branch — both axes transported).                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _MODES)
def test_bitemporal_stale_web_edit_updates_the_displayed_rectangle(
    provisioner: Any, concurrency: Concurrency
) -> None:
    provisioner.reset(model_of(_BRANCH), {})
    db = connect(provisioner.port, _BRANCH, clock=ScriptedClock([_I1, _I2]))
    _seed_branch(db)

    node, edge = render_branch_milestone(db, id=1)  # RENDER time
    assert node.name == "Central Branch"

    # SUBMIT time — the correction takes effect from I2 onward, distinct from
    # the displayed rectangle's own Valid-Time start (I1): a `valid_from`
    # equal to the rectangle's own `from_z` degenerates the head interval.
    submit_branch_edit(
        db,
        id=1,
        edge=edge,
        fields={"name": "Renamed Branch"},
        valid_from=_I2,
        concurrency=concurrency,
    )

    current = db.find(Branch.where(Branch.id == 1)).result()
    assert current.name == "Renamed Branch"
    assert current.address is not None  # the untouched VO document survives the merge


@pytest.mark.parametrize("concurrency", _MODES)
def test_bitemporal_stale_web_edit_refuses_a_superseded_rectangle(
    provisioner: Any, concurrency: Concurrency
) -> None:
    # A concurrent writer chains a replacement rectangle BETWEEN the render and
    # the submit. The submit's Valid-Time pin still selects the rectangle the
    # form displayed, but its Transaction-Time axis reads that rectangle's
    # CURRENT milestone, whose edge is the concurrent writer's -- so the
    # comparison refuses the stale submit before it authors anything.
    provisioner.reset(model_of(_BRANCH), {})
    db = connect(provisioner.port, _BRANCH, clock=ScriptedClock([_I1, _I3]))
    _seed_branch(db)

    _node, edge = render_branch_milestone(db, id=1)  # RENDER time — the stale edge

    # An independent second connection commits a REAL chaining update first.
    peer_port = provisioner.peer()
    peer_db = connect(peer_port, _BRANCH, clock=ScriptedClock([_I2]))

    def concurrent_write(tx: Transaction) -> None:
        current = tx.find(Branch.where(Branch.id == 1)).result()
        tx.update(current.edit(name="Renamed By Someone Else"), valid_from=_I2)

    peer_db.transact(concurrent_write)

    with pytest.raises(StaleMilestoneError, match="superseded"):
        # SUBMIT time — nothing is ever applied, so the correction's own
        # `valid_from` is immaterial; any instant distinct from the rectangle's
        # own start.
        submit_branch_edit(
            db,
            id=1,
            edge=edge,
            fields={"name": "My Stale Edit"},
            valid_from=_I3,
            concurrency=concurrency,
        )

    current = db.find(Branch.where(Branch.id == 1)).result()
    assert current.name == "Renamed By Someone Else"  # the stale edit never landed
