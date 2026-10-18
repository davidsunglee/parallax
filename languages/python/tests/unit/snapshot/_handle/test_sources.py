"""Keyed-source interpretation, asked of every carrier either representation hands a verb.

Each row obtains a value the way a caller does — a read in some placement, an
edit, an insert, a conversion — hands it to the production adapter its verb
constructs, and states what the resolved record answers. The table is the one
statement of which carrier answers which provenance, Pin, evidence, and
authority; what the order then does with the answer belongs to
`test_keyed_write_order.py`, and what each adapter authors to the two
representation suites beside this one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, cast

import pytest

from parallax.conformance.vo_models import CONTACT_MODEL, Contact
from parallax.core import LATEST, DomainModel
from parallax.core._execution._keyed_writes import (
    Provenance,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
)
from parallax.core._execution._unit_work.retain import KeyedWriteRefusalAdvice
from parallax.core.base import PresentDocument
from parallax.core.db_port import MappingRow
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import EntityGraphWriter, NodeHandle
from parallax.core.read_delivery import InvalidData
from parallax.core.unit_work import WriteInstructionError
from parallax.snapshot import TxnContext, WireEntity
from parallax.snapshot._handle._typed_writes import TypedKeyedInsertSource, TypedKeyedWriteSource
from parallax.snapshot._handle._wire_writes import WireKeyedInsertSource, WireKeyedWriteSource
from parallax.snapshot._inspection import insertion_of, snapshot_state_of
from parallax.snapshot._publication._wire import authoring_of, read_evidence_of
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests._support.model_capabilities import cataloged_for, graph_construction_for, row_codec_for
from tests.unit._transact_support import ACCOUNT, INFINITY_INSTANT, db_for, new_account
from tests.unit._where_position_model import WHERE_POSITION_META, WherePosition

_ACCOUNT_NAME: Final = "parallax.compatibility.Account"
_CONTACT_NAME: Final = "parallax.compatibility.Contact"
_POSITION_NAME: Final = "parallax.compatibility.WherePosition"
_TX_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_TX_PIN: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)

_ACCOUNT_ROW: Final[MappingRow] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}
_POSITION_ROW: Final[MappingRow] = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("100.00"),
    "from_z": _TX_START,
    "thru_z": INFINITY_INSTANT,
    "in_z": _TX_START,
    "out_z": INFINITY_INSTANT,
}
# `Contact` requires every member of its address, so a stored address stating
# no `city` publishes a hydratable classified root.
_INCOMPLETE_CONTACT_ROW: Final[MappingRow] = {
    "id": 1,
    "name": "Ada",
    "address": PresentDocument(
        {"street": "Main", "geo": {"country": "DE", "point": {"lat": 1.0, "lon": 2.0}}}
    ),
}

_TYPED_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="write it with `tx.insert(...)`, or amend or replace a value a `find` returned",
    already_stored="change it with `value.edit(...)` and write it with `tx.amend(...)`",
    repeated_insert=(
        "write the change with `tx.amend(inserted.edit(...))`, where `inserted` is the value "
        "the first insert took"
    ),
)
_WIRE_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="write it with `tx.insert(...)`, or amend or replace a value a `find` returned",
    already_stored="write the change with `tx.wire.amend(value, {...})`",
    repeated_insert=(
        "write the change with `tx.wire.amend(opened, {...})`, where `opened` is the node "
        "the first insert answered"
    ),
)


# --------------------------------------------------------------------------- #
# How a caller obtains each carrier.                                          #
# --------------------------------------------------------------------------- #
def _wire_query(entity: str, temporal: dict[str, object] | None = None) -> dict[str, object]:
    query: dict[str, object] = {
        "target": entity,
        "predicate": {"eq": {"path": f"{entity}.id", "value": 1}},
    }
    if temporal is not None:
        query["temporal"] = temporal
    return query


_TYPED_ACCOUNT_QUERY: Final = mm.Account.where(mm.Account.id == 1)
_WIRE_ACCOUNT_QUERY: Final = _wire_query(_ACCOUNT_NAME)


def _standalone_typed() -> mm.Account:
    port = ScriptedAdapter(Read(rows=[dict(_ACCOUNT_ROW)]))
    return db_for(ACCOUNT, port).find(_TYPED_ACCOUNT_QUERY).result()


def _read_only_typed() -> mm.Account:
    port = ScriptedAdapter(Transact(Read(rows=[dict(_ACCOUNT_ROW)])))
    return db_for(ACCOUNT, port).read_only(lambda rtx: rtx.find(_TYPED_ACCOUNT_QUERY).result())


def _writable_typed() -> mm.Account:
    port = ScriptedAdapter(Transact(Read(rows=[dict(_ACCOUNT_ROW)])))
    return db_for(ACCOUNT, port).transact(lambda tx: tx.find(_TYPED_ACCOUNT_QUERY).result())


def _edited_writable_typed() -> mm.Account:
    return _writable_typed().edit(balance=Decimal("125.00"))


def _pinned_typed() -> WherePosition:
    port = ScriptedAdapter(Read(rows=[dict(_POSITION_ROW)]))
    query = WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST, tx_time=_TX_PIN)
    return db_for(WHERE_POSITION_META, port).find(query).result()


def _diagnostic_typed() -> Contact:
    port = ScriptedAdapter(Read(rows=[dict(_INCOMPLETE_CONTACT_ROW)]))
    published = db_for(CONTACT_MODEL, port).find(Contact.where(Contact.id == 1)).checked().result()
    assert isinstance(published, InvalidData)
    return cast("Contact", published.data)


class _OtherLifecycleState:
    """Lifecycle state this Snapshot did not attach."""


def _foreign_typed() -> mm.Account:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(mm.Account.identity)
        writer.populate(handle, (1, "Ada", Decimal("100.00"), 1), ())
        return (handle,)

    (node,) = graph_construction_for(ACCOUNT).construct(
        build, state_factory=lambda view, handle: _OtherLifecycleState()
    )
    return cast("mm.Account", node)


def _inserted_typed() -> mm.Account:
    value = new_account()
    db_for(ACCOUNT, ScriptedAdapter(Transact(Write()))).transact(lambda tx: tx.insert(value))
    return value


def _standalone_wire() -> WireEntity:
    port = ScriptedAdapter(Read(rows=[dict(_ACCOUNT_ROW)]))
    return db_for(ACCOUNT, port).wire.find(_WIRE_ACCOUNT_QUERY).result()


def _read_only_wire() -> WireEntity:
    port = ScriptedAdapter(Transact(Read(rows=[dict(_ACCOUNT_ROW)])))
    return db_for(ACCOUNT, port).read_only(lambda rtx: rtx.wire.find(_WIRE_ACCOUNT_QUERY).result())


def _writable_wire() -> WireEntity:
    port = ScriptedAdapter(Transact(Read(rows=[dict(_ACCOUNT_ROW)])))
    return db_for(ACCOUNT, port).transact(lambda tx: tx.wire.find(_WIRE_ACCOUNT_QUERY).result())


def _projected_writable_wire() -> WireEntity:
    port = ScriptedAdapter(Transact(Read(rows=[dict(_ACCOUNT_ROW)])))
    return db_for(ACCOUNT, port).transact(lambda tx: tx.find(_TYPED_ACCOUNT_QUERY).wire().result())


def _pinned_wire() -> WireEntity:
    port = ScriptedAdapter(Read(rows=[dict(_POSITION_ROW)]))
    query = _wire_query(
        _POSITION_NAME,
        {
            "transaction-time": {"asOf": "2024-03-01T00:00:00.000000Z"},
            "valid-time": {"asOf": "latest"},
        },
    )
    return db_for(WHERE_POSITION_META, port).wire.find(query).result()


def _invalid_wire() -> InvalidData[WireEntity]:
    port = ScriptedAdapter(Read(rows=[dict(_INCOMPLETE_CONTACT_ROW)]))
    published = db_for(CONTACT_MODEL, port).wire.find(_wire_query(_CONTACT_NAME)).checked()
    invalid = published.result()
    assert isinstance(invalid, InvalidData)
    return invalid


def _diagnostic_wire() -> WireEntity:
    node = _invalid_wire().data
    assert isinstance(node, WireEntity)
    return node


def _inserted_wire() -> WireEntity:
    def fn(tx: TxnContext) -> WireEntity:
        return tx.wire.insert(_ACCOUNT_NAME, {"id": 7, "owner": "Newton", "balance": "5.00"})

    return db_for(ACCOUNT, ScriptedAdapter(Transact(Write()))).transact(fn)


# --------------------------------------------------------------------------- #
# The table.                                                                  #
# --------------------------------------------------------------------------- #
type Representation = Literal["typed", "wire"]


@dataclass(frozen=True, slots=True)
class _Row:
    """One carrier and the facts its resolved record answers.

    ``pinned`` asks whether the record carries the view's Pin; ``evidence`` and
    ``authoring`` whether it carries exactly the Read Evidence or insertion
    authority the carrier itself holds."""

    name: str
    representation: Representation
    model: DomainModel
    obtain: Callable[[], object]
    provenance: Provenance
    pinned: bool = False
    evidence: bool = False
    authoring: bool = False

    def __str__(self) -> str:
        return self.name


_SOURCE_ROWS: Final = (
    _Row("typed-constructed", "typed", ACCOUNT, new_account, "none"),
    _Row("typed-standalone-read", "typed", ACCOUNT, _standalone_typed, "this"),
    _Row("typed-read-only-read", "typed", ACCOUNT, _read_only_typed, "this"),
    _Row("typed-writable-read", "typed", ACCOUNT, _writable_typed, "this", evidence=True),
    _Row("typed-edit", "typed", ACCOUNT, _edited_writable_typed, "this", evidence=True),
    _Row("typed-pinned-read", "typed", WHERE_POSITION_META, _pinned_typed, "this", pinned=True),
    _Row("typed-diagnostic", "typed", CONTACT_MODEL, _diagnostic_typed, "none"),
    _Row("typed-foreign-lifecycle", "typed", ACCOUNT, _foreign_typed, "foreign"),
    _Row("typed-inserted", "typed", ACCOUNT, _inserted_typed, "none", authoring=True),
    _Row("wire-standalone-read", "wire", ACCOUNT, _standalone_wire, "this"),
    _Row("wire-read-only-read", "wire", ACCOUNT, _read_only_wire, "this"),
    _Row("wire-writable-read", "wire", ACCOUNT, _writable_wire, "this", evidence=True),
    _Row("wire-projected", "wire", ACCOUNT, _projected_writable_wire, "this", evidence=True),
    _Row("wire-pinned-read", "wire", WHERE_POSITION_META, _pinned_wire, "this", pinned=True),
    _Row("wire-inserted", "wire", ACCOUNT, _inserted_wire, "none", authoring=True),
)
"""What a source-backed write's adapter answers for each carrier. Typed
diagnostic data keeps its inspection state yet is no stored value, and the node
a Wire insert answered is published by no read: both answer ``none``, which only
standing insertion authority lifts."""

_INSERT_ROWS: Final = (
    _Row("typed-constructed", "typed", ACCOUNT, new_account, "none"),
    _Row("typed-standalone-read", "typed", ACCOUNT, _standalone_typed, "this"),
    _Row("typed-pinned-read", "typed", WHERE_POSITION_META, _pinned_typed, "this", pinned=True),
    _Row("typed-diagnostic", "typed", CONTACT_MODEL, _diagnostic_typed, "none"),
    _Row("typed-foreign-lifecycle", "typed", ACCOUNT, _foreign_typed, "foreign"),
    _Row("typed-inserted", "typed", ACCOUNT, _inserted_typed, "none"),
    _Row("wire-fresh-payload", "wire", ACCOUNT, lambda: {"id": 7, "owner": "N"}, "none"),
    _Row("wire-standalone-read", "wire", ACCOUNT, _standalone_wire, "this"),
    _Row("wire-pinned-read", "wire", WHERE_POSITION_META, _pinned_wire, "this", pinned=True),
    _Row("wire-inserted", "wire", ACCOUNT, _inserted_wire, "this"),
    _Row("wire-diagnostic", "wire", CONTACT_MODEL, _diagnostic_wire, "none"),
    _Row("wire-converted", "wire", ACCOUNT, lambda: dict(_standalone_wire()), "none"),
)
"""What an insert's adapter answers for each payload. An insertion-only Typed
instance answers ``none`` and so reaches the prepared-key repeat check, while
the node a Wire insert answered is one this store published and is refused
before preparation. Only a stored read node carries a view to judge."""

_ENTITY_NAMES: Final = {
    ACCOUNT: _ACCOUNT_NAME,
    WHERE_POSITION_META: _POSITION_NAME,
    CONTACT_MODEL: _CONTACT_NAME,
}


def _resolved_source(row: _Row, value: object) -> ResolvedKeyedWriteSource:
    meta = cataloged_for(row.model).meta
    if row.representation == "typed":
        typed = TypedKeyedWriteSource(cast("EntityBase", value), row_codec_for(row.model))
        return typed.resolve(meta, "amend")
    wire = WireKeyedWriteSource(value, {})
    wire.capture("amend")
    return wire.resolve(meta, "amend")


def _resolved_insert(row: _Row, value: object) -> ResolvedKeyedInsert:
    meta = cataloged_for(row.model).meta
    if row.representation == "typed":
        typed = TypedKeyedInsertSource(cast("EntityBase", value), row_codec_for(row.model))
        return typed.resolve(meta, "insert")
    wire = WireKeyedInsertSource(_ENTITY_NAMES[row.model], cast("dict[str, object]", value))
    wire.capture("insert")
    return wire.resolve(meta, "insert")


def _carried_evidence(value: object) -> object:
    if isinstance(value, WireEntity):
        return read_evidence_of(value)
    state = snapshot_state_of(value)
    return None if state is None else state.read_evidence


def _carried_authoring(value: object) -> object:
    return authoring_of(value) if isinstance(value, WireEntity) else insertion_of(value)


def _advice(representation: Representation) -> KeyedWriteRefusalAdvice:
    return _TYPED_ADVICE if representation == "typed" else _WIRE_ADVICE


@pytest.mark.parametrize("row", _SOURCE_ROWS, ids=str)
def test_a_source_answers_the_facts_its_carrier_holds(row: _Row) -> None:
    value = row.obtain()

    resolved = _resolved_source(row, value)

    assert resolved.provenance == row.provenance
    assert (resolved.pin is not None) is row.pinned
    if row.pinned:
        assert resolved.pin is not None
        assert resolved.pin.tx_time == _TX_PIN
    evidence = _carried_evidence(value)
    assert (evidence is not None) is row.evidence
    assert resolved.read_evidence is evidence
    authoring = _carried_authoring(value)
    assert (authoring is not None) is row.authoring
    assert resolved.authoring is authoring
    assert resolved.advice == _advice(row.representation)


@pytest.mark.parametrize("row", _INSERT_ROWS, ids=str)
def test_an_insert_payload_answers_where_it_came_from(row: _Row) -> None:
    resolved = _resolved_insert(row, row.obtain())

    assert resolved.provenance == row.provenance
    assert (resolved.pin is not None) is row.pinned
    if row.pinned:
        assert resolved.pin is not None
        assert resolved.pin.tx_time == _TX_PIN
    assert resolved.advice == _advice(row.representation)


@pytest.mark.parametrize(
    "obtain",
    [
        lambda: {"id": 1, "owner": "Ada"},
        lambda: dict(_standalone_wire()),
        _diagnostic_wire,
        _invalid_wire,
    ],
    ids=["mapping", "converted", "diagnostic", "invalid-data"],
)
def test_a_wire_value_published_by_no_read_or_insert_is_no_keyed_source(
    obtain: Callable[[], object],
) -> None:
    # Recognition refuses before the shared interpretation is asked, so no
    # Wire carrier can answer `foreign` or reach a provenance refusal.
    source = WireKeyedWriteSource(obtain(), {})
    source.capture("amend")

    with pytest.raises(WriteInstructionError, match="carries no such provenance"):
        source.resolve(cataloged_for(CONTACT_MODEL).meta, "amend")


@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_every_resolution_shares_one_advice_value_per_representation(
    representation: Representation,
) -> None:
    rows = [row for row in _SOURCE_ROWS if row.representation == representation]
    inserts = [row for row in _INSERT_ROWS if row.representation == representation]
    answered = [_resolved_source(row, row.obtain()).advice for row in rows]
    answered += [_resolved_insert(row, row.obtain()).advice for row in inserts]

    assert all(advice is answered[0] for advice in answered)
