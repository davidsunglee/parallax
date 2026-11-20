"""A keyed or target payload is judged names first, then the key that
addresses its object, then its other values, in both representations: an
authored framework-owned member is refused before any value, and a key naming
no object before any member beside it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core._execution._unit_work import instructions as wi
from parallax.core._execution._unit_work.preparation import TYPED, WIRE, WriteRepresentation
from parallax.core.internal.base import Int32, UsageError
from parallax.core.internal.entity._model import model_of
from tests._support.errors import raises_code
from tests._support.write_preparation import (
    REPRESENTATIONS,
    prepare_instruction,
    write_preparation_of,
)

_NS = "row.order"


class Crate(Entity, table="crate", namespace=_NS):
    owner: Attr[str]
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_MODEL: Final = model_of(DomainModel(Crate))
_CRATE: Final = f"{_NS}.Crate"


def _amend(row: Mapping[str, object]) -> list[wi.WriteInstruction]:
    return [
        wi.KeyedWriteInstruction("amend", _CRATE, row),
        wi.TargetWriteInstruction("amend", _CRATE, row, if_version=3),
    ]


def _replace(row: Mapping[str, object]) -> list[wi.WriteInstruction]:
    return [
        wi.KeyedWriteInstruction("replace", _CRATE, row),
        wi.TargetWriteInstruction("replace", _CRATE, row, if_version=3),
    ]


_OWNED: Final = {"id": 1, "owner": 7, "version": 3}


@pytest.mark.parametrize(
    ("representation", "instruction"),
    [
        *((TYPED, instruction) for instruction in _amend(_OWNED)),
        *((WIRE, instruction) for instruction in (*_amend(_OWNED), *_replace(_OWNED))),
    ],
    ids=["typed-keyed-amend", "typed-target-amend", *(f"wire-{i}" for i in range(4))],
)
def test_a_framework_owned_member_is_refused_before_an_earlier_members_value(
    representation: WriteRepresentation, instruction: wi.WriteInstruction
) -> None:
    with raises_code(
        UsageError,
        "framework-owned-member-assigned",
        match=r"Crate\.version: framework-owned fields may not be",
    ):
        prepare_instruction(instruction, write_preparation_of(_MODEL), representation)


@REPRESENTATIONS
@pytest.mark.parametrize(
    "instruction",
    [*_amend({"owner": 7, "id": "bad-key"}), *_replace({"owner": 7, "id": "bad-key"})],
    ids=["keyed-amend", "target-amend", "keyed-replace", "target-replace"],
)
def test_an_addressed_write_judges_its_key_before_any_member_beside_it(
    representation: WriteRepresentation, instruction: wi.WriteInstruction
) -> None:
    """``Crate`` declares its key after ``owner``, and the payload states it
    last, so neither member order nor authored order puts the key first."""
    with pytest.raises(UsageError, match=r"Crate\.id: ") as refused:
        prepare_instruction(instruction, write_preparation_of(_MODEL), representation)

    assert "owner" not in str(refused.value)
