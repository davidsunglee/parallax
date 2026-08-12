"""Model-aware Predicate validation unit tests (m-predicate / m-navigate /
m-value-object).

Each rejected rule is pinned with the exact identifier `validate_operation`
raises, alongside the representative VALID operations that must NOT be
rejected — including the corpus boundary case (an equivalent-spelling narrow
that is NOT outside the active position). The 21 in-slice rejected corpus
cases are additionally round-tripped through the real validator here (not
just via the engine's rejected sweep), so a regression in either the node
construction or the model resolution fails at the unit layer first.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from _corpus_model_support import formed, records

from parallax.conformance import case_format
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query import (
    AsOf,
    History,
    IncludePath,
    IncludeSegment,
    OrderKey,
    TemporalDimension,
    TemporalSelection,
    object_query,
    query_entities,
    validate_object_query,
)
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.predicate import (
    All,
    And,
    Between,
    Comparison,
    Exists,
    Group,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NestedRange,
    NestedStringMatch,
    NestedStringOp,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    OperationRejectedError,
    Or,
    PredicateNode,
    Scalar,
    StringMatch,
    validate_operation,
)
from parallax.descriptor._records import (
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)


def test_query_entities_collects_every_class_the_query_names() -> None:
    # The reachable-closure seed the Entity frontend forms its early-validation
    # model from: the queried target, the `Class` prefix of every attribute /
    # nested-path / relationship reference, plus every Subtype Selection
    # alternative and every Sort Key, over every clause and combinator.
    query = object_query(
        EntityIdentity(None, "Root"),
        And(
            operands=(
                Not(
                    operand=Group(
                        operand=Or(
                            operands=(
                                Comparison(op="eq", attr="Animal.name", value="x"),
                                Between(attr="Dog.barkVolume", lower=1, upper=3),
                                NullCheck(op="isNull", attr="Cat.whisker"),
                                StringMatch(op="like", attr="Pet.tag", value="p"),
                                Membership(op="in", attr="WildBoar.id", values=(1,)),
                            )
                        )
                    )
                ),
                Narrow(to=("Dog", "Cat"), operand=All()),
                Navigate(
                    rel="Person.pets",
                    op=NestedComparison(op="nestedEq", path="Pet.spec.n", value="v"),
                ),
                Exists(rel="Owner.kennels", op=None),
                NotExists(rel="Kennel.owners", op=None),
                NestedMembership(op="nestedIn", path="Order.address.zip", values=("1",)),
                NestedNullCheck(op="nestedIsNull", path="Item.meta.flag"),
                NestedExists(path="Status.tags", where=None),
                NestedNotExists(path="Status.notes", where=None),
                NoneOp(),
            )
        ),
        narrow_to=("Narrowed",),
        temporal={"valid-time": AsOf("latest")},
        order_by=(OrderKey(attr="Sorted.rank"),),
        includes=(
            IncludePath(
                segments=(IncludeSegment(rel="Root.leaves", narrow_to=("Leaf",)),),
                applies_to=("Branch",),
            ),
        ),
    )
    assert query_entities(query) == frozenset(
        {
            "Animal",
            "Dog",
            "Cat",
            "Pet",
            "WildBoar",
            "Person",
            "Owner",
            "Kennel",
            "Order",
            "Item",
            "Status",
            "Root",
            "Leaf",
            "Branch",
            "Sorted",
            "Narrowed",
        }
    )


_MODEL_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"
_ANIMAL = records("animal")
_BALANCE = records("balance")
_CONTACT = records("contact")
_CUSTOMER = records("customer")
_ORDERS = records("orders")
_POSITION = records("position")
_SHARED_LOCAL_NAME = records("shared-local-name")
_MODEL_BY_FILE: Mapping[str, Metamodel] = {
    "animal.yaml": _ANIMAL,
    "contact.yaml": _CONTACT,
    "customer.yaml": _CUSTOMER,
    "orders.yaml": _ORDERS,
    "shared-local-name.yaml": _SHARED_LOCAL_NAME,
}
# The animal family plus one abstract subtype with no concrete descendants — the
# only way a `to` list resolves to the empty set.
_ANIMAL_WITH_A_CHILDLESS_SUBTYPE = Metamodel(
    entities=(
        *_ANIMAL.entities,
        Entity(
            name="Ghost",
            namespace="parallax.compatibility",
            inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        ),
    )
)


def _validate(target: str, op: PredicateNode, meta: Metamodel) -> None:
    """Form ``meta`` into an accepted model, resolve ``target`` to its accepted
    root Metadata, and run the model-aware validator over ``op``."""
    model = formed(meta)
    validate_operation(_root(model, target), op, model)


def _root(model: object, target: str) -> Any:
    return next(
        entity
        for entity in cast("Any", model).entities
        if target in (entity.identity.name, entity.identity.canonical)
    )


def _validate_query(target: str, meta: Metamodel, **clauses: Any) -> None:
    """Run the model-aware Object Query validator over one query's clauses."""
    model = formed(meta)
    root = _root(model, target)
    predicate = clauses.pop("predicate", All())
    validate_object_query(root, object_query(root.identity, predicate, **clauses), model)


def _query_rejects(target: str, meta: Metamodel, **clauses: Any) -> OperationRejectedError:
    with pytest.raises(OperationRejectedError) as excinfo:
        _validate_query(target, meta, **clauses)
    return excinfo.value


def _rejects(op: PredicateNode, meta: Metamodel, target: str) -> OperationRejectedError:
    with pytest.raises(OperationRejectedError) as excinfo:
        _validate(target, op, meta)
    return excinfo.value


# --------------------------------------------------------------------------- #
# temporal-read-dimension-selection-cardinality (m-temporal-read).            #
# --------------------------------------------------------------------------- #
def test_temporal_read_requires_one_selection_per_declared_dimension() -> None:
    missing = _query_rejects("Balance", _BALANCE)
    assert missing.rule == "temporal-read-dimension-selection-cardinality"
    only_valid: dict[TemporalDimension, TemporalSelection] = {"valid-time": AsOf("latest")}
    partial = _query_rejects("Position", _POSITION, temporal=only_valid)
    assert partial.rule == "temporal-read-dimension-selection-cardinality"


def test_temporal_read_accepts_complete_explicit_selections() -> None:
    _validate_query("Balance", _BALANCE, temporal={"transaction-time": AsOf("latest")})
    both: dict[TemporalDimension, TemporalSelection] = {
        "transaction-time": AsOf("latest"),
        "valid-time": AsOf("latest"),
    }
    _validate_query("Position", _POSITION, temporal=both)


def test_temporal_read_rejects_an_undeclared_dimension() -> None:
    # A dimension is keyed once by construction, so the only cardinality defect a
    # canonical query can still carry is naming one the target does not declare.
    undeclared: dict[TemporalDimension, TemporalSelection] = {
        "transaction-time": History(),
        "valid-time": AsOf("latest"),
    }
    exc = _query_rejects("Balance", _BALANCE, temporal=undeclared)
    assert exc.rule == "temporal-read-dimension-selection-cardinality"


# --------------------------------------------------------------------------- #
# The 21 in-slice rejected corpus cases, round-tripped end to end.            #
# --------------------------------------------------------------------------- #
_REJECTED_CASE_IDS = (
    "m-inheritance-040",
    "m-inheritance-041",
    "m-inheritance-042",
    "m-inheritance-064",
    "m-inheritance-132",
    "m-inheritance-133",
    "m-op-algebra-039",
    "m-op-algebra-040",
    "m-op-algebra-041",
    "m-op-algebra-042",
    "m-op-algebra-043",
    "m-op-algebra-044",
    "m-op-algebra-045",
    "m-op-algebra-046",
    "m-op-algebra-047",
    "m-op-algebra-048",
    "m-op-algebra-049",
    "m-value-object-034",
    "m-value-object-035",
    "m-value-object-036",
    "m-value-object-038",
)


def _load_rejected_case(case_id: str) -> case_format.Case:
    (path,) = Path(case_format.default_cases_dir()).glob(f"{case_id}-*.yaml")
    return case_format.load_case(path)


@pytest.mark.parametrize("case_id", _REJECTED_CASE_IDS)
def test_corpus_rejected_case_classifies_to_its_own_rejected_rule(case_id: str) -> None:
    case = _load_rejected_case(case_id)
    when = cast("Mapping[str, Any]", case.document["when"])
    then = cast("Mapping[str, Any]", case.document["then"])
    meta = _MODEL_BY_FILE[Path(case.model).name]
    query = deserialize_query(cast("Mapping[str, object]", when["objectQuery"]))
    model = formed(meta)
    root = _root(model, query.target.canonical)
    with pytest.raises(OperationRejectedError) as excinfo:
        validate_object_query(root, query, model)
    assert excinfo.value.rule == then["rejectedRule"]


# --------------------------------------------------------------------------- #
# between-bounds-inverted (m-predicate "Bound-ordering rule").               #
# --------------------------------------------------------------------------- #
def _between(lower: Scalar, upper: Scalar) -> Between:
    return Between(attr="Order.price", lower=lower, upper=upper)


@pytest.mark.parametrize(
    ("lower", "upper"),
    [(50.75, 20.00), (5, 1), ("2024-05-01", "2024-02-01"), ("b", "a")],
)
def test_between_with_inverted_same_kind_bounds_rejects(lower: Scalar, upper: Scalar) -> None:
    exc = _rejects(_between(lower, upper), _ORDERS, "Order")
    assert exc.rule == "between-bounds-inverted"


@pytest.mark.parametrize(
    ("lower", "upper"),
    [
        (20.00, 50.75),
        (5, 5),
        ("a", "a"),
        ("2024-02-01", "2024-05-01"),
        (5, "1"),
        ("5", 1),
        (None, 1),
        (5, None),
        (True, False),
    ],
)
def test_between_bounds_the_rule_stands_aside_for_accept(lower: Scalar, upper: Scalar) -> None:
    # Ordered and equal same-kind bounds are legal ranges; a mixed-kind pair, a null
    # bound, and a boolean pair are all skipped rather than guessed — the comparison
    # is by literal kind, so a bool is never read as the number 1 or 0.
    _validate("Order", _between(lower, upper), _ORDERS)


def test_between_bound_ordering_is_checked_wherever_the_node_sits() -> None:
    op = And(operands=(All(), Not(operand=_between(50.75, 20.00))))
    exc = _rejects(op, _ORDERS, "Order")
    assert exc.rule == "between-bounds-inverted"


def test_between_subject_is_resolved_before_its_bounds_are_ordered() -> None:
    # A value-object-rooted range names the root misuse rather than blaming its
    # (also inverted) bounds.
    op = Between(attr="address.city", lower="b", upper="a")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def _nested_range_scopes(
    lower: Scalar, upper: Scalar, *, path: str, element: str
) -> tuple[PredicateNode, PredicateNode]:
    """The same range, once path-scoped and once element-scoped, so a rule can be
    asserted at both scopes from one expectation."""
    return (
        NestedRange(path=path, lower=lower, upper=upper),
        NestedExists(
            path="Customer.address.phones",
            where=NestedRange(path=element, lower=lower, upper=upper),
        ),
    )


def test_nested_range_inverted_bounds_reject_in_both_scopes() -> None:
    # The nested ranges reuse the shared bound-ordering rule rather than restating
    # the literal-kind logic, so both scopes classify identically to top-level
    # `between`.
    numeric, _ = _nested_range_scopes(
        12, 5, path="Customer.address.geo.elevation", element="number"
    )
    _, textual = _nested_range_scopes("work", "home", path="Customer.address.city", element="type")
    for op in (numeric, textual):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "between-bounds-inverted"


def test_nested_range_typed_bounds_are_checked_before_the_ordering_in_both_scopes() -> None:
    # Both bounds mistype a `string` leaf AND are inverted as raw numbers. Ordering
    # first would report `between-bounds-inverted` and blame the ordering for what is
    # really the bounds' types, so this pins the order the two checks run in.
    for op in _nested_range_scopes(42, 7, path="Customer.address.city", element="type"):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "nested-literal-type-mismatch"


def test_nested_range_ordered_typed_bounds_accept_in_both_scopes() -> None:
    _validate(
        "Customer",
        NestedRange(path="Customer.address.geo.elevation", lower=5, upper=12),
        _CUSTOMER,
    )
    _validate(
        "Customer",
        NestedExists(
            path="Customer.address.phones",
            where=NestedRange(path="number", lower="555-9000", upper="555-9999"),
        ),
        _CUSTOMER,
    )


def test_nested_range_unknown_path_rejects_before_any_bound_check() -> None:
    op = NestedRange(path="Customer.address.bogus", lower=12, upper=5)
    assert _rejects(op, _CUSTOMER, "Customer").rule == "nested-path-unknown-member"


def test_nested_negated_membership_type_checks_its_values_in_both_scopes() -> None:
    flat = NestedMembership(op="nestedNotIn", path="Customer.address.city", values=("Oslo", 42))
    scoped = NestedExists(
        path="Customer.address.phones",
        where=NestedMembership(op="nestedNotIn", path="type", values=(42,)),
    )
    for op in (flat, scoped):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "nested-literal-type-mismatch"
    _validate(
        "Customer",
        NestedMembership(op="nestedNotIn", path="Customer.address.city", values=("Oslo",)),
        _CUSTOMER,
    )


# --------------------------------------------------------------------------- #
# narrow-outside-position / narrow-empty-effective-set                       #
# (m-predicate "the four-step validation rule").                            #
# --------------------------------------------------------------------------- #
def test_narrow_broadening_past_position_rejects() -> None:
    op = Narrow(to=("Person",), operand=All())
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_nested_narrow_cannot_broaden_back_out_of_the_enclosing_narrow() -> None:
    op = Narrow(
        to=("Dog",),
        operand=Narrow(to=("Cat",), operand=All()),
    )
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_narrow_within_position_accepts() -> None:
    op = Narrow(to=("Dog",), operand=All())
    _validate("Animal", op, _ANIMAL)  # no raise


def test_equivalent_narrow_spelling_is_not_outside_position() -> None:
    # `to=[Pet]` and `to=[Cat, Dog]` resolve to the SAME effective set — both are
    # valid, non-broadening selections of the Animal root.
    _validate("Animal", Narrow(to=("Pet",), operand=All()), _ANIMAL)
    _validate("Animal", Narrow(to=("Cat", "Dog"), operand=All()), _ANIMAL)


def test_subtype_selection_rejects_an_exact_duplicate() -> None:
    exc = _rejects(Narrow(to=("Dog", "Dog"), operand=All()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-duplicate-alternative"


def test_subtype_selection_rejects_overlapping_alternatives() -> None:
    exc = _rejects(Narrow(to=("Dog", "Pet"), operand=All()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-overlapping-alternatives"


def test_subtype_selection_checks_exact_duplicates_before_overlap() -> None:
    exc = _rejects(Narrow(to=("Pet", "Dog", "Dog"), operand=All()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-duplicate-alternative"


def test_redundant_self_narrow_is_valid() -> None:
    # Narrowing a position to itself is a documented no-op, not a rejection.
    _validate("Pet", Narrow(to=("Pet",), operand=All()), _ANIMAL)


def test_narrow_empty_effective_set_rejects() -> None:
    # An abstract subtype with NO concrete descendants: `to` resolves to the empty
    # concrete-subtype set. The childless subtype must sit in a family that DOES
    # compose a concrete elsewhere — a family composing none of them never forms
    # (`inheritance-missing-concrete-subtype`), so the operation rule is reached
    # only through this shape.
    op = Narrow(to=("Ghost",), operand=All())
    exc = _rejects(op, _ANIMAL_WITH_A_CHILDLESS_SUBTYPE, "Animal")
    assert exc.rule == "narrow-empty-effective-set"


def test_a_narrow_to_a_name_the_model_does_not_declare_resolves_to_nothing() -> None:
    # A `to` entry naming NO Entity contributes nothing and leaves the resolved set
    # empty, which the narrow rules classify. Only a spelling naming MORE than one
    # Entity is named as a resolution failure of its own.
    op = Narrow(to=("Bogus",), operand=All())
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-empty-effective-set"


# --------------------------------------------------------------------------- #
# subtype-attribute-outside-narrow-scope.                                    #
# --------------------------------------------------------------------------- #
def test_subtype_attribute_outside_narrow_scope_rejects() -> None:
    op = Comparison(op="greaterThan", attr="Dog.barkVolume", value=5)
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_subtype_attribute_within_narrow_scope_accepts() -> None:
    op = Narrow(
        to=("Dog",),
        operand=Comparison(op="greaterThan", attr="Dog.barkVolume", value=3),
    )
    _validate("Animal", op, _ANIMAL)  # no raise


def test_root_declared_attribute_needs_no_narrow() -> None:
    _validate("Animal", Comparison(op="eq", attr="Animal.name", value="Rex"), _ANIMAL)


def test_an_ancestors_attribute_is_addressable_from_a_descendant_position() -> None:
    # The contravariant half the family rule keeps: an ancestor's member applies to
    # every concrete under it, so it applies at a narrower position too.
    _validate("Dog", Comparison(op="eq", attr="Animal.name", value="Rex"), _ANIMAL)


@pytest.mark.parametrize(
    "op",
    [
        Comparison(op="eq", attr="Dog.name", value="Rex"),
        Comparison(op="eq", attr="Pet.licenseId", value="L-1"),
        Narrow(
            to=("Dog",),
            operand=Comparison(op="eq", attr="Cat.name", value="Tom"),
        ),
    ],
    ids=("predicate", "abstract-subtype", "disjoint-sibling"),
)
def test_the_position_is_measured_against_the_entity_a_reference_names(op: PredicateNode) -> None:
    # `m-predicate`: "the active position's effective set is a subset of the
    # REFERENCED Entity's" — not the ancestor's that declares the member. `name` is
    # declared on Animal, so measuring the declaring entity would accept `Dog.name`
    # at the root position and, worse, accept `Cat.name` inside a narrow to Dog,
    # where the reference addresses no row the position contains. Pinned by
    # m-op-algebra-049.
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_a_subtype_spelling_is_in_scope_once_the_position_is_narrowed_to_it() -> None:
    # The remedy the rule names: narrowing to Dog makes `Dog.name` applicable, which
    # is what keeps the rejection above `subtype-attribute-outside-narrow-scope`
    # rather than the non-family rule.
    op = Narrow(to=("Dog",), operand=Comparison(op="eq", attr="Dog.name", value="Rex"))
    _validate("Animal", op, _ANIMAL)


# --------------------------------------------------------------------------- #
# attribute-outside-active-position — the non-family half of the same rule.   #
# --------------------------------------------------------------------------- #
def test_an_unrelated_entitys_attribute_is_outside_the_active_position() -> None:
    # The read is positioned at `Order` and the predicate names `OrderItem.id`.
    # Both entities declare an `id`, so a lowering that keeps only the reference's
    # local part would emit `t0.id = ?` and silently answer a different question —
    # on a predicate-selected write, against different rows. The two share no
    # inheritance family, so no narrow is a remedy and the narrow-scope rule would
    # name one that does not exist.
    op = Comparison(op="eq", attr="OrderItem.id", value=1)
    exc = _rejects(op, _ORDERS, "Order")
    assert exc.rule == "attribute-outside-active-position"


def test_a_sibling_familys_attribute_is_outside_the_active_position() -> None:
    # Neither entity is standalone: `Person` is a plain entity and the position is
    # the whole animal family. The split is by FAMILY membership, not by whether
    # either side happens to participate in inheritance at all.
    op = Comparison(op="eq", attr="Person.name", value="Ada")
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "attribute-outside-active-position"


def test_the_related_entity_is_the_active_position_inside_a_navigation_filter() -> None:
    # The hop re-roots the position at the relationship target, so a reference that
    # is foreign at the queried position is native inside the filter.
    op = Exists(rel="Person.pets", op=Comparison(op="eq", attr="Animal.name", value="Rex"))
    _validate("Person", op, _ANIMAL)


# --------------------------------------------------------------------------- #
# narrow-outside-relationship-target (m-navigate).                           #
# --------------------------------------------------------------------------- #
def test_narrow_to_outside_relationship_target_rejects() -> None:
    op = Exists(rel="Person.pets", op=Narrow(to=("WildBoar",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_empty_narrow_inside_relationship_target_keeps_the_shared_empty_rule() -> None:
    op = Exists(rel="Person.pets", op=Narrow(to=("Bogus",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-empty-effective-set"


def test_narrow_within_relationship_target_accepts() -> None:
    op = Exists(
        rel="Person.pets",
        op=Narrow(
            to=("parallax.compatibility.Dog",),
            operand=All(),
        ),
    )
    _validate("Person", op, _ANIMAL)  # no raise


def test_navigate_with_no_inner_operation_accepts() -> None:
    _validate("Person", Navigate(rel="Person.pets"), _ANIMAL)


def test_not_exists_relationship_target_scope_propagates() -> None:
    op = NotExists(rel="Person.pets", op=Narrow(to=("WildBoar",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def _hop(narrow_to: tuple[str, ...] = ()) -> tuple[IncludePath, ...]:
    return (IncludePath(segments=(IncludeSegment(rel="Person.pets", narrow_to=narrow_to),)),)


def test_include_segment_narrow_outside_relationship_target_rejects() -> None:
    exc = _query_rejects("Person", _ANIMAL, includes=_hop(("WildBoar",)))
    assert exc.rule == "narrow-outside-relationship-target"


def test_include_segment_narrow_within_relationship_target_accepts() -> None:
    _validate_query("Person", _ANIMAL, includes=_hop(("Dog",)))  # no raise


def test_empty_include_segment_narrow_keeps_the_shared_empty_rule() -> None:
    exc = _query_rejects("Person", _ANIMAL, includes=_hop(("Bogus",)))
    assert exc.rule == "narrow-empty-effective-set"


def _guarded(applies_to: tuple[str, ...] | None) -> tuple[IncludePath, ...]:
    return (
        IncludePath(
            segments=(IncludeSegment(rel="Animal.owner"),),
            applies_to=applies_to,
        ),
    )


def test_include_source_guard_within_the_queried_position_accepts() -> None:
    # The SOURCE guard is governed by the four-step same-position rule, not by the
    # relationship-target rule its segments follow: it names the queried position
    # and may resolve anywhere inside it, including redundantly to all of it.
    for guard in (("Dog",), ("Pet",), ("Animal",)):
        _validate_query("Animal", _ANIMAL, includes=_guarded(guard))


def test_include_source_guard_broadening_past_the_position_rejects() -> None:
    # Read of the abstract subtype Pet, guard reaching the sibling branch: the
    # queried position supplies the active position, so WildBoar is outside it.
    exc = _query_rejects("Pet", _ANIMAL, includes=_guarded(("WildBoar",)))
    assert exc.rule == "narrow-outside-position"


def test_include_source_guard_reads_the_queried_position_not_the_narrowed_result() -> None:
    # Result narrowing decides which objects come back, not which sources a path
    # may start from, so a guard naming a sibling of the narrowed result is legal.
    _validate_query("Animal", _ANIMAL, narrow_to=("Dog",), includes=_guarded(("Cat",)))


def test_include_source_guard_empty_effective_set_rejects() -> None:
    # A guard naming an abstract subtype with no concrete descendants resolves to
    # nothing, which is the guard's own rejection, not a broadening.
    exc = _query_rejects("Animal", _ANIMAL_WITH_A_CHILDLESS_SUBTYPE, includes=_guarded(("Ghost",)))
    assert exc.rule == "narrow-empty-effective-set"


# --------------------------------------------------------------------------- #
# Value-object structural rules (m-value-object contracts 4/5,               #
# m-predicate nested-predicate resolver).                                   #
# --------------------------------------------------------------------------- #
def test_nested_path_first_segment_not_value_object_rejects() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.contact.city", value="Oslo")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-first-segment-not-value-object"


def test_nested_path_unknown_leaf_member_rejects() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.unknown", value="x")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_path_ending_on_nested_value_object_rejects() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.geo", value="x")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_literal_type_mismatch_rejects() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.city", value=42)
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_comparison_valid_string_literal_accepts() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.city", value="Oslo")
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_comparison_null_literal_always_matches() -> None:
    # The absence-collapse rule: a `null` literal matches any declared type.
    op = NestedComparison(op="nestedEq", path="Customer.address.city", value=None)
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_membership_all_valid_literals_accepts() -> None:
    op = NestedMembership(op="nestedIn", path="Customer.address.city", values=("Oslo", "Bergen"))
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_path_short_form_rejects_as_unknown_member() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address", value="x")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_path_mid_scalar_segment_rejects() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.city.extra", value="x")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_path_descends_through_intermediate_nested_value_object() -> None:
    op = NestedComparison(op="nestedEq", path="Customer.address.geo.country", value="Norway")
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_exists_short_form_rejects_as_unknown_member() -> None:
    exc = _rejects(NestedExists(path="Customer"), _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


_STRING_TAGS: tuple[NestedStringOp, ...] = (
    "nestedLike",
    "nestedNotLike",
    "nestedStartsWith",
    "nestedEndsWith",
    "nestedContains",
)


@pytest.mark.parametrize("tag", _STRING_TAGS)
def test_nested_string_predicate_on_a_string_member_accepts(tag: NestedStringOp) -> None:
    _validate(
        "Customer", NestedStringMatch(op=tag, path="Customer.address.city", value="Os"), _CUSTOMER
    )
    _validate(
        "Customer",
        NestedExists(
            path="Customer.address.phones",
            where=NestedStringMatch(op=tag, path="number", value="555"),
        ),
        _CUSTOMER,
    )


@pytest.mark.parametrize("tag", _STRING_TAGS)
def test_nested_string_predicate_on_a_numeric_member_names_the_member(tag: NestedStringOp) -> None:
    # `geo.elevation` is float64 and the literal is a string, so BOTH nested rules
    # apply and their ORDER is what this pins: the member's own type is judged first,
    # so the diagnostic is not the literal's.
    op = NestedStringMatch(op=tag, path="Customer.address.geo.elevation", value="1")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-string-predicate-non-string-member"


def test_nested_string_predicate_on_a_date_member_is_rejected_in_both_scopes() -> None:
    # The hole the dedicated rule closes: `_literal_matches_type` reads a Date leaf
    # permissively as a `str`, so the typed-literal rule alone would ACCEPT a text
    # pattern over a date. Same member, both scopes, one rule.
    path_scoped = NestedStringMatch(
        op="nestedStartsWith", path="Contact.address.phones.expires", value="2024"
    )
    element_scoped = NestedExists(
        path="Contact.address.phones",
        where=NestedStringMatch(op="nestedEndsWith", path="expires", value="-01"),
    )
    for op in (path_scoped, element_scoped):
        exc = _rejects(op, _CONTACT, "Contact")
        assert exc.rule == "nested-string-predicate-non-string-member"


_MULTI_TYPE_MODEL = Metamodel(
    entities=(
        Entity(
            name="Widget",
            table="widget",
            attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
            value_objects=(
                ValueObject(
                    name="spec",
                    column="spec",
                    attributes=(
                        ValueObjectAttribute(name="flag", type="boolean"),
                        ValueObjectAttribute(name="count", type="int32"),
                        ValueObjectAttribute(name="ratio", type="float64"),
                        ValueObjectAttribute(name="amount", type="decimal(10,2)"),
                        ValueObjectAttribute(name="label", type="string"),
                        ValueObjectAttribute(name="whenMade", type="date"),
                    ),
                ),
            ),
        ),
    )
)


def _nested(path: str, value: Scalar) -> NestedComparison:
    return NestedComparison(op="nestedEq", path=path, value=value)


def test_literal_matches_type_boolean() -> None:
    _validate("Widget", _nested("Widget.spec.flag", True), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.flag", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_int() -> None:
    _validate("Widget", _nested("Widget.spec.count", 3), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.count", "3"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"
    # A bool is never a numeric literal (m-core: `True` never equals `1`).
    exc = _rejects(_nested("Widget.spec.count", True), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_float_and_decimal() -> None:
    _validate("Widget", _nested("Widget.spec.ratio", 1.5), _MULTI_TYPE_MODEL)
    _validate("Widget", _nested("Widget.spec.amount", 2), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.ratio", "x"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_string_and_portable_fallback() -> None:
    _validate("Widget", _nested("Widget.spec.label", "x"), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.label", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"

    # date / time / timestamp / uuid / bytes / json ride the portable literal as a
    # string (m-predicate's typed-literal vocabulary has no dedicated carrier).
    _validate("Widget", _nested("Widget.spec.whenMade", "2024-01-02"), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.whenMade", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_membership_literal_type_mismatch_rejects() -> None:
    op = NestedMembership(op="nestedIn", path="Customer.address.city", values=("Oslo", 42))
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_null_check_resolves_the_path_without_a_type_check() -> None:
    op = NestedNullCheck(op="nestedIsNotNull", path="Customer.address.city")
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_exists_value_object_terminated_path_accepts() -> None:
    _validate("Customer", NestedExists(path="Customer.address.geo"), _CUSTOMER)
    _validate("Customer", NestedNotExists(path="Customer.address.phones"), _CUSTOMER)


def test_nested_exists_first_segment_not_value_object_rejects() -> None:
    exc = _rejects(NestedExists(path="Customer.contact"), _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-first-segment-not-value-object"


def test_nested_exists_unknown_intermediate_segment_rejects() -> None:
    exc = _rejects(NestedExists(path="Customer.address.unknown"), _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


# --------------------------------------------------------------------------- #
# The scoped `where` inside nestedExists/nestedNotExists: element-relative     #
# (no `Class` prefix), validated against the TERMINAL value-object descriptor #
# `path` resolves to (m-value-object same-element semantics).                 #
# --------------------------------------------------------------------------- #
def test_nested_exists_scoped_where_unknown_member_rejects() -> None:
    op = NestedExists(
        path="Customer.address.phones",
        where=NestedComparison(op="nestedEq", path="bogus", value="x"),
    )
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_not_exists_scoped_where_unknown_member_rejects() -> None:
    op = NestedNotExists(
        path="Customer.address.phones",
        where=NestedComparison(op="nestedEq", path="bogus", value="x"),
    )
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


def test_nested_exists_scoped_where_literal_type_mismatch_rejects() -> None:
    # `phones.type` is declared `string`; a numeric literal must reject, exactly
    # as the flat (unscoped) nested-comparison rule does.
    op = NestedExists(
        path="Customer.address.phones",
        where=NestedComparison(op="nestedEq", path="type", value=42),
    )
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_exists_scoped_where_membership_literal_type_mismatch_rejects() -> None:
    op = NestedExists(
        path="Customer.address.phones",
        where=NestedMembership(op="nestedIn", path="number", values=("555-9999", 42)),
    )
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_exists_scoped_where_valid_compound_accepts() -> None:
    # A same-element compound (and/or/not) over nested element-relative paths,
    # one of which descends through an intermediate nested value object
    # (`point.lat`) — the multi-segment element-relative walk.
    where = And(
        operands=(
            NestedComparison(op="nestedEq", path="country", value="Norway"),
            Or(
                operands=(
                    NestedComparison(op="nestedEq", path="point.lat", value=59.9),
                    Not(operand=NestedNullCheck(op="nestedIsNotNull", path="point.lon")),
                )
            ),
        )
    )
    op = NestedExists(path="Customer.address.geo", where=where)
    _validate("Customer", op, _CUSTOMER)  # no raise


def test_nested_exists_no_where_still_validates_the_terminal_path() -> None:
    # Absence of `where` must not regress the plain path validation.
    exc = _rejects(NestedExists(path="Customer.address.unknown"), _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


@pytest.mark.parametrize(
    "case_id", ["m-value-object-019", "m-value-object-020", "m-value-object-022"]
)
def test_corpus_scoped_where_cases_still_validate_unrejected(case_id: str) -> None:
    # These claimed `read` cases carry a legitimate scoped `where` (the P2 gap
    # silently accepted them before this fix by never walking `where` at all);
    # confirm they still classify as VALID now that `where` is actually checked.
    case = _load_rejected_case(case_id)
    when = cast("Mapping[str, Any]", case.document["when"])
    query = deserialize_query(cast("Mapping[str, object]", when["objectQuery"]))
    model = formed(_CUSTOMER)
    validate_object_query(_root(model, "Customer"), query, model)  # no raise


def test_include_value_object_segment_rejects() -> None:
    includes = (IncludePath(segments=(IncludeSegment(rel="Customer.address"),)),)
    exc = _query_rejects("Customer", _CUSTOMER, includes=includes)
    assert exc.rule == "deep-fetch-value-object-segment"


def test_include_relationship_path_accepts() -> None:
    includes = (IncludePath(segments=(IncludeSegment(rel="Customer.locations"),)),)
    _validate_query("Customer", _CUSTOMER, includes=includes)  # no raise


def test_navigate_value_object_target_rejects() -> None:
    exc = _rejects(Navigate(rel="Customer.address"), _CUSTOMER, "Customer")
    assert exc.rule == "navigate-value-object-target"


def test_navigate_relationship_target_accepts() -> None:
    _validate("Customer", Navigate(rel="Customer.locations"), _CUSTOMER)


def test_find_root_value_object_rejects() -> None:
    op = NullCheck(op="isNotNull", attr="address.city")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def test_unknown_class_that_is_not_a_value_object_raises_plain_error() -> None:
    with pytest.raises(ValueError, match="names no declared entity or value object"):
        _validate("Customer", Comparison(op="eq", attr="Bogus.name", value=1), _CUSTOMER)


def test_unknown_relationship_that_is_not_a_value_object_raises_plain_error() -> None:
    with pytest.raises(ValueError, match="names no declared relationship"):
        _validate("Customer", Navigate(rel="Customer.bogus"), _CUSTOMER)


# --------------------------------------------------------------------------- #
# Boolean, negation, grouping, and mid-predicate `narrow` propagate the       #
# active scope unchanged (structural pass-through, no position of their own). #
# --------------------------------------------------------------------------- #
def test_boolean_combinators_walk_every_operand() -> None:
    valid = And(
        operands=(
            Comparison(op="eq", attr="Customer.name", value="Ada"),
            Between(attr="Customer.id", lower=1, upper=10),
            NullCheck(op="isNotNull", attr="Customer.name"),
            StringMatch(op="startsWith", attr="Customer.name", value="A"),
            Membership(op="in", attr="Customer.id", values=(1, 2, 3)),
        )
    )
    _validate("Customer", valid, _CUSTOMER)  # no raise

    rejecting = And(
        operands=(
            Comparison(op="eq", attr="Customer.name", value="Ada"),
            NullCheck(op="isNotNull", attr="address.city"),
        )
    )
    exc = _rejects(rejecting, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    or_rejecting = And(
        operands=(
            Comparison(op="eq", attr="Customer.name", value="Ada"),
            Or(
                operands=(
                    NullCheck(op="isNotNull", attr="address.city"),
                    Comparison(op="eq", attr="Customer.name", value="Bob"),
                )
            ),
        )
    )
    exc = _rejects(or_rejecting, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def test_negation_and_grouping_propagate() -> None:
    good = Comparison(op="eq", attr="Customer.name", value="Ada")
    bad = NullCheck(op="isNotNull", attr="address.city")

    _validate("Customer", Not(operand=good), _CUSTOMER)
    exc = _rejects(Not(operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    _validate("Customer", Group(operand=good), _CUSTOMER)
    exc = _rejects(Group(operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    _validate("Customer", Narrow(to=("Customer",), operand=good), _CUSTOMER)
    exc = _rejects(Narrow(to=("Customer",), operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def test_none_and_all_are_no_ops() -> None:
    _validate("Customer", All(), _CUSTOMER)
    _validate("Customer", NoneOp(), _CUSTOMER)


# --------------------------------------------------------------------------- #
# Sort Keys carry attribute references, so they take the positional rule too.  #
# --------------------------------------------------------------------------- #
def test_a_sort_key_outside_the_active_position_rejects() -> None:
    exc = _query_rejects("Order", _ORDERS, order_by=(OrderKey(attr="OrderItem.sku"),))
    assert exc.rule == "attribute-outside-active-position"


def test_a_sort_key_at_the_queried_position_accepts() -> None:
    _validate_query("Order", _ORDERS, order_by=(OrderKey(attr="Order.sku"),))


def test_every_sort_key_is_checked_not_only_the_first() -> None:
    keys = (OrderKey(attr="Order.sku"), OrderKey(attr="OrderItem.sku", direction="desc"))
    exc = _query_rejects("Order", _ORDERS, order_by=keys)
    assert exc.rule == "attribute-outside-active-position"


def test_a_sort_key_reads_the_position_result_narrowing_moved_it_to() -> None:
    # `orderBy` and `narrowTo` are siblings, so the rows a Sort Key orders are the
    # narrowed ones: a concrete subtype's key is legal exactly when the result was
    # narrowed to that subtype, and not before.
    _validate_query(
        "Animal", _ANIMAL, narrow_to=("Dog",), order_by=(OrderKey(attr="Dog.barkVolume"),)
    )
    exc = _query_rejects("Animal", _ANIMAL, order_by=(OrderKey(attr="Dog.barkVolume"),))
    assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_a_narrow_inside_the_predicate_does_not_move_a_sort_keys_position() -> None:
    # A narrow inside the predicate is a term over the same position, not the
    # whole-result narrowing a Sort Key reads. Every clause that could carry one
    # is a sibling of `orderBy`, so only `narrowTo` moves the ordered position.
    narrow_to_dog = Narrow(to=("Dog",), operand=All())
    for predicate in (
        And(operands=(All(), narrow_to_dog)),
        Or(operands=(NoneOp(), narrow_to_dog)),
        Group(operand=narrow_to_dog),
        Not(operand=narrow_to_dog),
        narrow_to_dog,
    ):
        exc = _query_rejects(
            "Animal",
            _ANIMAL,
            predicate=predicate,
            order_by=(OrderKey(attr="Dog.barkVolume"),),
        )
        assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_a_sort_key_rooted_at_a_value_object_names_the_root_misuse() -> None:
    exc = _query_rejects("Customer", _CUSTOMER, order_by=(OrderKey(attr="address.city"),))
    assert exc.rule == "find-root-value-object"


# --------------------------------------------------------------------------- #
# Namespace-aware reference resolution.                                       #
# --------------------------------------------------------------------------- #
_TWO_NAMESPACES = Metamodel(
    entities=(
        Entity(
            name="Customer",
            namespace="crm",
            table="crm_customer",
            attributes=(
                Attribute(name="id", type="int64", column="id", primary_key=True),
                Attribute(name="name", type="string", column="name", max_length=32),
            ),
        ),
        Entity(
            name="Customer",
            namespace="sales",
            table="sales_customer",
            attributes=(
                Attribute(name="id", type="int64", column="id", primary_key=True),
                Attribute(name="name", type="string", column="name", max_length=32),
            ),
        ),
    )
)


def test_a_canonical_reference_resolves_across_namespaces() -> None:
    op = Comparison(op="eq", attr="crm.Customer.name", value="Ada")
    _validate("crm.Customer", op, _TWO_NAMESPACES)


def test_a_canonical_reference_to_the_other_namespace_is_outside_the_position() -> None:
    op = Comparison(op="eq", attr="sales.Customer.name", value="Ada")
    exc = _rejects(op, _TWO_NAMESPACES, "crm.Customer")
    assert exc.rule == "attribute-outside-active-position"


def test_a_bare_reference_two_namespaces_share_resolves_nowhere() -> None:
    # `entity_by_name` answers an ambiguous bare spelling with a miss rather than a
    # silent first match, so the reference names no position at all — the classified
    # refusal, whose message answers with the spellings that would resolve.
    op = Comparison(op="eq", attr="Customer.name", value="Ada")
    exc = _rejects(op, _TWO_NAMESPACES, "crm.Customer")
    assert exc.rule == "reference-ambiguous-entity-name"
    assert "crm.Customer" in str(exc)
    assert "sales.Customer" in str(exc)


# Every PREDICATE position that names an Entity, spelled the only way the grammar
# allows it to be ambiguous — bare — against the corpus model declaring
# `SharedVariant` in two namespaces. The rule is about the spelling failing to
# resolve, so it fires wherever a position is named, not only where an attribute
# is referenced. The query's own clause positions are covered below.
_AMBIGUOUS_BY_POSITION: Mapping[str, PredicateNode] = {
    "attr": Comparison(op="eq", attr="SharedVariant.archiveLabel", value="A-1"),
    "between.attr": Between(attr="SharedVariant.archiveLabel", lower="a", upper="b"),
    "rel": Exists(rel="SharedVariant.register", op=All()),
    "nested path": NestedComparison(op="nestedEq", path="SharedVariant.spec.label", value="A-1"),
    "nestedExists path": NestedExists(path="SharedVariant.spec", where=None),
    "narrow.to": Narrow(to=("SharedVariant",), operand=All()),
    "relationship-scope narrow.to": Exists(
        rel="Register.variant",
        op=Narrow(to=("SharedVariant",), operand=All()),
    ),
}


@pytest.mark.parametrize("position", sorted(_AMBIGUOUS_BY_POSITION))
def test_an_ambiguous_bare_name_is_rejected_in_every_reference_position(position: str) -> None:
    exc = _rejects(_AMBIGUOUS_BY_POSITION[position], _SHARED_LOCAL_NAME, "Register")
    assert exc.rule == "reference-ambiguous-entity-name"
    assert "archive.SharedVariant" in str(exc)
    assert "catalog.SharedVariant" in str(exc)


_AMBIGUOUS_BY_CLAUSE: Mapping[str, dict[str, Any]] = {
    "orderBy.attr": {"order_by": (OrderKey(attr="SharedVariant.archiveLabel"),)},
    "narrowTo": {"narrow_to": ("SharedVariant",)},
    "includes.segment.rel": {
        "includes": (IncludePath(segments=(IncludeSegment(rel="SharedVariant.register"),)),)
    },
    "includes.segment.narrowTo": {
        "includes": (
            IncludePath(
                segments=(IncludeSegment(rel="Register.variant", narrow_to=("SharedVariant",)),)
            ),
        )
    },
    "includes.appliesTo": {
        "includes": (
            IncludePath(
                segments=(IncludeSegment(rel="Register.variant"),),
                applies_to=("SharedVariant",),
            ),
        )
    },
}


@pytest.mark.parametrize("position", sorted(_AMBIGUOUS_BY_CLAUSE))
def test_an_ambiguous_bare_name_is_rejected_in_every_query_clause(position: str) -> None:
    exc = _query_rejects("Register", _SHARED_LOCAL_NAME, **_AMBIGUOUS_BY_CLAUSE[position])
    assert exc.rule == "reference-ambiguous-entity-name"
    assert "archive.SharedVariant" in str(exc)
    assert "catalog.SharedVariant" in str(exc)


def test_an_unambiguous_bare_name_still_resolves_in_a_two_namespace_model() -> None:
    # The refusal is a property of the SPELLING, not of the model: the same model
    # answers every bare name only one namespace declares, and the relationship
    # declaration reaches `archive.SharedVariant` by its qualified identity, so
    # declaring the collision costs the rest of the model nothing.
    _validate("Register", Comparison(op="eq", attr="Register.id", value=1), _SHARED_LOCAL_NAME)
    _validate("Register", Exists(rel="Register.variant", op=All()), _SHARED_LOCAL_NAME)
