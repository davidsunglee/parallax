"""m-value-object: the Model Formation Rule Set over declared composite shapes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from _metamodel_support import Declaration, accepted, identity, key, source

from parallax.conformance import case_format
from parallax.core import value_object
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import STRING
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    Column,
    IssueCode,
    Metamodel,
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
from parallax.core.model_formation import (
    MODEL_FORMATION_MODULE,
    MetamodelValidationError,
    RequiredRuleSet,
)
from parallax.core.value_object import (
    CONTAINMENT_CYCLE,
    EMPTY,
    ISSUE_CODES,
    MANY_NULLABLE,
    RULE_SET,
    VALUE_OBJECT_MODULE,
)
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

pytestmark = pytest.mark.unit

_OWNER = identity("Customer")

_CORPUS = sorted(
    (case_format.find_repo_root() / "core" / "compatibility" / "models").glob("*.yaml")
)


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


def _formed(path: Path) -> Metamodel:
    """The accepted model a corpus descriptor forms into."""
    document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return form_metamodel(
        unresolved_metamodel(parse_document(cast("Mapping[str, object]", document)))
    )


# --------------------------------------------------------------------------
# The module's formation contract.
# --------------------------------------------------------------------------


def test_the_builtin_manifest_declares_this_modules_rule_set_and_no_compiler() -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == VALUE_OBJECT_MODULE)
    assert isinstance(entry.rule_set, RequiredRuleSet)
    assert entry.issue_codes == ISSUE_CODES
    assert entry.compiler is None
    assert entry.required_facets == frozenset()
    assert entry.required_modules == frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE})
    assert RULE_SET in BUILTIN_PROFILE.rule_sets
    assert RULE_SET.owner == VALUE_OBJECT_MODULE
    assert all(
        compiler.owner != VALUE_OBJECT_MODULE for compiler in BUILTIN_PROFILE.model_compilers
    )


def test_this_module_publishes_no_facet_view() -> None:
    # Accepted occurrences are expanded by the Metadata Compiler, so there is no
    # derived view for this owner to install or serve.
    assert not hasattr(value_object, "FACET_KEY")
    assert not hasattr(value_object, "view")


def test_the_value_object_row_sits_between_inheritance_and_relationship() -> None:
    # Manifest entry order is Rule Set invocation order, and this file's row is
    # the spec manifest's fourth.
    owners = [entry.owner for entry in BUILTIN_MANIFEST.entries]
    assert owners.index("m-inheritance") < owners.index(VALUE_OBJECT_MODULE)
    assert owners.index(VALUE_OBJECT_MODULE) < owners.index("m-relationship")


def test_the_owned_code_set_is_closed() -> None:
    assert sorted(ISSUE_CODES) == [CONTAINMENT_CYCLE, EMPTY, MANY_NULLABLE]


# --------------------------------------------------------------------------
# Positives.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", _CORPUS, ids=lambda path: cast("Path", path).stem)
def test_every_corpus_model_declares_only_valid_value_objects(path: Path) -> None:
    assert _formed(path) is not None


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


def test_a_cycle_stops_the_walk_rather_than_expanding_forever() -> None:
    # Reporting the cycle is also what bounds the traversal: nothing below the
    # re-entry is visited, so exactly one issue is emitted per closing path.
    assert _codes(_occurrence("node", _self_containing())) == [CONTAINMENT_CYCLE]


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
