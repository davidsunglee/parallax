"""``parallax.descriptor._family``: the pre-formation inheritance-family
validator a caller reaches through the public
:func:`~parallax.descriptor.validate_inheritance_families` door."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, cast

import pytest

from parallax.conformance import case_format
from parallax.core.inheritance import InheritanceError
from parallax.descriptor import validate_inheritance_families
from parallax.descriptor._family import validate_families
from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel
from tests.unit._corpus_model_support import corpus_records

_REPO = case_format.find_repo_root()
_MODELS = corpus_records()
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
_FORMATION_OWNED_RULES: Final[frozenset[str]] = frozenset(
    {
        "inheritance-materialization-key-collision",
        "inheritance-concrete-subtype-with-children",
    }
)
"""The family rules whose defects survive adaptation into the accepted algebra,
so formation reports them and this walk never has to."""
_RAW_ONLY_REJECTIONS = [
    rejection for rejection in _REJECTIONS if rejection[2] not in _FORMATION_OWNED_RULES
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
    assert len(_RAW_ONLY_REJECTIONS) == 19


@pytest.mark.parametrize(
    "stem, model, rule", _RAW_ONLY_REJECTIONS, ids=[r[0] for r in _RAW_ONLY_REJECTIONS]
)
def test_rejected_descriptor_classifies_with_its_corpus_rule(
    stem: str, model: dict[str, Any], rule: str
) -> None:
    with pytest.raises(InheritanceError) as caught:
        validate_inheritance_families(model)
    assert caught.value.rule == rule


def test_valid_inheritance_family_passes_validation() -> None:
    validate_families(_MODELS["animal"])  # no raise
    validate_families(_MODELS["document"])
    validate_families(_MODELS["vehicle"])


def test_non_inheritance_descriptor_validates_trivially() -> None:
    validate_families(_MODELS["account"])  # no participants, no raise


def test_independent_families_in_one_descriptor_pass_validation() -> None:
    # `workshop` declares two families that share no ancestry, each under its own
    # strategy: resolving one strategy for the whole descriptor would apply the
    # table-per-hierarchy shared-table rule to the table-per-concrete-subtype family.
    validate_families(_MODELS["workshop"])  # no raise


def test_a_rootless_family_beside_a_rooted_one_is_rejected() -> None:
    # A rooted family does not answer for its neighbour: the abstract-orphan chain
    # reaches no root of its own and is still rejected.
    document = {
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
    with pytest.raises(InheritanceError) as caught:
        validate_inheritance_families(document)
    assert caught.value.rule == "inheritance-missing-root"


def test_two_families_with_same_named_roots_in_different_namespaces_stay_apart() -> None:
    # A local Entity name may be declared in more than one namespace of one
    # model, roots included. Family membership therefore has to key on the
    # root's CANONICAL identity: keyed on the bare one, both families answer
    # "Record" and merge, so one root's table-per-hierarchy rules judge the other
    # family's members.
    document = {
        "entities": [
            {
                "name": "Record",
                "namespace": namespace,
                "table": f"{namespace}_record",
                "inheritance": {
                    "role": "root",
                    "strategy": "table-per-hierarchy",
                    "tag": {"column": "kind"},
                },
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            }
            for namespace in ("catalog", "archive")
        ]
        + [
            {
                "name": "Variant",
                "namespace": namespace,
                "inheritance": {
                    "role": "concrete-subtype",
                    "parent": f"{namespace}.Record",
                    "tagValue": "variant",
                },
            }
            for namespace in ("catalog", "archive")
        ]
    }
    validate_inheritance_families(document)  # no raise


def test_a_bare_parent_reaches_its_own_namespaces_root() -> None:
    # Each subtype below spells its parent bare, and the local name `Record`
    # names a root in two namespaces. A bare parent is relative to the declaring
    # entity's namespace, so both sides still reach a root: read as a model-wide
    # name, neither would, and each subtype would name a parent the descriptor
    # does not declare.
    validate_inheritance_families(
        {
            "entities": [
                {
                    "name": "Record",
                    "namespace": "catalog",
                    "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                    "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                },
                {
                    "name": "Record",
                    "namespace": "archive",
                    "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                    "attributes": [{"name": "archiveId", "type": "int64", "primaryKey": True}],
                },
                {
                    "name": "CatalogVariant",
                    "namespace": "catalog",
                    "table": "catalog_variant",
                    "inheritance": {"role": "concrete-subtype", "parent": "Record"},
                },
                {
                    "name": "ArchiveVariant",
                    "namespace": "archive",
                    "table": "archive_variant",
                    "inheritance": {"role": "concrete-subtype", "parent": "Record"},
                },
            ]
        }
    )  # no raise


def test_a_bare_parent_is_never_read_across_a_namespace_boundary() -> None:
    # Resolution has no model-wide unique-name fallback: a bare parent the
    # declaring namespace does not declare reaches nothing, even when exactly
    # one entity of the whole model carries that local name. Adopting the other
    # namespace's `Record` would enrol this leaf in a foreign family.
    with pytest.raises(InheritanceError) as caught:
        validate_inheritance_families(
            {
                "entities": [
                    {
                        "name": "Record",
                        "namespace": "catalog",
                        "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                        "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                    },
                    {
                        "name": "StrayLeaf",
                        "namespace": "elsewhere",
                        "table": "stray_leaf",
                        "inheritance": {"role": "concrete-subtype", "parent": "Record"},
                    },
                ]
            }
        )
    assert caught.value.rule == "inheritance-unknown-parent"
    assert caught.value.entity == "StrayLeaf"


def test_a_chain_that_repeats_a_local_name_is_no_cycle() -> None:
    # A local Entity name may be declared in more than one namespace, so two
    # positions of ONE valid chain may share it. The cycle guard therefore has
    # to remember canonical identities: keyed on the bare name, reaching the
    # second `Node` looks like a revisit and the walk reports a cycle the
    # descriptor never declared.
    validate_inheritance_families(
        {
            "entities": [
                {
                    "name": "Root",
                    "namespace": "top",
                    "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                    "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                },
                {
                    "name": "Node",
                    "namespace": "mid",
                    "inheritance": {"role": "abstract-subtype", "parent": "top.Root"},
                },
                {
                    "name": "Node",
                    "namespace": "leaf",
                    "table": "leaf_node",
                    "inheritance": {"role": "concrete-subtype", "parent": "mid.Node"},
                },
            ]
        }
    )  # no raise


def _minimal_attrs() -> tuple[Attribute, ...]:
    return (Attribute(name="id", type="int64", column="id", primary_key=True),)


def test_reject_descendant_temporality_under_a_non_temporal_root() -> None:
    # A non-temporal TPH root with an abstract-subtype declaring its own profile.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        temporality="transaction-time",
    )
    dog = Entity(
        name="Dog",
        inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog"),
        attributes=(Attribute(name="barkVolume", type="int32", column="bark_volume"),),
    )
    meta = Metamodel(entities=(root, pet, dog))
    with pytest.raises(InheritanceError) as caught:
        validate_families(meta)
    assert caught.value.rule == "inheritance-temporality-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_temporality_under_a_temporal_root() -> None:
    # A temporal TPCS root whose concrete subtype widens the family profile.
    root = Entity(
        name="Rate",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=_minimal_attrs(),
        temporality="transaction-time",
    )
    deposit = Entity(
        name="DepositRate",
        table="deposit_rate",
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
        attributes=(Attribute(name="grade", type="string", column="grade"),),
        temporality="bitemporal",
    )
    meta = Metamodel(entities=(root, deposit))
    with pytest.raises(InheritanceError) as caught:
        validate_families(meta)
    assert caught.value.rule == "inheritance-temporality-not-root-owned"
    assert caught.value.entity == "DepositRate"


def test_temporal_root_and_root_owned_profile_still_validate_cleanly() -> None:
    # A well-formed family (the profile declared ONLY on the root) passes
    # validation — the invariant must not reject the corpus's own families.
    validate_families(_MODELS["rate"])
    validate_families(_MODELS["instrument"])


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
        validate_families(meta)
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
        validate_families(meta)
    assert caught.value.rule == "inheritance-optimistic-locking-not-root-owned"
    assert caught.value.entity == "Fridge"


def test_versioned_root_and_root_owned_version_still_validates_cleanly() -> None:
    # A well-formed family (the version declared ONLY on the root) passes
    # validation — the new invariant must not reject the corpus's own
    # root-declared versioned families.
    validate_families(_MODELS["vehicle"])
    validate_families(_MODELS["appliance"])
