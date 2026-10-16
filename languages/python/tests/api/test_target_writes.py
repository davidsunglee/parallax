"""Caller-addressed patch, replacement, and deletion of Non-Temporal rows, against
real Postgres.

A web client holds a key and the version an earlier query returned. Each case
commits a starting row in one transaction, writes it from the caller's own
revision in a second, and reads back the stored row under both storage layouts:
what was assigned, what survived, what a replacement reset, the version the
write advanced to, and the row a deletion removed — or, when the caller's
revision no longer holds, that nothing changed and nothing retried. An
unversioned row has no revision to state, so it is written through a read of
the writing transaction instead.

Standalone Docker-backed proofs, like `test_insertion_authority.py`: each is a
developer choreography rather than a case's authored observation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Document, DomainModel, Entity, ValueObject, attr
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.unit_work import (
    WriteEvidenceError,
    WriteInstructionError,
    WritePreconditionError,
)
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root
from tests.api._peer_commit import commit_as_a_peer

_NAMESPACE = "target.writes"
_AT = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)


class Spec(ValueObject):
    title: Attr[str | None]
    kind: Attr[str | None]


class Mark(ValueObject):
    code: Attr[str | None]


class ColumnsAccount(Entity, table="tw_columns_account", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentAccount(Entity, table="tw_document_account", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]
    version: Attr[int] = attr(optimistic_locking=True)


class ColumnsWallet(Entity, table="tw_columns_wallet", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


class DocumentWallet(Entity, table="tw_document_wallet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    note: Attr[str | None] = attr(max_length=16)


_MODEL = DomainModel(ColumnsAccount, DocumentAccount, ColumnsWallet, DocumentWallet)
_ACCOUNTS = (ColumnsAccount, DocumentAccount)
_WALLETS = (ColumnsWallet, DocumentWallet)
_DOCUMENT = (DocumentAccount, DocumentWallet)
_TABLES: dict[type[Any], str] = {
    ColumnsAccount: "tw_columns_account",
    DocumentAccount: "tw_document_account",
    ColumnsWallet: "tw_columns_wallet",
    DocumentWallet: "tw_document_wallet",
}

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_ACCOUNT_AXES = pytest.mark.parametrize("entity", _ACCOUNTS, ids=["columns", "document"])
_WALLET_AXES = pytest.mark.parametrize("entity", _WALLETS, ids=["columns", "document"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_NO_MARKS: list[object] = []
_SPEC = {"title": "carried", "kind": "seed"}
_SEED: dict[str, object] = {
    "label": "seed",
    "note": "kept",
    "spec": _SPEC,
    "marks": [{"code": "a"}],
}
_WALLET_SEED: dict[str, object] = {"label": "seed", "note": "kept"}


def _db(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL, clock=FixedClock(_AT))).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENT else member


def _seeded(profile_run: Any, entity: type[Any]) -> ScopedDatabase:
    db = _db(profile_run)
    db.transact(lambda tx: tx.wire.insert(_name(entity), {"id": 1, **_seed(entity)}))
    return db


def _seed(entity: type[Any]) -> dict[str, object]:
    return _SEED if entity in _ACCOUNTS else _WALLET_SEED


def _accounts(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    members = ", ".join(_member(entity, name) for name in ("label", "note", "spec", "marks"))
    sql = f"select id, {members}, version from {_TABLES[entity]} order by id"
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _wallets(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        f"select id, {_member(entity, 'label')}, {_member(entity, 'note')} "
        f"from {_TABLES[entity]} order by id"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _patch(tx: TxnContext, entity: type[Any], version: int = 1, **changes: object) -> None:
    tx.wire.amend_if(_name(entity), {"id": 1, **changes}, version=version)


def _replace(
    tx: TxnContext,
    entity: type[Any],
    representation: _Representation,
    version: int = 1,
    **data: object,
) -> None:
    if representation == "typed":
        tx.replace_if(entity(id=1, **data), version=version)
    else:
        tx.wire.replace_if(_name(entity), {"id": 1, **data}, version=version)


def _delete(
    tx: TxnContext, entity: type[Any], representation: _Representation, version: int = 1
) -> None:
    if representation == "typed":
        tx.delete_if(entity, key=1, version=version)
    else:
        tx.wire.delete_if(_name(entity), {"id": 1}, version=version)


def _read(tx: TxnContext, entity: type[Any]) -> Any:
    return tx.find(entity.where(entity.id == 1)).result()


# --------------------------------------------------------------------------- #
# The caller's revision addresses a committed row; no read precedes the write. #
# --------------------------------------------------------------------------- #
@_ACCOUNT_AXES
@_STRATEGIES
def test_a_patch_assigns_what_it_states_and_keeps_every_other_member(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity)
    db.transact(lambda tx: _patch(tx, entity, label="patched"), concurrency=concurrency)
    assert _accounts(profile_run, entity) == [(1, "patched", "kept", _SPEC, [{"code": "a"}], 2)]


@_ACCOUNT_AXES
def test_a_patch_replaces_an_occurrence_it_assigns_whole(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)
    db.transact(lambda tx: _patch(tx, entity, spec={"title": "patched"}))
    assert _accounts(profile_run, entity)[0][3] == {"title": "patched"}


@_ACCOUNT_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_replacement_states_the_whole_writable_state(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded(profile_run, entity)
    db.transact(
        lambda tx: _replace(tx, entity, representation, label="replaced"),
        concurrency=concurrency,
    )
    assert _accounts(profile_run, entity) == [(1, "replaced", None, None, [], 2)]


@_ACCOUNT_AXES
def test_an_equal_valued_target_write_still_advances_the_version(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        _patch(tx, entity, label="other")
        _patch(tx, entity, label="seed")

    db.transact(fn)
    assert _accounts(profile_run, entity) == [(1, "seed", "kept", _SPEC, [{"code": "a"}], 2)]


@_ACCOUNT_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_deletion_removes_the_row_its_callers_revision_names(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _seeded(profile_run, entity)
    db.transact(
        lambda tx: tx.wire.insert(_name(entity), {"id": 2, **_seed(entity)}),
    )
    db.transact(lambda tx: _delete(tx, entity, representation), concurrency=concurrency)
    assert [row[0] for row in _accounts(profile_run, entity)] == [2]


@_ACCOUNT_AXES
@_STRATEGIES
@pytest.mark.parametrize("verb", ["patch", "delete"])
@pytest.mark.parametrize("peer", ["revised", "deleted"])
def test_a_revision_that_no_longer_holds_fails_without_retry_and_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, verb: str, peer: str
) -> None:
    db = _seeded(profile_run, entity)

    def by_peer(tx: TxnContext) -> None:
        source = _read(tx, entity)
        if peer == "revised":
            tx.amend(source.edit(label="peer"))
        else:
            tx.delete(source)

    db.transact(by_peer)
    before = _accounts(profile_run, entity)
    attempts = 0

    def stale(tx: TxnContext) -> None:
        nonlocal attempts
        attempts += 1
        if verb == "patch":
            _patch(tx, entity, label="stale")
        else:
            _delete(tx, entity, "wire")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(stale, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert failed.value.cause.expected == 1
    assert attempts == 1
    assert _accounts(profile_run, entity) == before


@_WALLET_AXES
def test_an_unversioned_row_takes_no_conditional_write_and_is_written_through_a_read(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        for conditional in (
            lambda: tx.wire.amend_if(_name(entity), {"id": 1, "label": "patched"}, version=1),
            lambda: tx.wire.replace_if(_name(entity), {"id": 1, "label": "replaced"}, version=1),
            lambda: tx.wire.delete_if(_name(entity), {"id": 1}, version=1),
        ):
            with pytest.raises(WriteInstructionError, match="has none to state"):
                conditional()
        tx.amend(_read(tx, entity).edit(label="patched"))

    db.transact(fn)
    assert _wallets(profile_run, entity) == [(1, "patched", "kept")]


# --------------------------------------------------------------------------- #
# Exact composition with observed writes, and the conditions it keeps.         #
# --------------------------------------------------------------------------- #
@_ACCOUNT_AXES
@_STRATEGIES
@pytest.mark.parametrize(
    "sequence, stored",
    [
        pytest.param("P-O-O", (1, "observed", "observed", _SPEC, [{"code": "a"}], 2)),
        pytest.param("R-O-P", (1, "patched", "observed", None, _NO_MARKS, 2)),
        pytest.param("O-R-D", None),
        pytest.param("P-D", None),
    ],
)
def test_target_and_observed_writes_of_one_state_compose_into_one_effect(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    sequence: str,
    stored: tuple[object, ...] | None,
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        source = _read(tx, entity)
        for step in sequence.split("-"):
            if step == "P":
                _patch(tx, entity, label="patched")
            elif step == "R":
                _replace(tx, entity, "wire", label="replaced")
            elif step == "D":
                tx.delete(source)
            else:
                # Each edit derives from the last, so the second observed write
                # restates the first's note beside its own label.
                source = source.edit(
                    **({"label": "observed"} if source.note == "observed" else {"note": "observed"})
                )
                tx.amend(source)
        _read_other(tx, entity)
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.amend(source.edit(label="again"))

    db.transact(fn, concurrency=concurrency)
    assert _accounts(profile_run, entity) == ([] if stored is None else [stored])


def _read_other(tx: TxnContext, entity: type[Any]) -> None:
    tx.find(entity.where(entity.id == 2))


@_ACCOUNT_AXES
def test_a_stale_observed_source_a_replacement_overwrote_still_fails_the_write(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        stale = _read(tx, entity)
        commit_as_a_peer(
            lambda: db.transact(lambda peer: peer.amend(_read(peer, entity).edit(note="peer")))
        )
        tx.amend(stale.edit(label="stale"))
        _replace(tx, entity, "wire", label="replaced")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _accounts(profile_run, entity)[0][1:3] == ("seed", "peer")


# --------------------------------------------------------------------------- #
# An object the attempt inserted is the insertion's to write until commit.    #
# --------------------------------------------------------------------------- #
@_ACCOUNT_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_target_write_of_an_object_this_attempt_inserted_is_refused_until_commit(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _db(profile_run)

    def fn(tx: TxnContext) -> None:
        inserted = tx.wire.insert(_name(entity), {"id": 1, **_seed(entity)})
        fresh: Any = None
        for flushed in (False, True):
            if flushed:
                # A read of the row itself flushes the insertion and supplies the
                # actual stored revision under this attempt's participation.
                fresh = _read(tx, entity)
                assert fresh.version == 1
            for refused in (
                lambda: (
                    _replace(tx, entity, "typed", label="target")
                    if representation == "typed"
                    else _patch(tx, entity, label="target")
                ),
                lambda: _delete(tx, entity, representation),
            ):
                with pytest.raises(WriteEvidenceError, match="write-evidence-inserted"):
                    refused()
            _patch(tx, entity)
        tx.amend(fresh.edit(note="observed"))
        tx.wire.amend(inserted, {"label": "authored"})

    db.transact(fn, concurrency=concurrency)
    assert _accounts(profile_run, entity)[0][1:3] == ("authored", "observed")
    db.transact(lambda tx: _patch(tx, entity, version=2, label="later"), concurrency=concurrency)
    assert _accounts(profile_run, entity)[0][1:3] == ("later", "observed")


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_committed_row_this_attempt_rewrote_takes_a_target_write_at_its_new_version(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        tx.amend(_read(tx, entity).edit(note="observed"))
        assert _read(tx, entity).version == 2
        _patch(tx, entity, version=2, label="patched")

    db.transact(fn, concurrency=concurrency)
    assert _accounts(profile_run, entity) == [(1, "patched", "observed", _SPEC, [{"code": "a"}], 3)]


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_token_this_attempts_own_flush_outdated_fails_and_rolls_the_attempt_back(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity)
    before = _accounts(profile_run, entity)

    def fn(tx: TxnContext) -> None:
        tx.amend(_read(tx, entity).edit(note="observed"))
        _read_other(tx, entity)
        _patch(tx, entity, version=1, label="patched")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _accounts(profile_run, entity) == before
