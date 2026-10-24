"""The keyed write ingress names the object a write addresses once, for every
representation: by the source's Read Evidence, or else by the row the write
prepared."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Final, Literal

import pytest

from parallax.core._execution._keyed_writes import (
    OpenedKeyedWrite,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_instruction,
)
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core._execution._unit_work._errors import (
    KeyedWriteValueError,
    UnitOfWorkError,
    WriteEvidenceError,
)
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    ParticipationToken,
    ReadEvidence,
)
from parallax.core._execution._unit_work.write_items import InsertionAuthorizedWrite, KeyedInsert
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.write_plan import ObjectKey
from tests._support.db_port import ScriptedAdapter, Transact, Write
from tests.unit.core._execution._execution_support import ACCOUNT, itself, scope

_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="repeated"
)


def _account(model: Metamodel) -> EntityMetadata:
    entity = entity_by_name(model, "Account")
    assert entity is not None
    return entity


_ACCOUNT: Final = _account(model_of(ACCOUNT)).identity


def _key(entity: EntityIdentity, account_id: int) -> ObjectKey:
    return ObjectKey(entity, (("id", account_id),))


def _prepared(
    model: Metamodel, mutation: KeyedMutation, entity: EntityMetadata, row: Mapping[str, object]
) -> PreparedKeyedInstruction:
    return prepare_typed_write(keyed_instruction(mutation, entity.identity, row), model)


type Named = Literal["evidence", "authoring", "both", "neither"]


def _resolved(entity: EntityMetadata, named: Named) -> ResolvedKeyedWriteSource:
    """A source whose Read Evidence names account 2 and whose insertion
    authority names account 3, as ``named`` selects; neither is this attempt's,
    so the write is refused for its evidence."""
    evidence = ReadEvidence(entity.identity, _key(entity.identity, 2), ParticipationToken(), None)
    authoring = InsertionIdentity(_key(entity.identity, 3))
    return ResolvedKeyedWriteSource(
        entity,
        None,
        evidence if named in ("evidence", "both") else None,
        "this",
        _ADVICE,
        authoring if named in ("authoring", "both") else None,
    )


class _AmendingAccountOne:
    """A source whose amendment's row keys account 1, whatever it names."""

    def __init__(self, named: Named) -> None:
        self._named: Named = named

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        return _resolved(_account(model), self._named)

    def prepare(
        self,
        model: Metamodel,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedInstruction:
        return _prepared(model, mutation, resolved.entity, {"id": 1, "balance": Decimal("9.00")})


class _OpeningAccountSeven:
    def __init__(self, advice: KeyedWriteRefusalAdvice = _ADVICE) -> None:
        self._advice = advice

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        return ResolvedKeyedInsert(_account(model), None, "none", self._advice)

    def prepare(
        self,
        model: Metamodel,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedInstruction:
        row = {"id": 7, "owner": "Newton", "balance": Decimal("5.00")}
        return _prepared(model, mutation, resolved.entity, row)


@pytest.mark.parametrize(
    ("named", "account_id"),
    [("evidence", 2), ("authoring", 3), ("both", 2), ("neither", None)],
)
def test_a_resolved_source_names_the_object_its_evidence_or_else_its_authoring_names(
    named: Named, account_id: int | None
) -> None:
    entity = _account(model_of(ACCOUNT))

    resolved = _resolved(entity, named)

    assert resolved.object_key == (None if account_id is None else _key(_ACCOUNT, account_id))


@pytest.mark.parametrize(
    ("named", "account_id"),
    [("evidence", 2), ("both", 2), ("authoring", 1), ("neither", 1)],
)
def test_an_evidence_refusal_names_the_read_object_before_the_prepared_row(
    named: Named, account_id: int
) -> None:
    refused: list[WriteEvidenceError] = []

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(WriteEvidenceError) as refusal:
            tx.keyed_write(_AmendingAccountOne(named), "amend")
        refused.append(refusal.value)

    scope(ScriptedAdapter(Transact())).transact(fn, itself)
    [refusal] = refused
    assert refusal.code == "write-evidence-unavailable"
    assert refusal.object_key == _key(_ACCOUNT, account_id)


def test_an_insert_opens_the_object_its_prepared_row_keys() -> None:
    def fn(tx: TxnAttempt) -> OpenedKeyedWrite:
        return tx.keyed_insert(_OpeningAccountSeven())

    opened = scope(ScriptedAdapter(Transact(Write()))).transact(fn, itself)

    assert opened.object_key == _key(_ACCOUNT, 7)
    assert opened.authority.object_key == opened.object_key


def test_a_repeated_insert_is_refused_with_its_openers_advice_before_anything_buffers() -> None:
    repeat = KeyedWriteRefusalAdvice(
        not_stored="not stored", already_stored="already stored", repeated_insert="the repeat's"
    )

    def fn(tx: TxnAttempt) -> None:
        opened = tx.keyed_insert(_OpeningAccountSeven())
        with pytest.raises(KeyedWriteValueError) as refusal:
            tx.keyed_insert(_OpeningAccountSeven(repeat))
        assert refusal.value.code == "write-value-already-stored"
        assert refusal.value.message.endswith("repeated")
        assert refusal.value.identity == _ACCOUNT
        assert tx.uow.insertion_authority(opened.authority) is None

    # Only the opening insert executes.
    scope(ScriptedAdapter(Transact(Write()))).transact(fn, itself)


class _Abandoned(Exception):
    """Ends a transaction whose buffer no flush is meant to plan."""


class _RevisingInsertedAccountSeven:
    """A source carrying the insertion authority of account 7, whose
    preparation runs caller-owned code that ``interferes`` with that insertion
    before the row is derived."""

    def __init__(self, authoring: InsertionIdentity, interferes: Callable[[], object]) -> None:
        self._authoring = authoring
        self._interferes = interferes

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        return ResolvedKeyedWriteSource(
            _account(model), None, None, "none", _ADVICE, self._authoring
        )

    def prepare(
        self,
        model: Metamodel,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> PreparedKeyedInstruction:
        self._interferes()
        return _prepared(model, mutation, resolved.entity, {"id": 7, "balance": Decimal("9.00")})


@pytest.mark.parametrize("interference", ["superseded", "retired"])
def test_an_insertion_its_writes_preparation_ended_is_refused_when_the_write_is_admitted(
    interference: str,
) -> None:
    # The verb found the insertion standing before preparation, which lifted
    # the provenance refusal; admission asks again once preparation is done.
    model = model_of(ACCOUNT)
    entity = _account(model)
    key = _key(_ACCOUNT, 7)
    opening = _prepared(
        model, "insert", entity, {"id": 7, "owner": "N", "balance": Decimal("5.00")}
    )

    def fn(tx: TxnAttempt) -> None:
        authority = tx.uow.buffer_insert(KeyedInsert(opening, key), insertion_advice=None)
        assert authority is not None

        def interfere() -> object:
            if interference == "superseded":
                return tx.uow.buffer_insert(KeyedInsert(opening, key), insertion_advice=None)
            deletion = _prepared(model, "delete", entity, {"id": 7})
            return tx.uow.buffer(InsertionAuthorizedWrite(deletion, key, authority))

        with pytest.raises(UnitOfWorkError, match="no longer stands"):
            tx.keyed_write(_RevisingInsertedAccountSeven(authority, interfere), "amend")
        raise _Abandoned

    with pytest.raises(ExecutionFailure) as failure:
        scope(ScriptedAdapter(Transact())).transact(fn, itself)
    assert isinstance(failure.value.__cause__, _Abandoned)
