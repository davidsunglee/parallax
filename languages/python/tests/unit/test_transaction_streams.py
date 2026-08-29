"""Participating-stream unit tests for `parallax.snapshot.handle` (spec §5, Docker-free fake ports).

`Transaction.stream` and `tx.wire.stream`: what participation adds to a delivery
whose own contract — the state table, statement accounting, root-local identity,
and the cursorless root — is graded in `test_snapshot_stream.py`.

Four claims bound this suite. Participation is per PAGE, so the force-flush
`Transaction.find` performs once happens once per page and read-your-own-writes
holds at every one of them; the write buffer a consuming loop fills is therefore
bounded by a page rather than by the result, which is the same unbounded growth
a stream exists to remove, measured on the buffer itself. Each materialized
level derives its read lock from that level's OWN target Entity, exactly as a
participating find does. Evidence is the streamed root's, so a root a delivery
published licenses a later keyed write, outlives the page it arrived in for as
long as something reaches it, and meets a Typed read of the same row on ONE
retained observation. And delivery is per ATTEMPT: a re-executed callback opens
a fresh stream and observes the same roots again.
"""

from __future__ import annotations

import datetime as dt
import gc
from decimal import Decimal
from typing import Any, cast

import _mixed_strategy_model as mx
import pytest
from _transact_support import account_db, db_for, deadlock

from _support import mirrored_models as mm
from _support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    Read,
    ReadCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import POSITION_MODEL, Position
from parallax.core import LATEST
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.object_query import TX_TIME, VALID_TIME
from parallax.core.unit_work import ObservedStateKey, RetainedObservation, instructions
from parallax.snapshot import SnapshotStream, SnapshotStreamStateError
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import Transaction, TransactionTimePinReadOnlyError
from parallax.snapshot.materialize import source_hint_of

_UPDATE_SQL = POSTGRES.to_driver_sql(
    "update account set balance = ?, version = ? where id = ? and version = ?"
)

_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_INFINITY = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)

# The bitemporal pair the evidence-lifetime tests deliver: an observed state
# exists for a temporal Entity without a version attribute, and `Policy` is the
# one mirrored model whose root reaches an included child worth retaining alone.
_POLICY_ROW: Row = {
    "id": 1,
    "name": "P-1",
    "from_z": _TX_START,
    "thru_z": _INFINITY,
    "in_z": _TX_START,
    "out_z": _INFINITY,
}
_COVERAGE_ROW: Row = {
    "id": 10,
    "policy_id": 1,
    "amount": Decimal("250.00"),
    "from_z": _TX_START,
    "thru_z": _INFINITY,
    "in_z": _TX_START,
    "out_z": _INFINITY,
}
_POLICY_QUERY = Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)


def _account_row(account_id: int, *, balance: str = "100.00") -> Row:
    return {
        "id": account_id,
        "owner": f"owner-{account_id}",
        "balance": Decimal(balance),
        "version": 1,
    }


def _accounts() -> Any:
    return mm.Account.where(mm.Account.id >= 1)


def _kinds(port: ScriptedPort) -> list[type[PortCall]]:
    return [type(op) for op in port.calls]


def _sql(port: ScriptedPort, position: int) -> str:
    call = port.calls[position]
    assert isinstance(call, (ReadCall, WriteCall))
    return call.sql


def _pending_writes(tx: Transaction) -> int:
    """How many writes this transaction is still holding, read off the buffer.

    The claim is about the buffer rather than about the statements it eventually
    lowers to, so it is measured there: a bound inferred from DML would be
    satisfied by coalescing that never happened.
    """
    uow = tx._uow  # pyright: ignore[reportPrivateUsage] - unit test reads the transaction's own ledger
    return len(uow._buffer)  # pyright: ignore[reportPrivateUsage] - the buffer IS the claim's subject


def _observation(node: object) -> Any:
    state = snapshot_state_of(node)
    assert state is not None
    return cast("Any", state.source)


# --------------------------------------------------------------------------- #
# Participation is per page: the flush happens once per page, not once at entry.#
# --------------------------------------------------------------------------- #
def test_a_write_buffered_mid_delivery_reaches_the_database_before_the_next_page() -> None:
    # Read-your-own-writes at every page rather than intermittently: the page
    # after a buffered write force-flushes it, so the statement that would
    # observe it runs after it. A flush once at entry would leave the rule
    # holding only when the loop happened to call `find` as well.
    port = ScriptedPort(
        Transact(Read(rows=[_account_row(1)]), Write(), Read(rows=[_account_row(2)]), Read(rows=[]))
    )

    def fn(tx: Transaction) -> None:
        with tx.stream(_accounts(), batch_size=1) as stream:
            for account in stream:
                if account.id == 1:
                    tx.update(account.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert _kinds(port) == [BeginCall, ReadCall, WriteCall, ReadCall, ReadCall, CommitCall]
    assert port.calls[2] == WriteCall(_UPDATE_SQL, (Decimal("125.00"), 2, 1, 1))


def test_a_read_only_delivery_emits_no_dml_at_all() -> None:
    # An empty buffer is one truthiness check, so a loop that writes nothing pays
    # nothing for the per-page flush — no DML, and no Write Batch to open.
    port = ScriptedPort(
        Transact(Read(rows=[_account_row(1), _account_row(2)]), Read(rows=[_account_row(3)]))
    )

    def fn(tx: Transaction) -> list[int]:
        with tx.stream(_accounts(), batch_size=2) as stream:
            return [account.id for account in stream]

    assert account_db(port).transact(fn) == [1, 2, 3]
    assert _kinds(port) == [BeginCall, ReadCall, ReadCall, CommitCall]


@pytest.mark.parametrize("size", [1, 2, 3])
def test_a_writing_loop_never_holds_more_than_one_pages_writes(size: int) -> None:
    # The bound the per-page flush buys, measured on the buffer at every root:
    # what a loop accumulates is a page's worth, whatever the result's size, so
    # the same dial that sizes a page sizes the buffer.
    rows = [_account_row(account_id) for account_id in range(1, 7)]
    pages = [rows[at : at + size] for at in range(0, len(rows), size)]
    port = ScriptedPort(
        Transact(
            *(entry for page in pages for entry in (Read(rows=page), Write(times=len(page)))),
            Read(),
        )
    )
    held: list[int] = []

    def fn(tx: Transaction) -> None:
        with tx.stream(_accounts(), batch_size=size) as stream:
            for account in stream:
                tx.update(account.edit(balance=Decimal("125.00")))
                held.append(_pending_writes(tx))

    account_db(port).transact(fn)
    assert len(held) == len(rows)
    assert max(held) == size


# --------------------------------------------------------------------------- #
# Each level's read lock derives from that level's own target Entity.          #
# --------------------------------------------------------------------------- #
def test_a_streamed_page_locks_the_unversioned_level_and_not_the_versioned_root() -> None:
    # The per-level derivation a participating find already makes, unchanged by
    # the page loop above it: ONE preference, one page, two strategies.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "total": Decimal("10.00"), "version": 1}]),
            Read(rows=[{"id": 5, "consignment_id": 1, "carrier": "Hansa"}]),
            Read(rows=[]),
        )
    )

    def fn(tx: Transaction) -> None:
        query = mx.Consignment.where(mx.Consignment.id == 1).include(mx.Consignment.legs)
        with tx.stream(query, batch_size=1) as stream:
            list(stream)

    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(fn)
    assert _kinds(port) == [BeginCall, ReadCall, ReadCall, ReadCall, CommitCall]
    assert not _sql(port, 1).endswith("for share of t0")
    assert _sql(port, 2).endswith("for share of t0")


def test_the_locking_preference_locks_every_level_of_a_streamed_page() -> None:
    # The same delivery under the override, which is what makes the mixed result
    # above a derivation rather than a property of the model.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "total": Decimal("10.00"), "version": 1}]),
            Read(rows=[{"id": 5, "consignment_id": 1, "carrier": "Hansa"}]),
            Read(rows=[]),
        )
    )

    def fn(tx: Transaction) -> None:
        query = mx.Consignment.where(mx.Consignment.id == 1).include(mx.Consignment.legs)
        with tx.stream(query, batch_size=1) as stream:
            list(stream)

    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(fn, concurrency="locking")
    assert _sql(port, 1).endswith("for share of t0")
    assert _sql(port, 2).endswith("for share of t0")


# --------------------------------------------------------------------------- #
# Evidence belongs to the streamed root, not to the page it arrived in.        #
# --------------------------------------------------------------------------- #
def test_a_streamed_roots_own_observation_licenses_a_later_keyed_write() -> None:
    # The write is settled against the version the DELIVERY observed rather than
    # against a resolving read at write time: the gate binds 1 and the advance
    # writes 2, both derived from the root the stream published.
    port = ScriptedPort(Transact(Read(rows=[_account_row(1)]), Read(rows=[]), Write()))

    def fn(tx: Transaction) -> None:
        with tx.stream(_accounts(), batch_size=1) as stream:
            accounts = list(stream)
        tx.update(accounts[0].edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert port.calls[-2] == WriteCall(_UPDATE_SQL, (Decimal("125.00"), 2, 1, 1))


def test_a_wire_streamed_value_and_a_typed_find_of_one_row_carry_one_observation() -> None:
    # Representation is the namespace and delivery is the verb, so neither
    # decides what a value may license: two views of one observed state share
    # ONE retained observation rather than equal copies, which is what keeps a
    # flush that spends the evidence from leaving a second copy still licensing.
    # Two result sets, not three: the delivery is abandoned after its first root
    # rather than drained, so no terminal page is read and the second belongs to
    # the find.
    port = ScriptedPort(Transact(Read(rows=[_account_row(1)], times=2)))

    def fn(tx: Transaction) -> tuple[Any, Any]:
        with tx.wire.stream(mm.Account.where(mm.Account.id == 1), batch_size=1) as stream:
            streamed = next(iter(stream))
        found = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        return cast("Any", source_hint_of(streamed)), _observation(found)

    streamed_hint, found_hint = account_db(port).transact(fn)
    assert streamed_hint is not None
    assert streamed_hint.object_key == found_hint.object_key
    assert streamed_hint.observation is found_hint.observation


def test_a_retained_streamed_child_outlives_its_released_root_and_page() -> None:
    # Liveness is strong reachability, and a page is not a scope evidence hangs
    # on: the claim belongs to the entity node, so a child extracted from a
    # delivered root keeps its own after the root and the page are gone.
    port = ScriptedPort(Transact(Read(rows=[_POLICY_ROW]), Read(rows=[_COVERAGE_ROW])))

    def fn(tx: Transaction) -> Any:
        with tx.stream(_POLICY_QUERY, batch_size=1) as stream:
            child = next(iter(stream)).coverages[0]
        gc.collect()
        return _observation(child)

    hint = db_for(POLICY_MODEL, port).transact(fn)
    assert hint.observation is not None
    assert hint.object_key.primary_key == (("id", 10),)


def test_releasing_every_streamed_source_makes_the_transactions_index_forget_it() -> None:
    # The converse, and the reason the page is not a retention scope either: the
    # unit of work holds a WEAK index, so an observed state no delivered value
    # still reaches disappears from it with the last reference to that value.
    port = ScriptedPort(
        Transact(Read(rows=[_POLICY_ROW]), Read(rows=[_COVERAGE_ROW]), Read(rows=[]))
    )

    def fn(tx: Transaction) -> tuple[ObservedStateKey, RetainedObservation | None]:
        with tx.stream(_POLICY_QUERY, batch_size=1) as stream:
            roots = list(stream)
        hint = _observation(roots[0])
        state = cast("ObservedStateKey", hint.observation.key)
        assert tx._uow.retained_for(state) is hint.observation  # pyright: ignore[reportPrivateUsage] - the index is first-party state
        del roots, hint
        gc.collect()
        return state, tx._uow.retained_for(state)  # pyright: ignore[reportPrivateUsage] - the index is first-party state

    state, after_release = db_for(POLICY_MODEL, port).transact(fn)
    assert state is not None
    assert after_release is None


# --------------------------------------------------------------------------- #
# Delivery is attempt-local: a retry re-delivers through a fresh stream.       #
# --------------------------------------------------------------------------- #
def test_a_retried_callback_opens_a_fresh_stream_and_observes_the_roots_again() -> None:
    # A root already consumed cannot be recalled, and nothing buffers delivery
    # until commit, so the re-executed callback starts from the beginning. The
    # stream it opens is a new one: the previous attempt's is closed with its
    # scope and answers nothing further.
    port = ScriptedPort(
        Transact(
            Read(rows=[_account_row(1), _account_row(2)]),
            Read(rows=[_account_row(3)]),
            commit=deadlock(),
        ),
        Transact(Read(rows=[_account_row(1), _account_row(2)]), Read(rows=[_account_row(3)])),
    )
    attempts: list[list[int]] = []
    opened: list[SnapshotStream[Any]] = []

    def fn(tx: Transaction) -> None:
        with tx.stream(_accounts(), batch_size=2) as stream:
            opened.append(stream)
            attempts.append([account.id for account in stream])

    account_db(port).transact(fn)
    assert attempts == [[1, 2, 3], [1, 2, 3]]
    assert port.calls.count(BeginCall()) == 2
    assert opened[0] is not opened[1]
    with pytest.raises(SnapshotStreamStateError, match="inside its own scope"):
        _ = opened[0].pin


# --------------------------------------------------------------------------- #
# A streamed milestone root is a historical view: read-only, both namespaces.  #
# --------------------------------------------------------------------------- #
_POSITION_MILESTONES: tuple[Row, ...] = (
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("90.00"),
        "from_z": _TX_START,
        "thru_z": _INFINITY,
        "in_z": _TX_START,
        "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    },
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("200.00"),
        "from_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "thru_z": _INFINITY,
        "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY,
    },
)


def _milestone_query() -> Any:
    return Position.where(Position.id == 1).history(TX_TIME).history(VALID_TIME)


def test_a_streamed_milestone_root_is_read_only_in_both_namespaces() -> None:
    # Every milestone stands at a FINITE Transaction-Time edge, so a delivered
    # milestone root is the Transaction-Time past and no keyed verb rewrites it.
    # The two namespaces refuse it for the two reasons each has: the Typed node
    # carries the edge as its own lifecycle pin, and the Wire node carries no
    # provenance at all, a milestone-set read retaining none — which is exactly
    # what the whole-result read of the same query publishes.
    typed_port = ScriptedPort(Transact(Read(rows=list(_POSITION_MILESTONES))))
    wire_port = ScriptedPort(Transact(Read(rows=list(_POSITION_MILESTONES))))

    def typed(tx: Transaction) -> None:
        with tx.stream(_milestone_query(), batch_size=2) as stream:
            root = next(iter(stream))
        with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
            tx.update(root.edit(value=Decimal("1.00")))

    def wire(tx: Transaction) -> None:
        with tx.wire.stream(_milestone_query(), batch_size=2) as stream:
            root = next(iter(stream))
        assert source_hint_of(root) is None
        with pytest.raises(instructions.WriteInstructionError, match="no such provenance"):
            tx.wire.update(root, {"value": "1.00"})

    db_for(POSITION_MODEL, typed_port).transact(typed)
    db_for(POSITION_MODEL, wire_port).transact(wire)
