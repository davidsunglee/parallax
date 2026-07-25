"""``parallax.core.entity._family``: the entity scope's own raw-descriptor
inheritance-family walk (:func:`family_root`, :func:`effective_concrete_subtypes`)."""

from __future__ import annotations

from typing import Final, cast

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.descriptor import Attribute, Entity, Inheritance, Metamodel, unresolved_metamodel
from parallax.core.entity._family import effective_concrete_subtypes, family_root
from parallax.core.metamodel import EntityIdentity

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)
_CORPUS_NAMESPACE: Final[str] = "parallax.compatibility"


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
    assert effective_concrete_subtypes(_MODELS["animal"], position) == expected


@pytest.mark.parametrize(
    "names",
    [("Animal",), ("Pet",), ("Dog",), ("Cat", "WildBoar"), ("Pet", "Dog"), ("Person",)],
    ids=lambda names: "+".join(cast("tuple[str, ...]", names)),
)
def test_the_walk_resolves_the_same_effective_set_the_facet_does(
    names: tuple[str, ...],
) -> None:
    # A narrowed relationship view is keyed by its resolved effective
    # concrete-subtype set, and the two resolutions that can produce that key
    # must never disagree: a read keys the view through the Inheritance Facet,
    # while a registry chain that cannot form falls back to this walk. A
    # divergence would key a view under a name the read that produced it never
    # wrote, silently reporting the relationship as unloaded.
    records = _MODELS["animal"]
    facet = inheritance.view(form_metamodel(unresolved_metamodel(records)))
    position = facet.position([EntityIdentity(_CORPUS_NAMESPACE, name) for name in names])
    assert position is not None
    assert [member.name for member in position.concrete_subtypes] == sorted(
        {concrete for name in names for concrete in effective_concrete_subtypes(records, name)}
    )


def test_family_root_resolves_the_abstract_root() -> None:
    animal = _MODELS["animal"]
    assert family_root(animal, animal.entity("Dog")).name == "Animal"
    assert family_root(animal, animal.entity("Animal")).name == "Animal"


def test_family_root_raises_for_a_non_participant() -> None:
    plain = Entity(
        name="Plain",
        table="plain",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    meta = Metamodel(entities=(plain,))
    with pytest.raises(ValueError, match="no resolvable inheritance root"):
        family_root(meta, plain)


def test_effective_concrete_subtypes_terminates_on_a_cyclic_family() -> None:
    # A malformed (self-referential) family: the descendant walk must still terminate.
    cyclic = Metamodel(
        entities=(Entity(name="R", inheritance=Inheritance(role="abstract-subtype", parent="R")),)
    )
    assert effective_concrete_subtypes(cyclic, "R") == ()


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
        family_root(cyclic, cyclic.entity("A"))
