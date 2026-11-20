"""One model's write preparation: every Entity's row selection and lane plan
derived once, at construction, and the payloads a name mapping states."""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core._execution._planning import prepare_model
from parallax.core._execution._publication import write_projection
from parallax.core._execution._unit_work.preparation import (
    CompletePayload,
    EntityPreparation,
    PartialPayload,
    WritePreparation,
)
from parallax.core.internal import inheritance
from parallax.core.internal.base import UsageError
from tests._support.bindings import TEST_BINDING
from tests._support.errors import raises_code
from tests._support.mirrored_models import ACCOUNT_MODEL
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ABSENT: Final = object()
_BRANCH = corpus_model("branch")


def test_every_entity_is_prepared_once_over_its_member_selection() -> None:
    preparation = WritePreparation(_BRANCH, absent=_ABSENT)
    branch = entity_of(_BRANCH, "Branch")
    prepared = preparation.entity(branch.identity)
    view = inheritance.inheritance_facet_of(_BRANCH).entity(branch.identity)
    assert view is not None

    assert prepared.selection.members is view.member_selection
    assert prepared.selection.absent is _ABSENT
    assert prepared.plan.shape is view.member_selection.shape
    assert preparation.entity(branch.identity) is prepared


def test_a_prepared_model_prepares_writes_against_its_own_model() -> None:
    selection = prepare_model(ACCOUNT_MODEL, edition="test", binding=TEST_BINDING)
    write = write_projection(selection)

    assert write.preparation.meta is write.model.meta


_ACCOUNT = corpus_model("account")


def _account() -> EntityPreparation:
    return WritePreparation(_ACCOUNT, absent=_ABSENT).entity(
        entity_of(_ACCOUNT, "Account").identity
    )


def test_a_complete_payload_states_each_named_member_at_its_position_converting_nothing() -> None:
    payload = _account().complete_payload_from_names({"owner": "Ada", "id": "7", "nickname": 1})

    assert payload == CompletePayload(("7", "Ada", _ABSENT, _ABSENT), ("nickname",))


def test_a_partial_payload_states_each_named_member_in_the_order_named() -> None:
    payload = _account().partial_payload_from_names({"balance": "9.00", "id": 7, "nickname": 1})

    assert payload == PartialPayload(((2, "9.00"), (0, 7)), ("nickname",))


def test_a_stated_key_stands_for_any_key_the_names_state() -> None:
    prepared = _account()
    members = {"id": 9, "balance": "9.00"}

    assert prepared.complete_payload_from_names(members, key=7).values == (
        7,
        _ABSENT,
        "9.00",
        _ABSENT,
    )
    assert prepared.partial_payload_from_names(members, key=7).stated == ((0, 7), (2, "9.00"))
    assert prepared.partial_payload_from_names(members, key=None).stated == (
        (0, None),
        (2, "9.00"),
    )
    assert prepared.key_name == "id"


@pytest.mark.parametrize("control", ["observedVersion", "observedTxStart", "observedValidStart"])
@pytest.mark.parametrize("shape", ["complete", "partial"])
def test_a_payload_naming_an_observation_control_is_refused(control: str, shape: str) -> None:
    prepared = _account()
    build = (
        prepared.complete_payload_from_names
        if shape == "complete"
        else prepared.partial_payload_from_names
    )
    with raises_code(UsageError, "write-instruction-invalid", match=control):
        build({"id": 7, control: 1})
