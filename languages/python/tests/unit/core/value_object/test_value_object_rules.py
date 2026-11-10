"""m-value-object: the Model Formation Rule Set over declared composite shapes."""

from __future__ import annotations

import pytest

from parallax.core._formation_profile import form_metamodel
from parallax.core.internal.base import STRING
from parallax.core.internal.metamodel import (
    Column,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    Table,
    UnresolvedEntityDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.internal.model_formation import MetamodelValidationError
from parallax.core.internal.value_object import RULE_SET
from parallax.core.internal.value_object._rules import CONTAINMENT_CYCLE, EMPTY, MANY_NULLABLE
from tests.unit._metamodel_support import Declaration, accepted, identity, key, source

_OWNER = identity("Customer")


# --------------------------------------------------------------------------
# Hand-built occurrence graphs.
# --------------------------------------------------------------------------


def _leaf(name: str = "line") -> ValueObjectShapeDeclaration:
    """A shape with one scalar leaf and nothing nested."""
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(), attributes=(ValueObjectAttributeDeclaration(name, type=STRING),)
    )


def _empty() -> ValueObjectShapeDeclaration:
    """A shape declaring neither an Attribute nor a nested occurrence."""
    return ValueObjectShapeDeclaration(key=ValueObjectShapeKey())


def _containing(name: str, shape: ValueObjectShapeDeclaration) -> ValueObjectShapeDeclaration:
    """A shape with one scalar leaf and one nested occurrence of ``shape``."""
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("label", type=STRING),),
        value_objects=(NestedValueObjectOccurrenceDeclaration(name, shape),),
    )


def _owner(*occurrences: ValueObjectOccurrenceDeclaration) -> UnresolvedEntityDeclaration:
    return Declaration(
        identity=_OWNER,
        container=Table("customer"),
        attributes=(key(_OWNER),),
        value_objects=occurrences,
    )


def _occurrence(
    name: str,
    shape: ValueObjectShapeDeclaration,
    *,
    multiplicity: Multiplicity = Multiplicity.ONE,
    nullable: bool = False,
) -> ValueObjectOccurrenceDeclaration:
    return ValueObjectOccurrenceDeclaration(
        name=name,
        storage=Column(name),
        shape=shape,
        multiplicity=multiplicity,
        nullable=nullable,
    )


def _issues(*occurrences: ValueObjectOccurrenceDeclaration) -> tuple[MetamodelIssue, ...]:
    """The Value Object issues a resolvable model is rejected with."""
    return tuple(RULE_SET.validate(accepted(source(_owner(*occurrences)))))


def _codes(*occurrences: ValueObjectOccurrenceDeclaration) -> list[IssueCode]:
    return [issue.code for issue in _issues(*occurrences)]


def _at(*path: str) -> ModelLocation:
    return ValueObjectLocation(ValueObjectIdentity(_OWNER, path))


# --------------------------------------------------------------------------
# Positives.
# --------------------------------------------------------------------------


def test_a_shape_reaching_a_scalar_leaf_through_nesting_is_accepted() -> None:
    assert _codes(_occurrence("address", _containing("street", _leaf("name")))) == []


def test_a_many_occurrence_that_is_not_nullable_is_accepted() -> None:
    assert _codes(_occurrence("phones", _leaf("number"), multiplicity=Multiplicity.MANY)) == []


def test_one_shape_reused_at_disjoint_paths_is_not_a_cycle() -> None:
    # Reuse expands to distinct path-identified occurrence trees, so the same
    # shape appearing at two paths is equivalent to two structurally equal
    # declarations rather than containment.
    shared = _leaf("street")
    reusing = ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration("home", shared),
            NestedValueObjectOccurrenceDeclaration("work", shared),
        ),
    )
    assert _codes(_occurrence("contact", reusing)) == []
    model = form_metamodel(source(_owner(_occurrence("contact", reusing))))
    owner = model.entity(_OWNER)
    assert owner is not None
    contact = owner.value_object("contact")
    assert contact is not None
    assert [nested.identity.path for nested in contact.value_objects] == [
        ("contact", "home"),
        ("contact", "work"),
    ]


# --------------------------------------------------------------------------
# value-object-empty.
# --------------------------------------------------------------------------


def test_an_empty_top_level_shape_is_rejected() -> None:
    (issue,) = _issues(_occurrence("address", _empty()))
    assert issue.code == EMPTY
    assert issue.location == _at("address")
    assert issue.related == ()


def test_an_empty_nested_shape_is_rejected_at_its_own_path() -> None:
    (issue,) = _issues(_occurrence("address", _containing("region", _empty())))
    assert issue.code == EMPTY
    assert issue.location == _at("address", "region")


def test_one_empty_shape_reused_at_two_paths_is_reported_at_each() -> None:
    shared = _empty()
    reusing = ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration("home", shared),
            NestedValueObjectOccurrenceDeclaration("work", shared),
        ),
    )
    assert [issue.location for issue in _issues(_occurrence("contact", reusing))] == [
        _at("contact", "home"),
        _at("contact", "work"),
    ]


# --------------------------------------------------------------------------
# value-object-many-nullable.
# --------------------------------------------------------------------------


def test_a_nullable_many_occurrence_is_rejected() -> None:
    (issue,) = _issues(
        _occurrence("phones", _leaf("number"), multiplicity=Multiplicity.MANY, nullable=True)
    )
    assert issue.code == MANY_NULLABLE
    assert issue.location == _at("phones")


def test_a_nullable_many_nested_occurrence_is_rejected_at_its_own_path() -> None:
    shape = ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        value_objects=(
            NestedValueObjectOccurrenceDeclaration(
                "phones", _leaf("number"), multiplicity=Multiplicity.MANY, nullable=True
            ),
        ),
    )
    (issue,) = _issues(_occurrence("contact", shape))
    assert issue.code == MANY_NULLABLE
    assert issue.location == _at("contact", "phones")


def test_a_nullable_one_occurrence_is_accepted() -> None:
    assert _codes(_occurrence("address", _leaf(), nullable=True)) == []


# --------------------------------------------------------------------------
# value-object-containment-cycle.
# --------------------------------------------------------------------------


def _self_containing() -> ValueObjectShapeDeclaration:
    """A shape that contains itself directly.

    Reuse is carried by the Shape Key alone, so two declaration nodes sharing one
    key are one shape however they are spelled — which is what a frontend that
    resolves a self-referential type produces.
    """
    shape_key = ValueObjectShapeKey()
    label = (ValueObjectAttributeDeclaration("label", type=STRING),)
    return ValueObjectShapeDeclaration(
        key=shape_key,
        attributes=label,
        value_objects=(
            NestedValueObjectOccurrenceDeclaration(
                "self", ValueObjectShapeDeclaration(key=shape_key, attributes=label)
            ),
        ),
    )


def test_a_shape_containing_itself_is_rejected_with_the_containment_path() -> None:
    (issue,) = _issues(_occurrence("node", _self_containing()))
    assert issue.code == CONTAINMENT_CYCLE
    assert issue.location == _at("node", "self")
    assert issue.related == (_at("node"),)


def test_an_indirect_cycle_names_every_step_of_the_loop() -> None:
    outer_key = ValueObjectShapeKey()
    inner_key = ValueObjectShapeKey()
    reentry = ValueObjectShapeDeclaration(key=outer_key)
    inner = ValueObjectShapeDeclaration(
        key=inner_key,
        attributes=(ValueObjectAttributeDeclaration("city", type=STRING),),
        value_objects=(NestedValueObjectOccurrenceDeclaration("owner", reentry),),
    )
    outer = ValueObjectShapeDeclaration(
        key=outer_key,
        attributes=(ValueObjectAttributeDeclaration("label", type=STRING),),
        value_objects=(NestedValueObjectOccurrenceDeclaration("address", inner),),
    )
    (issue,) = _issues(_occurrence("contact", outer))
    assert issue.code == CONTAINMENT_CYCLE
    assert issue.location == _at("contact", "address", "owner")
    assert issue.related == (_at("contact"), _at("contact", "address"))


def test_a_cycle_is_rejected_before_the_metadata_compiler_expands_it() -> None:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(_owner(_occurrence("node", _self_containing()))))
    assert [issue.code for issue in raised.value.issues] == [CONTAINMENT_CYCLE]


# --------------------------------------------------------------------------
# Aggregation and canonical order.
# --------------------------------------------------------------------------


def test_every_defect_is_reported_in_canonical_path_order() -> None:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(
            source(
                _owner(
                    _occurrence("phones", _empty(), multiplicity=Multiplicity.MANY, nullable=True),
                    _occurrence("address", _empty()),
                )
            )
        )
    assert [(issue.code, issue.location) for issue in raised.value.issues] == [
        (EMPTY, _at("address")),
        (EMPTY, _at("phones")),
        (MANY_NULLABLE, _at("phones")),
    ]
