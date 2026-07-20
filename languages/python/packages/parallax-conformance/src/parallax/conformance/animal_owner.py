"""``models/animal.yaml``'s own polymorphic owner (``Person``), installed for
real (ledger D-20, COR-3 Phase 8 increment 7).

``models/animal.yaml``'s owner entity is ALSO named ``Person`` — the same
literal canonical name ``read_models.Person`` (``models/person.yaml``)
already claims in the process :func:`~parallax.core.entity.base.default_registry`.
Before ledger D-20 this was a structural, unliftable collision (a single,
flat, process-wide class registry); the fix is an explicit
:class:`~parallax.core.entity.base.EntityRegistry` scope: ``ANIMAL_OWNER_REGISTRY``
here is a SEPARATE registry (its ``parent`` defaults to the process
:func:`~parallax.core.entity.base.default_registry`, so it still resolves
``Animal`` / ``Pet`` / ``Dog`` / ``Cat`` from ``read_models.py`` without
redeclaring them) that shadows the default registry's own ``Person`` with
THIS family's real owner, never colliding with it.

A ``Database`` exercising the animal-owner relationship connects with
``ANIMAL_OWNER_REGISTRY.metamodel()`` (never the bare ``metamodel(classes)``
helper, and never an ingested corpus descriptor) so ``db.find`` resolves
``Person`` through THIS scope specifically (`parallax.snapshot.handle`'s D-20
bridge, ``registry_of`` / ``resolve_entity_class``) — the SAME real
``rel: Person.pets`` / ``Person.animals`` operation text the corpus's own
``models/animal.yaml`` authors, at last reproducible from a production-reachable
mirror (`m-inheritance-064..067`/`-072`, `m-snapshot-read-012`).

Owned by ``parallax.conformance`` for the same package-boundary reason
``read_models``/``story_models``/``graph_models`` are (spec §7/§8): a
dev-only package module resolvable at ordinary import time. This module
deliberately avoids ``from __future__ import annotations`` so the metaclass
reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from parallax.conformance.read_models import Animal, Pet
from parallax.core import Attr, Entity, EntityConfig, Field, Rel, Relationship
from parallax.core.entity.base import EntityRegistry

_NS = "parallax.compatibility"

__all__ = ["ANIMAL_OWNER_REGISTRY", "Person"]

# Parent defaults to the process `default_registry()` -- `Animal`/`Pet`/`Dog`/
# `Cat` (registered there by `read_models.py`) resolve through this registry's
# own parent-chain delegation, so this scope needs to declare only the ONE
# name that actually collides.
ANIMAL_OWNER_REGISTRY = EntityRegistry()


class Person(Entity, frozen=True, registry=ANIMAL_OWNER_REGISTRY):
    """Mirror of ``models/animal.yaml``'s own polymorphic owner ``Person`` —
    NOT ``read_models.Person`` (``models/person.yaml``'s unrelated one-to-one
    Passport owner): the two share a canonical name but live in separate
    registries (ledger D-20)."""

    __parallax__ = EntityConfig(table="person", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=32)
    animals: Rel[tuple[Animal, ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Animal.ownerId",
        related_entity="Animal",
        reverse_name="owner",
        foreign_key="owner_id",
    )
    pets: Rel[tuple[Pet, ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Pet.ownerId",
        related_entity="Pet",
        reverse_name="owner",
        foreign_key="owner_id",
    )
