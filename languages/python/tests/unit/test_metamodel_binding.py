"""The Metamodel Binding: permanence, the bidirectional index, and the claim race.

The claim is the only synchronization primitive in the hub, so the race here is
not optional: it is the direct proof that overlapping constructions have exactly
one winner and that the loser publishes nothing.
"""

from __future__ import annotations

import threading

import pytest

from parallax.core import Attr, Entity, MetamodelHub, MetamodelStateError, attr
from parallax.core.entity import METAMODEL_STATE_CODES
from parallax.core.entity._binding import MetamodelBinding, binding_of
from parallax.core.metamodel import EntityIdentity

pytestmark = pytest.mark.unit

_SPEC_CODES = frozenset({"metamodel-class-not-bound", "metamodel-class-already-bound"})


def test_a_sealed_hub_binds_every_class_to_one_binding() -> None:
    class Alpha(Entity, table="alpha", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    class Beta(Entity, table="beta", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    models = MetamodelHub(Alpha, Beta)
    binding = binding_of(Alpha)
    assert binding is not None
    assert binding_of(Beta) is binding
    # The binding references the hub's one accepted Metamodel; it copies nothing.
    assert binding.model.entity(EntityIdentity("bind", "Alpha")) is models.meta(Alpha)


def test_the_index_is_bidirectional_and_local_to_its_own_hub() -> None:
    class Gamma(Entity, table="gamma", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    class Delta(Entity, table="delta", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    MetamodelHub(Gamma)
    MetamodelHub(Delta)
    gamma = binding_of(Gamma)
    assert gamma is not None
    assert gamma.identity_of(Gamma) == EntityIdentity("bind", "Gamma")
    assert gamma.class_of(EntityIdentity("bind", "Gamma")) is Gamma
    assert gamma.identity_of(Delta) is None
    assert gamma.class_of(EntityIdentity("bind", "Delta")) is None


def test_hub_identity_is_a_private_sentinel_unique_per_hub() -> None:
    class Epsilon(Entity, table="epsilon", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    class Zeta(Entity, table="zeta", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    MetamodelHub(Epsilon)
    MetamodelHub(Zeta)
    first, second = binding_of(Epsilon), binding_of(Zeta)
    assert first is not None and second is not None
    assert first.hub_identity is first.hub_identity
    assert first.hub_identity is not second.hub_identity


def test_a_claim_is_permanent_for_the_class_objects_lifetime() -> None:
    class Eta(Entity, table="eta", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    MetamodelHub(Eta)
    binding = binding_of(Eta)
    with pytest.raises(MetamodelStateError) as caught:
        MetamodelHub(Eta)
    assert caught.value.code == "metamodel-class-already-bound"
    assert binding_of(Eta) is binding


def test_a_second_hub_over_a_shared_class_reports_every_conflict_in_canonical_order() -> None:
    class Theta(Entity, table="theta", namespace="zz"):
        id: Attr[int] = attr(primary_key=True)

    class Iota(Entity, table="iota", namespace="aa"):
        id: Attr[int] = attr(primary_key=True)

    class Kappa(Entity, table="kappa", namespace="mm"):
        id: Attr[int] = attr(primary_key=True)

    MetamodelHub(Theta, Iota, Kappa)
    with pytest.raises(MetamodelStateError) as caught:
        MetamodelHub(Theta, Kappa, Iota)
    assert caught.value.code == "metamodel-class-already-bound"
    assert [identity.canonical for identity in caught.value.entities] == [
        "aa.Iota",
        "mm.Kappa",
        "zz.Theta",
    ]


def test_the_state_code_set_is_closed() -> None:
    assert METAMODEL_STATE_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not a metamodel state code"):
        MetamodelStateError(code="metamodel-unsealed", message="no such state")


def test_an_unclaimed_class_has_no_binding() -> None:
    class Lambda_(Entity, table="lambda", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    assert binding_of(Lambda_) is None
    assert binding_of(int) is None


def test_racing_constructions_over_one_class_have_exactly_one_winner() -> None:
    class Shared(Entity, table="shared", namespace="race"):
        id: Attr[int] = attr(primary_key=True)

    racers = 8
    start = threading.Barrier(racers)
    outcomes: list[MetamodelHub | MetamodelStateError] = []
    guard = threading.Lock()

    def construct() -> None:
        start.wait()
        try:
            result: MetamodelHub | MetamodelStateError = MetamodelHub(Shared)
        except MetamodelStateError as error:
            result = error
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=construct) for _ in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [outcome for outcome in outcomes if isinstance(outcome, MetamodelHub)]
    losers = [outcome for outcome in outcomes if isinstance(outcome, MetamodelStateError)]
    assert len(winners) == 1
    assert len(losers) == racers - 1
    assert {loser.code for loser in losers} == {"metamodel-class-already-bound"}
    assert {tuple(identity.canonical for identity in loser.entities) for loser in losers} == {
        ("race.Shared",)
    }
    binding = binding_of(Shared)
    assert binding is not None
    assert binding.class_of(EntityIdentity("race", "Shared")) is Shared
    assert binding.model.entity(EntityIdentity("race", "Shared")) is winners[0].meta(Shared)


def test_a_binding_publishes_exactly_the_claims_it_indexes() -> None:
    class Mu(Entity, table="mu", namespace="bind"):
        id: Attr[int] = attr(primary_key=True)

    MetamodelHub(Mu)
    binding = binding_of(Mu)
    assert binding is not None
    assert isinstance(binding, MetamodelBinding)
    assert [(cls, identity.canonical) for cls, identity in binding.claims] == [(Mu, "bind.Mu")]
