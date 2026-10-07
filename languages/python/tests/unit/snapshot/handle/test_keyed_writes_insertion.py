"""What an admitted insertion authorizes, through the public verbs over a scripted port.

An insertion's authority belongs to the source it was stated through — the
instance a Typed insert took and every value derived from it afterwards, or the
node a Wire insert answered — never to the key it opened. It survives ordinary
flushes and edits, starts every write it licenses at its own anchor, and ends
with its attempt or the complete removal of what it opened. Each case states the
statements it expects, so the SQL a pending opening flushes as, the coverage a
stored one is read from, and the order a removal-dependent reinsertion runs in
are pinned exactly; `tests/api/test_insertion_authority.py` proves the stored
results against a real database.
"""

from __future__ import annotations

import datetime as dt
import pickle
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.story_models import Wallet
from parallax.conformance.vo_models import (
    CONTACT_MODEL,
    Contact,
    ContactAddress,
    ContactGeo,
    ContactPoint,
)
from parallax.core.base import DocumentValue, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow
from parallax.core.entity import DomainModel
from parallax.core.execution import KeyedWriteValueError
from parallax.core.read_delivery import InvalidData
from parallax.core.unit_work import MissingTargetError, WriteInstructionError
from parallax.snapshot._inspection import insertion_of, snapshot_state_of
from parallax.snapshot.handle import (
    Database,
    Transaction,
    WriteEvidenceError,
)
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.root_ownership import own_root
from tests.unit._transact_support import (
    ACCOUNT,
    BALANCE,
    FIXED,
    INFINITY_INSTANT,
    PERSON,
    db_for,
    deadlock,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)

_JAN, _MAR, _MAY, _JUN, _AUG, _SEP, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 6, 8, 9, 12)
)


def _position(value: str = "100.00") -> WherePosition:
    return WherePosition(id=1, acct_num="A", value=Decimal(value))


def _transact(port: ScriptedAdapter, fn: Callable[[Transaction], object]) -> None:
    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn)


def _writes(port: ScriptedAdapter) -> list[WriteCall]:
    return [call for call in port.calls if isinstance(call, WriteCall)]


def _opened(port: ScriptedAdapter) -> list[tuple[object, object, object]]:
    """Each inserted Bitemporal row as its value and Valid-Time bounds."""
    return [
        (call.binds[2], call.binds[3], call.binds[4])
        for call in _writes(port)
        if call.sql.startswith("insert into")
    ]


def _rectangle(start: dt.datetime, end: object, value: str = "100.00") -> MappingRow:
    """A current row of WherePosition 1 this attempt opened."""
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal(value),
        "from_z": start,
        "thru_z": end,
        "in_z": FIXED,
        "out_z": INFINITY_INSTANT,
    }


def _read_at(tx: Transaction, at: dt.datetime) -> WherePosition:
    return tx.find(WherePosition.where(WherePosition.id == 1).as_of(valid_time=at)).result()


# --------------------------------------------------------------------------- #
# A pending opening takes each edit its insertion authorizes over only the      #
# coverage it opens: a bound inside it splits it, a bound at or beyond its own  #
# end changes the whole of it, and nothing extends it. Every edit starts at the #
# insertion's anchor, and the flush inserts only what survives.                #
# --------------------------------------------------------------------------- #
_OPENING_MATRIX: tuple[
    tuple[str, dt.datetime | None, dt.datetime | None, tuple[tuple[str, object, object], ...]],
    ...,
] = (
    ("unbounded-plain", None, None, (("150.00", _JAN, INFINITY_INSTANT),)),
    ("unbounded-until", None, _JUN, (("150.00", _JAN, _JUN), ("100.00", _JUN, INFINITY_INSTANT))),
    ("finite-plain", _SEP, None, (("150.00", _JAN, _SEP),)),
    ("finite-until-inside", _SEP, _JUN, (("150.00", _JAN, _JUN), ("100.00", _JUN, _SEP))),
    ("finite-until-its-end", _SEP, _SEP, (("150.00", _JAN, _SEP),)),
    ("finite-until-beyond", _SEP, _DEC, (("150.00", _JAN, _SEP),)),
)


@pytest.mark.parametrize("representation", ["typed", "wire"])
@pytest.mark.parametrize(
    ("opening_end", "until", "expected"),
    [case[1:] for case in _OPENING_MATRIX],
    ids=[case[0] for case in _OPENING_MATRIX],
)
def test_a_pending_opening_takes_each_edit_over_only_the_coverage_it_opens(
    opening_end: dt.datetime | None,
    until: dt.datetime | None,
    expected: tuple[tuple[str, object, object], ...],
    representation: str,
) -> None:
    port = ScriptedAdapter(Transact(Write(times=len(expected))))

    def fn(tx: Transaction) -> None:
        bounds: dict[str, Any] = {} if opening_end is None else {"until": opening_end}
        edit: dict[str, Any] = {} if until is None else {"until": until}
        if representation == "typed":
            opened = _position()
            tx.insert(opened, valid_from=_JAN, **bounds)
            tx.update(opened.edit(value=Decimal("150.00")), **edit)
            return
        node = tx.wire.insert(
            "WherePosition", {"id": 1, "acctNum": "A", "value": "100.00"}, valid_from=_JAN, **bounds
        )
        tx.wire.update(node, {"value": "150.00"}, **edit)

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert"] * len(expected)
    assert _opened(port) == [(Decimal(value), start, end) for value, start, end in expected]


def test_an_edit_bounded_at_or_before_the_anchor_is_refused_and_leaves_the_opening() -> None:
    # The bound is judged against the start the edit takes from its insertion,
    # so a bound that does not follow the anchor is refused before anything
    # changes, and a valid edit afterwards still transforms the whole opening.
    port = ScriptedAdapter(Transact(Write(times=2)))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_MAR, until=_SEP)
        for bound in (_JAN, _MAR):
            with pytest.raises(WriteInstructionError):
                tx.update(opened.edit(value=Decimal("150.00")), until=bound)
        tx.update(opened.edit(value=Decimal("175.00")), until=_JUN)

    _transact(port, fn)
    assert _opened(port) == [
        (Decimal("175.00"), _MAR, _JUN),
        (Decimal("100.00"), _JUN, _SEP),
    ]


def test_repeated_bounded_edits_start_at_the_anchor_rather_than_at_a_split() -> None:
    port = ScriptedAdapter(Transact(Write(times=2)))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN, until=_DEC)
        tx.update(opened.edit(value=Decimal("150.00")), until=_MAY)
        tx.update(opened.edit(value=Decimal("175.00")), until=_AUG)

    _transact(port, fn)
    assert _opened(port) == [
        (Decimal("175.00"), _JAN, _AUG),
        (Decimal("100.00"), _AUG, _DEC),
    ]


def test_a_literal_reset_of_a_pending_opening_writes_the_reset_value() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN)
        tx.update(opened.edit(value=Decimal("150.00")))
        tx.update(opened.edit(value=Decimal("100.00")))

    _transact(port, fn)
    assert _opened(port) == [(Decimal("100.00"), _JAN, INFINITY_INSTANT)]


def test_a_resubmitted_draft_reasserts_its_whole_touched_set() -> None:
    # A draft's assignments are cumulative: extending an earlier draft after a
    # later edit was submitted reasserts the earlier draft's value beside the
    # member it adds.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN)
        draft = opened.edit(value=Decimal("150.00"))
        tx.update(draft)
        tx.update(opened.edit(value=Decimal("200.00")))
        tx.update(draft.edit(acct_num="B"))

    _transact(port, fn)
    (insert,) = _writes(port)
    assert insert.binds[:3] == (1, "B", Decimal("150.00"))


def test_an_edit_over_coverage_a_pending_destruction_removed_is_refused() -> None:
    # Terminating the opening up to May leaves only its tail pending. An edit
    # starts at the anchor, January, inside the destroyed window, so it would
    # resurrect coverage: it is refused, and the tail is all the flush inserts.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN)
        tx.terminate(opened, until=_MAY)
        with pytest.raises(WriteEvidenceError) as refused:
            tx.update(opened.edit(value=Decimal("150.00")))
        assert refused.value.code == "write-evidence-already-claimed"

    _transact(port, fn)
    assert _opened(port) == [(Decimal("100.00"), _MAY, INFINITY_INSTANT)]


# --------------------------------------------------------------------------- #
# Authority belongs to the admitted source, not to the key.                     #
# --------------------------------------------------------------------------- #
def _refused_as_not_stored(write: Callable[[], object]) -> None:
    with pytest.raises(KeyedWriteValueError) as refused:
        write()
    assert refused.value.code == "write-value-not-stored"


def test_a_draft_derived_before_the_insertion_carries_no_authority() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = mm.Person(id=9, name="Newton")
        earlier = opened.edit(name="Hooke")
        tx.insert(opened)
        _refused_as_not_stored(lambda: tx.update(earlier))
        tx.update(opened.edit(name="Grace"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Grace"))
    ]


def test_an_independently_built_value_of_the_inserted_key_carries_no_authority() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx.insert(mm.Person(id=9, name="Newton"))
        _refused_as_not_stored(lambda: tx.update(mm.Person(id=9, name="Newton").edit(name="X")))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Newton"))
    ]


def test_a_refused_insertion_grants_nothing() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        refused = _position()
        with pytest.raises(WriteInstructionError):
            tx.insert(refused, valid_from=_SEP, until=_JAN)
        _refused_as_not_stored(lambda: tx.update(refused.edit(value=Decimal("1.00"))))

    _transact(port, fn)
    assert _writes(port) == []


@pytest.mark.parametrize("ending", ["commit", "rollback"])
def test_an_insertion_authority_ends_with_its_attempt(ending: str) -> None:
    port = ScriptedAdapter(Transact(Write()) if ending == "commit" else Transact(), Transact())
    db = db_for(PERSON, port)
    opened = mm.Person(id=9, name="Newton")

    def insert(tx: Transaction) -> None:
        tx.insert(opened)
        if ending == "rollback":
            raise RuntimeError("abandon")

    if ending == "commit":
        db.transact(insert)
    else:
        with raises_contextualized(RuntimeError):
            db.transact(insert)
    later = opened.edit(name="Grace")

    def edit(tx: Transaction) -> None:
        _refused_as_not_stored(lambda: tx.update(later))

    db.transact(edit)
    assert len(_writes(port)) == (1 if ending == "commit" else 0)


def test_a_reinsertion_rebinds_only_the_instance_it_takes() -> None:
    # A pending insert-then-terminate pair cancels and retires the first
    # insertion; inserting the same instance again grants it a fresh authority,
    # while a draft derived under the first keeps the retired one.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(opened)
        draft = opened.edit(value=Decimal("5.00"))
        tx.terminate(opened)
        tx.insert(opened)
        _refused_as_not_stored(lambda: tx.update(draft))
        tx.update(opened.edit(value=Decimal("2.00")))

    db_for(BALANCE, port).transact(fn)
    (insert,) = _writes(port)
    assert insert.sql.startswith("insert into balance")
    assert Decimal("2.00") in insert.binds


def test_converting_a_wire_insertion_node_loses_its_authority() -> None:
    # The authority rides the node privately: a plain mapping copy and a pickle
    # round trip are ordinary data, which no keyed verb takes as a source.
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        node = tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        for converted in (dict(node), pickle.loads(pickle.dumps(node))):
            assert converted == node
            with pytest.raises(WriteInstructionError):
                tx.wire.update(cast("Any", converted), {"name": "Grace"})
        tx.wire.update(node, {"name": "Grace"})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Grace"))
    ]


def test_an_inserted_instance_pickles_as_domain_data_without_its_authority() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = mm.Person(id=9, name="Newton")
        tx.insert(opened)
        copied = pickle.loads(pickle.dumps(opened))
        assert copied == opened
        _refused_as_not_stored(lambda: tx.update(copied.edit(name="Grace")))

    db_for(PERSON, port).transact(fn)
    assert len(_writes(port)) == 1


# --------------------------------------------------------------------------- #
# After its insert flushes, the insertion source still edits what it opened:   #
# the stored coverage is read from the anchor and the rows the attempt opened   #
# are revised or removed in place, as an observed write's would be.            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_an_insertion_source_edits_its_stored_bitemporal_coverage_after_a_helper_read(
    concurrency: str,
) -> None:
    # The flush reads the coverage from the insertion's anchor — under the
    # shared row lock where the strategy is Locking — and revises the row the
    # attempt opened in place: its kept tail moves its start to the bound, and
    # the head it split off opens beside it.
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.update(opened.edit(value=Decimal("150.00")), until=_JUN)

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED))
    ).using_database_login().transact(fn, concurrency=cast("Any", concurrency))
    coverage = [call for call in port.calls if isinstance(call, ReadCall)][1]
    lock = " for share of t0" if concurrency == "locking" else ""
    assert coverage.sql.endswith(
        "where t0.id = %s and t0.thru_z > %s and t0.from_z < %s and t0.out_z = %s" + lock
    )
    assert coverage.binds == (1, _JAN, _JUN, INFINITY_INSTANT)
    revision, head = _writes(port)[1:]
    gate = " and in_z = %s" if concurrency == "optimistic" else ""
    assert revision.sql == (
        "update where_position set from_z = %s where id = %s and thru_z = %s and out_z = %s" + gate
    )
    assert revision.binds[:4] == (_JUN, 1, "infinity", "infinity")
    assert head.binds[2:5] == (Decimal("150.00"), _JAN, _JUN)


def test_an_insertion_source_revises_its_stored_transaction_time_row_after_a_helper_read() -> None:
    row: MappingRow = {
        "bal_id": 9,
        "acct_num": "Z",
        "val": Decimal("1.00"),
        "in_z": FIXED,
        "out_z": INFINITY_INSTANT,
    }
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write()))

    def fn(tx: Transaction) -> None:
        opened = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(opened)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.update(opened.edit(value=Decimal("2.00")))

    db_for(BALANCE, port).transact(fn)
    coverage = [call for call in port.calls if isinstance(call, ReadCall)][1]
    assert coverage.sql.endswith("where t0.bal_id = %s and t0.out_z = %s")
    assert _writes(port)[1] == WriteCall(
        "update balance set val = %s where bal_id = %s and out_z = %s and in_z = %s",
        (Decimal("2.00"), 9, "infinity", FIXED),
    )


def _account_row(version: int) -> MappingRow:
    return {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": version}


def test_an_insertion_source_advances_its_stored_version_after_each_flush() -> None:
    # The attempt wrote every revision of the row it inserted, so the version
    # each later write advances from is known without reading it.
    port = ScriptedAdapter(
        Transact(
            Write(), Read(rows=[_account_row(1)]), Write(), Read(rows=[_account_row(2)]), Write()
        )
    )

    def fn(tx: Transaction) -> None:
        opened = mm.Account(id=7, owner="Newton", balance=Decimal("5.00"))
        tx.insert(opened)
        tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.update(opened.edit(balance=Decimal("6.00")))
        tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.update(opened.edit(balance=Decimal("7.00")))

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port)[1:] == [
        WriteCall(
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("6.00"), 2, 7, 1),
        ),
        WriteCall(
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("7.00"), 3, 7, 2),
        ),
    ]


@pytest.mark.parametrize("insertion_first", [True, False], ids=["insertion-first", "read-first"])
def test_an_insertion_source_and_a_read_of_the_same_version_compose_into_one_update(
    insertion_first: bool,
) -> None:
    port = ScriptedAdapter(Transact(Write(), Read(rows=[_account_row(1)]), Write()))

    def fn(tx: Transaction) -> None:
        opened = mm.Account(id=7, owner="Newton", balance=Decimal("5.00"))
        tx.insert(opened)
        read = tx.find(mm.Account.where(mm.Account.id == 7)).result()
        writes = [
            lambda: tx.update(opened.edit(balance=Decimal("6.00"))),
            lambda: tx.update(read.edit(owner="Hooke")),
        ]
        for write in writes if insertion_first else reversed(writes):
            write()

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port)[1:] == [
        WriteCall(
            "update account set owner = %s, balance = %s, version = %s "
            "where id = %s and version = %s",
            ("Hooke", Decimal("6.00"), 2, 7, 1),
        )
    ]


@pytest.mark.parametrize("insertion_first", [True, False], ids=["insertion-first", "read-first"])
def test_insertion_and_observed_assignments_compose_over_unequal_windows_after_a_flush(
    insertion_first: bool,
) -> None:
    # Opening [March, September); a read at May flushes it and yields an
    # observed source. The insertion source assigns 150 until June and the
    # observed source 175 from May until August; the later-authored write wins
    # where the windows overlap, and the opening's own value survives past it.
    port = ScriptedAdapter(Transact(Write(), Read(rows=[_rectangle(_MAR, _SEP)]), Write(times=3)))

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_MAR, until=_SEP)
        observed = _read_at(tx, _MAY)
        writes = [
            lambda: tx.update(opened.edit(value=Decimal("150.00")), until=_JUN),
            lambda: tx.update(observed.edit(value=Decimal("175.00")), until=_AUG),
        ]
        for write in writes if insertion_first else reversed(writes):
            write()

    _transact(port, fn)
    overlap = Decimal("175.00") if insertion_first else Decimal("150.00")
    middle_end = _AUG if insertion_first else _JUN
    revision = _writes(port)[1]
    assert revision.sql.startswith("update where_position set from_z = %s")
    assert revision.binds[0] == _AUG
    assert _opened(port)[1:] == (
        [(Decimal("150.00"), _MAR, _MAY), (overlap, _MAY, middle_end)]
        if insertion_first
        else [(Decimal("150.00"), _MAR, _JUN), (Decimal("175.00"), _JUN, _AUG)]
    )


def test_an_insertion_source_whose_anchor_was_removed_fails_its_flush() -> None:
    # A read at January terminates the stored opening until March, so coverage
    # survives only from March. The insertion's authority still starts at
    # January, where nothing is current any more: the edit's flush reads its
    # coverage, finds none at the anchor, and fails as a missing target — which
    # dooms the attempt rather than shifting the anchor.
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[_rectangle(_JAN, INFINITY_INSTANT)]),
            Write(),
            Read(rows=[_rectangle(_MAR, INFINITY_INSTANT)]),
            Read(rows=[_rectangle(_MAR, INFINITY_INSTANT)]),
        )
    )

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_JAN)
        tx.terminate(_read_at(tx, _JAN), until=_MAR)
        _read_at(tx, _MAR)
        tx.update(opened.edit(value=Decimal("150.00")))

    with raises_contextualized(MissingTargetError):
        _transact(port, fn)
    assert len(_writes(port)) == 2
    assert RollbackCall() in port.calls


# --------------------------------------------------------------------------- #
# Complete removal of what an insertion opened admits a fresh insertion of the  #
# object, which executes after that removal whatever the batching, and never    #
# revives the first insertion's authority.                                      #
# --------------------------------------------------------------------------- #
def test_a_reinsertion_after_a_complete_stored_removal_executes_after_it() -> None:
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        draft = first.edit(value=Decimal("1.00"))
        tx.terminate(first)
        second = _position("200.00")
        tx.insert(second, valid_from=_JAN)
        _refused_as_not_stored(lambda: tx.update(draft))

    _transact(port, fn)
    removal, insert = _writes(port)[1:]
    assert removal.sql == (
        "delete from where_position where id = %s and thru_z = %s and out_z = %s and in_z = %s"
    )
    assert insert.binds[2:5] == (Decimal("200.00"), _JAN, INFINITY_INSTANT)


def test_a_reinsertion_at_identical_coordinates_never_revives_the_first() -> None:
    # The second insertion opens exactly the address, Valid-Time start and
    # Transaction Instant the first did, and still carries an authority of its
    # own: the first's source stays refused after the second's rows exist.
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(
        Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2), Read(rows=[row]))
    )

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.terminate(first)
        second = _position()
        tx.insert(second, valid_from=_JAN)
        _read_at(tx, _MAR)
        _refused_as_not_stored(lambda: tx.update(first.edit(value=Decimal("1.00"))))

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert", "delete", "insert"]


def test_a_failed_removal_withholds_the_reinsertion_that_depends_on_it() -> None:
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(affected=0)))

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.terminate(first)
        tx.insert(_position("200.00"), valid_from=_JAN)

    with raises_contextualized(Exception):
        _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert", "delete"]
    assert RollbackCall() in port.calls


def test_a_failed_reinsertion_after_its_removal_rolls_the_attempt_back() -> None:
    row = _rectangle(_JAN, INFINITY_INSTANT)
    duplicate = DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
    port = ScriptedAdapter(
        Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(), Write(raises=duplicate))
    )

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.terminate(first)
        tx.insert(_position("200.00"), valid_from=_JAN)

    with raises_contextualized(DatabaseError):
        _transact(port, fn)
    assert RollbackCall() in port.calls


# --------------------------------------------------------------------------- #
# A readless predicate write keeps a pending opening from the writes after it:  #
# the opening executes before the barrier, so only what those writes destroy    #
# removes it, and only a removal of all of it admits a fresh insertion.         #
# --------------------------------------------------------------------------- #
_BARRIER_MODEL = DomainModel(WherePosition, Wallet)


def _barrier(tx: Transaction) -> None:
    tx.update_where(Wallet.where(Wallet.balance < Decimal("2.00")), Wallet.owner.set("Low"))


def _refused_as_a_repeat(write: Callable[[], object]) -> None:
    with pytest.raises(KeyedWriteValueError) as refused:
        write()
    assert refused.value.code == "write-value-already-stored"


class _Abandoned(Exception):
    pass


@pytest.mark.parametrize("opening_end", [None, _SEP], ids=["unbounded", "finite"])
def test_an_opening_a_barrier_kept_back_and_removed_whole_admits_a_reinsertion(
    opening_end: dt.datetime | None,
) -> None:
    opened = _rectangle(_JAN, INFINITY_INSTANT if opening_end is None else opening_end)
    port = ScriptedAdapter(Transact(Write(times=2), Read(rows=[opened]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        first = _position()
        if opening_end is None:
            tx.insert(first, valid_from=_JAN)
        else:
            tx.insert(first, valid_from=_JAN, until=opening_end)
        _barrier(tx)
        tx.terminate(first)
        tx.insert(_position("200.00"), valid_from=_JAN)
        _refused_as_not_stored(lambda: tx.update(first.edit(value=Decimal("1.00"))))

    db_for(_BARRIER_MODEL, port).transact(fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == [
        "insert",
        "update",
        "delete",
        "insert",
    ]
    assert _opened(port) == [
        (Decimal("100.00"), _JAN, INFINITY_INSTANT if opening_end is None else opening_end),
        (Decimal("200.00"), _JAN, INFINITY_INSTANT),
    ]


def test_an_opening_a_barrier_kept_back_and_removed_in_part_refuses_a_reinsertion() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _barrier(tx)
        tx.terminate(first, until=_MAR)
        _refused_as_a_repeat(lambda: tx.insert(_position("200.00"), valid_from=_JAN))
        raise _Abandoned

    with raises_contextualized(_Abandoned):
        db_for(_BARRIER_MODEL, port).transact(fn)


def test_a_removal_before_a_pending_reinsertion_never_counts_against_it() -> None:
    # The first insertion's stored coverage is removed before the reinsertion
    # opens; only what the writes after the reinsertion destroy removes it, and
    # those leave its coverage from March standing.
    row = _rectangle(_MAR, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row])))

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_MAR)
        _read_at(tx, _MAR)
        tx.terminate(first)
        second = _position("200.00")
        tx.insert(second, valid_from=_JAN)
        _barrier(tx)
        tx.terminate(second, until=_MAR)
        _refused_as_a_repeat(lambda: tx.insert(_position("300.00"), valid_from=_JAN))
        raise _Abandoned

    with raises_contextualized(_Abandoned):
        db_for(_BARRIER_MODEL, port).transact(fn)


def _balance_row(key: int, in_z: dt.datetime, value: str = "1.00") -> MappingRow:
    return {
        "bal_id": key,
        "acct_num": "Z",
        "val": Decimal(value),
        "in_z": in_z,
        "out_z": INFINITY_INSTANT,
    }


def test_an_assignment_an_owned_row_already_holds_revises_nothing() -> None:
    # The stored row the insertion opened already holds the very value the
    # edit assigns, and a row the attempt opened has no history to record, so
    # revising it in place would change nothing: the edit's unit emits no
    # statement after its coverage read.
    row = _balance_row(9, FIXED)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row])))

    def fn(tx: Transaction) -> None:
        opened = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(opened)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.update(opened.edit(acct_num="Z"))

    db_for(BALANCE, port).transact(fn)
    assert len(_writes(port)) == 1


def test_a_reinsertion_after_its_removal_flushed_is_a_first_opening() -> None:
    row = _balance_row(9, FIXED)
    neighbour = _balance_row(2, _JAN)
    port = ScriptedAdapter(
        Transact(
            Write(), Read(rows=[row]), Read(rows=[row]), Write(), Read(rows=[neighbour]), Write()
        )
    )

    def fn(tx: Transaction) -> None:
        first = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(first)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.terminate(first)
        tx.find(mm.Balance.where(mm.Balance.id == 2)).result()
        tx.insert(mm.Balance(id=9, acct_num="Z", value=Decimal("2.00")))

    db_for(BALANCE, port).transact(fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert", "delete", "insert"]


def test_a_transaction_time_reinsertion_runs_after_the_removal_it_depends_on() -> None:
    row = _balance_row(9, FIXED)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        first = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(first)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.terminate(first)
        tx.insert(mm.Balance(id=9, acct_num="Z", value=Decimal("2.00")))

    db_for(BALANCE, port).transact(fn)
    removal, insert = _writes(port)[1:]
    assert removal.sql == "delete from balance where bal_id = %s and out_z = %s and in_z = %s"
    assert Decimal("2.00") in insert.binds


def test_a_cancelled_reinsertion_leaves_the_next_one_depending_on_the_same_removal() -> None:
    # The second insertion depended on the pending removal of the first; a
    # termination cancels it while still pending, which leaves the first's
    # stored row and its pending removal standing, so a third insertion again
    # depends on that removal and runs after it.
    row = _balance_row(9, FIXED)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        first = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(first)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.terminate(first)
        second = mm.Balance(id=9, acct_num="Z", value=Decimal("2.00"))
        tx.insert(second)
        tx.terminate(second)
        _refused_as_not_stored(lambda: tx.update(second.edit(value=Decimal("4.00"))))
        tx.insert(mm.Balance(id=9, acct_num="Z", value=Decimal("3.00")))

    db_for(BALANCE, port).transact(fn)
    removal, insert = _writes(port)[1:]
    assert removal.sql.startswith("delete from balance")
    assert Decimal("3.00") in insert.binds


def test_a_pending_assignment_alone_leaves_a_stored_insertion_standing() -> None:
    row = _balance_row(9, FIXED)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write()))

    def fn(tx: Transaction) -> None:
        first = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(first)
        tx.find(mm.Balance.where(mm.Balance.id == 9)).result()
        tx.update(first.edit(value=Decimal("2.00")))
        with pytest.raises(KeyedWriteValueError) as refused:
            tx.insert(mm.Balance(id=9, acct_num="Z", value=Decimal("3.00")))
        assert refused.value.code == "write-value-already-stored"

    db_for(BALANCE, port).transact(fn)
    assert len(_writes(port)) == 2


def test_a_bounded_removal_reaching_every_end_the_insertion_opened_is_complete() -> None:
    # The insertion opened [January, September) and a sibling object's
    # insertion opened its own row beside it. Terminating the first until
    # September reaches the latest end any of its rows has, so it removes all of
    # it and a reinsertion of that object is admitted, while the sibling is
    # untouched.
    first_row = _rectangle(_JAN, _SEP)
    port = ScriptedAdapter(
        Transact(
            Write(times=2),
            Read(rows=[first_row]),
            Read(rows=[first_row]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN, until=_SEP)
        tx.insert(WherePosition(id=2, acct_num="B", value=Decimal("5.00")), valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.terminate(first, until=_SEP)
        tx.insert(_position("200.00"), valid_from=_MAR)

    _transact(port, fn)
    removal, insert = _writes(port)[2:]
    assert removal.sql.startswith("delete from where_position")
    assert insert.binds[2:5] == (Decimal("200.00"), _MAR, INFINITY_INSTANT)


def test_a_removal_composed_of_several_pending_writes_admits_a_reinsertion() -> None:
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.terminate(first)
        tx.terminate(first)
        tx.insert(_position("200.00"), valid_from=_JAN)

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert", "delete", "insert"]


def test_removing_a_row_no_insertion_opened_leaves_the_insertions_standing() -> None:
    # The attempt rewrites a stored object twice — its second write removes the
    # row its first opened, which no insertion tags — while an insertion of
    # another object stands; that insertion's source still edits its own row.
    stored = _balance_row(1, _JAN, "5.00")
    rewritten = _balance_row(1, FIXED, "6.00")
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[stored]),
            Write(times=2),
            Read(rows=[rewritten]),
            Read(rows=[_balance_row(9, FIXED)]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        opened = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(opened)
        other = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(other.edit(value=Decimal("6.00")))
        tx.terminate(tx.find(mm.Balance.where(mm.Balance.id == 1)).result())
        tx.update(opened.edit(value=Decimal("2.00")))

    db_for(BALANCE, port).transact(fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == [
        "insert",
        "update",
        "insert",
        "update",
        "delete",
    ]


def test_an_inserted_value_keeps_the_node_state_a_classified_read_gave_it() -> None:
    # A classified read hands back a hydrated root with no Read Origin; a copy
    # of it completed by an edit is a value no read published, so it may be
    # inserted. The insertion's authority is bound beside the node state that
    # value already carries, which stays the node's own — its pin and views
    # still answer, and it still refuses to pickle.
    stored: dict[str, DocumentValue] = {
        "street": "Main",
        "geo": {"country": "DE", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [],
    }
    port = ScriptedAdapter(
        Transact(
            Read(rows=[{"id": 1, "name": "Ada", "address": PresentDocument(stored)}]),
            Write(),
        )
    )
    complete = ContactAddress(
        street="Main",
        city="Berlin",
        geo=ContactGeo(country="DE", point=ContactPoint(lat=1.0, lon=2.0)),
        phones=(),
    )

    def fn(tx: Transaction) -> None:
        published = tx.find(Contact.where(Contact.id == 1)).checked().result()
        assert isinstance(published, InvalidData)
        value = cast("Contact", published.data).edit(address=complete)
        node = snapshot_state_of(value)
        assert node is not None and node.source is None
        tx.insert(value)
        assert snapshot_state_of(value) is node
        assert insertion_of(value) is not None
        with pytest.raises(pickle.PicklingError):
            pickle.dumps(value)
        tx.update(value.edit(name="Grace"))

    db_for(CONTACT_MODEL, port).transact(fn)
    (insert,) = _writes(port)
    assert "Grace" in insert.binds


def test_a_retry_admits_the_insertion_afresh_and_expires_the_first_attempts_drafts() -> None:
    port = ScriptedAdapter(Transact(Write(), commit=deadlock()), Transact(Write()))
    opened = mm.Person(id=9, name="Newton")
    drafts: list[mm.Person] = []

    def fn(tx: Transaction) -> None:
        if drafts:
            _refused_as_not_stored(lambda: tx.update(drafts[0]))
        tx.insert(opened)
        drafts.append(opened.edit(name="Hooke"))

    db_for(PERSON, port).transact(fn)
    assert len(drafts) == 2
    assert len(_writes(port)) == 2


def test_composition_spends_the_observed_source_and_not_the_insertions_authority() -> None:
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[_rectangle(_MAR, _SEP)]),
            Write(times=3),
            Read(rows=[_rectangle(_MAR, _MAY, "150.00")]),
            Read(rows=[_rectangle(_MAR, _MAY, "150.00")]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        opened = _position()
        tx.insert(opened, valid_from=_MAR, until=_SEP)
        observed = _read_at(tx, _MAY)
        tx.update(opened.edit(value=Decimal("150.00")), until=_JUN)
        tx.update(observed.edit(value=Decimal("175.00")), until=_AUG)
        _read_at(tx, _MAR)
        with pytest.raises(WriteEvidenceError) as refused:
            tx.update(observed.edit(value=Decimal("1.00")), until=_AUG)
        assert refused.value.code == "write-evidence-consumed"
        tx.update(opened.edit(value=Decimal("125.00")), until=_MAY)

    _transact(port, fn)
    last = _writes(port)[-1]
    assert last.sql.startswith("update where_position set value = %s")
    assert last.binds[0] == Decimal("125.00")


def test_a_reinsertion_at_identical_coordinates_revives_no_earlier_observation() -> None:
    # A read of the first insertion's row predates its removal, so the
    # removal's completion invalidates it; the second insertion opens a row at
    # the same address, start and instant, and only a read of that row writes.
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[row]),
            Read(rows=[row]),
            Write(times=2),
            Read(rows=[row]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        earlier = _read_at(tx, _MAR)
        tx.terminate(first)
        tx.insert(_position("200.00"), valid_from=_JAN)
        fresh = _read_at(tx, _MAR)
        with pytest.raises(WriteEvidenceError) as refused:
            tx.update(earlier.edit(value=Decimal("1.00")))
        assert refused.value.code == "write-evidence-consumed"
        tx.update(fresh.edit(value=Decimal("250.00")))

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == [
        "insert",
        "delete",
        "insert",
        "update",
        "insert",
    ]


def test_a_pending_assignment_alone_leaves_a_stored_bitemporal_insertion_standing() -> None:
    row = _rectangle(_JAN, INFINITY_INSTANT)
    port = ScriptedAdapter(Transact(Write(), Read(rows=[row]), Read(rows=[row]), Write()))

    def fn(tx: Transaction) -> None:
        first = _position()
        tx.insert(first, valid_from=_JAN)
        _read_at(tx, _MAR)
        tx.update(first.edit(value=Decimal("150.00")))
        with pytest.raises(KeyedWriteValueError) as refused:
            tx.insert(_position("200.00"), valid_from=_JAN)
        assert refused.value.code == "write-value-already-stored"

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == ["insert", "update"]


def test_removing_a_bitemporal_row_no_insertion_opened_leaves_the_insertions_standing() -> None:
    # Position 9 is inserted; position 1 existed before the attempt and is
    # rewritten twice, the second write removing the successor the first
    # opened, which no insertion tags. Position 9's insertion still stands and
    # still refuses a repeat.
    stored = {**_rectangle(_JAN, INFINITY_INSTANT), "in_z": _JAN}
    rewritten = _rectangle(_MAR, INFINITY_INSTANT, "150.00")
    port = ScriptedAdapter(
        Transact(
            Write(),
            Read(rows=[stored]),
            Write(times=3),
            Read(rows=[rewritten]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        tx.insert(WherePosition(id=9, acct_num="B", value=Decimal("5.00")), valid_from=_JAN)
        tx.update(_read_at(tx, _MAR).edit(value=Decimal("150.00")))
        tx.terminate(_read_at(tx, _MAR))
        with pytest.raises(KeyedWriteValueError) as refused:
            tx.insert(WherePosition(id=9, acct_num="B", value=Decimal("6.00")), valid_from=_JAN)
        assert refused.value.code == "write-value-already-stored"

    _transact(port, fn)
    assert [call.sql.split(" ", 1)[0] for call in _writes(port)] == [
        "insert",
        "update",
        "insert",
        "insert",
        "delete",
    ]
