"""The public ``evolve``: Domain Models in, the accepted-model evolution out.

Each case reaches the evolution through the application door and compares it
with what the first-party ``evolve_metamodels`` answers over the same accepted
models, so the wrapper is graded on what it adds — the argument check, the
narrowing, and the endpoints it hands through — rather than on evolution
semantics its owner's suite already grades.
"""

from __future__ import annotations

import dataclasses
from typing import Any, assert_type

import pytest

from parallax.core import Attr, DomainModel, Entity, attr, index
from parallax.core.internal.base import UsageError
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity import model_of
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import (
    ABSENT,
    CoordinatedEvolution,
    Evolution,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.evolution.internal.model_evolution import (
    EntityAdded,
    EntityRemoved,
    evolve_resolved,
)
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresTable
from tests._support.bindings import TEST_BINDING, binding_for, bound_model


class Widget(Entity, table="widget", namespace="shop"):
    id: Attr[int] = attr(primary_key=True)


class Gadget(Entity, table="gadget", namespace="shop"):
    id: Attr[int] = attr(primary_key=True)


_WIDGETS = DomainModel(Widget)
_BOTH = DomainModel(Widget, Gadget)


def test_provisioning_narrows_to_a_unilateral_evolution_of_the_accepted_model() -> None:
    evolution = evolve(ABSENT, _BOTH, later_binding=TEST_BINDING)
    assert_type(evolution, UnilateralEvolution)
    assert evolution == evolve_resolved(ABSENT, bound_model(model_of(_BOTH)))
    assert evolution.earlier is None
    assert evolution.later.meta is model_of(_BOTH)


def test_identical_endpoints_evolve_to_an_empty_unilateral_evolution() -> None:
    evolution = evolve(_WIDGETS, _WIDGETS, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING)
    assert_type(evolution, Evolution)
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == ()
    assert evolution.earlier is not None
    assert evolution.earlier.meta is evolution.later.meta is model_of(_WIDGETS)


def test_a_coordinated_change_keeps_both_exact_accepted_endpoints() -> None:
    evolution = evolve(_BOTH, _WIDGETS, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING)
    assert isinstance(evolution, CoordinatedEvolution)
    assert [type(operation) for operation in evolution.operations] == [EntityRemoved]
    assert evolution.earlier.meta is model_of(_BOTH)
    assert evolution.later.meta is model_of(_WIDGETS)


def test_class_and_descriptor_backed_models_evolve_alike() -> None:
    deployed = domain_model_from_yaml(export_yaml(_WIDGETS))
    assert (
        evolve(
            deployed, _WIDGETS, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING
        ).operations
        == ()
    )
    assert (
        evolve(
            _WIDGETS,
            domain_model_from_yaml(export_yaml(_WIDGETS)),
            earlier_binding=TEST_BINDING,
            later_binding=TEST_BINDING,
        ).operations
        == ()
    )
    mixed = evolve(deployed, _BOTH, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING)
    assert [type(operation) for operation in mixed.operations] == [EntityAdded]
    assert mixed.earlier is not None
    assert mixed.earlier.meta is model_of(deployed)


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
        evolve(earlier, later, earlier_binding=TEST_BINDING, later_binding=TEST_BINDING)


def test_endpoints_bound_for_different_backends_are_refused_before_comparison() -> None:
    other_backend = binding_for(dataclasses.replace(POSTGRES, name="mariadb"))
    with pytest.raises(UsageError) as refused:
        evolve(_WIDGETS, _WIDGETS, earlier_binding=TEST_BINDING, later_binding=other_backend)
    assert refused.value.code == "evolution-backend-mismatch"


class Labelled(Entity, table="labelled", namespace="shop", indices=(index("by_label", "label"),)):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


def _index_names(binding: PostgresBinding) -> tuple[str, ...]:
    delta = schema_delta(evolve(ABSENT, DomainModel(Labelled), later_binding=binding))
    return tuple(created.physical_index_name.value for created in delta.created_indices)


def test_authored_index_names_follow_the_resolved_local_name_alone() -> None:
    declared = _index_names(TEST_BINDING)
    moved = _index_names(PostgresBinding(default=PostgresLocation(schema="elsewhere")))
    renamed = _index_names(
        PostgresBinding(
            default=PostgresLocation(schema="px"),
            entities={"shop.Labelled": PostgresTable(name="tagged")},
        )
    )
    assert moved == declared
    assert renamed != declared
    assert all(name.startswith("pxi_labelled_") for name in declared)
    assert all(name.startswith("pxi_tagged_") for name in renamed)
