"""A scenario `mutate` step's `set` is an authored assignment the model must admit.

`m-case-format` makes an assignment no member of the edited Entity admits a
**case-authoring failure**: the closed per-step `expectError` vocabulary has no
member for an edit refusal, so a case cannot declare one, and an executor that
reached the refusal would have nothing portable to report — one executor would
fail the case while another, modelling `mutate` as authored golden DML alone,
passed it. The corpus therefore refuses such a case statically, before either
executor runs it, exactly as it refuses a bare write row naming an undeclared
member.

These DB-free probes pin the judgement over real corpus models: an assignment
naming a declared, assignable member with a value that member admits is ACCEPTED,
and each of the five ways one can fail — an undeclared or relationship name, a
protected target, an ill-typed value, a null where the member is not nullable, and
a malformed Value Object document — is REJECTED. Two structural halves ride along:
which Entities the set is judged against (a polymorphic read leaves the node's own
Entity open, so every concrete its RESULT position can answer must admit the whole
set, and a chained edit inherits the find's position), and where the check stops (a
step whose `on` names no read at all).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import load_model
from reference_harness.inheritance import Family
from reference_harness.schema_validate import _validate_scenario_edit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_ANIMAL = "parallax.compatibility.Animal"
_CAT = "parallax.compatibility.Cat"
_CUSTOMER = "parallax.compatibility.Customer"
_DOG = "parallax.compatibility.Dog"
_ORDER = "parallax.compatibility.Order"
_PET = "parallax.compatibility.Pet"


def _defs(model_rel: str) -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, model_rel).entity_defs


def _judged(model_rel: str, steps: list[Any], index: int) -> list[str]:
    entity_defs = _defs(model_rel)
    errors: list[str] = []
    _validate_scenario_edit(steps, index, entity_defs, Family(entity_defs), "probe", errors)
    return errors


def _edit(model_rel: str, target: str, assignments: dict[str, Any]) -> list[str]:
    """One find + one `mutate` naming it, the shape every edit-bearing case opens with."""
    return _narrowed_edit(model_rel, target, None, assignments)


def _narrowed_edit(
    model_rel: str, target: str, narrow_to: list[str] | None, assignments: dict[str, Any]
) -> list[str]:
    query: dict[str, Any] = {"target": target}
    if narrow_to is not None:
        query["narrowTo"] = narrow_to
    steps: list[Any] = [
        {"objectQuery": query},
        {"action": "mutate", "on": 0, "set": assignments},
    ]
    return _judged(model_rel, steps, 1)


@pytest.mark.parametrize(
    ("model_rel", "target", "assignments"),
    [
        ("models/orders.yaml", _ORDER, {"name": "Mutant"}),
        ("models/orders.yaml", _ORDER, {"price": 10.50, "qty": 5}),
        ("models/orders.yaml", _ORDER, {"sku": None}),
        (
            "models/customer.yaml",
            _CUSTOMER,
            {"address": {"street": "Main", "city": "Oslo", "phones": []}},
        ),
        ("models/animal.yaml", _DOG, {"barkVolume": 9}),
    ],
)
def test_an_assignment_the_model_admits_is_accepted(
    model_rel: str, target: str, assignments: dict[str, Any]
) -> None:
    assert _edit(model_rel, target, assignments) == []


@pytest.mark.parametrize(
    ("assignments", "detail"),
    [
        ({"nickname": "Nick"}, "Order.nickname: names no assignable attribute or value object"),
        ({"items": []}, "Order.items: names no assignable attribute or value object"),
        ({"id": 2}, "Order.id: primary-key fields may not be assigned"),
        ({"qty": "five"}, "Order.qty: value 'five' does not match the declared type 'int32'"),
        ({"name": None}, "Order.name: required attribute (nullable:false) is absent or null"),
    ],
)
def test_an_assignment_the_model_refuses_is_rejected(
    assignments: dict[str, Any], detail: str
) -> None:
    assert _edit("models/orders.yaml", _ORDER, assignments) == [f"probe: `mutate` set {detail}"]


def test_a_framework_owned_target_is_rejected() -> None:
    # An As-Of Axis endpoint is the framework's to supply, so no edit authors one —
    # the same exemption the write row walk makes, asked as a refusal because a set
    # names its member deliberately.
    assert _edit("models/balance.yaml", "parallax.compatibility.Balance", {"txEnd": None}) == [
        "probe: `mutate` set Balance.txEnd: framework-owned fields may not be assigned"
    ]
    assert _edit("models/account.yaml", "parallax.compatibility.Account", {"version": 2}) == [
        "probe: `mutate` set Account.version: framework-owned fields may not be assigned"
    ]


@pytest.mark.parametrize(
    ("value", "detail"),
    [
        ("Oslo", "Customer.address: expected a value-object document, got str"),
        (
            {"city": "Oslo", "phones": []},
            "Customer.address.street: required attribute (nullable:false) is absent or null",
        ),
    ],
)
def test_a_value_object_assignment_binds_a_whole_document(value: Any, detail: str) -> None:
    # An occurrence binds atomically (m-value-object), so a scalar standing where a
    # document is declared is a type mismatch and a document missing a required leaf
    # is incomplete — neither is a partial assignment the walk could accept.
    assert _edit("models/customer.yaml", _CUSTOMER, {"address": value}) == [
        f"probe: `mutate` set {detail}"
    ]


def test_an_inherited_member_is_assignable_on_every_concrete_the_read_answers() -> None:
    # `name` is the abstract root's own, so whichever concrete the read hands the
    # executor admits it — the one shape a broad polymorphic read may edit.
    assert _edit("models/animal.yaml", _ANIMAL, {"name": "Mutant"}) == []


def test_one_concretes_own_member_needs_a_read_narrowed_to_it() -> None:
    # An abstract-target read materializes complete concrete instances but does not
    # say WHICH, so a set only Dog admits describes a node the read may never
    # produce — the executor holding a Cat would refuse the case this gate passed.
    # `narrowTo` is how a case says which concrete its edit means, and it is judged
    # against that concrete alone.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": 9}) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value "
        "object — the read answers any of (Cat, Dog, WildBoar), so narrow it to the "
        "concrete this edit means"
    ]
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_DOG], {"barkVolume": 9}) == []


def test_a_narrowed_read_refuses_a_sibling_branchs_member() -> None:
    # The read's RESULT position is `target` narrowed by `narrowTo` (m-object-query),
    # so a read narrowed to Dog is guaranteed to hand the executor a Dog. Judging the
    # set against the bare target instead would admit Cat's `indoor` here, which the
    # narrowed read can never satisfy.
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_DOG], {"indoor": True}) == [
        "probe: `mutate` set Dog.indoor: names no assignable attribute or value object"
    ]
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_PET], {"tuskLength": 1.5}) == [
        "probe: `mutate` set Cat.tuskLength: names no assignable attribute or value "
        "object — no concrete the read answers (Cat, Dog) admits the whole set"
    ]


def test_a_set_spanning_two_branches_names_no_node_at_all() -> None:
    # Dog admits the first key and Cat the second, but no single concrete instance
    # admits both, so judging each key against the family's union would pass a case
    # every executor refuses.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": 9, "indoor": True}) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value "
        "object — no concrete the read answers (Cat, Dog, WildBoar) admits the whole set"
    ]


def test_a_refusal_no_narrowing_can_fix_is_reported_from_the_declaring_concrete() -> None:
    # Every candidate refuses, so the assignment is wrong wherever it lands. Cat and
    # WildBoar answer only that the name is nothing of theirs, which says less than
    # Dog's own verdict on the value.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": "loud"}) == [
        "probe: `mutate` set Dog.barkVolume: value 'loud' does not match the declared "
        "type 'int32' — no concrete the read answers (Cat, Dog, WildBoar) admits the "
        "whole set"
    ]


def test_read_time_provenance_names_no_member_of_any_concrete() -> None:
    # `familyVariant` is the key an abstract-target read publishes beside the node's
    # members, and no concrete declares it.
    assert _edit("models/animal.yaml", _ANIMAL, {"familyVariant": "Cat"}) == [
        "probe: `mutate` set Cat.familyVariant: names no assignable attribute or value "
        "object — no concrete the read answers (Cat, Dog, WildBoar) admits the whole set"
    ]


def test_a_sibling_branchs_member_is_refused_on_a_concrete_target() -> None:
    assert _edit("models/animal.yaml", _DOG, {"indoor": True}) == [
        "probe: `mutate` set Dog.indoor: names no assignable attribute or value object"
    ]


def test_a_narrowing_to_one_concrete_is_judged_as_that_concrete_alone() -> None:
    # Narrowing an abstract SUBTYPE resolves the same way as narrowing the root, so a
    # case reaches every concrete position through the clause the read already has.
    assert _narrowed_edit("models/animal.yaml", _PET, [_CAT], {"indoor": True}) == []
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_DOG], {"barkVolume": "loud"}) == [
        "probe: `mutate` set Dog.barkVolume: value 'loud' does not match the declared type 'int32'"
    ]


def test_an_incoherent_narrowing_falls_back_to_the_unnarrowed_position() -> None:
    # A selection escaping the queried position states no position, so there is
    # nothing to narrow to. Judging against the whole queried set is the strictest
    # reading available — narrowing only ever removes candidates — so a broken
    # selection cannot buy an assignment a coherent one would have refused.
    assert _narrowed_edit(
        "models/animal.yaml", _ANIMAL, ["parallax.compatibility.Person"], {"barkVolume": 9}
    ) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value "
        "object — the read answers any of (Cat, Dog, WildBoar), so narrow it to the "
        "concrete this edit means"
    ]


def test_a_chained_edit_is_judged_against_the_find_its_chain_started_from() -> None:
    # A `mutate` naming an earlier `mutate` edits that copy, which carries the find's
    # own Entity: the chain resolves back to the read rather than stopping at a step
    # that declares no query.
    steps: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
        {"action": "mutate", "on": 1, "set": {"sku": 7}},
    ]
    assert _judged("models/orders.yaml", steps, 2) == [
        "probe: `mutate` set Order.sku: value 7 does not match the declared type 'string'"
    ]


def test_a_chain_through_a_same_entity_derivation_reaches_the_find() -> None:
    # A detached deep copy and a merged-back object are the object their source step
    # held, so an edit of one is judged against the find that materialized the chain.
    for verb in ("detachCopy", "mergeBack"):
        steps: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": verb, "on": 0},
            {"action": "mutate", "on": 1, "set": {"id": 2}},
        ]
        assert _judged("models/orders.yaml", steps, 2) == [
            "probe: `mutate` set Order.id: primary-key fields may not be assigned"
        ]


def test_a_chain_through_a_relationship_step_resolves_to_no_position() -> None:
    # A `load` / `access` result is the relationship TARGET, a different position from
    # the find's own, so the chain stops rather than judging against the wrong Entity.
    for verb in ("load", "access"):
        steps: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": verb, "on": 0, "path": "items"},
            {"action": "mutate", "on": 1, "set": {"nickname": "Nick"}},
        ]
        assert _judged("models/orders.yaml", steps, 2) == []


@pytest.mark.parametrize(
    "steps",
    [
        [{"write": []}, {"action": "mutate", "on": 0, "set": {"nickname": "Nick"}}],
        [{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "on": 7, "set": {"id": 2}}],
        [{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "set": {"id": 2}}],
    ],
)
def test_a_step_resolving_to_no_read_is_left_to_the_on_rules(steps: list[Any]) -> None:
    # An `on` naming a write step, an out-of-range index, or no index at all resolves
    # to no query: what the step edits is undecidable here, and the runtime `on`
    # rules already report the index itself.
    assert _judged("models/orders.yaml", steps, 1) == []


def test_a_change_free_edit_carries_nothing_to_judge() -> None:
    steps: list[Any] = [{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "on": 0}]
    assert _judged("models/orders.yaml", steps, 1) == []
