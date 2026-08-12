"""DB-free unit tests for the abstract-target inheritance READ oracle.

The read-side counterpart of the write-derivation oracle (m-inheritance / m-sql,
resolved Q6): from the descriptor alone the harness derives a narrow's effective
concrete-subtype set and its validity, the abstract-read projection superset, and
the per-row `familyVariant` (`tagValue` -> concrete subtype name). These tests
exercise that derivation with no database:

* the narrow four-step validation ACCEPTS a valid / redundant narrow and RAISES the
  exact operation rule for a broadening narrow, an empty effective set, and a
  concrete-subtype attribute used outside a compatible narrowing scope;
* the family-variant map and the concrete superset are derived from the ancestry;
* `_materialize_family_variant` replaces the raw tag column with the derived
  `familyVariant`, and FAILS loudly when the golden projection omits a superset
  column or the tag column.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.case import Case, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _materialize_family_variant,
    _resolve_hop,
    run_case,
)
from reference_harness.inheritance import (
    ATTRIBUTE_OUTSIDE_ACTIVE_POSITION,
    NARROW_EMPTY_EFFECTIVE_SET,
    NARROW_OUTSIDE_POSITION,
    REFERENCE_AMBIGUOUS_ENTITY_NAME,
    SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
    SUBTYPE_SELECTION_DUPLICATE_ALTERNATIVE,
    SUBTYPE_SELECTION_OVERLAPPING_ALTERNATIVES,
    Family,
    tag_value_to_subtype,
    validate_query_inheritance,
)
from reference_harness.storage_layout import compile_storage_layout, position_projection
from reference_harness.value_object_resolve import RejectionError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _animal_defs() -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, "models/animal.yaml").entity_defs


def _judge(defs: list[dict[str, Any]], position: str, **clauses: Any) -> None:
    """Judge the Object Query ``clauses`` author at the queried position ``position``.

    The walk judges a whole query, so a claim about one clause is stated by naming
    that clause and letting every other take its unfiltered default.
    """
    validate_query_inheritance(defs, {"target": position, "predicate": {"all": {}}, **clauses})


# --- effective concrete-set derivation --------------------------------------


def test_effective_and_narrow_resolution() -> None:
    family = Family(_animal_defs())
    # The effective concrete set is in canonical sibling-set order: ALPHABETICAL by
    # entity name (Cat < Dog < WildBoar), independent of the descriptor's file layout
    # (which declares Dog, Cat, WildBoar).
    assert family.effective_concrete_set("Animal") == ["Cat", "Dog", "WildBoar"]
    assert family.effective_concrete_set("Pet") == ["Cat", "Dog"]
    assert family.effective_concrete_set("Dog") == ["Dog"]
    # An abstract subtype and its explicit concrete list resolve to the same SET.
    assert set(family.resolve_to_set(["Pet"])) == {"Dog", "Cat"}
    assert set(family.resolve_to_set(["Cat", "Dog"])) == {"Dog", "Cat"}


def test_canonical_order_is_independent_of_descriptor_layout() -> None:
    # The canonical sibling-set order is ALPHABETICAL by entity name, a total order
    # that does NOT depend on the order the descriptor declares the subtypes. This
    # inline family declares its concretes in REVERSE-alphabetical order (Zebra, Mule,
    # Ant) yet the effective set comes back alphabetical (Ant, Mule, Zebra).
    defs = [
        {
            "name": "Beast",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
        },
        {
            "name": "Zebra",
            "table": "beast",
            "inheritance": {"role": "concrete-subtype", "parent": "Beast", "tagValue": "z"},
            "attributes": [],
        },
        {
            "name": "Mule",
            "table": "beast",
            "inheritance": {"role": "concrete-subtype", "parent": "Beast", "tagValue": "m"},
            "attributes": [],
        },
        {
            "name": "Ant",
            "table": "beast",
            "inheritance": {"role": "concrete-subtype", "parent": "Beast", "tagValue": "a"},
            "attributes": [],
        },
    ]
    family = Family(defs)
    assert family.effective_concrete_set("Beast") == ["Ant", "Mule", "Zebra"]
    assert family.canonical_concrete_order(["Zebra", "Ant", "Mule"]) == ["Ant", "Mule", "Zebra"]


def test_canonical_concrete_order_sorts_exact_identities_then_renders_unique_locals() -> None:
    family = Family(
        [
            {
                "name": "Root",
                "namespace": "root",
                "inheritance": {
                    "role": "root",
                    "strategy": "table-per-concrete-subtype",
                },
            },
            {
                "name": "Alpha",
                "namespace": "z",
                "inheritance": {"role": "concrete-subtype", "parent": "root.Root"},
            },
            {
                "name": "Zulu",
                "namespace": "a",
                "inheritance": {"role": "concrete-subtype", "parent": "root.Root"},
            },
        ]
    )
    assert family.concrete_descendants("Root") == [
        "Zulu",
        "Alpha",
    ]


# --- the narrow four-step validation ----------------------------------------


def test_valid_and_redundant_narrows_are_accepted() -> None:
    defs = _animal_defs()
    # Narrow the root to a proper subset (Pet -> Dog, Cat).
    _judge(defs, "Animal", predicate={"narrow": {"to": ["Pet"], "operand": {"all": {}}}})
    # Redundant narrow (a position to itself) is a no-op, not a rejection.
    _judge(defs, "Pet", predicate={"narrow": {"to": ["Pet"], "operand": {"all": {}}}})
    # A concrete-subtype attribute IS in scope once narrowed to that subtype.
    _judge(
        defs,
        "Animal",
        predicate={
            "narrow": {
                "to": ["Dog"],
                "operand": {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
            }
        },
    )


def test_subtype_selection_rejects_an_exact_duplicate() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={"narrow": {"to": ["Dog", "Dog"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == SUBTYPE_SELECTION_DUPLICATE_ALTERNATIVE


def test_subtype_selection_rejects_overlapping_alternatives() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={"narrow": {"to": ["Dog", "Pet"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == SUBTYPE_SELECTION_OVERLAPPING_ALTERNATIVES


def test_subtype_selection_checks_exact_duplicates_before_overlap() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={"narrow": {"to": ["Pet", "Dog", "Dog"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == SUBTYPE_SELECTION_DUPLICATE_ALTERNATIVE


def test_broadening_narrow_is_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={"narrow": {"to": ["Person"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_narrow_broadening_beyond_the_threaded_position_is_rejected() -> None:
    # A predicate-root selection cannot reach a subtype outside the active threaded
    # position: narrowing Pet to [WildBoar] resolves outside Pet. It lives here as a
    # unit test rather than in the corpus because the corpus already pins the same
    # subset rule at the queried position (m-inheritance-040).
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Pet",
            predicate={"narrow": {"to": ["WildBoar"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_nested_narrow_cannot_broaden_back_out() -> None:
    # After the OUTER narrow ([Dog]) the active position is {Dog}. The INNER
    # selection asks for [Cat], broadening back out of {Dog}. It is outside the
    # threaded active position, so it is rejected. (The corpus witness is
    # m-inheritance-042; this pins the same claim directly through the walker.)
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={
                "narrow": {
                    "to": ["Dog"],
                    "operand": {"narrow": {"to": ["Cat"], "operand": {"all": {}}}},
                }
            },
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_narrow_within_the_context_supplied_position_is_accepted() -> None:
    # The position is supplied by context. A [Dog] selection inside Pet stays valid.
    _judge(_animal_defs(), "Pet", predicate={"narrow": {"to": ["Dog"], "operand": {"all": {}}}})


def test_narrow_to_empty_effective_set_is_rejected() -> None:
    # An abstract subtype with NO concrete descendants resolves to the empty set;
    # narrowing to it is rejected as an empty effective set. Built inline so the
    # corpus families (every abstract subtype has concretes) stay untouched.
    defs = [
        {
            "name": "Root",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
        },
        {
            "name": "Empty",
            "inheritance": {"role": "abstract-subtype", "parent": "Root"},
            "attributes": [],
        },
        {
            "name": "Real",
            "table": "root",
            "inheritance": {"role": "concrete-subtype", "parent": "Root", "tagValue": "real"},
            "attributes": [{"name": "v", "type": "int32", "column": "v", "nullable": True}],
        },
    ]
    with pytest.raises(RejectionError) as exc:
        _judge(defs, "Root", predicate={"narrow": {"to": ["Empty"], "operand": {"all": {}}}})
    assert exc.value.rule == NARROW_EMPTY_EFFECTIVE_SET


def test_subtype_attribute_outside_narrow_scope_is_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate={"greaterThan": {"attr": "Dog.barkVolume", "value": 5}},
        )
    assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


def test_inherited_attribute_is_always_in_scope() -> None:
    # `name` is declared on the root Animal, so it is available to every concrete in
    # any position — a root-position predicate on it is NOT a subtype-scope violation.
    _judge(_animal_defs(), "Animal", predicate={"eq": {"attr": "Animal.name", "value": "Rex"}})


def test_a_position_is_measured_against_the_entity_a_reference_names() -> None:
    # m-predicate measures the rule against the REFERENCED entity, not the ancestor
    # that declares the member: "the active position's effective set is a subset of
    # the referenced Entity's". `Dog.name` therefore names dogs even though `name` is
    # declared on Animal, so at the root position it is out of scope and a narrow to
    # Dog is the remedy. Substituting the declaring entity would accept it, and would
    # equally accept a DISJOINT sibling's spelling (`Cat.name` inside a narrow to
    # Dog), which addresses no row the position contains. Pinned by m-op-algebra-049.
    defs = _animal_defs()
    for reference in ("Dog.name", "Cat.name", "Pet.licenseId"):
        with pytest.raises(RejectionError) as exc:
            _judge(defs, "Animal", predicate={"eq": {"attr": reference, "value": "Rex"}})
        assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE

    with pytest.raises(RejectionError) as ordered:
        _judge(defs, "Animal", orderBy=[{"attr": "Dog.name"}])
    assert ordered.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE

    with pytest.raises(RejectionError) as sibling:
        _judge(
            defs,
            "Animal",
            predicate={
                "narrow": {
                    "to": ["Dog"],
                    "operand": {"eq": {"attr": "Cat.name", "value": "Tom"}},
                }
            },
        )
    assert sibling.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE

    _judge(
        defs,
        "Animal",
        predicate={
            "narrow": {
                "to": ["Dog"],
                "operand": {"eq": {"attr": "Dog.name", "value": "Rex"}},
            }
        },
    )


def test_non_inheritance_model_accepts_its_own_entitys_attribute() -> None:
    defs = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").entity_defs
    _judge(defs, "Customer", predicate={"eq": {"attr": "Customer.name", "value": "Ada"}})


def test_a_standalone_entitys_attribute_is_outside_an_unrelated_standalone_position() -> None:
    # The positional rule is not an inheritance rule wearing a second name: with no
    # family anywhere in the descriptor, a standalone entity's effective concrete set
    # is itself, so the same subset test rejects `OrderItem.sku` at `Order`. Both
    # entities declare a `sku`, so an unchecked reference reads the orders table for
    # a question about items. Pinned by m-op-algebra-047.
    defs = load_model(_COMPATIBILITY_ROOT, "models/orders.yaml").entity_defs
    with pytest.raises(RejectionError) as exc:
        _judge(defs, "Order", predicate={"eq": {"attr": "OrderItem.sku", "value": "SKU-1"}})
    assert exc.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION

    with pytest.raises(RejectionError) as ordered:
        _judge(defs, "Order", orderBy=[{"attr": "OrderItem.sku"}])
    assert ordered.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION


def test_a_navigation_filter_re_roots_the_position_in_a_non_inheritance_model() -> None:
    # The hop's target is the active position for the inner predicate, so the related
    # entity's own attribute is in scope there and the SOURCE entity's is not.
    defs = load_model(_COMPATIBILITY_ROOT, "models/orders.yaml").entity_defs
    _judge(
        defs,
        "Order",
        predicate={
            "exists": {"rel": "Order.items", "op": {"eq": {"attr": "OrderItem.sku", "value": "s"}}}
        },
    )
    with pytest.raises(RejectionError) as exc:
        _judge(
            defs,
            "Order",
            predicate={
                "exists": {"rel": "Order.items", "op": {"eq": {"attr": "Order.sku", "value": "s"}}}
            },
        )
    assert exc.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION


def test_a_canonically_spelled_reference_resolves_to_the_entity_it_names() -> None:
    # The class part is the spelling up to the LAST dot, so a namespaced position
    # names its entity rather than its leading namespace segment. Splitting on the
    # first dot instead yields `parallax`, which names no entity, and the reference
    # escapes the positional check entirely.
    defs = _animal_defs()
    _judge(
        defs,
        "Animal",
        predicate={"eq": {"attr": "parallax.compatibility.Animal.name", "value": "Rex"}},
    )
    with pytest.raises(RejectionError) as foreign:
        _judge(
            defs,
            "Animal",
            predicate={"eq": {"attr": "parallax.compatibility.Person.name", "value": "Ada"}},
        )
    assert foreign.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION
    with pytest.raises(RejectionError) as subtype:
        _judge(
            defs,
            "Animal",
            predicate={"eq": {"attr": "parallax.compatibility.Dog.barkVolume", "value": 5}},
        )
    assert subtype.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


_TWO_NAMESPACES: list[dict[str, Any]] = [
    {
        "name": "Customer",
        "namespace": "crm",
        "table": "crm_customer",
        "attributes": [
            {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
            {"name": "name", "type": "string", "column": "name", "maxLength": 32},
        ],
    },
    {
        "name": "Customer",
        "namespace": "sales",
        "table": "sales_customer",
        "attributes": [
            {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
            {"name": "name", "type": "string", "column": "name", "maxLength": 32},
        ],
    },
]


def test_two_namespaces_sharing_a_local_name_stay_distinct_positions() -> None:
    # Each namespace's entity is its own effective concrete set, so a canonically
    # spelled reference to the OTHER namespace's same-named entity is outside the
    # position rather than silently equal to it.
    _judge(
        _TWO_NAMESPACES,
        "crm.Customer",
        predicate={"eq": {"attr": "crm.Customer.name", "value": "Ada"}},
    )
    with pytest.raises(RejectionError) as exc:
        _judge(
            _TWO_NAMESPACES,
            "crm.Customer",
            predicate={"eq": {"attr": "sales.Customer.name", "value": "Ada"}},
        )
    assert exc.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION


def _shared_local_name_defs() -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, "models/shared-local-name.yaml").entity_defs


# Every position that names an entity, spelled the only way the operation grammars
# allow — bare — against the model declaring `SharedVariant` in two namespaces. The
# rule is about the spelling failing to resolve, so it fires wherever a position is
# named, not only where an attribute is referenced.
_AMBIGUOUS_BY_POSITION: dict[str, dict[str, Any]] = {
    "attr": {"predicate": {"eq": {"attr": "SharedVariant.archiveLabel", "value": "A-1"}}},
    "orderBy.attr": {"orderBy": [{"attr": "SharedVariant.archiveLabel"}]},
    "rel": {"predicate": {"exists": {"rel": "SharedVariant.register", "op": {"all": {}}}}},
    # A nested path spells its entity as its FIRST segment, so its resolution is
    # asked of a different split than an `attr`'s and needs its own position here.
    "nested path": {
        "predicate": {"nestedEq": {"path": "SharedVariant.spec.label", "value": "A-1"}}
    },
    "nestedExists path": {"predicate": {"nestedExists": {"path": "SharedVariant.spec"}}},
    "narrow.to": {"predicate": {"narrow": {"to": ["SharedVariant"], "operand": {"all": {}}}}},
    "narrowTo": {"narrowTo": ["SharedVariant"]},
    "includes.segment.rel": {"includes": [{"segments": [{"rel": "SharedVariant.register"}]}]},
    "includes.segment.narrowTo": {
        "includes": [{"segments": [{"rel": "Register.variant", "narrowTo": ["SharedVariant"]}]}]
    },
    "includes.appliesTo": {
        "includes": [{"appliesTo": ["SharedVariant"], "segments": [{"rel": "Register.variant"}]}]
    },
    "relationship-scope narrow.to": {
        "predicate": {
            "exists": {
                "rel": "Register.variant",
                "op": {"narrow": {"to": ["SharedVariant"], "operand": {"all": {}}}},
            }
        }
    },
}


@pytest.mark.parametrize("position", sorted(_AMBIGUOUS_BY_POSITION))
def test_a_bare_name_two_namespaces_share_is_rejected_in_every_reference_position(
    position: str,
) -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(_shared_local_name_defs(), "Register", **_AMBIGUOUS_BY_POSITION[position])
    assert exc.value.rule == REFERENCE_AMBIGUOUS_ENTITY_NAME
    assert "archive.SharedVariant" in exc.value.detail
    assert "catalog.SharedVariant" in exc.value.detail


def test_an_unambiguous_bare_name_still_resolves_in_a_two_namespace_model() -> None:
    # The refusal is a property of the SPELLING, not of the model: the same model
    # answers every bare name only one namespace declares, so declaring the
    # collision costs the rest of the model nothing.
    defs = _shared_local_name_defs()
    _judge(defs, "Register", predicate={"eq": {"attr": "Register.id", "value": 1}})
    _judge(defs, "Register", predicate={"exists": {"rel": "Register.variant", "op": {"all": {}}}})


def test_an_unrelated_entitys_attribute_is_outside_the_active_position() -> None:
    # `Person` is the plain owner entity, in no inheritance family with the animals.
    # Narrowing cannot bring it into scope, so the reference takes the non-family
    # half of the positional rule rather than the narrow-scope half. `Animal`
    # declares a `name` of its own, so an unchecked reference would silently answer
    # a different question.
    with pytest.raises(RejectionError) as exc:
        _judge(_animal_defs(), "Animal", predicate={"eq": {"attr": "Person.name", "value": "Ada"}})
    assert exc.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION


def test_a_related_entitys_attribute_is_in_scope_inside_a_navigation_filter() -> None:
    # The hop re-roots the active position at the relationship target, so the inner
    # predicate is asked of Pet's concretes, not of Person's.
    _judge(
        _animal_defs(),
        "Person",
        predicate={
            "exists": {"rel": "Person.pets", "op": {"eq": {"attr": "Animal.name", "value": "Rex"}}}
        },
    )


def test_an_order_key_outside_the_active_position_is_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(_animal_defs(), "Animal", orderBy=[{"attr": "Person.name"}])
    assert exc.value.rule == ATTRIBUTE_OUTSIDE_ACTIVE_POSITION


def test_an_order_key_reads_the_position_result_narrowing_moved_it_to() -> None:
    # A Sort Key addresses the rows the query RETURNS, so a Dog key is legal exactly
    # when `narrowTo` narrowed the result to Dog, and refused when it did not.
    _judge(_animal_defs(), "Animal", narrowTo=["Dog"], orderBy=[{"attr": "Dog.barkVolume"}])

    with pytest.raises(RejectionError) as exc:
        _judge(_animal_defs(), "Animal", orderBy=[{"attr": "Dog.barkVolume"}])
    assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


_NARROW_TO_DOG: dict[str, Any] = {"narrow": {"to": ["Dog"], "operand": {"all": {}}}}
_INCLUDE_OWNER: list[dict[str, Any]] = [{"segments": [{"rel": "Animal.owner"}]}]


@pytest.mark.parametrize(
    "clauses",
    [
        {"limit": 5},
        {"includes": _INCLUDE_OWNER},
        {"temporal": {"valid-time": {"asOf": "latest"}}},
        {"limit": 5, "includes": _INCLUDE_OWNER},
    ],
    ids=["limit", "includes", "temporal", "limit+includes"],
)
def test_no_other_clause_moves_the_ordered_position(clauses: dict[str, Any]) -> None:
    # Result narrowing is the ONLY clause that moves the position a Sort Key is
    # measured at. Every other clause is its sibling and shapes something else, so
    # adding any of them beside the narrowing leaves the same key in scope — which
    # is a property of the flat query rather than a rule anything restates.
    _judge(
        _animal_defs(),
        "Animal",
        narrowTo=["Dog"],
        orderBy=[{"attr": "Dog.barkVolume"}],
        **clauses,
    )


@pytest.mark.parametrize("combinator", ["and", "or", "group", "not"])
def test_a_narrow_inside_a_boolean_combinator_moves_no_ordered_position(combinator: str) -> None:
    # A narrow used as a predicate term filters the same position rather than
    # narrowing the result, so the order key is still asked of the whole family.
    predicate = (
        {combinator: {"operands": [_NARROW_TO_DOG]}}
        if combinator in ("and", "or")
        else {combinator: {"operand": _NARROW_TO_DOG}}
    )
    with pytest.raises(RejectionError) as exc:
        _judge(
            _animal_defs(),
            "Animal",
            predicate=predicate,
            orderBy=[{"attr": "Dog.barkVolume"}],
        )
    assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


class _RefusingDb:
    """A provider that fails loudly if the runner reaches the database at all."""

    dialect = "postgres"

    def reset(self) -> None:
        raise AssertionError("a read refused pre-SQL must never provision a database")

    def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
        raise AssertionError(f"a read refused pre-SQL must never execute {sql!r}")


def test_run_case_validates_a_deep_fetch_reads_positions_before_any_sql() -> None:
    # Guards the WIRING: every read result form reaches the positional oracle through
    # one owner in `run_case`, so a read carrying Includes is validated exactly as a
    # flat one is. This query orders the whole Animal family by a Dog-declared
    # attribute with no narrowing to bring it into scope; if the graph forms were
    # left unvalidated the refusal would go unnoticed and the case would reach a
    # database.
    raw = {
        "model": "models/animal.yaml",
        "tags": ["m-inheritance"],
        "shape": "read",
        "when": {
            "objectQuery": {
                "target": "Animal",
                "predicate": {"all": {}},
                "orderBy": [{"attr": "Dog.barkVolume"}],
                "includes": _INCLUDE_OWNER,
            },
        },
        # SQL text is inert: the refusal precedes execution, so nothing runs it.
        "then": {
            "statements": [
                {"sql": {"postgres": _ANIMAL_GOLDEN}},
                {"sql": {"postgres": "select t0.id, t0.name from person t0"}},
            ],
            "graph": {"Animal": []},
            "roundTrips": 2,
        },
    }
    case = Case(
        path=Path("m-inheritance-999-x.yaml"),
        raw=raw,
        model=load_model(_COMPATIBILITY_ROOT, "models/animal.yaml"),
    )
    with pytest.raises(RejectionError) as exc:
        run_case(case, cast("Any", _RefusingDb()))
    assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


# --- familyVariant + projection superset derivation -------------------------


def test_tag_value_to_subtype_map() -> None:
    assert tag_value_to_subtype(_animal_defs()) == {
        "dog": "Dog",
        "cat": "Cat",
        "boar": "WildBoar",
    }


def test_tag_value_to_subtype_qualifies_duplicate_local_names() -> None:
    defs = [
        {
            "name": "Root",
            "namespace": "catalog",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
        },
        {
            "name": "Entry",
            "namespace": "archive",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "catalog.Root",
                "tagValue": "archive",
            },
        },
        {
            "name": "Entry",
            "namespace": "catalog",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "Root",
                "tagValue": "current",
            },
        },
    ]
    assert tag_value_to_subtype(defs) == {
        "archive": "archive.Entry",
        "current": "catalog.Entry",
    }


def test_tph_position_projection_follows_the_shared_table_layout() -> None:
    defs = _animal_defs()
    layout = compile_storage_layout(defs)
    family = Family(defs)
    # The shared Table Layout's tier order: the `Identity` slot, the raw
    # `Discriminator` slot, then the `Domain` slots — ancestry prefix first,
    # then each concrete's own block in alphabetical subtype order. Pet's
    # descendants alone drop WildBoar's `tusk_length` without disturbing it.
    assert position_projection(layout, family, ["Dog", "Cat"]) == (
        "id",
        "kind",
        "name",
        "owner_id",
        "license_id",
        "indoor",
        "bark_volume",
    )
    assert position_projection(layout, family, ["Dog", "Cat", "WildBoar"]) == (
        "id",
        "kind",
        "name",
        "owner_id",
        "license_id",
        "indoor",
        "bark_volume",
        "tusk_length",
    )


def test_tpcs_position_projection_order_is_canonical() -> None:
    # The stable cross-Table contributor ORDER (not just the set): the inherited
    # prefix in ANCESTRY order (id, title, folder_id, currency) then the
    # per-subtype OWN-column blocks in ALPHABETICAL subtype order — Invoice's
    # amount_due, then Memo's body, then Receipt's paid_amount. The passed
    # effective set is deliberately shuffled to prove canonicalization.
    defs = _document_defs()
    layout = compile_storage_layout(defs)
    family = Family(defs)
    assert position_projection(layout, family, ["Receipt", "Memo", "Invoice"]) == (
        "id",
        "title",
        "folder_id",
        "currency",
        "amount_due",
        "body",
        "paid_amount",
    )


def test_tpcs_single_concrete_position_projection_is_its_own_table() -> None:
    # A single-concrete position is an ordinary read of that concrete's own
    # Table: its ancestry chain plus its own slot, and no sibling padding.
    defs = _document_defs()
    layout = compile_storage_layout(defs)
    family = Family(defs)
    assert position_projection(layout, family, ["Invoice"]) == (
        "id",
        "title",
        "folder_id",
        "currency",
        "amount_due",
    )


# --- _materialize_family_variant --------------------------------------------


# The full Animal-family concrete superset projected with the raw tag column
# (`kind`) — the shape an abstract-root read of Animal MUST emit. The failing-mode
# tests drop one column from this to witness the row-count-independent check.
_ANIMAL_GOLDEN = (
    "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, "
    "t0.indoor, t0.tusk_length, t0.kind from animal t0"
)


def _read_case(target: str, golden: str = _ANIMAL_GOLDEN, **clauses: Any) -> Case:
    model = load_model(_COMPATIBILITY_ROOT, "models/animal.yaml")
    raw = {
        "model": "models/animal.yaml",
        "tags": ["m-inheritance"],
        "shape": "read",
        "when": {"objectQuery": {"target": target, "predicate": {"all": {}}, **clauses}},
        "then": {"statements": [{"sql": {"postgres": golden}}], "rows": []},
    }
    return Case(path=Path("m-inheritance-999-x.yaml"), raw=raw, model=model)


def _dog_row() -> dict[str, Any]:
    return {
        "id": 1,
        "name": "Rex",
        "owner_id": 10,
        "license_id": "L-100",
        "bark_volume": 7,
        "indoor": None,
        "tusk_length": None,
        "kind": "dog",
    }


def test_materialize_replaces_tag_with_family_variant() -> None:
    case = _read_case("Animal")
    out = _materialize_family_variant(case, [_dog_row()])
    assert out == [
        {
            "id": 1,
            "name": "Rex",
            "owner_id": 10,
            "license_id": "L-100",
            "bark_volume": 7,
            "indoor": None,
            "tusk_length": None,
            "familyVariant": "Dog",
        }
    ]


def test_materialize_is_noop_for_concrete_target() -> None:
    case = _read_case("Dog")
    rows = [{"id": 1, "name": "Rex", "license_id": "L-100", "bark_volume": 7}]
    assert _materialize_family_variant(case, rows) == rows


def test_materialize_fails_when_superset_column_missing() -> None:
    # The GOLDEN drops WildBoar's tusk_length, so the Animal superset is not projected.
    # The check reads the projection from the golden SQL, not the sampled row.
    golden = (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.kind from animal t0"
    )
    case = _read_case("Animal", golden)
    with pytest.raises(CaseFailure, match="concrete-superset column"):
        _materialize_family_variant(case, [_dog_row()])


_DOG_NARROWED_GOLDEN = (
    "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.bark_volume from animal t0"
)


def test_materialize_reads_the_narrowed_projection_through_a_deep_fetch() -> None:
    # A deep fetch attaches fetched levels to the rows its operand yields rather than
    # replacing them, so its ROOT projection follows the operand's own narrow: a root
    # narrowed to Dog projects Dog's chain and no sibling column. Reading the position
    # from the queried `target` alone would demand Cat's `indoor` and WildBoar's
    # `tusk_length` here and reject a golden the compiler correctly emits.
    case = _read_case(
        "Animal",
        _DOG_NARROWED_GOLDEN,
        narrowTo=["Dog"],
        orderBy=[{"attr": "Dog.barkVolume", "direction": "desc"}],
        includes=_INCLUDE_OWNER,
    )
    row = {
        "id": 1,
        "kind": "dog",
        "name": "Rex",
        "owner_id": 10,
        "license_id": "L-100",
        "bark_volume": 7,
    }
    assert _materialize_family_variant(case, [row]) == [
        {
            "id": 1,
            "name": "Rex",
            "owner_id": 10,
            "license_id": "L-100",
            "bark_volume": 7,
            "familyVariant": "Dog",
        }
    ]


def test_materialize_fails_when_tag_column_missing() -> None:
    # Pet's superset (no tusk_length) but with the tag column `kind` dropped from the GOLDEN.
    golden = (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, "
        "t0.indoor from animal t0"
    )
    case = _read_case("Pet", golden)
    row = {
        "id": 1,
        "name": "Rex",
        "owner_id": 10,
        "license_id": "L-100",
        "bark_volume": 7,
        "indoor": None,
    }
    with pytest.raises(CaseFailure, match="tag column"):
        _materialize_family_variant(case, [row])


# --- row-count-independence of the projection-shape check ---------------------
#
# The projection shape is derived from the GOLDEN SELECT, not a sample row, so a
# ZERO-row abstract-target read still witnesses a golden that drops a superset / tag
# column. Before this fix the check was gated `if rows:` and read `rows[0].keys()`, so
# these empty-result cases passed silently (nothing to inspect). They are the
# reproduce-then-green witnesses for closing that gap.


def test_materialize_zero_row_missing_superset_column_still_fails() -> None:
    golden = (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.kind from animal t0"  # WildBoar's tusk_length dropped
    )
    case = _read_case("Animal", golden)
    with pytest.raises(CaseFailure, match="concrete-superset column"):
        _materialize_family_variant(case, [])


def test_materialize_zero_row_missing_tag_column_still_fails() -> None:
    golden = (
        "select t0.id, t0.name, t0.owner_id, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.tusk_length from animal t0"  # tag column `kind` dropped
    )
    case = _read_case("Animal", golden)
    with pytest.raises(CaseFailure, match="tag column"):
        _materialize_family_variant(case, [])


def test_materialize_zero_row_correct_golden_passes() -> None:
    # Positive twin: an empty result over a correct full-superset + tag golden
    # materializes nothing and does NOT raise.
    case = _read_case("Animal")
    assert _materialize_family_variant(case, []) == []


# --- table-per-concrete-subtype `union all` oracle -----------------------------
#
# The TPCS counterpart of the TPH projection-shape check: from the descriptor alone
# the harness recomputes the `union all` branch count/order (the effective concrete
# set in ALPHABETICAL order by entity name), the stable superset projection every
# branch shares, and each branch's `familyVariant` subtype-name LITERAL (the settled
# TPCS asymmetry — TPCS projects the variant literal per branch, TPH derives it from
# the raw tag).


def _document_model() -> Any:
    return load_model(_COMPATIBILITY_ROOT, "models/document.yaml")


def _document_defs() -> list[dict[str, Any]]:
    return _document_model().entity_defs


# The canonical three-branch abstract-root golden (Document over Invoice / Memo /
# Receipt — ALPHABETICAL branch order). The stable superset is inherited
# (id, title, folder_id) first, then the OWN-column blocks in alphabetical subtype
# order — Invoice's amount_due, Memo's body, Receipt's paid_amount (currency is
# FinancialDocument's inherited attribute, contributed where Invoice's chain first
# surfaces it; folder_id is the polymorphic-owner FK on the root). The
# failing-mode tests mutate one aspect of this to witness the check.
_DOCUMENT_ROOT_UNION = (
    "select t0.id, t0.title, t0.folder_id, t0.currency, t0.amount_due, "
    "cast(null as varchar(64)) body, cast(null as decimal(18, 2)) paid_amount, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.folder_id, cast(null as varchar(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, t0.body, "
    "cast(null as decimal(18, 2)) paid_amount, 'Memo' family_variant from memo t0 "
    "union all "
    "select t0.id, t0.title, t0.folder_id, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "cast(null as varchar(64)) body, t0.paid_amount, 'Receipt' family_variant "
    "from receipt t0"
)


def _document_case(target: str, golden: str = _DOCUMENT_ROOT_UNION, **clauses: Any) -> Case:
    model = _document_model()
    raw = {
        "model": "models/document.yaml",
        "tags": ["m-inheritance"],
        "shape": "read",
        "when": {"objectQuery": {"target": target, "predicate": {"all": {}}, **clauses}},
        "then": {"statements": [{"sql": {"postgres": golden}}], "rows": []},
    }
    return Case(path=Path("m-inheritance-999-x.yaml"), raw=raw, model=model)


def test_document_effective_sets_and_canonical_order() -> None:
    family = Family(_document_defs())
    # Canonical sibling-set order is ALPHABETICAL (Invoice < Memo < Receipt), NOT the
    # descriptor's declaration order (Invoice, Receipt, Memo).
    assert family.concrete_descendants("Document") == ["Invoice", "Memo", "Receipt"]
    assert family.effective_concrete_set("FinancialDocument") == ["Invoice", "Receipt"]
    assert family.strategy_of("Document") == "table-per-concrete-subtype"


def test_tpcs_materialize_renames_family_variant_literal() -> None:
    # The DB projects the per-branch literal under `family_variant`; the oracle
    # renames it to `familyVariant` (no raw tag column exists to map).
    case = _document_case("Document")
    invoice_row = {
        "id": 1,
        "title": "Invoice-A",
        "currency": "USD",
        "amount_due": 120,
        "paid_amount": None,
        "body": None,
        "family_variant": "Invoice",
    }
    (out,) = _materialize_family_variant(case, [invoice_row])
    assert "family_variant" not in out
    assert out["familyVariant"] == "Invoice"


def test_tpcs_zero_row_still_asserts_union_shape() -> None:
    # A correct golden over an empty result raises nothing but still runs the shape
    # assertion (row-count-independent, parsed from the golden text).
    case = _document_case("Document")
    assert _materialize_family_variant(case, []) == []


def test_tpcs_wrong_branch_count_is_rejected() -> None:
    # Two branches for a three-concrete abstract root (Memo branch dropped).
    two_branch = " union all ".join(_DOCUMENT_ROOT_UNION.split(" union all ")[:2])
    case = _document_case("Document", two_branch)
    with pytest.raises(CaseFailure, match="union all"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_branch_order_is_rejected() -> None:
    # Swap the first two branches: branch order must be the canonical alphabetical
    # order (Invoice, Memo, Receipt), so a leading Memo branch is rejected.
    parts = _DOCUMENT_ROOT_UNION.split(" union all ")
    swapped = " union all ".join([parts[1], parts[0], parts[2]])
    case = _document_case("Document", swapped)
    with pytest.raises(CaseFailure, match="alphabetical-order"):
        _materialize_family_variant(case, [])


def test_tpcs_missing_superset_column_is_rejected() -> None:
    # Drop `body` from every branch's projection: the stable superset is incomplete.
    golden = _DOCUMENT_ROOT_UNION.replace(", cast(null as varchar(64)) body", "")
    golden = golden.replace(", t0.body", "")
    case = _document_case("Document", golden)
    with pytest.raises(CaseFailure, match="stable superset"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_variant_literal_is_rejected() -> None:
    # A branch whose familyVariant literal is not its concrete subtype name.
    golden = _DOCUMENT_ROOT_UNION.replace("'Memo' family_variant", "'Note' family_variant")
    case = _document_case("Document", golden)
    with pytest.raises(CaseFailure, match="familyVariant literal"):
        _materialize_family_variant(case, [])


def test_tpcs_concrete_target_is_a_noop() -> None:
    # A concrete-target TPCS read (Invoice) is an ordinary single-table read with no
    # familyVariant and no union — the oracle leaves it untouched.
    case = _document_case("Invoice", "select t0.id, t0.amount_due from invoice t0")
    rows = [{"id": 1, "amount_due": 120}]
    assert _materialize_family_variant(case, rows) == rows


def test_tpcs_narrow_to_multiple_concretes_shape() -> None:
    # A narrow to [Invoice, Memo] lowers to a two-branch union in alphabetical order
    # (Invoice, Memo); the oracle recomputes the shape from the narrow's effective set.
    golden = (
        "select t0.id, t0.title, t0.folder_id, t0.currency, t0.amount_due, "
        "cast(null as varchar(64)) body, 'Invoice' family_variant from invoice t0 "
        "union all "
        "select t0.id, t0.title, t0.folder_id, cast(null as varchar(3)) currency, "
        "cast(null as decimal(18, 2)) amount_due, t0.body, 'Memo' family_variant "
        "from memo t0"
    )
    case = _document_case("Document", golden, narrowTo=["Invoice", "Memo"])
    memo_row = {
        "id": 1,
        "title": "Memo-A",
        "currency": None,
        "amount_due": None,
        "body": "Reminder",
        "family_variant": "Memo",
    }
    (out,) = _materialize_family_variant(case, [memo_row])
    assert out["familyVariant"] == "Memo"


# --- union-all validation ------------------------------------------------------
#
# The branch walk accepts only `union all`, so a golden
# using a de-duplicating plain `union` (or `intersect`) passed the shape check.
# The shape check validates output NAMES, the trailing literal, and
# the per-column cast SHAPE, so a bare `null <col>` or a wrong-typed cast passed.
# The per-column cast type is asserted per dialect (Postgres `varchar` /
# MariaDB `char`). A real column colliding with the synthetic
# `family_variant` alias is rejected. All reproduce-then-green.


def test_tpcs_plain_union_is_rejected() -> None:
    # First arm is a de-duplicating `union`, not `union all` — the oracle must reject it.
    plain = _DOCUMENT_ROOT_UNION.replace(" union all ", " union ", 1)
    case = _document_case("Document", plain)
    with pytest.raises(CaseFailure, match="union all"):
        _materialize_family_variant(case, [])


def test_tpcs_bare_null_placeholder_no_cast_is_rejected() -> None:
    # A non-applicable column projected as a bare `null` (no cast) gives the union an
    # untyped column; the placeholder MUST be `cast(null as <type>)`.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "cast(null as decimal(18, 2)) paid_amount", "null paid_amount"
    )
    case = _document_case("Document", golden)
    with pytest.raises(CaseFailure, match="cast"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_typed_placeholder_cast_is_rejected() -> None:
    # A non-applicable decimal column cast to a string type — same output name, wrong type.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "cast(null as decimal(18, 2)) paid_amount", "cast(null as varchar(9)) paid_amount"
    )
    case = _document_case("Document", golden)
    with pytest.raises(CaseFailure, match="declared type"):
        _materialize_family_variant(case, [])


def test_tpcs_applicable_column_projected_as_null_is_rejected() -> None:
    # Invoice's own `amount_due` projected as a NULL placeholder rather than the real
    # column reference — an applicable column MUST be a real reference.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "t0.amount_due,", "cast(null as decimal(18, 2)) amount_due,", 1
    )
    case = _document_case("Document", golden)
    with pytest.raises(CaseFailure, match="APPLICABLE"):
        _materialize_family_variant(case, [])


# The MariaDB abstract-root golden: bounded strings cast to `char`, decimals identical.
_DOCUMENT_ROOT_UNION_MARIADB = _DOCUMENT_ROOT_UNION.replace("varchar(64)", "char(64)").replace(
    "varchar(3)", "char(3)"
)


def test_tpcs_mariadb_char_cast_golden_is_accepted() -> None:
    case = _document_case("Document")
    case.raw["then"]["statements"][0]["sql"]["mariadb"] = _DOCUMENT_ROOT_UNION_MARIADB
    assert _materialize_family_variant(case, []) == []


def test_tpcs_mariadb_varchar_cast_golden_is_rejected() -> None:
    # A MariaDB golden that used `varchar` (a Postgres-only CAST target) is rejected by
    # the per-dialect cast-type check.
    bad_mariadb = _DOCUMENT_ROOT_UNION.replace("varchar(64)", "char(64)")  # leaves varchar(3)
    case = _document_case("Document")
    case.raw["then"]["statements"][0]["sql"] = {"mariadb": bad_mariadb}
    with pytest.raises(CaseFailure, match="declared type"):
        _materialize_family_variant(case, [])


def test_tpcs_family_variant_column_requires_a_hygienic_internal_alias() -> None:
    case = copy.deepcopy(_document_case("Document"))
    for definition in case.model.entity_defs:
        if definition["name"] == "Memo":
            definition["attributes"].append(
                {"name": "familyVariant", "type": "string", "column": "family_variant"}
            )
    with pytest.raises(CaseFailure, match="parallax_attr_0"):
        _materialize_family_variant(case, [])


# --- polymorphic navigation + narrowed deep-fetch view keys -------------------
#
# The relationship-target narrowing (resolved Q10) and the deterministic narrowed
# view key `<rel>[<Concrete>,<Concrete>]` (m-deep-fetch), derived from the descriptor
# alone.

from reference_harness.inheritance import (  # noqa: E402
    NARROW_OUTSIDE_RELATIONSHIP_TARGET,
    narrowed_view_key,
    resolve_clamped_narrow,
    resolve_hop_effective_set,
    resolve_root_source_set,
)


def _person_op(rel: str, to: list[str]) -> dict[str, Any]:
    return {
        "exists": {
            "rel": rel,
            "op": {"narrow": {"to": to, "operand": {"all": {}}}},
        }
    }


def test_relationship_target_resolution() -> None:
    family = Family(_animal_defs())
    assert family.relationship_target("Person.pets") == "parallax.compatibility.Pet"
    assert family.relationship_target("Person.animals") == "parallax.compatibility.Animal"
    assert family.relationship_target("Person.missing") is None


def test_relationship_target_preserves_qualified_duplicate_local_identity() -> None:
    defs = [
        {
            "name": "Owner",
            "namespace": "catalog",
            "relationships": [
                {
                    "name": "entry",
                    "join": {"target": {"entity": "archive.Entry", "attribute": "id"}},
                }
            ],
        },
        {"name": "Entry", "namespace": "archive"},
        {"name": "Entry", "namespace": "catalog"},
    ]
    assert Family(defs).relationship_target("catalog.Owner.entry") == "archive.Entry"


def test_narrowed_view_key_is_canonical_ordered_and_spaceless() -> None:
    family = Family(_animal_defs())
    # Equivalent authored spellings converge on ONE key, in canonical alphabetical
    # order (Cat before Dog), independent of the authored `to` spelling.
    assert narrowed_view_key(family, "Person.pets", ["Cat", "Dog"]) == "pets[Cat,Dog]"
    assert narrowed_view_key(family, "Person.pets", ["Dog"]) == "pets[Dog]"
    assert narrowed_view_key(family, "Person.pets", ["Cat"]) == "pets[Cat]"


def test_resolve_hop_effective_set_broad_and_narrowed() -> None:
    family = Family(_animal_defs())
    # Broad hop: the relationship target's own effective set, canonically (alphabetically) ordered.
    assert resolve_hop_effective_set(family, "Person.pets", None) == (["Cat", "Dog"], False)
    assert resolve_hop_effective_set(family, "Person.animals", None) == (
        ["Cat", "Dog", "WildBoar"],
        False,
    )
    # Narrowed hops: equivalent spellings converge; a single concrete stays singular.
    assert resolve_hop_effective_set(family, "Person.pets", ["Pet"]) == (["Cat", "Dog"], True)
    assert resolve_hop_effective_set(family, "Person.pets", ["Cat", "Dog"]) == (
        ["Cat", "Dog"],
        True,
    )
    assert resolve_hop_effective_set(family, "Person.pets", ["Dog"]) == (["Dog"], True)


def test_hop_key_separates_a_broad_hop_from_a_redundant_narrow() -> None:
    # `Person.pets` targets Pet, whose effective concrete set is exactly {Cat, Dog},
    # so `narrowTo: [Pet]` is REDUNDANT: it resolves to the very set the broad
    # hop already reaches. The two hops nonetheless stay distinct, because a
    # segment's view key is derived from whether a narrow was AUTHORED — `pets`
    # versus `pets[Cat,Dog]` — so hop identity must carry that flag and cannot key
    # on the resolved set alone (m-deep-fetch, case m-inheritance-068).
    family = Family(_animal_defs())
    broad_set, broad_narrowed = resolve_hop_effective_set(family, "Person.pets", None)
    redundant_set, redundant_narrowed = resolve_hop_effective_set(family, "Person.pets", ["Pet"])
    assert broad_set == redundant_set == ["Cat", "Dog"]
    assert (broad_narrowed, redundant_narrowed) == (False, True)

    broad_key = _segment_key(family, {"rel": "Person.pets"})
    redundant_key = _segment_key(family, {"rel": "Person.pets", "narrowTo": ["Pet"]})
    assert broad_key != redundant_key
    assert narrowed_view_key(family, "Person.pets", redundant_set) == "pets[Cat,Dog]"

    # Two AUTHORED narrows resolving to that same set still converge on one hop —
    # dedup of equivalent spellings applies between two narrowed hops only.
    equivalent = _segment_key(family, {"rel": "Person.pets", "narrowTo": ["Cat", "Dog"]})
    assert equivalent == redundant_key


def _segment_key(
    family: Family, segment: dict[str, Any], root_source: tuple[str, ...] | None = None
) -> Any:
    return _resolve_hop(family, segment, parent=None, root_source=root_source).key


def test_hop_key_separates_two_branches_reaching_one_relationship() -> None:
    # One relationship reached from two DIFFERENT parents is two hops: each gathers
    # its keys from its own branch's rows, so they can neither share a statement nor
    # share a bucket of fetched children (m-deep-fetch branch provenance).
    family = Family(_animal_defs())
    dog_branch = _segment_key(family, {"rel": "Animal.owner"}, ("Dog",))
    boar_branch = _segment_key(family, {"rel": "Animal.owner"}, ("WildBoar",))
    under_dog = _resolve_hop(
        family, {"rel": "Person.pets"}, parent=dog_branch, root_source=None
    ).key
    under_boar = _resolve_hop(
        family, {"rel": "Person.pets"}, parent=boar_branch, root_source=None
    ).key
    assert under_dog != under_boar
    # A shared prefix still folds: the same relationship under the same parent is one
    # hop however many paths walk into it.
    assert (
        _resolve_hop(family, {"rel": "Person.pets"}, parent=dog_branch, root_source=None).key
        == under_dog
    )


def test_root_source_set_resolves_a_guard_against_the_queried_position() -> None:
    family = Family(_animal_defs())
    # An unguarded path starts from the whole queried position, canonically ordered.
    assert resolve_root_source_set(family, "Animal", {}) == ("Cat", "Dog", "WildBoar")
    # A guard resolves to its own effective set — equivalent spellings converge on
    # the SAME tuple, which is what makes them one hop at the root position.
    pet_guard = {"appliesTo": ["Pet"]}
    concrete_guard = {"appliesTo": ["Cat", "Dog"]}
    assert resolve_root_source_set(family, "Animal", pet_guard) == ("Cat", "Dog")
    assert resolve_root_source_set(family, "Animal", concrete_guard) == ("Cat", "Dog")
    # A non-polymorphic queried position has no source set to distinguish hops by.
    assert resolve_root_source_set(family, "Person", {}) is None


def test_root_hop_identity_keys_on_the_resolved_source_set() -> None:
    # The four relations two guards can stand in, all measured through the hop key
    # (m-deep-fetch "Path-root guards"). The root component keys on the RESOLVED
    # source set — deliberately unlike the segment component, which keys on whether
    # a narrow was AUTHORED — so a guard admitting every root object collapses onto
    # the broad path and every proper guard separates from it automatically.
    family = Family(_animal_defs())

    def key(path: dict[str, Any]) -> Any:
        return _segment_key(
            family, {"rel": "Animal.owner"}, resolve_root_source_set(family, "Animal", path)
        )

    broad = key({})
    pet_guard = key({"appliesTo": ["Pet"]})
    concrete_guard = key({"appliesTo": ["Cat", "Dog"]})
    dog_guard = key({"appliesTo": ["Dog"]})
    cat_guard = key({"appliesTo": ["Cat"]})
    boar_dog_guard = key({"appliesTo": ["Dog", "WildBoar"]})
    whole_guard = key({"appliesTo": ["Animal"]})

    assert pet_guard == concrete_guard  # equal / equivalent -> one hop
    assert dog_guard != cat_guard  # disjoint -> two hops
    assert boar_dog_guard != pet_guard  # overlapping (shares Dog, neither nests) -> two hops
    assert dog_guard != pet_guard  # containment (a guard inside a guard) -> two hops
    assert dog_guard != broad  # containment (a guard inside broad) -> two hops
    assert whole_guard == broad  # a full-set guard IS the broad path


def test_root_guard_outside_the_queried_position_is_rejected() -> None:
    family = Family(_animal_defs())
    # A guard is clamped to the queried position exactly as result narrowing is:
    # WildBoar is outside a read already narrowed to Pet's concretes.
    with pytest.raises(RejectionError) as exc:
        resolve_clamped_narrow(family, ["Cat", "Dog"], ["WildBoar"])
    assert exc.value.rule == NARROW_OUTSIDE_POSITION
    # An abstract subtype with no concrete descendants resolves to nothing, which
    # is the guard's own rejection rather than a position violation.
    childless = [
        {"name": "Root", "table": "root", "inheritance": {"role": "root", "tag": {"column": "k"}}},
        {"name": "Empty", "inheritance": {"role": "abstract-subtype", "parent": "Root"}},
        {
            "name": "Real",
            "inheritance": {"role": "concrete-subtype", "parent": "Root", "tagValue": "real"},
        },
    ]
    with pytest.raises(RejectionError) as empty:
        resolve_clamped_narrow(Family(childless), ["Real"], ["Empty"])
    assert empty.value.rule == NARROW_EMPTY_EFFECTIVE_SET


def test_resolve_hop_outside_relationship_target_is_rejected() -> None:
    family = Family(_animal_defs())
    # WildBoar shares the family root but is a SIBLING of Pet — not reachable via pets.
    with pytest.raises(RejectionError) as exc:
        resolve_hop_effective_set(family, "Person.pets", ["WildBoar"])
    assert exc.value.rule == NARROW_OUTSIDE_RELATIONSHIP_TARGET


def test_operation_narrow_in_navigation_filter_accepts_valid() -> None:
    defs = _animal_defs()
    # narrow the pets target (Pet) to [Cat] — valid; animals (Animal) to [Pet] — valid.
    _judge(defs, "Person", predicate=_person_op("Person.pets", ["Cat"]))
    _judge(defs, "Person", predicate=_person_op("Person.animals", ["Pet"]))


def test_operation_narrow_in_navigation_filter_rejects_outside_target() -> None:
    defs = _animal_defs()
    with pytest.raises(RejectionError) as exc:
        _judge(defs, "Person", predicate=_person_op("Person.pets", ["WildBoar"]))
    assert exc.value.rule == NARROW_OUTSIDE_RELATIONSHIP_TARGET


def test_empty_selection_in_navigation_filter_keeps_the_shared_empty_rule() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(_animal_defs(), "Person", predicate=_person_op("Person.pets", ["Bogus"]))
    assert exc.value.rule == NARROW_EMPTY_EFFECTIVE_SET


def _include(rel: str, to: list[str] | None) -> list[dict[str, Any]]:
    segment: dict[str, Any] = {"rel": rel}
    if to is not None:
        segment["narrowTo"] = to
    return [{"segments": [segment]}]


def test_include_segment_narrowing_is_resolved_through_the_path_object() -> None:
    # A path is a closed object carrying its hops under `segments`, so the position
    # walk reaches a segment's narrowing only through that member. A hop narrowed
    # outside the relationship target is rejected exactly as it is in a navigation
    # filter.
    defs = _animal_defs()
    _judge(defs, "Person", includes=_include("Person.pets", ["Dog"]))
    _judge(defs, "Person", includes=_include("Person.pets", None))
    with pytest.raises(RejectionError) as exc:
        _judge(defs, "Person", includes=_include("Person.pets", ["WildBoar"]))
    assert exc.value.rule == NARROW_OUTSIDE_RELATIONSHIP_TARGET


def test_empty_include_segment_selection_keeps_the_shared_empty_rule() -> None:
    with pytest.raises(RejectionError) as exc:
        _judge(_animal_defs(), "Person", includes=_include("Person.pets", ["Bogus"]))
    assert exc.value.rule == NARROW_EMPTY_EFFECTIVE_SET
