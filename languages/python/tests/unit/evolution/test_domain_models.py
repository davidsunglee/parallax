"""The public ``evolve``: Domain Models in, the accepted-model evolution out.

Each case reaches the evolution through the application door and compares it
with what the first-party ``evolve_metamodels`` answers over the same accepted
models, so the wrapper is graded on what it adds — the argument check, the
narrowing, and the endpoints it hands through — rather than on evolution
semantics its owner's suite already grades.
"""

from __future__ import annotations

from typing import Any, assert_type

import pytest

from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.entity import model_of
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import (
    ABSENT,
    CoordinatedEvolution,
    Evolution,
    UnilateralEvolution,
    evolve,
)
from parallax.evolution.model_evolution import EntityAdded, EntityRemoved, evolve_metamodels


class Widget(Entity, table="widget", namespace="shop"):
    id: Attr[int] = attr(primary_key=True)


class Gadget(Entity, table="gadget", namespace="shop"):
    id: Attr[int] = attr(primary_key=True)


_WIDGETS = DomainModel(Widget)
_BOTH = DomainModel(Widget, Gadget)


def test_provisioning_narrows_to_a_unilateral_evolution_of_the_accepted_model() -> None:
    evolution = evolve(ABSENT, _BOTH)
    assert_type(evolution, UnilateralEvolution)
    assert evolution == evolve_metamodels(ABSENT, model_of(_BOTH))
    assert evolution.earlier is None
    assert evolution.later is model_of(_BOTH)


def test_identical_endpoints_evolve_to_an_empty_unilateral_evolution() -> None:
    evolution = evolve(_WIDGETS, _WIDGETS)
    assert_type(evolution, Evolution)
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == ()
    assert evolution.earlier is evolution.later is model_of(_WIDGETS)


def test_a_coordinated_change_keeps_both_exact_accepted_endpoints() -> None:
    evolution = evolve(_BOTH, _WIDGETS)
    assert isinstance(evolution, CoordinatedEvolution)
    assert [type(operation) for operation in evolution.operations] == [EntityRemoved]
    assert evolution.earlier is model_of(_BOTH)
    assert evolution.later is model_of(_WIDGETS)


def test_class_and_descriptor_backed_models_evolve_alike() -> None:
    deployed = domain_model_from_yaml(export_yaml(_WIDGETS))
    assert evolve(deployed, _WIDGETS).operations == ()
    assert evolve(_WIDGETS, domain_model_from_yaml(export_yaml(_WIDGETS))).operations == ()
    mixed = evolve(deployed, _BOTH)
    assert [type(operation) for operation in mixed.operations] == [EntityAdded]
    assert mixed.earlier is model_of(deployed)


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        pytest.param(model_of(_WIDGETS), _WIDGETS, id="earlier-accepted-model"),
        pytest.param(_WIDGETS, model_of(_WIDGETS), id="later-accepted-model"),
        pytest.param(ABSENT, ABSENT, id="later-absent"),
    ],
)
def test_an_argument_that_is_no_domain_model_is_refused(earlier: Any, later: Any) -> None:
    with pytest.raises(TypeError, match="takes a Domain Model"):
        evolve(earlier, later)
