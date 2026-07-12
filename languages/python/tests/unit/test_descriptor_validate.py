"""Schema-equivalent domain validation of compiled metamodel records."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    DescriptorError,
    Entity,
    Inheritance,
    Metamodel,
    PkGenerator,
    Relationship,
    validate_entity,
    validate_metamodel,
)

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)


def _attr(**overrides: object) -> Attribute:
    base: dict[str, object] = {"name": "id", "type": "int64", "column": "id", "primary_key": True}
    base.update(overrides)
    return Attribute(**base)  # type: ignore[arg-type]


def _entity(**overrides: object) -> Entity:
    base: dict[str, object] = {"name": "Account", "table": "account", "attributes": (_attr(),)}
    base.update(overrides)
    return Entity(**base)  # type: ignore[arg-type]


def test_valid_entity_passes() -> None:
    entity = _entity(
        attributes=(
            _attr(),
            Attribute(name="owner", type="string", column="owner", max_length=64),
            Attribute(name="balance", type="decimal(18,2)", column="balance"),
            Attribute(name="version", type="int32", column="version", optimistic_locking=True),
        ),
        relationships=(
            Relationship(
                name="passport",
                related_entity="Passport",
                cardinality="one-to-one",
                join="this.id = Passport.personId",
                reverse_name="holder",
            ),
        ),
    )
    validate_entity(entity)  # no raise
    validate_metamodel(Metamodel(entities=(entity,)))  # no raise


def test_empty_entity_name_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="entity name must be non-empty"):
        validate_entity(_entity(name=""))


def test_empty_table_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="table must be non-empty"):
        validate_entity(_entity(table=""))


def test_no_attributes_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="declares no attributes"):
        validate_entity(_entity(attributes=()))


def _root_and_subtype() -> Metamodel:
    root = Entity(
        name="Reading",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(_attr(),),
    )
    subtype = Entity(
        name="MeterReading",
        table="reading",
        inheritance=Inheritance(role="concrete-subtype", parent="Reading", tag_value="meter"),
    )
    return Metamodel(entities=(root, subtype))


def test_inheritance_participant_may_omit_own_attributes() -> None:
    # A concrete subtype whose members are wholly inherited declares no attributes
    # of its own; the family — not the local block — supplies its chain.
    family = _root_and_subtype()
    validate_metamodel(family)  # no raise
    validate_entity(family.entity("MeterReading"))  # no raise (schema per-entity rule)


def test_family_with_no_attributes_anywhere_is_rejected() -> None:
    root = Entity(
        name="R", inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype")
    )
    subtype = Entity(
        name="S", table="s", inheritance=Inheritance(role="concrete-subtype", parent="R")
    )
    with pytest.raises(DescriptorError, match="declares no attributes, directly or inherited"):
        validate_metamodel(Metamodel(entities=(root, subtype)))


def test_reading_corpus_model_with_wholly_inherited_subtype_validates() -> None:
    # reading.yaml's MeterReading concrete subtype inherits every member from the
    # abstract Reading root — validate_metamodel must accept it (the finding).
    validate_metamodel(_MODELS["reading"])  # no raise


def test_every_corpus_model_validates() -> None:
    assert _MODELS  # non-empty
    for metamodel in _MODELS.values():
        validate_metamodel(metamodel)  # no raise across the whole corpus


def test_temporal_entity_with_optimistic_locking_attr_is_rejected() -> None:
    entity = _entity(
        attributes=(
            _attr(),
            Attribute(name="version", type="int64", column="version", optimistic_locking=True),
        ),
        as_of_attributes=(
            AsOfAttribute(
                name="processing", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    with pytest.raises(DescriptorError, match="must not also declare an optimisticLocking"):
        validate_entity(entity)


def test_non_identifier_attribute_name_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="not a canonical camelCase identifier"):
        validate_entity(_entity(attributes=(_attr(name="Bad Name"),)))


def test_invalid_neutral_type_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="is not a neutral type"):
        validate_entity(_entity(attributes=(_attr(type="widget"),)))


def test_empty_column_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="column must be non-empty"):
        validate_entity(_entity(attributes=(_attr(column=""),)))


def test_out_of_range_max_length_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="maxLength must be >= 1"):
        validate_entity(_entity(attributes=(_attr(type="string", max_length=0),)))


def test_optimistic_locking_on_non_integral_type_is_rejected() -> None:
    with pytest.raises(DescriptorError, match="must be int32 or int64"):
        validate_entity(_entity(attributes=(_attr(type="string", optimistic_locking=True),)))


def test_pk_generator_batch_size_below_one_is_rejected() -> None:
    pk = PkGenerator(strategy="sequence", batch_size=0)
    with pytest.raises(DescriptorError, match="batchSize must be >= 1"):
        validate_entity(_entity(attributes=(_attr(pk_generator=pk),)))


def test_pk_generator_increment_size_below_one_is_rejected() -> None:
    pk = PkGenerator(strategy="sequence", increment_size=0)
    with pytest.raises(DescriptorError, match="incrementSize must be >= 1"):
        validate_entity(_entity(attributes=(_attr(pk_generator=pk),)))


def test_non_identifier_relationship_name_is_rejected() -> None:
    rel = Relationship(name="Bad", related_entity="Passport", cardinality="one-to-one", join="x")
    with pytest.raises(DescriptorError, match="not a canonical camelCase identifier"):
        validate_entity(_entity(relationships=(rel,)))


def test_empty_related_entity_is_rejected() -> None:
    rel = Relationship(name="passport", related_entity="", cardinality="one-to-one", join="x")
    with pytest.raises(DescriptorError, match="relatedEntity must be non-empty"):
        validate_entity(_entity(relationships=(rel,)))


def test_empty_join_is_rejected() -> None:
    rel = Relationship(
        name="passport", related_entity="Passport", cardinality="one-to-one", join=""
    )
    with pytest.raises(DescriptorError, match="join must be non-empty"):
        validate_entity(_entity(relationships=(rel,)))


def test_non_identifier_reverse_name_is_rejected() -> None:
    rel = Relationship(
        name="passport",
        related_entity="Passport",
        cardinality="one-to-one",
        join="x",
        reverse_name="Holder",
    )
    with pytest.raises(DescriptorError, match=r"reverseName .* is not an identifier"):
        validate_entity(_entity(relationships=(rel,)))
