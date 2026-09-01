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
naming an applicable, assignable member with a value that member admits is
ACCEPTED, and each of the five ways one can fail — a name the Entity does not have
or a relationship name, a protected target, an ill-typed value, a null where the
member is not nullable, and a malformed Value Object document — is REJECTED. Two
structural halves ride along: WHERE the edited node stands (a derivation stands
where its source does, a `load` / `access` at its path's terminal position — each
hop resolved through the relationship APPLICABLE to every concrete the position
holds, inherited or its own — and a polymorphic position leaves the node's own
Entity open, so every concrete that position can answer must admit the whole
set), and where the walk stops (a step whose `on` reaches no position at all).
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
_PERSON = "parallax.compatibility.Person"
_PET = "parallax.compatibility.Pet"

# A relationship declared on ONE concrete branch of a family, which no corpus model
# carries: every corpus relationship over an inheritance family is declared on the
# abstract root. It is what makes a hop resolvable at one position and unresolvable
# at the broader one above it.
_BRANCH_RELATIONSHIP_DEFS: list[dict[str, Any]] = [
    {
        "name": "Animal",
        "namespace": "probe",
        "table": "animal",
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy",
            "tag": {"column": "kind"},
        },
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True},
            {"name": "toyId", "type": "int64", "nullable": True},
        ],
    },
    {
        "name": "Dog",
        "namespace": "probe",
        "inheritance": {"role": "concrete-subtype", "parent": "probe.Animal", "tagValue": "dog"},
        "relationships": [
            {
                "name": "favouriteToy",
                "cardinality": "many-to-one",
                "join": {"source": "toyId", "target": {"entity": "probe.Toy", "attribute": "id"}},
            }
        ],
    },
    {
        "name": "Cat",
        "namespace": "probe",
        "inheritance": {"role": "concrete-subtype", "parent": "probe.Animal", "tagValue": "cat"},
    },
    {
        "name": "Toy",
        "namespace": "probe",
        "table": "toy",
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True},
            {"name": "label", "type": "string", "maxLength": 32, "nullable": True},
        ],
    },
]


def _defs(model_rel: str) -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, model_rel).entity_defs


def _judged_defs(entity_defs: list[dict[str, Any]], steps: list[Any], index: int) -> list[str]:
    errors: list[str] = []
    _validate_scenario_edit(steps, index, entity_defs, Family(entity_defs), "probe", errors)
    return errors


def _judged(model_rel: str, steps: list[Any], index: int) -> list[str]:
    return _judged_defs(_defs(model_rel), steps, index)


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
        ("models/orders.yaml", _ORDER, {"price": "10.50", "qty": 5}),
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
        ({"qty": "five"}, "Order.qty: literal 'five' is type-mismatch for declared type 'int32'"),
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
    # `narrowTo` is how a case reaches a narrower position, and `barkVolume` is
    # Dog's own, so only the narrowing that leaves Dog alone admits it.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": 9}) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value "
        "object — the edited node is any of (Cat, Dog, WildBoar), so the set must be one "
        "every one of them admits; a read narrows to such a position with `narrowTo`"
    ]
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_DOG], {"barkVolume": 9}) == []


def test_a_narrowing_admitting_the_set_need_not_reach_one_concrete() -> None:
    # The bar is a position every concrete of which admits the whole set, NOT a
    # single concrete: `licenseId` is the abstract subtype Pet's own, so narrowing
    # Animal to Pet is narrow enough — both Cat and Dog inherit it — while the
    # unnarrowed read still fails on the sibling branch WildBoar, which does not.
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_PET], {"licenseId": "L-1"}) == []
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_CAT, _DOG], {"licenseId": "L-1"}) == []
    assert _edit("models/animal.yaml", _PET, {"licenseId": "L-1"}) == []
    assert _edit("models/animal.yaml", _ANIMAL, {"licenseId": "L-1"}) == [
        "probe: `mutate` set WildBoar.licenseId: names no assignable attribute or value "
        "object — the edited node is any of (Cat, Dog, WildBoar), so the set must be one "
        "every one of them admits; a read narrows to such a position with `narrowTo`"
    ]


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
        "object — no concrete the edited node may be (Cat, Dog) admits the whole set"
    ]


def test_a_set_spanning_two_branches_names_no_node_at_all() -> None:
    # Dog admits the first key and Cat the second, but no single concrete instance
    # admits both, so judging each key against the family's union would pass a case
    # every executor refuses.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": 9, "indoor": True}) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value object "
        "— no concrete the edited node may be (Cat, Dog, WildBoar) admits the whole set"
    ]


def test_a_refusal_no_narrowing_can_fix_is_reported_from_the_concrete_that_has_it() -> None:
    # Every candidate refuses, so the assignment is wrong wherever it lands. Cat and
    # WildBoar answer only that the name is nothing of theirs, which says less than
    # Dog's own verdict on the value.
    assert _edit("models/animal.yaml", _ANIMAL, {"barkVolume": "loud"}) == [
        "probe: `mutate` set Dog.barkVolume: literal 'loud' is type-mismatch for declared "
        "type 'int32' — no concrete the edited node may be (Cat, Dog, WildBoar) admits "
        "the whole set"
    ]


def test_read_time_provenance_names_no_member_of_any_concrete() -> None:
    # `familyVariant` is the key an abstract-target read publishes beside the node's
    # members, and no concrete declares it.
    assert _edit("models/animal.yaml", _ANIMAL, {"familyVariant": "Cat"}) == [
        "probe: `mutate` set Cat.familyVariant: names no assignable attribute or value "
        "object — no concrete the edited node may be (Cat, Dog, WildBoar) admits the "
        "whole set"
    ]


def test_a_sibling_branchs_member_is_refused_on_a_concrete_target() -> None:
    assert _edit("models/animal.yaml", _DOG, {"indoor": True}) == [
        "probe: `mutate` set Dog.indoor: names no assignable attribute or value object"
    ]


def test_a_narrowing_to_one_concrete_is_judged_as_that_concrete_alone() -> None:
    # Narrowing an abstract SUBTYPE resolves the same way as narrowing the root, so a
    # case reaches every position in the family through the clause the read already has.
    assert _narrowed_edit("models/animal.yaml", _PET, [_CAT], {"indoor": True}) == []
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_DOG], {"barkVolume": "loud"}) == [
        "probe: `mutate` set Dog.barkVolume: literal 'loud' is type-mismatch for declared "
        "type 'int32'"
    ]


def test_an_incoherent_narrowing_falls_back_to_the_unnarrowed_position() -> None:
    # A selection escaping the queried position states no position, so there is
    # nothing to narrow to. Judging against the whole queried set is the strictest
    # reading available — narrowing only ever removes candidates — so a broken
    # selection cannot buy an assignment a coherent one would have refused.
    assert _narrowed_edit("models/animal.yaml", _ANIMAL, [_PERSON], {"barkVolume": 9}) == [
        "probe: `mutate` set Cat.barkVolume: names no assignable attribute or value "
        "object — the edited node is any of (Cat, Dog, WildBoar), so the set must be one "
        "every one of them admits; a read narrows to such a position with `narrowTo`"
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
        "probe: `mutate` set Order.sku: literal 7 is type-mismatch for declared type 'string'"
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


def test_an_edit_after_a_relationship_step_is_judged_at_the_relationship_target() -> None:
    # A `load` / `access` result is the relationship TARGET, so an edit of one states
    # a member of the ITEM. Judging it against the find's own Entity would be wrong,
    # and judging it against nothing at all would let every invalid assignment on a
    # relationship result through the gate the corpus refuses one by.
    for verb in ("load", "access"):
        undeclared: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": verb, "on": 0, "path": "items"},
            {"action": "mutate", "on": 1, "set": {"nickname": "Nick"}},
        ]
        assert _judged("models/orders.yaml", undeclared, 2) == [
            "probe: `mutate` set OrderItem.nickname: names no assignable attribute or value object"
        ]
        source_member: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": verb, "on": 0, "path": "items"},
            {"action": "mutate", "on": 1, "set": {"name": "Mutant"}},
        ]
        assert _judged("models/orders.yaml", source_member, 2) == [
            "probe: `mutate` set OrderItem.name: names no assignable attribute or value object"
        ]
        admitted: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": verb, "on": 0, "path": "items"},
            {"action": "mutate", "on": 1, "set": {"sku": "COPY-ONLY"}},
        ]
        assert _judged("models/orders.yaml", admitted, 2) == []


def test_a_multi_hop_path_is_judged_at_its_terminal_position() -> None:
    # Each hop resolves at the position the previous one reached, so a dotted path
    # lands where its LAST hop does — including a hop back through a reverse
    # relationship, which returns to the entity the path started from.
    forward: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"action": "load", "on": 0, "path": "items.statuses"},
        {"action": "mutate", "on": 1, "set": {"sku": "A-100"}},
    ]
    assert _judged("models/orders.yaml", forward, 2) == [
        "probe: `mutate` set OrderStatus.sku: names no assignable attribute or value object"
    ]
    back: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"action": "load", "on": 0, "path": "items.order"},
        {"action": "mutate", "on": 1, "set": {"quantity": 2}},
    ]
    assert _judged("models/orders.yaml", back, 2) == [
        "probe: `mutate` set Order.quantity: names no assignable attribute or value object"
    ]


def test_a_path_less_access_stands_where_its_source_does() -> None:
    # The path-less `access` form navigates no relationship — it resolves a
    # query-backed list, whose members are the source's own position.
    steps: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"action": "access", "on": 0},
        {"action": "mutate", "on": 1, "set": {"id": 2}},
    ]
    assert _judged("models/orders.yaml", steps, 2) == [
        "probe: `mutate` set Order.id: primary-key fields may not be assigned"
    ]


def test_a_derivation_rooted_at_a_relationship_result_keeps_that_position() -> None:
    # The shape `m-detach-011` authors: a copy taken of (or merged back from) a
    # relationship result is still an item, so the position survives the derivation
    # instead of the chain falling back to the find or to nothing.
    for verb in ("mutate", "detachCopy", "mergeBack"):
        derivation: dict[str, Any] = {"action": verb, "on": 1}
        if verb == "mutate":
            derivation["set"] = {"sku": "COPY-ONLY"}
        steps: list[Any] = [
            {"objectQuery": {"target": _ORDER}},
            {"action": "access", "on": 0, "path": "items"},
            derivation,
            {"action": "mutate", "on": 2, "set": {"quantity": "five"}},
        ]
        assert _judged("models/orders.yaml", steps, 3) == [
            "probe: `mutate` set OrderItem.quantity: literal 'five' is type-mismatch for "
            "declared type 'int32'"
        ]


def test_a_grouped_load_stands_where_its_sources_do() -> None:
    # An `on` ARRAY spans sources at different lowered coordinates — one position
    # pinned several ways — so the load lands at the same relationship target a
    # single-source load would.
    steps: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"objectQuery": {"target": _ORDER}},
        {"action": "load", "on": [0, 1], "path": "items"},
        {"action": "mutate", "on": 2, "set": {"nickname": "Nick"}},
    ]
    assert _judged("models/orders.yaml", steps, 3) == [
        "probe: `mutate` set OrderItem.nickname: names no assignable attribute or value object"
    ]


def test_a_polymorphic_relationship_target_is_judged_as_every_concrete_it_reaches() -> None:
    # A navigated position is judged by the same whole-set/every-concrete rule a read's
    # own is: `Person.animals` reaches the whole family, `Person.pets` only Pet's branch.
    root_member: list[Any] = [
        {"objectQuery": {"target": _PERSON}},
        {"action": "load", "on": 0, "path": "animals"},
        {"action": "mutate", "on": 1, "set": {"name": "Mutant"}},
    ]
    assert _judged("models/animal.yaml", root_member, 2) == []
    branch_member: list[Any] = [
        {"objectQuery": {"target": _PERSON}},
        {"action": "load", "on": 0, "path": "animals"},
        {"action": "mutate", "on": 1, "set": {"licenseId": "L-1"}},
    ]
    assert _judged("models/animal.yaml", branch_member, 2) == [
        "probe: `mutate` set WildBoar.licenseId: names no assignable attribute or value "
        "object — the edited node is any of (Cat, Dog, WildBoar), so the set must be one "
        "every one of them admits; a read narrows to such a position with `narrowTo`"
    ]
    narrower_relationship: list[Any] = [
        {"objectQuery": {"target": _PERSON}},
        {"action": "load", "on": 0, "path": "pets"},
        {"action": "mutate", "on": 1, "set": {"licenseId": "L-1"}},
    ]
    assert _judged("models/animal.yaml", narrower_relationship, 2) == []


def test_an_inherited_relationship_is_navigable_from_every_concrete_that_inherits_it() -> None:
    # `owner` is declared on the abstract ROOT `Animal` and inherited by every
    # concrete descendant under that one identity (m-inheritance), so a read of the
    # concrete `Dog` — or of the abstract subtype `Pet` — navigates it and the edit
    # that follows stands on the `Person` it reaches. Resolving the hop against the
    # source's own declarations alone would find nothing on `Dog` and let every
    # invalid assignment behind an inherited hop through the gate.
    for source in (_DOG, _PET, _ANIMAL):
        for verb in ("load", "access"):
            undeclared: list[Any] = [
                {"objectQuery": {"target": source}},
                {"action": verb, "on": 0, "path": "owner"},
                {"action": "mutate", "on": 1, "set": {"nope": 1}},
            ]
            assert _judged("models/animal.yaml", undeclared, 2) == [
                "probe: `mutate` set Person.nope: names no assignable attribute or value object"
            ]
            source_member: list[Any] = [
                {"objectQuery": {"target": source}},
                {"action": verb, "on": 0, "path": "owner"},
                {"action": "mutate", "on": 1, "set": {"barkVolume": 9}},
            ]
            assert _judged("models/animal.yaml", source_member, 2) == [
                "probe: `mutate` set Person.barkVolume: names no assignable attribute or "
                "value object"
            ]
            admitted: list[Any] = [
                {"objectQuery": {"target": source}},
                {"action": verb, "on": 0, "path": "owner"},
                {"action": "mutate", "on": 1, "set": {"name": "Ann"}},
            ]
            assert _judged("models/animal.yaml", admitted, 2) == []


def test_an_inherited_hop_survives_a_later_hop_and_a_later_derivation() -> None:
    # The two ways the bypass outlived a single hop: `pets` lands on the abstract
    # subtype `Pet`, whose own `owner` is the root's, and a copy taken of a
    # relationship result still stands where that result does.
    later_hop: list[Any] = [
        {"objectQuery": {"target": _PERSON}},
        {"action": "access", "on": 0, "path": "pets.owner"},
        {"action": "mutate", "on": 1, "set": {"nope": 1}},
    ]
    assert _judged("models/animal.yaml", later_hop, 2) == [
        "probe: `mutate` set Person.nope: names no assignable attribute or value object"
    ]
    for verb in ("mutate", "detachCopy", "mergeBack"):
        derivation: dict[str, Any] = {"action": verb, "on": 1}
        if verb == "mutate":
            derivation["set"] = {"name": "Ann"}
        steps: list[Any] = [
            {"objectQuery": {"target": _DOG}},
            {"action": "access", "on": 0, "path": "owner"},
            derivation,
            {"action": "mutate", "on": 2, "set": {"id": 2}},
        ]
        assert _judged("models/animal.yaml", steps, 3) == [
            "probe: `mutate` set Person.id: primary-key fields may not be assigned"
        ]


def test_a_hop_only_some_concrete_of_the_position_has_reaches_no_position() -> None:
    # `favouriteToy` is `Dog`'s own, so a read that may hand the executor a `Cat`
    # states a navigation that node cannot make. The path is what is broken there,
    # which the runtime reports; judging the edit at `Toy` anyway would judge it for
    # a node the step may never reach.
    unreachable: list[Any] = [
        {"objectQuery": {"target": "probe.Animal"}},
        {"action": "access", "on": 0, "path": "favouriteToy"},
        {"action": "mutate", "on": 1, "set": {"nope": 1}},
    ]
    assert _judged_defs(_BRANCH_RELATIONSHIP_DEFS, unreachable, 2) == []
    # Narrowing the read to the declaring concrete makes the hop applicable to every
    # node the position holds, so the terminal position resolves and is judged.
    narrowed: list[Any] = [
        {"objectQuery": {"target": "probe.Animal", "narrowTo": ["probe.Dog"]}},
        {"action": "access", "on": 0, "path": "favouriteToy"},
        {"action": "mutate", "on": 1, "set": {"nope": 1}},
    ]
    assert _judged_defs(_BRANCH_RELATIONSHIP_DEFS, narrowed, 2) == [
        "probe: `mutate` set Toy.nope: names no assignable attribute or value object"
    ]
    admitted: list[Any] = [
        {"objectQuery": {"target": "probe.Animal", "narrowTo": ["probe.Dog"]}},
        {"action": "access", "on": 0, "path": "favouriteToy"},
        {"action": "mutate", "on": 1, "set": {"label": "ball"}},
    ]
    assert _judged_defs(_BRANCH_RELATIONSHIP_DEFS, admitted, 2) == []


def test_a_path_naming_no_relationship_reaches_no_position() -> None:
    # The navigation itself is then broken, which the runtime reports; guessing a
    # target here would judge the edit against an Entity the step never reaches.
    steps: list[Any] = [
        {"objectQuery": {"target": _ORDER}},
        {"action": "load", "on": 0, "path": "nope"},
        {"action": "mutate", "on": 1, "set": {"nickname": "Nick"}},
    ]
    assert _judged("models/orders.yaml", steps, 2) == []


def test_a_chain_reaching_itself_resolves_to_no_position() -> None:
    # A step whose `on` leads back to it names no earlier result at all. The runtime
    # `on` rules report the reference; the walk answers the cycle rather than looping.
    self_naming: list[Any] = [{"action": "mutate", "on": 0, "set": {"nickname": "Nick"}}]
    assert _judged("models/orders.yaml", self_naming, 0) == []
    mutual: list[Any] = [
        {"action": "detachCopy", "on": 1},
        {"action": "mutate", "on": 0, "set": {"nickname": "Nick"}},
    ]
    assert _judged("models/orders.yaml", mutual, 1) == []


@pytest.mark.parametrize(
    ("steps", "index"),
    [
        ([{"write": []}, {"action": "mutate", "on": 0, "set": {"nickname": "Nick"}}], 1),
        ([{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "on": 7, "set": {"id": 2}}], 1),
        ([{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "set": {"id": 2}}], 1),
        (
            [
                {"objectQuery": {"target": _ORDER}},
                {"action": "mutate", "on": [0], "set": {"id": 2}},
            ],
            1,
        ),
        (
            [
                {"objectQuery": {"target": _ORDER}},
                {"action": "commit", "on": 0},
                {"action": "mutate", "on": 1, "set": {"id": 2}},
            ],
            2,
        ),
    ],
)
def test_a_step_resolving_to_no_position_is_left_to_the_on_rules(
    steps: list[Any], index: int
) -> None:
    # An `on` naming a write step, an out-of-range index, no index at all, a GROUP of
    # sources where the verb acts on one object, or a boundary verb that holds no
    # queried node resolves to no position: where the step's node stands is undecidable
    # here, and the runtime `on` rules already report the reference itself.
    assert _judged("models/orders.yaml", steps, index) == []


def test_a_change_free_edit_carries_nothing_to_judge() -> None:
    steps: list[Any] = [{"objectQuery": {"target": _ORDER}}, {"action": "mutate", "on": 0}]
    assert _judged("models/orders.yaml", steps, 1) == []
