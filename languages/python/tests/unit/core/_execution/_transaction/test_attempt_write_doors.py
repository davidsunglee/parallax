"""The Transaction Attempt's write doors select the bounded verb from the
caller's raw ``until``, once for every representation."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Final, Literal, NoReturn, cast

import pytest

from parallax.core._execution._keyed_writes import (
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    TargetRevisionArguments,
)
from parallax.core._execution._options import OMITTED, Omitted
from parallax.core._execution._publication import SelectedWriteModel
from parallax.core._execution._transaction._attempt import TxnAttempt, WriteVerb
from parallax.core._execution._unit_work.instructions import KeyedMutation, TargetMutation
from parallax.core._execution._unit_work.retain import KeyedWriteRefusalAdvice
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from tests._support.db_port import ScriptedAdapter, Transact
from tests.unit.core._execution._execution_support import itself, scope

_UNTIL: Final = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
_STATED_NONE: Final = cast("dt.datetime", None)
_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="repeated"
)

type Selected = tuple[KeyedMutation, dt.datetime | None]


class _Prepared(Exception):
    """Ends a door's call once preparation has been handed what it selected."""


def _account(model: Metamodel) -> EntityMetadata:
    entity = entity_by_name(model, "Account")
    assert entity is not None
    return entity


class _KeyedSource:
    def __init__(self, selected: list[Selected]) -> None:
        self._selected = selected
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        self._mutation = mutation

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        return ResolvedKeyedWriteSource(_account(model), None, None, "this", _ADVICE)

    def prepare(
        self,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        assert self._mutation is not None
        self._selected.append((self._mutation, until))
        raise _Prepared


class _InsertSource:
    def __init__(self, selected: list[Selected]) -> None:
        self._selected = selected
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        self._mutation = mutation

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        return ResolvedKeyedInsert(_account(model), None, "none", _ADVICE)

    def prepare(
        self,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        assert self._mutation is not None
        self._selected.append((self._mutation, until))
        raise _Prepared


class _TargetAdapter:
    def __init__(self, selected: list[Selected]) -> None:
        self._selected = selected

    def prepare(
        self,
        write_model: SelectedWriteModel,
        mutation: TargetMutation,
        revision_arguments: TargetRevisionArguments,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        self._selected.append((mutation, until))
        raise _Prepared


def _selected(write: Callable[[TxnAttempt, list[Selected]], object]) -> Selected:
    selected: list[Selected] = []

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(_Prepared):
            write(tx, selected)

    scope(ScriptedAdapter(Transact())).transact(fn, itself)
    [answer] = selected
    return answer


_BY_VERB: Final[tuple[tuple[WriteVerb, dt.datetime | Omitted, Selected], ...]] = (
    ("amend", OMITTED, ("amend", None)),
    ("amend", _UNTIL, ("amendUntil", _UNTIL)),
    ("amend", _STATED_NONE, ("amendUntil", None)),
    ("replace", OMITTED, ("replace", None)),
    ("replace", _UNTIL, ("replaceUntil", _UNTIL)),
    ("replace", _STATED_NONE, ("replaceUntil", None)),
    ("terminate", OMITTED, ("terminate", None)),
    ("terminate", _UNTIL, ("terminateUntil", _UNTIL)),
    ("terminate", _STATED_NONE, ("terminateUntil", None)),
    # Deletion has no bounded form: a stated bound reaches preparation, which
    # refuses it, beside the unbounded verb.
    ("delete", OMITTED, ("delete", None)),
    ("delete", _UNTIL, ("delete", _UNTIL)),
)


@pytest.mark.parametrize("door", ["keyed_write", "target_write"])
@pytest.mark.parametrize(("verb", "until", "expected"), _BY_VERB)
def test_a_write_over_an_existing_object_selects_its_bounded_verb_from_until(
    door: Literal["keyed_write", "target_write"],
    verb: WriteVerb,
    until: dt.datetime | Omitted,
    expected: Selected,
) -> None:
    def write(tx: TxnAttempt, selected: list[Selected]) -> None:
        if door == "keyed_write":
            tx.keyed_write(_KeyedSource(selected), verb, until=until)
        else:
            tx.target_write(_TargetAdapter(selected), verb, until=until)

    assert _selected(write) == expected


@pytest.mark.parametrize(
    ("until", "expected"),
    [
        (OMITTED, ("insert", None)),
        (_UNTIL, ("insertUntil", _UNTIL)),
        (_STATED_NONE, ("insertUntil", None)),
    ],
)
def test_an_insert_selects_its_bounded_form_from_until(
    until: dt.datetime | Omitted, expected: Selected
) -> None:
    assert (
        _selected(lambda tx, selected: tx.keyed_insert(_InsertSource(selected), until=until))
        == expected
    )
