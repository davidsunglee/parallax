"""The Wire write interface (`python.md` §5, `m-unit-work`).

``tx.wire``'s keyed and predicate verb families, driven through the real handles
over a recording port. Three questions are asked here and nowhere else: that a
Wire verb lowers through the SAME pipeline its Typed peer does, that its static
judgements all precede any evidence question, and that a Wire write and a Typed
write of one object meet in one claim algebra rather than in two.

What a Wire READ publishes is `test_wire_reads.py`'s subject; the claim algebra
itself is `test_write_claims.py`'s. What lives here is the ingress.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import pickle
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    CONTACT,
    FIXED,
    INFINITY_INSTANT,
    PAYMENT,
    PERSON,
    WHERE_POSITION_META,
    balance_row,
    db_for,
)

from _support import mirrored_models as mm
from _support.db_port import (
    Read,
    ReadCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance import vo_models as vo
from parallax.core import Attr, DomainModel, Entity, ValueObject, attr
from parallax.core.base import InstantError, PresentDocument
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.predicate import CanonicalDocumentError
from parallax.core.unit_work import FixedClock, WriteRejectedError, instructions
from parallax.snapshot import connect
from parallax.snapshot.handle import (
    Database,
    KeyedWriteValueError,
    Transaction,
    TransactionTimePinReadOnlyError,
    WireEntity,
    WriteEvidenceError,
)

_ACCOUNT_ROW: Row = {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4}
_PERSON_ROW: Row = {"id": 1, "name": "Ada"}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_NAIVE_INSTANT = dt.datetime(2024, 7, 1)  # no tzinfo: not an instant at all
_OTHER_FROM = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)

_ACCOUNT_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Account",
    "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 1}},
}

_ACCOUNT_READ = Read(rows=[_ACCOUNT_ROW])
_PERSON_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Person",
    "predicate": {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
}
_BALANCE_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Balance",
    "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
    "temporal": {"transaction-time": {"asOf": "latest"}},
}
_POSITION_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.WherePosition",
    "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
    "temporal": {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"asOf": "latest"},
    },
}
_PERSON_TARGET: dict[str, object] = {
    "entity": "parallax.compatibility.Person",
    "predicate": {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
}
# The one document-mapped mirror, whose `address` occurrence is what an
# assignment replaces whole.
_TRAVELER_ROW: Row = {
    "id": 1,
    "payload": PresentDocument({"address": {"city": "Oslo", "geo": {"country": "NO"}}, "tags": []}),
}
_TRAVELER_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Traveler",
    "predicate": {"eq": {"attr": "parallax.compatibility.Traveler.id", "value": 1}},
}
_CONTACT_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Contact",
    "predicate": {"eq": {"attr": "parallax.compatibility.Contact.id", "value": 1}},
}


class Sample(Entity, table="sample", namespace="parallax.compatibility"):
    """A LOCAL entity declaring a plain, assignable `timestamp` member.

    Every corpus `timestamp` is a framework-owned axis bound, which no write may
    assign, so an authored instant reaches the member judgement only through a
    model declared here.
    """

    id: Attr[int] = attr(primary_key=True)
    taken: Attr[dt.datetime]


SAMPLE_META = DomainModel(Sample)


class RosterMember(ValueObject):
    label: Attr[str | None]


class Roster(Entity, table="wire_roster", namespace="parallax.compatibility"):
    """A LOCAL entity whose TOP-LEVEL `many` occurrence has a Column of its own.

    Every corpus `many` these suites reach is either nested inside a `one` or
    document-resident, and a top-level `many` under `Columns` is where an opening
    row's canonical member set differs from its payload's authored keys.
    """

    id: Attr[int] = attr(primary_key=True)
    members: Attr[tuple[RosterMember, ...]]


ROSTER_META = DomainModel(Roster)

_SAMPLE_ROW: Row = {"id": 1, "taken": dt.datetime(2024, 5, 1, tzinfo=dt.UTC)}
_SAMPLE_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Sample",
    "predicate": {"eq": {"attr": "parallax.compatibility.Sample.id", "value": 1}},
}
_SAMPLE_TARGET: dict[str, object] = {
    "entity": "parallax.compatibility.Sample",
    "predicate": {"eq": {"attr": "parallax.compatibility.Sample.id", "value": 1}},
}
# `datetime.min` fourteen hours east of UTC: an accepted wire spelling naming an
# instant before the first one a canonical UTC spelling can write.
_UNSPELLABLE_INSTANT = "0001-01-01T00:00:00.000000+14:00"
_POSITION_TARGET: dict[str, object] = {
    "entity": "parallax.compatibility.WherePosition",
    "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
}


def _position_row() -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("200.00"),
        "from_z": _TX_START,
        "thru_z": INFINITY_INSTANT,
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    }


def _writes(port: ScriptedPort) -> list[WriteCall]:
    return [op for op in port.calls if isinstance(op, WriteCall)]


def _reads(port: ScriptedPort) -> list[ReadCall]:
    return [op for op in port.calls if isinstance(op, ReadCall)]


def _node(tx: Transaction, query: dict[str, object]) -> WireEntity:
    return tx.wire.find(query).result()


def _standalone(db: Database, query: dict[str, object]) -> WireEntity:
    return db.wire.find(query).result()


# --------------------------------------------------------------------------- #
# Canonical lowering: every verb reaches the shared pipeline, and a Wire write #
# emits exactly what its Typed peer emits for the same intent.                #
# --------------------------------------------------------------------------- #
def test_a_wire_update_emits_what_the_typed_update_emits() -> None:
    wire_port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))

    def wire(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _ACCOUNT_QUERY), {"balance": "125.00"})

    db_for(ACCOUNT, wire_port).transact(wire)

    typed_port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))

    def typed(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))

    db_for(ACCOUNT, typed_port).transact(typed)

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_occurrence_assignment_emits_what_the_typed_one_emits() -> None:
    # The authored occurrence restates `city` and omits the stored `geo`, so the
    # write it emits REMOVES `geo` — an assignment replaces its subtree whole.
    # The two interfaces reach that verdict through different machinery, the
    # Wire lane against the source it read and the Typed lane against its Change
    # Record, and one authored value must still get one answer from both.
    wire_port = ScriptedPort(Transact(Read(rows=[dict(_TRAVELER_ROW)]), Write()))

    def wire(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _TRAVELER_QUERY), {"address": {"city": "Oslo"}})

    db_for(mm.DOCUMENT_LAYOUT_MODEL, wire_port).transact(wire)

    typed_port = ScriptedPort(Transact(Read(rows=[dict(_TRAVELER_ROW)]), Write()))

    def typed(tx: Transaction) -> None:
        node = tx.find(mm.Traveler.where(mm.Traveler.id == 1)).result()
        tx.update(node.edit(address=mm.TravelerAddress(city="Oslo")))

    db_for(mm.DOCUMENT_LAYOUT_MODEL, typed_port).transact(typed)

    assert len(_writes(wire_port)) == 1
    assert _writes(wire_port) == _writes(typed_port)


def test_authoring_a_null_over_a_member_the_document_omitted_emits_one_answer() -> None:
    # The stored occurrence holds `city` and no `geo`, and both authored values
    # spell `geo` as an explicit null — a change the write must make, because an
    # omitted key and a stored null are two documents. It is one answer only
    # because the two lanes weigh it against ONE observed value: the Wire node
    # publishes the presence the document carried, exactly as the hydrated Typed
    # value keeps it, so neither lane can read the absence as a null already
    # there and eliminate the write.
    stored: Row = {"id": 1, "payload": PresentDocument({"address": {"city": "Oslo"}, "tags": []})}
    wire_port = ScriptedPort(Transact(Read(rows=[dict(stored)]), Write()))

    def wire(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _TRAVELER_QUERY), {"address": {"city": "Oslo", "geo": None}})

    db_for(mm.DOCUMENT_LAYOUT_MODEL, wire_port).transact(wire)

    typed_port = ScriptedPort(Transact(Read(rows=[dict(stored)]), Write()))

    def typed(tx: Transaction) -> None:
        node = tx.find(mm.Traveler.where(mm.Traveler.id == 1)).result()
        tx.update(node.edit(address=mm.TravelerAddress(city="Oslo", geo=None)))

    db_for(mm.DOCUMENT_LAYOUT_MODEL, typed_port).transact(typed)

    assert len(_writes(wire_port)) == 1
    assert _writes(wire_port) == _writes(typed_port)


def test_authoring_an_occurrence_short_of_a_nested_many_emits_one_answer() -> None:
    # The stored document omits `phones`, which a `many` has no absent state for:
    # the read publishes `[]` there and storing this authored occurrence would too.
    # Both authored values therefore state exactly the value the row holds, and the
    # two lanes agree on the only answer that leaves state as it is — no DML, no
    # milestone, no clock. A Wire author who omits the key spells the same zero the
    # Typed author's unpopulated tuple does.
    stored: Row = {
        "id": 1,
        "name": "Ada",
        "address": PresentDocument(
            {
                "street": "S",
                "city": "C",
                "geo": {"country": "NO", "point": {"lat": 1.0, "lon": 2.0}},
            }
        ),
    }
    authored = {
        "street": "S",
        "city": "C",
        "geo": {"country": "NO", "point": {"lat": 1.0, "lon": 2.0}},
    }
    wire_port = ScriptedPort(Transact(Read(rows=[copy.deepcopy(stored)])))

    def wire(tx: Transaction) -> None:
        node = tx.wire.find(_CONTACT_QUERY).result()
        assert _address(node)["phones"] == []
        tx.wire.update(node, {"address": authored})

    db_for(CONTACT, wire_port).transact(wire)

    typed_port = ScriptedPort(Transact(Read(rows=[copy.deepcopy(stored)])))

    def typed(tx: Transaction) -> None:
        node = tx.find(vo.Contact.where(vo.Contact.id == 1)).result()
        tx.update(
            node.edit(
                address=vo.ContactAddress(
                    street="S",
                    city="C",
                    geo=vo.ContactGeo(country="NO", point=vo.ContactPoint(lat=1.0, lon=2.0)),
                )
            )
        )

    db_for(CONTACT, typed_port).transact(typed)

    assert _writes(wire_port) == []
    assert _writes(typed_port) == []


def test_an_insert_answers_the_nested_many_its_own_buffered_row_stores() -> None:
    # The document an insert composes carries `[]` at a nested `many` the payload
    # left out, so the node it answers has to carry it too: a caller revising that
    # node compares its own authored value against what was published, and a key
    # the answer omitted while the row stored it would make the next write differ
    # from the row it addresses.
    port = ScriptedPort(Transact(Write()))

    def body(tx: Transaction) -> None:
        opened = tx.wire.insert(
            "parallax.compatibility.Contact",
            {
                "id": 7,
                "name": "Grace",
                "address": {
                    "street": "S",
                    "city": "C",
                    "geo": {"country": "NO", "point": {"lat": 1.0, "lon": 2.0}},
                },
            },
        )
        assert _address(opened)["phones"] == []

    db_for(CONTACT, port).transact(body)
    stored = cast("JsonDocument", _writes(port)[0].binds[2])
    assert cast("dict[str, Any]", stored.value)["phones"] == []


def test_an_insert_answers_the_top_level_many_its_own_buffered_row_stores() -> None:
    # A Create Payload may omit a top-level `many` — omission and `[]` are one zero
    # state — and the row the insert composes carries `[]` there whether the
    # occurrence has a Column of its own or rides a Structured Column. Both layouts
    # are asserted because the two lowerings supply that zero independently, and
    # what the node answers has to be the row under either: a caller revising a key
    # the answer omitted while the row stored it would author a change against a
    # value the row does not hold.
    columns_port = ScriptedPort(Transact(Write()))

    def columns(tx: Transaction) -> None:
        opened = tx.wire.insert("parallax.compatibility.Roster", {"id": 7})
        assert opened["members"] == []

    db_for(ROSTER_META, columns_port).transact(columns)
    assert _bound_documents(columns_port) == [[]]

    document_port = ScriptedPort(Transact(Write()))

    def document(tx: Transaction) -> None:
        opened = tx.wire.insert("parallax.compatibility.Traveler", {"id": 7})
        assert opened["tags"] == []

    db_for(mm.DOCUMENT_LAYOUT_MODEL, document_port).transact(document)
    assert _bound_documents(document_port) == [{"tags": []}]


def _bound_documents(port: ScriptedPort) -> list[object]:
    return [
        bind.value for op in _writes(port) for bind in op.binds if isinstance(bind, JsonDocument)
    ]


def _address(node: WireEntity) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", dict(node)["address"])


def test_a_wire_delete_emits_what_the_typed_delete_emits() -> None:
    wire_port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))
    db_for(ACCOUNT, wire_port).transact(lambda tx: tx.wire.delete(_node(tx, _ACCOUNT_QUERY)))

    typed_port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))
    db_for(ACCOUNT, typed_port).transact(
        lambda tx: tx.delete(tx.find(mm.Account.where(mm.Account.id == 1)).result())
    )

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_insert_emits_what_the_typed_insert_emits() -> None:
    wire_port = ScriptedPort(Transact(Write()))
    db_for(ACCOUNT, wire_port).transact(
        lambda tx: tx.wire.insert(
            "parallax.compatibility.Account",
            {"id": 7, "owner": "Newton", "balance": "5.00"},
        )
    )

    typed_port = ScriptedPort(Transact(Write()))
    db_for(ACCOUNT, typed_port).transact(
        lambda tx: tx.insert(mm.Account(id=7, owner="Newton", balance=Decimal("5.00")))
    )

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_terminate_closes_the_observed_milestone() -> None:
    port = ScriptedPort(Transact(Read(rows=[balance_row(in_z=_TX_START)]), Write()))
    db_for(BALANCE, port).transact(lambda tx: tx.wire.terminate(_node(tx, _BALANCE_QUERY)))

    assert len(_writes(port)) == 1
    sql = _writes(port)[0].sql
    assert sql.startswith("update balance set out_z")


def test_a_wire_update_until_splits_the_observed_rectangle() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row()]), Write(times=4)))

    def fn(tx: Transaction) -> None:
        tx.wire.update_until(
            _node(tx, _POSITION_QUERY),
            {"value": "300.00"},
            valid_from=_VALID_FROM,
            until=_UNTIL,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    kinds = [op.sql.split()[0] for op in _writes(port)]
    assert kinds == ["update", "insert", "insert", "insert"]


def test_a_wire_terminate_until_closes_and_reopens_the_flanks() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row()]), Write(times=3)))

    def fn(tx: Transaction) -> None:
        tx.wire.terminate_until(_node(tx, _POSITION_QUERY), valid_from=_VALID_FROM, until=_UNTIL)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    kinds = [op.sql.split()[0] for op in _writes(port)]
    assert kinds == ["update", "insert", "insert"]


def test_a_wire_insert_until_opens_one_bounded_rectangle() -> None:
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx.wire.insert_until(
            "parallax.compatibility.WherePosition",
            {"id": 2, "acctNum": "B", "value": "10.00"},
            valid_from=_VALID_FROM,
            until=_UNTIL,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    assert [op.sql.split()[0] for op in _writes(port)] == ["insert"]


def test_a_wire_predicate_delete_over_an_unversioned_target_is_readless() -> None:
    port = ScriptedPort(Transact(Write()))
    db_for(PERSON, port).transact(lambda tx: tx.wire.delete_where(_PERSON_TARGET))

    assert _reads(port) == []
    assert _writes(port) == [WriteCall("delete from person where id = %s", (1,))]


def test_a_wire_predicate_update_lowers_its_assignments_canonically() -> None:
    port = ScriptedPort(Transact(Write()))
    db_for(PERSON, port).transact(
        lambda tx: tx.wire.update_where(_PERSON_TARGET, {"name": "Grace"})
    )

    assert _writes(port) == [WriteCall("update person set name = %s where id = %s", ("Grace", 1))]


def test_a_wire_predicate_terminate_over_a_temporal_target_materializes() -> None:
    port = ScriptedPort(Transact(Read(rows=[balance_row(in_z=_TX_START)]), Write()))
    db_for(BALANCE, port).transact(
        lambda tx: tx.wire.terminate_where(
            {
                "entity": "parallax.compatibility.Balance",
                "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
            }
        )
    )

    assert len(_reads(port)) == 1
    assert len(_writes(port)) == 1


def test_the_bounded_predicate_verbs_reach_the_rectangle_split() -> None:
    for verb, expected in (("update_until_where", 4), ("terminate_until_where", 3)):
        port = ScriptedPort(Transact(Read(rows=[_position_row()]), Write(times=expected)))
        target: dict[str, object] = {
            "entity": "parallax.compatibility.WherePosition",
            "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
        }

        def fn(tx: Transaction, verb: str = verb, target: dict[str, object] = target) -> None:
            if verb == "update_until_where":
                tx.wire.update_until_where(
                    target, {"value": "300.00"}, valid_from=_VALID_FROM, until=_UNTIL
                )
            else:
                tx.wire.terminate_until_where(target, valid_from=_VALID_FROM, until=_UNTIL)

        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
        assert len(_writes(port)) == expected


# --------------------------------------------------------------------------- #
# A keyed source is a Parallax Wire read result, and nothing else.            #
# --------------------------------------------------------------------------- #
def _lost_provenance(node: WireEntity) -> list[object]:
    """Every way a caller can hold the same data and no longer hold the source."""
    return [
        dict(node),
        {"id": 1, "owner": "Ada", "balance": "100.00", "version": 4},
        json.loads(json.dumps(node)),
        pickle.loads(pickle.dumps(node)),
    ]


def test_a_mapping_that_lost_its_provenance_is_no_keyed_source() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        for candidate in _lost_provenance(node):
            with pytest.raises(instructions.WriteInstructionError, match="Parallax Wire read"):
                tx.wire.update(cast("WireEntity", candidate), {"balance": "125.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_copy_of_a_published_node_keeps_its_provenance() -> None:
    # An immutable value's copy IS the value, so the claim travels with it —
    # the Wire counterpart of `Entity.edit` transferring a Typed node's claim.
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(copy.deepcopy(node), {"balance": "125.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert len(_writes(port)) == 1


def test_none_and_a_non_mapping_are_refused_as_keyed_sources() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        for candidate in (None, 7, "Account"):
            with pytest.raises(instructions.WriteInstructionError):
                tx.wire.delete(cast("WireEntity", candidate))

    db_for(ACCOUNT, port).transact(fn)


# --------------------------------------------------------------------------- #
# Static validation precedes the strategy and its evidence, always.           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("changes", "error", "match"),
    [
        ({"id": 2}, instructions.WriteInstructionError, "primary-key"),
        ({"version": 9}, instructions.WriteInstructionError, "framework-owned"),
        ({"nope": 1}, instructions.WriteInstructionError, "undeclared member"),
        ({"passport": {}}, instructions.WriteInstructionError, "undeclared member"),
        ({"owner": 5}, instructions.InstructionRejectedError, "type-mismatch"),
    ],
)
def test_an_illegal_wire_assignment_is_refused_statically(
    changes: dict[str, object], error: type[Exception], match: str
) -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        with pytest.raises(error, match=match):
            tx.wire.update(_node(tx, _ACCOUNT_QUERY), changes)

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_temporal_axis_member_is_not_assignable() -> None:
    port = ScriptedPort(Transact(Read(rows=[balance_row(in_z=_TX_START)])))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
            tx.wire.update(_node(tx, _BALANCE_QUERY), {"txStart": "2024-01-01T00:00:00Z"})

    db_for(BALANCE, port).transact(fn)


def test_an_illegal_assignment_beats_unusable_evidence() -> None:
    # A standalone source of an effective-Locking target has no usable evidence
    # AND the change names a member no write may assign: the static verdict is
    # the one a caller sees, because nothing about concurrency has been asked yet.
    port = ScriptedPort(Read(rows=[dict(_PERSON_ROW)]), Transact())
    db = db_for(PERSON, port)
    standalone = _standalone(db, _PERSON_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="primary-key"):
            tx.wire.update(standalone, {"id": 2})

    db.transact(fn)
    assert _writes(port) == []


def test_a_reversed_window_is_refused_before_any_member_is_measured() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row()])))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="valid_from < until"):
            tx.wire.update_until(
                _node(tx, _POSITION_QUERY),
                {"value": "300.00"},
                valid_from=_UNTIL,
                until=_VALID_FROM,
            )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert _writes(port) == []


def test_a_bounded_verb_states_its_window_as_a_pair() -> None:
    # Half a window states nothing, and reading the absent bound as "unbounded"
    # would buffer a rectangle the caller never asked for. Which bound is missing
    # is asked of the VERB rather than of the other bound, because the instruction
    # build is not always downstream: the restoring change set below buffers no
    # instruction at all, so a window this seam waves through is a window nothing
    # else ever judges.
    account = ScriptedPort(Transact(_ACCOUNT_READ))
    position = ScriptedPort(Transact(Read(rows=[_position_row()])))

    def absent_valid_from(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="valid_from is absent"):
            tx.wire.update_until(
                _node(tx, _ACCOUNT_QUERY),
                {"balance": "125.00"},
                valid_from=cast("dt.datetime", None),
                until=_UNTIL,
            )

    def absent_until(tx: Transaction) -> None:
        node = _node(tx, _POSITION_QUERY)
        with pytest.raises(instructions.WriteInstructionError, match="until is absent"):
            tx.wire.update_until(
                node,
                {"value": node["value"]},
                valid_from=_VALID_FROM,
                until=cast("dt.datetime", None),
            )
        with pytest.raises(instructions.WriteInstructionError, match="until is absent"):
            tx.wire.terminate_until(node, valid_from=_VALID_FROM, until=cast("dt.datetime", None))

    db_for(ACCOUNT, account).transact(absent_valid_from)
    Database.connect(position, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(absent_until)
    assert _writes(account) == []
    assert _writes(position) == []


def test_a_bound_carries_the_refusal_of_whichever_rule_it_broke() -> None:
    # A bound the target's temporality does not admit is the verb's own verdict
    # on caller input, so it carries the static refusal every other one does. A
    # bound that is no instant broke `m-core`'s rule instead, and keeps that
    # module's classification — one input, one classification, at every boundary.
    # A value of no datetime type at all is the same rule as a naive datetime:
    # both are answered rather than left to leak out of instant normalization.
    port = ScriptedPort(Transact(Read(rows=[_position_row()])))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _POSITION_QUERY)
        with pytest.raises(InstantError, match="naive datetime"):
            tx.wire.update(node, {"value": "300.00"}, valid_from=_NAIVE_INSTANT)
        with pytest.raises(InstantError, match="no `timestamp`"):
            tx.wire.update(node, {"value": "300.00"}, valid_from=cast("dt.datetime", "2024-07-01"))
        with pytest.raises(InstantError, match="no `timestamp`"):
            tx.wire.update_until(
                node,
                {"value": "300.00"},
                valid_from=_VALID_FROM,
                until=cast("dt.datetime", "2024-11-01"),
            )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert _writes(port) == []


def test_an_instant_no_canonical_spelling_writes_is_refused_at_every_ingress() -> None:
    # A member VALUE is judged before it is buffered, and for a `timestamp`
    # awareness is not membership: this spelling decodes into an aware
    # `datetime` whose instant no UTC one holds, so the value space has no
    # member for it and neither does any Wire Value. Buffering it would leave an
    # instruction every later encode overflows on — the stored document, the
    # Wire read of what was written, the bind — with the verb long returned.
    #
    # Serialized values are decoded at Wire ingress, so every shape preserves
    # the typed-literal decoder's exact out-of-space classification.
    keyed = ScriptedPort(Transact(Read(rows=[dict(_SAMPLE_ROW)])))
    inserted = ScriptedPort(Transact())
    selected = ScriptedPort(Transact())

    def update(tx: Transaction) -> None:
        with pytest.raises(instructions.InstructionRejectedError, match="out-of-space"):
            tx.wire.update(_node(tx, _SAMPLE_QUERY), {"taken": _UNSPELLABLE_INSTANT})

    def insert(tx: Transaction) -> None:
        with pytest.raises(instructions.InstructionRejectedError, match="out-of-space"):
            tx.wire.insert(
                "parallax.compatibility.Sample", {"id": 2, "taken": _UNSPELLABLE_INSTANT}
            )

    def update_where(tx: Transaction) -> None:
        with pytest.raises(instructions.InstructionRejectedError, match="out-of-space"):
            tx.wire.update_where(_SAMPLE_TARGET, {"taken": _UNSPELLABLE_INSTANT})

    for port, fn in ((keyed, update), (inserted, insert), (selected, update_where)):
        Database.connect(port, SAMPLE_META, clock=FixedClock(FIXED)).transact(fn)
        assert _writes(port) == []


def test_a_non_temporal_target_takes_no_valid_from() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="takes no valid_from"):
            tx.wire.update(_node(tx, _ACCOUNT_QUERY), {"balance": "125.00"}, valid_from=_VALID_FROM)

    db_for(ACCOUNT, port).transact(fn)


def test_a_predicate_target_carries_exactly_entity_and_predicate() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="exactly `entity`"):
            tx.wire.delete_where({**_PERSON_TARGET, "limit": 1})
        with pytest.raises(instructions.WriteInstructionError, match="exactly `entity`"):
            tx.wire.delete_where({"entity": "parallax.compatibility.Person"})
        with pytest.raises(instructions.WriteInstructionError, match="non-empty entity name"):
            tx.wire.delete_where({"entity": "", "predicate": {"all": {}}})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


@pytest.mark.parametrize("changes", [["balance"], [], 0, "", None])
def test_a_change_set_that_is_not_a_document_is_refused(changes: object) -> None:
    # The falsy spellings are the interesting half, `None` among them: read as
    # "no changes stated" they would answer a malformed call with a silent no-op
    # instead of a refusal. No argument states that intent to an update verb —
    # its signature requires the document, and the verbs that name no member are
    # the destructive and close ones, which take no change set at all.
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update(_node(tx, _ACCOUNT_QUERY), cast("dict[str, object]", changes))

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_every_update_verb_requires_the_change_document_its_signature_states() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row()])))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _POSITION_QUERY)
        none_changes = cast("dict[str, object]", None)
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update(node, none_changes, valid_from=_VALID_FROM)
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update_until(node, none_changes, valid_from=_VALID_FROM, until=_UNTIL)
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update_where(_POSITION_TARGET, none_changes, valid_from=_VALID_FROM)
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update_until_where(
                _POSITION_TARGET, none_changes, valid_from=_VALID_FROM, until=_UNTIL
            )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert _writes(port) == []


def test_a_malformed_change_set_is_judged_before_the_source_is_required() -> None:
    # Both arguments are wrong, and the one answered is the one no other input
    # is needed to judge: whether a document was stated at all needs neither the
    # source's provenance nor the Entity that source names.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.update(cast("WireEntity", {}), cast("dict[str, object]", []))

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_tuple_is_not_a_wire_array_the_predicate_algebra_accepts() -> None:
    # Capture copies caller input; it does not translate its spellings. A tuple
    # rewritten as a list would make this verb accept an operand list the
    # canonical predicate serde refuses for the identical document.
    port = ScriptedPort(Transact(Write()))
    operands = (
        {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
        {"eq": {"attr": "parallax.compatibility.Person.name", "value": "Ada"}},
    )
    target: dict[str, object] = {
        "entity": "parallax.compatibility.Person",
        "predicate": {"and": {"operands": operands}},
    }

    def fn(tx: Transaction) -> None:
        with pytest.raises(CanonicalDocumentError, match="operands"):
            tx.wire.delete_where(target)
        tx.wire.delete_where({**target, "predicate": {"and": {"operands": list(operands)}}})

    db_for(PERSON, port).transact(fn)
    assert len(_writes(port)) == 1


def test_an_insert_payload_that_is_not_a_document_is_refused() -> None:
    # The second call states neither a payload nor an Entity this model declares,
    # and the one answered is the payload: whether a document was stated needs
    # nothing from the model, so it leads the spelling an insert has to resolve.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.insert("parallax.compatibility.Person", cast("dict[str, object]", [("id", 9)]))
        with pytest.raises(instructions.WriteInstructionError, match="document of names"):
            tx.wire.insert("Unknown", cast("dict[str, object]", []))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_a_malformed_predicate_is_judged_before_anything_the_model_decides() -> None:
    # A selection's shape runs to the bottom of its predicate, so a node
    # `m-predicate`'s algebra does not admit is that module's refusal rather than
    # whatever the model would have said about the Entity or the assignments
    # standing beside it. The envelope around the node stays the verb's own.
    port = ScriptedPort(Transact())
    malformed: dict[str, object] = {"entity": "Unknown", "predicate": {"nonsense": {}}}

    def fn(tx: Transaction) -> None:
        with pytest.raises(CanonicalDocumentError, match="unknown predicate node"):
            tx.wire.delete_where(malformed)
        with pytest.raises(CanonicalDocumentError, match="unknown predicate node"):
            tx.wire.update_where(
                {**malformed, "entity": "parallax.compatibility.Person"},
                {"undeclared": 1},
            )
        with pytest.raises(instructions.WriteInstructionError, match="must be a mapping"):
            tx.wire.delete_where({**_PERSON_TARGET, "predicate": []})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_an_empty_change_document_is_a_keyed_no_op_and_a_predicate_refusal() -> None:
    # `{}` is a document naming no member, never an absent argument, and what it
    # states differs by family. A keyed update addresses one row whose values its
    # source published, so naming none is the ordinary no-op. A selection has no
    # published values to be a no-op against, and its change set lowers to the
    # canonical assignment algebra, whose list must name at least one assignment.
    keyed = ScriptedPort(Transact(_ACCOUNT_READ))
    predicate = ScriptedPort(Transact())

    def keyed_fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _ACCOUNT_QUERY), {})

    def predicate_fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="MUST carry `assignments`"):
            tx.wire.update_where(_PERSON_TARGET, {})

    db_for(ACCOUNT, keyed).transact(keyed_fn)
    db_for(PERSON, predicate).transact(predicate_fn)
    assert _writes(keyed) == []
    assert _writes(predicate) == []


def test_a_document_key_that_is_not_a_name_is_refused() -> None:
    # Every walk downstream reads a document's keys as names — sorting them into
    # a refusal message among them — so a key that is not one is refused at the
    # verb rather than reaching the comparison that cannot order it.
    port = ScriptedPort(Transact(Read(rows=[dict(_PERSON_ROW)])))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="keyed by names"):
            tx.wire.insert(
                "parallax.compatibility.Person",
                cast("dict[str, object]", {"id": 9, "name": "Newton", 3: "x"}),
            )
        with pytest.raises(instructions.WriteInstructionError, match="keyed by names"):
            tx.wire.update(_node(tx, _PERSON_QUERY), cast("dict[str, object]", {3: "x"}))
        with pytest.raises(instructions.WriteInstructionError, match="keyed by names"):
            tx.wire.delete_where(cast("dict[str, object]", {**_PERSON_TARGET, 3: "x"}))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_a_document_that_contains_itself_is_refused() -> None:
    port = ScriptedPort(Transact())
    data: dict[str, Any] = {"id": 9, "name": "Newton"}
    data["self"] = data
    target: dict[str, Any] = dict(_PERSON_TARGET)
    target["predicate"] = {"and": {"operands": [target]}}

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="contains itself"):
            tx.wire.insert("parallax.compatibility.Person", data)
        with pytest.raises(instructions.WriteInstructionError, match="contains itself"):
            tx.wire.delete_where(target)

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_an_insert_refuses_a_value_a_read_published() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        with pytest.raises(KeyedWriteValueError) as exc_info:
            tx.wire.insert("parallax.compatibility.Account", node)
        assert exc_info.value.code == "write-value-already-stored"

    db_for(ACCOUNT, port).transact(fn)


def test_an_insert_refuses_a_framework_owned_member() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
            tx.wire.insert(
                "parallax.compatibility.Account",
                {"id": 7, "owner": "Newton", "balance": "5.00", "version": 3},
            )

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_an_unresolvable_entity_spelling_is_refused_at_the_verb() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="unknown entity"):
            tx.wire.insert("parallax.compatibility.Nope", {"id": 7})

    db_for(ACCOUNT, port).transact(fn)


def test_a_bare_entity_spelling_resolves_when_one_entity_carries_it() -> None:
    # `insert` names its Entity by the reference-position rule every write
    # target resolves through, so an unambiguous bare local name reaches the
    # same Entity the canonical spelling does; a shared one refuses instead.
    port = ScriptedPort(Transact(Write()))
    db_for(PERSON, port).transact(lambda tx: tx.wire.insert("Person", {"id": 9, "name": "Newton"}))

    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Newton"))
    ]


def test_a_finite_transaction_time_pinned_source_is_read_only() -> None:
    port = ScriptedPort(Transact(Read(rows=[balance_row(in_z=_TX_START)])))
    pinned: dict[str, object] = {
        **_BALANCE_QUERY,
        "temporal": {"transaction-time": {"asOf": "2024-03-01T00:00:00.000000Z"}},
    }

    def fn(tx: Transaction) -> None:
        with pytest.raises(TransactionTimePinReadOnlyError):
            tx.wire.terminate(_node(tx, pinned))

    db_for(BALANCE, port).transact(fn)
    assert _writes(port) == []


# --------------------------------------------------------------------------- #
# Evidence: what a Wire source licenses under each Concurrency Strategy.      #
# --------------------------------------------------------------------------- #
def test_an_unversioned_participating_wire_source_licenses_an_ungated_write() -> None:
    port = ScriptedPort(Transact(Read(rows=[dict(_PERSON_ROW)]), Write()))

    def fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _PERSON_QUERY), {"name": "Grace"})

    db_for(PERSON, port).transact(fn)

    assert _reads(port)[0].sql.endswith("for share of t0")
    assert _writes(port) == [WriteCall("update person set name = %s where id = %s", ("Grace", 1))]


def test_a_standalone_unversioned_wire_source_has_no_usable_evidence() -> None:
    port = ScriptedPort(Read(rows=[dict(_PERSON_ROW)]), Transact())
    db = db_for(PERSON, port)
    standalone = _standalone(db, _PERSON_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(standalone, {"name": "Grace"})
        assert exc_info.value.code == "write-evidence-unavailable"

    db.transact(fn)
    assert _writes(port) == []


def test_a_standalone_versioned_wire_source_supplies_its_own_gate() -> None:
    port = ScriptedPort(_ACCOUNT_READ, Transact(Write()))
    db = db_for(ACCOUNT, port)
    standalone = _standalone(db, _ACCOUNT_QUERY)

    db.transact(lambda tx: tx.wire.update(standalone, {"balance": "125.00"}))

    assert len(_reads(port)) == 1
    assert _writes(port) == [
        WriteCall(
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_explicit_locking_refuses_a_standalone_versioned_wire_source() -> None:
    port = ScriptedPort(_ACCOUNT_READ, Transact())
    db = db_for(ACCOUNT, port)
    standalone = _standalone(db, _ACCOUNT_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(standalone, {"balance": "125.00"})
        assert exc_info.value.code == "write-evidence-unavailable"

    db.transact(fn, concurrency="locking")
    assert _writes(port) == []


def test_a_wire_source_whose_evidence_a_flush_spent_is_refused() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write(), _ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        # The dependent read force-flushes, which spends the claim the write carried.
        tx.wire.find(_ACCOUNT_QUERY)
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(node, {"balance": "150.00"})
        assert exc_info.value.code == "write-evidence-consumed"

    db_for(ACCOUNT, port).transact(fn)


def test_two_wire_intents_over_different_regions_are_refused_synchronously() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row()]), Write(times=4)))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _POSITION_QUERY)
        tx.wire.update_until(node, {"value": "300.00"}, valid_from=_VALID_FROM, until=_UNTIL)
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update_until(node, {"value": "400.00"}, valid_from=_OTHER_FROM, until=_UNTIL)
        assert exc_info.value.code == "write-evidence-already-claimed"

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)


def test_a_wire_verb_refuses_before_any_io() -> None:
    port = ScriptedPort(Transact())
    db = Database.connect(cast("DbPort", port), ACCOUNT, clock=FixedClock(FIXED))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError):
            tx.wire.update(cast("WireEntity", {"id": 1}), {"balance": "1.00"})

    db.transact(fn)


# --------------------------------------------------------------------------- #
# Coalescing, restoration, and the no-op — including across representations.  #
# --------------------------------------------------------------------------- #
def test_two_wire_assignments_of_one_state_merge_with_the_later_value_winning() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.wire.update(node, {"balance": "150.00", "owner": "Grace"})

    db_for(ACCOUNT, port).transact(fn)

    assert len(_writes(port)) == 1
    assert _writes(port)[0].binds[:2] == ("Grace", Decimal("150.00"))


def test_a_wire_assignment_equal_to_what_the_read_published_is_a_no_op() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": node["balance"], "owner": node["owner"]})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_wire_restore_chain_across_two_verbs_emits_nothing() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.wire.update(node, {"balance": "100.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_typed_assignment_a_wire_verb_restores_emits_nothing() -> None:
    # Both sources are taken BEFORE either write, because a participating read
    # force-flushes: read-your-own-writes is what a mixed chain has to work
    # inside, not around.
    port = ScriptedPort(Transact(Read(rows=[_ACCOUNT_ROW], times=2)))

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.update(typed.edit(balance=Decimal("125.00")))
        tx.wire.update(node, {"balance": "100.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_wire_assignment_a_typed_verb_restores_emits_nothing() -> None:
    port = ScriptedPort(Transact(Read(rows=[_ACCOUNT_ROW], times=2)))

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.update(typed.edit(balance=Decimal("125.00")).edit(balance=Decimal("100.00")))

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_typed_and_a_wire_assignment_of_one_object_merge_in_authored_order() -> None:
    port = ScriptedPort(Transact(Read(rows=[_ACCOUNT_ROW], times=2), Write()))

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.update(typed.edit(balance=Decimal("125.00")))
        tx.wire.update(node, {"owner": "Grace"})

    db_for(ACCOUNT, port).transact(fn)

    assert len(_writes(port)) == 1
    assert _writes(port)[0].binds[:2] == ("Grace", Decimal("125.00"))


def test_a_wire_update_then_delete_of_one_object_emits_one_delete() -> None:
    port = ScriptedPort(Transact(Read(rows=[dict(_PERSON_ROW)]), Write()))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _PERSON_QUERY)
        tx.wire.update(node, {"name": "Grace"})
        tx.wire.delete(node)

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [WriteCall("delete from person where id = %s", (1,))]


def test_an_insert_answers_the_frozen_node_it_opened() -> None:
    # The Typed peer leaves its caller holding the instance it passed, so a pure
    # Wire caller must be handed something too. The node publishes the payload's
    # own members in canonical Wire spelling and refuses mutation like any other.
    port = ScriptedPort(Transact(Write()))
    opened: list[object] = []

    def fn(tx: Transaction) -> None:
        opened.append(tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"}))

    db_for(PERSON, port).transact(fn)
    node = opened[0]
    assert isinstance(node, WireEntity)
    assert dict(node) == {"id": 9, "name": "Newton"}
    with pytest.raises(TypeError):
        cast("dict[str, object]", node)["name"] = "Mallory"


def test_a_wire_update_of_a_row_the_same_unit_inserted_coalesces_in_place() -> None:
    # The parity gap this return closes: with no node to hand back, a pure Wire
    # caller could not revise the row it just opened, and re-reading is not an
    # option — a participating read force-flushes.
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        tx.wire.update(opened, {"name": "Grace"})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Grace"))
    ]


def test_a_wire_delete_of_a_row_the_same_unit_inserted_cancels_to_no_dml() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        tx.wire.delete(tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "N"}))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_writing_back_what_an_insert_published_is_the_ordinary_no_op() -> None:
    # The node is rendered through the SAME canonical encoding a read publishes,
    # so a member written back off it restores rather than assigns — which is
    # what makes the returned value interchangeable with a read result.
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        tx.wire.update(opened, {"name": opened["name"]})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Newton"))
    ]


def test_an_insert_refuses_the_node_a_previous_insert_answered() -> None:
    # It names a row this unit of work already opened, so the verb for it is
    # `tx.wire.update` — the same provenance refusal a read result earns.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        opened = tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        tx.wire.insert("parallax.compatibility.Person", opened)

    with pytest.raises(KeyedWriteValueError, match="write-value-already-stored"):
        db_for(PERSON, port).transact(fn)


def test_a_typed_update_of_a_row_a_wire_insert_opened_coalesces_in_place() -> None:
    # The buffered-insert ledger is ONE ledger: the Typed provenance refusal
    # exempts a value naming an object the WIRE verb inserted, so the pair
    # coalesces into a single INSERT carrying the final value rather than being
    # refused as a write of a row no read produced.
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        tx.update(mm.Person(id=9, name="Newton").edit(name="Grace"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Grace"))
    ]


# --------------------------------------------------------------------------- #
# Input capture: what a verb buffered is its own from the moment it returns.  #
# --------------------------------------------------------------------------- #
def test_mutating_the_changes_mapping_after_the_verb_returns_changes_nothing() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))
    changes: dict[str, object] = {"balance": "125.00"}

    def fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _ACCOUNT_QUERY), changes)
        changes["balance"] = "999.00"
        changes["owner"] = "Mallory"

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == [
        WriteCall(
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_mutating_insert_data_after_the_verb_returns_changes_nothing() -> None:
    port = ScriptedPort(Transact(Write()))
    data: dict[str, Any] = {"id": 9, "name": "Newton"}

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Person", data)
        data["name"] = "Mallory"

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        WriteCall("insert into person(id, name) values (%s, %s)", (9, "Newton"))
    ]


def test_mutating_a_predicate_target_after_the_verb_returns_changes_nothing() -> None:
    port = ScriptedPort(Transact(Write()))
    predicate: dict[str, Any] = {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}}
    target: dict[str, Any] = {"entity": "parallax.compatibility.Person", "predicate": predicate}

    def fn(tx: Transaction) -> None:
        tx.wire.delete_where(target)
        cast("dict[str, Any]", predicate["eq"])["value"] = 99

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [WriteCall("delete from person where id = %s", (1,))]


def test_a_returned_wire_mapping_still_refuses_mutation_after_a_write() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        with pytest.raises(TypeError):
            cast("dict[str, object]", node)["balance"] = "999.00"
        assert node["balance"] == "100.00"

    db_for(ACCOUNT, port).transact(fn)


def test_the_wire_view_is_reachable_from_the_module_level_connect() -> None:
    port = ScriptedPort(Transact(_ACCOUNT_READ, Write()))
    connect(port, ACCOUNT, clock=FixedClock(FIXED)).transact(
        lambda tx: tx.wire.delete(_node(tx, _ACCOUNT_QUERY))
    )
    assert len(_writes(port)) == 1


# --------------------------------------------------------------------------- #
# Value Object documents: an authored occurrence crosses the serde seam whole. #
# --------------------------------------------------------------------------- #
def _bound_address(port: ScriptedPort) -> dict[str, Any]:
    """The address document the insert actually bound, as ordinary data.

    A Document-layout occurrence binds through a canonical JSON carrier, so the
    bind is unwrapped once here rather than at each assertion.
    """
    bound = _writes(port)[0].binds[2]
    assert isinstance(bound, JsonDocument)
    return cast("dict[str, Any]", bound.value)


_ADDRESS: dict[str, Any] = {
    "street": "1 Main",
    "city": "Springfield",
    "geo": {"country": "US", "point": {"lat": 1.5, "lon": 2.5}},
    "phones": [{"type": "home", "number": "555", "expires": "2030-01-01"}],
}


def test_an_authored_occurrence_decodes_at_every_depth() -> None:
    # The `many` element's `expires` is an ISO date STRING, which only the serde
    # crossing admits: an undecoded string is no member of `date`'s value space,
    # so a verb that skipped the crossing would refuse this document rather than
    # bind it. What reaches storage is the canonical spelling of the whole
    # subtree, nested `one` and `many` alike.
    port = ScriptedPort(Transact(Write()))
    data: dict[str, Any] = {"id": 1, "name": "Ada", "address": copy.deepcopy(_ADDRESS)}

    db_for(CONTACT, port).transact(
        lambda tx: tx.wire.insert("parallax.compatibility.Contact", data)
    )

    assert _bound_address(port) == {
        "street": "1 Main",
        "city": "Springfield",
        "geo": {"country": "US", "point": {"lat": 1.5, "lon": 2.5}},
        "phones": [{"type": "home", "number": "555", "expires": "2030-01-01"}],
    }


def test_an_authored_occurrence_is_captured_at_the_call() -> None:
    port = ScriptedPort(Transact(Write()))
    address: dict[str, Any] = copy.deepcopy(_ADDRESS)
    data: dict[str, Any] = {"id": 1, "name": "Ada", "address": address}

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Contact", data)
        cast("list[dict[str, Any]]", address["phones"]).append({"type": "work"})
        cast("dict[str, Any]", address["geo"])["country"] = "FR"

    db_for(CONTACT, port).transact(fn)

    document = _bound_address(port)
    assert cast("dict[str, Any]", document["geo"])["country"] == "US"
    assert len(cast("list[object]", document["phones"])) == 1


def test_two_positions_sharing_one_document_are_captured_rather_than_refused() -> None:
    # Sharing is not a cycle: the capture refuses only a container reachable
    # from itself, so a caller reusing one subdocument at two positions has it
    # copied at each and mutating the original reaches neither.
    port = ScriptedPort(Transact(Write()))
    phone: dict[str, Any] = {"type": "home", "number": "555"}
    address: dict[str, Any] = {**copy.deepcopy(_ADDRESS), "phones": [phone, phone]}

    def fn(tx: Transaction) -> None:
        tx.wire.insert(
            "parallax.compatibility.Contact", {"id": 1, "name": "Ada", "address": address}
        )
        phone["number"] = "999"

    db_for(CONTACT, port).transact(fn)

    numbers = [
        cast("dict[str, Any]", entry)["number"]
        for entry in cast("list[object]", _bound_address(port)["phones"])
    ]
    assert numbers == ["555", "555"]


def test_a_nullable_occurrence_may_be_authored_absent() -> None:
    port = ScriptedPort(Transact(Write()))
    db_for(CONTACT, port).transact(
        lambda tx: tx.wire.insert(
            "parallax.compatibility.Contact", {"id": 1, "name": "Ada", "address": None}
        )
    )
    assert len(_writes(port)) == 1


@pytest.mark.parametrize(
    "address",
    [
        5,
        {**_ADDRESS, "phones": "oops"},
        {**_ADDRESS, "geo": 7},
    ],
)
def test_a_malformed_occurrence_document_is_refused_by_the_judgement(address: object) -> None:
    # Decoding is total and nonthrowing, so a value no declared decoding
    # recognizes reaches the type verdict rather than a decoding failure. The
    # verdict is the normative payload rule's own, which is why it carries that
    # rule's class rather than the verb's: one input, one classification, at
    # every ingress that accepts it.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteRejectedError, match=r"Contact\.address"):
            tx.wire.insert(
                "parallax.compatibility.Contact",
                {"id": 1, "name": "Ada", "address": copy.deepcopy(address)},
            )

    db_for(CONTACT, port).transact(fn)
    assert _writes(port) == []


def test_a_predicate_target_that_is_not_a_document_is_refused() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="canonical"):
            tx.wire.delete_where(cast("dict[str, object]", ["Person"]))

    db_for(PERSON, port).transact(fn)


def test_an_insert_naming_an_undeclared_member_reaches_the_honesty_gate() -> None:
    # Decoding leaves a key the model declares no member for exactly as authored,
    # so what names it is the member-name honesty gate rather than a decoding
    # failure standing in for one.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="undeclared member"):
            tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton", "nope": 1})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_an_insert_of_a_family_subtype_answers_a_node_carrying_its_variant() -> None:
    # The node an insert answers describes the row the SAME way a read publishes
    # it, which for a family participant includes the variant tag: a caller that
    # revises the row it just opened, or that grades what the verb answered, sees
    # the concrete subtype rather than having to infer it from the members.
    port = ScriptedPort(Transact(Write()))
    opened: list[WireEntity] = []

    def fn(tx: Transaction) -> None:
        opened.append(
            tx.wire.insert(
                "parallax.compatibility.CardPayment",
                {"id": 9, "amount": "10.00", "cardNetwork": "Visa"},
            )
        )

    db_for(PAYMENT, port).transact(fn)
    assert dict(opened[0]) == {
        "id": 9,
        "amount": "10.00",
        "cardNetwork": "Visa",
        "familyVariant": "CardPayment",
    }
