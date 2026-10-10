"""Model-aware Predicate validation unit tests (m-predicate / m-navigate /
m-value-object).

Each rejected rule is pinned with the exact identifier `validate_predicate`
raises, alongside the representative VALID predicates that must NOT be
rejected — including the corpus boundary case (an equivalent-spelling narrow
that is NOT outside the active position). The in-slice rejected corpus cases
are additionally round-tripped through case normalization and the real
validator here (not just via the engine's rejected sweep), so a regression in
node construction, case ingress, or model resolution fails at the unit layer
first.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import _case_ingress, case_format
from parallax.core import inheritance
from parallax.core.base import INFINITY
from parallax.core.metamodel import RelationshipIdentity
from parallax.core.object_query import (
    AsOf,
    History,
    IncludeSegment,
    OrderKey,
    TemporalSelection,
    object_query,
    validate_object_query,
)
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query import validate as query_validation
from parallax.core.object_query._nodes import IncludePathNode, TemporalDimension
from parallax.core.predicate import (
    CURRENT_SCALAR_ELEMENT,
    And,
    Comparison,
    FalseNode,
    FieldSubject,
    Group,
    Membership,
    ModelRejectedError,
    Narrow,
    Not,
    NullCheck,
    Or,
    PredicateNode,
    Presence,
    Quantifier,
    Range,
    ScalarLiteral,
    StringMatch,
    StringOp,
    TrueNode,
    validate_predicate,
)
from parallax.core.predicate import validate as predicate_validation
from parallax.core.predicate._resolved import (
    CURRENT,
    ELEMENT,
    RelatedObject,
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRelationship,
    ResolvedStringMatch,
    ScalarCollection,
    conjunction,
    disjunction,
    framework_comparison,
    managed_comparison,
)
from parallax.descriptor._records import (
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    ValueObject,
    ValueObjectAttribute,
)
from tests.unit._corpus_model_support import formed, records

_MODEL_DIR = case_format.find_repo_root() / "core" / "compatibility" / "models"
_ANIMAL = records("animal")
_BALANCE = records("balance")
_COLLECTIONS = records("predicate-collections")
_CONTACT = records("contact")
_CUSTOMER = records("customer")
_ORDERS = records("orders")
_POSITION = records("position")
_SHARED_LOCAL_NAME = records("shared-local-name")
_TWIN = records("scalar-collection-layout-twin-columns")
_MODEL_BY_FILE: Mapping[str, Metamodel] = {
    "animal.yaml": _ANIMAL,
    "contact.yaml": _CONTACT,
    "customer.yaml": _CUSTOMER,
    "orders.yaml": _ORDERS,
    "scalar-collection-layout-twin-columns.yaml": _TWIN,
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

_INHERITED_VALUE_OBJECTS = Metamodel(
    entities=(
        Entity(
            name="Root",
            table="root",
            inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
            attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
            value_objects=(
                ValueObject(
                    name="spec",
                    column="spec",
                    attributes=(ValueObjectAttribute(name="flag", type="boolean"),),
                ),
                ValueObject(
                    name="entries",
                    column="entries",
                    multiplicity="many",
                    attributes=(ValueObjectAttribute(name="flag", type="boolean"),),
                ),
            ),
        ),
        Entity(
            name="Leaf",
            inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        ),
    )
)


def _validate(target: str, op: PredicateNode, meta: Metamodel) -> None:
    """Form ``meta`` into an accepted model, resolve ``target`` to its accepted
    root Metadata, and run the model-aware validator over ``op``."""
    model = formed(meta)
    validate_predicate(_root(model, target), op, model)


def _resolved(target: str, op: PredicateNode, meta: Metamodel) -> Any:
    model = formed(meta)
    return validate_predicate(_root(model, target), op, model)


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
    predicate = clauses.pop("predicate", TrueNode())
    validate_object_query(root, object_query(root.identity, predicate, **clauses), model)


def _query_rejects(target: str, meta: Metamodel, **clauses: Any) -> ModelRejectedError:
    with pytest.raises(ModelRejectedError) as excinfo:
        _validate_query(target, meta, **clauses)
    return excinfo.value


def _rejects(op: PredicateNode, meta: Metamodel, target: str) -> ModelRejectedError:
    with pytest.raises(ModelRejectedError) as excinfo:
        _validate(target, op, meta)
    return excinfo.value


def _eq(path: str, value: ScalarLiteral) -> Comparison:
    return Comparison(op="eq", subject=FieldSubject(path), value=value)


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


def test_object_query_validation_rejects_incomplete_resolved_metadata_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = formed(_POSITION)
    root = _root(model, "Position")
    axis = root.declared_as_of_axes[0]
    malformed = dataclasses.replace(
        root,
        declared_attributes=tuple(
            member
            for member in root.declared_attributes
            if member.identity.name != axis.start_attribute.name
        ),
    )

    class Family:
        @staticmethod
        def entity(_identity: object) -> Any:
            return type("Position", (), {"root": malformed.identity})()

    class Model:
        @staticmethod
        def entity(_identity: object) -> Any:
            return malformed

    def family_view(_model: object) -> Family:
        return Family()

    monkeypatch.setattr(inheritance, "view", family_view)
    query = object_query(
        malformed.identity,
        TrueNode(),
        temporal={
            "transaction-time": AsOf("latest"),
            "valid-time": AsOf("latest"),
        },
    )

    with pytest.raises(ValueError, match="no declared temporal Attribute"):
        query_validation._validate_temporal_selections(  # pyright: ignore[reportPrivateUsage]
            malformed, query, cast("Any", Model())
        )

    class MissingFamily:
        @staticmethod
        def entity(_identity: object) -> None:
            return None

    def missing_family_view(_model: object) -> MissingFamily:
        return MissingFamily()

    monkeypatch.setattr(inheritance, "view", missing_family_view)
    with pytest.raises(RuntimeError, match="has no Inheritance Facet view"):
        query_validation._validate_temporal_selections(  # pyright: ignore[reportPrivateUsage]
            malformed, query, cast("Any", Model())
        )


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
# The in-slice rejected corpus cases, round-tripped end to end.               #
# --------------------------------------------------------------------------- #
_REJECTED_CASE_IDS = (
    "m-inheritance-040",
    "m-inheritance-041",
    "m-inheritance-042",
    "m-inheritance-064",
    "m-inheritance-132",
    "m-inheritance-133",
    "m-predicate-039",
    "m-predicate-040",
    "m-predicate-041",
    "m-predicate-042",
    "m-predicate-043",
    "m-predicate-044",
    "m-predicate-045",
    "m-object-query-008",
    "m-predicate-047",
    "m-predicate-048",
    "m-predicate-049",
    "m-predicate-054",
    "m-predicate-055",
    "m-predicate-056",
    "m-predicate-057",
    "m-predicate-058",
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
    model = formed(meta)
    query = _case_ingress.normalize_case_query(
        deserialize_query(cast("Mapping[str, object]", when["objectQuery"])), model
    )
    root = _root(model, query.target.canonical)
    with pytest.raises(ModelRejectedError) as excinfo:
        validate_object_query(root, query, model)
    assert excinfo.value.rule == then["rejectedRule"]


# --------------------------------------------------------------------------- #
# between-bounds-inverted (m-predicate "Bound-ordering rule").               #
# --------------------------------------------------------------------------- #
def _between(lower: ScalarLiteral, upper: ScalarLiteral) -> Range:
    return Range(subject=FieldSubject("Order.price"), lower=lower, upper=upper)


@pytest.mark.parametrize(
    ("lower", "upper"),
    [("50.75", "20.00"), ("5.00", "1.00")],
)
def test_between_with_inverted_same_kind_bounds_rejects(
    lower: ScalarLiteral, upper: ScalarLiteral
) -> None:
    exc = _rejects(_between(lower, upper), _ORDERS, "Order")
    assert exc.rule == "between-bounds-inverted"


@pytest.mark.parametrize(
    ("lower", "upper"),
    [
        ("20.00", "50.75"),
        ("5.00", "5.00"),
    ],
)
def test_between_bounds_the_rule_stands_aside_for_accept(
    lower: ScalarLiteral, upper: ScalarLiteral
) -> None:
    # Ordering is evaluated only after both serialized values decode against the
    # resolved Decimal value space.
    _validate("Order", _between(lower, upper), _ORDERS)


@pytest.mark.parametrize("lower", [20.0, 5, "5", True, "2024-02-01"])
def test_between_rejects_a_bound_outside_the_resolved_value_space(lower: ScalarLiteral) -> None:
    exc = _rejects(_between(lower, "50.75"), _ORDERS, "Order")
    assert exc.rule in {"neutral-literal-type-mismatch", "neutral-literal-noncanonical"}


def test_between_bound_ordering_is_checked_wherever_the_node_sits() -> None:
    op = And(operands=(TrueNode(), Not(operand=_between("50.75", "20.00"))))
    exc = _rejects(op, _ORDERS, "Order")
    assert exc.rule == "between-bounds-inverted"


def test_between_subject_is_resolved_before_its_bounds_are_ordered() -> None:
    # A relative path at the queried position names the scope misuse rather than
    # blaming its (also inverted) bounds.
    op = Range(subject=FieldSubject("address.city"), lower="b", upper="a")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "predicate-subject-outside-scope"


def _range_scopes(
    lower: ScalarLiteral, upper: ScalarLiteral, *, path: str, element: str
) -> tuple[PredicateNode, PredicateNode]:
    """The same range, once over a dotted field and once over a quantified
    element's field, so a rule can be asserted at both scopes from one
    expectation."""
    return (
        Range(subject=FieldSubject(path), lower=lower, upper=upper),
        Quantifier(
            "any",
            "Customer.address.phones",
            Range(subject=FieldSubject(element), lower=lower, upper=upper),
        ),
    )


def test_a_value_object_range_rejects_inverted_bounds_in_both_scopes() -> None:
    numeric, _ = _range_scopes(12, 5, path="Customer.address.geo.elevation", element="number")
    _, textual = _range_scopes("work", "home", path="Customer.address.city", element="type")
    for op in (numeric, textual):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "between-bounds-inverted"


def test_range_bounds_are_typed_before_they_are_ordered_in_both_scopes() -> None:
    # Both bounds mistype a `string` leaf AND are inverted as raw numbers. Ordering
    # first would blame the ordering for what is really the bounds' types.
    for op in _range_scopes(42, 7, path="Customer.address.city", element="type"):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "neutral-literal-type-mismatch"


def test_ordered_typed_value_object_bounds_accept_in_both_scopes() -> None:
    _validate(
        "Customer",
        Range(subject=FieldSubject("Customer.address.geo.elevation"), lower=5, upper=12),
        _CUSTOMER,
    )
    _validate(
        "Customer",
        Quantifier(
            "any",
            "Customer.address.phones",
            Range(subject=FieldSubject("number"), lower="555-9000", upper="555-9999"),
        ),
        _CUSTOMER,
    )


def test_a_range_over_an_unknown_path_rejects_before_any_bound_check() -> None:
    op = Range(subject=FieldSubject("Customer.address.bogus"), lower=12, upper=5)
    assert _rejects(op, _CUSTOMER, "Customer").rule == "path-unknown-member"


def test_negated_membership_type_checks_its_values_in_both_scopes() -> None:
    flat = Membership(
        op="notIn", subject=FieldSubject("Customer.address.city"), values=("Oslo", 42)
    )
    scoped = Quantifier(
        "any",
        "Customer.address.phones",
        Membership(op="notIn", subject=FieldSubject("type"), values=(42,)),
    )
    for op in (flat, scoped):
        assert _rejects(op, _CUSTOMER, "Customer").rule == "neutral-literal-type-mismatch"
    _validate(
        "Customer",
        Membership(op="notIn", subject=FieldSubject("Customer.address.city"), values=("Oslo",)),
        _CUSTOMER,
    )


# narrow-outside-position / narrow-empty-effective-set                       #
# (m-predicate "the four-step validation rule").                            #
# --------------------------------------------------------------------------- #
def test_narrow_broadening_past_position_rejects() -> None:
    op = Narrow(to=("Person",), operand=TrueNode())
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_nested_narrow_cannot_broaden_back_out_of_the_enclosing_narrow() -> None:
    op = Narrow(
        to=("Dog",),
        operand=Narrow(to=("Cat",), operand=TrueNode()),
    )
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-position"


def test_narrow_within_position_accepts() -> None:
    op = Narrow(to=("Dog",), operand=TrueNode())
    _validate("Animal", op, _ANIMAL)  # no raise


def test_equivalent_narrow_spelling_is_not_outside_position() -> None:
    # `to=[Pet]` and `to=[Cat, Dog]` resolve to the SAME effective set — both are
    # valid, non-broadening selections of the Animal root.
    _validate("Animal", Narrow(to=("Pet",), operand=TrueNode()), _ANIMAL)
    _validate("Animal", Narrow(to=("Cat", "Dog"), operand=TrueNode()), _ANIMAL)


def test_subtype_selection_rejects_an_exact_duplicate() -> None:
    exc = _rejects(Narrow(to=("Dog", "Dog"), operand=TrueNode()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-duplicate-alternative"


def test_subtype_selection_rejects_overlapping_alternatives() -> None:
    exc = _rejects(Narrow(to=("Dog", "Pet"), operand=TrueNode()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-overlapping-alternatives"


def test_subtype_selection_checks_exact_duplicates_before_overlap() -> None:
    exc = _rejects(Narrow(to=("Pet", "Dog", "Dog"), operand=TrueNode()), _ANIMAL, "Animal")
    assert exc.rule == "subtype-selection-duplicate-alternative"


def test_redundant_self_narrow_is_valid() -> None:
    # Narrowing a position to itself is a documented no-op, not a rejection.
    _validate("Pet", Narrow(to=("Pet",), operand=TrueNode()), _ANIMAL)


def test_narrow_empty_effective_set_rejects() -> None:
    # An abstract subtype with NO concrete descendants: `to` resolves to the empty
    # concrete-subtype set. The childless subtype must sit in a family that DOES
    # compose a concrete elsewhere — a family composing none of them never forms
    # (`inheritance-missing-concrete-subtype`), so the predicate rule is reached
    # only through this shape.
    op = Narrow(to=("Ghost",), operand=TrueNode())
    exc = _rejects(op, _ANIMAL_WITH_A_CHILDLESS_SUBTYPE, "Animal")
    assert exc.rule == "narrow-empty-effective-set"


def test_a_narrow_to_a_name_the_model_does_not_declare_resolves_to_nothing() -> None:
    # A `to` entry naming NO Entity contributes nothing and leaves the resolved set
    # empty, which the narrow rules classify. Only a spelling naming MORE than one
    # Entity is named as a resolution failure of its own.
    op = Narrow(to=("Bogus",), operand=TrueNode())
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "narrow-empty-effective-set"


def test_a_positions_family_set_is_its_roots_concrete_set_without_a_metadata_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An abstract position's own effective set stays narrower than its whole
    # family's, which the root's compiled view answers.
    model = formed(_ANIMAL)
    pet = _root(model, "Pet")
    own = predicate_validation.effective_set(model, pet)

    def refuse(_model: object, identity: object) -> object:
        raise AssertionError(f"{identity} was fetched to find its family's set")

    monkeypatch.setattr(type(model), "entity", refuse)

    family = predicate_validation._family_set(model, pet)  # pyright: ignore[reportPrivateUsage]

    assert own == {"parallax.compatibility.Cat", "parallax.compatibility.Dog"}
    assert family == own | {"parallax.compatibility.WildBoar"}


# --------------------------------------------------------------------------- #
# subtype-attribute-outside-narrow-scope.                                    #
# --------------------------------------------------------------------------- #
def test_subtype_attribute_outside_narrow_scope_rejects() -> None:
    op = Comparison(op="greaterThan", subject=FieldSubject("Dog.barkVolume"), value=5)
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_subtype_attribute_within_narrow_scope_accepts() -> None:
    op = Narrow(
        to=("Dog",),
        operand=Comparison(op="greaterThan", subject=FieldSubject("Dog.barkVolume"), value=3),
    )
    _validate("Animal", op, _ANIMAL)  # no raise


def test_root_declared_attribute_needs_no_narrow() -> None:
    _validate(
        "Animal", Comparison(op="eq", subject=FieldSubject("Animal.name"), value="Rex"), _ANIMAL
    )


def test_an_ancestors_attribute_is_addressable_from_a_descendant_position() -> None:
    # The contravariant half the family rule keeps: an ancestor's member applies to
    # every concrete under it, so it applies at a narrower position too.
    _validate("Dog", Comparison(op="eq", subject=FieldSubject("Animal.name"), value="Rex"), _ANIMAL)


def test_a_descendant_scoped_null_check_resolves_an_inherited_non_nullable_attribute() -> None:
    exc = _rejects(NullCheck(op="isNull", subject=FieldSubject("Dog.name")), _ANIMAL, "Dog")
    assert exc.rule == "null-check-non-nullable-member"


def test_descendant_scoped_null_checks_resolve_inherited_value_objects() -> None:
    operations = (
        NullCheck(op="isNull", subject=FieldSubject("Leaf.spec.flag")),
        Quantifier("any", "Leaf.entries", NullCheck(op="isNull", subject=FieldSubject("flag"))),
    )
    for operation in operations:
        exc = _rejects(operation, _INHERITED_VALUE_OBJECTS, "Leaf")
        assert exc.rule == "null-check-non-nullable-member"


@pytest.mark.parametrize(
    "op",
    [
        Comparison(op="eq", subject=FieldSubject("Dog.name"), value="Rex"),
        Comparison(op="eq", subject=FieldSubject("Pet.licenseId"), value="L-1"),
        Narrow(
            to=("Dog",),
            operand=Comparison(op="eq", subject=FieldSubject("Cat.name"), value="Tom"),
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
    # m-predicate-049.
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "subtype-attribute-outside-narrow-scope"


def test_a_subtype_spelling_is_in_scope_once_the_position_is_narrowed_to_it() -> None:
    # The remedy the rule names: narrowing to Dog makes `Dog.name` applicable, which
    # is what keeps the rejection above `subtype-attribute-outside-narrow-scope`
    # rather than the non-family rule.
    op = Narrow(
        to=("Dog",), operand=Comparison(op="eq", subject=FieldSubject("Dog.name"), value="Rex")
    )
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
    op = Comparison(op="eq", subject=FieldSubject("OrderItem.id"), value=1)
    exc = _rejects(op, _ORDERS, "Order")
    assert exc.rule == "attribute-outside-active-position"


def test_a_sibling_familys_attribute_is_outside_the_active_position() -> None:
    # Neither entity is standalone: `Person` is a plain entity and the position is
    # the whole animal family. The split is by FAMILY membership, not by whether
    # either side happens to participate in inheritance at all.
    op = Comparison(op="eq", subject=FieldSubject("Person.name"), value="Ada")
    exc = _rejects(op, _ANIMAL, "Animal")
    assert exc.rule == "attribute-outside-active-position"


def test_a_quantifier_binds_the_related_entity_its_relative_paths_read() -> None:
    # A to-many quantifier binds each related Entity, so its `where` spells paths
    # relative to that element — and an Entity-qualified one is outside the scope.
    inner = Comparison(op="eq", subject=FieldSubject("name"), value="Rex")
    _validate("Person", Quantifier("any", "Person.pets", inner), _ANIMAL)
    qualified = Comparison(op="eq", subject=FieldSubject("Animal.name"), value="Rex")
    exc = _rejects(Quantifier("any", "Person.pets", qualified), _ANIMAL, "Person")
    assert exc.rule == "predicate-subject-outside-scope"


# --------------------------------------------------------------------------- #
# narrow-outside-relationship-target (m-navigate).                           #
# --------------------------------------------------------------------------- #
def test_narrow_to_outside_relationship_target_rejects() -> None:
    op = Quantifier("any", "Person.pets", Narrow(to=("WildBoar",), operand=TrueNode()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-outside-relationship-target"


def test_empty_narrow_inside_relationship_target_keeps_the_shared_empty_rule() -> None:
    op = Quantifier("any", "Person.pets", Narrow(to=("Bogus",), operand=TrueNode()))
    exc = _rejects(op, _ANIMAL, "Person")
    assert exc.rule == "narrow-empty-effective-set"


def test_narrow_within_relationship_target_accepts() -> None:
    op = Quantifier(
        "any", "Person.pets", Narrow(to=("parallax.compatibility.Dog",), operand=TrueNode())
    )
    _validate("Person", op, _ANIMAL)  # no raise


def test_a_bare_quantifier_accepts() -> None:
    _validate("Person", Quantifier("any", "Person.pets"), _ANIMAL)
    _validate("Person", Quantifier("none", "Person.pets"), _ANIMAL)


def test_every_quantifier_kind_scopes_its_relationship_target() -> None:
    for kind in ("any", "all", "none"):
        op = Quantifier(kind, "Person.pets", Narrow(to=("WildBoar",), operand=TrueNode()))
        exc = _rejects(op, _ANIMAL, "Person")
        assert exc.rule == "narrow-outside-relationship-target"


def test_a_target_local_narrow_measures_its_selection_against_the_reached_target() -> None:
    _validate("Animal", Narrow(path="Animal.owner", to=("Person",), operand=TrueNode()), _ANIMAL)
    exc = _rejects(Narrow(path="Animal.owner", to=("Dog",), operand=TrueNode()), _ANIMAL, "Animal")
    assert exc.rule == "narrow-outside-relationship-target"


def _hop(narrow_to: tuple[str, ...] = ()) -> tuple[IncludePathNode, ...]:
    return (IncludePathNode(segments=(IncludeSegment(rel="Person.pets", narrow_to=narrow_to),)),)


def test_include_segment_narrow_outside_relationship_target_rejects() -> None:
    exc = _query_rejects("Person", _ANIMAL, includes=_hop(("WildBoar",)))
    assert exc.rule == "narrow-outside-relationship-target"


def test_include_segment_narrow_within_relationship_target_accepts() -> None:
    _validate_query("Person", _ANIMAL, includes=_hop(("Dog",)))  # no raise


def test_empty_include_segment_narrow_keeps_the_shared_empty_rule() -> None:
    exc = _query_rejects("Person", _ANIMAL, includes=_hop(("Bogus",)))
    assert exc.rule == "narrow-empty-effective-set"


def _guarded(applies_to: tuple[str, ...] | None) -> tuple[IncludePathNode, ...]:
    return (
        IncludePathNode(
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
# Path resolution: members, crossings, terminal kinds, and scope spelling.    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("path", "rule"),
    [
        ("Customer.contact.city", "path-unknown-member"),
        ("Customer.address.unknown", "path-unknown-member"),
        ("Customer.address.city.extra", "path-unknown-member"),
        ("Customer.name.first", "path-unknown-member"),
        ("Customer.address.geo", "path-target-kind-mismatch"),
        ("Customer.address", "path-target-kind-mismatch"),
        ("Customer.locations", "path-target-kind-mismatch"),
        ("Customer.address.phones", "path-target-kind-mismatch"),
        ("Customer.address.phones.type", "path-crosses-many"),
        ("Customer.locations.label", "path-crosses-many"),
    ],
)
def test_a_field_path_resolves_through_single_members_to_a_scalar(path: str, rule: str) -> None:
    exc = _rejects(_eq(path, "x"), _CUSTOMER, "Customer")
    assert exc.rule == rule


def test_a_path_descends_through_single_value_objects() -> None:
    _validate("Customer", _eq("Customer.address.geo.country", "Norway"), _CUSTOMER)
    _validate(
        "Customer",
        Quantifier("any", "Customer.address.phones", _eq("type", "home")),
        _CUSTOMER,
    )


def test_a_path_never_continues_past_a_top_level_many_value_object() -> None:
    exc = _rejects(_eq("Basket.parcels.sku", "a"), _COLLECTIONS, "Basket")
    assert exc.rule == "path-crosses-many"


def test_a_relative_path_names_a_member_of_the_bound_entity() -> None:
    exc = _rejects(Quantifier("any", "Order.items", _eq("bogus", 1)), _ORDERS, "Order")
    assert exc.rule == "path-unknown-member"


def test_a_path_follows_a_to_one_relationship_and_refuses_a_to_many_one() -> None:
    _validate("OrderItem", _eq("OrderItem.order.name", "A"), _ORDERS)
    exc = _rejects(_eq("Order.items.sku", "A"), _ORDERS, "Order")
    assert exc.rule == "path-crosses-many"


@pytest.mark.parametrize(
    ("op", "target", "meta"),
    [
        (Quantifier("any", "Customer.address"), "Customer", _CUSTOMER),
        (Quantifier("all", "Customer.name", TrueNode()), "Customer", _CUSTOMER),
        (Quantifier("none", "OrderItem.order"), "OrderItem", _ORDERS),
        (Presence("exists", "Customer.address.phones"), "Customer", _CUSTOMER),
        (Presence("notExists", "Order.items"), "Order", _ORDERS),
        (Presence("exists", "Order.name"), "Order", _ORDERS),
        (Narrow(path="Person.pets", to=("Dog",), operand=TrueNode()), "Person", _ANIMAL),
        (
            Narrow(path="Customer.address", to=("Customer",), operand=TrueNode()),
            "Customer",
            _CUSTOMER,
        ),
    ],
    ids=[
        "any-single-value-object",
        "all-scalar",
        "none-to-one",
        "exists-many-value-object",
        "not-exists-to-many",
        "exists-scalar",
        "narrow-to-many",
        "narrow-value-object",
    ],
)
def test_each_operation_admits_only_its_own_terminal_kind(
    op: PredicateNode, target: str, meta: Metamodel
) -> None:
    assert _rejects(op, meta, target).rule == "path-target-kind-mismatch"


def test_presence_tests_single_objects_and_quantifiers_collections() -> None:
    _validate("Customer", Presence("exists", "Customer.address.geo"), _CUSTOMER)
    _validate("Customer", Quantifier("none", "Customer.address.phones"), _CUSTOMER)
    _validate("OrderItem", Presence("notExists", "OrderItem.order"), _ORDERS)
    _validate("Order", Quantifier("all", "Order.items", _eq("sku", "A")), _ORDERS)


@pytest.mark.parametrize(
    ("op", "target", "meta"),
    [
        (_eq("address.city", "Oslo"), "Customer", _CUSTOMER),
        (
            Quantifier("any", "Customer.address.phones", _eq("Customer.address.city", "Oslo")),
            "Customer",
            _CUSTOMER,
        ),
        (Quantifier("any", "Order.items", _eq("Order.name", "A")), "Order", _ORDERS),
        (
            Comparison(op="eq", subject=CURRENT_SCALAR_ELEMENT, value="a"),
            "CollectionTwinItem",
            _TWIN,
        ),
        (
            Quantifier("any", "CollectionTwinItem.tags", _eq("tags", "a")),
            "CollectionTwinItem",
            _TWIN,
        ),
        (
            Quantifier(
                "any",
                "CollectionTwinItem.parts",
                Comparison(op="eq", subject=CURRENT_SCALAR_ELEMENT, value="a"),
            ),
            "CollectionTwinItem",
            _TWIN,
        ),
        (
            Quantifier(
                "any",
                "Customer.address.phones",
                Narrow(to=("Customer",), operand=TrueNode()),
            ),
            "Customer",
            _CUSTOMER,
        ),
    ],
    ids=[
        "relative-at-the-queried-position",
        "qualified-inside-a-value-object-quantifier",
        "qualified-inside-a-relationship-quantifier",
        "element-at-the-queried-position",
        "field-inside-a-scalar-quantifier",
        "element-inside-a-value-object-quantifier",
        "narrow-inside-a-value-object-quantifier",
    ],
)
def test_a_subject_is_spelled_for_the_scope_it_is_read_in(
    op: PredicateNode, target: str, meta: Metamodel
) -> None:
    assert _rejects(op, meta, target).rule == "predicate-subject-outside-scope"


def test_a_scalar_collection_element_takes_scalar_operations_but_no_null_check() -> None:
    element = Comparison(op="eq", subject=CURRENT_SCALAR_ELEMENT, value="a")
    _validate("CollectionTwinItem", Quantifier("any", "CollectionTwinItem.tags", element), _TWIN)
    nested = Quantifier(
        "any",
        "CollectionTwinItem.parts",
        Quantifier(
            "all", "marks", Comparison(op="greaterThan", subject=CURRENT_SCALAR_ELEMENT, value=0)
        ),
    )
    _validate("CollectionTwinItem", nested, _TWIN)
    mistyped = Quantifier(
        "any",
        "CollectionTwinItem.counts",
        Comparison(op="eq", subject=CURRENT_SCALAR_ELEMENT, value="a"),
    )
    assert _rejects(mistyped, _TWIN, "CollectionTwinItem").rule == "neutral-literal-type-mismatch"
    matched = Quantifier(
        "any",
        "CollectionTwinItem.counts",
        StringMatch(op="like", subject=CURRENT_SCALAR_ELEMENT, value="1%"),
    )
    assert _rejects(matched, _TWIN, "CollectionTwinItem").rule == (
        "string-predicate-non-string-member"
    )


def test_literal_comparison_over_a_value_object_field() -> None:
    _validate("Customer", _eq("Customer.address.city", "Oslo"), _CUSTOMER)
    exc = _rejects(_eq("Customer.address.city", 42), _CUSTOMER, "Customer")
    assert exc.rule == "neutral-literal-type-mismatch"


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: Comparison(
            op="eq", subject=FieldSubject("Order.price"), value=cast("ScalarLiteral", None)
        ),
        lambda: Range(
            subject=FieldSubject("Order.price"), lower=cast("ScalarLiteral", None), upper="1.00"
        ),
        lambda: StringMatch(op="like", subject=FieldSubject("Order.name"), value=cast("str", None)),
        lambda: Membership(
            op="in", subject=FieldSubject("Order.name"), values=("A", cast("ScalarLiteral", None))
        ),
        lambda: Comparison(
            op="eq", subject=CURRENT_SCALAR_ELEMENT, value=cast("ScalarLiteral", None)
        ),
        lambda: Membership(
            op="in", subject=CURRENT_SCALAR_ELEMENT, values=("Oslo", cast("ScalarLiteral", None))
        ),
    ],
)
def test_literal_nodes_reject_none_at_construction(
    constructor: Callable[[], PredicateNode],
) -> None:
    with pytest.raises(ValueError, match=r"\.is_null\(\).+\.is_not_null\(\)"):
        constructor()


_STRING_TAGS: tuple[StringOp, ...] = ("like", "notLike", "startsWith", "endsWith", "contains")


@pytest.mark.parametrize("tag", _STRING_TAGS)
def test_a_string_predicate_on_a_string_member_accepts_in_every_scope(tag: StringOp) -> None:
    _validate(
        "Customer",
        StringMatch(op=tag, subject=FieldSubject("Customer.address.city"), value="Os"),
        _CUSTOMER,
    )
    _validate(
        "Customer",
        Quantifier(
            "any",
            "Customer.address.phones",
            StringMatch(op=tag, subject=FieldSubject("number"), value="555"),
        ),
        _CUSTOMER,
    )


def test_string_patterns_retain_their_text_and_member_in_every_scope() -> None:
    # String-pattern syntax is not a serialized typed literal, so field, dotted,
    # and element occurrences retain their text verbatim beside the resolved
    # String member, and an omitted flag folds nothing.
    scalar = _resolved(
        "Order",
        StringMatch(op="startsWith", subject=FieldSubject("Order.name"), value="A"),
        _ORDERS,
    )
    nested = _resolved(
        "Customer",
        StringMatch(
            op="contains",
            subject=FieldSubject("Customer.address.city"),
            value="sl",
            case_insensitive=True,
        ),
        _CUSTOMER,
    )
    elements = _resolved(
        "Customer",
        Quantifier(
            "any",
            "Customer.address.phones",
            StringMatch(op="endsWith", subject=FieldSubject("number"), value="55"),
        ),
        _CUSTOMER,
    )
    assert isinstance(elements, ResolvedQuantifier)
    assert isinstance(scalar, ResolvedStringMatch)
    assert isinstance(nested, ResolvedStringMatch)
    assert isinstance(elements.where, ResolvedStringMatch)
    assert (scalar.op, scalar.pattern, scalar.case_insensitive) == ("startsWith", "A", False)
    assert (nested.op, nested.pattern, nested.case_insensitive) == ("contains", "sl", True)
    assert (elements.where.op, elements.where.pattern) == ("endsWith", "55")
    assert scalar.member.identity.name == "name"
    assert nested.member.identity.name == "city"
    assert elements.where.member.identity.name == "number"


def test_dotted_operations_resolve_to_the_shared_scalar_operators_over_their_leaf() -> None:
    inequality = _resolved(
        "Customer",
        Comparison(op="notEq", subject=FieldSubject("Customer.address.city"), value="Oslo"),
        _CUSTOMER,
    )
    absence = _resolved(
        "Customer",
        NullCheck(op="isNull", subject=FieldSubject("Customer.address.geo.elevation")),
        _CUSTOMER,
    )
    excluded = _resolved(
        "Customer",
        Membership(op="notIn", subject=FieldSubject("Customer.address.city"), values=("Oslo",)),
        _CUSTOMER,
    )

    assert isinstance(inequality, ResolvedComparison)
    assert (inequality.op, inequality.value, inequality.position) == ("notEq", "Oslo", CURRENT)
    assert inequality.member.identity.name == "city"
    assert isinstance(absence, ResolvedNullCheck)
    assert absence.op == "isNull"
    assert isinstance(excluded, ResolvedMembership)
    assert (excluded.op, excluded.values) == ("notIn", ("Oslo",))


def test_a_field_past_a_to_one_hop_is_read_at_the_related_position() -> None:
    resolved = _resolved("OrderItem", _eq("OrderItem.order.name", "A"), _ORDERS)
    assert isinstance(resolved, ResolvedComparison)
    assert isinstance(resolved.position, RelatedObject)
    assert resolved.position.source == CURRENT
    assert resolved.position.relationship.identity.name == "order"
    assert resolved.position.relationship.target.identity.name == "Order"
    assert resolved.member.identity.name == "name"


def test_collections_resolve_to_the_quantifier_over_what_they_hold() -> None:
    scalar = _resolved(
        "CollectionTwinItem",
        Quantifier(
            "all",
            "CollectionTwinItem.tags",
            Comparison(op="eq", subject=CURRENT_SCALAR_ELEMENT, value="a"),
        ),
        _TWIN,
    )
    occurrence = _resolved("Customer", Quantifier("none", "Customer.address.phones"), _CUSTOMER)
    related = _resolved("Customer", Quantifier("any", "Customer.locations"), _CUSTOMER)

    assert isinstance(scalar, ResolvedQuantifier)
    assert isinstance(scalar.collection, ScalarCollection)
    assert scalar.collection.member.identity.name == "tags"
    assert isinstance(scalar.where, ResolvedComparison)
    assert scalar.where.position == ELEMENT
    assert isinstance(occurrence, ResolvedQuantifier)
    assert (occurrence.kind, occurrence.where) == ("none", None)
    assert cast("Any", occurrence.collection).identity.path == ("address", "phones")
    assert isinstance(related, ResolvedQuantifier)
    assert isinstance(related.collection, ResolvedRelationship)
    assert related.collection.identity.name == "locations"


def test_presence_resolves_to_its_single_object() -> None:
    occurrence = _resolved("Customer", Presence("exists", "Customer.address.geo"), _CUSTOMER)
    related = _resolved("OrderItem", Presence("notExists", "OrderItem.order"), _ORDERS)

    assert isinstance(occurrence, ResolvedPresence)
    assert occurrence.negated is False
    assert cast("Any", occurrence.target).identity.path == ("address", "geo")
    assert isinstance(related, ResolvedPresence)
    assert related.negated is True
    assert isinstance(related.target, ResolvedRelationship)
    assert related.target.identity.name == "order"


def test_a_target_local_narrow_resolves_at_the_reached_target() -> None:
    bare = _resolved(
        "Animal", Narrow(path="Animal.owner", to=("Person",), operand=TrueNode()), _ANIMAL
    )
    assert isinstance(bare, ResolvedNarrow)
    assert bare.operand is None
    assert isinstance(bare.target, RelatedObject)
    assert bare.target.relationship.identity.name == "owner"
    scoped = _resolved(
        "Animal",
        Narrow(path="Animal.owner", to=("Person",), operand=_eq("name", "Ada")),
        _ANIMAL,
    )
    assert isinstance(scoped, ResolvedNarrow)
    assert isinstance(scoped.operand, ResolvedComparison)
    assert scoped.operand.position == CURRENT


def test_constants_resolve_without_an_operation() -> None:
    assert _resolved("Order", TrueNode(), _ORDERS) == ResolvedConstant(True)
    assert _resolved("Order", FalseNode(), _ORDERS) == ResolvedConstant(False)


def test_a_null_check_on_an_undeclared_attribute_is_refused_at_validation() -> None:
    exc = _rejects(NullCheck(op="isNull", subject=FieldSubject("Order.bogus")), _ORDERS, "Order")
    assert exc.rule == "path-unknown-member"


def test_generated_predicate_products_reject_missing_or_mistyped_semantics() -> None:
    model = formed(_ORDERS)
    root = _root(model, "Order")
    member = root.attribute("id")
    assert member is not None

    with pytest.raises(ValueError, match="outside"):
        managed_comparison(op="eq", member=member, value=cast("Any", "1"))
    with pytest.raises(ValueError, match="at least one term"):
        conjunction(ResolvedConstant(True))
    with pytest.raises(ValueError, match="no resolved relationship direction"):
        predicate_validation._direction_join(  # pyright: ignore[reportPrivateUsage]
            RelationshipIdentity(root.identity, "missing"), model
        )


def test_generated_compositions_group_alternatives_and_drop_identity_terms() -> None:
    model = formed(_ORDERS)
    root = _root(model, "Order")
    member = root.attribute("id")
    assert member is not None
    one, two, three = (managed_comparison(op="eq", member=member, value=n) for n in (1, 2, 3))

    either = disjunction(conjunction(one, two), three)
    composed = conjunction(ResolvedConstant(True), either, conjunction(two, three))

    assert disjunction(one) is one
    assert conjunction(ResolvedConstant(True), one) is one
    assert either == ResolvedOr((ResolvedGroup(ResolvedAnd((one, two))), three))
    assert composed == ResolvedAnd((ResolvedGroup(either), two, three))


def test_a_framework_comparison_binds_its_sentinel_as_is() -> None:
    root = _root(formed(_POSITION), "Position")
    end = root.attribute("txEnd")
    assert end is not None

    current = framework_comparison(op="eq", member=end, value=INFINITY)

    assert current == ResolvedComparison("eq", end, INFINITY, framework=True)
    assert current.member is end


def test_string_predicate_rejects_a_non_string_member() -> None:
    exc = _rejects(
        StringMatch(op="like", subject=FieldSubject("Order.qty"), value="1%"), _ORDERS, "Order"
    )
    assert exc.rule == "string-predicate-non-string-member"


@pytest.mark.parametrize("tag", _STRING_TAGS)
def test_a_string_predicate_on_a_numeric_leaf_names_the_member(tag: StringOp) -> None:
    # `geo.elevation` is float64 and the literal is a string, so BOTH rules
    # apply and their ORDER is what this pins: the member's own type is judged first.
    op = StringMatch(op=tag, subject=FieldSubject("Customer.address.geo.elevation"), value="1")
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "string-predicate-non-string-member"


def test_a_string_predicate_on_a_date_member_is_rejected_in_both_scopes() -> None:
    # A Date leaf reads as a `str` literal, so the typed-literal rule alone would
    # ACCEPT a text pattern over a date. Same member, both scopes, one rule.
    dotted = StringMatch(
        op="startsWith", subject=FieldSubject("Contact.address.phones.expires"), value="2024"
    )
    assert _rejects(dotted, _CONTACT, "Contact").rule == "path-crosses-many"
    element_scoped = Quantifier(
        "any",
        "Contact.address.phones",
        StringMatch(op="endsWith", subject=FieldSubject("expires"), value="-01"),
    )
    exc = _rejects(element_scoped, _CONTACT, "Contact")
    assert exc.rule == "string-predicate-non-string-member"


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


def test_literal_matches_type_boolean() -> None:
    _validate("Widget", _eq("Widget.spec.flag", True), _MULTI_TYPE_MODEL)
    exc = _rejects(_eq("Widget.spec.flag", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"


def test_literal_matches_type_int() -> None:
    _validate("Widget", _eq("Widget.spec.count", 3), _MULTI_TYPE_MODEL)
    exc = _rejects(_eq("Widget.spec.count", "3"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"
    # A bool is never a numeric literal (m-core: `True` never equals `1`).
    exc = _rejects(_eq("Widget.spec.count", True), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"


def test_literal_matches_type_float_and_decimal() -> None:
    _validate("Widget", _eq("Widget.spec.ratio", 1.5), _MULTI_TYPE_MODEL)
    _validate("Widget", _eq("Widget.spec.amount", "2.00"), _MULTI_TYPE_MODEL)
    exc = _rejects(_eq("Widget.spec.ratio", "x"), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"


def test_literal_matches_type_string_and_portable_fallback() -> None:
    _validate("Widget", _eq("Widget.spec.label", "x"), _MULTI_TYPE_MODEL)
    exc = _rejects(_eq("Widget.spec.label", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"
    # date / time / timestamp / uuid / bytes / json ride the portable literal as a
    # string (m-predicate's typed-literal vocabulary has no dedicated carrier).
    _validate("Widget", _eq("Widget.spec.whenMade", "2024-01-02"), _MULTI_TYPE_MODEL)
    exc = _rejects(_eq("Widget.spec.whenMade", 1), _MULTI_TYPE_MODEL, "Widget")
    assert exc.rule == "neutral-literal-type-mismatch"


def test_a_null_check_rejects_a_non_nullable_leaf() -> None:
    op = NullCheck(op="isNotNull", subject=FieldSubject("Customer.address.street"))
    exc = _rejects(op, _CUSTOMER, "Customer")
    assert exc.rule == "null-check-non-nullable-member"


def test_null_checks_accept_nullable_leaves_in_every_scope() -> None:
    _validate("Order", NullCheck(op="isNull", subject=FieldSubject("Order.sku")), _ORDERS)
    _validate(
        "Customer",
        NullCheck(op="isNotNull", subject=FieldSubject("Customer.address.geo.elevation")),
        _CUSTOMER,
    )
    _validate(
        "Customer",
        Quantifier(
            "any", "Customer.address.phones", NullCheck(op="isNull", subject=FieldSubject("type"))
        ),
        _CUSTOMER,
    )


def test_a_value_object_quantifier_judges_its_where_against_the_element() -> None:
    where = And(
        operands=(
            _eq("country", "Norway"),
            Or(
                operands=(
                    _eq("point.lat", 59.9),
                    Not(operand=NullCheck(op="isNotNull", subject=FieldSubject("point.lon"))),
                )
            ),
        )
    )
    exc = _rejects(Quantifier("any", "Customer.address.geo", where), _CUSTOMER, "Customer")
    assert exc.rule == "path-target-kind-mismatch"
    for kind in ("any", "none"):
        unknown = Quantifier(kind, "Customer.address.phones", _eq("bogus", "x"))
        assert _rejects(unknown, _CUSTOMER, "Customer").rule == "path-unknown-member"
    mistyped = Quantifier("any", "Customer.address.phones", _eq("type", 42))
    assert _rejects(mistyped, _CUSTOMER, "Customer").rule == "neutral-literal-type-mismatch"


@pytest.mark.parametrize(
    "case_id", ["m-value-object-019", "m-value-object-020", "m-value-object-022"]
)
def test_corpus_scoped_where_cases_still_validate_unrejected(case_id: str) -> None:
    case = _load_rejected_case(case_id)
    when = cast("Mapping[str, Any]", case.document["when"])
    query = deserialize_query(cast("Mapping[str, object]", when["objectQuery"]))
    model = formed(_CUSTOMER)
    validate_object_query(_root(model, "Customer"), query, model)  # no raise


def test_include_value_object_segment_rejects() -> None:
    includes = (IncludePathNode(segments=(IncludeSegment(rel="Customer.address"),)),)
    exc = _query_rejects("Customer", _CUSTOMER, includes=includes)
    assert exc.rule == "deep-fetch-value-object-segment"


def test_include_relationship_path_accepts() -> None:
    includes = (IncludePathNode(segments=(IncludeSegment(rel="Customer.locations"),)),)
    _validate_query("Customer", _CUSTOMER, includes=includes)  # no raise


def test_unknown_class_that_is_not_a_value_object_raises_plain_error() -> None:
    with pytest.raises(ValueError, match="names no declared entity or value object"):
        _validate("Customer", _eq("Bogus.name", 1), _CUSTOMER)


# --------------------------------------------------------------------------- #
# Boolean, negation, grouping, and mid-predicate `narrow` propagate the       #
# active scope unchanged (structural pass-through, no position of their own). #
# --------------------------------------------------------------------------- #
_OUT_OF_SCOPE = NullCheck(op="isNotNull", subject=FieldSubject("address.city"))


def test_boolean_combinators_walk_every_operand() -> None:
    valid = And(
        operands=(
            _eq("Customer.name", "Ada"),
            Range(subject=FieldSubject("Customer.id"), lower=1, upper=10),
            NullCheck(op="isNotNull", subject=FieldSubject("Customer.address.geo.elevation")),
            StringMatch(op="startsWith", subject=FieldSubject("Customer.name"), value="A"),
            Membership(op="in", subject=FieldSubject("Customer.id"), values=(1, 2, 3)),
        )
    )
    _validate("Customer", valid, _CUSTOMER)  # no raise

    rejecting = And(operands=(_eq("Customer.name", "Ada"), _OUT_OF_SCOPE))
    assert _rejects(rejecting, _CUSTOMER, "Customer").rule == "predicate-subject-outside-scope"

    or_rejecting = And(
        operands=(
            _eq("Customer.name", "Ada"),
            Or(operands=(_OUT_OF_SCOPE, _eq("Customer.name", "Bob"))),
        )
    )
    assert _rejects(or_rejecting, _CUSTOMER, "Customer").rule == "predicate-subject-outside-scope"


def test_negation_and_grouping_propagate() -> None:
    good = _eq("Customer.name", "Ada")
    wraps: tuple[Callable[[PredicateNode], PredicateNode], ...] = (
        lambda op: Not(operand=op),
        lambda op: Group(operand=op),
        lambda op: Narrow(to=("Customer",), operand=op),
    )
    for wrap in wraps:
        _validate("Customer", wrap(good), _CUSTOMER)
        exc = _rejects(wrap(_OUT_OF_SCOPE), _CUSTOMER, "Customer")
        assert exc.rule == "predicate-subject-outside-scope"


def test_the_constants_are_no_ops() -> None:
    _validate("Customer", TrueNode(), _CUSTOMER)
    _validate("Customer", FalseNode(), _CUSTOMER)


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
    narrow_to_dog = Narrow(to=("Dog",), operand=TrueNode())
    for predicate in (
        And(operands=(TrueNode(), narrow_to_dog)),
        Or(operands=(FalseNode(), narrow_to_dog)),
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
    op = Comparison(op="eq", subject=FieldSubject("crm.Customer.name"), value="Ada")
    _validate("crm.Customer", op, _TWO_NAMESPACES)


def test_a_canonical_reference_to_the_other_namespace_is_outside_the_position() -> None:
    op = Comparison(op="eq", subject=FieldSubject("sales.Customer.name"), value="Ada")
    exc = _rejects(op, _TWO_NAMESPACES, "crm.Customer")
    assert exc.rule == "attribute-outside-active-position"


def test_a_bare_reference_two_namespaces_share_resolves_nowhere() -> None:
    # `entity_by_name` answers an ambiguous bare spelling with a miss rather than a
    # silent first match, so the reference names no position at all — the classified
    # refusal, whose message answers with the spellings that would resolve.
    op = Comparison(op="eq", subject=FieldSubject("Customer.name"), value="Ada")
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
    "field path": _eq("SharedVariant.archiveLabel", "A-1"),
    "range path": Range(subject=FieldSubject("SharedVariant.archiveLabel"), lower="a", upper="b"),
    "quantifier path": Quantifier("any", "SharedVariant.register"),
    "presence path": Presence("exists", "SharedVariant.spec"),
    "dotted path": _eq("SharedVariant.spec.label", "A-1"),
    "narrow.to": Narrow(to=("SharedVariant",), operand=TrueNode()),
    "target-local narrow.to": Narrow(
        path="Register.variant", to=("SharedVariant",), operand=TrueNode()
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
        "includes": (IncludePathNode(segments=(IncludeSegment(rel="SharedVariant.register"),)),)
    },
    "includes.segment.narrowTo": {
        "includes": (
            IncludePathNode(
                segments=(IncludeSegment(rel="Register.variant", narrow_to=("SharedVariant",)),)
            ),
        )
    },
    "includes.appliesTo": {
        "includes": (
            IncludePathNode(
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
    _validate("Register", _eq("Register.id", 1), _SHARED_LOCAL_NAME)
    _validate("Register", Presence("exists", "Register.variant"), _SHARED_LOCAL_NAME)
