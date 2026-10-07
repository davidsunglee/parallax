"""Caller-addressed patch and replacement of Non-Temporal rows, against real Postgres.

A web client holds a key and the version an earlier query returned. Each case
commits a starting row in one transaction, writes it from the caller's own
revision in a second, and reads back the stored row under both storage layouts:
what was assigned, what survived, what a replacement reset, and the version the
write advanced to — or, when the caller's revision no longer holds, that
nothing changed and nothing retried.

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
from parallax.core.unit_work import MissingTargetError, WriteEvidenceError, WritePreconditionError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

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


def _stated(entity: type[Any], version: int) -> int | None:
    """The revision a caller states for ``entity``: its version, or none at all
    for an unversioned Entity."""
    return version if entity in _ACCOUNTS else None


def _stored(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    return (_accounts if entity in _ACCOUNTS else _wallets)(profile_run, entity)


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


def _patch(tx: Transaction, entity: type[Any], version: int | None = 1, **changes: object) -> None:
    tx.wire.update(_name(entity), {"id": 1, **changes}, if_version=version)


def _replace(
    tx: Transaction,
    entity: type[Any],
    representation: _Representation,
    version: int | None = 1,
    **data: object,
) -> None:
    if representation == "typed":
        tx.replace(entity(id=1, **data), if_version=version)
    else:
        tx.wire.replace(_name(entity), {"id": 1, **data}, if_version=version)


def _read(tx: Transaction, entity: type[Any]) -> Any:
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

    def fn(tx: Transaction) -> None:
        _patch(tx, entity, label="other")
        _patch(tx, entity, label="seed")

    db.transact(fn)
    assert _accounts(profile_run, entity) == [(1, "seed", "kept", _SPEC, [{"code": "a"}], 2)]


@_ACCOUNT_AXES
@_STRATEGIES
@pytest.mark.parametrize("peer", ["revised", "deleted"])
def test_a_revision_that_no_longer_holds_fails_without_retry_and_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, peer: str
) -> None:
    db = _seeded(profile_run, entity)

    def by_peer(tx: Transaction) -> None:
        source = _read(tx, entity)
        if peer == "revised":
            tx.update(source.edit(label="peer"))
        else:
            tx.delete(source)

    db.transact(by_peer)
    before = _accounts(profile_run, entity)
    attempts = 0

    def stale(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _patch(tx, entity, label="stale")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(stale, concurrency=concurrency, retry_optimistic_conflicts=True)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert failed.value.cause.expected == 1
    assert attempts == 1
    assert _accounts(profile_run, entity) == before


@_WALLET_AXES
def test_an_unversioned_target_writes_under_the_locking_fallback_and_misses_as_a_missing_target(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)
    db.transact(lambda tx: _patch(tx, entity, version=None, label="patched"))
    assert _wallets(profile_run, entity) == [(1, "patched", "kept")]
    db.transact(lambda tx: _replace(tx, entity, "wire", version=None, label="replaced"))
    assert _wallets(profile_run, entity) == [(1, "replaced", None)]

    def missing(tx: Transaction) -> None:
        tx.wire.update(_name(entity), {"id": 2, "label": "nobody"})

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(missing)
    assert isinstance(failed.value.cause, MissingTargetError)
    assert _wallets(profile_run, entity) == [(1, "replaced", None)]


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

    def fn(tx: Transaction) -> None:
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
                tx.update(source)
        _read_other(tx, entity)
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.update(source.edit(label="again"))

    db.transact(fn, concurrency=concurrency)
    assert _accounts(profile_run, entity) == ([] if stored is None else [stored])


def _read_other(tx: Transaction, entity: type[Any]) -> None:
    tx.find(entity.where(entity.id == 2))


@_ACCOUNT_AXES
def test_a_stale_observed_source_a_replacement_overwrote_still_fails_the_write(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded(profile_run, entity)
    stale = db.find(entity.where(entity.id == 1)).result()
    db.transact(lambda tx: tx.update(_read(tx, entity).edit(note="peer")))

    def fn(tx: Transaction) -> None:
        tx.update(stale.edit(label="stale"))
        _replace(tx, entity, "wire", label="replaced")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _accounts(profile_run, entity)[0][1:3] == ("seed", "peer")


@_WALLET_AXES
@pytest.mark.parametrize(
    "sequence, stored",
    [
        pytest.param("O-P", (1, "patched", "observed")),
        pytest.param("P-O", (1, "patched", "observed")),
        pytest.param("R-O", (1, "replaced", "observed")),
        pytest.param("P-D", None),
    ],
)
def test_an_unversioned_target_and_observed_writes_of_one_object_compose(
    profile_run: Any, entity: type[Any], sequence: str, stored: tuple[object, ...] | None
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: Transaction) -> None:
        source = _read(tx, entity)
        for step in sequence.split("-"):
            if step == "P":
                _patch(tx, entity, version=None, label="patched")
            elif step == "R":
                _replace(tx, entity, "wire", version=None, label="replaced")
            elif step == "D":
                tx.delete(source)
            else:
                tx.update(source.edit(note="observed"))
        _read_other(tx, entity)
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.update(source.edit(label="again"))

    db.transact(fn)
    assert _wallets(profile_run, entity) == ([] if stored is None else [stored])


# --------------------------------------------------------------------------- #
# An object the attempt inserted is the insertion's to write until commit.    #
# --------------------------------------------------------------------------- #
_ENTITY_AXES = pytest.mark.parametrize(
    "entity",
    (*_ACCOUNTS, *_WALLETS),
    ids=["versioned-columns", "versioned-document", "unversioned-columns", "unversioned-document"],
)


@_ENTITY_AXES
@_STRATEGIES
@_REPRESENTATIONS
def test_a_target_write_of_an_object_this_attempt_inserted_is_refused_until_commit(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    db = _db(profile_run)
    stated = _stated(entity, 1)

    def fn(tx: Transaction) -> None:
        inserted = tx.wire.insert(_name(entity), {"id": 1, **_seed(entity)})
        fresh: Any = None
        for flushed in (False, True):
            if flushed:
                # A read of the row itself flushes the insertion and supplies the
                # actual stored revision under this attempt's participation.
                fresh = _read(tx, entity)
                assert getattr(fresh, "version", None) == stated
            with pytest.raises(WriteEvidenceError, match="write-evidence-inserted"):
                if representation == "typed":
                    _replace(tx, entity, "typed", version=stated, label="target")
                else:
                    _patch(tx, entity, version=stated, label="target")
            _patch(tx, entity, version=stated)
        tx.update(fresh.edit(note="observed"))
        tx.wire.update(inserted, {"label": "authored"})

    db.transact(fn, concurrency=concurrency)
    assert _stored(profile_run, entity)[0][1:3] == ("authored", "observed")
    db.transact(
        lambda tx: _patch(tx, entity, version=_stated(entity, 2), label="later"),
        concurrency=concurrency,
    )
    assert _stored(profile_run, entity)[0][1:3] == ("later", "observed")


@_ACCOUNT_AXES
@_STRATEGIES
def test_a_committed_row_this_attempt_rewrote_takes_a_target_write_at_its_new_version(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity)

    def fn(tx: Transaction) -> None:
        tx.update(_read(tx, entity).edit(note="observed"))
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

    def fn(tx: Transaction) -> None:
        tx.update(_read(tx, entity).edit(note="observed"))
        _read_other(tx, entity)
        _patch(tx, entity, version=1, label="patched")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _accounts(profile_run, entity) == before
