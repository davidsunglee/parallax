"""Admitted writes: each holds only what licenses it (m-unit-work, Docker-free)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest

from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
    prepare_typed_write,
)
from parallax.core._execution._unit_work.write_items import KeyedInsert
from parallax.core.unit_work import KeyedMutation, KeyedWriteInstruction, admitted_write
from tests.unit._corpus_model_support import model as corpus_model

_ACCOUNT = corpus_model("account")


def _prepared(mutation: KeyedMutation, *rows: Mapping[str, object]) -> PreparedKeyedInstruction:
    prepared = prepare_typed_write(KeyedWriteInstruction(mutation, "Account", rows), _ACCOUNT)
    assert isinstance(prepared, PreparedKeyedInstruction)
    return prepared


def _account(account_id: int) -> dict[str, object]:
    return {"id": account_id, "owner": "Ada", "balance": Decimal("1.00")}


def test_an_insert_is_admitted_as_its_own_keyed_insert() -> None:
    prepared = _prepared("insert", _account(1))
    admitted = admitted_write(prepared, None)
    assert isinstance(admitted, KeyedInsert)
    assert admitted.instruction is prepared


@pytest.mark.parametrize(
    ("mutation", "row"),
    [("amend", {"id": 1, "balance": Decimal("2.00")}), ("delete", {"id": 1})],
)
def test_a_write_of_existing_state_needs_a_licence_beyond_itself(
    mutation: KeyedMutation, row: Mapping[str, object]
) -> None:
    with pytest.raises(ValueError, match="only an insert is admitted unlicensed"):
        admitted_write(_prepared(mutation, row), None)


def test_an_admitted_insert_opens_one_row() -> None:
    with pytest.raises(ValueError, match="opens 2 rows"):
        admitted_write(_prepared("insert", _account(1), _account(2)), None)
