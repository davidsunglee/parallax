"""m-inheritance: family model, effective concrete sets, and descriptor rejection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    deserialize,
)

pytestmark = pytest.mark.unit

_REPO = case_format.find_repo_root()
_MODELS = corpus_models.load_models(_REPO / "core" / "compatibility" / "models")
_CASES = _REPO / "core" / "compatibility" / "cases"


def _descriptor_rejection_cases() -> list[tuple[str, dict[str, Any], str]]:
    found: list[tuple[str, dict[str, Any], str]] = []
    for path in sorted(_CASES.glob("m-inheritance-0*-rejected-*.yaml")):
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        document = cast("dict[str, Any]", loaded)
        when = document.get("when")
        if isinstance(when, dict) and "model" in when:
            model = cast("dict[str, Any]", when["model"])
            then = cast("dict[str, Any]", document["then"])
            found.append((path.stem, model, str(then["rejectedRule"])))
    return found


_REJECTIONS = _descriptor_rejection_cases()


def test_every_descriptor_rejection_case_is_covered() -> None:
    # 15 inline-descriptor inheritance rejection cases carry `when.model` (13
    # original + the two root-ownership witnesses, m-inheritance-098/099).
    assert len(_REJECTIONS) == 15


@pytest.mark.parametrize("stem, model, rule", _REJECTIONS, ids=[r[0] for r in _REJECTIONS])
def test_rejected_descriptor_classifies_with_its_corpus_rule(
    stem: str, model: dict[str, Any], rule: str
) -> None:
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(deserialize(model))
    assert caught.value.rule == rule


def test_valid_inheritance_family_passes_validation() -> None:
    inheritance.validate(_MODELS["animal"])  # no raise
    inheritance.validate(_MODELS["document"])
    inheritance.validate(_MODELS["vehicle"])


def test_non_inheritance_descriptor_validates_trivially() -> None:
    inheritance.validate(_MODELS["account"])  # no participants, no raise


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ("Animal", ("Cat", "Dog", "WildBoar")),
        ("Pet", ("Cat", "Dog")),
        ("Dog", ("Dog",)),
        ("Person", ("Person",)),
    ],
)
def test_effective_concrete_subtypes_is_alphabetical(
    position: str, expected: tuple[str, ...]
) -> None:
    assert inheritance.effective_concrete_subtypes(_MODELS["animal"], position) == expected


def test_family_of_reports_the_single_root_and_strategy() -> None:
    family = inheritance.family_of(_MODELS["animal"])
    assert family.root is not None
    assert family.root.name == "Animal"
    assert family.strategy == "table-per-hierarchy"


def test_family_of_is_empty_without_participants() -> None:
    family = inheritance.family_of(_MODELS["account"])
    assert family.root is None
    assert family.strategy is None
    assert family.participants == ()


def test_inheritance_error_carries_rule_and_entity() -> None:
    error = inheritance.InheritanceError("inheritance-cycle", "boom", entity="Pet")
    assert error.rule == "inheritance-cycle"
    assert error.entity == "Pet"


def test_ancestor_chain_orders_root_first_then_deeper_abstract_nodes() -> None:
    animal = _MODELS["animal"]
    assert [e.name for e in inheritance.ancestor_chain(animal, ("Cat", "Dog"))] == [
        "Animal",
        "Pet",
    ]
    # WildBoar's own chain is just the root (a sibling branch directly under it).
    assert [e.name for e in inheritance.ancestor_chain(animal, ("WildBoar",))] == ["Animal"]


def test_family_attributes_widens_across_the_whole_family() -> None:
    animal = _MODELS["animal"]
    names = {attr.name for attr in inheritance.family_attributes(animal, animal.entity("Dog"))}
    assert names == {"id", "name", "ownerId", "licenseId", "barkVolume", "indoor", "tuskLength"}


def test_family_attributes_is_the_entitys_own_attributes_outside_a_family() -> None:
    account = _MODELS["account"]
    entity = account.entity("Account")
    assert inheritance.family_attributes(account, entity) == entity.attributes


def test_family_root_resolves_the_abstract_root() -> None:
    animal = _MODELS["animal"]
    assert inheritance.family_root(animal, animal.entity("Dog")).name == "Animal"
    assert inheritance.family_root(animal, animal.entity("Animal")).name == "Animal"


def test_family_root_raises_on_a_malformed_ancestry() -> None:
    # A concrete-subtype whose parent chain cycles rather than reaching a root.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    cyclic = Metamodel(
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
    with pytest.raises(ValueError, match="no resolvable inheritance root"):
        inheritance.family_root(cyclic, cyclic.entity("A"))


def test_concrete_descendants_terminates_on_a_cyclic_family() -> None:
    # A malformed (cyclic) family: `concrete_descendants` must still terminate.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    cyclic = Metamodel(
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
    assert inheritance.family_of(cyclic).concrete_descendants("A") == frozenset({"A", "B"})


# --------------------------------------------------------------------------- #
# Binding decision (COR-3 Phase 7 review remediation, P3/P4): temporality is a #
# family-wide property; only the root may declare `asOfAttributes`, and every #
# descendant — abstract-subtype or concrete-subtype — inherits exactly that   #
# set. `declaring_entity` always resolves to the family root; a non-root      #
# participant that declares its own axes is rejected pre-SQL.                 #
# --------------------------------------------------------------------------- #
def _synthetic_temporal_family() -> Metamodel:
    """A THREE-level TPH family — Root (temporal) -> Mid (abstract-subtype) ->
    Leaf (concrete) — proving `declaring_entity` resolves to the root from
    EVERY position in the chain, not just the immediate parent."""
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    mid = Entity(
        name="Mid",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
    )
    leaf = Entity(
        name="Leaf",
        table="root_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Mid", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, mid, leaf))


def test_declaring_entity_resolves_to_the_family_root_from_every_position() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        declaring = inheritance.declaring_entity(meta, meta.entity(name))
        assert declaring.name == "Root", name
        assert declaring.as_of_attributes == meta.entity("Root").as_of_attributes


def test_declaring_entity_is_the_entity_itself_outside_a_family() -> None:
    # A non-inheritance temporal entity remains unaffected: `declaring_entity`
    # is a strict identity for it (m-inheritance only applies within a family).
    plain = Entity(
        name="Balance",
        table="balance",
        attributes=(Attribute(name="id", type="int64", column="bal_id", primary_key=True),),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    meta = Metamodel(entities=(plain,))
    assert inheritance.declaring_entity(meta, plain) is plain


def _minimal_attrs() -> tuple[Attribute, ...]:
    return (Attribute(name="id", type="int64", column="id", primary_key=True),)


def test_reject_descendant_temporal_axes_under_a_non_temporal_root() -> None:
    # A non-temporal TPH root with an abstract-subtype that declares its own axes.
    root = Entity(
        name="Animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
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
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_temporal_axes_under_a_temporal_root() -> None:
    # A temporal TPCS root whose concrete subtype adds its own second axis.
    root = Entity(
        name="Rate",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=_minimal_attrs(),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    deposit = Entity(
        name="DepositRate",
        table="deposit_rate",
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
        attributes=(Attribute(name="grade", type="string", column="grade"),),
        as_of_attributes=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
        ),
    )
    meta = Metamodel(entities=(root, deposit))
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "DepositRate"


def test_temporal_root_and_root_owned_axes_still_validate_cleanly() -> None:
    # A well-formed family (axes declared ONLY on the root) passes validation —
    # the new invariant must not reject the corpus's own root-declared families.
    inheritance.validate(_MODELS["rate"])
    inheritance.validate(_MODELS["instrument"])
