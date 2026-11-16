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
from typing import Any, Literal, assert_type, cast

import pytest
from pydantic import ValidationError

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    KeySequence,
    RootExecution,
    TablePerHierarchy,
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
from parallax.core.internal.entity._model import model_of
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


_MODEL = DomainModel(ColumnsTicket, DocumentTicket, Shape, Square)
_TABLES: dict[type[Any], str] = {
    ColumnsTicket: "pkg_columns_ticket",
    DocumentTicket: "pkg_document_ticket",
}
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
    label = "payload->>'label'" if entity is DocumentTicket else "label"
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
