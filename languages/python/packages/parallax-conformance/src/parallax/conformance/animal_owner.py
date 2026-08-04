"""``models/animal.yaml``'s own polymorphic owner, and the family's model.

``models/animal.yaml`` declares an owner entity also named ``Person`` — the same
canonical name ``read_models.Person`` (``models/person.yaml``) carries. Two
models each naming a ``Person`` is unremarkable once a model is an explicit
class set: this owner and that one are different classes in different models, and
neither can see the other.

The Domain Model below is the whole of ``models/animal.yaml``: the owner plus
the family it names. It lives here rather than beside the family in
:mod:`parallax.conformance.read_models` because a model composes the complete
class set, and the owner is declared here.

This module deliberately avoids ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from parallax.conformance.read_models import Animal, Cat, Dog, Pet, WildBoar
from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Rel, attr, rel

_NS = "parallax.compatibility"

__all__ = ["ANIMAL_MODEL", "Person"]


class Person(
    Entity,
    table="person",
    namespace=_NS,
):
    """``models/animal.yaml``'s polymorphic owner — NOT ``read_models.Person``
    (``models/person.yaml``'s unrelated one-to-one Passport owner)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    animals: Rel[tuple[Animal, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))
    pets: Rel[tuple[Pet, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))


ANIMAL_MODEL = DomainModel(Person, Animal, Pet, Dog, Cat, WildBoar)
"""``models/animal.yaml`` as one sealed model: the owner plus the whole family
it names, which is what a ``Database`` exercising this family connects with."""
