"""One model's write preparation: every Entity's row selection, lane plans,
and member masks derived once, at construction."""

from __future__ import annotations

from typing import Final

from parallax.core import inheritance
from parallax.core._execution._planning import prepare_model
from parallax.core._execution._publication import write_projection
from parallax.core._execution._unit_work.preparation import WritePreparation
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
    assert prepared.plan.shape is view.member_selection.shape
    assert preparation.entity(branch.identity) is prepared


def test_a_prepared_model_prepares_writes_against_its_own_model() -> None:
    selection = prepare_model(ACCOUNT_MODEL, edition="test")
    write = write_projection(selection)

    assert write.preparation.meta is write.model.meta
