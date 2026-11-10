"""The exact-model layout catalog: positions, keys, order, and refusals.

Four claims, in the order the catalog fixes them. **Positions** are a function
of the accepted Metamodel alone, so the whole corpus is graded against the
family-effective member set every other read path already agrees on.
**Agreement** holds the layout's family, logical key, and view order against the
merge-side rules they restate, so neither statement of either rule can move
without the other. **Construction** is the cataloged model a runtime composes
over one model's metadata, every declared Entity derived at once. **Refusals**
are raised errors rather than stored-data classifications, because a row cannot
contradict a position the model itself failed to fix.

The defect witnesses are doctored models rather than authored ones: an accepted
Metamodel is exactly what cannot carry these shapes — formation refuses a
duplicate member and admits one primary-key Attribute per Entity — so the only
way to reach the checks is to hand the catalog metadata that contradicts itself
after formation accepted it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import class_models, models
from parallax.core.internal.base import SQL_NULL
from parallax.core.internal.entity._layout import (
    CatalogedModel,
    EntityLayout,
    LayoutCatalog,
)
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.internal.inheritance import (
    EntityMemberSelection,
    InheritanceEntityView,
    InheritanceFacet,
    family_variant_name,
    inheritance_facet_of,
)
from parallax.core.internal.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    MemberShape,
    Metamodel,
    Multiplicity,
    OccurrenceMetadata,
    PrimaryKey,
    RelationshipIdentity,
    ValueObjectMetadata,
)
from parallax.core.internal.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    ViewSchema,
    page_rows,
)
from parallax.core.internal.read_planning import RelationshipViewKey
from parallax.core.internal.relationship import relationship_facet_of
from parallax.core.internal.temporal_read import Pin
from tests._support.document_reads import folded_names
from tests._support.fake_metadata import with_facet
from tests.unit._corpus_model_support import corpus, formed, target
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._prepared_read_support import bound_read, compiled_read
from tests.unit._root_publication_support import observed_roots

_NAMESPACE = "parallax.compatibility"


def _identity(name: str, *, namespace: str | None = _NAMESPACE) -> EntityIdentity:
    return EntityIdentity(namespace, name)


def _view(model: Metamodel, identity: EntityIdentity) -> InheritanceEntityView:
    position = inheritance_facet_of(model).entity(identity)
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
        value_objects = tuple(real.applicable_value_objects)
        self.member_selection = EntityMemberSelection(
            MemberShape.of(attributes, value_objects),
            (*attributes, *value_objects),
            len(attributes),
        )

    @property
    def applicable_attributes(self) -> Sequence[AttributeMetadata]:
        return self.member_selection.attributes

    @property
    def applicable_value_objects(self) -> Sequence[ValueObjectMetadata]:
        return self.member_selection.value_objects

    @property
    def applicable_document_shape(self) -> MemberShape:
        return self.member_selection.shape

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


def _with_applicable_attributes(
    model: Metamodel, identity: EntityIdentity, attributes: Sequence[AttributeMetadata]
) -> Metamodel:
    """``model`` answering ``attributes`` as ``identity``'s applicable set."""
    doctored = cast("InheritanceEntityView", _DoctoredView(_view(model, identity), attributes))
    facet = cast(
        "InheritanceFacet", _DoctoredFacet(inheritance_facet_of(model), identity, doctored)
    )
    return with_facet(model, INHERITANCE_FACET_KEY, facet)


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
        assert layout.member_selection is position.member_selection, where
        assert layout.attributes == attributes, where
        assert layout.occurrences == occurrences, where
        assert layout.attribute_count == len(attributes), where
        assert layout.members == (
            *(attribute.identity for attribute in attributes),
            *(occurrence.identity for occurrence in occurrences),
        ), where


def test_the_category_boundary_separates_attributes_from_top_level_occurrences() -> None:
    layout = LayoutCatalog(corpus_model("customer")).entity(_identity("Customer"))
    attributes = layout.members[: layout.attribute_count]
    occurrences = layout.members[layout.attribute_count :]
    assert [member.name for member in cast("Any", attributes)] == ["id", "name"]
    assert [member.path for member in cast("Any", occurrences)] == [("address",)]
    assert layout.occurrences[0].identity == occurrences[0]


def _assert_bound(declared: OccurrenceMetadata) -> None:
    assert len(declared.members) == len(declared.document_shape.members)
    for binding, definition in zip(declared.members, declared.document_shape.members, strict=True):
        assert binding.definition is definition
    for occurrence in declared.value_objects:
        _assert_bound(occurrence)


def test_every_corpus_occurrence_reuses_definitions_at_both_multiplicities() -> None:
    reached: set[Multiplicity] = set()
    for _stem, _model, _identity, layout in _corpus_layouts():
        for occurrence in layout.occurrences:
            _assert_bound(occurrence)
            reached.update(_multiplicities(occurrence))
    assert reached == {Multiplicity.ONE, Multiplicity.MANY}


def _multiplicities(occurrence: OccurrenceMetadata) -> set[Multiplicity]:
    """Every multiplicity ``occurrence``'s own subtree carries, itself included."""
    found = {occurrence.multiplicity}
    for nested in occurrence.value_objects:
        found |= _multiplicities(nested)
    return found


# --------------------------------------------------------------------------- #
# Family identity and the logical key.                                         #
# --------------------------------------------------------------------------- #


def test_a_standalone_entity_is_its_own_family() -> None:
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    assert layout.family == _identity("Order")


# --------------------------------------------------------------------------- #
# A family node's type: fixed per exact Entity where the catalog lays it out.   #
# --------------------------------------------------------------------------- #


def test_only_an_inheritance_participant_fixes_a_wire_type() -> None:
    for _stem, model, identity, layout in _corpus_layouts():
        participates = _view(model, identity).strategy is not None
        assert layout.wire_type == (identity.canonical if participates else None)


def test_a_family_gaining_a_concrete_of_the_same_local_name_keeps_every_nodes_type() -> None:
    from parallax.descriptor._records import Attribute, Entity, Inheritance
    from parallax.descriptor._records import Metamodel as DescriptorMetamodel

    root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    existing = Entity(
        name="SharedVariant",
        namespace="catalog",
        table="catalog_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="catalogLabel", type="string", column="shared_label"),),
    )
    joining = Entity(
        name="SharedVariant",
        namespace="archive",
        table="archive_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="archiveLabel", type="string", column="shared_label"),),
    )
    before = formed(DescriptorMetamodel(entities=(root, existing)))
    after = formed(DescriptorMetamodel(entities=(root, joining, existing)))
    concrete = _identity("SharedVariant", namespace="catalog")

    assert LayoutCatalog(before).entity(concrete).wire_type == "catalog.SharedVariant"
    assert LayoutCatalog(after).entity(concrete).wire_type == "catalog.SharedVariant"
    assert (
        LayoutCatalog(after).entity(_identity("SharedVariant", namespace="archive")).wire_type
        == "archive.SharedVariant"
    )
    assert family_variant_name(inheritance_facet_of(before), concrete) == "SharedVariant"
    assert family_variant_name(inheritance_facet_of(after), concrete) == "catalog.SharedVariant"


def test_a_class_backed_model_fixes_the_type_its_descriptor_twin_fixes() -> None:
    descriptor_meta = model_of(_domain_models()["animal"])
    descriptor = LayoutCatalog(descriptor_meta)
    class_backed = LayoutCatalog(model_of(class_models.MODELS["animal"]))
    types = {
        entity.identity: descriptor.entity(entity.identity).wire_type
        for entity in descriptor_meta.entities
    }
    assert any(wire_type is not None for wire_type in types.values())
    for identity, wire_type in types.items():
        assert class_backed.entity(identity).wire_type == wire_type


def test_every_corpus_key_position_locates_its_family_key_in_its_own_row() -> None:
    for stem, model, identity, layout in _corpus_layouts():
        key = _view(model, identity).primary_key
        assert layout.primary_key == (layout.index_of[key.identity],), (stem, identity.canonical)


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


def test_ordered_places_another_entitys_direction_of_the_same_name_last() -> None:
    # `statuses` is declared by Order and, separately, by OrderItem. Order
    # navigates only its own, so the item's direction is not a position of this
    # layout at all and sorts with the undeclared ones — which is what keeps the
    # canonical order a statement about identities rather than about names.
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    statuses = _key("Order", "statuses")
    foreign = _key("OrderItem", "statuses")
    items = _key("Order", "items")
    assert layout.ordered((foreign, statuses, items)) == (items, statuses, foreign)


def test_ordered_answers_an_empty_selection_and_a_single_view_unchanged() -> None:
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("Order"))
    items = _key("Order", "items")
    assert layout.ordered(()) == ()
    assert layout.ordered((items,)) == (items,)


# --------------------------------------------------------------------------- #
# Which navigable directions are to-many.                                      #
# --------------------------------------------------------------------------- #


def test_a_layout_names_the_directions_it_navigates_at_many_and_no_other() -> None:
    # OrderItem navigates one direction of each kind: the to-many `statuses` and
    # the to-one `order`.
    layout = LayoutCatalog(corpus_model("orders")).entity(_identity("OrderItem"))
    order = RelationshipIdentity(_identity("OrderItem"), "order")
    statuses = RelationshipIdentity(_identity("OrderItem"), "statuses")
    assert set(layout.relationships) == {order, statuses}
    assert layout.to_many == frozenset({statuses})


def test_an_inherited_direction_takes_the_cardinality_its_declaring_ancestor_fixed() -> None:
    # `owner` is declared to-one on the abstract root Animal and reached by every
    # concrete descendant under that identity, while Person's own directions are
    # to-many — so one model answers both ways, and a descendant's answer is the
    # declaration it inherits rather than anything it states itself.
    catalog = LayoutCatalog(corpus_model("animal"))
    cat = catalog.entity(_identity("Cat"))
    assert cat.relationships == (RelationshipIdentity(_identity("Animal"), "owner"),)
    assert cat.to_many == frozenset()
    person = catalog.entity(_identity("Person"))
    assert person.to_many == frozenset(person.relationships)


def test_every_corpus_entitys_to_many_set_is_the_declared_cardinality_of_its_own_row() -> None:
    reached: set[bool] = set()
    for stem, model, identity, layout in _corpus_layouts():
        facet = relationship_facet_of(model)
        where = (stem, identity.canonical)
        assert layout.to_many <= set(layout.relationships), where
        for direction in layout.relationships:
            declared = facet.relationship(direction)
            assert declared is not None, where
            at_many = declared.cardinality.target is Multiplicity.MANY
            assert (direction in layout.to_many) is at_many, where
            reached.add(at_many)
    assert reached == {False, True}


# --------------------------------------------------------------------------- #
# Agreement with the merge-side statements of these same two rules.            #
# --------------------------------------------------------------------------- #


def _merged_view_order(
    model: Metamodel, identity: EntityIdentity, views: tuple[RelationshipViewKey, ...]
) -> tuple[RelationshipViewKey, ...]:
    """The order projection merging walks and publishes ``views`` in, over one
    converted row of ``identity`` carrying them all."""
    builder = PageBuilder(ViewSchema.of(*views))
    projection = _claimed(builder, model, identity, 0)
    for view in views:
        builder.write_view(projection, view, None)
    (root,) = observed_roots(builder.finish((projection,), Pin()), model)
    return root.view_layouts[0].slots


def _claimed(builder: PageBuilder, model: Metamodel, identity: EntityIdentity, seed: int) -> int:
    """One driver row of ``identity``'s own read, every cell distinct and derived
    from ``seed``, converted into ``builder`` as a root provider row is."""
    compiled = compiled_read(model, identity)
    shared = compiled.result_contract.shared_document
    row = tuple(
        SQL_NULL
        if shared is not None and key == shared.column
        else f"{seed + position:04x}"
        if key.endswith("_hex")
        else seed + position
        for position, key in enumerate(
            folded_names(compiled.statement.sql, compiled.document_reads)
        )
    )
    ref, _resolved, _document = bound_read(model, identity).record_row(
        row, builder, source=ROOT_LEVEL
    )
    return ref


def test_every_corpus_entitys_family_and_key_agree_with_the_merge_identity_rule() -> None:
    # Two projections of one row share a logical node exactly where the layout
    # says their keys agree, which is the merge-side statement of `family` and
    # `primary_key` together. Each concrete Entity's own read converts its rows,
    # so the keys are the ones conversion claims.
    for stem, model, identity, layout in _corpus_layouts():
        if tuple(_view(model, identity).concrete_subtypes) != (identity,):
            continue
        where = (stem, identity.canonical)
        builder = PageBuilder(ViewSchema.of())
        first = _claimed(builder, model, identity, 100)
        again = _claimed(builder, model, identity, 100)
        apart = _claimed(builder, model, identity, 101)
        rows = page_rows(builder.finish((first, again, apart), Pin()))
        assert list(rows.logical_rows) == [0, 0, 1], where
        first_key, apart_key = rows.keys[first], rows.keys[apart]
        assert first_key is not None and apart_key is not None, where
        assert first_key.family == apart_key.family == layout.family, where
        assert first_key.primary_key != apart_key.primary_key, where


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
    assert layout.ordered(scrambled) == _merged_view_order(model, identity, scrambled)


# --------------------------------------------------------------------------- #
# Construction: one catalog per model, every Entity derived at once.           #
# --------------------------------------------------------------------------- #


def _domain_models() -> dict[str, Any]:
    return models.load_domain_models(Path(models.default_models_dir()))


def test_separate_catalogs_share_the_inheritance_owned_member_selection() -> None:
    meta = model_of(_domain_models()["orders"])
    one, other = CatalogedModel(meta), CatalogedModel(meta)
    identity = _identity("Order")
    assert (
        one.layouts.entity(identity).member_selection
        is other.layouts.entity(identity).member_selection
    )


def test_a_cataloged_model_is_the_model_it_carries_and_not_the_catalog_it_derived() -> None:
    # The catalog is a function of the metadata, so it distinguishes no two
    # records the metadata does not, and comparing it by identity would make two
    # records over one model unequal — the identity no consumer is allowed to
    # depend on.
    meta = model_of(_domain_models()["orders"])
    one, other = CatalogedModel(meta), CatalogedModel(meta)
    assert one.layouts is not other.layouts
    assert one == other
    assert one != CatalogedModel(model_of(_domain_models()["animal"]))


# --------------------------------------------------------------------------- #
# Refusals: model defects refuse the whole catalog where it is constructed.    #
# --------------------------------------------------------------------------- #


def test_an_entity_the_model_does_not_declare_is_refused_rather_than_laid_out() -> None:
    catalog = LayoutCatalog(corpus_model("orders"))
    with pytest.raises(ValueError, match="declares no Entity"):
        catalog.entity(_identity("Nope"))


def test_two_members_claiming_one_position_refuse_the_member_selection() -> None:
    model = corpus_model("orders")
    identity = _identity("Order")
    attributes = tuple(_view(model, identity).applicable_attributes)
    with pytest.raises(ValueError, match="each identity one position"):
        _with_applicable_attributes(model, identity, (*attributes, attributes[0]))


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
        CatalogedModel(doctored)


def test_a_refused_entity_leaves_the_catalog_usable_for_every_other_one() -> None:
    model = corpus_model("orders")
    catalog = LayoutCatalog(model)
    with pytest.raises(ValueError, match="declares no Entity"):
        catalog.entity(_identity("Nope"))
    assert catalog.entity(target(model, "OrderItem").identity).concrete == _identity("OrderItem")
