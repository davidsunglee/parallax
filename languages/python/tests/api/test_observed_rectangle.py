"""The observed-rectangle close under optimistic concurrency, against real Postgres.

One key holding two rectangles current at a single Transaction Time, read at two
Valid-Time coordinates inside one transaction and then corrected from the first
read's own value. The Docker-free lane already pins what the close ADDRESSES and
what its gate BINDS (`tests/unit/test_temporal_write_lowering.py`); it cannot pin
that the gate MATCHES. A recording port reports every gated write as affecting a
row, so a close gating on the wrong rectangle's own `in_z` is indistinguishable
there from one gating on the right rectangle's — both look like a clean success.
Only a real database separates them, and what separates them is which row was
left closed.

Like `test_stale_web_edit.py`, this is a standalone Docker-backed proof rather
than a case-keyed `api_suite.EXAMPLES` entry: it is the developer choreography of
two reads and one write, not a case's own authored observation, so registering it
under a borrowed case id would misrepresent what that case's goldens grade.

The `Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`: three flushing
transactions need three distinct Transaction-Time instants, and the system
clock's resolution does not always separate back-to-back `db.transact` calls.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from parallax.conformance.class_models import MODELS
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.story_models import Position
from parallax.core.entity._model import model_of
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction

_POSITION = MODELS["position"]

# The three flushing transactions' instants: the two seeding inserts, then the
# correction.
_T1 = dt.datetime(2023, 11, 1, tzinfo=dt.UTC)
_T2 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T3 = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)

# The Valid-Time skeleton: the retroactive rectangle runs [V1, V2), the current
# one [V2, infinity), and the correction takes effect from V3 inside the latter.
# VP pins a read inside the retroactive rectangle.
_V1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_V2 = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_V3 = dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
_VP = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)

_CURRENT_ROWS = (
    "select from_z, case when thru_z = 'infinity' then null else thru_z end as valid_end, val "
    "from position where out_z = 'infinity' order by from_z"
)
_CLOSED_ROWS = "select from_z from position where out_z <> 'infinity' order by from_z"


def test_an_optimistic_close_settles_against_the_rectangle_it_read(provisioner: Any) -> None:
    # A key carrying a retroactive rectangle beside its current one — what an
    # earlier correction leaves behind — is read latest, read again at a
    # Valid-Time instant inside the retroactive rectangle to compare against, and
    # then corrected from the value the FIRST read handed back. The current
    # rectangle is the one closed and split; the retroactive one is left exactly
    # as it was, still current on the Transaction-Time axis and still carrying its
    # own value. The distinction is that the optimistic gate cannot rescue a
    # misresolved address: it binds the same observation the address came from, so
    # a close aimed at the wrong rectangle gates on that rectangle's own `in_z`,
    # matches one row, and reports success. Which row was closed is therefore the
    # only observable that separates the two outcomes, and it needs a real
    # database to read.
    provisioner.reset(model_of(_POSITION), {})
    db = connect(provisioner.port, _POSITION, clock=ScriptedClock([_T1, _T2, _T3]))

    db.transact(
        lambda tx: tx.insert_until(
            Position(id=1, acct_num="A", value=Decimal("50.00")), valid_from=_V1, until=_V2
        )
    )
    db.transact(
        lambda tx: tx.insert(Position(id=1, acct_num="A", value=Decimal("100.00")), valid_from=_V2)
    )

    def correct(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1)).result()
        tx.find(Position.where(Position.id == 1).as_of(valid_time=_VP)).result()
        tx.update(current.edit(value=Decimal("150.00")), valid_from=_V3)

    db.transact(correct, concurrency="optimistic")

    closed = provisioner.port.execute(_CLOSED_ROWS, [])
    assert [row["from_z"] for row in closed] == [_V2]

    current_rows = provisioner.port.execute(_CURRENT_ROWS, [])
    assert [(row["from_z"], row["valid_end"], row["val"]) for row in current_rows] == [
        (_V1, _V2, Decimal("50.00")),
        (_V2, _V3, Decimal("100.00")),
        (_V3, None, Decimal("150.00")),
    ]
