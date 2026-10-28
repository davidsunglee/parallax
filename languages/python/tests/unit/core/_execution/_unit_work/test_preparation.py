"""One model's write preparation: every Entity's row selection, lane plans,
and member masks derived once, at construction."""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core import inheritance
from parallax.core._execution._planning import build_write_planner, prepare_model
from parallax.core._execution._publication import write_projection
from parallax.core._execution._unit_work.preparation import WritePreparation
from parallax.core.entity._model import model_of
from tests._support.mirrored_models import ACCOUNT_MODEL
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ABSENT: Final = object()
_BRANCH = corpus_model("branch")


def test_every_entity_is_prepared_once_over_its_member_selection() -> None:
    preparation = WritePreparation(_BRANCH, absent=_ABSENT)
    branch = entity_of(_BRANCH, "Branch")
    prepared = preparation.entity(branch.identity)
    view = inheritance.view(_BRANCH).entity(branch.identity)
    assert view is not None

    assert prepared.selection.members is view.member_selection
    assert prepared.selection.absent is _ABSENT
    assert prepared.typed.shape is view.member_selection.shape
    assert prepared.wire.shape is view.member_selection.shape
    assert preparation.entity(branch.identity) is prepared


def test_member_masks_name_required_and_framework_owned_positions() -> None:
    branch = entity_of(_BRANCH, "Branch")
    prepared = WritePreparation(_BRANCH, absent=_ABSENT).entity(branch.identity)
    names = [member.name for member in prepared.selection.members.shape.members]

    required = {name for p, name in enumerate(names) if prepared.insert_required >> p & 1}
    owned = {name for p, name in enumerate(names) if prepared.framework_owned >> p & 1}

    assert required == {"id", "name"}
    assert len(owned) == 4
    assert not prepared.insert_required & prepared.framework_owned


def test_a_prepared_model_prepares_writes_against_its_own_model() -> None:
    selection = prepare_model(ACCOUNT_MODEL, edition="test")
    write = write_projection(selection)

    assert write.preparation.meta is write.model.meta


def test_a_planner_refuses_another_models_preparation() -> None:
    other = WritePreparation(model_of(ACCOUNT_MODEL), absent=_ABSENT)

    with pytest.raises(ValueError, match="its own model's preparation"):
        build_write_planner(_BRANCH, preparation=other)
