"""``parallax.conformance._descriptor_family``: the raw-descriptor family walk
and the raw-descriptor family-invariant validator the corpus `rejected`
grading path uses to classify an inline `when.model` document."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.conformance._descriptor_family import family_attributes, family_of, validate
from parallax.core.inheritance import InheritanceError
from parallax.descriptor._records import AsOfAxisMetadata, Attribute, Entity, Inheritance, Metamodel
from parallax.descriptor._serde import deserialize

_REPO = case_format.find_repo_root()
_MODELS = corpus_models.load_models(_REPO / "core" / "compatibility" / "models")
_CASES = _REPO / "core" / "compatibility" / "cases"


def _descriptor_rejection_cases() -> list[tuple[str, dict[str, Any], str]]:
    found: list[tuple[str, dict[str, Any], str]] = []
    # `*` (not `0*`): the root-ownership witnesses (m-inheritance-102/103)
    # are the first `when.model` cases numbered past 099, so the glob must not
    # assume every id stays in the 0xx range.
    for path in sorted(_CASES.glob("m-inheritance-*-rejected-*.yaml")):
        loaded = case_format.safe_load_yaml(Path(path).read_text(encoding="utf-8"))
        document = cast("dict[str, Any]", loaded)
        when = document.get("when")
        if isinstance(when, dict) and "model" in when:
            model = cast("dict[str, Any]", when["model"])
            then = cast("dict[str, Any]", document["then"])
            found.append((path.stem, model, str(then["rejectedRule"])))
    return found


_REJECTIONS = _descriptor_rejection_cases()
_RAW_ONLY_REJECTIONS = [
    rejection
    for rejection in _REJECTIONS
    if rejection[2] != "inheritance-materialization-key-collision"
]

_INDEPENDENT_FAMILIES: Final[dict[str, Any]] = {
    "entities": [
        {
            "name": "Payment",
            "table": "payment",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        },
        {
            "name": "CardPayment",
            "inheritance": {"role": "concrete-subtype", "parent": "Payment", "tagValue": "card"},
            "attributes": [{"name": "network", "type": "string", "nullable": True}],
        },
        {
            "name": "Document",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        },
        {
            "name": "Invoice",
            "table": "invoice",
            "inheritance": {"role": "concrete-subtype", "parent": "Document"},
            "attributes": [{"name": "total", "type": "int64", "nullable": True}],
        },
    ]
}
"""Two families that share no ancestry, each rooted and each with its own
strategy — the shape a Domain Model assembles from independently declared
families."""


def test_every_descriptor_rejection_case_is_covered() -> None:
    assert len(_RAW_ONLY_REJECTIONS) == 18


@pytest.mark.parametrize(
    "stem, model, rule", _RAW_ONLY_REJECTIONS, ids=[r[0] for r in _RAW_ONLY_REJECTIONS]
)
def test_rejected_descriptor_classifies_with_its_corpus_rule(
    stem: str, model: dict[str, Any], rule: str
) -> None:
    with pytest.raises(InheritanceError) as caught:
        validate(deserialize(model))
    assert caught.value.rule == rule


def test_valid_inheritance_family_passes_validation() -> None:
    validate(_MODELS["animal"])  # no raise
    validate(_MODELS["document"])
    validate(_MODELS["vehicle"])


def test_non_inheritance_descriptor_validates_trivially() -> None:
    validate(_MODELS["account"])  # no participants, no raise


def test_independent_families_in_one_descriptor_pass_validation() -> None:
    # `workshop` declares two families that share no ancestry, each under its own
    # strategy: resolving one strategy for the whole descriptor would apply the
    # table-per-hierarchy shared-table rule to the table-per-concrete-subtype family.
    validate(_MODELS["workshop"])  # no raise


def test_a_rootless_family_beside_a_rooted_one_is_rejected() -> None:
    # A rooted family does not answer for its neighbour: the abstract-orphan chain
    # reaches no root of its own and is still rejected.
    descriptor = deserialize(
        {
            "entities": [
                *_INDEPENDENT_FAMILIES["entities"],
                {
                    "name": "Widget",
                    "table": "widget",
                    "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                },
                {
                    "name": "Pet",
                    "inheritance": {"role": "abstract-subtype", "parent": "Widget"},
                    "attributes": [{"name": "licenseId", "type": "string", "maxLength": 16}],
                },
            ]
        }
    )
    with pytest.raises(InheritanceError) as caught:
        validate(descriptor)
    assert caught.value.rule == "inheritance-missing-root"


def test_family_of_reports_the_single_root_and_strategy() -> None:
    family = family_of(_MODELS["animal"])
    assert family.root is not None
    assert family.root.name == "Animal"
    assert family.strategy == "table-per-hierarchy"


def test_family_of_is_empty_without_participants() -> None:
    family = family_of(_MODELS["account"])
    assert family.root is None
    assert family.strategy is None
    assert family.participants == ()


def test_family_attributes_widens_across_the_whole_family() -> None:
    animal = _MODELS["animal"]
    names = {attr.name for attr in family_attributes(animal, animal.entity("Dog"))}
    assert names == {"id", "name", "ownerId", "licenseId", "barkVolume", "indoor", "tuskLength"}


def test_family_attributes_is_the_entitys_own_attributes_outside_a_family() -> None:
    account = _MODELS["account"]
    entity = account.entity("Account")
    assert family_attributes(account, entity) == entity.attributes


def _cyclic_pair() -> Metamodel:
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    return Metamodel(
        entities=(
            Entity(
                name="A",
                table="a",
                inheritance=Inheritance(role="concrete-subtype", parent="B"),
                attributes=attrs,
            ),
            Entity(
                name="B",
                table="b",
                inheritance=Inheritance(role="concrete-subtype", parent="A"),
                attributes=attrs,
            ),
        )
    )


def test_family_attributes_falls_back_to_local_when_ancestry_is_malformed() -> None:
    # A malformed (cyclic) ancestry resolves to no root: `family_attributes`
    # falls back to the entity's own local attributes, the same "resolve to
    # what it can reach" posture `declaring_entity` itself takes.
    cyclic = _cyclic_pair()
    entity = cyclic.entity("A")
    assert family_attributes(cyclic, entity) == entity.attributes


def _minimal_attrs() -> tuple[Attribute, ...]:
    return (Attribute(name="id", type="int64", column="id", primary_key=True),)


def test_reject_descendant_temporal_axes_under_a_non_temporal_root() -> None:
    # A non-temporal TPH root with an abstract-subtype that declares its own axes.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    dog = Entity(
        name="Dog",
        table="animal",
        inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog"),
        attributes=(Attribute(name="barkVolume", type="int32", column="bark_volume"),),
    )
    meta = Metamodel(entities=(root, pet, dog))
    with pytest.raises(InheritanceError) as caught:
        validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_temporal_axes_under_a_temporal_root() -> None:
    # A temporal TPCS root whose concrete subtype adds its own second axis.
    root = Entity(
        name="Rate",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=_minimal_attrs(),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    deposit = Entity(
        name="DepositRate",
        table="deposit_rate",
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
        attributes=(Attribute(name="grade", type="string", column="grade"),),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="valid-time", start_attribute="valid_start", end_attribute="valid_end"
            ),
        ),
    )
    meta = Metamodel(entities=(root, deposit))
    with pytest.raises(InheritanceError) as caught:
        validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "DepositRate"


def test_temporal_root_and_root_owned_axes_still_validate_cleanly() -> None:
    # A well-formed family (axes declared ONLY on the root) passes validation —
    # the new invariant must not reject the corpus's own root-declared families.
    validate(_MODELS["rate"])
    validate(_MODELS["instrument"])


def test_reject_descendant_optimistic_locking_under_a_non_versioned_root() -> None:
    # ADR 0027: a non-versioned TPH root with an abstract-subtype that
    # declares its own optimisticLocking attribute.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        attributes=(
            Attribute(name="revision", type="int32", column="revision", optimistic_locking=True),
        ),
    )
    dog = Entity(
        name="Dog",
        inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog"),
        attributes=(Attribute(name="barkVolume", type="int32", column="bark_volume"),),
    )
    meta = Metamodel(entities=(root, pet, dog))
    with pytest.raises(InheritanceError) as caught:
        validate(meta)
    assert caught.value.rule == "inheritance-optimistic-locking-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_optimistic_locking_under_a_versioned_root() -> None:
    # A versioned TPCS root whose concrete subtype adds a SECOND version
    # attribute of its own, under a different name.
    root = Entity(
        name="Appliance",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            *_minimal_attrs(),
            Attribute(name="version", type="int32", column="version", optimistic_locking=True),
        ),
    )
    fridge = Entity(
        name="Fridge",
        table="fridge",
        inheritance=Inheritance(role="concrete-subtype", parent="Appliance"),
        attributes=(
            Attribute(name="revision", type="int32", column="revision", optimistic_locking=True),
        ),
    )
    meta = Metamodel(entities=(root, fridge))
    with pytest.raises(InheritanceError) as caught:
        validate(meta)
    assert caught.value.rule == "inheritance-optimistic-locking-not-root-owned"
    assert caught.value.entity == "Fridge"


def test_versioned_root_and_root_owned_version_still_validates_cleanly() -> None:
    # A well-formed family (the version declared ONLY on the root) passes
    # validation — the new invariant must not reject the corpus's own
    # root-declared versioned families.
    validate(_MODELS["vehicle"])
    validate(_MODELS["appliance"])
