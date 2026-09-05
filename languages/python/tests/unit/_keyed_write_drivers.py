"""Typed and Wire drivers for the keyed-write order matrix.

One :class:`Scenario` states what a keyed write IS — the target Entity, the verb,
the Concurrency Preference, how the source value was obtained, what the caller
authored, and which window it stated — without stating which representation
issues it. Each driver then obtains that source in its own representation, calls
the one verb, and reports what the call produced: the whole port chronology the
transaction ran, and — when it refused — the refusal's class, code, message, and
the point in the transaction it was raised at. The two reports are directly
comparable, which is what lets one row assert that both representations answer
one scenario the same way rather than asserting a Typed shape and a Wire shape
separately.

The report is deliberately lossless where a lossy one could let two different
behaviors compare equal. It carries every read, boundary, and statement rather
than the DML alone, so a lane that reads differently or commits where the other
rolls back cannot pass; it carries the phase, so a refusal at the verb and one at
the flush are never the same answer; and a failure of the harness itself — an
unscripted call, or a driver assertion — propagates as the assertion it is rather
than being serialized as a product refusal two lanes could agree on.

A scenario is deliberately not a free-form callback. Every axis it carries is a
value the matrix can name in a test id, so a disagreeing row reads as the
scenario that disagrees rather than as a lambda that failed.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore — the same convention `_transact_support`
follows. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Literal, cast

from _transact_support import (
    ACCOUNT,
    BALANCE,
    CONTACT,
    INFINITY_INSTANT,
    PERSON,
    WHERE_POSITION_META,
    WherePosition,
    balance_row,
    db_for,
)

from _support import mirrored_models as mm
from _support.db_port import PortCall, Read, ReadCall, ScriptedPort, Transact, Write
from parallax.conformance.vo_models import ContactAddress, ContactGeo, ContactPhone, ContactPoint
from parallax.core import LATEST, DomainModel
from parallax.core.base import SQL_NULL, DocumentValue, PresentDocument
from parallax.core.db_port import Row
from parallax.core.entity import Entity as EntityBase
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot.handle import Database, Transaction, WireEntity

__all__ = [
    "ACCOUNT_TARGET",
    "BALANCE_TARGET",
    "BLANK_CONTACT_TARGET",
    "CONCURRENCIES",
    "CONTACT_TARGET",
    "DOCUMENT_TARGETS",
    "PERSON_TARGET",
    "POSITION_TARGET",
    "REPRESENTATIONS",
    "TARGETS",
    "UNTIL",
    "VALID_FROM",
    "VERBS",
    "Change",
    "Completed",
    "Outcome",
    "Phase",
    "Refused",
    "Representation",
    "Scenario",
    "Source",
    "Target",
    "Verb",
    "Window",
    "outcome",
    "reachable",
]


type Verb = Literal[
    "insert", "insert_until", "update", "update_until", "delete", "terminate", "terminate_until"
]
type Representation = Literal["typed", "wire"]
type Concurrency = Literal["locking", "optimistic"]

type Source = Literal["participating", "standalone", "pinned", "reread"]
"""How the source value the verb writes was obtained.

``reread`` follows a same-transaction insert with a read of the row it opened,
which is the only route by which a Wire keyed verb can write a row a TYPED
insert opened — and, because a participating read force-flushes, the route on
which the pair no longer coalesces.
"""

type Change = Literal["ordinary", "net_zero", "untouched"]
"""What the caller authored over that source, for the two update verbs."""

type Window = Literal["stated", "reversed"]
"""Which Valid-Time window the call stated, for the three bounded verbs."""

type Phase = Literal["source", "verb", "flush"]
"""Where a refusal was raised: obtaining the source, at the verb, or at the flush."""

VERBS: Final[tuple[Verb, ...]] = (
    "insert",
    "insert_until",
    "update",
    "update_until",
    "delete",
    "terminate",
    "terminate_until",
)
CONCURRENCIES: Final[tuple[Concurrency, ...]] = ("locking", "optimistic")
REPRESENTATIONS: Final[tuple[Representation, ...]] = ("typed", "wire")

_INSERT_VERBS: Final[frozenset[str]] = frozenset({"insert", "insert_until"})
_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"update", "update_until"})
VALID_FROM: Final = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
UNTIL: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_TX_PIN: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_TX_PIN_WIRE: Final = "2024-03-01T00:00:00.000000Z"


@dataclass(frozen=True, slots=True)
class Refused:
    """The refusal a verb raised, as a caller observes it, and where it landed.

    ``code`` is ``None`` for the refusal classes that carry no code — the whole
    of the `m-core` window and instruction vocabulary — whose message is then the
    only thing distinguishing two refusals of one class. ``phase`` distinguishes
    two refusals that are otherwise identical but reach the caller at different
    points, and ``calls`` carries everything the transaction had already done to
    the database by then.
    """

    error: str
    code: str | None
    message: str
    phase: Phase
    calls: tuple[PortCall, ...]


@dataclass(frozen=True, slots=True)
class Completed:
    """Everything the transaction asked of the port, in order, through commit.

    Reads and boundaries ride beside the DML rather than being filtered out: a
    lane that resolves its source with a different statement, or that ends its
    boundary differently, states a different outcome even when the DML matches.
    """

    calls: tuple[PortCall, ...]


type Outcome = Refused | Completed


@dataclass(frozen=True, slots=True)
class Target:
    """One Entity fixture, addressable from both representations.

    Every field comes in a Typed and a Wire spelling of ONE value, so a scenario
    names the value and each driver spells it its own way: the stored row and the
    query that reads it, the fresh row an insert opens, the row that insert leaves
    behind for a later read, the assignment an ordinary change authors, and the
    value already stored under that member.

    ``valid_from`` is the Valid-Time instant this target's PLAIN verbs state — an
    instant for a Bitemporal target, absent for every other, which is exactly
    what :func:`~parallax.snapshot.handle._write_inputs.validate_window` admits.
    """

    name: str
    model: DomainModel
    entity: str
    row: Row
    typed_query: ObjectQuery[EntityBase, EntityBase]
    wire_query: Mapping[str, object]
    fresh: Callable[[], EntityBase]
    payload: Mapping[str, object]
    inserted_row: Row
    inserted_typed_query: ObjectQuery[EntityBase, EntityBase]
    inserted_wire_query: Mapping[str, object]
    change_typed: Mapping[str, object]
    change_wire: Mapping[str, object]
    stored_typed: Mapping[str, object]
    stored_wire: Mapping[str, object]
    valid_from: dt.datetime | None
    pinned_typed_query: ObjectQuery[EntityBase, EntityBase] | None = None
    pinned_wire_query: Mapping[str, object] | None = None

    @property
    def opened_typed(self) -> Mapping[str, object]:
        """The changed member's value as an insert of :attr:`fresh` opens it."""
        opened = self.fresh()
        return {name: getattr(opened, name) for name in self.change_typed}

    @property
    def opened_wire(self) -> Mapping[str, object]:
        return {name: self.payload[name] for name in self.change_wire}


def _account_query(key: int = 1) -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Account.where(mm.Account.id == key))


def _person_query(key: int = 1) -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Person.where(mm.Person.id == key))


def _balance_query(key: int = 1) -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Balance.where(mm.Balance.id == key))


def _contact_query(key: int = 1) -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Contact.where(mm.Contact.id == key))


def _position_query(
    key: int = 1, tx_time: dt.datetime | None = None
) -> ObjectQuery[EntityBase, EntityBase]:
    query = WherePosition.where(WherePosition.id == key)
    pinned = (
        query.as_of(valid_time=LATEST)
        if tx_time is None
        else query.as_of(valid_time=LATEST, tx_time=tx_time)
    )
    return cast("ObjectQuery[EntityBase, EntityBase]", pinned)


def _wire_query(
    entity: str, key: int, temporal: Mapping[str, object] | None = None
) -> Mapping[str, object]:
    query: dict[str, object] = {
        "target": entity,
        "predicate": {"eq": {"attr": f"{entity}.id", "value": key}},
    }
    if temporal is not None:
        query["temporal"] = temporal
    return query


_LATEST_TX: Final[Mapping[str, object]] = {"transaction-time": {"asOf": "latest"}}
_LATEST_BOTH: Final[Mapping[str, object]] = {
    "transaction-time": {"asOf": "latest"},
    "valid-time": {"asOf": "latest"},
}


def _position_row(key: int, acct_num: str, value: Decimal, from_z: dt.datetime) -> Row:
    return {
        "id": key,
        "acct_num": acct_num,
        "value": value,
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    }


def _contact_address(street: str, city: str, numbers: tuple[str, ...]) -> ContactAddress:
    return ContactAddress(
        street=street,
        city=city,
        geo=ContactGeo(country="NO", point=ContactPoint(lat=59.9, lon=10.7)),
        phones=tuple(ContactPhone(type="work", number=number, expires=None) for number in numbers),
    )


def _contact_document(street: str, city: str, numbers: tuple[str, ...]) -> dict[str, DocumentValue]:
    return {
        "street": street,
        "city": city,
        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
        "phones": [{"type": "work", "number": number, "expires": None} for number in numbers],
    }


_STORED_ADDRESS: Final = _contact_address("1 Park", "Oslo", ("111", "222"))
_STORED_DOCUMENT: Final = _contact_document("1 Park", "Oslo", ("111", "222"))
_OTHER_ADDRESS: Final = _contact_address("2 Park", "Bergen", ("333",))
_OTHER_DOCUMENT: Final = _contact_document("2 Park", "Bergen", ("333",))


_ACCOUNT = "parallax.compatibility.Account"
_PERSON = "parallax.compatibility.Person"
_BALANCE = "parallax.compatibility.Balance"
_CONTACT = "parallax.compatibility.Contact"
_POSITION = "parallax.compatibility.WherePosition"

# Non-Temporal with an explicit version: the optimistic gate is the version column.
ACCOUNT_TARGET: Final = Target(
    name="account",
    model=ACCOUNT,
    entity=_ACCOUNT,
    row={"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4},
    typed_query=_account_query(),
    wire_query=_wire_query(_ACCOUNT, 1),
    fresh=lambda: mm.Account(id=7, owner="Newton", balance=Decimal("5.00")),
    payload={"id": 7, "owner": "Newton", "balance": "5.00"},
    inserted_row={"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1},
    inserted_typed_query=_account_query(7),
    inserted_wire_query=_wire_query(_ACCOUNT, 7),
    change_typed={"balance": Decimal("125.00")},
    change_wire={"balance": "125.00"},
    stored_typed={"balance": Decimal("100.00")},
    stored_wire={"balance": "100.00"},
    valid_from=None,
)

# Non-Temporal and unversioned: no gate source at all, so every preference falls
# back to Locking and a participating read's shared lock is the whole evidence.
PERSON_TARGET: Final = Target(
    name="person",
    model=PERSON,
    entity=_PERSON,
    row={"id": 1, "name": "Ada"},
    typed_query=_person_query(),
    wire_query=_wire_query(_PERSON, 1),
    fresh=lambda: mm.Person(id=9, name="Newton"),
    payload={"id": 9, "name": "Newton"},
    inserted_row={"id": 9, "name": "Newton"},
    inserted_typed_query=_person_query(9),
    inserted_wire_query=_wire_query(_PERSON, 9),
    change_typed={"name": "Grace"},
    change_wire={"name": "Grace"},
    stored_typed={"name": "Ada"},
    stored_wire={"name": "Ada"},
    valid_from=None,
)

# Transaction-Time-Only: the gate is derived from the as-of axis rather than
# from a version column, and no verb here states a Valid-Time bound.
BALANCE_TARGET: Final = Target(
    name="balance",
    model=BALANCE,
    entity=_BALANCE,
    row=balance_row(in_z=_TX_START),
    typed_query=_balance_query(),
    wire_query=_wire_query(_BALANCE, 1, _LATEST_TX),
    fresh=lambda: mm.Balance(id=9, acct_num="A-9", value=Decimal("5.00")),
    payload={"id": 9, "acctNum": "A-9", "value": "5.00"},
    inserted_row={
        "bal_id": 9,
        "acct_num": "A-9",
        "val": Decimal("5.00"),
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    },
    inserted_typed_query=_balance_query(9),
    inserted_wire_query=_wire_query(_BALANCE, 9, _LATEST_TX),
    change_typed={"value": Decimal("125.00")},
    change_wire={"value": "125.00"},
    stored_typed={"value": Decimal("5.00")},
    stored_wire={"value": "5.00"},
    valid_from=None,
)

# Non-Temporal with a document-resident Value Object occurrence, whose own
# members carry a nested occurrence and a nested many: the change axis's only
# fixture where the Typed codec's serialized-document equality and the Wire
# lane's frozen-decoded equality are compared over anything but one scalar.
CONTACT_TARGET: Final = Target(
    name="contact",
    model=CONTACT,
    entity=_CONTACT,
    row={"id": 1, "name": "Ada", "address": PresentDocument(dict(_STORED_DOCUMENT))},
    typed_query=_contact_query(),
    wire_query=_wire_query(_CONTACT, 1),
    fresh=lambda: mm.Contact(id=4, name="Newton", address=_OTHER_ADDRESS),
    payload={"id": 4, "name": "Newton", "address": dict(_OTHER_DOCUMENT)},
    inserted_row={"id": 4, "name": "Newton", "address": PresentDocument(dict(_OTHER_DOCUMENT))},
    inserted_typed_query=_contact_query(4),
    inserted_wire_query=_wire_query(_CONTACT, 4),
    change_typed={"address": _OTHER_ADDRESS},
    change_wire={"address": dict(_OTHER_DOCUMENT)},
    stored_typed={"address": _STORED_ADDRESS},
    stored_wire={"address": dict(_STORED_DOCUMENT)},
    valid_from=None,
)

# The same document-resident member, stored ABSENT: restoring it names the
# member explicitly and states null, which an untouched copy never names at all.
BLANK_CONTACT_TARGET: Final = Target(
    name="blank-contact",
    model=CONTACT,
    entity=_CONTACT,
    row={"id": 2, "name": "Ada", "address": SQL_NULL},
    typed_query=_contact_query(2),
    wire_query=_wire_query(_CONTACT, 2),
    fresh=lambda: mm.Contact(id=6, name="Newton", address=None),
    payload={"id": 6, "name": "Newton", "address": None},
    inserted_row={"id": 6, "name": "Newton", "address": SQL_NULL},
    inserted_typed_query=_contact_query(6),
    inserted_wire_query=_wire_query(_CONTACT, 6),
    change_typed={"address": _STORED_ADDRESS},
    change_wire={"address": dict(_STORED_DOCUMENT)},
    stored_typed={"address": None},
    stored_wire={"address": None},
    valid_from=None,
)

# Bitemporal: the only target every bounded verb admits, and the only one whose
# source can carry a finite Transaction-Time pin.
POSITION_TARGET: Final = Target(
    name="position",
    model=WHERE_POSITION_META,
    entity=_POSITION,
    row=_position_row(1, "A", Decimal("100.00"), _TX_START),
    typed_query=_position_query(),
    wire_query=_wire_query(_POSITION, 1, _LATEST_BOTH),
    fresh=lambda: WherePosition(id=2, acct_num="B", value=Decimal("10.00")),
    payload={"id": 2, "acctNum": "B", "value": "10.00"},
    inserted_row=_position_row(2, "B", Decimal("10.00"), VALID_FROM),
    inserted_typed_query=_position_query(2),
    inserted_wire_query=_wire_query(_POSITION, 2, _LATEST_BOTH),
    change_typed={"value": Decimal("300.00")},
    change_wire={"value": "300.00"},
    stored_typed={"value": Decimal("100.00")},
    stored_wire={"value": "100.00"},
    valid_from=VALID_FROM,
    pinned_typed_query=_position_query(tx_time=_TX_PIN),
    pinned_wire_query=_wire_query(
        _POSITION,
        1,
        {"transaction-time": {"asOf": _TX_PIN_WIRE}, "valid-time": {"asOf": "latest"}},
    ),
)

TARGETS: Final[tuple[Target, ...]] = (
    ACCOUNT_TARGET,
    PERSON_TARGET,
    BALANCE_TARGET,
    POSITION_TARGET,
)

DOCUMENT_TARGETS: Final[tuple[Target, ...]] = (CONTACT_TARGET, BLANK_CONTACT_TARGET)


@dataclass(frozen=True, slots=True)
class Scenario:
    """One keyed write, stated without naming a representation."""

    target: Target
    verb: Verb
    concurrency: Concurrency = "optimistic"
    source: Source = "participating"
    change: Change = "ordinary"
    window: Window = "stated"
    opened_by: Representation | None = None
    opened_until: bool = False
    """Whether the same-transaction insert stated a bounded Valid-Time window."""
    wire_changes: Mapping[str, object] | None = None
    """A Wire-only authored document, for shapes no Typed caller can express."""
    label: str = field(default="", compare=False)

    def __str__(self) -> str:
        if self.label:
            return self.label
        parts = [self.target.name, self.verb, self.concurrency]
        if self.source != "participating":
            parts.append(self.source)
        if self.change != "ordinary":
            parts.append(self.change)
        if self.window != "stated":
            parts.append(self.window)
        if self.opened_by is not None:
            parts.append(f"opened-by-{self.opened_by}")
        if self.opened_until:
            parts.append("opened-until")
        return "-".join(parts)


def reachable(scenario: Scenario, representation: Representation) -> bool:
    """Whether ``representation`` can issue ``scenario`` at all.

    One shape is not reachable: a Wire keyed write over a source a TYPED insert
    opened and STILL HOLDS BUFFERED. A Typed insert hands its caller back
    nothing, and a Wire keyed verb accepts only a hinted Wire Entity, which only
    a Wire read or a Wire insert can produce — and a Wire read force-flushes the
    insert first, so the pair it would have coalesced is already two writes by
    the time the source exists. That route is the ``reread`` source, which every
    representation can spell; it is a different scenario, not this one.
    """
    return not (
        representation == "wire" and scenario.opened_by == "typed" and scenario.source != "reread"
    )


def outcome(scenario: Scenario, representation: Representation) -> Outcome:
    """Run ``scenario`` through ``representation`` and report what it produced.

    Only a refusal the product raised is reported as one. An ``AssertionError``
    is the harness speaking — an unscripted call, or a driver's own claim about
    the fixture — and propagates, because a row that serialized it as a refusal
    could report two broken lanes as one agreement.
    """
    port = _port(scenario)
    db = db_for(scenario.target.model, port)
    phase: Phase = "source"

    def body(tx: Transaction) -> None:
        nonlocal phase
        _body(tx, scenario, representation, prior)
        phase = "flush"

    try:
        prior = _standalone_source(db, scenario, representation)
        phase = "verb"
        db.transact(body, concurrency=scenario.concurrency)
    except AssertionError:
        raise
    except Exception as raised:
        return Refused(
            type(raised).__name__,
            cast("str | None", getattr(raised, "code", None)),
            str(raised),
            phase,
            tuple(port.calls),
        )
    _assert_the_scripted_read_was_reached(port, scenario)
    return Completed(tuple(port.calls))


def _reads_the_stored_row(scenario: Scenario) -> bool:
    """Whether this scenario's source comes from a read of the target's own row."""
    return scenario.verb not in _INSERT_VERBS and scenario.opened_by is None


def _assert_the_scripted_read_was_reached(port: ScriptedPort, scenario: Scenario) -> None:
    """Fail a row that completed without running the read its scenario states.

    The write allowance below is a budget rather than a count, so the port cannot
    be asked to assert its whole script was consumed. Its reads are exact, and a
    lane that resolved its source without one did less than the scenario says.
    """
    reads = sum(1 for call in port.calls if isinstance(call, ReadCall))
    expected = int(_reads_the_stored_row(scenario)) + int(scenario.source == "reread")
    if reads != expected:
        raise AssertionError(f"{scenario}: {expected} scripted read(s), {reads} run")


def _port(scenario: Scenario) -> ScriptedPort:
    """A port scripted for the reads this scenario runs and the DML it may emit.

    The write budget is deliberately generous: what a row asserts is the DML two
    representations agree on, and a script that pinned a count per row would be
    stating that expectation twice. A row that overruns it is loud rather than
    quiet, because the unscripted call raises through :func:`outcome`.

    A ``reread`` source is the one shape whose writes straddle a read: the insert
    it follows is force-flushed by that read, so its one statement is scripted
    ahead of the read rather than inside the budget after it.
    """
    read = Read(rows=[dict(scenario.target.row)])
    writes = Write(times=8)
    if scenario.source == "reread":
        reread = Read(rows=[dict(scenario.target.inserted_row)])
        return ScriptedPort(Transact(Write(), reread, writes))
    if scenario.verb in _INSERT_VERBS or scenario.opened_by is not None:
        return ScriptedPort(Transact(writes))
    if scenario.source == "standalone":
        return ScriptedPort(read, Transact(writes))
    return ScriptedPort(Transact(read, writes))


def _standalone_source(
    db: Database, scenario: Scenario, representation: Representation
) -> object | None:
    if scenario.source != "standalone" or scenario.verb in _INSERT_VERBS:
        return None
    if representation == "typed":
        return db.find(scenario.target.typed_query).result()
    return db.wire.find(scenario.target.wire_query).result()


def _body(
    tx: Transaction, scenario: Scenario, representation: Representation, prior: object | None
) -> None:
    if representation == "typed":
        _typed(tx, scenario, prior)
    else:
        _wire(tx, scenario, prior)


def _typed(tx: Transaction, scenario: Scenario, prior: object | None) -> None:
    target = scenario.target
    if scenario.verb in _INSERT_VERBS:
        _call_typed(tx, scenario, target.fresh())
        return
    source = cast("EntityBase", _typed_source(tx, scenario, prior))
    _call_typed(tx, scenario, _typed_authored(scenario, source))


def _typed_source(tx: Transaction, scenario: Scenario, prior: object | None) -> object:
    target = scenario.target
    if scenario.opened_by is not None:
        _open(tx, scenario)
        if scenario.source == "reread":
            return tx.find(target.inserted_typed_query).result()
        # A fresh instance names the object the insert opened: the ledger keys by
        # the Entity and the identity members, never by object identity.
        return target.fresh()
    if prior is not None:
        return prior
    if scenario.source == "pinned":
        assert target.pinned_typed_query is not None
        return tx.find(target.pinned_typed_query).result()
    return tx.find(target.typed_query).result()


def _typed_authored(scenario: Scenario, source: EntityBase) -> EntityBase:
    target = scenario.target
    if scenario.verb not in _UPDATE_VERBS or scenario.change == "untouched":
        return source
    edited = source.edit(**target.change_typed)
    if scenario.change == "ordinary":
        return edited
    restored = target.opened_typed if scenario.opened_by is not None else target.stored_typed
    return edited.edit(**restored)


def _call_typed(tx: Transaction, scenario: Scenario, value: EntityBase) -> None:
    plain = scenario.target.valid_from
    valid_from, until = _bounded_window(scenario)
    match scenario.verb:
        case "insert":
            tx.insert(value, valid_from=plain)
        case "insert_until":
            tx.insert_until(value, valid_from=valid_from, until=until)
        case "update":
            tx.update(value, valid_from=plain)
        case "update_until":
            tx.update_until(value, valid_from=valid_from, until=until)
        case "delete":
            tx.delete(value)
        case "terminate":
            tx.terminate(value, valid_from=plain)
        case "terminate_until":
            tx.terminate_until(value, valid_from=valid_from, until=until)
        case _:
            # Every `Verb` is spelled above; a verb added to one lane and not the
            # other would otherwise write nothing and read as an agreed no-op.
            raise AssertionError(f"no {scenario.verb} in this lane")


def _wire(tx: Transaction, scenario: Scenario, prior: object | None) -> None:
    target = scenario.target
    if scenario.verb in _INSERT_VERBS:
        _call_wire(tx, scenario, target.payload, {})
        return
    source = _wire_source(tx, scenario, prior)
    _call_wire(tx, scenario, source, _wire_authored(scenario))


def _wire_source(tx: Transaction, scenario: Scenario, prior: object | None) -> object:
    target = scenario.target
    if scenario.opened_by is not None:
        opened = _open(tx, scenario)
        if scenario.source == "reread":
            return tx.wire.find(target.inserted_wire_query).result()
        assert opened is not None
        return opened
    if prior is not None:
        return prior
    if scenario.source == "pinned":
        assert target.pinned_wire_query is not None
        return tx.wire.find(target.pinned_wire_query).result()
    return tx.wire.find(target.wire_query).result()


def _wire_authored(scenario: Scenario) -> Mapping[str, object]:
    target = scenario.target
    if scenario.wire_changes is not None:
        return scenario.wire_changes
    if scenario.verb not in _UPDATE_VERBS or scenario.change == "untouched":
        return {}
    if scenario.change == "ordinary":
        return target.change_wire
    return target.opened_wire if scenario.opened_by is not None else target.stored_wire


def _call_wire(
    tx: Transaction, scenario: Scenario, source: object, changes: Mapping[str, object]
) -> None:
    plain = scenario.target.valid_from
    valid_from, until = _bounded_window(scenario)
    observed = cast("WireEntity", source)
    authored = dict(changes)
    match scenario.verb:
        case "insert":
            tx.wire.insert(scenario.target.entity, dict(scenario.target.payload), valid_from=plain)
        case "insert_until":
            tx.wire.insert_until(
                scenario.target.entity,
                dict(scenario.target.payload),
                valid_from=valid_from,
                until=until,
            )
        case "update":
            tx.wire.update(observed, authored, valid_from=plain)
        case "update_until":
            tx.wire.update_until(observed, authored, valid_from=valid_from, until=until)
        case "delete":
            tx.wire.delete(observed)
        case "terminate":
            tx.wire.terminate(observed, valid_from=plain)
        case "terminate_until":
            tx.wire.terminate_until(observed, valid_from=valid_from, until=until)
        case _:
            # Every `Verb` is spelled above; a verb added to one lane and not the
            # other would otherwise write nothing and read as an agreed no-op.
            raise AssertionError(f"no {scenario.verb} in this lane")


def _bounded_window(scenario: Scenario) -> tuple[dt.datetime, dt.datetime]:
    """The pair a bounded verb states — ordered, or reversed onto one instant.

    A plain verb never reads it: its own bound is the target's, which is what
    keeps a Transaction-Time-Only or Non-Temporal target free of a Valid-Time
    instant it does not admit.
    """
    if scenario.window == "reversed":
        return UNTIL, VALID_FROM
    return VALID_FROM, UNTIL


def _open(tx: Transaction, scenario: Scenario) -> WireEntity | None:
    """Buffer the same-transaction insert this scenario's source came from.

    Bounded or plain: an ``insert_until`` opens a Valid-Time-bounded rectangle
    where ``insert`` opens one running to infinity, and the write that follows it
    is exempted by the same ledger either way. The opener's own window is always
    the ordered one — ``scenario.window`` states what the WRITE bounded, so a
    reversed window has to reach the write rather than be spent on the insert.
    """
    target = scenario.target
    if scenario.opened_by == "typed":
        if scenario.opened_until:
            tx.insert_until(target.fresh(), valid_from=VALID_FROM, until=UNTIL)
        else:
            tx.insert(target.fresh(), valid_from=target.valid_from)
        return None
    if scenario.opened_until:
        return tx.wire.insert_until(
            target.entity, dict(target.payload), valid_from=VALID_FROM, until=UNTIL
        )
    return tx.wire.insert(target.entity, dict(target.payload), valid_from=target.valid_from)
