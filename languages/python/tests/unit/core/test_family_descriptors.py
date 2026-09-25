"""Family-descriptor unit tests over every compatibility-corpus model.

Every accepted Entity, a standalone one being its own family, reads four
family-wide facts from formation: its root's Metadata, the family primary key,
the temporal shape, and the optimistic key. What a write addresses and what a
read retains rest on every position answering exactly its root's facts, so this
suite grades the owners over the whole corpus rather than through one fixture:
each position answers its root's objects by identity, and the family key is the
one the root declares itself. Formation is what makes the root's own
declaration the family's answer: `m-inheritance` "One family primary key" is
asked of EVERY position's applicable ancestry chain, and a root's chain is the
root alone, so a key declared below the root leaves the root's own chain
without one.

Family-shape resolution AS A WHOLE stays covered by the `m-inheritance-*` corpus
cases and by the downstream suites that write and read through these owners.
"""

from __future__ import annotations

from typing import Final

import pytest

from parallax.core import inheritance, opt_lock, temporal_read
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
from tests.unit._corpus_model_support import corpus

_CORPUS: Final[tuple[str, ...]] = tuple(sorted(corpus()))

# The corpus models declaring an inheritance family, exactly. Held as a literal
# so the shapes the equivalence is measured over stay legible, and checked
# against the corpus itself below so the list cannot quietly stop being true.
_FAMILIES: Final[tuple[str, ...]] = (
    "animal",
    "appliance",
    "document",
    "document-layout",
    "evolution-branch-move-v1",
    "evolution-branch-move-v2",
    "evolution-concrete-subtype-tables-v1",
    "evolution-concrete-subtype-tables-v2",
    "evolution-crossing-family-v1",
    "evolution-crossing-family-v2",
    "evolution-departing-domain-v1",
    "evolution-departing-domain-v2",
    "evolution-departing-shape-v1",
    "evolution-departing-shape-v2",
    "evolution-hierarchy-v1",
    "evolution-hierarchy-v2",
    "evolution-inherited-column-v1",
    "evolution-inherited-column-v2",
    "evolution-interposed-subtype-v1",
    "evolution-interposed-subtype-v2",
    "evolution-position-role-v1",
    "evolution-position-role-v2",
    "evolution-rowless-branch-v1",
    "evolution-rowless-branch-v2",
    "evolution-rowless-domain-v1",
    "evolution-rowless-domain-v2",
    "evolution-rowless-member-v1",
    "evolution-rowless-member-v2",
    "evolution-rowless-position-v1",
    "evolution-rowless-position-v2",
    "instrument",
    "materialization-key-compatibility",
    "materialization-stress-columns",
    "materialization-stress-document",
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

# Every temporal shape and optimistic key a family can carry, each witnessed at
# a position below its root, where sharing the root's object is the claim.
_EVERY_INHERITED_FACT: Final[frozenset[str]] = frozenset(
    {
        "NonTemporal",
        "TransactionTimeOnly",
        "Bitemporal",
        "Unversioned",
        "ExplicitVersion",
        "TransactionTimeDerived",
    }
)

# `Animal -> Pet -> Dog` and `Document -> FinancialDocument -> Invoice`: an
# inherited key resolved two levels below the ancestor that introduced it.
_DEEPEST_ANCESTRY: Final[int] = 3


def _locally_declared_primary_key(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """The primary key ``entity``'s OWN local declaration carries, in declared
    order — the root-local reading the family's owner is measured against.
    """
    return tuple(
        attribute
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )


def _family_shape(model: Metamodel, entity: EntityMetadata, position: InheritanceMetadata) -> str:
    families = inheritance.view(model)
    strategy = inheritance.root_metadata(families, model, entity.identity).inheritance
    strategy_name = (
        "table-per-hierarchy"
        if isinstance(strategy, AbstractRoot) and isinstance(strategy.strategy, TablePerHierarchy)
        else "table-per-concrete-subtype"
    )
    if isinstance(position, AbstractRoot):
        return f"{strategy_name} root"
    if isinstance(position, AbstractSubtype):
        return f"{strategy_name} abstract subtype"
    return f"{strategy_name} concrete subtype"


def _divergent_owners(model: Metamodel, entity: EntityMetadata) -> list[str]:
    """Each family fact ``entity`` does not answer with its root's own object."""
    families = inheritance.view(model)
    temporal = temporal_read.view(model)
    keys = opt_lock.view(model)
    view = families.entity(entity.identity)
    assert view is not None
    root_view = families.entity(view.root)
    assert root_view is not None
    root = inheritance.root_metadata(families, model, entity.identity)
    divergent: list[str] = []
    if root is not model.entity(view.root):
        divergent.append("root")
    if (view.primary_key,) != _locally_declared_primary_key(root):
        divergent.append("declared key")
    if view.primary_key is not root_view.primary_key:
        divergent.append("key")
    if temporal.shape(entity.identity) is not temporal.shape(view.root):
        divergent.append("temporal shape")
    if keys.key(entity.identity) is not keys.key(view.root):
        divergent.append("optimistic key")
    return divergent


@pytest.mark.parametrize("stem", _CORPUS)
def test_every_position_reads_its_roots_family_facts_by_identity(stem: str) -> None:
    model = corpus()[stem]
    divergent = {
        entity.identity.canonical: facts
        for entity in model.entities
        if (facts := _divergent_owners(model, entity))
    }
    assert divergent == {}


def test_the_measured_families_span_both_strategies_every_position_and_every_fact() -> None:
    """What makes the sweep above a statement about inheritance.

    It is measured over the whole corpus, most of which is standalone
    Entities the equivalence holds trivially for. This is the witness that the
    corpus they walk really does declare both strategies at every position, an
    ancestry deep enough for a key to be inherited across an intermediate
    abstract position rather than straight from a parent, and every temporal
    shape and optimistic key at a position that inherits it.
    """
    declared = tuple(
        stem for stem in _CORPUS if any(e.inheritance is not None for e in corpus()[stem].entities)
    )
    shapes: set[str] = set()
    ancestries: set[int] = set()
    inherited: set[str] = set()
    for stem in _FAMILIES:
        model = corpus()[stem]
        facet = inheritance.view(model)
        temporal = temporal_read.view(model)
        keys = opt_lock.view(model)
        for entity in model.entities:
            position = entity.inheritance
            if position is None:
                continue
            shapes.add(_family_shape(model, entity, position))
            view = facet.entity(entity.identity)
            assert view is not None
            ancestries.add(len(view.ancestry))
            if view.root != entity.identity:
                inherited.add(type(temporal.shape(entity.identity)).__name__)
                inherited.add(type(keys.key(entity.identity)).__name__)
    assert declared == _FAMILIES
    assert shapes == _EVERY_FAMILY_SHAPE
    assert max(ancestries) == _DEEPEST_ANCESTRY
    assert inherited == _EVERY_INHERITED_FACT
