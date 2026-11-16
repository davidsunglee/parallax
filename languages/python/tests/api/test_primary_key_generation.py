"""Native pooled primary keys through the public insert verbs, against real Postgres.

A keyless draft takes its key at the insert call, from a block the root reserved
on its own writer connection, and the insert answers a new immutable keyed
value; a supplied key is used as given. Each test reads the stored rows back and
counts the reservation Reads, their acquisitions, and the DML the attempt ran,
so what was allocated, and when, is observed rather than inferred.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from contextlib import closing
from typing import Any, Literal, assert_type, cast

import pytest
from pydantic import ValidationError

from parallax.core import (
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    KeySequence,
    RootExecution,
    TablePerHierarchy,
    TxTemporal,
    UsageError,
    ValueObject,
    attr,
)
from parallax.core.execution_lifecycle import (
    AcquisitionStarted,
    DatabaseCallStarted,
    ExecutionEvent,
    ReadStarted,
)
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import TablePerConcreteSubtype
from parallax.descriptor import domain_model_from_document, export_document
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresTable
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.bindings import TEST_BINDING
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root

_NAMESPACE = "key.generation"
_NOW = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


class Spec(ValueObject):
    title: Attr[str | None]


class ColumnsTicket(Entity, table="pkg_columns_ticket", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_columns_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)
    spec: Attr[Spec | None]
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentTicket(Entity, table="pkg_document_ticket", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_document_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)
    spec: Attr[Spec | None]
    version: Attr[int] = attr(optimistic_locking=True)


class Shape(
    Entity,
    table="pkg_shape",
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_shape_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class Square(Shape, namespace=_NAMESPACE, inheritance=ConcreteSubtype(tag_value="square")):
    side: Attr[int]


class ColumnsNote(Entity, table="pkg_columns_note", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_columns_note_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class DocumentNote(Entity, table="pkg_document_note", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_document_note_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class ColumnsLog(TxTemporal, table="pkg_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_columns_log_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class DocumentLog(TxTemporal, table="pkg_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_document_log_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class ColumnsSpan(Bitemporal, table="pkg_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_columns_span_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class DocumentSpan(Bitemporal, table="pkg_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_document_span_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class Order(Entity, table="pkg_order", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_order_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class OrderLine(Entity, table="pkg_order_line", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_order_line_ids", batch_size=3))
    order_id: Attr[int]
    label: Attr[str] = attr(max_length=8)


class Invoice(Entity, table="pkg_invoice", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_document_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


_MODEL = DomainModel(
    ColumnsTicket, DocumentTicket, Shape, Square, ColumnsNote, DocumentNote, ColumnsLog,
    DocumentLog, ColumnsSpan, DocumentSpan, Order, OrderLine, Invoice,
)  # fmt: skip
_TABLES: dict[type[Any], str] = {
    ColumnsTicket: "pkg_columns_ticket",
    DocumentTicket: "pkg_document_ticket",
    ColumnsNote: "pkg_columns_note",
    DocumentNote: "pkg_document_note",
    ColumnsLog: "pkg_columns_log",
    DocumentLog: "pkg_document_log",
    ColumnsSpan: "pkg_columns_span",
    DocumentSpan: "pkg_document_span",
}
_DOCUMENT_LAYOUT = (DocumentTicket, DocumentNote, DocumentLog, DocumentSpan)
_JAN, _MAR, _MAY = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5))
_SPEC = Spec(title="carried")

type _Representation = Literal["typed", "wire"]
_REPRESENTATIONS: tuple[_Representation, ...] = ("typed", "wire")
_ENTITIES = (ColumnsTicket, DocumentTicket)

type _Event = tuple[str, ...]


class _Events:
    """A lifecycle Provider recording, in order, every Read with its purpose,
    every acquisition with the policy it requested, and every Database Call's
    kind and statement."""

    def __init__(self) -> None:
        self.seen: list[_Event] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return _Recording(self.seen)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(f"lifecycle handler failed: {error!r}")

    def take(self) -> list[_Event]:
        seen, self.seen = self.seen, []
        return seen

    def reservations(self) -> int:
        return sum(event == ("read", "reservation") for event in self.seen)


class _Recording:
    def __init__(self, seen: list[_Event]) -> None:
        self._seen = seen

    def handle(self, event: ExecutionEvent, /) -> None:
        match event:
            case ReadStarted(purpose=purpose):
                self._seen.append(("read", purpose))
            case AcquisitionStarted(route_policy=policy):
                self._seen.append(("acquisition", str(policy)))
            case DatabaseCallStarted(kind=kind, statement=statement):
                self._seen.append((kind, statement.sql.split(" ", 1)[0]))
            case _:
                pass


def _db(profile_run: Any, events: _Events) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    return own_root(
        connect(profile_run.port, _MODEL, binding=TEST_BINDING, lifecycle_provider=events)
    ).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _stored(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    label = "payload->>'label'" if entity in _DOCUMENT_LAYOUT else "label"
    return list(
        profile_run.port.execute(
            f"select id, {label}, version from px.{_TABLES[entity]} order by id", []
        )
    )


def _insert(tx: TxnContext, entity: type[Any], representation: _Representation, **row: Any) -> Any:
    if representation == "typed":
        return tx.insert(entity(spec=_SPEC, **row))
    return tx.wire.insert(_name(entity), {"spec": {"title": "carried"}, **row})


def _key(value: object) -> object:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)["id"]
    return cast("ColumnsTicket", value).id


# --------------------------------------------------------------------------- #
# An omitted key is allocated at the call and answered on a new value.        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entity", _ENTITIES)
def test_a_typed_keyless_insert_answers_a_new_keyed_value_and_leaves_its_draft(
    profile_run: Any, entity: type[Any]
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    draft = entity(label="first", spec=_SPEC)

    def insert(tx: TxnContext) -> Any:
        inserted = tx.insert(draft)
        assert_type(inserted, Any)
        assert type(inserted) is entity
        assert inserted is not draft
        assert inserted.id == 1
        assert inserted.label == "first"
        assert inserted.spec == _SPEC
        # The version is the flush's to stamp into the stored row alone.
        assert inserted.version is None
        assert "version" not in inserted.model_fields_set
        return inserted

    inserted = db.transact(insert)
    assert inserted.version is None
    assert draft.id is None
    assert "id" not in draft.model_fields_set
    assert _stored(profile_run, entity) == [(1, "first", 1)]
    assert events.take() == [
        ("acquisition", "writer_only"),
        ("read", "reservation"),
        ("acquisition", "None"),
        ("read", "select"),
        ("write", "insert"),
    ]


@pytest.mark.parametrize("entity", _ENTITIES)
def test_a_wire_keyless_insert_answers_a_node_holding_its_allocated_key(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _db(profile_run, _Events())
    payload = {"label": "first", "spec": {"title": "carried"}}

    node = db.transact(lambda tx: tx.wire.insert(_name(entity), payload))

    assert node["id"] == 1
    assert node["label"] == "first"
    assert "version" not in node
    assert "id" not in payload
    assert _stored(profile_run, entity) == [(1, "first", 1)]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _ENTITIES)
def test_repeated_keyless_inserts_take_fresh_keys_and_join_one_grouped_insert(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    draft = entity(label="same", spec=_SPEC)

    def insert(tx: TxnContext) -> list[object]:
        if representation == "typed":
            return [_key(tx.insert(draft)) for _ in range(4)]
        payload = {"label": "same", "spec": {"title": "carried"}}
        return [_key(tx.wire.insert(_name(entity), payload)) for _ in range(4)]

    assert db.transact(insert) == [1, 2, 3, 4]
    assert _stored(profile_run, entity) == [(key, "same", 1) for key in (1, 2, 3, 4)]
    # A block of three serves three inserts, a second serves the fourth, and the
    # four rows are one statement: no insert rereads its key.
    seen = events.take()
    assert events.reservations() == 0
    assert seen.count(("read", "reservation")) == 2
    assert seen.count(("write", "insert")) == 1


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_later_transaction_hands_out_its_root_s_reserved_keys_without_sql(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    db.transact(lambda tx: _insert(tx, ColumnsTicket, representation, label="first"))
    events.take()

    second = db.transact(lambda tx: _key(_insert(tx, ColumnsTicket, representation, label="next")))

    assert second == 2
    assert events.take() == [("acquisition", "writer_only"), ("write", "insert")]


# --------------------------------------------------------------------------- #
# A supplied key is used as given.                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("key", [0, 40], ids=["zero", "positive"])
@pytest.mark.parametrize("entity", _ENTITIES)
def test_a_supplied_key_is_used_as_given_and_allocates_nothing(
    profile_run: Any, entity: type[Any], key: int
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    instance = entity(id=key, label="given", spec=_SPEC)

    def insert(tx: TxnContext) -> None:
        assert tx.insert(instance) is instance
        node = tx.wire.insert(_name(entity), {"id": key + 1, "label": "wired"})
        assert node["id"] == key + 1

    db.transact(insert)
    assert _stored(profile_run, entity) == [(key, "given", 1), (key + 1, "wired", 1)]
    assert events.reservations() == 0


def test_a_stated_null_key_is_refused_and_allocates_nothing(profile_run: Any) -> None:
    events = _Events()
    db = _db(profile_run, events)
    with pytest.raises(ValidationError):
        ColumnsTicket(id=None, label="null")
    with raises_code(UsageError, "write-required-attribute-missing"):
        db.transact(lambda tx: tx.wire.insert(_name(ColumnsTicket), {"id": None, "label": "x"}))
    assert events.reservations() == 0
    assert _stored(profile_run, ColumnsTicket) == []


# --------------------------------------------------------------------------- #
# Only an insert accepts a keyless draft, and nothing else spends a key.       #
# --------------------------------------------------------------------------- #

_NO_START = cast("dt.datetime", None)
_KEYLESS_WRITES: dict[str, Callable[[TxnContext, ColumnsTicket], object]] = {
    "amend": lambda tx, draft: tx.amend(draft.edit(label="edited")),
    "replace": lambda tx, draft: tx.replace(draft),
    "delete": lambda tx, draft: tx.delete(draft),
    "replace_if": lambda tx, draft: tx.replace_if(draft, version=1),
    "wire.amend_if": lambda tx, _draft: tx.wire.amend_if(
        _name(ColumnsTicket), {"label": "x"}, version=1
    ),
    "wire.replace_if": lambda tx, _draft: tx.wire.replace_if(
        _name(ColumnsTicket), {"label": "x"}, version=1
    ),
    "wire.delete_if": lambda tx, _draft: tx.wire.delete_if(_name(ColumnsTicket), {}, version=1),
    # Absence outranks the payload and the window each call also gets wrong.
    "amend-two-authors": lambda tx, draft: tx.amend(
        draft.edit(label="edited"), ColumnsTicket.label.set("other")
    ),
    "replace_if-none-start": lambda tx, draft: tx.replace_if(
        draft, version=1, valid_from=_NO_START
    ),
    "wire.replace_if-none-start": lambda tx, _draft: tx.wire.replace_if(
        _name(ColumnsTicket), {"label": "x"}, version=1, valid_from=_NO_START
    ),
    "wire.amend_if-observation-key": lambda tx, _draft: tx.wire.amend_if(
        _name(ColumnsTicket), {"label": "x", "observedVersion": 1}, version=1
    ),
}


@pytest.mark.parametrize("verb", list(_KEYLESS_WRITES))
def test_every_verb_but_insert_refuses_a_keyless_draft_and_reserves_nothing(
    profile_run: Any, verb: str
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    draft = ColumnsTicket(label="keyless")

    with raises_code(UsageError, "write-key-absent"):
        db.transact(lambda tx: _KEYLESS_WRITES[verb](tx, draft))

    assert events.reservations() == 0
    assert ("acquisition", "None") not in events.take()
    assert db.transact(lambda tx: tx.insert(draft).id) == 1


_REFUSED_OPENINGS: dict[str, Callable[[TxnContext], object]] = {
    "typed": lambda tx: tx.insert(ColumnsTicket(label="ok"), valid_from=_NOW),
    "wire": lambda tx: tx.wire.insert(_name(ColumnsTicket), {"label": "ok", "undeclared": 1}),
}


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_opening_its_preparation_refuses_spends_no_key(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    with pytest.raises(UsageError):
        db.transact(_REFUSED_OPENINGS[representation])
    assert events.reservations() == 0

    assert db.transact(lambda tx: _key(_insert(tx, ColumnsTicket, representation, label="ok"))) == 1


def test_a_classless_model_refuses_a_typed_keyless_insert_before_it_spends_a_key(
    profile_run: Any,
) -> None:
    events = _Events()
    profile_run.reset(model_of(_MODEL), {}, TEST_BINDING)
    classless = domain_model_from_document(export_document(_MODEL))
    db = own_root(
        connect(profile_run.port, classless, binding=TEST_BINDING, lifecycle_provider=events)
    ).using_database_login()
    supplied = ColumnsTicket(id=40, label="given", spec=_SPEC)

    def insert(tx: TxnContext) -> object:
        # Answering an allocated key needs an instance the model cannot construct.
        with raises_code(UsageError, "snapshot-class-backed-model-required"):
            tx.insert(ColumnsTicket(label="keyless", spec=_SPEC))
        assert events.reservations() == 0
        assert tx.insert(supplied) is supplied
        return tx.wire.insert(_name(ColumnsTicket), {"label": "wired"})["id"]

    assert db.transact(insert) == 1
    assert _stored(profile_run, ColumnsTicket) == [(1, "wired", 1), (40, "given", 1)]


# --------------------------------------------------------------------------- #
# The answered value is a record of the insert call.                           #
# --------------------------------------------------------------------------- #


def test_an_allocated_value_carries_the_insertion_through_edits_and_a_flush(
    profile_run: Any,
) -> None:
    db = _db(profile_run, _Events())

    def write(tx: TxnContext) -> tuple[ColumnsTicket, ColumnsTicket]:
        inserted = tx.insert(ColumnsTicket(label="first", spec=_SPEC))
        edited = inserted.edit(label="second")
        tx.amend(edited)
        stored = tx.find(ColumnsTicket.where(ColumnsTicket.id == inserted.id)).result()
        tx.amend(inserted.edit(label="third"))
        return inserted, stored

    inserted, stored = db.transact(write)
    assert (inserted.label, inserted.version) == ("first", None)
    assert (stored.label, stored.version) == ("second", 1)
    assert _stored(profile_run, ColumnsTicket) == [(1, "third", 2)]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_keyed_result_inserts_under_its_own_key_after_a_rollback(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    held: list[Any] = []

    class _Undo(Exception):
        pass

    def first(tx: TxnContext) -> None:
        held.append(_insert(tx, ColumnsTicket, representation, label="held"))
        raise _Undo

    with pytest.raises(_Undo):
        db.transact(first)
    events.take()

    def again(tx: TxnContext) -> object:
        value = held[0]
        if representation == "typed":
            return tx.insert(value).id
        return tx.wire.insert(_name(ColumnsTicket), dict(value))["id"]

    assert db.transact(again) == 1
    assert events.reservations() == 0
    assert _stored(profile_run, ColumnsTicket) == [(1, "held", 1)]
    assert (
        db.transact(lambda tx: _key(_insert(tx, ColumnsTicket, representation, label="new"))) == 2
    )


def test_a_family_subtype_takes_its_key_from_the_root_s_allocator(profile_run: Any) -> None:
    db = _db(profile_run, _Events())

    def insert(tx: TxnContext) -> tuple[object, object]:
        typed = tx.insert(Square(label="typed", side=2))
        node = tx.wire.insert(f"{_NAMESPACE}.Square", {"label": "wired", "side": 3})
        assert type(typed) is Square
        return typed.id, node["id"]

    assert db.transact(insert) == (1, 2)
    assert list(
        profile_run.port.execute("select id, kind, side from px.pkg_shape order by id", [])
    ) == [(1, "square", 2), (2, "square", 3)]


# --------------------------------------------------------------------------- #
# The answered value records the insert call; edits finalize only in the       #
# stored row, which an ordinary participating read retrieves. Every            #
# temporality, layout, representation, and strategy, with one key throughout.  #
# --------------------------------------------------------------------------- #

type _Concurrency = Literal["optimistic", "locking"]
_CONCURRENCIES: tuple[_Concurrency, ...] = ("optimistic", "locking")
_TEMPORALITIES: dict[type[Any], str] = {
    ColumnsNote: "plain",
    DocumentNote: "plain",
    ColumnsTicket: "versioned",
    DocumentTicket: "versioned",
    ColumnsLog: "transaction-time",
    DocumentLog: "transaction-time",
    ColumnsSpan: "bitemporal",
    DocumentSpan: "bitemporal",
}
_VALID_FROM: dict[str, dict[str, dt.datetime]] = {"bitemporal": {"valid_from": _JAN}}


def _current(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    """Every stored row's key, and the labels of the rows current in
    Transaction Time."""
    label = "payload->>'label'" if entity in _DOCUMENT_LAYOUT else "label"
    table = f"px.{_TABLES[entity]}"
    current = "out_z = 'infinity'" if _TEMPORALITIES[entity] in _TIMED else "true"
    keys = profile_run.port.execute(f"select distinct id from {table}", [])
    rows = profile_run.port.execute(f"select id, {label} from {table} where {current}", [])
    return [tuple(row) for row in keys] + [tuple(row) for row in rows]


_TIMED = ("transaction-time", "bitemporal")


def _stated(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {name for name in cast("Mapping[str, object]", value) if not name.startswith("@")}
    return set(cast("ColumnsNote", value).model_fields_set)


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", list(_TEMPORALITIES), ids=lambda entity: entity.__name__)
def test_an_allocated_value_stays_as_inserted_while_its_edits_finalize_in_the_stored_row(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    temporality = _TEMPORALITIES[entity]
    bounds = _VALID_FROM.get(temporality, {})
    spec = {"spec": _SPEC} if temporality == "versioned" else {}
    authored = {"id", "label", *spec}

    def amend(tx: TxnContext, source: Any, label: str) -> None:
        if representation == "typed":
            tx.amend(source.edit(label=label))
        else:
            tx.wire.amend(source, {"label": label})

    def write(tx: TxnContext) -> tuple[Any, object]:
        if representation == "typed":
            inserted: Any = tx.insert(entity(label="first", **spec), **bounds)
        else:
            payload = {"label": "first"} | ({"spec": {"title": "carried"}} if spec else {})
            inserted = tx.wire.insert(_name(entity), payload, **bounds)
        key = _key(inserted)
        # Framework members are the flush's: absent on the answer.
        assert _stated(inserted) == authored
        amend(tx, inserted, "second")
        query = entity.where(entity.id == key)
        if temporality == "bitemporal":
            query = query.as_of(valid_time=_MAR)
        stored = tx.find(query).result()
        assert stored.label == "second"
        assert _stated(stored) > authored or temporality == "plain"
        # The source still edits what its insertion opened, now stored.
        amend(tx, inserted, "third")
        return inserted, key

    inserted, key = db.transact(write, concurrency=concurrency)
    assert _key(inserted) == key == 1
    assert _stated(inserted) == authored
    if representation == "typed":
        assert inserted.label == "first"
    else:
        assert inserted["label"] == "first"
    # One identity throughout: edits and temporal successors allocate nothing.
    assert _current(profile_run, entity) == [(1,), (1, "third")]
    assert events.reservations() == 1


# --------------------------------------------------------------------------- #
# A supplied key opens a temporal gap or reopens a terminated object.          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_gap_insert_under_an_allocated_key_reserves_nothing_and_shares_its_identity(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    name = _name(ColumnsSpan)

    def opened(tx: TxnContext) -> Any:
        if representation == "typed":
            return tx.insert(ColumnsSpan(label="early"), valid_from=_JAN, until=_MAR)
        return tx.wire.insert(name, {"label": "early"}, valid_from=_JAN, until=_MAR)

    held = db.transact(opened)
    events.take()

    def gap(tx: TxnContext) -> object:
        if representation == "typed":
            # The held answer inserts under the key it holds, in a later attempt.
            return tx.insert(held.edit(label="later"), valid_from=_MAY).id
        return tx.wire.insert(name, {"id": _key(held), "label": "later"}, valid_from=_MAY)["id"]

    assert db.transact(gap) == 1
    assert events.reservations() == 0
    assert list(
        profile_run.port.execute(
            "select id, label, from_z, case when thru_z = 'infinity' then null else thru_z end "
            "from px.pkg_columns_span order by from_z",
            [],
        )
    ) == [(1, "early", _JAN, _MAR), (1, "later", _MAY, None)]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_reopening_a_terminated_object_supplies_its_key_and_reserves_nothing(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    key = db.transact(lambda tx: _key(_insert_log(tx, representation, label="opened")))

    def terminate(tx: TxnContext) -> None:
        tx.terminate(tx.find(ColumnsLog.where(ColumnsLog.id == key)).result())

    db.transact(terminate)
    events.take()
    db.transact(lambda tx: _insert_log(tx, representation, id=key, label="reopened"))

    assert events.reservations() == 0
    assert list(
        profile_run.port.execute(
            "select id, label, out_z = 'infinity' from px.pkg_columns_log order by in_z", []
        )
    ) == [(1, "opened", False), (1, "reopened", True)]


def _insert_log(tx: TxnContext, representation: _Representation, **row: Any) -> Any:
    if representation == "typed":
        return tx.insert(ColumnsLog(**row))
    return tx.wire.insert(_name(ColumnsLog), row)


# --------------------------------------------------------------------------- #
# A parent's answered key builds its child before anything flushes.           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_child_takes_its_parent_s_answered_key_before_either_flushes(
    profile_run: Any, representation: _Representation
) -> None:
    events = _Events()
    db = _db(profile_run, events)
    parent = Order(label="order")
    line = {"label": "line"}

    def write(tx: TxnContext) -> tuple[object, object]:
        if representation == "typed":
            order = tx.insert(parent)
            child = tx.insert(OrderLine(order_id=order.id, **line))
            return order.id, child.id
        order_node = tx.wire.insert(_name(Order), {"label": "order"})
        child_node = tx.wire.insert(_name(OrderLine), {"orderId": order_node["id"], **line})
        return order_node["id"], child_node["id"]

    assert db.transact(write) == (1, 1)
    # Both keys were reserved before anything flushed, and both rows went in
    # at the commit's flush.
    seen = events.take()
    reservations = [index for index, event in enumerate(seen) if event == ("read", "reservation")]
    writes = [index for index, event in enumerate(seen) if event == ("write", "insert")]
    assert len(reservations) == len(writes) == 2
    assert max(reservations) < min(writes)
    assert parent.id is None
    assert line == {"label": "line"}
    assert list(profile_run.port.execute("select id, label from px.pkg_order", [])) == [
        (1, "order")
    ]
    assert list(
        profile_run.port.execute("select id, order_id, label from px.pkg_order_line", [])
    ) == [(1, 1, "line")]


# --------------------------------------------------------------------------- #
# Entities naming one allocator draw from one stream.                          #
# --------------------------------------------------------------------------- #


def test_unrelated_entities_naming_one_allocator_share_its_stream(profile_run: Any) -> None:
    events = _Events()
    db = _db(profile_run, events)

    def write(tx: TxnContext) -> list[int]:
        return [
            tx.insert(DocumentTicket(label="t1", spec=_SPEC)).id,
            tx.insert(Invoice(label="i1")).id,
            tx.insert(DocumentTicket(label="t2", spec=_SPEC)).id,
            tx.insert(Invoice(label="i2")).id,
        ]

    assert db.transact(write) == [1, 2, 3, 4]
    assert events.reservations() == 2
    assert list(profile_run.port.execute("select id from px.pkg_invoice order by id", [])) == [
        (2,),
        (4,),
    ]
    assert list(
        profile_run.port.execute("select last_value, is_called from px.pkg_document_ids", [])
    ) == [(4, True)]


# --------------------------------------------------------------------------- #
# Insertion authority across flushes, joined scopes, and attempts.             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_allocated_value_carries_its_insertion_across_a_joined_scope(
    profile_run: Any, representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _db(profile_run, _Events())

    def outer(tx: TxnContext) -> object:
        inner_value = db.transact(
            lambda inner: _insert(inner, ColumnsTicket, representation, label="inner")
        )
        outer_value = _insert(tx, ColumnsTicket, representation, label="outer")

        def edit_outer(inner: TxnContext) -> None:
            _amend(inner, representation, outer_value, "outer2")

        db.transact(edit_outer)
        tx.find(ColumnsTicket.where(ColumnsTicket.id == 1)).result()
        _amend(tx, representation, inner_value, "inner2")
        return _key(inner_value), _key(outer_value)

    assert db.transact(outer, concurrency=concurrency) == (1, 2)
    assert _stored(profile_run, ColumnsTicket) == [(1, "inner2", 2), (2, "outer2", 1)]


def _amend(tx: TxnContext, representation: _Representation, source: Any, label: str) -> None:
    if representation == "typed":
        tx.amend(source.edit(label=label))
    else:
        tx.wire.amend(source, {"label": label})


@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_allocated_value_s_insertion_ends_with_its_attempt(
    profile_run: Any, representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _db(profile_run, _Events())
    held = db.transact(
        lambda tx: _insert(tx, ColumnsTicket, representation, label="held"),
        concurrency=concurrency,
    )

    def later(tx: TxnContext) -> None:
        with raises_code(UsageError, "write-value-not-stored"):
            _amend(tx, representation, held, "edited")

    db.transact(later, concurrency=concurrency)
    assert _stored(profile_run, ColumnsTicket) == [(1, "held", 1)]


def test_a_retried_attempt_answers_a_fresh_value_and_the_failed_one_s_insert_is_undone(
    profile_run: Any,
) -> None:
    # The first attempt's amend of a stored ticket meets a peer's overtaking
    # revision at its flush and replays; the retry inserts the same draft again
    # and takes the next key, while the failed attempt's answer cannot write.
    events = _Events()
    db = _db(profile_run, events)
    db.transact(lambda tx: tx.insert(ColumnsTicket(id=40, label="stored", spec=_SPEC)))
    events.take()
    draft = ColumnsTicket(label="drafted", spec=_SPEC)
    answered: list[ColumnsTicket] = []

    def body(tx: TxnContext) -> int:
        if answered:
            with raises_code(UsageError, "write-value-not-stored"):
                tx.amend(answered[0].edit(label="stale"))
        stored = tx.find(ColumnsTicket.where(ColumnsTicket.id == 40)).result()
        answered.append(tx.insert(draft))
        if len(answered) == 1:
            with closing(profile_run.control()) as peer:
                peer.execute_write(
                    "update px.pkg_columns_ticket set version = version + 1 where id = 40", []
                )
        tx.amend(stored.edit(label="revised"))
        return answered[-1].id

    assert db.transact(body, concurrency="optimistic") == 2
    assert [value.id for value in answered] == [1, 2]
    assert draft.id is None
    assert _stored(profile_run, ColumnsTicket) == [(2, "drafted", 1), (40, "revised", 3)]
    assert events.reservations() == 1


# --------------------------------------------------------------------------- #
# Where an allocator's sequence lives: the family root's, and the binding's.   #
# --------------------------------------------------------------------------- #

_PLACED = "key.placement"


class Fleet(Entity, namespace=_PLACED, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_fleet_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


class Truck(Fleet, table="pkg_vehicle", namespace=_PLACED, inheritance=ConcreteSubtype()):
    axles: Attr[int | None]


class Van(Fleet, table="pkg_vehicle", namespace=_PLACED, inheritance=ConcreteSubtype()):
    doors: Attr[int | None]


class Coupon(Entity, table="pkg_coupon", namespace=_PLACED):
    id: Attr[int] = attr(primary_key=KeySequence("pkg_coupon_ids", batch_size=3))
    label: Attr[str] = attr(max_length=8)


_PLACED_MODEL = DomainModel(Fleet, Truck, Van)
_TENANT_MODEL = DomainModel(Coupon)
_SPLIT_FLEET = PostgresBinding(
    default=PostgresLocation(schema="px"),
    entities={
        f"{_PLACED}.Truck": PostgresTable(schema="px_eu"),
        f"{_PLACED}.Van": PostgresTable(schema="px_us"),
    },
)


def _placed(
    profile_run: Any, model: DomainModel, binding: PostgresBinding, events: _Events
) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, model, binding=binding, lifecycle_provider=events)
    ).using_database_login()


def _rows(profile_run: Any, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_table_per_concrete_subtype_leaves_in_two_schemas_share_the_root_s_sequence(
    profile_run: Any, representation: _Representation
) -> None:
    profile_run.reset(model_of(_PLACED_MODEL), {}, _SPLIT_FLEET)
    events = _Events()
    db = _placed(profile_run, _PLACED_MODEL, _SPLIT_FLEET, events)

    def write(tx: TxnContext) -> list[object]:
        if representation == "typed":
            return [
                tx.insert(Truck(label="hauler", axles=3)).id,
                tx.insert(Van(label="courier", doors=4)).id,
                tx.insert(Truck(label="tipper", axles=2)).id,
            ]
        return [
            tx.wire.insert(f"{_PLACED}.Truck", {"label": "hauler", "axles": 3})["id"],
            tx.wire.insert(f"{_PLACED}.Van", {"label": "courier", "doors": 4})["id"],
            tx.wire.insert(f"{_PLACED}.Truck", {"label": "tipper", "axles": 2})["id"],
        ]

    assert db.transact(write) == [1, 2, 3]
    assert events.reservations() == 1
    assert _rows(profile_run, "select id, label from px_eu.pkg_vehicle order by id") == [
        (1, "hauler"),
        (3, "tipper"),
    ]
    assert _rows(profile_run, "select id, label from px_us.pkg_vehicle") == [(2, "courier")]
    # The tableless root's allocator lives where the binding's default puts it.
    assert _rows(profile_run, "select last_value, is_called from px.pkg_fleet_ids") == [(1, True)]


_TENANT_A = PostgresBinding(default=PostgresLocation(schema="px"))
_TENANT_B = PostgresBinding(default=PostgresLocation(schema="public"))


def _provision_both_tenants(profile_run: Any) -> None:
    """Tenant A through the provider's reset, then tenant B's table and
    sequence beside it through the shipped generator under B's binding."""
    profile_run.reset(model_of(_TENANT_MODEL), {}, _TENANT_A)
    role = POSTGRES.quote(profile_run.default_role.name)
    with closing(profile_run.control()) as control:
        for statement in schema_delta(
            evolve(ABSENT, _TENANT_MODEL, later_binding=_TENANT_B)
        ).statements:
            control.execute_write(statement, [])
        control.execute_write(
            f"grant select, insert, update, delete on all tables in schema public to {role}", []
        )
        control.execute_write(f"grant usage on all sequences in schema public to {role}", [])


def test_one_allocator_under_two_tenant_bindings_reserves_from_each_tenant_s_sequence(
    profile_run: Any,
) -> None:
    # Equal keys are expected: each tenant's sequence starts at its own initial
    # value. Isolation is that each root advanced its own sequence alone.
    _provision_both_tenants(profile_run)
    tenant_a = _placed(profile_run, _TENANT_MODEL, _TENANT_A, _Events())
    tenant_b = _placed(profile_run, _TENANT_MODEL, _TENANT_B, _Events())

    def coupons(count: int) -> Callable[[TxnContext], list[int]]:
        return lambda tx: [tx.insert(Coupon(label=f"c{index}")).id for index in range(count)]

    assert tenant_a.transact(coupons(4)) == [1, 2, 3, 4]
    assert tenant_b.transact(coupons(1)) == [1]
    assert _rows(profile_run, "select last_value from px.pkg_coupon_ids") == [(4,)]
    assert _rows(profile_run, "select last_value from public.pkg_coupon_ids") == [(1,)]
    assert _rows(profile_run, "select id from px.pkg_coupon order by id") == [
        (1,),
        (2,),
        (3,),
        (4,),
    ]
    assert _rows(profile_run, "select id from public.pkg_coupon") == [(1,)]
