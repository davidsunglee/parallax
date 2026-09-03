"""Family-descriptor unit tests (`parallax.snapshot.handle._family`).

Drives :func:`family_primary_key` over every compatibility-corpus model rather
than through a downstream module, because what it answers is a property of the
whole declared family and a standalone Entity is the degenerate case of one.

The property pinned here is the one the write side rests on: for a family's
DECLARING ROOT, the family-effective primary key resolved through the applicable
member chain is exactly the primary key that root declares locally, in exactly
that order — and every position of the family, abstract or concrete, resolves the
same key its root does. `m-inheritance` "One family primary key" constrains only
the CARDINALITY of the key across the applicable chain and leaves declaration
identity with the ancestor that introduced it, so a primary key declared below
the root is a legal shape in principle. This suite is what says the corpus
declares none; a model that grew one would fail here rather than silently
changing which object a write addresses.

Family-shape resolution AS A WHOLE stays covered by the `m-inheritance-*` corpus
cases and by the downstream suites that write and read through these helpers.
"""

from __future__ import annotations

from typing import Final

import pytest
from _corpus_model_support import corpus

from parallax.core import inheritance
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    EntityMetadata,
    InheritanceMetadata,
    Metamodel,
    PrimaryKey,
    TablePerHierarchy,
)
from parallax.snapshot.handle._family import declaring, family_primary_key

_CORPUS: Final[tuple[str, ...]] = tuple(sorted(corpus()))

# The corpus models declaring an inheritance family, exactly. Held as a literal
# so the shapes the equivalence is measured over stay legible, and checked
# against the corpus itself below so the list cannot quietly stop being true.
_FAMILIES: Final[tuple[str, ...]] = (
    "animal",
    "appliance",
    "document",
    "document-layout",
    "instrument",
    "materialization-key-compatibility",
    "payment",
    "quote",
    "rate",
    "reading",
    "storage-layout",
    "vehicle",
    "workshop",
)

# Every combination of root-owned strategy and family position the corpus
# declares. Both strategies at all three positions, which is what makes the
# equivalence above a statement about families rather than about one shape.
_EVERY_FAMILY_SHAPE: Final[frozenset[str]] = frozenset(
    {
        "table-per-hierarchy root",
        "table-per-hierarchy abstract subtype",
        "table-per-hierarchy concrete subtype",
        "table-per-concrete-subtype root",
        "table-per-concrete-subtype abstract subtype",
        "table-per-concrete-subtype concrete subtype",
    }
)

# `Animal -> Pet -> Dog` and `Document -> FinancialDocument -> Invoice`: an
# inherited key resolved two levels below the ancestor that introduced it.
_DEEPEST_ANCESTRY: Final[int] = 3


def _locally_declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """The primary key ``entity``'s OWN local declaration carries.

    The second reading the keyed write inputs once held, restated here so the
    equivalence stays provable now that only :func:`family_primary_key` remains.
    """
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _family_shape(model: Metamodel, entity: EntityMetadata, position: InheritanceMetadata) -> str:
    strategy = declaring(model, entity).inheritance
    named = (
        "table-per-hierarchy"
        if isinstance(strategy, AbstractRoot) and isinstance(strategy.strategy, TablePerHierarchy)
        else "table-per-concrete-subtype"
    )
    if isinstance(position, AbstractRoot):
        return f"{named} root"
    if isinstance(position, AbstractSubtype):
        return f"{named} abstract subtype"
    return f"{named} concrete subtype"


@pytest.mark.parametrize("stem", _CORPUS)
def test_a_declaring_root_resolves_the_primary_key_it_declares_itself(stem: str) -> None:
    model = corpus()[stem]
    divergent = {
        root.identity.canonical
        for entity in model.entities
        if family_primary_key(model, (root := declaring(model, entity)))
        != _locally_declared_primary_key(root)
    }
    assert divergent == set()


@pytest.mark.parametrize("stem", _CORPUS)
def test_a_family_position_resolves_the_primary_key_its_declaring_root_does(stem: str) -> None:
    model = corpus()[stem]
    divergent = {
        entity.identity.canonical
        for entity in model.entities
        if family_primary_key(model, entity) != family_primary_key(model, declaring(model, entity))
    }
    assert divergent == set()


def test_the_measured_families_span_both_strategies_and_every_position() -> None:
    """What makes the two equivalences above statements about inheritance.

    Both are measured over the whole corpus, most of which is standalone
    Entities the equivalence holds trivially for. This is the witness that the
    corpus the other two walk really does declare both strategies at every
    position, and an ancestry deep enough for a key to be inherited across an
    intermediate abstract position rather than straight from a parent.
    """
    declared = tuple(
        stem for stem in _CORPUS if any(e.inheritance is not None for e in corpus()[stem].entities)
    )
    shapes: set[str] = set()
    ancestries: set[int] = set()
    for stem in _FAMILIES:
        model = corpus()[stem]
        facet = inheritance.view(model)
        for entity in model.entities:
            position = entity.inheritance
            if position is None:
                continue
            shapes.add(_family_shape(model, entity, position))
            view = facet.entity(entity.identity)
            assert view is not None
            ancestries.add(len(view.ancestry))
    assert declared == _FAMILIES
    assert shapes == _EVERY_FAMILY_SHAPE
    assert max(ancestries) == _DEEPEST_ANCESTRY
