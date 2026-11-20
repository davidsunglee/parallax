"""Each family entry reads its payload once, judges its key once and first, and
takes only the payload shape its verb states."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Final

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core._execution._unit_work import instructions as wi
from parallax.core._execution._unit_work.preparation import (
    TYPED,
    UNSTATED,
    WIRE,
    CompletePayload,
    PartialPayload,
    TargetRevisionArguments,
    WriteRepresentation,
)
from parallax.core.internal import predicate as predicate_algebra
from parallax.core.internal.base import Int32, UsageError
from parallax.core.internal.document_codec._plan import AuthoringPlan
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import CompiledEntity
from parallax.core.internal.planned_step.managed_row import named_members
from tests._support.errors import raises_code
from tests._support.write_preparation import REPRESENTATIONS, write_preparation_of

_NS = "payload.order"


class Gadget(Entity, table="gadget", namespace=_NS):
    label: Attr[str]
    id: Attr[int] = attr(primary_key=True)
    price: Attr[Decimal] = attr(precision=6, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Plain(Entity, table="plain", namespace=_NS):
    label: Attr[str]
    id: Attr[int] = attr(primary_key=True)


_MODEL: Final = model_of(DomainModel(Gadget, Plain))
_PREPARATION: Final = write_preparation_of(_MODEL)
_REVISION: Final = TargetRevisionArguments(1, None, ("version",))


def _target(entity: type[Entity]) -> CompiledEntity:
    compiled = _MODEL.entity(entity.identity)
    assert compiled is not None
    return compiled


_GADGET: Final = _target(Gadget)
_PLAIN: Final = _target(Plain)
_ABSENT: Final = _PREPARATION.absent


def _once(*values: object) -> Iterator[object]:
    """``values`` as an input that can be read only once."""
    yield from values


def test_a_typed_opening_reads_a_one_shot_payload_once() -> None:
    prepared = wi.prepare_insert(
        _PREPARATION,
        TYPED,
        "insert",
        _GADGET,
        CompletePayload(_once("L", 7, Decimal("1.00"), _ABSENT)),
        valid_from=None,
        until=None,
    )
    assert named_members(prepared.rows[0]) == {"label": "L", "id": 7, "price": Decimal("1.00")}


@pytest.mark.parametrize("family", ["keyed", "target"])
def test_a_typed_replacement_reads_a_one_shot_payload_once_past_a_later_key(family: str) -> None:
    payload = CompletePayload(_once("L", 7, Decimal("1.00"), 3))
    if family == "keyed":
        prepared = wi.prepare_keyed_write(
            _PREPARATION, TYPED, "replace", _GADGET, payload, valid_from=None, until=None
        )
        (row,) = prepared.rows
    else:
        row = wi.prepare_target_write(
            _PREPARATION,
            TYPED,
            "replace",
            _GADGET,
            payload,
            revision=_REVISION,
            valid_from=None,
            until=None,
        ).row
    assert named_members(row) == {"label": "L", "id": 7, "price": Decimal("1.00")}


@pytest.mark.parametrize("mutation", ["insert", "replace"])
def test_a_wire_complete_payload_names_an_owned_member_before_an_earlier_invalid_value(
    mutation: wi.KeyedMutation,
) -> None:
    payload = CompletePayload(("L", 7, "not-a-price", 3))
    prepare = wi.prepare_insert if mutation == "insert" else wi.prepare_keyed_write
    with raises_code(UsageError, "framework-owned-member-assigned", match=r"Gadget\.version"):
        prepare(_PREPARATION, WIRE, mutation, _GADGET, payload, valid_from=None, until=None)


def test_an_addressed_key_is_converted_once_and_placed_in_its_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    converted: list[int] = []
    scalar = AuthoringPlan._top_level_scalar  # pyright: ignore[reportPrivateUsage]

    def counted(plan: AuthoringPlan, base: int, position: int, raw: object) -> object:
        converted.append(position)
        return scalar(plan, base, position, raw)

    monkeypatch.setattr(AuthoringPlan, "_top_level_scalar", counted)
    prepared = wi.prepare_keyed_write(
        _PREPARATION,
        WIRE,
        "amend",
        _GADGET,
        PartialPayload(((2, "1.00"), (1, 7))),
        valid_from=None,
        until=None,
    )
    assert converted == [1, 2]
    assert named_members(prepared.rows[0]) == {"id": 7, "price": Decimal("1.00")}


@REPRESENTATIONS
def test_a_restated_key_naming_the_same_object_is_judged_and_set_aside(
    representation: WriteRepresentation,
) -> None:
    prepared = wi.prepare_keyed_write(
        _PREPARATION,
        representation,
        "amend",
        _GADGET,
        PartialPayload(((1, 7), (0, "M"))),
        restated_key=7,
        valid_from=None,
        until=None,
    )
    assert named_members(prepared.rows[0]) == {"id": 7, "label": "M"}


def test_a_restated_key_naming_another_object_is_refused_before_any_other_value() -> None:
    with raises_code(UsageError, "write-instruction-invalid", match=r"Gadget\.id: the document"):
        wi.prepare_keyed_write(
            _PREPARATION,
            WIRE,
            "amend",
            _GADGET,
            PartialPayload(((1, 7), (2, "not-a-price"))),
            restated_key=8,
            valid_from=None,
            until=None,
        )


def test_a_restated_key_that_is_no_key_is_refused_as_its_literal() -> None:
    with raises_code(UsageError, "neutral-literal-type-mismatch", match=r"Gadget\.id"):
        wi.prepare_keyed_write(
            _PREPARATION,
            WIRE,
            "amend",
            _GADGET,
            PartialPayload(((1, 7),)),
            restated_key="seven",
            valid_from=None,
            until=None,
        )


def test_an_unstated_restatement_restates_nothing() -> None:
    prepared = wi.prepare_keyed_write(
        _PREPARATION,
        WIRE,
        "delete",
        _GADGET,
        PartialPayload(((1, 7),)),
        restated_key=UNSTATED,
        valid_from=None,
        until=None,
    )
    assert named_members(prepared.rows[0]) == {"id": 7}


def test_a_keyed_destructive_payload_states_its_key_alone() -> None:
    with raises_code(UsageError, "write-instruction-invalid", match="primary key alone"):
        wi.prepare_keyed_write(
            _PREPARATION,
            WIRE,
            "delete",
            _GADGET,
            PartialPayload(((1, 7), (0, "L"))),
            valid_from=None,
            until=None,
        )


def test_a_wire_target_key_carrying_several_values_is_refused_as_its_literal() -> None:
    with raises_code(UsageError, "neutral-literal-type-mismatch", match=r"Gadget\.id"):
        wi.prepare_target_write(
            _PREPARATION,
            WIRE,
            "delete",
            _GADGET,
            PartialPayload(((1, {"id": 7}),)),
            revision=_REVISION,
            valid_from=None,
            until=None,
        )


_ALL: Final = predicate_algebra.TrueNode()


@REPRESENTATIONS
def test_a_predicate_replacement_may_omit_its_key(representation: WriteRepresentation) -> None:
    prepared = wi.prepare_predicate_write(
        _PREPARATION,
        representation,
        "replace",
        _PLAIN,
        _ALL,
        CompletePayload(("L", _ABSENT)),
    )
    assert named_members(prepared.row) == {"label": "L"}


def test_a_predicate_replacement_judges_and_drops_a_stated_key() -> None:
    with raises_code(UsageError, "neutral-literal-type-mismatch", match=r"Plain\.id"):
        wi.prepare_predicate_write(
            _PREPARATION, WIRE, "replace", _PLAIN, _ALL, CompletePayload(("L", "seven"))
        )
    prepared = wi.prepare_predicate_write(
        _PREPARATION, WIRE, "replace", _PLAIN, _ALL, CompletePayload(("L", 7))
    )
    assert named_members(prepared.row) == {"label": "L"}


def test_a_predicate_amendment_stating_the_key_is_refused() -> None:
    with raises_code(
        UsageError, "write-instruction-invalid", match="primary-key fields may not be assigned"
    ):
        wi.prepare_predicate_write(
            _PREPARATION, WIRE, "amend", _PLAIN, _ALL, PartialPayload(((0, "L"), (1, 7)))
        )


@pytest.mark.parametrize(
    ("mutation", "payload"),
    [
        ("replace", PartialPayload(((1, 7),))),
        ("amend", CompletePayload(("L", 7, "1.00", _ABSENT))),
    ],
)
def test_a_payload_of_the_wrong_shape_for_its_verb_is_a_programming_error(
    mutation: wi.KeyedMutation, payload: CompletePayload | PartialPayload
) -> None:
    with pytest.raises(ValueError, match="payload is not"):
        wi.prepare_keyed_write(
            _PREPARATION, WIRE, mutation, _GADGET, payload, valid_from=None, until=None
        )


def test_assignments_join_no_complete_payload() -> None:
    with pytest.raises(ValueError, match="payload is not"):
        wi.prepare_keyed_write(
            _PREPARATION,
            TYPED,
            "replace",
            _GADGET,
            CompletePayload(("L", 7, Decimal("1.00"), _ABSENT)),
            assignments=(wi.WriteAssignment(f"{_NS}.Gadget.label", "M"),),
            valid_from=None,
            until=None,
        )
