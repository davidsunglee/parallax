"""A keyed or target row is judged names first, then its values, on both
lanes: an authored framework-owned member is refused before any value, and a
partial row judges the key that addresses its object after every assignment."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core._execution._unit_work import instructions as wi
from parallax.core.base import Int32
from parallax.core.entity._model import model_of
from tests._support.write_preparation import write_preparation_of

_NS = "row.order"


class Crate(Entity, table="crate", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


_MODEL: Final = model_of(DomainModel(Crate))
_LANES: Final = pytest.mark.parametrize(
    "prepare",
    [
        pytest.param(wi.prepare_typed_write, id="typed"),
        pytest.param(wi.prepare_wire_write, id="wire"),
    ],
)
_CRATE: Final = f"{_NS}.Crate"

type _Prepare = Callable[..., Any]


@_LANES
@pytest.mark.parametrize(
    ("instruction", "authored"),
    [
        pytest.param(
            wi.KeyedWriteInstruction("amend", _CRATE, ({"id": 1, "owner": 7, "version": 3},)),
            frozenset({"owner", "version"}),
            id="keyed-amend",
        ),
        pytest.param(
            wi.KeyedWriteInstruction("replace", _CRATE, ({"id": 1, "owner": 7, "version": 3},)),
            None,
            id="keyed-replace",
        ),
        pytest.param(
            wi.TargetWriteInstruction(
                "amend", _CRATE, {"id": 1, "owner": 7, "version": 3}, if_version=3
            ),
            None,
            id="target-amend",
        ),
        pytest.param(
            wi.TargetWriteInstruction(
                "replace", _CRATE, {"id": 1, "owner": 7, "version": 3}, if_version=3
            ),
            None,
            id="target-replace",
        ),
    ],
)
def test_a_framework_owned_member_is_refused_before_an_earlier_members_value(
    prepare: _Prepare, instruction: wi.WriteInstruction, authored: frozenset[str] | None
) -> None:
    with pytest.raises(
        wi.WriteInstructionError, match=r"Crate\.version: framework-owned fields may not be"
    ):
        prepare(instruction, write_preparation_of(_MODEL), authored_members=authored)


@_LANES
@pytest.mark.parametrize(
    "instruction",
    [
        pytest.param(
            wi.KeyedWriteInstruction("amend", _CRATE, ({"id": "bad-key", "owner": 7},)),
            id="keyed-amend",
        ),
        pytest.param(
            wi.TargetWriteInstruction("amend", _CRATE, {"id": "bad-key", "owner": 7}, if_version=3),
            id="target-amend",
        ),
    ],
)
def test_an_amendment_judges_its_key_after_every_assignment(
    prepare: _Prepare, instruction: wi.WriteInstruction
) -> None:
    with pytest.raises(ValueError, match=r"Crate\.owner: ") as refused:
        prepare(instruction, write_preparation_of(_MODEL))

    assert "bad-key" not in str(refused.value)
