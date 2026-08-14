"""Write admission and Observed-State Coalescing (`m-unit-work`).

One claim algebra backs two seams — the synchronous refusal a keyed verb raises
and the merge finalization performs — so this module measures both against the
same rows: the algebra itself as a pure function, and the choreography a caller
actually performs through the real handles over a fake port.

The evidence a source carries and how long it lives is `test_source_evidence.py`'s
subject; what lives here is what a SECOND intent against the same evidence may do.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from _transact_support import (
    BALANCE,
    FIND_SQL_LOCKED,
    FIND_SQL_UNLOCKED,
    FIXED,
    INFINITY_INSTANT,
    PERSON,
    WHERE_POSITION_META,
    RecordingPort,
    WherePosition,
    account_db,
    balance_row,
    db_for,
)

from _support import mirrored_models as mm
from parallax.conformance.read_models import Person
from parallax.core import LATEST
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    SELECTION_INTENT,
    ClaimTable,
    FixedClock,
    KeyedWrite,
    ObjectKey,
    VersionedStateKey,
    WriteIntent,
    admits,
    keyed_intent,
)
from parallax.snapshot.handle import Database, Transaction, WriteEvidenceError

_ACCOUNT_ROW: dict[str, object] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_OTHER_FROM = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

_ASSIGNMENT = WriteIntent(kind="assignment")
_DESTRUCTIVE = WriteIntent(kind="destructive")
_STATE = VersionedStateKey(ObjectKey(EntityIdentity("parallax.compatibility", "Account"), ()), 4)


def _account_port(rows: list[dict[str, object]] | None = None) -> RecordingPort:
    return RecordingPort(rows=[dict(row) for row in (rows or [_ACCOUNT_ROW])])


def _writes(port: RecordingPort) -> list[tuple[object, ...]]:
    return [op for op in port.ops if op[0] == "write"]


# --------------------------------------------------------------------------- #
# The algebra itself.                                                         #
# --------------------------------------------------------------------------- #
def test_an_insert_intends_nothing_against_an_observed_state() -> None:
    # An opening row observes no prior state, so there is no claim for a second
    # intent to compete for — the absence is the missing answer, not an intent
    # kind of its own.
    assert keyed_intent(KeyedWrite("insert", "Account", ({"id": 1},))) is None
    assert keyed_intent(KeyedWrite("insertUntil", "Account", ({"id": 1},))) is None


@pytest.mark.parametrize(
    ("mutation", "kind"),
    [
        ("update", "assignment"),
        ("updateUntil", "assignment"),
        ("delete", "destructive"),
        ("terminate", "destructive"),
        ("terminateUntil", "destructive"),
    ],
)
def test_every_other_keyed_mutation_intends_an_assignment_or_a_destruction(
    mutation: str, kind: str
) -> None:
    intent = keyed_intent(KeyedWrite(mutation, "Account", ({"id": 1},), valid_from="2024-01-01"))  # pyright: ignore[reportArgumentType]
    assert intent is not None
    assert intent.kind == kind
    assert intent.region == ("2024-01-01", None)


@pytest.mark.parametrize(
    ("held", "arriving", "verdict"),
    [
        (_ASSIGNMENT, _ASSIGNMENT, "coalesce"),
        (_ASSIGNMENT, _DESTRUCTIVE, "supersede"),
        (_DESTRUCTIVE, _DESTRUCTIVE, "deduplicate"),
        (_DESTRUCTIVE, _ASSIGNMENT, "incompatible"),
        (SELECTION_INTENT, _ASSIGNMENT, "incompatible"),
        (_ASSIGNMENT, SELECTION_INTENT, "incompatible"),
        (
            WriteIntent(kind="assignment", valid_from="2024-01-01"),
            WriteIntent(kind="assignment", valid_from="2024-06-01"),
            "incompatible",
        ),
    ],
)
def test_the_claim_algebra_answers_one_verdict_per_pair(
    held: WriteIntent, arriving: WriteIntent, verdict: str
) -> None:
    assert admits(held, arriving) == verdict


def test_the_claim_table_holds_what_the_buffer_will_carry() -> None:
    # An unclaimed state admits; a compatible intent replaces what is held,
    # because the merged write is what the flush will carry; a deduplicated or
    # refused one leaves the held claim exactly as it was.
    table = ClaimTable()
    assert table.claim(_STATE, _ASSIGNMENT) == "admit"
    assert table.held(_STATE) == _ASSIGNMENT
    assert table.claim(_STATE, _DESTRUCTIVE) == "supersede"
    assert table.held(_STATE) == _DESTRUCTIVE
    assert table.claim(_STATE, _DESTRUCTIVE) == "deduplicate"
    assert table.claim(_STATE, _ASSIGNMENT) == "incompatible"
    assert table.held(_STATE) == _DESTRUCTIVE
    table.clear()
    assert table.held(_STATE) is None


# --------------------------------------------------------------------------- #
# Coalescing through the real verbs.                                          #
# --------------------------------------------------------------------------- #
def test_two_updates_of_one_state_with_disjoint_assignments_merge_into_one_write() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.update(node.edit(owner="Grace"))

    account_db(port).transact(fn)
    assert _writes(port) == [
        (
            "write",
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? "
                "where id = ? and version = ?"
            ),
            ("Grace", Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_a_repeated_assignment_member_takes_the_later_authored_value() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.update(node.edit(balance=Decimal("150.00")))

    account_db(port).transact(fn)
    assert _writes(port)[0][2] == (Decimal("150.00"), 5, 1, 4)


def test_a_restoring_edit_cancels_the_assignment_already_buffered_for_that_state() -> None:
    # `100 -> 125 -> 100`: the second verb's own effective change set is empty,
    # but it is the caller's last word on `balance`, so it cancels the pending
    # assignment rather than being dropped. What survives names only the key,
    # which is no work at all — no DML, and the observation stays eligible.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        edited = node.edit(balance=Decimal("125.00"))
        tx.update(edited)
        tx.update(edited.edit(balance=Decimal("100.00")))

    account_db(port).transact(fn)
    assert _writes(port) == []


def test_a_restoring_edit_with_nothing_buffered_still_buffers_nothing() -> None:
    # The ordinary net-zero no-op: with no pending assignment to cancel, an edit
    # that nets to zero issues no DML and reaches no buffer at all, exactly as
    # it always has.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")).edit(balance=Decimal("100.00")))

    account_db(port).transact(fn)
    assert _writes(port) == []


def test_a_restoring_edit_of_an_unversioned_source_buffers_nothing() -> None:
    # An unversioned Non-Temporal row observes no state, so there is no claim for
    # a restoration to cancel: the net-zero edit takes the ordinary no-op path and
    # the shared row lock its read holds is all the write it never makes needed.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada"}])

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.update(node.edit(name="Grace").edit(name="Ada"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_a_partial_restore_keeps_the_member_the_later_edit_did_change() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        edited = node.edit(balance=Decimal("125.00"))
        tx.update(edited)
        tx.update(edited.edit(balance=Decimal("100.00"), owner="Grace"))

    account_db(port).transact(fn)
    assert _writes(port) == [
        (
            "write",
            POSTGRES.to_driver_sql(
                "update account set owner = ?, version = ? where id = ? and version = ?"
            ),
            ("Grace", 5, 1, 4),
        )
    ]


def test_an_update_then_a_delete_of_one_state_is_one_delete() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.delete(node)

    account_db(port).transact(fn)
    assert _writes(port) == [
        (
            "write",
            POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"),
            (1, 4),
        )
    ]


def test_identical_destructive_intents_deduplicate() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(node)
        tx.delete(node)

    account_db(port).transact(fn)
    assert len(_writes(port)) == 1


def test_an_assignment_after_a_destructive_intent_is_refused() -> None:
    # No resurrection: the row the assignment would write is going away, and
    # Unit Work invents no order in which both could be true.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(node)
        tx.update(node.edit(balance=Decimal("125.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"
    assert refusal.value.object_key.primary_key == (("id", 1),)


def test_a_temporal_update_and_terminate_over_one_region_is_one_terminate() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(node.edit(value=Decimal("9.00")))
        tx.terminate(node)

    db_for(BALANCE, port).transact(fn)
    assert [op[1] for op in _writes(port)] == [
        POSTGRES.to_driver_sql(
            "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
        )
    ]


def test_temporal_updates_over_different_regions_are_refused() -> None:
    # Two Valid-Time windows compose no interval, so the second verb refuses
    # rather than Unit Work inventing composition semantics.
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        node = tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)).result()
        tx.update_until(node.edit(value=Decimal("9.00")), valid_from=_VALID_FROM, until=_UNTIL)
        tx.update_until(node.edit(value=Decimal("8.00")), valid_from=_OTHER_FROM, until=_UNTIL)

    with pytest.raises(WriteEvidenceError) as refusal:
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"


def test_temporal_updates_over_one_region_merge_into_one_rectangle_split() -> None:
    # The compatible half of the same pair: one region, so the two sparse
    # assignments merge and the split is planned once rather than twice.
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        node = tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)).result()
        tx.update_until(node.edit(value=Decimal("9.00")), valid_from=_VALID_FROM, until=_UNTIL)
        tx.update_until(node.edit(acct_num="B"), valid_from=_VALID_FROM, until=_UNTIL)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert len(_writes(port)) == 4  # close + head + middle + tail, once


def _position_row() -> dict[str, object]:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("100.00"),
        "from_z": _TX_START,
        "thru_z": INFINITY_INSTANT,
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    }


def test_a_participating_read_flushes_the_first_intent_and_frees_the_state() -> None:
    # The remedy the refusal names: the dependent read force-flushes the pending
    # intent, and the fresh read it then runs observes a state nothing claims.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(first)
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(second.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert [op[0] for op in port.ops] == [
        "begin",
        "read",
        "write",
        "read",
        "write",
        "commit",
    ]


# --------------------------------------------------------------------------- #
# Materialized Write Group claims.                                            #
# --------------------------------------------------------------------------- #
def test_a_predicate_group_claims_every_state_it_selected() -> None:
    # The group owns the observations its predicate resolved, and it is one
    # compact indivisible unit — so a later keyed write of a state it selected
    # has nothing to join and is refused without the group being indexed or
    # mutated.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update_where(mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Grace"))
        tx.update(node.edit(balance=Decimal("125.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"


def test_a_keyed_write_of_a_state_the_group_did_not_select_stays_independent() -> None:
    port = RecordingPort(
        row_queue=[
            [dict(_ACCOUNT_ROW)],
            [{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 7}],
        ]
    )

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update_where(mm.Account.where(mm.Account.id == 2), mm.Account.owner.set("Grace"))
        tx.update(node.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert len(_writes(port)) == 2


def test_a_keyed_intent_before_an_overlapping_predicate_write_force_flushes_first() -> None:
    # The reverse order needs no claim: the resolving read force-flushes the
    # buffered keyed write, so the rows the predicate selects are fresh state no
    # pending intent still holds.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.update_where(mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Grace"))

    account_db(port).transact(fn)
    assert [op[0] for op in port.ops] == [
        "begin",
        "read",
        "write",
        "read",
        "write",
        "commit",
    ]


def test_the_locked_read_is_what_a_locking_preference_still_licenses() -> None:
    # The claim seam is strategy-independent: an explicit `locking` preference
    # locks the read and the same two assignments still merge into one write.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.update(node.edit(owner="Grace"))

    account_db(port).transact(fn, concurrency="locking")
    assert [op[1] for op in port.ops if op[0] == "read"] == [FIND_SQL_LOCKED]
    assert len(_writes(port)) == 1


def test_the_default_preference_leaves_the_versioned_read_unlocked() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert [op[1] for op in port.ops if op[0] == "read"] == [FIND_SQL_UNLOCKED]
