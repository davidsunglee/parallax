"""Typed and Wire drivers for the write-order suites.

A scenario states what one write IS without stating which representation issues
it, and each driver then spells it in its own representation and calls the one
public verb, so a row states the scenario once and the expectation once, and
asserts it of each representation in turn. Each write family states only the
axes its own order reads. A :class:`KeyedWriteScenario` names the target Entity,
the verb, the Concurrency Preference, how the source value was obtained, what
the caller authored, and which window it stated. A
:class:`PredicateWriteScenario` names the selection, the assignments, the
original window keywords, and any pending write ahead of it. A
:class:`TargetWriteScenario` names the addressed input, the revision and window
keywords, and any pending write ahead of it. Neither reads a source in the
writing attempt: a predicate or conditional write consults none.

Two readings of what a call produced. :func:`answer` is the one a fixed
expectation is stated against: the refusal's class, code, verb-phase message, and
where it landed, plus how much DML the transaction emitted. :func:`outcome` is
the whole port chronology behind it, for the rows whose claim is the ORDER of
reads, boundaries, and statements rather than the verdict.

Both are deliberately lossless where a lossy reading could let two different
behaviors compare equal. The phase rides beside the class, so a refusal at the
verb and one at the flush are never the same answer; and a failure of the harness
itself — an unscripted call, or a driver assertion — propagates as the assertion
it is rather than being serialized as a product refusal an expectation could be
written around.

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
from typing import Any, Final, Literal, cast

from parallax.conformance.vo_models import ContactAddress, ContactGeo, ContactPhone, ContactPoint
from parallax.core import DomainModel, Predicate
from parallax.core.base import SQL_NULL, DocumentValue, PresentDocument
from parallax.core.db_port import MappingRow
from parallax.core.entity import AttributeAssignment
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity._expressions import AttributeRef, AuthoredPath, UnfinishedOperation
from parallax.core.execution import ExecutionFailure
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.predicate._interpretation import COMPARE
from parallax.snapshot import ReadOnlyTxnContext, ScopedDatabase, TxnContext, WireEntity
from tests._support import inheritance_models as im
from tests._support import mirrored_models as mm
from tests._support.db_port import (
    PortCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.write_bounds import stated_start
from tests.unit._transact_support import (
    ACCOUNT,
    BALANCE,
    CONTACT,
    FIXED,
    INFINITY_INSTANT,
    PAYMENT,
    PERSON,
    balance_row,
    db_for,
)
from tests.unit._where_position_model import (
    WHERE_POSITION_META,
    WherePosition,
)

__all__ = [
    "ACCOUNT_CONDITIONAL",
    "ACCOUNT_SELECTION",
    "ACCOUNT_TARGET",
    "BALANCE_CONDITIONAL",
    "BALANCE_SELECTION",
    "BALANCE_TARGET",
    "BLANK_CONTACT_TARGET",
    "CARD_PAYMENT_SELECTION",
    "CONCURRENCIES",
    "CONTACT_TARGET",
    "DOCUMENT_TARGETS",
    "OUTSIDE_SOURCES",
    "PERSON_CONDITIONAL",
    "PERSON_SELECTION",
    "PERSON_TARGET",
    "POSITION_CONDITIONAL",
    "POSITION_SELECTION",
    "POSITION_TARGET",
    "REPRESENTATIONS",
    "TARGETS",
    "TX_PIN",
    "UNDECLARED_CONDITIONAL",
    "UNDECLARED_SELECTION",
    "UNTIL",
    "VALID_FROM",
    "VERBS",
    "Address",
    "Answer",
    "Assignments",
    "Change",
    "Completed",
    "Concurrency",
    "ConditionalTarget",
    "Gate",
    "KeyedWriteScenario",
    "Outcome",
    "Payload",
    "Pending",
    "Phase",
    "PredicateTarget",
    "PredicateVerb",
    "PredicateWriteScenario",
    "Profile",
    "Refused",
    "Representation",
    "Revision",
    "Selection",
    "Source",
    "Start",
    "Target",
    "TargetVerb",
    "TargetWriteScenario",
    "Until",
    "Verb",
    "Window",
    "WriteScenario",
    "answer",
    "answered",
    "outcome",
    "reachable",
]


type Verb = Literal[
    "insert",
    "bounded_insert",
    "amend",
    "bounded_update",
    "delete",
    "terminate",
    "bounded_terminate",
]
type Representation = Literal["typed", "wire"]
type Concurrency = Literal["locking", "optimistic"]

type Source = Literal[
    "participating", "standalone", "read_only", "earlier_attempt", "pinned", "reread"
]
"""How the source value the verb writes was obtained.

``standalone``, ``read_only``, and ``earlier_attempt`` read the row before the
writing transaction opens — standalone, inside a read-only transaction, and
inside an earlier writable transaction that committed — so each publishes a
value no read of the writing attempt produced.

``reread`` follows a same-transaction insert with a read of the row it opened,
which is the only route by which a Wire keyed verb can write a row a TYPED
insert opened — and, because a participating read force-flushes, the route on
which the pair no longer coalesces.
"""

OUTSIDE_SOURCES: Final[tuple[Source, ...]] = ("standalone", "read_only", "earlier_attempt")
"""The sources read outside the writing attempt."""

type Change = Literal["ordinary", "net_zero", "untouched"]
"""What the caller authored over that source, for the two update verbs."""

type Window = Literal["stated", "reversed"]
"""Which Valid-Time window the call stated, for the three bounded verbs."""

type Phase = Literal["source", "verb", "flush"]
"""Where a refusal was raised: obtaining the source, at the verb, or at the flush."""

type Profile = Literal["non_temporal", "transaction_time", "bitemporal"]
"""Which As-Of Axes a target declares — the fact every verb's applicability and
window admissibility follows from, and the axis the fixed expectations are keyed
by rather than by fixture name."""

type Gate = Literal["version", "axis", "none"]
"""What supplies a target's Optimistic Lock Facet key: a declared version
column, a Transaction-Time axis, or nothing at all. A target with none has no
gate for the Optimistic strategy to weigh, so its Effective Concurrency Strategy
is Locking under either preference."""

VERBS: Final[tuple[Verb, ...]] = (
    "insert",
    "bounded_insert",
    "amend",
    "bounded_update",
    "delete",
    "terminate",
    "bounded_terminate",
)
CONCURRENCIES: Final[tuple[Concurrency, ...]] = ("locking", "optimistic")
REPRESENTATIONS: Final[tuple[Representation, ...]] = ("typed", "wire")

_INSERT_VERBS: Final[frozenset[str]] = frozenset({"insert", "bounded_insert"})
_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"amend", "bounded_update"})
VALID_FROM: Final = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
UNTIL: Final = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
TX_PIN: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
"""The finite Transaction-Time instant a ``pinned`` source stands at."""
_TX_PIN_WIRE: Final = "2024-03-01T00:00:00.000000Z"


@dataclass(frozen=True, slots=True)
class Refused:
    """The refusal a verb raised, as a caller observes it, and where it landed.

    ``error`` is the raised class itself rather than its name, so a row states the
    class it imported and a rename cannot leave two unrelated exceptions sharing
    one spelling. ``code`` is ``None`` for the refusal classes that carry no code
    — the whole of the `m-core` window and instruction vocabulary — whose message
    is then the only thing distinguishing two refusals of one class. ``phase``
    distinguishes two refusals that are otherwise identical but reach the caller
    at different points, and ``calls`` carries everything the transaction had
    already done to the database by then.
    """

    error: type[Exception]
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
class Answer:
    """What one write answered, at the grain the order fixes.

    A refusal states its class, its code, and the point it landed at; a call that
    completed states none of the three. ``statements`` is how much DML the
    transaction emitted either way, which is what separates a write from the no-op
    that buffers nothing, and a same-transaction pair that coalesces into one
    statement from two writes that stay two.

    ``message`` is stated for every refusal, wherever it landed. Neither the
    `m-core` window and instruction vocabulary nor the two planning refusals a
    write this order admitted can earn carry a code, so the message is the only
    thing distinguishing two refusals of one class — and a row that stated the
    class alone would accept a different verdict about a different rule.

    Deliberately coarser than :class:`Completed`'s whole chronology: the SQL each
    verb lowers to belongs to the per-representation lowering goldens, and what
    this suite fixes is which answer the order gives, not how it is spelled.
    """

    error: type[Exception] | None
    code: str | None
    message: str | None
    phase: Phase | None
    statements: int


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
    what write preparation admits.

    ``profile`` and ``gate`` are the two model facts a fixed expectation is keyed
    by: which verbs the target admits and which window they may state, and what
    the Optimistic strategy has to gate on.
    """

    name: str
    profile: Profile
    gate: Gate
    model: DomainModel
    entity: str
    row: MappingRow
    typed_query: ObjectQuery[EntityBase, EntityBase]
    wire_query: Mapping[str, object]
    fresh: Callable[[], EntityBase]
    payload: Mapping[str, object]
    inserted_row: MappingRow
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
        query.as_of(valid_time=VALID_FROM)
        if tx_time is None
        else query.as_of(valid_time=VALID_FROM, tx_time=tx_time)
    )
    return cast("ObjectQuery[EntityBase, EntityBase]", pinned)


def _wire_query(
    entity: str, key: int, temporal: Mapping[str, object] | None = None
) -> Mapping[str, object]:
    query: dict[str, object] = {
        "target": entity,
        "predicate": {"eq": {"path": f"{entity}.id", "value": key}},
    }
    if temporal is not None:
        query["temporal"] = temporal
    return query


_LATEST_TX: Final[Mapping[str, object]] = {"transaction-time": {"asOf": "latest"}}
_VALID_FROM_WIRE: Final = "2024-07-01T00:00:00.000000Z"
_LATEST_BOTH: Final[Mapping[str, object]] = {
    "transaction-time": {"asOf": "latest"},
    "valid-time": {"asOf": _VALID_FROM_WIRE},
}


def _position_row(
    key: int, acct_num: str, value: Decimal, from_z: dt.datetime, in_z: dt.datetime = _TX_START
) -> MappingRow:
    return {
        "id": key,
        "acct_num": acct_num,
        "value": value,
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": in_z,
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
    profile="non_temporal",
    gate="version",
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
    profile="non_temporal",
    gate="none",
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
    profile="transaction_time",
    gate="axis",
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
        "in_z": FIXED,
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
# fixture whose changed member is anything but one scalar, so each lane's
# restoration rule is asked of a whole occurrence rather than of a leaf.
CONTACT_TARGET: Final = Target(
    name="contact",
    profile="non_temporal",
    gate="none",
    model=CONTACT,
    entity=_CONTACT,
    row={"id": 1, "name": "Ada", "address": PresentDocument(dict(_STORED_DOCUMENT))},
    typed_query=_contact_query(),
    wire_query=_wire_query(_CONTACT, 1),
    # The row a fresh insert opens holds the value the STORED row holds, not the
    # one an ordinary change authors: a target whose opened row already held the
    # authored value would make every ordinary write over an insert source a
    # no-op, which is what the net-zero rows beside it are for.
    fresh=lambda: mm.Contact(id=4, name="Newton", address=_STORED_ADDRESS),
    payload={"id": 4, "name": "Newton", "address": dict(_STORED_DOCUMENT)},
    inserted_row={"id": 4, "name": "Newton", "address": PresentDocument(dict(_STORED_DOCUMENT))},
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
    profile="non_temporal",
    gate="none",
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
    profile="bitemporal",
    gate="axis",
    model=WHERE_POSITION_META,
    entity=_POSITION,
    row=_position_row(1, "A", Decimal("100.00"), _TX_START),
    typed_query=_position_query(),
    wire_query=_wire_query(_POSITION, 1, _LATEST_BOTH),
    fresh=lambda: WherePosition(id=2, acct_num="B", value=Decimal("10.00")),
    payload={"id": 2, "acctNum": "B", "value": "10.00"},
    inserted_row=_position_row(2, "B", Decimal("10.00"), VALID_FROM, FIXED),
    inserted_typed_query=_position_query(2),
    inserted_wire_query=_wire_query(_POSITION, 2, _LATEST_BOTH),
    change_typed={"value": Decimal("300.00")},
    change_wire={"value": "300.00"},
    stored_typed={"value": Decimal("100.00")},
    stored_wire={"value": "100.00"},
    valid_from=VALID_FROM,
    pinned_typed_query=_position_query(tx_time=TX_PIN),
    pinned_wire_query=_wire_query(
        _POSITION,
        1,
        {"transaction-time": {"asOf": _TX_PIN_WIRE}, "valid-time": {"asOf": _VALID_FROM_WIRE}},
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
class KeyedWriteScenario:
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
    lost_provenance: bool = False
    """Whether the Wire source reaches the verb as a copy carrying no Read Evidence
    — the one defect a keyed source can arrive with that no Typed value has a
    spelling for, and the argument the shape of an authored document is judged
    ahead of."""
    wire_changes: Mapping[str, object] | None = None
    """A Wire-only authored document, for shapes no Typed caller can express: the
    change set of an update verb, or the members an insert's payload states over
    and above the fixture's own."""
    typed_changes: Mapping[str, object] | None = None
    """The Typed spelling of the same authoring, for the rows that pin where a
    Typed assignment the model does not admit is judged."""
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
        if self.lost_provenance:
            parts.append("lost-provenance")
        return "-".join(parts)


type PredicateVerb = Literal["amend", "delete", "terminate"]
"""The base verb of a ``_where`` call: ``amend`` is ``amend_where``."""

type Selection = Literal["ordinary", "inverted", "unbound", "unshaped"]
"""What the selecting predicate states.

``ordinary`` selects the target's stored object by key. ``inverted`` is a
well-formed range whose bounds `m-predicate` refuses once the model binds it.
``unbound`` names a member the target does not declare through an unfinished
Typed path, which only the Typed representation can author. ``unshaped`` is each
representation's own shape fault: a Typed query carrying a result-shaping clause,
and a Wire predicate node the canonical algebra has no spelling for.
"""

type Assignments = Literal["ordinary", "undeclared", "none"]
"""What an amendment assigns: the target's own member, a member the target does
not declare, or nothing at all. The destructive and close verbs assign nothing
whatever this states."""

type Start = Literal["omitted", "stated", "none", "naive", "unspellable"]
"""The ``valid_from`` keyword a call states: omitted, an instant, a stated
``None``, a naive datetime, or an aware datetime whose instant no UTC spelling
holds."""

type Until = Literal["omitted", "stated", "none", "reversed", "equal", "naive", "unspellable"]
"""The ``until`` keyword a call states, as :data:`Start` states ``valid_from``,
plus a bound before :data:`VALID_FROM` and one at it."""

_PREDICATE_KEY: Final = 1
_REVERSED_UNTIL: Final = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_NAIVE_INSTANT: Final = dt.datetime(2024, 7, 1)
_UNSPELLABLE_INSTANT: Final = dt.datetime.min.replace(tzinfo=dt.timezone(dt.timedelta(hours=14)))


@dataclass(frozen=True, slots=True)
class PredicateTarget:
    """One predicate-write target, addressable from both representations.

    ``entity_class`` spells the Typed selection and ``entity`` the Wire one, over
    the same key. ``row`` is what a resolving read of that selection answers,
    and ``materializes`` whether an admitted write makes that read at all: the
    port is scripted for it, so a write that reads when it should not, or the
    reverse, fails at the unscripted call. ``fresh`` and ``payload`` open an
    unrelated object of the same Entity, in each representation, for the rows
    whose claim is what a pending write does around the predicate write.
    """

    name: str
    profile: Profile
    model: DomainModel
    entity: str
    entity_class: type[EntityBase]
    row: MappingRow
    materializes: bool
    typed_change: AttributeAssignment[Any]
    wire_change: Mapping[str, object]
    typed_undeclared: AttributeAssignment[Any]
    """A Typed assignment through an Entity other than the target, which names no
    member of it."""
    valid_from: dt.datetime | None = None
    fresh: Callable[[], EntityBase] | None = None
    payload: Mapping[str, object] | None = None


PERSON_SELECTION: Final = PredicateTarget(
    name="person",
    profile="non_temporal",
    model=PERSON,
    entity=_PERSON,
    entity_class=mm.Person,
    row={"id": 1, "name": "Ada"},
    materializes=False,
    typed_change=mm.Person.name.set("Grace"),
    wire_change={"name": "Grace"},
    typed_undeclared=mm.Account.owner.set("Grace"),
    fresh=lambda: mm.Person(id=9, name="Newton"),
    payload={"id": 9, "name": "Newton"},
)

ACCOUNT_SELECTION: Final = PredicateTarget(
    name="account",
    profile="non_temporal",
    model=ACCOUNT,
    entity=_ACCOUNT,
    entity_class=mm.Account,
    row={"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4},
    materializes=True,
    typed_change=mm.Account.balance.set(Decimal("125.00")),
    wire_change={"balance": "125.00"},
    typed_undeclared=mm.Person.name.set("Grace"),
)

BALANCE_SELECTION: Final = PredicateTarget(
    name="balance",
    profile="transaction_time",
    model=BALANCE,
    entity=_BALANCE,
    entity_class=mm.Balance,
    row=balance_row(in_z=_TX_START),
    materializes=True,
    typed_change=mm.Balance.value.set(Decimal("125.00")),
    wire_change={"value": "125.00"},
    typed_undeclared=mm.Person.name.set("Grace"),
)

POSITION_SELECTION: Final = PredicateTarget(
    name="position",
    profile="bitemporal",
    model=WHERE_POSITION_META,
    entity=_POSITION,
    entity_class=WherePosition,
    row=_position_row(1, "A", Decimal("100.00"), _TX_START),
    materializes=True,
    typed_change=WherePosition.value.set(Decimal("300.00")),
    wire_change={"value": "300.00"},
    typed_undeclared=mm.Person.name.set("Grace"),
    valid_from=VALID_FROM,
    fresh=lambda: WherePosition(id=2, acct_num="B", value=Decimal("10.00")),
    payload={"id": 2, "acctNum": "B", "value": "10.00"},
)

# A table-per-hierarchy family member: a set-based write over it is refused
# whatever it assigns. The Typed undeclared assignment is the inherited member
# addressed through its declaring root, which names no member of the exact target.
CARD_PAYMENT_SELECTION: Final = PredicateTarget(
    name="card-payment",
    profile="non_temporal",
    model=PAYMENT,
    entity="parallax.compatibility.CardPayment",
    entity_class=im.CardPayment,
    row={"id": 1, "amount": Decimal("1.00"), "card_network": "visa"},
    materializes=False,
    typed_change=im.CardPayment.card_network.set("visa"),
    wire_change={"cardNetwork": "visa"},
    typed_undeclared=im.Payment.amount.set(Decimal("1.00")),
)

# An Entity the connected model does not declare, spelled the same way through
# either representation: the Account class and its canonical name against a model
# of Person alone.
UNDECLARED_SELECTION: Final = PredicateTarget(
    name="undeclared",
    profile="non_temporal",
    model=PERSON,
    entity=_ACCOUNT,
    entity_class=mm.Account,
    row={"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4},
    materializes=False,
    typed_change=mm.Account.owner.set("Grace"),
    wire_change={"owner": "Grace"},
    typed_undeclared=mm.Person.name.set("Grace"),
)


@dataclass(frozen=True, slots=True)
class PredicateWriteScenario:
    """One predicate-selected write, stated without naming a representation.

    It carries no source, pin, provenance, or insertion authority: a predicate
    write consults none, so no participating-source read is scripted for it.
    """

    target: PredicateTarget
    verb: PredicateVerb
    valid_from: Start = "omitted"
    until: Until = "omitted"
    selection: Selection = "ordinary"
    assignments: Assignments = "ordinary"
    concurrency: Concurrency = "optimistic"
    pending: bool = False
    """Whether an insert of :attr:`PredicateTarget.fresh` is buffered, in the
    scenario's own representation, ahead of the predicate write."""
    label: str = field(default="", compare=False)

    def __str__(self) -> str:
        if self.label:
            return self.label
        parts = [self.target.name, f"{self.verb}_where", self.concurrency]
        if self.valid_from != "omitted":
            parts.append(f"valid-from-{self.valid_from}")
        if self.until != "omitted":
            parts.append(f"until-{self.until}")
        if self.selection != "ordinary":
            parts.append(f"{self.selection}-selection")
        if self.verb == "amend" and self.assignments != "ordinary":
            parts.append(f"{self.assignments}-assignments")
        if self.pending:
            parts.append("pending")
        return "-".join(parts)


type TargetVerb = Literal["amend", "replace", "delete", "terminate"]
"""The base verb of an ``_if`` call: ``amend`` is ``amend_if``."""

type Revision = Literal[
    "applicable", "omitted", "none", "misstated", "both", "both_none", "ill_typed", "stale"
]
"""The revision keywords a call states.

``applicable`` is the one kind the target has, at the value it stores;
``stale`` is that kind at a value it no longer stores. ``none`` states that
kind as ``None``, ``misstated`` the other kind instead, ``both`` and
``both_none`` the two kinds together, with values or as ``None``, and
``ill_typed`` the applicable kind at a value of the wrong type. A target with no
revision kind states ``version`` wherever a kind is applicable.
"""

type Payload = Literal[
    "ordinary",
    "empty",
    "undeclared",
    "mapping_key",
    "extra_member",
    "observation_key",
    "unshaped",
    "incomplete",
]
"""What the addressed input states beside its key.

``ordinary`` is the verb's own payload: an amendment's change, a replacement's
complete state, and nothing for a destructive or close verb. ``empty`` is an
amendment of nothing. ``undeclared`` names a member the target does not
declare. ``mapping_key`` addresses the object by a mapping where a Typed key is
one scalar value, which only a Typed call can state. The rest are Wire documents
no Typed call has a spelling for: a destructive key carrying a declared member
beside the key, a reserved observation key, a document that is no mapping, and
a replacement missing its required members.
"""

type Address = Literal["spelled", "published", "published_with_data", "unaddressable"]
"""How the call names its object.

``spelled`` names the Entity — its class, or its Wire spelling — or, for a Typed
replacement, supplies a fresh instance. ``published`` supplies the value a
standalone read published before the writing transaction opened: a Typed
instance or a Wire node, which only a replacement takes as its state and which a
Wire caller can hand any verb. ``published_with_data`` is that Wire node beside
a document. ``unaddressable`` names neither an Entity Class nor a spelling.
"""

type Pending = Literal["none", "unrelated", "addressed"]
"""What is buffered, in the scenario's own representation, ahead of the
conditional write: nothing, an insert of an unrelated object, or an insert of
the very object the write addresses."""

_STALE_VERSION: Final = 3
_STALE_TX_START: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)


@dataclass(frozen=True, slots=True)
class ConditionalTarget:
    """One conditional-write target, addressable from both representations.

    ``entity_class`` spells the Typed address and ``entity`` the Wire one, of
    the object keyed ``1``. ``row`` is what a read of that object answers — the
    acquisition a Locking call makes, the coverage an Optimistic temporal flush
    reads, or the standalone read a published value comes from — and stores the
    revision an ``applicable`` call states. The change and replacement come in a
    Typed and a Wire spelling of one value; ``fresh`` and ``payload`` open an
    unrelated object of the same Entity. ``valid_from`` is the start an insert
    of this target states.
    """

    name: str
    profile: Profile
    gate: Gate
    model: DomainModel
    entity: str
    entity_class: type[EntityBase]
    row: MappingRow
    typed_change: AttributeAssignment[Any]
    wire_change: Mapping[str, object]
    typed_replacement: Callable[[], EntityBase]
    wire_replacement: Mapping[str, object]
    typed_query: ObjectQuery[EntityBase, EntityBase]
    wire_query: Mapping[str, object]
    fresh: Callable[[], EntityBase]
    payload: Mapping[str, object]
    valid_from: dt.datetime | None = None


ACCOUNT_CONDITIONAL: Final = ConditionalTarget(
    name="account",
    profile="non_temporal",
    gate="version",
    model=ACCOUNT,
    entity=_ACCOUNT,
    entity_class=mm.Account,
    row=ACCOUNT_TARGET.row,
    typed_change=mm.Account.balance.set(Decimal("125.00")),
    wire_change={"balance": "125.00"},
    typed_replacement=lambda: mm.Account(id=1, owner="Zed", balance=Decimal("3.00")),
    wire_replacement={"id": 1, "owner": "Zed", "balance": "3.00"},
    typed_query=ACCOUNT_TARGET.typed_query,
    wire_query=ACCOUNT_TARGET.wire_query,
    fresh=ACCOUNT_TARGET.fresh,
    payload=ACCOUNT_TARGET.payload,
)

PERSON_CONDITIONAL: Final = ConditionalTarget(
    name="person",
    profile="non_temporal",
    gate="none",
    model=PERSON,
    entity=_PERSON,
    entity_class=mm.Person,
    row=PERSON_TARGET.row,
    typed_change=mm.Person.name.set("Grace"),
    wire_change={"name": "Grace"},
    typed_replacement=lambda: mm.Person(id=1, name="Grace"),
    wire_replacement={"id": 1, "name": "Grace"},
    typed_query=PERSON_TARGET.typed_query,
    wire_query=PERSON_TARGET.wire_query,
    fresh=PERSON_TARGET.fresh,
    payload=PERSON_TARGET.payload,
)

BALANCE_CONDITIONAL: Final = ConditionalTarget(
    name="balance",
    profile="transaction_time",
    gate="axis",
    model=BALANCE,
    entity=_BALANCE,
    entity_class=mm.Balance,
    row=BALANCE_TARGET.row,
    typed_change=mm.Balance.value.set(Decimal("125.00")),
    wire_change={"value": "125.00"},
    typed_replacement=lambda: mm.Balance(id=1, acct_num="Z", value=Decimal("7.00")),
    wire_replacement={"id": 1, "acctNum": "Z", "value": "7.00"},
    typed_query=BALANCE_TARGET.typed_query,
    wire_query=BALANCE_TARGET.wire_query,
    fresh=BALANCE_TARGET.fresh,
    payload=BALANCE_TARGET.payload,
)

POSITION_CONDITIONAL: Final = ConditionalTarget(
    name="position",
    profile="bitemporal",
    gate="axis",
    model=WHERE_POSITION_META,
    entity=_POSITION,
    entity_class=WherePosition,
    row=POSITION_TARGET.row,
    typed_change=WherePosition.value.set(Decimal("300.00")),
    wire_change={"value": "300.00"},
    typed_replacement=lambda: WherePosition(id=1, acct_num="Z", value=Decimal("300.00")),
    wire_replacement={"id": 1, "acctNum": "Z", "value": "300.00"},
    typed_query=POSITION_TARGET.typed_query,
    wire_query=POSITION_TARGET.wire_query,
    fresh=POSITION_TARGET.fresh,
    payload=POSITION_TARGET.payload,
    valid_from=VALID_FROM,
)

# An Entity the connected model does not declare, spelled the same way through
# either representation: the Account class and its canonical name against a model
# of Person alone.
UNDECLARED_CONDITIONAL: Final = ConditionalTarget(
    name="undeclared",
    profile="non_temporal",
    gate="version",
    model=PERSON,
    entity=_ACCOUNT,
    entity_class=mm.Account,
    row=ACCOUNT_TARGET.row,
    typed_change=mm.Account.balance.set(Decimal("125.00")),
    wire_change={"balance": "125.00"},
    typed_replacement=lambda: mm.Account(id=1, owner="Zed", balance=Decimal("3.00")),
    wire_replacement={"id": 1, "owner": "Zed", "balance": "3.00"},
    typed_query=ACCOUNT_TARGET.typed_query,
    wire_query=ACCOUNT_TARGET.wire_query,
    fresh=ACCOUNT_TARGET.fresh,
    payload=ACCOUNT_TARGET.payload,
)


@dataclass(frozen=True, slots=True)
class TargetWriteScenario:
    """One caller-addressed conditional write, stated without naming a
    representation.

    It carries no source, pin, provenance, or insertion authority: a conditional
    write consults none, so the only read scripted for it is the one its
    target's revision kind and Concurrency Preference make, and a ``published``
    value's standalone read outside the writing transaction.
    """

    target: ConditionalTarget
    verb: TargetVerb
    revision: Revision = "applicable"
    valid_from: Start = "omitted"
    until: Until = "omitted"
    payload: Payload = "ordinary"
    address: Address = "spelled"
    concurrency: Concurrency = "optimistic"
    pending: Pending = "none"
    label: str = field(default="", compare=False)

    def __str__(self) -> str:
        if self.label:
            return self.label
        parts = [self.target.name, f"{self.verb}_if", self.concurrency]
        if self.revision != "applicable":
            parts.append(f"revision-{self.revision}")
        if self.valid_from != "omitted":
            parts.append(f"valid-from-{self.valid_from}")
        if self.until != "omitted":
            parts.append(f"until-{self.until}")
        if self.payload != "ordinary":
            parts.append(f"{self.payload}-payload")
        if self.address != "spelled":
            parts.append(self.address)
        if self.pending != "none":
            parts.append(f"pending-{self.pending}")
        return "-".join(parts)


_WIRE_ONLY_PAYLOADS: Final[frozenset[Payload]] = frozenset(
    {"extra_member", "observation_key", "unshaped", "incomplete"}
)


type WriteScenario = KeyedWriteScenario | PredicateWriteScenario | TargetWriteScenario


def reachable(scenario: WriteScenario, representation: Representation) -> bool:
    """Whether ``representation`` can issue ``scenario`` at all.

    One keyed shape is not reachable: a keyed write through the insertion source
    of an insert the OTHER interface stated. Only the inserted instance and the
    values derived from it carry a Typed insert's authority, and only the node a
    Wire insert answered carries a Wire insert's, so neither interface holds a
    source of the other's insert; an independently built value of the same key
    is no source at all. Reading the row produces one in either interface, and
    that route is the ``reread`` source — a different scenario, not this one.

    The exclusion is about SOURCE verbs. An insert of the same object through
    the other interface needs no source — its payload is fresh — so that
    crossing is reachable, and is exactly the one the repeated-insert refusal
    is asked over.

    One predicate shape is Typed alone: an ``unbound`` selection, whose
    unfinished path no Wire document has a spelling for.

    A conditional shape is reachable where its representation spells it: a
    mapping key is Typed alone; the Wire-only documents, a published node handed
    a verb other than a replacement or beside data, and a destructive or
    replacing write naming an undeclared member are Wire alone; and a Typed
    replacement is always addressed by an instance.
    """
    if isinstance(scenario, PredicateWriteScenario):
        return scenario.selection != "unbound" or representation == "typed"
    if isinstance(scenario, TargetWriteScenario):
        return _target_reachable(scenario, representation)
    return not (
        scenario.opened_by is not None
        and representation != scenario.opened_by
        and scenario.source != "reread"
        and scenario.verb not in _INSERT_VERBS
    )


def answer(scenario: WriteScenario, representation: Representation) -> Answer:
    """Run ``scenario`` through ``representation`` and report what it answered.

    The reading a fixed expectation is stated against: :func:`outcome`'s report
    reduced by :func:`answered`, so a row states the answer the write's order
    gives rather than the statements one representation happens to lower it to.
    """
    return answered(outcome(scenario, representation))


def answered(result: Outcome) -> Answer:
    """``result`` with the SQL dropped and the DML counted."""
    statements = sum(1 for call in result.calls if isinstance(call, WriteCall))
    if isinstance(result, Refused):
        return Answer(result.error, result.code, result.message, result.phase, statements)
    return Answer(None, None, None, None, statements)


def _refused(raised: Exception, phase: Phase, port: ScriptedAdapter) -> Refused:
    """The refusal ``raised`` states, in the four facts a row is graded on.

    A refusal escaping the transaction arrives as the cause of an
    ``ExecutionFailure``; what the order judged is that cause, so it is
    reported unwrapped, exactly as a refusal raised obtaining an outside source is.
    """
    return Refused(
        type(raised),
        cast("str | None", getattr(raised, "code", None)),
        str(raised),
        phase,
        tuple(port.calls),
    )


def outcome(scenario: WriteScenario, representation: Representation) -> Outcome:
    """Run ``scenario`` through ``representation`` and report what it produced.

    Only a refusal the product raised is reported as one. An ``AssertionError``
    is the harness speaking — an unscripted call, or a driver's own claim about
    the fixture — and propagates, because a row that serialized it as a refusal
    could report two broken lanes as one agreement.
    """
    if isinstance(scenario, TargetWriteScenario):
        port = _target_port(scenario)
        return _observed(
            port,
            db_for(scenario.target.model, port),
            scenario.concurrency,
            lambda db: _published(db, scenario, representation),
            lambda tx, prior: _target_body(tx, scenario, representation, prior),
            lambda: _assert_the_target_reads_were_reached(port, scenario),
        )
    if isinstance(scenario, PredicateWriteScenario):
        port = _predicate_port(scenario)
        return _observed(
            port,
            db_for(scenario.target.model, port),
            scenario.concurrency,
            lambda _db: None,
            lambda tx, _prior: _predicate_body(tx, scenario, representation),
            lambda: _assert_the_resolving_read_was_reached(port, scenario),
        )
    port = _port(scenario)
    return _observed(
        port,
        db_for(scenario.target.model, port),
        scenario.concurrency,
        lambda db: _outside_source(db, scenario, representation),
        lambda tx, prior: _body(tx, scenario, representation, prior),
        lambda: _assert_the_scripted_read_was_reached(port, scenario),
    )


def _observed(
    port: ScriptedAdapter,
    db: ScopedDatabase,
    concurrency: Concurrency,
    source: Callable[[ScopedDatabase], object | None],
    write: Callable[[TxnContext, object | None], None],
    reached: Callable[[], None],
) -> Outcome:
    """Obtain any outside source, then run ``write`` in one transaction, and
    report the refusal and the phase it landed in, or the chronology of a
    completed write once ``reached`` has confirmed its scripted reads ran."""
    phase: Phase = "source"

    def body(tx: TxnContext) -> None:
        nonlocal phase
        write(tx, prior)
        phase = "flush"

    try:
        prior = source(db)
        phase = "verb"
        db.transact(body, concurrency=concurrency)
    except AssertionError:
        raise
    except ExecutionFailure as failed:
        underlying = failed.cause
    except Exception as raised:
        return _refused(raised, phase, port)
    else:
        reached()
        return Completed(tuple(port.calls))
    # Outside the handler, so the wrapper enters neither the chain of the
    # harness's own claim nor that of the refusal a row is graded on.
    if isinstance(underlying, AssertionError):
        raise underlying
    return _refused(underlying, phase, port)


def _reads_the_stored_row(scenario: KeyedWriteScenario) -> bool:
    """Whether this scenario's source comes from a read of the target's own row.

    An insert ordinarily authors a fresh payload and reads nothing. The one
    exception is the pinned source, which every verb including the two insert
    ones is stated over: what the insert door is handed there is the published
    node itself, which is exactly the argument the pin refusal is about.
    """
    reads = scenario.verb not in _INSERT_VERBS or scenario.source == "pinned"
    return reads and scenario.opened_by is None


def _assert_the_scripted_read_was_reached(
    port: ScriptedAdapter, scenario: KeyedWriteScenario
) -> None:
    """Fail a row that completed without running the read its scenario states.

    The write allowance below is a budget rather than a count, so the port cannot
    be asked to assert its whole script was consumed. Its reads are exact, and a
    lane that resolved its source without one did less than the scenario says.
    """
    reads = sum(1 for call in port.calls if isinstance(call, ReadCall))
    expected = int(_reads_the_stored_row(scenario)) + int(scenario.source == "reread")
    if reads != expected:
        raise AssertionError(f"{scenario}: {expected} scripted read(s), {reads} run")


def _port(scenario: KeyedWriteScenario) -> ScriptedAdapter:
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
        return ScriptedAdapter(Transact(Write(), reread, writes))
    if scenario.source == "pinned":
        return ScriptedAdapter(Transact(read, writes))
    if scenario.verb in _INSERT_VERBS or scenario.opened_by is not None:
        return ScriptedAdapter(Transact(writes))
    if scenario.source == "standalone":
        return ScriptedAdapter(read, Transact(writes))
    if scenario.source in OUTSIDE_SOURCES:
        return ScriptedAdapter(Transact(read), Transact(writes))
    return ScriptedAdapter(Transact(read, writes))


def _outside_source(
    db: ScopedDatabase, scenario: KeyedWriteScenario, representation: Representation
) -> object | None:
    """The value a read outside the writing attempt published, or ``None`` for a
    scenario whose source the attempt obtains itself."""
    if scenario.source not in OUTSIDE_SOURCES or scenario.verb in _INSERT_VERBS:
        return None
    target = scenario.target

    def read(reader: ReadOnlyTxnContext | TxnContext | ScopedDatabase) -> object:
        if representation == "typed":
            return reader.find(target.typed_query).result()
        return reader.wire.find(target.wire_query).result()

    if scenario.source == "read_only":
        return db.read_only(read)
    if scenario.source == "earlier_attempt":
        return db.transact(read)
    return read(db)


def _body(
    tx: TxnContext,
    scenario: KeyedWriteScenario,
    representation: Representation,
    prior: object | None,
) -> None:
    if representation == "typed":
        _typed(tx, scenario, prior)
    else:
        _wire(tx, scenario, prior)


def _typed(tx: TxnContext, scenario: KeyedWriteScenario, prior: object | None) -> None:
    target = scenario.target
    if scenario.verb in _INSERT_VERBS and scenario.source != "pinned":
        _open_ahead_of_the_insert(tx, scenario, "typed")
        _call_typed(tx, scenario, target.fresh())
        return
    source = cast("EntityBase", _typed_source(tx, scenario, prior))
    _call_typed(tx, scenario, _typed_authored(scenario, source))


def _open_ahead_of_the_insert(
    tx: TxnContext, scenario: KeyedWriteScenario, representation: Representation
) -> None:
    """Buffer the same-transaction insert an INSERT scenario repeats, and on the
    ``reread`` route run the participating read that force-flushes it.

    What the read returned is discarded: the insert that follows authors a fresh
    value either way, because what the scenario states is a second opening of
    the OBJECT, not a write over the value a read published.
    """
    if scenario.opened_by is None:
        return
    _open(tx, scenario)
    if scenario.source != "reread":
        return
    if representation == "typed":
        tx.find(scenario.target.inserted_typed_query).result()
    else:
        tx.wire.find(scenario.target.inserted_wire_query).result()


def _typed_source(tx: TxnContext, scenario: KeyedWriteScenario, prior: object | None) -> object:
    target = scenario.target
    if scenario.opened_by is not None:
        opened = _open(tx, scenario)
        if scenario.source == "reread":
            return tx.find(target.inserted_typed_query).result()
        # The instance the insert took carries its authority; another instance
        # of the same key carries none.
        return opened
    if prior is not None:
        return prior
    if scenario.source == "pinned":
        assert target.pinned_typed_query is not None
        return tx.find(target.pinned_typed_query).result()
    return tx.find(target.typed_query).result()


def _typed_authored(scenario: KeyedWriteScenario, source: EntityBase) -> EntityBase:
    target = scenario.target
    if scenario.typed_changes is not None:
        return source.edit(**scenario.typed_changes)
    if scenario.verb not in _UPDATE_VERBS or scenario.change == "untouched":
        return source
    edited = source.edit(**target.change_typed)
    if scenario.change == "ordinary":
        return edited
    restored = target.opened_typed if scenario.opened_by is not None else target.stored_typed
    return edited.edit(**restored)


def _call_typed(tx: TxnContext, scenario: KeyedWriteScenario, value: EntityBase) -> None:
    plain = scenario.target.valid_from
    valid_from, until = _bounded_window(scenario)
    match scenario.verb:
        case "insert":
            tx.insert(value, **stated_start(plain))
        case "bounded_insert":
            tx.insert(value, valid_from=valid_from, until=until)
        case "amend":
            tx.amend(value)
        case "bounded_update":
            tx.amend(value, until=_source_until(scenario))
        case "delete":
            tx.delete(value)
        case "terminate":
            tx.terminate(value)
        case "bounded_terminate":
            tx.terminate(value, until=_source_until(scenario))
        case _:
            # Every `Verb` is spelled above; a verb added to one lane and not the
            # other would otherwise write nothing and read as an agreed no-op.
            raise AssertionError(f"no {scenario.verb} in this lane")


def _wire(tx: TxnContext, scenario: KeyedWriteScenario, prior: object | None) -> None:
    target = scenario.target
    if scenario.verb in _INSERT_VERBS and scenario.source != "pinned":
        _open_ahead_of_the_insert(tx, scenario, "wire")
        _call_wire(tx, scenario, target.payload, {})
        return
    source = _wire_source(tx, scenario, prior)
    if scenario.lost_provenance:
        source = dict(cast("Mapping[str, object]", source))
    _call_wire(tx, scenario, source, _wire_authored(scenario))


def _wire_source(tx: TxnContext, scenario: KeyedWriteScenario, prior: object | None) -> object:
    target = scenario.target
    if scenario.opened_by is not None:
        opened = _open(tx, scenario)
        if scenario.source == "reread":
            return tx.wire.find(target.inserted_wire_query).result()
        return opened
    if prior is not None:
        return prior
    if scenario.source == "pinned":
        assert target.pinned_wire_query is not None
        return tx.wire.find(target.pinned_wire_query).result()
    return tx.wire.find(target.wire_query).result()


def _wire_authored(scenario: KeyedWriteScenario) -> Mapping[str, object]:
    target = scenario.target
    if scenario.wire_changes is not None:
        return scenario.wire_changes
    if scenario.verb not in _UPDATE_VERBS or scenario.change == "untouched":
        return {}
    if scenario.change == "ordinary":
        return target.change_wire
    return target.opened_wire if scenario.opened_by is not None else target.stored_wire


def _call_wire(
    tx: TxnContext, scenario: KeyedWriteScenario, source: object, changes: Mapping[str, object]
) -> None:
    plain = scenario.target.valid_from
    valid_from, until = _bounded_window(scenario)
    observed = cast("WireEntity", source)
    authored = dict(changes)
    payload = _wire_payload(scenario, source)
    match scenario.verb:
        case "insert":
            tx.wire.insert(scenario.target.entity, payload, **stated_start(plain))
        case "bounded_insert":
            tx.wire.insert(scenario.target.entity, payload, valid_from=valid_from, until=until)
        case "amend":
            tx.wire.amend(observed, authored)
        case "bounded_update":
            tx.wire.amend(observed, authored, until=_source_until(scenario))
        case "delete":
            tx.wire.delete(observed)
        case "terminate":
            tx.wire.terminate(observed)
        case "bounded_terminate":
            tx.wire.terminate(observed, until=_source_until(scenario))
        case _:
            # Every `Verb` is spelled above; a verb added to one lane and not the
            # other would otherwise write nothing and read as an agreed no-op.
            raise AssertionError(f"no {scenario.verb} in this lane")


def _wire_payload(scenario: KeyedWriteScenario, source: object) -> Mapping[str, object]:
    """The Create Payload an insert states.

    A fresh document copied off the fixture, carrying whatever Wire-only members
    the scenario states beside it, or — where the scenario states a pinned
    source — the published node itself, which is the argument the insert door's
    own pin refusal is about and which a ``dict(...)`` copy would strip the view
    off.
    """
    if scenario.source == "pinned":
        return cast("Mapping[str, object]", source)
    return {**scenario.target.payload, **(scenario.wire_changes or {})}


def _bounded_window(scenario: KeyedWriteScenario) -> tuple[dt.datetime, dt.datetime]:
    """The pair a bounded insert states — ordered, or reversed onto one instant.

    A plain verb never reads it: its own bound is the target's, which is what
    keeps a Transaction-Time-Only or Non-Temporal target free of a Valid-Time
    instant it does not admit.
    """
    if scenario.window == "reversed":
        return UNTIL, VALID_FROM
    return VALID_FROM, UNTIL


def _source_until(scenario: KeyedWriteScenario) -> dt.datetime:
    """The bound a source-backed bounded verb states: its window starts at the
    source's own pin, :data:`VALID_FROM`, so a reversed window ends there too."""
    return VALID_FROM if scenario.window == "reversed" else UNTIL


def _open(tx: TxnContext, scenario: KeyedWriteScenario) -> object:
    """Buffer the same-transaction insert this scenario's source came from, and
    answer the carrier of its authority: the instance a Typed insert took, or
    the node a Wire insert answered.

    Bounded or plain: an bounded ``insert`` opens a Valid-Time-bounded rectangle
    where ``insert`` opens one running to infinity, and the write that follows it
    is licensed by the same authority either way. The opener's own window is
    always the ordered one — ``scenario.window`` states what the WRITE bounded,
    so a reversed window has to reach the write rather than be spent on the
    insert.
    """
    target = scenario.target
    if scenario.opened_by == "typed":
        inserted = target.fresh()
        if scenario.opened_until:
            tx.insert(inserted, valid_from=VALID_FROM, until=UNTIL)
        else:
            tx.insert(inserted, **stated_start(target.valid_from))
        return inserted
    if scenario.opened_until:
        return tx.wire.insert(
            target.entity, dict(target.payload), valid_from=VALID_FROM, until=UNTIL
        )
    return tx.wire.insert(target.entity, dict(target.payload), **stated_start(target.valid_from))


def _predicate_port(scenario: PredicateWriteScenario) -> ScriptedAdapter:
    """A port scripted for the one resolving read a materializing target makes,
    the pending insert that read force-flushes ahead of it, and a DML budget.

    A readless target is scripted no read at all, so a predicate write that read
    where its target admits a readless one fails at the call. A refusal consumes
    nothing, so its whole chronology is the boundary's begin and rollback.
    """
    target = scenario.target
    writes = Write(times=8)
    if not target.materializes:
        return ScriptedAdapter(Transact(writes))
    read = Read(rows=[dict(target.row)])
    if scenario.pending:
        return ScriptedAdapter(Transact(Write(), read, writes))
    return ScriptedAdapter(Transact(read, writes))


def _assert_the_resolving_read_was_reached(
    port: ScriptedAdapter, scenario: PredicateWriteScenario
) -> None:
    """Fail a row that completed without the resolving read its target makes."""
    reads = sum(1 for call in port.calls if isinstance(call, ReadCall))
    expected = int(scenario.target.materializes)
    if reads != expected:
        raise AssertionError(f"{scenario}: {expected} scripted read(s), {reads} run")


def _predicate_body(
    tx: TxnContext, scenario: PredicateWriteScenario, representation: Representation
) -> None:
    if scenario.pending:
        _open_pending(tx, scenario.target, representation)
    window = _stated_window(scenario)
    if representation == "typed":
        _call_typed_predicate(tx, scenario, window)
    else:
        _call_wire_predicate(tx, scenario, window)


def _open_pending(tx: TxnContext, target: PredicateTarget, representation: Representation) -> None:
    assert target.fresh is not None and target.payload is not None
    if representation == "typed":
        tx.insert(target.fresh(), **stated_start(target.valid_from))
    else:
        tx.wire.insert(target.entity, dict(target.payload), **stated_start(target.valid_from))


def _stated_window(scenario: PredicateWriteScenario | TargetWriteScenario) -> dict[str, Any]:
    """The window keywords exactly as the scenario states them: an omitted one
    is not passed, and every other one is, ``None`` included."""
    instants: Mapping[str, dt.datetime | None] = {
        "stated": VALID_FROM,
        "none": None,
        "naive": _NAIVE_INSTANT,
        "unspellable": _UNSPELLABLE_INSTANT,
    }
    window: dict[str, Any] = {}
    if scenario.valid_from != "omitted":
        window["valid_from"] = instants[scenario.valid_from]
    if scenario.until == "reversed":
        window["until"] = _REVERSED_UNTIL
    elif scenario.until == "equal":
        window["until"] = VALID_FROM
    elif scenario.until == "stated":
        window["until"] = UNTIL
    elif scenario.until != "omitted":
        window["until"] = instants[scenario.until]
    if window and scenario.verb == "delete":
        # Neither `delete_where` nor `delete_if` has a window keyword to state
        # one through.
        raise AssertionError(f"{scenario}: a deletion states no window")
    return window


def _typed_query(scenario: PredicateWriteScenario) -> ObjectQuery[EntityBase, EntityBase]:
    entity = scenario.target.entity_class
    key = cast("Any", entity).id
    match scenario.selection:
        case "ordinary":
            return entity.where(key == _PREDICATE_KEY)
        case "inverted":
            return entity.where(key.between(10, _PREDICATE_KEY))
        case "unbound":
            path = AuthoredPath(entity.identity, ("missing",), unfinished=True)
            return entity.where(
                Predicate(UnfinishedOperation(path, COMPARE["eq"], (_PREDICATE_KEY,)))
            )
        case "unshaped":
            return entity.where(key == _PREDICATE_KEY).limit(1)


def _typed_assignments(scenario: PredicateWriteScenario) -> tuple[AttributeAssignment[Any], ...]:
    if scenario.verb != "amend" or scenario.assignments == "none":
        return ()
    target = scenario.target
    return (target.typed_change if scenario.assignments == "ordinary" else target.typed_undeclared,)


def _call_typed_predicate(
    tx: TxnContext, scenario: PredicateWriteScenario, window: Mapping[str, Any]
) -> None:
    query = _typed_query(scenario)
    match scenario.verb:
        case "amend":
            tx.amend_where(query, *_typed_assignments(scenario), **window)
        case "delete":
            tx.delete_where(query)
        case "terminate":
            tx.terminate_where(query, **window)


def _wire_selection(scenario: PredicateWriteScenario) -> Mapping[str, object]:
    entity = scenario.target.entity
    path = f"{entity}.id"
    match scenario.selection:
        case "ordinary":
            predicate: Mapping[str, object] = {"eq": {"path": path, "value": _PREDICATE_KEY}}
        case "inverted":
            predicate = {"between": {"path": path, "lower": 10, "upper": _PREDICATE_KEY}}
        case "unshaped":
            predicate = {"nonsense": {}}
        case "unbound":
            raise AssertionError(f"{scenario}: no Wire document spells an unfinished path")
    return {"entity": entity, "predicate": predicate}


def _wire_changes(scenario: PredicateWriteScenario) -> Mapping[str, object]:
    match scenario.assignments:
        case "ordinary":
            return dict(scenario.target.wire_change)
        case "undeclared":
            return {"undeclared": 1}
        case "none":
            return {}


def _call_wire_predicate(
    tx: TxnContext, scenario: PredicateWriteScenario, window: Mapping[str, Any]
) -> None:
    selection = _wire_selection(scenario)
    match scenario.verb:
        case "amend":
            tx.wire.amend_where(selection, _wire_changes(scenario), **window)
        case "delete":
            tx.wire.delete_where(selection)
        case "terminate":
            tx.wire.terminate_where(selection, **window)


def _target_reachable(scenario: TargetWriteScenario, representation: Representation) -> bool:
    if representation == "wire":
        return scenario.payload != "mapping_key"
    if scenario.payload in _WIRE_ONLY_PAYLOADS or scenario.address == "published_with_data":
        return False
    if scenario.verb == "replace":
        return scenario.address != "unaddressable" and scenario.payload != "undeclared"
    if scenario.address == "published":
        return False
    return scenario.payload != "undeclared" or scenario.verb == "amend"


def _target_reads_its_row(scenario: TargetWriteScenario) -> bool:
    """Whether an admitted write of this scenario reads its object's row inside
    the writing transaction: a Locking call acquires it at the call, and an
    Optimistic temporal flush reads the coverage it reaches. An amendment of
    nothing is dropped before either."""
    reads = scenario.concurrency == "locking" or scenario.target.profile != "non_temporal"
    return reads and not (scenario.verb == "amend" and scenario.payload == "empty")


def _target_port(scenario: TargetWriteScenario) -> ScriptedAdapter:
    """A port scripted for the standalone read a published value comes from,
    the one read of the object an admitted write makes, any pending insert,
    and a DML budget.

    A Locking call reads at the call, ahead of every pending statement the
    commit flushes. An Optimistic temporal write reads its coverage at the
    flush, after the pending insert ahead of it. A write that reads nothing —
    an Optimistic Non-Temporal one, or an amendment of nothing — is scripted no
    read, so a write that read there fails at the unscripted call.
    """
    target = scenario.target
    writes = Write(times=8)
    read = Read(rows=[dict(target.row)])
    if not _target_reads_its_row(scenario):
        body: tuple[Read | Write, ...] = (writes,)
    elif scenario.concurrency == "locking":
        body = (read, writes)
    else:
        pending = (Write(),) if scenario.pending != "none" else ()
        body = (*pending, read, writes)
    published = (Read(rows=[dict(target.row)]),) if _publishes(scenario) else ()
    return ScriptedAdapter(*published, Transact(*body))


def _publishes(scenario: TargetWriteScenario) -> bool:
    return scenario.address in ("published", "published_with_data")


def _assert_the_target_reads_were_reached(
    port: ScriptedAdapter, scenario: TargetWriteScenario
) -> None:
    """Fail a row that completed without every read its scenario states."""
    reads = sum(1 for call in port.calls if isinstance(call, ReadCall))
    expected = int(_publishes(scenario)) + int(_target_reads_its_row(scenario))
    if reads != expected:
        raise AssertionError(f"{scenario}: {expected} scripted read(s), {reads} run")


def _published(
    db: ScopedDatabase, scenario: TargetWriteScenario, representation: Representation
) -> object | None:
    """The value a standalone read published before the writing transaction
    opened, or ``None`` for a scenario that names its object itself."""
    if not _publishes(scenario):
        return None
    target = scenario.target
    if representation == "typed":
        return db.find(target.typed_query).result()
    return db.wire.find(target.wire_query).result()


def _target_body(
    tx: TxnContext,
    scenario: TargetWriteScenario,
    representation: Representation,
    published: object | None,
) -> None:
    if scenario.pending != "none":
        _open_ahead_of_the_target(tx, scenario, representation)
    window = _stated_window(scenario)
    revision = _stated_revision(scenario)
    if representation == "typed":
        _call_typed_target(tx, scenario, published, {**revision, **window})
    else:
        _call_wire_target(tx, scenario, published, {**revision, **window})


def _open_ahead_of_the_target(
    tx: TxnContext, scenario: TargetWriteScenario, representation: Representation
) -> None:
    target = scenario.target
    addressed = scenario.pending == "addressed"
    start = stated_start(target.valid_from)
    if representation == "typed":
        tx.insert(target.typed_replacement() if addressed else target.fresh(), **start)
        return
    payload = target.wire_replacement if addressed else target.payload
    tx.wire.insert(target.entity, dict(payload), **start)


def _stated_revision(scenario: TargetWriteScenario) -> dict[str, Any]:
    """The revision keywords exactly as the scenario states them."""
    stored = scenario.target.row
    if scenario.target.gate == "axis":
        applicable, other = "tx_start", "version"
        value: object = stored["in_z"]
        stale: object = _STALE_TX_START
        ill_typed: object = "2024-01-01"
    else:
        applicable, other = "version", "tx_start"
        value = stored.get("version", 1)
        stale = _STALE_VERSION
        ill_typed = True
    values: Mapping[str, object] = {"version": 4, "tx_start": _TX_START}
    match scenario.revision:
        case "applicable":
            return {applicable: value}
        case "omitted":
            return {}
        case "none":
            return {applicable: None}
        case "misstated":
            return {other: values[other]}
        case "both":
            return {applicable: value, other: values[other]}
        case "both_none":
            return {"version": None, "tx_start": None}
        case "ill_typed":
            return {applicable: ill_typed}
        case "stale":
            return {applicable: stale}


def _undeclared_assignment(target: ConditionalTarget) -> AttributeAssignment[Any]:
    """An assignment of a member ``target`` does not declare, as a caller could
    construct one without ``Attr.set``."""
    return AttributeAssignment(AttributeRef(target.entity, "nickname"), "x")


def _call_typed_target(
    tx: TxnContext,
    scenario: TargetWriteScenario,
    published: object | None,
    keywords: Mapping[str, Any],
) -> None:
    target = scenario.target
    entity_class = (
        cast("type[EntityBase]", int)
        if scenario.address == "unaddressable"
        else target.entity_class
    )
    key: object = {"id": 1} if scenario.payload == "mapping_key" else 1
    match scenario.verb:
        case "amend":
            assignments = _typed_target_assignments(scenario)
            tx.amend_if(entity_class, *assignments, key=key, **keywords)
        case "replace":
            instance = (
                cast("EntityBase", published)
                if published is not None
                else target.typed_replacement()
            )
            tx.replace_if(instance, **keywords)
        case "delete":
            tx.delete_if(entity_class, key=key, **keywords)
        case "terminate":
            tx.terminate_if(entity_class, key=key, **keywords)


def _typed_target_assignments(
    scenario: TargetWriteScenario,
) -> tuple[AttributeAssignment[Any], ...]:
    target = scenario.target
    match scenario.payload:
        case "ordinary" | "mapping_key":
            return (target.typed_change,)
        case "empty":
            return ()
        case "undeclared":
            return (_undeclared_assignment(target),)
        case _:
            # A payload no Typed amendment spells must not reach the verb as a
            # lookup failure the runner would report as a product refusal.
            raise AssertionError(f"{scenario}: no Typed amendment spells this payload")


def _wire_document(scenario: TargetWriteScenario) -> object:
    """The document a Wire call states beside its address."""
    target = scenario.target
    if scenario.payload == "unshaped":
        return ["id", 1]
    if scenario.verb == "replace":
        base: dict[str, object] = (
            {"id": 1} if scenario.payload == "incomplete" else dict(target.wire_replacement)
        )
    elif scenario.payload == "extra_member" or (
        scenario.verb == "amend" and scenario.payload != "empty"
    ):
        base = {"id": 1, **target.wire_change}
    else:
        base = {"id": 1}
    if scenario.payload == "undeclared":
        base["nickname"] = "x"
    elif scenario.payload == "observation_key":
        base["observedVersion"] = 4
    return base


def _call_wire_target(
    tx: TxnContext,
    scenario: TargetWriteScenario,
    published: object | None,
    keywords: Mapping[str, Any],
) -> None:
    address: Any = (
        published
        if published is not None
        else 42
        if scenario.address == "unaddressable"
        else scenario.target.entity
    )
    document: Any = _wire_document(scenario)
    match scenario.verb:
        case "amend":
            tx.wire.amend_if(address, document, **keywords)
        case "replace":
            if scenario.address == "published":
                tx.wire.replace_if(address, **keywords)
            else:
                tx.wire.replace_if(address, document, **keywords)
        case "delete":
            tx.wire.delete_if(address, document, **keywords)
        case "terminate":
            tx.wire.terminate_if(address, document, **keywords)
