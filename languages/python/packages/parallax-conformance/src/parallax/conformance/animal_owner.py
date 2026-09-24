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
