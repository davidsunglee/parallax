"""The Transaction Attempt's write doors select the bounded verb from the
caller's raw ``until``, and the target door states the canonical instruction,
once for every representation."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Set
from typing import Any, Final, Literal, NoReturn, cast

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
from parallax.core._execution._unit_work.instructions import (
    KeyedMutation,
    TargetMutation,
    TargetWriteInstruction,
)
from parallax.core._execution._unit_work.retain import KeyedWriteRefusalAdvice
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from tests._support.db_port import ScriptedAdapter, Transact
from tests.unit.core._execution._execution_support import itself, scope

_START: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
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

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        return ResolvedKeyedWriteSource(_account(model), None, None, "this", _ADVICE)

    def prepare(
        self,
        model: Metamodel,
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
        model: Metamodel,
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
    Literal["typed", "wire"],
    TargetWriteInstruction,
    Set[str] | None,
    Callable[[], Mapping[str, object]] | None,
]


@pytest.fixture
def converted(monkeypatch: pytest.MonkeyPatch) -> list[Converted]:
    """What the target door hands the leaf converter it selects, preparation
    ending the call there."""
    calls: list[Converted] = []

    def converter(representation: Literal["typed", "wire"]) -> Callable[..., NoReturn]:
        def prepare(
            instruction: TargetWriteInstruction,
            model: Metamodel,
            *,
            authored_members: Set[str] | None,
            members: Callable[[], Mapping[str, object]] | None,
        ) -> NoReturn:
            calls.append((representation, instruction, authored_members, members))
            raise _Prepared

        return prepare

    monkeypatch.setattr(attempt_module, "prepare_typed_write", converter("typed"))
    monkeypatch.setattr(attempt_module, "prepare_wire_write", converter("wire"))
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
    adapter = _TargetAdapter(TargetWriteInput("Account", {"id": 7}, "typed"), asked)

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(_Prepared):
            tx.target_write(adapter, verb, until=until)

    scope(ScriptedAdapter(Transact())).transact(fn, itself)
    [(_, instruction, _, _)] = converted
    assert asked == [expected[0]]
    assert (instruction.mutation, instruction.until) == expected


def _members() -> Mapping[str, object]:
    return {"owner": "Newton"}


@pytest.mark.parametrize(
    ("answer", "revision", "stated"),
    [
        (
            TargetWriteInput(
                "Account",
                {"id": 7, "balance": 5},
                "wire",
                authored_members=frozenset({"id", "balance"}),
            ),
            {"version": 3},
            (3, None, ("version",)),
        ),
        (
            TargetWriteInput("Account", {"id": 7}, "typed", members=_members),
            {"tx_start": None},
            (None, None, ("tx_start",)),
        ),
        (
            TargetWriteInput("Account", {"id": 7}, "typed"),
            {"version": 4, "tx_start": _START},
            (4, _START, ("version", "tx_start")),
        ),
        (TargetWriteInput("Account", {"id": 7}, "wire"), {}, (None, None, ())),
    ],
)
def test_the_target_door_states_the_adapters_input_under_the_callers_revision_and_window(
    converted: list[Converted],
    answer: TargetWriteInput,
    revision: dict[str, object],
    stated: tuple[object, object, tuple[str, ...]],
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
    if_version, if_tx_start, names = stated
    assert converted == [
        (
            answer.representation,
            TargetWriteInstruction(
                "amendUntil",
                answer.entity,
                answer.row,
                cast("int | None", if_version),
                cast("dt.datetime | None", if_tx_start),
                _START,
                _UNTIL,
                names,
            ),
            answer.authored_members,
            answer.members,
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
