"""A source written again after a flush its own earlier write completed in,
against real Postgres.

A read-dependency flush executes what a transaction buffered; the source a
completed write went through still authorizes the state that write produced,
without another read, while its values stay what its read returned. Each case
writes through a source, reads something else to flush, writes through the same
source again, and reads the committed rows back under both storage layouts and
both strategies.

A Non-Temporal source continues from the version its object's completed updates
advanced to. A caller's stated revision stays literal, and a source whose object
a completed deletion removed licenses nothing, a fresh insertion at its key
included.

A temporal source continues through the rows the attempt's completed writes
derived from what it observed, however many of them lie between, reading none
of them again: the cases count the attempt's reads, and coverage no completed
write produced is still read as a positive control. A Bitemporal source
continues only while its own Valid-Time pin survives, so two sources of one
observation part when a termination removes one pin; a source whose state a
completed write destroyed stays ended through a reinsertion; and a caller's
stated start stays literal.

Standalone Docker-backed proofs, like `test_target_writes.py`: each is a
developer choreography rather than a case's authored observation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.scripted_clock import FixedClock, ScriptedClock
from parallax.core import LATEST, Attr, Bitemporal, Document, DomainModel, Entity, TxTemporal, attr
from parallax.core.entity._model import model_of
from parallax.core.unit_work import WriteEvidenceError, WritePreconditionError
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root

_NAMESPACE = "source.continuation"
_AT = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)


class ColumnsAccount(Entity, table="sc_columns_account", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentAccount(Entity, table="sc_document_account", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class ColumnsWallet(Entity, table="sc_columns_wallet", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class DocumentWallet(Entity, table="sc_document_wallet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


_MODEL = DomainModel(ColumnsAccount, DocumentAccount, ColumnsWallet, DocumentWallet)
_ACCOUNTS = (ColumnsAccount, DocumentAccount)
_ENTITIES = (ColumnsAccount, DocumentAccount, ColumnsWallet, DocumentWallet)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_ACCOUNT_AXES = pytest.mark.parametrize("entity", _ACCOUNTS, ids=["columns", "document"])
_ENTITY_AXES = pytest.mark.parametrize(
    "entity",
    _ENTITIES,
    ids=["versioned-columns", "versioned-document", "unversioned-columns", "unversioned-document"],
)
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
type _Source = Any


def _seeded(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(connect(profile_run.port, _MODEL, clock=FixedClock(_AT))).using_database_login()

    def seed(tx: TxnContext) -> None:
        for entity in _ENTITIES:
            for key in (1, 2):
                tx.wire.insert(_name(entity), {"id": key, "label": "seed", "note": "kept"})

    db.transact(seed)
    return db


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _read(
    tx: TxnContext, entity: type[Any], representation: _Representation, key: int = 1
) -> _Source:
    if representation == "typed":
        return tx.find(entity.where(entity.id == key)).result()
    return tx.wire.find(
        {
            "target": _name(entity),
            "predicate": {"eq": {"path": f"{_name(entity)}.id", "value": key}},
        }
    ).result()


def _amend(tx: TxnContext, source: _Source, **changes: object) -> None:
    if isinstance(source, WireEntity):
        tx.wire.amend(source, changes)
    else:
        tx.amend(source.edit(**changes))


def _replace(tx: TxnContext, source: _Source, **changes: object) -> None:
    if isinstance(source, WireEntity):
        tx.wire.replace(source, {**tx.wire.editable_data(source), **changes})
    else:
        tx.replace(source.edit(**changes))


def _delete(tx: TxnContext, source: _Source) -> None:
    if isinstance(source, WireEntity):
        tx.wire.delete(source)
    else:
        tx.delete(source)


def _flush(tx: TxnContext, entity: type[Any]) -> None:
    """A read of another key, which flushes everything buffered first."""
    tx.find(entity.where(entity.id == 2))


def _stored(db: ScopedDatabase, entity: type[Any]) -> tuple[object, ...] | None:
    def read(tx: TxnContext) -> tuple[object, ...] | None:
        rows = tx.find(entity.where(entity.id == 1)).results()
        if not rows:
            return None
        (row,) = rows
        return (row.label, row.note, getattr(row, "version", None))

    return db.transact(read)


def _version(entity: type[Any], version: int) -> int | None:
    return version if entity in _ACCOUNTS else None


@_ENTITY_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_source_amends_again_after_a_read_flushed_its_first_amendment(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        _amend(tx, source, label="first")
        _flush(tx, entity)
        _amend(tx, source, note="second")

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("first", "second", _version(entity, 3))


@_ENTITY_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    ("representation", "edited", "note"),
    [("typed", False, "kept"), ("typed", True, "seven"), ("wire", False, "kept")],
    ids=["typed-old-source", "typed-edited-source", "wire-old-source"],
)
def test_a_later_replacement_states_its_own_sources_literal_values(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
    edited: bool,
    note: str,
) -> None:
    # The first write changed the note; a replacement through the value read
    # before it states that value's note, not the one the write produced, and
    # one through the edited copy states the edited note.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        if isinstance(source, WireEntity):
            _amend(tx, source, note="seven")
            _flush(tx, entity)
            _replace(tx, source, label="new")
            return
        changed = source.edit(note="seven")
        tx.amend(changed)
        _flush(tx, entity)
        _replace(tx, changed if edited else source, label="new")

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("new", note, _version(entity, 3))


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_callers_completed_write_advances_the_source_of_the_state_it_named(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend_if(entity, entity.label.set("caller"), key=1, version=1)
        _flush(tx, entity)
        tx.amend(source.edit(note="source"))
        tx.amend_if(entity, entity.label.set("current"), key=1, version=2)

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("current", "source", 3)


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_callers_stated_revision_stays_literal_after_its_flush(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # Locking confirms the stated revision at the call; Optimistic gates on it
    # when it executes. Either way, the version the first write left is not
    # the one the caller stated.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(source.edit(label="first"))
        _flush(tx, entity)
        tx.amend_if(entity, entity.note.set("stale"), key=1, version=1)

    with raises_contextualized(WritePreconditionError):
        db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("seed", "kept", 1)


@_ACCOUNT_AXES
@_STRATEGIES
def test_an_equal_assignment_advances_the_version_and_an_empty_one_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(source.edit(label=source.label))
        _flush(tx, entity)
        tx.amend(source.edit())
        _flush(tx, entity)
        tx.amend(source.edit(note="after"))

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == ("seed", "after", 3)


@_ENTITY_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_deleted_source_ends_and_a_reinsertion_at_its_key_revives_none_of_it(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    db = _seeded(profile_run)
    refused: list[str] = []

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity, representation)
        _delete(tx, source)
        _flush(tx, entity)
        tx.wire.insert(_name(entity), {"id": 1, "label": "again", "note": "fresh"})
        for write in (lambda: _amend(tx, source, label="stale"), lambda: _delete(tx, source)):
            with pytest.raises(WriteEvidenceError) as refusal:
                write()
            refused.append(refusal.value.code)
        _flush(tx, entity)
        _amend(tx, _read(tx, entity, representation), note="reread")

    db.transact(fn, concurrency=concurrency)
    assert refused == ["write-evidence-consumed"] * 2
    assert _stored(db, entity) == ("again", "reread", _version(entity, 2))


@_ACCOUNT_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    ("replaced_first", "stored"),
    [(False, ("old", "kept")), (True, ("fresh", "later"))],
    ids=["amend-then-replace", "replace-then-amend"],
)
def test_an_old_and_a_fresh_source_of_one_produced_state_write_as_one(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    replaced_first: bool,
    stored: tuple[str, str],
) -> None:
    # Both sources reach the version the first write produced, so their writes
    # share its claim and coalesce in authored order: a replacement overwrites
    # an earlier amendment with its own source's complete state, and an
    # amendment after a replacement overrides only what it assigns. One write
    # advances the version once.
    db = _seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        old = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(old.edit(note="seven"))
        fresh = tx.find(entity.where(entity.id == 1)).result()
        assert (fresh.note, fresh.version) == ("seven", 2)
        if replaced_first:
            tx.replace(fresh.edit(label="fresh"))
            tx.amend(old.edit(note="later"))
        else:
            tx.amend(fresh.edit(label="fresh"))
            tx.replace(old.edit(label="old"))

    db.transact(fn, concurrency=concurrency)
    assert _stored(db, entity) == (*stored, 3)


_TEMPORAL = "source.continuation.temporal"
_SEEDED = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_RESEEDED = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_ATTEMPT = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_RETRIED = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_FEB = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_APR = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_JUN = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JUL = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_AUG = dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
_SEP = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


class ColumnsLedger(TxTemporal, table="sc_columns_ledger", namespace=_TEMPORAL):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class DocumentLedger(
    TxTemporal, table="sc_document_ledger", namespace=_TEMPORAL, layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class ColumnsTerm(Bitemporal, table="sc_columns_term", namespace=_TEMPORAL):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class DocumentTerm(Bitemporal, table="sc_document_term", namespace=_TEMPORAL, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


_TEMPORAL_MODEL = DomainModel(ColumnsLedger, DocumentLedger, ColumnsTerm, DocumentTerm)
_LEDGERS: tuple[type[Any], ...] = (ColumnsLedger, DocumentLedger)
_TERMS: tuple[type[Any], ...] = (ColumnsTerm, DocumentTerm)
_TEMPORAL_ENTITIES = (*_LEDGERS, *_TERMS)
_DOCUMENTS: tuple[type[Any], ...] = (DocumentLedger, DocumentTerm)
_TABLES = {
    ColumnsLedger: "sc_columns_ledger",
    DocumentLedger: "sc_document_ledger",
    ColumnsTerm: "sc_columns_term",
    DocumentTerm: "sc_document_term",
}

_TEMPORAL_AXES = pytest.mark.parametrize(
    "entity",
    _TEMPORAL_ENTITIES,
    ids=["txtime-columns", "txtime-document", "bitemporal-columns", "bitemporal-document"],
)
_TERM_AXES = pytest.mark.parametrize("entity", _TERMS, ids=["columns", "document"])


def _temporal_seeded(
    profile_run: Any, *, split: bool = False
) -> tuple[ScopedDatabase, LifecycleObservation]:
    """Objects 1 and 2 of every temporal Entity, labelled ``seed`` and noted
    ``kept``, Bitemporal ones current from January. Where ``split``, a later
    transaction notes each Bitemporal object ``later`` from September, so its
    coverage stands as two rows."""
    profile_run.reset(model_of(_TEMPORAL_MODEL), {})
    observation = LifecycleObservation()
    instants = [_SEEDED, _RESEEDED] if split else [_SEEDED]
    db = own_root(
        connect(
            profile_run.port,
            _TEMPORAL_MODEL,
            clock=ScriptedClock([*instants, _ATTEMPT, _RETRIED]),
            lifecycle_provider=observation.provider,
        )
    ).using_database_login()

    def seed(tx: TxnContext) -> None:
        for entity in _TEMPORAL_ENTITIES:
            for key in (1, 2):
                if entity in _TERMS:
                    tx.insert(entity(id=key, label="seed", note="kept"), valid_from=_JAN)
                else:
                    tx.insert(entity(id=key, label="seed", note="kept"))

    db.transact(seed)
    if split:

        def note_later(tx: TxnContext) -> None:
            for entity in _TERMS:
                for key in (1, 2):
                    row = tx.find(entity.where(entity.id == key).as_of(valid_time=_SEP)).result()
                    tx.amend(row.edit(note="later"))

        db.transact(note_later)
    return db, observation


def _temporal_name(entity: type[Any]) -> str:
    return f"{_TEMPORAL}.{entity.__name__}"


def _temporal_read(
    tx: TxnContext,
    entity: type[Any],
    representation: _Representation,
    *,
    key: int = 1,
    at: dt.datetime = _JUN,
) -> _Source:
    """Object ``key`` read latest on Transaction Time, and at Valid-Time ``at``
    where the Entity has Valid Time."""
    bitemporal = entity in _TERMS
    if representation == "typed":
        query = entity.where(entity.id == key)
        return tx.find(query.as_of(valid_time=at) if bitemporal else query).result()
    name = _temporal_name(entity)
    temporal: dict[str, object] = {"transaction-time": {"asOf": "latest"}}
    if bitemporal:
        temporal["valid-time"] = {"asOf": f"{at:%Y-%m-%dT%H:%M:%S.%fZ}"}
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"path": f"{name}.id", "value": key}},
            "temporal": temporal,
        }
    ).result()


def _bounded(until: dt.datetime | None) -> dict[str, dt.datetime]:
    return {} if until is None else {"until": until}


def _temporal_amend(
    tx: TxnContext, source: _Source, *, until: dt.datetime | None = None, **changes: object
) -> None:
    if isinstance(source, WireEntity):
        tx.wire.amend(source, changes, **_bounded(until))
    else:
        tx.amend(source.edit(**changes), **_bounded(until))


def _temporal_replace(
    tx: TxnContext, source: _Source, *, until: dt.datetime | None = None, **changes: object
) -> None:
    if isinstance(source, WireEntity):
        tx.wire.replace(source, {**tx.wire.editable_data(source), **changes}, **_bounded(until))
    else:
        tx.replace(source.edit(**changes), **_bounded(until))


def _terminate(tx: TxnContext, source: _Source, *, until: dt.datetime | None = None) -> None:
    if isinstance(source, WireEntity):
        tx.wire.terminate(source, **_bounded(until))
    else:
        tx.terminate(source, **_bounded(until))


def _temporal_flush(tx: TxnContext, entity: type[Any], key: int = 2) -> None:
    """A read of object ``key``, which flushes everything buffered first."""
    query = entity.where(entity.id == key)
    tx.find(query.as_of(valid_time=LATEST) if entity in _TERMS else query)


def _reads_since(observation: LifecycleObservation, mark: int) -> int:
    return sum(1 for call in observation.calls[mark:] if call.kind == "read")


def _member(entity: type[Any], member: str) -> str:
    return f"payload->>'{member}'" if entity in _DOCUMENTS else member


def _current(profile_run: Any, entity: type[Any], key: int = 1) -> list[tuple[object, ...]]:
    """Object ``key``'s rows current on Transaction Time: each one's
    Transaction-Time start, its Valid-Time interval where the Entity has Valid
    Time with ``None`` for infinity, and its label and note."""
    valid = (
        "from_z, case when thru_z = 'infinity' then null else thru_z end, "
        if entity in _TERMS
        else ""
    )
    order = "from_z" if entity in _TERMS else "in_z"
    sql = (
        f"select in_z, {valid}{_member(entity, 'label')}, {_member(entity, 'note')} "
        f"from {_TABLES[entity]} where id = %s and out_z = 'infinity' order by {order}"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [key])]


def _closed(profile_run: Any, entity: type[Any], key: int = 1) -> int:
    sql = f"select count(*) from {_TABLES[entity]} where id = %s and out_z <> 'infinity'"
    ((count,),) = profile_run.port.execute(sql, [key])
    return int(count)


@_TEMPORAL_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_temporal_source_writes_again_through_rows_no_read_observed(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # Each write after the first transforms rows only the attempt's completed
    # writes produced; the source reaches them without reading them, keeping
    # every member no write assigned as the latest write left it.
    db, observation = _temporal_seeded(profile_run)
    reads: list[int] = []

    def fn(tx: TxnContext) -> None:
        source = _temporal_read(tx, entity, representation)
        mark = len(observation.calls)
        _temporal_amend(tx, source, label="first", until=_AUG if entity in _TERMS else None)
        _temporal_flush(tx, entity)
        _temporal_amend(tx, source, note="second", until=_JUL if entity in _TERMS else None)
        _temporal_flush(tx, entity)
        _temporal_amend(tx, source, label="third")
        _temporal_flush(tx, entity)
        reads.append(_reads_since(observation, mark))

    db.transact(fn, concurrency=concurrency)

    assert reads == [3]
    if entity in _TERMS:
        assert _current(profile_run, entity) == [
            (_ATTEMPT, _JAN, _JUN, "seed", "kept"),
            (_ATTEMPT, _JUN, _JUL, "third", "second"),
            (_ATTEMPT, _JUL, None, "third", "kept"),
        ]
    else:
        assert _current(profile_run, entity) == [(_ATTEMPT, "third", "second")]
    assert _closed(profile_run, entity) == 1


@_TEMPORAL_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_temporal_replacement_states_its_own_sources_literal_values(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # The first write noted `seven`; a replacement through the value read
    # before it states that value's own note, not the one the write produced.
    db, _observation = _temporal_seeded(profile_run)

    def fn(tx: TxnContext) -> None:
        source = _temporal_read(tx, entity, representation)
        _temporal_amend(tx, source, note="seven")
        _temporal_flush(tx, entity)
        _temporal_replace(tx, source, label="new")

    db.transact(fn, concurrency=concurrency)

    if entity in _TERMS:
        assert _current(profile_run, entity) == [
            (_ATTEMPT, _JAN, _JUN, "seed", "kept"),
            (_ATTEMPT, _JUN, None, "new", "kept"),
        ]
    else:
        assert _current(profile_run, entity) == [(_ATTEMPT, "new", "kept")]


@_TEMPORAL_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_streamed_temporal_sources_write_again_after_their_pages_flushed_them(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # Each page of a one-root stream flushes the write made through the root
    # before it; once the stream is done, every root writes again from what
    # its own write left, reading nothing.
    db, observation = _temporal_seeded(profile_run)
    reads: list[int] = []
    name = _temporal_name(entity)

    def fn(tx: TxnContext) -> None:
        if representation == "typed":
            query = entity.where(entity.id >= 1)
            if entity in _TERMS:
                query = query.as_of(valid_time=_JUN)
            stream = tx.stream(query, batch_size=1)
        else:
            temporal: dict[str, object] = {"transaction-time": {"asOf": "latest"}}
            if entity in _TERMS:
                temporal["valid-time"] = {"asOf": f"{_JUN:%Y-%m-%dT%H:%M:%S.%fZ}"}
            stream = tx.wire.stream(
                {
                    "target": name,
                    "predicate": {"true": {}},
                    "temporal": temporal,
                    "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
                },
                batch_size=1,
            )
        sources: list[_Source] = []
        with stream as roots:
            for root in roots:
                _temporal_amend(tx, root, label="streamed")
                sources.append(root)
        _temporal_flush(tx, entity)
        mark = len(observation.calls)
        for root in sources:
            _temporal_amend(tx, root, note="again")
        _temporal_flush(tx, entity, 3)
        reads.append(_reads_since(observation, mark))

    db.transact(fn, concurrency=concurrency)

    assert reads == [1]
    for key in (1, 2):
        if entity in _TERMS:
            assert _current(profile_run, entity, key) == [
                (_ATTEMPT, _JAN, _JUN, "seed", "kept"),
                (_ATTEMPT, _JUN, None, "streamed", "again"),
            ]
        else:
            assert _current(profile_run, entity, key) == [(_ATTEMPT, "streamed", "again")]


@_TEMPORAL_AXES
@_STRATEGIES
def test_a_callers_completed_write_continues_a_source_and_its_stated_start_stays_literal(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # A caller's write of the observed state transforms it for the source that
    # observed it, which then writes on from what that write left; the same
    # caller's stated start no longer names a current row.
    db, observation = _temporal_seeded(profile_run)
    reads: list[int] = []
    bounds: dict[str, Any] = {"tx_start": _SEEDED}
    if entity in _TERMS:
        bounds["valid_from"] = _JUN

    def fn(tx: TxnContext) -> None:
        source = _temporal_read(tx, entity, "typed")
        tx.amend_if(entity, entity.label.set("caller"), key=1, **bounds)
        _temporal_flush(tx, entity)
        mark = len(observation.calls)
        tx.amend(source.edit(note="source"))
        _temporal_flush(tx, entity)
        reads.append(_reads_since(observation, mark))

    db.transact(fn, concurrency=concurrency)
    assert reads == [1]
    if entity in _TERMS:
        assert _current(profile_run, entity) == [
            (_ATTEMPT, _JAN, _JUN, "seed", "kept"),
            (_ATTEMPT, _JUN, None, "caller", "source"),
        ]
    else:
        assert _current(profile_run, entity) == [(_ATTEMPT, "caller", "source")]

    def stale(tx: TxnContext) -> None:
        source = _temporal_read(tx, entity, "typed", key=2)
        tx.amend(source.edit(label="first"))
        _temporal_flush(tx, entity)
        tx.amend_if(entity, entity.note.set("stale"), key=2, **bounds)

    with raises_contextualized(WritePreconditionError):
        db.transact(stale, concurrency=concurrency)


@_TERM_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_two_pins_of_one_observation_part_when_a_termination_removes_one(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # Both reads observe the one January row. Terminating March ends the March
    # source, which filling March again does not revive; the June source still
    # writes from June.
    db, _observation = _temporal_seeded(profile_run)
    refused: list[str] = []

    def fn(tx: TxnContext) -> None:
        march = _temporal_read(tx, entity, representation, at=_MAR)
        june = _temporal_read(tx, entity, representation, at=_JUN)
        _terminate(tx, march, until=_APR)
        _temporal_flush(tx, entity)
        with pytest.raises(WriteEvidenceError) as ended:
            _temporal_amend(tx, march, label="march")
        refused.append(ended.value.code)
        _temporal_replace(
            tx, _temporal_read(tx, entity, representation, at=_FEB), label="filled", until=_APR
        )
        _temporal_flush(tx, entity)
        with pytest.raises(WriteEvidenceError) as still_ended:
            _temporal_amend(tx, march, label="march")
        refused.append(still_ended.value.code)
        _temporal_amend(tx, june, label="june")

    db.transact(fn, concurrency=concurrency)

    assert refused == ["write-evidence-consumed"] * 2
    assert _current(profile_run, entity) == [
        (_ATTEMPT, _JAN, _FEB, "seed", "kept"),
        (_ATTEMPT, _FEB, _APR, "filled", "kept"),
        (_ATTEMPT, _APR, _JUN, "seed", "kept"),
        (_ATTEMPT, _JUN, None, "june", "kept"),
    ]


@_TERM_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_continuing_source_reads_only_the_coverage_no_completed_write_produced(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # The June source observed the row ending at September. Its first write
    # produced every row up to there, so its unbounded second write reads only
    # the September row, which no completed write of the attempt produced.
    db, observation = _temporal_seeded(profile_run, split=True)
    reads: list[int] = []

    def fn(tx: TxnContext) -> None:
        source = _temporal_read(tx, entity, representation)
        _temporal_amend(tx, source, label="first", until=_AUG)
        _temporal_flush(tx, entity)
        mark = len(observation.calls)
        _temporal_amend(tx, source, label="second")
        _temporal_flush(tx, entity)
        reads.append(_reads_since(observation, mark))

    db.transact(fn, concurrency=concurrency)

    assert reads == [2]
    assert _current(profile_run, entity) == [
        (_ATTEMPT, _JAN, _JUN, "seed", "kept"),
        (_ATTEMPT, _JUN, _SEP, "second", "kept"),
        (_ATTEMPT, _SEP, None, "second", "later"),
    ]


@_STRATEGIES
@_REPRESENTATIONS
def test_document_content_no_member_declares_survives_in_every_row_a_source_continues_through(
    profile_run: Any, concurrency: _Concurrency, representation: _Representation
) -> None:
    # Later writes split rows only the attempt's completed writes produced,
    # each piece carrying the document those writes stored, so content no
    # member declares reaches every row without being read again.
    db, observation = _temporal_seeded(profile_run)
    profile_run.port.execute(
        'update sc_document_term set payload = payload || \'{"undeclared": "x"}\' where id = 1',
        [],
    )
    reads: list[int] = []

    def fn(tx: TxnContext) -> None:
        source = _temporal_read(tx, DocumentTerm, representation)
        _temporal_amend(tx, source, label="first", until=_AUG)
        _temporal_flush(tx, DocumentTerm)
        mark = len(observation.calls)
        _temporal_amend(tx, source, note="second", until=_JUL)
        _temporal_flush(tx, DocumentTerm)
        _temporal_amend(tx, source, label="third", until=_JUL)
        _temporal_flush(tx, DocumentTerm)
        reads.append(_reads_since(observation, mark))

    db.transact(fn, concurrency=concurrency)

    assert reads == [2]
    rows = profile_run.port.execute(
        "select from_z, payload->>'label', payload->>'note', payload->>'undeclared' "
        "from sc_document_term where id = 1 and out_z = 'infinity' order by from_z",
        [],
    )
    assert [tuple(row) for row in rows] == [
        (_JAN, "seed", "kept", "x"),
        (_JUN, "third", "second", "x"),
        (_JUL, "first", "kept", "x"),
        (_AUG, "seed", "kept", "x"),
    ]


def _temporal_insert(tx: TxnContext, entity: type[Any], key: int, label: str) -> None:
    value = entity(id=key, label=label, note="kept")
    if entity in _TERMS:
        tx.insert(value, valid_from=_JAN)
    else:
        tx.insert(value)


@_TEMPORAL_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_temporal_source_its_attempt_destroyed_stays_ended_through_a_reinsertion(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, representation: _Representation
) -> None:
    # The attempt inserts object 3, reads it, and terminates it through that
    # read from its first instant, removing all of it; inserting it again
    # grants a fresh authority the old source never shares.
    db, _observation = _temporal_seeded(profile_run)
    refused: list[str] = []

    def fn(tx: TxnContext) -> None:
        _temporal_insert(tx, entity, 3, "first")
        _temporal_flush(tx, entity)
        source = _temporal_read(tx, entity, representation, key=3, at=_JAN)
        _terminate(tx, source)
        _temporal_flush(tx, entity)
        for reinserting in (True, False):
            with pytest.raises(WriteEvidenceError) as ended:
                _temporal_amend(tx, source, label="stale")
            refused.append(ended.value.code)
            if reinserting:
                _temporal_insert(tx, entity, 3, "again")
                _temporal_flush(tx, entity)
        _temporal_amend(
            tx, _temporal_read(tx, entity, representation, key=3, at=_JAN), note="fresh"
        )

    db.transact(fn, concurrency=concurrency)

    assert refused == ["write-evidence-consumed"] * 2
    if entity in _TERMS:
        assert _current(profile_run, entity, 3) == [(_ATTEMPT, _JAN, None, "again", "fresh")]
    else:
        assert _current(profile_run, entity, 3) == [(_ATTEMPT, "again", "fresh")]
