"""Model-aware operation validation unit tests (m-op-algebra / m-navigate /
m-value-object, COR-3 Phase 7 increment 1).

Each rejected rule is pinned with the exact identifier `validate_operation`
raises, alongside the representative VALID operations that must NOT be
rejected — including the corpus boundary case (an equivalent-spelling narrow
that is NOT outside the active position). The 10 in-slice rejected corpus
cases are additionally round-tripped through the real validator here (not
just via the engine's rejected sweep), so a regression in either the node
construction or the model resolution fails at the unit layer first.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core.descriptor import (
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    AsOfRange,
    Between,
    Comparison,
    DeepFetch,
    Distinct,
    Exists,
    Group,
    History,
    Limit,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Operation,
    OperationRejectedError,
    Or,
    OrderBy,
    OrderKey,
    PathSegment,
    Scalar,
    StringMatch,
    deserialize,
    validate_operation,
)

pytestmark = pytest.mark.unit

_MODEL_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"
_ANIMAL = corpus_models.load_model(_MODEL_DIR / "animal.yaml")
_CUSTOMER = corpus_models.load_model(_MODEL_DIR / "customer.yaml")


def _rejects(op: Operation, meta: Metamodel, target: str) -> OperationRejectedError:
    with pytest.raises(OperationRejectedError) as excinfo:
        validate_operation(target, op, meta)
    return excinfo.value


# --------------------------------------------------------------------------- #
# The 10 in-slice rejected corpus cases, round-tripped end to end.            #
# --------------------------------------------------------------------------- #
_REJECTED_CASE_IDS = (
    "m-inheritance-040",
    "m-inheritance-041",
    "m-inheritance-042",
    "m-inheritance-064",
    "m-inheritance-072",
    "m-value-object-034",
    "m-value-object-035",
    "m-value-object-036",
    "m-value-object-037",
    "m-value-object-038",
)


def _rejected_target(meta: Metamodel) -> str:
    from parallax.core import inheritance

    root = inheritance.family_of(meta).root
    return root.name if root is not None else meta.entities[0].name


def _load_rejected_case(case_id: str) -> case_format.Case:
    (path,) = Path(case_format.default_cases_dir()).glob(f"{case_id}-*.yaml")
    return case_format.load_case(path)


@pytest.mark.parametrize("case_id", _REJECTED_CASE_IDS)
def test_corpus_rejected_case_classifies_to_its_own_rejected_rule(case_id: str) -> None:
    case = _load_rejected_case(case_id)
    when = cast("Mapping[str, Any]", case.document["when"])
    then = cast("Mapping[str, Any]", case.document["then"])
    meta = _ANIMAL if "animal" in case.model else _CUSTOMER
    op = deserialize(cast("Mapping[str, object]", when["operation"]))
    target = _rejected_target(meta)
    exc = _rejects(op, meta, target)
    assert exc.rule == then["rejectedRule"]


# --------------------------------------------------------------------------- #
# narrow-outside-position / narrow-empty-effective-set                       #
# (m-op-algebra "the four-step validation rule").                            #
# --------------------------------------------------------------------------- #
def test_narrow_broadening_past_position_rejects() -> None:
    op = Narrow(entity="Pet", to=("WildBoar",), operand=All())
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_nested_narrow_cannot_broaden_back_out_of_the_enclosing_narrow() -> None:
    op = Narrow(
        entity="Pet",
        to=("Dog",),
        operand=Narrow(entity="Animal", to=("Cat",), operand=All()),
    )
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_narrow_within_position_accepts() -> None:
    op = Narrow(entity="Animal", to=("Dog",), operand=All())
    validate_operation("Animal", op, _ANIMAL)  # no raise


def test_equivalent_narrow_spelling_is_not_outside_position() -> None:
    # `to=[Pet]` and `to=[Cat, Dog]` resolve to the SAME effective set — both are
    # valid, non-broadening narrows of the Animal root (m-op-algebra "the serde
    # preserves the authored `to` list verbatim"; the boundary this rule pins).
    validate_operation("Animal", Narrow(entity="Animal", to=("Pet",), operand=All()), _ANIMAL)
    validate_operation("Animal", Narrow(entity="Animal", to=("Cat", "Dog"), operand=All()), _ANIMAL)


def test_redundant_self_narrow_is_valid() -> None:
    # Narrowing a position to itself is a documented no-op, not a rejection.
    validate_operation("Pet", Narrow(entity="Pet", to=("Pet",), operand=All()), _ANIMAL)


def test_narrow_empty_effective_set_rejects() -> None:
    # A synthetic family whose abstract subtype has NO concrete descendants at
    # all: `to` resolves to the empty concrete-subtype set.
    empty_family = Metamodel(
        entities=(
            Entity(
                name="Root",
                table="root",
                attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
                inheritance=Inheritance(
                    role="root", strategy="table-per-hierarchy", tag_column="kind"
                ),
            ),
            Entity(name="Ghost", inheritance=Inheritance(role="abstract-subtype", parent="Root")),
        )
    )
    op = Narrow(entity="Root", to=("Ghost",), operand=All())
    exc = _rejects(op, empty_family, "Root")
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
        entity="Animal",
        to=("Dog",),
        operand=Comparison(op="greaterThan", attr="Dog.barkVolume", value=3),
    )
    validate_operation("Animal", op, _ANIMAL)  # no raise


def test_root_declared_attribute_needs_no_narrow() -> None:
    validate_operation("Animal", Comparison(op="eq", attr="Animal.name", value="Rex"), _ANIMAL)


# --------------------------------------------------------------------------- #
# narrow-outside-relationship-target (m-navigate, resolved Q10).             #
# --------------------------------------------------------------------------- #
def test_narrow_to_outside_relationship_target_rejects() -> None:
    op = Exists(rel="Person.pets", op=Narrow(entity="Pet", to=("WildBoar",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_narrow_entity_outside_relationship_target_rejects() -> None:
    op = Exists(rel="Person.pets", op=Narrow(entity="Animal", to=("Dog",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_narrow_within_relationship_target_accepts() -> None:
    op = Exists(rel="Person.pets", op=Narrow(entity="Pet", to=("Dog",), operand=All()))
    validate_operation("Person", op, _ANIMAL)  # no raise


def test_navigate_with_no_inner_operation_accepts() -> None:
    validate_operation("Person", Navigate(rel="Person.pets"), _ANIMAL)


def test_not_exists_relationship_target_scope_propagates() -> None:
    op = NotExists(rel="Person.pets", op=Narrow(entity="Pet", to=("WildBoar",), operand=All()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_deep_fetch_path_narrow_outside_relationship_target_rejects() -> None:
    op = DeepFetch(
        operand=All(),
        paths=((PathSegment(rel="Person.pets", narrow=("WildBoar",)),),),
    )
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_deep_fetch_path_narrow_within_relationship_target_accepts() -> None:
    op = DeepFetch(operand=All(), paths=((PathSegment(rel="Person.pets", narrow=("Dog",)),),))
    validate_operation("Person", op, _ANIMAL)  # no raise


# --------------------------------------------------------------------------- #
# Value-object structural rules (m-value-object contracts 4/5,               #
# m-op-algebra nested-predicate resolver).                                   #
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
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_nested_comparison_null_literal_always_matches() -> None:
    # The absence-collapse rule: a `null` literal matches any declared type.
    op = NestedComparison(op="nestedEq", path="Customer.address.city", value=None)
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_nested_membership_all_valid_literals_accepts() -> None:
    op = NestedMembership(path="Customer.address.city", values=("Oslo", "Bergen"))
    validate_operation("Customer", op, _CUSTOMER)  # no raise


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
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_nested_exists_short_form_rejects_as_unknown_member() -> None:
    exc = _rejects(NestedExists(path="Customer"), _CUSTOMER, "Customer")
    assert exc.rule == "nested-path-unknown-member"


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
    validate_operation("Widget", _nested("Widget.spec.flag", True), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.flag", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_int() -> None:
    validate_operation("Widget", _nested("Widget.spec.count", 3), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.count", "3"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"
    # A bool is never a numeric literal (m-core: `True` never equals `1`).
    exc = _rejects(_nested("Widget.spec.count", True), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_float_and_decimal() -> None:
    validate_operation("Widget", _nested("Widget.spec.ratio", 1.5), _MULTI_TYPE_MODEL)
    validate_operation("Widget", _nested("Widget.spec.amount", 2), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.ratio", "x"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_literal_matches_type_string_and_portable_fallback() -> None:
    validate_operation("Widget", _nested("Widget.spec.label", "x"), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.label", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"

    # date / time / timestamp / uuid / bytes / json ride the portable literal as a
    # string (m-op-algebra's typed-literal vocabulary has no dedicated carrier).
    validate_operation("Widget", _nested("Widget.spec.whenMade", "2024-01-02"), _MULTI_TYPE_MODEL)
    exc = _rejects(_nested("Widget.spec.whenMade", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_membership_literal_type_mismatch_rejects() -> None:
    op = NestedMembership(path="Customer.address.city", values=("Oslo", 42))
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "nested-literal-type-mismatch"


def test_nested_null_check_resolves_the_path_without_a_type_check() -> None:
    op = NestedNullCheck(op="nestedIsNotNull", path="Customer.address.city")
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_nested_exists_value_object_terminated_path_accepts() -> None:
    validate_operation("Customer", NestedExists(path="Customer.address.geo"), _CUSTOMER)
    validate_operation("Customer", NestedNotExists(path="Customer.address.phones"), _CUSTOMER)


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
        where=NestedMembership(path="number", values=("555-9999", 42)),
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
    validate_operation("Customer", op, _CUSTOMER)  # no raise


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
    op = deserialize(cast("Mapping[str, object]", when["operation"]))
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_deep_fetch_value_object_segment_rejects() -> None:
    op = DeepFetch(operand=All(), paths=((PathSegment(rel="Customer.address"),),))
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "deep-fetch-value-object-segment"


def test_deep_fetch_relationship_path_accepts() -> None:
    op = DeepFetch(operand=All(), paths=((PathSegment(rel="Customer.locations"),),))
    validate_operation("Customer", op, _CUSTOMER)  # no raise


def test_navigate_value_object_target_rejects() -> None:
    exc = _rejects(Navigate(rel="Customer.address"), _CUSTOMER, "Customer")
    assert exc.rule == "navigate-value-object-target"


def test_navigate_relationship_target_accepts() -> None:
    validate_operation("Customer", Navigate(rel="Customer.locations"), _CUSTOMER)


def test_find_root_value_object_rejects() -> None:
    op = NullCheck(op="isNotNull", attr="address.city")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def test_unknown_class_that_is_not_a_value_object_raises_plain_error() -> None:
    with pytest.raises(ValueError, match="names no declared entity or value object"):
        validate_operation("Customer", Comparison(op="eq", attr="Bogus.name", value=1), _CUSTOMER)


def test_unknown_relationship_that_is_not_a_value_object_raises_plain_error() -> None:
    with pytest.raises(ValueError, match="names no declared relationship"):
        validate_operation("Customer", Navigate(rel="Customer.bogus"), _CUSTOMER)


# --------------------------------------------------------------------------- #
# Result-shaping / boolean / temporal wrappers propagate the active scope     #
# unchanged (structural pass-through, no position change of their own).       #
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
    validate_operation("Customer", valid, _CUSTOMER)  # no raise

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


def test_negation_and_grouping_and_result_shaping_wrappers_propagate() -> None:
    good = Comparison(op="eq", attr="Customer.name", value="Ada")
    bad = NullCheck(op="isNotNull", attr="address.city")

    validate_operation("Customer", Not(operand=good), _CUSTOMER)
    exc = _rejects(Not(operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    validate_operation("Customer", Group(operand=good), _CUSTOMER)
    exc = _rejects(Group(operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    validate_operation(
        "Customer", OrderBy(operand=good, keys=(OrderKey(attr="Customer.id"),)), _CUSTOMER
    )
    exc = _rejects(
        OrderBy(operand=bad, keys=(OrderKey(attr="Customer.id"),)), _CUSTOMER, "Customer"
    )
    assert exc.rule == "find-root-value-object"

    validate_operation("Customer", Limit(operand=good, count=1), _CUSTOMER)
    exc = _rejects(Limit(operand=bad, count=1), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    validate_operation("Customer", Distinct(operand=good), _CUSTOMER)
    exc = _rejects(Distinct(operand=bad), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    validate_operation(
        "Customer", AsOf(operand=good, as_of_attr="Customer.asOf", date="now"), _CUSTOMER
    )
    exc = _rejects(AsOf(operand=bad, as_of_attr="Customer.asOf", date="now"), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    validate_operation("Customer", History(operand=good, as_of_attr="Customer.asOf"), _CUSTOMER)
    exc = _rejects(History(operand=bad, as_of_attr="Customer.asOf"), _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"

    range_op = AsOfRange(operand=good, as_of_attr="Customer.asOf", from_="now", to="now")
    validate_operation("Customer", range_op, _CUSTOMER)
    bad_range = AsOfRange(operand=bad, as_of_attr="Customer.asOf", from_="now", to="now")
    exc = _rejects(bad_range, _CUSTOMER, "Customer")
    assert exc.rule == "find-root-value-object"


def test_none_and_all_are_no_ops() -> None:
    validate_operation("Customer", All(), _CUSTOMER)
    validate_operation("Customer", NoneOp(), _CUSTOMER)
