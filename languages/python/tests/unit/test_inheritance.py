"""m-inheritance: family model, effective concrete sets, and descriptor rejection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core.descriptor import Attribute, Entity, Inheritance, Metamodel, deserialize

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
    # 13 inline-descriptor inheritance rejection cases carry `when.model`.
    assert len(_REJECTIONS) == 13


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
