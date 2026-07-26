"""The Metamodel Binding: permanence, the bidirectional index, and the claim race.

The claim is the only synchronization primitive in the hub, so the race here is
not optional: it is the direct proof that overlapping constructions have exactly
one winner, that the loser publishes nothing, and that the winner has nothing
half-built to observe the instant its claim becomes visible.
"""

from __future__ import annotations

import threading
from typing import Final

import pytest

from parallax.core import Attr, Entity, MetamodelHub, MetamodelStateError, attr
from parallax.core.entity import METAMODEL_STATE_CODES
from parallax.core.entity._binding import MetamodelBinding, binding_of, claim
from parallax.core.metamodel import EntityIdentity

pytestmark = pytest.mark.unit

_SPEC_CODES = frozenset({"metamodel-class-not-bound", "metamodel-class-already-bound"})
_HANDOFF_TIMEOUT: Final = 10.0


def _claimed_hub_state(binding: MetamodelBinding) -> str:
    """What the hub behind a freshly published claim can say about itself.

    The claim is the moment a construction becomes reachable from outside the
    thread running it, and the owner reference the Binding retains for lifetime
    is the only route from there back to the hub — so it is the one place an
    unfinished hub could be observed.
    """
    owner = binding._owner  # pyright: ignore[reportPrivateUsage]
    if not isinstance(owner, MetamodelHub):
        return f"not a hub: {owner!r}"
    try:
        return ", ".join(entity.identity.canonical for entity in owner.entities)
    except AttributeError as error:
        return f"unpublished hub: {error}"


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


def test_racing_constructions_over_one_class_have_exactly_one_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Shared(Entity, table="shared", namespace="race"):
        id: Attr[int] = attr(primary_key=True)

    racers = 8
    start = threading.Barrier(racers)
    claimed = threading.Event()
    inspected = threading.Event()
    outcomes: list[MetamodelHub | MetamodelStateError] = []
    observed: list[str] = []
    guard = threading.Lock()

    def held_open_after_claiming(binding: MetamodelBinding) -> None:
        """Freeze the winner where its claim is published but its own
        construction has not returned, so the observer thread looks at exactly
        the interleaving a natural race would only occasionally reach."""
        claim(binding)
        claimed.set()
        inspected.wait(timeout=_HANDOFF_TIMEOUT)

    monkeypatch.setattr("parallax.core.entity._hub.claim", held_open_after_claiming)

    def observe() -> None:
        try:
            if not claimed.wait(timeout=_HANDOFF_TIMEOUT):
                observed.append("no claim became visible")
                return
            binding = binding_of(Shared)
            observed.append("no binding" if binding is None else _claimed_hub_state(binding))
        finally:
            inspected.set()

    def construct() -> None:
        start.wait()
        try:
            result: MetamodelHub | MetamodelStateError = MetamodelHub(Shared)
        except MetamodelStateError as error:
            result = error
        with guard:
            outcomes.append(result)

    observer = threading.Thread(target=observe)
    threads = [threading.Thread(target=construct) for _ in range(racers)]
    observer.start()
    for thread in threads:
        thread.start()
    for thread in [*threads, observer]:
        thread.join(timeout=_HANDOFF_TIMEOUT)
        assert not thread.is_alive()

    # A claimed class always names a hub that already answers for it: the claim
    # publishes a complete construction or nothing at all.
    assert observed == ["race.Shared"]
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
