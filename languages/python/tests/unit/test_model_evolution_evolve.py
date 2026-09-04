"""`evolve` over the two evolutions that need no matching logic.

Provisioning from `ABSENT` and the evolution between equal models are the two
ends of the description: one where every Entity is an addition and nothing
survives, one where everything survives and nothing changed. Both run through
the same pipeline, so proving them here proves the pipeline is total rather than
proving two special cases.

The retention proof belongs beside them because it is about the pipeline too:
the identity-paired view every stage reads is transient, and an Evolution that
kept it alive would hold a structure proportional to the model for as long as a
caller holds the result.
"""

from __future__ import annotations

import gc
from collections.abc import Callable, Iterator

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.metamodel import (
    AbstractRoot,
    Column,
    ConcreteSubtype,
    Document,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Metamodel,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
)
from parallax.evolution.model_evolution import (
    ABSENT,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    EntityAdded,
    EntityRemoved,
    UnilateralEvolution,
    evolve,
)
from parallax.evolution.model_evolution._matching import Matching

_WIDGET = identity("Widget")
_GADGET = identity("Gadget")
_ROOT = identity("Instrument")
_LEAF = identity("Bond")
_EQUITY = identity("Equity")


def _widget() -> Metamodel:
    """A one-Entity Columns model with an authored secondary Index."""
    label = attribute(_WIDGET, "label", type=STRING)
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=Table("widget"),
                attributes=(key(_WIDGET), label),
                indices=(
                    IndexMetadata(
                        identity=IndexIdentity(_WIDGET, "widget_label"),
                        attributes=(label.identity,),
                    ),
                ),
            )
        )
    )


def _two_entities() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(identity=_GADGET, container=Table("gadget"), attributes=(key(_GADGET),)),
            Declaration(identity=_WIDGET, container=Table("widget"), attributes=(key(_WIDGET),)),
        )
    )


def _document_layout() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_WIDGET,
                container=Table("widget"),
                layout=Document(Column("doc")),
                attributes=(key(_WIDGET), attribute(_WIDGET, "label", type=STRING)),
            )
        )
    )


def _hierarchy() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                container=Table("instrument"),
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=_LEAF,
                attributes=(attribute(_LEAF, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "BOND"),
            ),
        )
    )


def test_provisioning_is_one_entity_level_addition_per_entity() -> None:
    evolution = evolve(ABSENT, _two_entities())
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == (EntityAdded(_GADGET), EntityAdded(_WIDGET))


def test_provisioning_suppresses_every_member_of_the_entity_it_adds() -> None:
    # `Widget` declares a key, an Attribute, and an authored Index, and the one
    # parent addition describes all three.
    assert evolve(ABSENT, _widget()).operations == (EntityAdded(_WIDGET),)


def test_provisioning_names_a_concrete_subtype_by_its_own_kind() -> None:
    # The generic Entity addition excludes concrete-subtype addition, so a family
    # provisions as one operation per participant in its own role's vocabulary.
    assert evolve(ABSENT, _hierarchy()).operations == (
        ConcreteSubtypeAdded(_LEAF),
        EntityAdded(_ROOT),
    )


def test_provisioning_retains_no_earlier_endpoint_and_no_continuity_payload() -> None:
    later = _widget()
    evolution = evolve(ABSENT, later)
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.earlier is None
    assert evolution.later is later
    assert evolution.behavioral_impacts == ()
    assert evolution.overlap_visible_operations == ()


@pytest.mark.parametrize(
    ("layout", "build"),
    [("columns", _widget), ("document", _document_layout), ("hierarchy", _hierarchy)],
)
def test_equal_models_evolve_to_an_empty_unilateral_evolution(
    layout: str, build: Callable[[], Metamodel]
) -> None:
    model = build()
    evolution = evolve(model, model)
    assert isinstance(evolution, UnilateralEvolution), layout
    assert evolution.operations == ()
    assert evolution.behavioral_impacts == ()
    assert evolution.overlap_visible_operations == ()


def test_an_evolution_between_equal_models_still_retains_both_endpoints() -> None:
    # `evolve` is total: equal models are an EMPTY evolution rather than a third
    # no-evolution result or a nullable return, and the endpoints stay reachable
    # so a consumer resolves identities the same way on every result.
    earlier = _widget()
    later = _widget()
    evolution = evolve(earlier, later)
    assert evolution.earlier is earlier
    assert evolution.later is later


def _tpcs_hierarchy() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=_LEAF,
                container=Table("bond"),
                attributes=(attribute(_LEAF, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT)),
            ),
        )
    )


def _tpcs_with_a_second_subtype() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=_LEAF,
                container=Table("bond"),
                attributes=(attribute(_LEAF, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT)),
            ),
            Declaration(
                identity=_EQUITY,
                container=Table("equity"),
                attributes=(attribute(_EQUITY, "ticker", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT)),
            ),
        )
    )


def _tph_with_a_second_subtype() -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                container=Table("instrument"),
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=_LEAF,
                attributes=(attribute(_LEAF, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "BOND"),
            ),
            Declaration(
                identity=_EQUITY,
                attributes=(attribute(_EQUITY, "ticker", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "EQUITY"),
            ),
        )
    )


def test_a_table_per_hierarchy_subtype_addition_is_unilateral_and_overlap_visible() -> None:
    # A later writer can place a new discriminator value in the SHARED Table that
    # an earlier reader cannot admit.
    evolution = evolve(_hierarchy(), _tph_with_a_second_subtype())
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == (ConcreteSubtypeAdded(_EQUITY),)
    assert evolution.overlap_visible_operations == (ConcreteSubtypeAdded(_EQUITY),)


def test_a_table_per_concrete_subtype_addition_is_unilateral_and_not_overlap_visible() -> None:
    # The later subtype occupies a separate Table the earlier edition never reads.
    evolution = evolve(_tpcs_hierarchy(), _tpcs_with_a_second_subtype())
    assert isinstance(evolution, UnilateralEvolution)
    assert evolution.operations == (ConcreteSubtypeAdded(_EQUITY),)
    assert evolution.overlap_visible_operations == ()


def test_removing_an_entity_makes_the_whole_evolution_coordinated() -> None:
    # Removing a model-facing declaration invalidates a previously valid authored
    # operation, so the evolution carries one requirement for that operation —
    # and the addition beside it stays uncoordinated, with no requirement of its
    # own, because coordination is per operation rather than per evolution.
    evolution = evolve(_widget(), _hierarchy())
    assert isinstance(evolution, CoordinatedEvolution)
    assert evolution.operations == (
        ConcreteSubtypeAdded(_LEAF),
        EntityAdded(_ROOT),
        EntityRemoved(_WIDGET),
    )
    assert evolution.coordination_requirements == (
        CoordinationRequirement(
            EntityRemoved(_WIDGET),
            (CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,),
        ),
    )


def test_removing_a_concrete_subtype_names_its_own_kind() -> None:
    evolution = evolve(_tph_with_a_second_subtype(), _hierarchy())
    assert isinstance(evolution, CoordinatedEvolution)
    assert evolution.operations == (ConcreteSubtypeRemoved(_EQUITY),)


def _reachable(root: object) -> Iterator[object]:
    """Every object reachable from ``root`` through the collector's own view."""
    seen = {id(root)}
    pending = [root]
    while pending:
        current = pending.pop()
        yield current
        for referent in gc.get_referents(current):
            if id(referent) not in seen:
                seen.add(id(referent))
                pending.append(referent)


def test_an_evolution_retains_its_endpoints_and_not_the_matching() -> None:
    # The identity-paired view is a transient seam proportional to the model. An
    # Evolution retains its two endpoints, its operations, and its impacts — a
    # held result that could still reach the Matching would keep a second copy of
    # the model's structure alive for as long as the caller holds it.
    earlier = _widget()
    evolution = evolve(earlier, _widget())
    held = list(_reachable(evolution))
    assert any(item is earlier for item in held), "the endpoints are retained by design"
    assert not any(isinstance(item, Matching) for item in held)
