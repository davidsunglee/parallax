"""The Transaction Attempt's write doors select the bounded verb from the
caller's raw ``until``, and the target door hands target preparation the
adapter's input under the caller's revision and window, once for every
representation."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Final, NoReturn, cast

import pytest

from parallax.core._execution._keyed_writes import ResolvedKeyedInsert, ResolvedKeyedWriteSource
from parallax.core._execution._options import OMITTED, Omitted
from parallax.core._execution._publication import SelectedWriteModel
from parallax.core._execution._transaction import _attempt as attempt_module
from parallax.core._execution._transaction._attempt import (
    TargetWriteInput,
    TxnAttempt,
    WriteVerb,
)
from parallax.core._execution._unit_work._write_ownership import KeyedWriteRefusalAdvice
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    TargetMutation,
    WriteAssignment,
)
from parallax.core._execution._unit_work.preparation import (
    TYPED,
    WIRE,
    PartialPayload,
    TargetRevisionArguments,
    WritePreparation,
    WriteRepresentation,
)
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import CompiledEntity, Metamodel, entity_by_name
from tests._support.db_port import ScriptedAdapter, Transact
from tests.unit.core._execution._execution_support import ACCOUNT, itself, scope

_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_UNTIL: Final = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
_STATED_NONE: Final = cast("dt.datetime", None)
_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="not stored", already_stored="already stored", repeated_insert="repeated"
)

type Selected = tuple[KeyedMutation, dt.datetime | None]


class _Prepared(Exception):
    """Ends a door's call once preparation has been handed what it selected."""


def _account(model: Metamodel) -> CompiledEntity:
    entity = entity_by_name(model, "Account")
    assert entity is not None
    return entity


_TARGET: Final = _account(model_of(ACCOUNT))
_KEY: Final = PartialPayload(((0, 7),))


class _KeyedSource:
    def __init__(self, selected: list[Selected]) -> None:
        self._selected = selected

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        return ResolvedKeyedWriteSource(_account(model), None, None, "this", _ADVICE)

    def prepare(
        self,
        preparation: WritePreparation,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedWriteSource,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        self._selected.append((mutation, until))
        raise _Prepared


class _InsertSource:
    def __init__(self, selected: list[Selected]) -> None:
        self._selected = selected

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        return ResolvedKeyedInsert(_account(model), None, "none", _ADVICE)

    def prepare(
        self,
        preparation: WritePreparation,
        mutation: KeyedMutation,
        resolved: ResolvedKeyedInsert,
        /,
        *,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        self._selected.append((mutation, until))
        raise _Prepared


class _TargetAdapter:
    def __init__(self, answer: TargetWriteInput, asked: list[TargetMutation]) -> None:
        self._answer = answer
        self._asked = asked

    def write_input(
        self, write_model: SelectedWriteModel, mutation: TargetMutation
    ) -> TargetWriteInput:
        self._asked.append(mutation)
        return self._answer


type Converted = tuple[
    WriteRepresentation,
    TargetMutation,
    CompiledEntity,
    PartialPayload,
    tuple[WriteAssignment, ...],
    TargetRevisionArguments,
    dt.datetime | None,
    dt.datetime | None,
]


@pytest.fixture
def converted(monkeypatch: pytest.MonkeyPatch) -> list[Converted]:
    """What the target door hands target preparation, which ends the call
    there."""
    calls: list[Converted] = []

    def prepare(
        preparation: WritePreparation,
        representation: WriteRepresentation,
        mutation: TargetMutation,
        target: CompiledEntity,
        payload: PartialPayload,
        *,
        assignments: tuple[WriteAssignment, ...],
        revision: TargetRevisionArguments,
        valid_from: dt.datetime | None,
        until: dt.datetime | None,
    ) -> NoReturn:
        calls.append(
            (representation, mutation, target, payload, assignments, revision, valid_from, until)
        )
        raise _Prepared

    monkeypatch.setattr(attempt_module, "prepare_target_write", prepare)
    return calls


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


@pytest.mark.parametrize(("verb", "until", "expected"), _BY_VERB)
def test_a_keyed_write_selects_its_bounded_verb_from_until(
    verb: WriteVerb, until: dt.datetime | Omitted, expected: Selected
) -> None:
    assert (
        _selected(lambda tx, selected: tx.keyed_write(_KeyedSource(selected), verb, until=until))
        == expected
    )


@pytest.mark.parametrize(("verb", "until", "expected"), _BY_VERB)
def test_a_target_write_selects_its_bounded_verb_from_until(
    converted: list[Converted],
    verb: WriteVerb,
    until: dt.datetime | Omitted,
    expected: Selected,
) -> None:
    asked: list[TargetMutation] = []
    adapter = _TargetAdapter(TargetWriteInput(_TARGET, TYPED, _KEY), asked)

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(_Prepared):
            tx.target_write(adapter, verb, until=until)

    scope(ScriptedAdapter(Transact())).transact(fn, itself)
    [(_, mutation, _, _, _, _, _, bound)] = converted
    assert asked == [expected[0]]
    assert (mutation, bound) == expected


@pytest.mark.parametrize(
    ("answer", "revision", "stated"),
    [
        (
            TargetWriteInput(_TARGET, WIRE, PartialPayload(((0, 7), (2, 5)))),
            {"version": 3},
            TargetRevisionArguments(3, None, ("version",)),
        ),
        (
            TargetWriteInput(_TARGET, TYPED, _KEY, (WriteAssignment("Account.owner", "N"),)),
            {"tx_start": None},
            TargetRevisionArguments(None, None, ("tx_start",)),
        ),
        (
            TargetWriteInput(_TARGET, TYPED, _KEY),
            {"version": 4, "tx_start": _START},
            TargetRevisionArguments(4, _START, ("version", "tx_start")),
        ),
        (TargetWriteInput(_TARGET, WIRE, _KEY), {}, TargetRevisionArguments(None, None, ())),
    ],
)
def test_the_target_door_states_the_adapters_input_under_the_callers_revision_and_window(
    converted: list[Converted],
    answer: TargetWriteInput,
    revision: dict[str, object],
    stated: TargetRevisionArguments,
) -> None:
    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(_Prepared):
            tx.target_write(
                _TargetAdapter(answer, []),
                "amend",
                valid_from=_START,
                until=_UNTIL,
                **cast("dict[str, Any]", revision),
            )

    scope(ScriptedAdapter(Transact())).transact(fn, itself)
    assert converted == [
        (
            answer.representation,
            "amendUntil",
            answer.target,
            answer.payload,
            answer.assignments,
            stated,
            _START,
            _UNTIL,
        )
    ]


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
