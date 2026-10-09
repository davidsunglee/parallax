"""m-metamodel: scalar multiplicity on the canonical member definition.

A ``MANY`` Attribute or Value Object Attribute keeps its scalar element type and
carries the multiplicity on the one ``Leaf`` every consumer reads. Its role and
option refusals belong to the existing construction invariants, the foundational
resolver, and the owning Rule Sets; assignment judgement consumes the codec's
authoring verdict for it exactly as it does for a Value Object occurrence.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.core.base import STRING, TIMESTAMP
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    AuthoringViolation,
    Column,
    EntityIdentity,
    Leaf,
    MemberShape,
    Multiplicity,
    PrimaryKey,
    TemporalDimension,
    ValueObjectAttributeDeclaration,
    WriteAssignmentError,
    judge_assignment,
)
from parallax.core.metamodel._resolve import AS_OF_ATTRIBUTE_TYPE
from tests.unit._metamodel_support import Declaration, codes, identity, key, source

_ORDER = EntityIdentity("parallax.test", "Order")
_MANY = Multiplicity.MANY


def _tags(**options: object) -> AttributeMetadata:
    return AttributeMetadata(
        identity=AttributeIdentity(_ORDER, "tags"),
        type=STRING,
        storage=Column("tags"),
        multiplicity=_MANY,
        **options,  # pyright: ignore[reportArgumentType]
    )


def test_a_collection_attribute_defines_one_many_leaf_of_its_element_type() -> None:
    attribute = _tags(read_only=True)

    assert attribute.definition == Leaf("tags", STRING, False, _MANY)
    assert attribute.type == STRING
    assert MemberShape.of((attribute,), ()).member("tags") == attribute.definition


def test_a_single_attribute_keeps_its_single_leaf() -> None:
    attribute = AttributeMetadata(AttributeIdentity(_ORDER, "name"), STRING, Column("name"))

    assert attribute.multiplicity is Multiplicity.ONE
    assert attribute.definition == Leaf("name", STRING, False)


@pytest.mark.parametrize(
    "construct",
    [
        lambda: _tags(nullable=True),
        lambda: _tags(primary_key=PrimaryKey()),
        lambda: _tags(optimistic_locking=True),
        lambda: _tags(max_length=8),
    ],
    ids=["nullable", "primary-key", "optimistic-locking", "max-length"],
)
def test_a_collection_attribute_refuses_every_role_and_option_it_cannot_hold(
    construct: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match="many Attribute"):
        construct()


def test_a_value_object_collection_leaf_is_never_nullable() -> None:
    declared = ValueObjectAttributeDeclaration("labels", STRING, multiplicity=_MANY)

    assert declared.definition == Leaf("labels", STRING, False, _MANY)
    with pytest.raises(ValueError, match="never nullable"):
        ValueObjectAttributeDeclaration("labels", STRING, nullable=True, multiplicity=_MANY)


def test_an_axis_endpoint_must_be_one_timestamp_rather_than_a_collection() -> None:
    entity = identity("Policy")
    start = AttributeMetadata(
        AttributeIdentity(entity, "validStart"), TIMESTAMP, Column("from_z"), multiplicity=_MANY
    )
    end = AttributeMetadata(AttributeIdentity(entity, "validEnd"), TIMESTAMP, Column("thru_z"))
    declaration = Declaration(
        identity=entity,
        attributes=(key(entity), start, end),
        as_of_axes=(AsOfAxisMetadata(TemporalDimension.VALID_TIME, start.identity, end.identity),),
    )

    assert codes(source(declaration)) == (AS_OF_ATTRIBUTE_TYPE,)


def test_a_collection_assignment_refuses_null_and_consumes_the_authoring_verdict() -> None:
    tags = _tags()

    with pytest.raises(WriteAssignmentError, match="required attribute is absent"):
        judge_assignment(tags, None, known_violation=None)
    judge_assignment(tags, ("a",), known_violation=None)
    with pytest.raises(TypeError, match="authoring verdict"):
        judge_assignment(tags, ("a",))


@pytest.mark.parametrize(
    ("violation", "message"),
    [
        (AuthoringViolation("", "not-a-list", "a"), r"tags: value 'a' .* a `many` attribute"),
        (
            AuthoringViolation("[1]", "type-mismatch", 2, STRING),
            r"tags\[1\]: value 2 does not match the declared type String\(\)",
        ),
    ],
    ids=["shape", "element"],
)
def test_a_collection_violation_is_a_value_type_mismatch_located_at_its_position(
    violation: AuthoringViolation, message: str
) -> None:
    with pytest.raises(WriteAssignmentError, match=message) as caught:
        judge_assignment(_tags(), "unused", known_violation=violation)
    assert caught.value.rule == "value-type-mismatch"


def test_a_read_only_collection_refuses_assignment_before_its_value_is_judged() -> None:
    with pytest.raises(WriteAssignmentError) as caught:
        judge_assignment(_tags(read_only=True), (), known_violation=None)
    assert caught.value.rule == "read-only"
