"""The exact-model layout catalog: positions, keys, order, and refusals.

Four claims, in the order the catalog fixes them. **Positions** are a function
of the accepted Metamodel alone, so the whole corpus is graded against the
family-effective member set every other read path already agrees on.
**Agreement** holds the layout's family, logical key, and view order against the
merge-side rules they restate, so neither statement of either rule can move
without the other. **Ownership** is the catalog a Domain Model retains, reached
through one door, with entries derived on first reach. **Refusals** are raised
errors rather than stored-data classifications, because a row cannot contradict
a position the model itself failed to fix.

The defect witnesses are doctored models rather than authored ones: an accepted
Metamodel is exactly what cannot carry these shapes — formation refuses a
duplicate member and admits one primary-key Attribute per Entity — so the only
way to reach the checks is to hand the catalog metadata that contradicts itself
after formation accepted it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from _corpus_model_support import corpus, target
from _corpus_model_support import model as corpus_model

from parallax.conformance import models
from parallax.core.entity._layout import (
    CatalogedModel,
    EntityLayout,
    LayoutCatalog,
    ValueObjectLayout,
)
from parallax.core.entity._model import cataloged_model, model_of
from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    FacetKey,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    RelationshipIdentity,
    ValueObjectMetadata,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize import RelationshipViewKey, merge_graph_input
from parallax.snapshot.materialize._graph import GraphBuilder
from parallax.snapshot.materialize._views import ROOT_LEVEL, ViewSchema

_NAMESPACE = "parallax.compatibility"
_COMPOSITE_KEY = frozenset({"id", "sku"})


def _identity(name: str, *, namespace: str | None = _NAMESPACE) -> EntityIdentity:
    return EntityIdentity(namespace, name)


def _view(model: Metamodel, identity: EntityIdentity) -> InheritanceEntityView:
    position = inheritance_view(model).entity(identity)
    assert position is not None, identity
    return position


# --------------------------------------------------------------------------- #
# Doctoring: an accepted model whose family-effective view says something its   #
# formation would never have accepted.                                         #
# --------------------------------------------------------------------------- #


class _DoctoredView:
    """One family-effective view with its applicable Attributes replaced."""

    def __init__(
        self, real: InheritanceEntityView, attributes: Sequence[AttributeMetadata]
    ) -> None:
        self._real = real
        self.applicable_attributes = tuple(attributes)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _DoctoredFacet:
    """The real Inheritance Facet with one Entity's view replaced."""

    def __init__(
        self, real: InheritanceFacet, identity: EntityIdentity, view: InheritanceEntityView
    ) -> None:
        self._real = real
        self._identity = identity
        self._view = view

    def entity(self, identity: EntityIdentity) -> InheritanceEntityView | None:
        return self._view if identity == self._identity else self._real.entity(identity)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _DoctoredModel:
    """One accepted model with a replaced Inheritance Facet, local metadata, or both."""

    def __init__(
        self,
        real: Metamodel,
        *,
        facet: InheritanceFacet | None = None,
        entities: dict[EntityIdentity, Any] | None = None,
    ) -> None:
        self._real = real
        self._facet = facet
        self._entities = entities or {}

    @property
    def entities(self) -> Sequence[Any]:
        return self._real.entities

    def entity(self, identity: EntityIdentity) -> Any:
        replacement = self._entities.get(identity)
        return self._real.entity(identity) if replacement is None else replacement

    def facet[T](self, key: FacetKey[T]) -> T:
        if self._facet is not None and key == INHERITANCE_FACET_KEY:
            return cast("T", self._facet)
        return self._real.facet(key)


def _with_applicable_attributes(
    model: Metamodel, identity: EntityIdentity, attributes: Sequence[AttributeMetadata]
) -> Metamodel:
    """``model`` answering ``attributes`` as ``identity``'s applicable set."""
    doctored = cast("InheritanceEntityView", _DoctoredView(_view(model, identity), attributes))
    facet = cast("InheritanceFacet", _DoctoredFacet(inheritance_view(model), identity, doctored))
    return cast("Metamodel", _DoctoredModel(model, facet=facet))


# --------------------------------------------------------------------------- #
# Positions: the whole corpus, graded against the family-effective member set.  #
# --------------------------------------------------------------------------- #


def _corpus_layouts() -> Iterable[tuple[str, Metamodel, EntityIdentity, EntityLayout]]:
    for stem, model in sorted(corpus().items()):
        catalog = LayoutCatalog(model)
        for entity in model.entities:
            yield stem, model, entity.identity, catalog.entity(entity.identity)


def test_every_corpus_entity_lays_out_its_family_effective_members_in_order() -> None:
    for stem, model, identity, layout in _corpus_layouts():
        position = _view(model, identity)
        attributes = tuple(position.applicable_attributes)
        occurrences = tuple(position.applicable_value_objects)
        where = (stem, identity.canonical)
        assert layout.concrete == identity, where
        assert layout.attributes == attributes, where
        assert layout.occurrences == occurrences, where
        assert layout.attribute_count == len(attributes), where
        assert layout.members == (
            *(attribute.identity for attribute in attributes),
            *(occurrence.identity for occurrence in occurrences),
        ), where


def test_every_corpus_entitys_index_maps_each_member_to_its_own_position() -> None:
    for stem, _model, identity, layout in _corpus_layouts():
        where = (stem, identity.canonical)
        assert dict(layout.index_of) == {
            member: position for position, member in enumerate(layout.members)
        }, where
        assert len(layout.index_of) == len(layout.members), where


def test_the_category_boundary_separates_attributes_from_top_level_occurrences() -> None:
    layout = LayoutCatalog(corpus_model("customer")).entity(_identity("Customer"))
    attributes = layout.members[: layout.attribute_count]
    occurrences = layout.members[layout.attribute_count :]
    assert [member.name for member in cast("Any", attributes)] == ["id", "name"]
    assert [member.path for member in cast("Any", occurrences)] == [("address",)]
    assert layout.value_objects[0].identity == occurrences[0]


def test_a_value_object_layout_pre_links_its_whole_nested_subtree() -> None:
    model = corpus_model("customer")
    layout = LayoutCatalog(model).entity(_identity("Customer"))
    (address,) = layout.value_objects
    declared = _declared_occurrence(model, _identity("Customer"), "address")
    assert address.identity == declared.identity
    assert address.multiplicity is declared.multiplicity
    _assert_pre_linked(address, declared)


def _declared_occurrence(
    model: Metamodel, identity: EntityIdentity, name: str
) -> ValueObjectMetadata:
    occurrence = _view(model, identity).applicable_value_object(name)
    assert occurrence is not None, name
    return occurrence


def _assert_pre_linked(
    layout: ValueObjectLayout, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> None:
    """``layout`` is ``declared``'s leaves then its nested occurrences, with the
    nested arm resolved rather than looked up — all the way down."""
    leaves = tuple(leaf.identity for leaf in declared.attributes)
    nested = tuple(occurrence.identity for occurrence in declared.value_objects)
    assert layout.members == (*leaves, *nested)
    assert dict(layout.index_of) == {
        member: position for position, member in enumerate(layout.members)
    }
    assert layout.nested[: len(leaves)] == (None,) * len(leaves)
    for arm, occurrence in zip(layout.nested[len(leaves) :], declared.value_objects, strict=True):
        assert arm is not None
        assert arm.identity == occurrence.identity
        assert arm.multiplicity is occurrence.multiplicity
        _assert_pre_linked(arm, occurrence)


def test_every_corpus_occurrence_pre_links_its_subtree_at_both_multiplicities() -> None:
    reached: set[Multiplicity] = set()
    for stem, _model, identity, layout in _corpus_layouts():
        for occurrence, declared in zip(layout.value_objects, layout.occurrences, strict=True):
            assert occurrence.identity == declared.identity, (stem, identity.canonical)
            _assert_pre_linked(occurrence, declared)
            reached.update(_multiplicities(occurrence))
    assert reached == {Multiplicity.ONE, Multiplicity.MANY}


def _multiplicities(layout: ValueObjectLayout) -> set[Multiplicity]:
    """Every multiplicity ``layout``'s own subtree carries, itself included."""
    found = {layout.multiplicity}
    for arm in layout.nested:
        if arm is not None:
            found |= _multiplicities(arm)
    return found


# --------------------------------------------------------------------------- #
# Family identity and the logical key.                                         #
# --------------------------------------------------------------------------- #


def test_an_inheritance_participant_normalizes_its_family_to_the_root() -> None:
    layout = LayoutCatalog(corpus_model("animal")).entity(_identity("Cat"))
    assert layout.concrete == _identity("Cat")
    assert layout.family == _identity("Animal")


def test_a_table_per_concrete_subtype_participant_keeps_its_own_identity() -> None:
    catalog = LayoutCatalog(corpus_model("rate"))
    assert catalog.entity(_identity("DepositRate")).family == _identity("DepositRate")
    assert catalog.entity(_identity("Rate")).family == _identity("Rate")


def test_a_standalone_entity_is_its_own_family() -> None:
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    assert layout.family == _identity("Order")


def test_a_single_column_key_reads_the_raw_scalar_out_of_its_own_position() -> None:
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    row = tuple(range(100, 100 + len(layout.members)))
    identity = _key_attribute(layout)
    assert layout.key_of(row) == row[layout.index_of[identity]]


def test_an_inherited_key_reads_the_position_the_family_root_declared() -> None:
    # The family root owns the key, and a descendant's row carries it under the
    # root's own Attribute Identity, so a Cat and an Animal key alike.
    catalog = LayoutCatalog(corpus_model("animal"))
    cat = catalog.entity(_identity("Cat"))
    animal = catalog.entity(_identity("Animal"))
    key = _key_attribute(animal)
    assert cat.index_of[key] == animal.index_of[key]
    row = tuple(range(len(cat.members)))
    assert cat.key_of(row) == row[cat.index_of[key]]


def _with_composite_key(model: Metamodel, identity: EntityIdentity) -> Metamodel:
    """``model`` with every ``_COMPOSITE_KEY`` Attribute of ``identity`` declared
    a primary key.

    No accepted Metamodel carries a composite key — formation admits one
    primary-key Attribute per Entity (`metamodel-primary-key-multiple`) — so the
    second key column is doctored on after formation accepted the model.
    """
    declared = model.entity(identity)
    assert declared is not None
    composite = _DoctoredEntity(
        declared,
        tuple(
            attribute
            if attribute.identity.name not in _COMPOSITE_KEY
            else dataclasses.replace(attribute, primary_key=PrimaryKey())
            for attribute in declared.declared_attributes
        ),
    )
    return cast("Metamodel", _DoctoredModel(model, entities={identity: composite}))


def test_a_composite_key_reads_a_tuple_in_the_order_the_family_declared_it() -> None:
    identity = _identity("Order")
    layout = LayoutCatalog(_with_composite_key(corpus_model("orders"), identity)).entity(identity)
    row = tuple(range(200, 200 + len(layout.members)))
    positions = [
        layout.index_of[attribute.identity]
        for attribute in layout.attributes
        if attribute.identity.name in _COMPOSITE_KEY
    ]
    assert layout.key_of(row) == tuple(row[position] for position in positions)


class _DoctoredEntity:
    """One Entity's accepted local metadata with its Attributes replaced."""

    def __init__(self, real: Any, attributes: tuple[AttributeMetadata, ...]) -> None:
        self._real = real
        self.declared_attributes = attributes

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _key_attribute(layout: EntityLayout) -> Any:
    (position,) = [
        index
        for index, attribute in enumerate(layout.attributes)
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    return layout.attributes[position].identity


# --------------------------------------------------------------------------- #
# Canonical view order.                                                        #
# --------------------------------------------------------------------------- #


def _key(entity: str, name: str, narrowed: str | None = None) -> RelationshipViewKey:
    return RelationshipViewKey(RelationshipIdentity(_identity(entity), name), narrowed)


def test_ordered_places_declaration_position_then_broad_then_narrowed_key() -> None:
    layout = LayoutCatalog(corpus_model("animal")).entity(_identity("Person"))
    pets = _key("Person", "pets")
    animals = _key("Person", "animals")
    narrowed_dog = _key("Person", "animals", "animals[Dog]")
    narrowed_cat = _key("Person", "animals", "animals[Cat]")
    undeclared = _key("Person", "zzz")
    assert layout.ordered((pets, undeclared, narrowed_dog, animals, narrowed_cat)) == (
        animals,
        narrowed_cat,
        narrowed_dog,
        pets,
        undeclared,
    )


def test_ordered_reaches_a_relationship_an_inheritance_ancestor_declared() -> None:
    # `owner` is declared on Animal and navigable from every descendant under
    # that identity, so a Cat's order places it first rather than last.
    layout = LayoutCatalog(corpus_model("animal")).entity(_identity("Cat"))
    owner = _key("Animal", "owner")
    undeclared = _key("Animal", "zzz")
    assert layout.ordered((undeclared, owner)) == (owner, undeclared)


def test_ordered_answers_an_empty_selection_and_a_single_view_unchanged() -> None:
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    items = _key("Order", "items")
    assert layout.ordered(()) == ()
    assert layout.ordered((items,)) == (items,)


# --------------------------------------------------------------------------- #
# Agreement with the merge-side statements of these same two rules.            #
# --------------------------------------------------------------------------- #


def _merged(layout: EntityLayout, row: tuple[object, ...], views: tuple[RelationshipViewKey, ...]):
    """One projection of ``layout``'s Entity carrying ``row`` and ``views``,
    merged — the state every consumer of these two rules reads them through."""
    builder = GraphBuilder(ViewSchema.of(*views))
    projection = builder.add(ROOT_LEVEL, layout, row)
    for view in views:
        builder.write_view(projection, view, None)
    return merge_graph_input(builder.seal((projection,), Pin()))


def _merged_view_order(
    layout: EntityLayout, views: tuple[RelationshipViewKey, ...]
) -> tuple[RelationshipViewKey, ...]:
    """The order projection merging walks and publishes ``views`` in."""
    row = tuple(range(len(layout.members)))
    return _merged(layout, row, views).view_layout(0).slots


def test_every_corpus_entitys_family_and_key_agree_with_the_merge_identity_rule() -> None:
    # Two projections of one row share a logical node exactly where the layout
    # says their keys agree, which is the merge-side statement of `family` and
    # `key_of` together — the builder derives identity through no other rule.
    for stem, model, identity, layout in _corpus_layouts():
        del model
        where = (stem, identity.canonical)
        row = tuple(range(100, 100 + len(layout.members)))
        other = tuple(value + 1 for value in row)
        builder = GraphBuilder(ViewSchema.of())
        first = builder.add(ROOT_LEVEL, layout, row)
        again = builder.add(ROOT_LEVEL, layout, row)
        apart = builder.add(ROOT_LEVEL, layout, other)
        merge = merge_graph_input(builder.seal((first, again, apart), Pin()))
        assert merge.roots == (0, 0, 1), where
        assert builder_key_of(layout, row) != builder_key_of(layout, other), where


def builder_key_of(layout: EntityLayout, row: tuple[object, ...]) -> tuple[EntityIdentity, object]:
    """The graph-local identity the builder assigns ``row``, spelled as one value."""
    return layout.family, layout.key_of(row)


def test_a_composite_key_agrees_with_the_merge_identity_rule_as_a_whole_tuple() -> None:
    identity = _identity("Order")
    doctored = _with_composite_key(corpus_model("orders"), identity)
    layout = LayoutCatalog(doctored).entity(identity)
    row = tuple(range(200, 200 + len(layout.members)))
    key = layout.key_of(row)
    assert isinstance(key, tuple)
    assert len(cast("tuple[object, ...]", key)) == len(_COMPOSITE_KEY)
    # One column of the composite differing is a different logical node, which a
    # single-column key spelling could not distinguish.
    first_column = min(
        layout.index_of[attribute.identity]
        for attribute in layout.attributes
        if attribute.identity.name in _COMPOSITE_KEY
    )
    varied = tuple(
        value + 1 if position == first_column else value for position, value in enumerate(row)
    )
    builder = GraphBuilder(ViewSchema.of())
    first = builder.add(ROOT_LEVEL, layout, row)
    apart = builder.add(ROOT_LEVEL, layout, varied)
    merge = merge_graph_input(builder.seal((first, apart), Pin()))
    assert merge.roots == (0, 1)


def test_the_layouts_view_order_is_the_order_the_merge_walks_and_publishes() -> None:
    model = corpus_model("animal")
    identity = _identity("Person")
    layout = LayoutCatalog(model).entity(identity)
    scrambled = (
        _key("Person", "pets"),
        _key("Person", "zzz"),
        _key("Person", "animals", "animals[Dog]"),
        _key("Person", "animals"),
        _key("Person", "animals", "animals[Cat]"),
    )
    assert layout.ordered(scrambled) == _merged_view_order(layout, scrambled)


# --------------------------------------------------------------------------- #
# Ownership: the catalog a Domain Model retains, entries on first reach.       #
# --------------------------------------------------------------------------- #


def _domain_models() -> dict[str, Any]:
    return models.load_domain_models(Path(models.default_models_dir()))


def test_one_domain_model_reaches_one_catalog_and_two_reach_two() -> None:
    loaded = _domain_models()
    orders, animal = loaded["orders"], loaded["animal"]
    assert cataloged_model(orders) is cataloged_model(orders)
    assert cataloged_model(orders).layouts is not cataloged_model(animal).layouts


def test_the_cataloged_model_pairs_one_models_metadata_with_the_catalog_it_derived() -> None:
    # A record derives its own catalog from the metadata it carries, so the two
    # halves a read carries can never name two models — and so the model's own
    # retained record, not a second record over the same metadata, is what a
    # runtime holds to share one model's layouts.
    orders = _domain_models()["orders"]
    cataloged = cataloged_model(orders)
    assert cataloged.meta is model_of(orders)
    assert CatalogedModel(cataloged.meta).layouts is not cataloged.layouts


def test_a_cataloged_model_is_the_model_it_carries_and_not_the_catalog_it_derived() -> None:
    # The catalog is a function of the metadata, so it distinguishes no two
    # records the metadata does not, and comparing it by identity would make two
    # records a first-reach race published over one model unequal — the identity
    # no consumer is allowed to depend on.
    meta = model_of(_domain_models()["orders"])
    one, other = CatalogedModel(meta), CatalogedModel(meta)
    assert one.layouts is not other.layouts
    assert one == other
    assert one != CatalogedModel(model_of(_domain_models()["animal"]))


def test_a_descriptor_backed_domain_model_reaches_a_working_catalog() -> None:
    # The class-less path `graph_construction_of` refuses: a layout depends on
    # the accepted metadata alone, so this one must not.
    catalog = cataloged_model(_domain_models()["orders"]).layouts
    assert catalog.entity(_identity("Order")).concrete == _identity("Order")


def test_one_entity_reached_twice_answers_the_same_layout() -> None:
    catalog = LayoutCatalog(corpus_model("orders"))
    assert catalog.entity(_identity("Order")) is catalog.entity(_identity("Order"))


def test_a_fresh_catalog_derives_nothing_until_an_entity_is_reached() -> None:
    catalog = LayoutCatalog(corpus_model("orders"))
    assert catalog._cache == {}  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
    catalog.entity(_identity("Order"))
    assert set(catalog._cache) == {  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
        _identity("Order")
    }


def test_reaching_one_family_derives_no_layout_for_an_unrelated_one() -> None:
    catalog = LayoutCatalog(corpus_model("animal"))
    catalog.entity(_identity("Cat"))
    assert set(catalog._cache) == {  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
        _identity("Cat")
    }


# --------------------------------------------------------------------------- #
# Refusals: model defects, raised at first reach.                              #
# --------------------------------------------------------------------------- #


def test_an_entity_the_model_does_not_declare_is_refused_rather_than_laid_out() -> None:
    catalog = LayoutCatalog(corpus_model("orders"))
    with pytest.raises(ValueError, match="declares no Entity"):
        catalog.entity(_identity("Nope"))


def test_two_members_claiming_one_position_refuse_the_whole_layout() -> None:
    model = corpus_model("orders")
    identity = _identity("Order")
    attributes = tuple(_view(model, identity).applicable_attributes)
    doctored = _with_applicable_attributes(model, identity, (*attributes, attributes[0]))
    with pytest.raises(ValueError, match="two members under one identity"):
        LayoutCatalog(doctored).entity(identity)


def test_a_family_key_the_row_does_not_express_refuses_the_whole_layout() -> None:
    model = corpus_model("orders")
    identity = _identity("Order")
    attributes = tuple(
        attribute
        for attribute in _view(model, identity).applicable_attributes
        if not isinstance(attribute.primary_key, PrimaryKey)
    )
    doctored = _with_applicable_attributes(model, identity, attributes)
    with pytest.raises(ValueError, match="no position for the primary key"):
        LayoutCatalog(doctored).entity(identity)


def test_a_refusal_is_raised_rather_than_classified_as_stored_data() -> None:
    # The categorical claim behind both shapes above: a member row the model
    # never fixed is a defect in the model, so it reaches no issue vocabulary.
    model = corpus_model("orders")
    identity = _identity("Order")
    attributes = tuple(_view(model, identity).applicable_attributes)
    doctored = _with_applicable_attributes(model, identity, (*attributes, attributes[0]))
    with pytest.raises(ValueError) as excinfo:
        LayoutCatalog(doctored).entity(identity)
    assert not hasattr(excinfo.value, "code")


def test_a_refused_entity_leaves_the_catalog_usable_for_every_other_one() -> None:
    model = corpus_model("orders")
    catalog = LayoutCatalog(model)
    with pytest.raises(ValueError, match="declares no Entity"):
        catalog.entity(_identity("Nope"))
    assert catalog.entity(target(model, "OrderItem").identity).concrete == _identity("OrderItem")
