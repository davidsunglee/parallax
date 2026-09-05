"""Typed and Wire drivers for the keyed-write order matrix.

One :class:`Scenario` states what a keyed write IS — the target Entity, the verb,
the Concurrency Preference, how the source value was obtained, what the caller
authored, and which window it stated — without stating which representation
issues it. Each driver then obtains that source in its own representation, calls
the one verb, and reports what the call produced: the DML the transaction emitted
in order, or the refusal it raised. The two reports are directly comparable,
which is what lets one row assert that both representations answer one scenario
the same way rather than asserting a Typed shape and a Wire shape separately.

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
    INFINITY_INSTANT,
    PERSON,
    WHERE_POSITION_META,
    WherePosition,
    balance_row,
    db_for,
)

from _support import mirrored_models as mm
from _support.db_port import Read, ScriptedPort, Transact, Write, WriteCall
from parallax.core import LATEST, DomainModel
from parallax.core.db_port import Row
from parallax.core.entity import Entity as EntityBase
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot.handle import Database, Transaction, WireEntity

__all__ = [
    "ACCOUNT_TARGET",
    "BALANCE_TARGET",
    "CONCURRENCIES",
    "PERSON_TARGET",
    "POSITION_TARGET",
    "TARGETS",
    "UNTIL",
    "VALID_FROM",
    "VERBS",
    "Buffered",
    "Outcome",
    "Refused",
    "Representation",
    "Scenario",
    "Target",
    "Verb",
    "outcome",
    "reachable",
]


type Verb = Literal[
    "insert", "insert_until", "update", "update_until", "delete", "terminate", "terminate_until"
]
type Representation = Literal["typed", "wire"]
type Concurrency = Literal["locking", "optimistic"]
"""How the source value the verb writes was obtained."""
type Source = Literal["participating", "standalone", "pinned"]
"""What the caller authored over that source, for the two update verbs."""
type Change = Literal["ordinary", "net_zero", "untouched"]
"""Which Valid-Time window the call stated, for the three bounded verbs."""
type Window = Literal["stated", "reversed"]

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

_INSERT_VERBS: Final[frozenset[str]] = frozenset({"insert", "insert_until"})
_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"update", "update_until"})
VALID_FROM: Final = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
UNTIL: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_TX_PIN: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_TX_PIN_WIRE: Final = "2024-03-01T00:00:00.000000Z"


# --------------------------------------------------------------------------- #
# What one row of the matrix reports.                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Refused:
    """The refusal a verb raised, as a caller observes it: class, code, message.

    ``code`` is ``None`` for the refusal classes that carry no code — the whole
    of the `m-core` window and instruction vocabulary — whose message is then the
    only thing distinguishing two refusals of one class.
    """

    error: str
    code: str | None
    message: str


@dataclass(frozen=True, slots=True)
class Buffered:
    """The DML the transaction emitted, in order — empty for an accepted no-op."""

    writes: tuple[WriteCall, ...]


type Outcome = Refused | Buffered


# --------------------------------------------------------------------------- #
# The Entity fixtures, one per (temporality, optimistic-gate) combination.    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Target:
    """One Entity fixture, addressable from both representations.

    Every field comes in a Typed and a Wire spelling of ONE value, so a scenario
    names the value and each driver spells it its own way: the stored row and the
    query that reads it, the fresh row an insert opens, the assignment an
    ordinary change authors, and the value already stored under that member.

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


def _account_query() -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Account.where(mm.Account.id == 1))


def _person_query() -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Person.where(mm.Person.id == 1))


def _balance_query() -> ObjectQuery[EntityBase, EntityBase]:
    return cast("ObjectQuery[EntityBase, EntityBase]", mm.Balance.where(mm.Balance.id == 1))


def _position_query(tx_time: dt.datetime | None = None) -> ObjectQuery[EntityBase, EntityBase]:
    query = WherePosition.where(WherePosition.id == 1)
    pinned = (
        query.as_of(valid_time=LATEST)
        if tx_time is None
        else query.as_of(valid_time=LATEST, tx_time=tx_time)
    )
    return cast("ObjectQuery[EntityBase, EntityBase]", pinned)


def _position_row() -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("100.00"),
        "from_z": _TX_START,
        "thru_z": INFINITY_INSTANT,
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    }


# Non-Temporal with an explicit version: the optimistic gate is the version column.
ACCOUNT_TARGET: Final = Target(
    name="account",
    model=ACCOUNT,
    entity="parallax.compatibility.Account",
    row={"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4},
    typed_query=_account_query(),
    wire_query={
        "target": "parallax.compatibility.Account",
        "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 1}},
    },
    fresh=lambda: mm.Account(id=7, owner="Newton", balance=Decimal("5.00")),
    payload={"id": 7, "owner": "Newton", "balance": "5.00"},
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
    entity="parallax.compatibility.Person",
    row={"id": 1, "name": "Ada"},
    typed_query=_person_query(),
    wire_query={
        "target": "parallax.compatibility.Person",
        "predicate": {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
    },
    fresh=lambda: mm.Person(id=9, name="Newton"),
    payload={"id": 9, "name": "Newton"},
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
    entity="parallax.compatibility.Balance",
    row=balance_row(in_z=_TX_START),
    typed_query=_balance_query(),
    wire_query={
        "target": "parallax.compatibility.Balance",
        "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
        "temporal": {"transaction-time": {"asOf": "latest"}},
    },
    fresh=lambda: mm.Balance(id=9, acct_num="A-9", value=Decimal("5.00")),
    payload={"id": 9, "acctNum": "A-9", "value": "5.00"},
    change_typed={"value": Decimal("125.00")},
    change_wire={"value": "125.00"},
    stored_typed={"value": Decimal("5.00")},
    stored_wire={"value": "5.00"},
    valid_from=None,
)

# Bitemporal: the only target every bounded verb admits, and the only one whose
# source can carry a finite Transaction-Time pin.
POSITION_TARGET: Final = Target(
    name="position",
    model=WHERE_POSITION_META,
    entity="parallax.compatibility.WherePosition",
    row=_position_row(),
    typed_query=_position_query(),
    wire_query={
        "target": "parallax.compatibility.WherePosition",
        "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
        "temporal": {
            "transaction-time": {"asOf": "latest"},
            "valid-time": {"asOf": "latest"},
        },
    },
    fresh=lambda: WherePosition(id=2, acct_num="B", value=Decimal("10.00")),
    payload={"id": 2, "acctNum": "B", "value": "10.00"},
    change_typed={"value": Decimal("300.00")},
    change_wire={"value": "300.00"},
    stored_typed={"value": Decimal("100.00")},
    stored_wire={"value": "100.00"},
    valid_from=VALID_FROM,
    pinned_typed_query=_position_query(tx_time=_TX_PIN),
    pinned_wire_query={
        "target": "parallax.compatibility.WherePosition",
        "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
        "temporal": {
            "transaction-time": {"asOf": _TX_PIN_WIRE},
            "valid-time": {"asOf": "latest"},
        },
    },
)

TARGETS: Final[tuple[Target, ...]] = (
    ACCOUNT_TARGET,
    PERSON_TARGET,
    BALANCE_TARGET,
    POSITION_TARGET,
)


# --------------------------------------------------------------------------- #
# One row of the matrix.                                                      #
# --------------------------------------------------------------------------- #
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
    """A Wire-only authored document, for shapes no Typed caller can express."""
    wire_changes: Mapping[str, object] | None = None
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
        return "-".join(parts)


def reachable(scenario: Scenario, representation: Representation) -> bool:
    """Whether ``representation`` can issue ``scenario`` at all.

    One shape is not reachable: a Typed insert hands its caller back nothing, and
    a Wire keyed verb accepts only a hinted Wire Entity — which only a Wire read
    or a Wire insert can produce, and a participating read force-flushes the
    insert it would have to follow. So a Wire write over a source a TYPED insert
    opened cannot be spelled, while all three other crossings can.
    """
    return not (representation == "wire" and scenario.opened_by == "typed")


# --------------------------------------------------------------------------- #
# Running one scenario in one representation.                                 #
# --------------------------------------------------------------------------- #
def outcome(scenario: Scenario, representation: Representation) -> Outcome:
    """Run ``scenario`` through ``representation`` and report what it produced."""
    port = _port(scenario)
    db = db_for(scenario.target.model, port)
    try:
        prior = _standalone_source(db, scenario, representation)
        db.transact(
            lambda tx: _body(tx, scenario, representation, prior),
            concurrency=scenario.concurrency,
        )
    except Exception as raised:
        return Refused(
            type(raised).__name__,
            cast("str | None", getattr(raised, "code", None)),
            str(raised),
        )
    return Buffered(tuple(op for op in port.calls if isinstance(op, WriteCall)))


def _port(scenario: Scenario) -> ScriptedPort:
    """A port scripted for the reads this scenario runs and the DML it may emit.

    The write budget is deliberately generous: what a row asserts is the DML two
    representations agree on, and a script that pinned a count per row would be
    stating that expectation twice.
    """
    read = Read(rows=[dict(scenario.target.row)])
    writes = Write(times=8)
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


# --------------------------------------------------------------------------- #
# The Typed driver.                                                           #
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# The Wire driver.                                                            #
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Shared: the window a bounded verb states, and the same-transaction insert.  #
# --------------------------------------------------------------------------- #
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
    """Buffer the same-transaction insert this scenario's source came from."""
    target = scenario.target
    if scenario.opened_by == "typed":
        tx.insert(target.fresh(), valid_from=target.valid_from)
        return None
    return tx.wire.insert(target.entity, dict(target.payload), valid_from=target.valid_from)
