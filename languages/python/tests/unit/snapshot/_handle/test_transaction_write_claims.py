"""Write admission and Observed-State Coalescing through the real handles over a
fake port (`m-unit-work`): the choreography a caller performs, refused at the
verb or merged at finalization by the claim algebra
``tests/unit/core/unit_work/test_write_claims.py`` measures as a pure function."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from parallax.conformance.read_models import Person
from parallax.conformance.scripted_clock import FixedClock
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import WriteEvidenceError
from parallax.snapshot import Database, Transaction
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._transact_support import (
    BALANCE,
    FIND_SQL_LOCKED,
    FIND_SQL_UNLOCKED,
    FIXED,
    INFINITY_INSTANT,
    PERSON,
    account_db,
    balance_row,
    db_for,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)

_ACCOUNT_ROW: dict[str, object] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}

_ACCOUNT_READ = Read(rows=[_ACCOUNT_ROW])
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_OTHER_FROM = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _writes(port: ScriptedAdapter) -> list[WriteCall]:
    return [op for op in port.calls if isinstance(op, WriteCall)]


# --------------------------------------------------------------------------- #
# Coalescing through the real verbs.                                          #
# --------------------------------------------------------------------------- #
def test_two_updates_of_one_state_with_disjoint_assignments_merge_into_one_write() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))
        tx.amend(node.edit(owner="Grace"))

    account_db(port).transact(fn)
    assert _writes(port) == [
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? "
                "where id = ? and version = ?"
            ),
            ("Grace", Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_a_repeated_assignment_member_takes_the_later_authored_value() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))
        tx.amend(node.edit(balance=Decimal("150.00")))

    account_db(port).transact(fn)
    assert _writes(port)[0].binds == (Decimal("150.00"), 5, 1, 4)


def test_a_net_equal_chain_across_two_verbs_writes_its_last_value() -> None:
    # `100 -> 125 -> 100`: the second verb restates `balance` at the value its
    # source was read with, which is a literal assignment rather than a
    # cancellation, so the merged write sets it — and, as every surviving
    # versioned update does, advances the version.
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        edited = node.edit(balance=Decimal("125.00"))
        tx.amend(edited)
        tx.amend(edited.edit(balance=Decimal("100.00")))

    account_db(port).transact(fn)
    assert _writes(port) == [
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set balance = ?, version = ? where id = ? and version = ?"
            ),
            (Decimal("100.00"), 5, 1, 4),
        )
    ]


def test_a_net_zero_edit_chain_still_writes_the_member_it_touched() -> None:
    # The touched set is cumulative across the chain and literal: a member set
    # and set back is still assigned, at the value the chain ended on.
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")).edit(balance=Decimal("100.00")))

    account_db(port).transact(fn)
    assert [write.binds for write in _writes(port)] == [(Decimal("100.00"), 5, 1, 4)]


def test_a_net_zero_edit_of_an_unversioned_source_still_writes() -> None:
    # An unversioned Non-Temporal row's write is licensed by the shared row lock
    # its read holds, and a net-zero chain writes its touched member there too.
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.amend(node.edit(name="Grace").edit(name="Ada"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Ada", 1))
    ]


def test_a_later_edit_restating_one_member_writes_both_it_and_its_new_one() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        edited = node.edit(balance=Decimal("125.00"))
        tx.amend(edited)
        tx.amend(edited.edit(balance=Decimal("100.00"), owner="Grace"))

    account_db(port).transact(fn)
    assert _writes(port) == [
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set owner = ?, balance = ?, version = ? "
                "where id = ? and version = ?"
            ),
            ("Grace", Decimal("100.00"), 5, 1, 4),
        )
    ]


def test_an_update_then_a_delete_of_one_state_is_one_delete() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))
        tx.delete(node)

    account_db(port).transact(fn)
    assert _writes(port) == [
        WriteCall(
            POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"), (1, 4)
        )
    ]


def test_identical_destructive_intents_deduplicate() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(node)
        tx.delete(node)

    account_db(port).transact(fn)
    assert len(_writes(port)) == 1


def test_an_assignment_after_a_destructive_intent_is_refused() -> None:
    # No resurrection: the row the assignment would write is going away, and
    # Unit Work invents no order in which both could be true.
    port = ScriptedAdapter(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(node)
        tx.amend(node.edit(balance=Decimal("125.00")))

    with raises_contextualized(WriteEvidenceError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"
    assert refusal.value.object_key.primary_key == (("id", 1),)


def test_a_temporal_update_and_terminate_over_one_region_is_one_terminate() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[balance_row(in_z=_TX_START)]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.amend(node.edit(value=Decimal("9.00")))
        tx.terminate(node)

    db_for(BALANCE, port).transact(fn)
    assert [op.sql for op in _writes(port)] == [
        POSTGRES.to_driver_sql(
            "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
        )
    ]


def _position_at(tx: Transaction, at: dt.datetime) -> WherePosition:
    return tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=at)).result()


def test_temporal_assignments_over_different_windows_compose_in_authored_order() -> None:
    # Two pins of one observed rectangle start two windows; their assignments
    # compose rather than refuse, the later value winning where they overlap,
    # and the rectangle is split once: the close, then the head, the earlier
    # write's own interval, the overlap, and the carried tail.
    port = ScriptedAdapter(
        Transact(Read(rows=[_position_row()]), Read(rows=[_position_row()]), Write(times=5))
    )

    def fn(tx: Transaction) -> None:
        early = _position_at(tx, _VALID_FROM)
        late = _position_at(tx, _OTHER_FROM)
        tx.amend(early.edit(value=Decimal("9.00")), until=_UNTIL)
        tx.amend(late.edit(value=Decimal("8.00")), until=_UNTIL)

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    close, *openings = _writes(port)
    assert close.sql.startswith("update where_position set out_z")
    assert [write.binds[2:5] for write in openings] == [
        (Decimal("100.00"), _TX_START, _VALID_FROM),
        (Decimal("9.00"), _VALID_FROM, _OTHER_FROM),
        (Decimal("8.00"), _OTHER_FROM, _UNTIL),
        (Decimal("100.00"), _UNTIL, INFINITY_INSTANT),
    ]


def test_a_destruction_over_another_window_of_the_same_state_is_refused() -> None:
    # Unequal windows compose only between assignments: a termination whose
    # window differs from an assignment's at the same observed state would apply
    # half of one and half of the other, so the second verb refuses.
    port = ScriptedAdapter(Transact(Read(rows=[_position_row()]), Read(rows=[_position_row()])))

    def fn(tx: Transaction) -> None:
        early = _position_at(tx, _VALID_FROM)
        late = _position_at(tx, _OTHER_FROM)
        tx.amend(early.edit(value=Decimal("9.00")), until=_UNTIL)
        tx.terminate(late, until=_UNTIL)

    with raises_contextualized(WriteEvidenceError) as refusal:
        own_root(
            Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
        ).using_database_login().transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"


def test_a_refused_composition_leaves_the_earlier_write_pending_and_executable() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_position_row()]), Read(rows=[_position_row()]), Write(times=4))
    )

    def fn(tx: Transaction) -> None:
        early = _position_at(tx, _VALID_FROM)
        late = _position_at(tx, _OTHER_FROM)
        tx.amend(early.edit(value=Decimal("9.00")), until=_UNTIL)
        with pytest.raises(WriteEvidenceError) as refusal:
            tx.terminate(late)
        assert refusal.value.code == "write-evidence-already-claimed"

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
    close, *openings = _writes(port)
    assert close.sql.startswith("update where_position set out_z")
    assert [write.binds[2] for write in openings] == [
        Decimal("100.00"),
        Decimal("9.00"),
        Decimal("100.00"),
    ]


def test_temporal_updates_over_one_region_merge_into_one_rectangle_split() -> None:
    # One region, so the two sparse assignments merge and the split is planned
    # once rather than twice.
    port = ScriptedAdapter(Transact(Read(rows=[_position_row()]), Write(times=4)))

    def fn(tx: Transaction) -> None:
        node = _position_at(tx, _VALID_FROM)
        tx.amend(node.edit(value=Decimal("9.00")), until=_UNTIL)
        tx.amend(node.edit(acct_num="B"), until=_UNTIL)

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)
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
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write(), _ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.delete(first)
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(second.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert [type(op) for op in port.calls] == [
        BeginCall,
        ReadCall,
        WriteCall,
        ReadCall,
        WriteCall,
        CommitCall,
    ]


def test_an_unversioned_update_then_delete_of_one_object_is_one_delete() -> None:
    # The object-claimed arm of the same algebra `-022`'s versioned pair proves:
    # the destruction supersedes the assignment buffered before it, so the UPDATE
    # never reaches the wire.
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.amend(node.edit(name="Grace"))
        tx.delete(node)

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("delete from person where id = ?"), (1,))
    ]


def test_identical_unversioned_destructive_intents_deduplicate() -> None:
    # Unclaimed, the pair reaches the batch collapse as two writes of one key and
    # a Key Target's addressed rows are distinct — so what the claim buys here is
    # a legal two-verb sequence reaching a Planned Write at all.
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.delete(node)
        tx.delete(node)

    db_for(PERSON, port).transact(fn)
    assert len(_writes(port)) == 1


def test_an_unversioned_assignment_after_a_destructive_intent_is_refused() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}])))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.delete(node)
        tx.amend(node.edit(name="Grace"))

    with raises_contextualized(WriteEvidenceError) as refusal:
        db_for(PERSON, port).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"
    assert refusal.value.object_key.primary_key == (("id", 1),)


def test_two_unversioned_updates_of_one_object_merge_into_one_write() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.amend(node.edit(name="Grace"))
        tx.amend(node.edit(name="Hopper"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Hopper", 1))
    ]


def test_a_net_equal_chain_of_an_unversioned_object_writes_its_last_value() -> None:
    # `Ada -> Grace -> Ada` across two verbs merges at the object's claim, and the
    # intermediate value never reaches the wire: the last word, equal to what the
    # row holds, is written.
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        edited = node.edit(name="Grace")
        tx.amend(edited)
        tx.amend(edited.edit(name="Ada"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Ada", 1))
    ]


def test_writes_of_two_unversioned_objects_stay_independent_and_batch() -> None:
    # One claim per object, so two objects' deletes are two claims — and they
    # leave coalescing as the ordinary instructions they always were, which is
    # what lets the batch collapse merge them into one set-based statement.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}]), Write(affected=2)
        )
    )

    def fn(tx: Transaction) -> None:
        people = tx.find(Person.where(Person.id.in_([1, 2]))).results()
        for person in people:
            tx.delete(person)

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("delete from person where id in (?, ?)"), (1, 2))
    ]


def test_a_restoring_edit_of_a_value_this_transaction_inserted_cancels_nothing() -> None:
    # The insert-exempt path: a value this transaction buffered an insert of came
    # from no read, so it carries no hint and claims nothing — the insert is the
    # provenance, and same-object coalescing is what would combine the pair. The
    # net-zero chain therefore takes the ordinary no-op path and the INSERT stands
    # alone, carrying the value the caller ended on.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        fresh = Person(id=9, name="Ada")
        tx.insert(fresh)
        tx.amend(fresh.edit(name="Grace").edit(name="Ada"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall(POSTGRES.to_driver_sql("insert into person(id, name) values (?, ?)"), (9, "Ada"))
    ]


# --------------------------------------------------------------------------- #
# Materialized Write Group claims.                                            #
# --------------------------------------------------------------------------- #
def test_a_predicate_group_claims_every_state_it_selected() -> None:
    # The group owns the observations its predicate resolved, and it is one
    # compact indivisible unit — so a later keyed write of a state it selected
    # has nothing to join and is refused without the group being indexed or
    # mutated.
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW], times=2)))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend_where(mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Grace"))
        tx.amend(node.edit(balance=Decimal("125.00")))

    with raises_contextualized(WriteEvidenceError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-evidence-already-claimed"


def test_a_keyed_write_of_a_state_the_group_did_not_select_stays_independent() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=[dict(_ACCOUNT_ROW)]),
            Read(rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 7}]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend_where(mm.Account.where(mm.Account.id == 2), mm.Account.owner.set("Grace"))
        tx.amend(node.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert len(_writes(port)) == 2


def test_a_keyed_intent_before_an_overlapping_predicate_write_force_flushes_first() -> None:
    # The reverse order needs no claim: the resolving read force-flushes the
    # buffered keyed write, so the rows the predicate selects are fresh state no
    # pending intent still holds.
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write(), _ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))
        tx.amend_where(mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Grace"))

    account_db(port).transact(fn)
    assert [type(op) for op in port.calls] == [
        BeginCall,
        ReadCall,
        WriteCall,
        ReadCall,
        WriteCall,
        CommitCall,
    ]


def test_the_locked_read_is_what_a_locking_preference_still_licenses() -> None:
    # The claim seam is strategy-independent: an explicit `locking` preference
    # locks the read and the same two assignments still merge into one write.
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))
        tx.amend(node.edit(owner="Grace"))

    account_db(port).transact(fn, concurrency="locking")
    assert [op.sql for op in port.calls if isinstance(op, ReadCall)] == [FIND_SQL_LOCKED]
    assert len(_writes(port)) == 1


def test_the_default_preference_leaves_the_versioned_read_unlocked() -> None:
    port = ScriptedAdapter(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.amend(node.edit(balance=Decimal("125.00")))

    account_db(port).transact(fn)
    assert [op.sql for op in port.calls if isinstance(op, ReadCall)] == [FIND_SQL_UNLOCKED]
