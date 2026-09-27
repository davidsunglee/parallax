"""m-inheritance: the compiled Inheritance Facet and its typed view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal, cast

import pytest

from parallax.conformance import case_format
from parallax.core import inheritance
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import INT64, STRING
from parallax.core.inheritance import (
    FACET_KEY,
    INHERITANCE_MODULE,
    MODEL_COMPILER,
    RULE_SET,
    EntityMemberSelection,
    InheritanceEntityView,
    InheritanceFacet,
    InheritanceFamilyView,
)
from parallax.core.inheritance import _compile as inheritance_compile
from parallax.core.inheritance._compile import compile_facet
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    MemberShape,
    Metamodel,
    Multiplicity,
    PersistenceMode,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.model_formation import MODEL_FORMATION_MODULE, ModelCompilerRequirement
from parallax.core.model_formation._manifest import RequiredRuleSet
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._parse import parse_document
from tests._support import fake_metamodel as fake
from tests.unit._metamodel_support import Declaration, identity, key, source
from tests.unit.core._dormant_family_support import (
    DORMANT,
    DORMANT_CHILD,
    LIVE,
    ROOT,
    dormant_family,
)
from tests.unit.core._family_owner_support import (
    DescendantsFirst,
    family_roots,
    record_root_derivations,
)

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"
_CORPUS_NAMESPACE: Final[str] = "parallax.compatibility"


def _formed(stem: str) -> Metamodel:
    """The accepted model a corpus descriptor forms into."""
    document = case_format.safe_load_yaml((_MODELS / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return form_metamodel(
        unresolved_metamodel(parse_document(cast("Mapping[str, object]", document)))
    )


def _corpus(stem: str) -> InheritanceFacet:
    return inheritance.view(_formed(stem))


def _corpus_entity(name: str) -> EntityIdentity:
    return EntityIdentity(_CORPUS_NAMESPACE, name)


def _view(facet: InheritanceFacet, name: str) -> InheritanceEntityView:
    found = facet.entity(_corpus_entity(name))
    assert found is not None, name
    return found


def _names(members: Sequence[EntityIdentity]) -> list[str]:
    return [member.name for member in members]


def _attribute_names(members: Sequence[AttributeMetadata]) -> list[str]:
    return [member.identity.name for member in members]


def _value_object_names(members: Sequence[ValueObjectMetadata]) -> list[str]:
    return [member.identity.path[-1] for member in members]


# --------------------------------------------------------------------------
# The module's formation contract.
# --------------------------------------------------------------------------


def test_the_builtin_manifest_declares_this_modules_rule_set_and_compiler() -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == INHERITANCE_MODULE)
    assert isinstance(entry.rule_set, RequiredRuleSet)
    assert entry.issue_codes == inheritance.ISSUE_CODES
    assert entry.compiler == ModelCompilerRequirement(FACET_KEY)
    assert entry.required_facets == frozenset()
    assert entry.required_modules == frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE})
    assert RULE_SET in BUILTIN_PROFILE.rule_sets
    assert MODEL_COMPILER in BUILTIN_PROFILE.model_compilers
    assert MODEL_COMPILER.owner == INHERITANCE_MODULE
    assert MODEL_COMPILER.facet_key == FACET_KEY
    assert MODEL_COMPILER.requires == frozenset()


def test_the_inheritance_row_precedes_the_relationship_row() -> None:
    # Manifest entry order is Rule Set invocation order, and this file's row is
    # the spec manifest's third — ahead of `m-relationship`.
    owners = [entry.owner for entry in BUILTIN_MANIFEST.entries]
    assert owners.index(INHERITANCE_MODULE) < owners.index("m-relationship")


def test_a_formed_model_serves_its_facet_through_the_typed_view() -> None:
    model = _formed("animal")
    assert inheritance.view(model) is model.facet(FACET_KEY)


def test_the_facet_offers_only_entity_position_and_family_lookup() -> None:
    facet = _corpus("animal")
    assert {name for name in dir(facet) if not name.startswith("_")} == {
        "entity",
        "position",
        "family",
    }


# --------------------------------------------------------------------------
# Per-Entity views.
# --------------------------------------------------------------------------


def test_a_standalone_entity_has_the_trivial_view() -> None:
    person = _view(_corpus("animal"), "Person")
    assert person.root == person.entity
    assert _names(person.ancestry) == ["Person"]
    assert _names(person.concrete_subtypes) == ["Person"]
    assert person.strategy is None
    assert person.tag_column is None
    assert person.tag_value is None
    assert person.container == Table("person")
    assert person.persistence is PersistenceMode.READ_WRITE
    assert _attribute_names(person.applicable_attributes) == ["id", "name"]
    assert [member.identity.name for member in person.applicable_relationships] == [
        "animals",
        "pets",
    ]


def test_every_accepted_entity_has_a_view_and_a_miss_returns_absence() -> None:
    model = _formed("animal")
    facet = inheritance.view(model)
    assert all(facet.entity(entity.identity) is not None for entity in model.entities)
    assert facet.entity(EntityIdentity("elsewhere", "Dog")) is None


def test_ancestry_runs_root_first_down_to_the_entity() -> None:
    facet = _corpus("animal")
    assert _names(_view(facet, "Dog").ancestry) == ["Animal", "Pet", "Dog"]
    assert _names(_view(facet, "WildBoar").ancestry) == ["Animal", "WildBoar"]
    assert _names(_view(facet, "Animal").ancestry) == ["Animal"]


def test_effective_concrete_subtypes_are_canonically_ordered_at_every_position() -> None:
    facet = _corpus("animal")
    assert _names(_view(facet, "Animal").concrete_subtypes) == ["Cat", "Dog", "WildBoar"]
    assert _names(_view(facet, "Pet").concrete_subtypes) == ["Cat", "Dog"]
    assert _names(_view(facet, "Dog").concrete_subtypes) == ["Dog"]


def test_a_table_per_hierarchy_family_shares_the_root_container_and_tag_column() -> None:
    facet = _corpus("animal")
    for name in ("Animal", "Pet", "Dog", "Cat", "WildBoar"):
        view = _view(facet, name)
        assert view.container == Table("animal"), name
        assert view.tag_column == "kind", name
        assert isinstance(view.strategy, TablePerHierarchy), name
    assert _view(facet, "Dog").tag_value == "dog"
    assert _view(facet, "Cat").tag_value == "cat"
    assert _view(facet, "Animal").tag_value is None
    assert _view(facet, "Pet").tag_value is None


def test_a_table_per_concrete_subtype_family_maps_its_concretes_alone() -> None:
    facet = _corpus("document")
    assert _view(facet, "Invoice").container == Table("invoice")
    assert _view(facet, "Memo").container == Table("memo")
    assert _view(facet, "Document").container is None
    assert _view(facet, "FinancialDocument").container is None
    for name in ("Document", "FinancialDocument", "Invoice"):
        view = _view(facet, name)
        assert isinstance(view.strategy, TablePerConcreteSubtype), name
        assert view.tag_column is None, name
        assert view.tag_value is None, name


def test_applicable_members_are_the_ancestry_chain_in_chain_order() -> None:
    facet = _corpus("animal")
    assert _attribute_names(_view(facet, "Dog").applicable_attributes) == [
        "id",
        "name",
        "ownerId",
        "licenseId",
        "barkVolume",
    ]
    assert _attribute_names(_view(facet, "Animal").applicable_attributes) == [
        "id",
        "name",
        "ownerId",
    ]


def test_an_entity_view_holds_its_applicable_document_shape() -> None:
    model = _formed("customer")
    view = inheritance.view(model).entity(_corpus_entity("Customer"))
    assert view is not None
    assert view.applicable_document_shape == MemberShape.of(
        view.applicable_attributes,
        view.applicable_value_objects,
    )


def test_effective_member_views_delegate_slices_equality_and_alignment_to_one_selection() -> None:
    view = _view(_corpus("customer"), "Customer")
    selection = view.member_selection
    assert tuple(selection.attributes[:]) == tuple(view.applicable_attributes)
    assert selection.attributes != object()
    assert selection.identities != object()
    identities = tuple(binding.identity for binding in selection.bindings)
    assert selection.identities == identities
    assert hash(selection.identities) == hash(identities)
    with pytest.raises(ValueError, match="aligns every shape member"):
        EntityMemberSelection(MemberShape(()), selection.bindings, selection.attribute_count)
    for count in (-1, len(selection.bindings) + 1):
        with pytest.raises(ValueError, match="counts its leaves within its bindings"):
            EntityMemberSelection(selection.shape, selection.bindings, count)


def test_a_member_selection_matches_and_prints_through_its_constructor_arguments() -> None:
    selection = _view(_corpus("customer"), "Customer").member_selection
    match selection:
        case EntityMemberSelection(shape, bindings, attribute_count):
            assert shape is selection.shape
            assert bindings is selection.bindings
            assert attribute_count == selection.attribute_count
    assert repr(selection) == (
        f"EntityMemberSelection(shape={selection.shape!r}, bindings={selection.bindings!r}, "
        f"attribute_count={selection.attribute_count!r})"
    )


def _member_ranges() -> list[tuple[str, Sequence[object], tuple[object, ...]]]:
    customer = _view(_corpus("customer"), "Customer").member_selection
    dog = _view(_corpus("animal"), "Dog").member_selection
    occurrences_only = EntityMemberSelection(
        MemberShape.of((), customer.value_objects),
        tuple(customer.value_objects),
        0,
    )
    return [
        ("prefix", customer.attributes, customer.bindings[: customer.attribute_count]),
        ("suffix", customer.value_objects, customer.bindings[customer.attribute_count :]),
        ("whole", dog.attributes, dog.bindings),
        ("empty", dog.value_objects, ()),
        ("leading-empty", occurrences_only.attributes, ()),
        ("trailing-whole", occurrences_only.value_objects, occurrences_only.bindings),
    ]


def test_member_windows_compare_by_content_across_backing_and_offset() -> None:
    customer = _view(_corpus("customer"), "Customer").member_selection
    rebased = EntityMemberSelection(
        MemberShape.of((), customer.value_objects), tuple(customer.value_objects), 0
    )
    assert rebased.bindings is not customer.bindings
    assert rebased.value_objects == customer.value_objects
    assert hash(rebased.value_objects) == hash(customer.value_objects)
    assert rebased.attributes != customer.attributes


def test_every_member_window_iterates_its_own_bindings_in_order_by_identity() -> None:
    for shape, window, expected in _member_ranges():
        assert len(window) == len(expected), shape
        assert all(left is right for left, right in zip(window, expected, strict=True)), shape
        assert [window[index] for index in range(len(window))] == list(expected), shape
        assert [window[-1 - index] for index in range(len(window))] == list(expected)[::-1], shape
        assert tuple(window[:]) == expected, shape
        assert tuple(window[1:]) == expected[1:], shape
        assert list(window) == list(window), shape
        first, second = iter(window), iter(window)
        interleaved = [next(iterator) for _ in expected for iterator in (first, second)]
        assert interleaved == [binding for binding in expected for _ in (first, second)], shape
        assert next(first, None) is None and next(second, None) is None, shape
        assert window == expected, shape
        assert hash(window) == hash(expected), shape
        for outside in (len(expected), -len(expected) - 1):
            with pytest.raises(IndexError):
                window[outside]


def test_iterating_a_member_window_never_indexes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_window: object, index: object) -> object:
        raise AssertionError(f"iteration indexed the window at {index!r}")

    ranges = _member_ranges()
    for shape, window, expected in ranges:
        monkeypatch.setattr(type(window), "__getitem__", refuse)
        assert list(window) == list(expected), shape
        assert all(left is right for left, right in zip(window, expected, strict=True)), shape


def test_an_applicable_member_is_the_ancestors_own_accepted_value() -> None:
    model = _formed("animal")
    facet = inheritance.view(model)
    root = model.entity(_corpus_entity("Animal"))
    assert root is not None
    found = _view(facet, "Dog").applicable_attribute("id")
    assert found is root.attribute("id")
    assert found is not None
    assert found.identity.entity == _corpus_entity("Animal")


def test_applicable_lookups_resolve_across_the_chain_and_return_absence_on_a_miss() -> None:
    facet = _corpus("animal")
    dog = _view(facet, "Dog")
    assert dog.applicable_attribute("licenseId") is not None
    assert dog.applicable_attribute("indoor") is None
    assert "animals" not in {member.identity.name for member in dog.applicable_relationships}
    person = _view(facet, "Person")
    assert "pets" in {member.identity.name for member in person.applicable_relationships}
    assert person.applicable_value_object("nothing") is None


def test_value_object_lookup_resolves_a_top_level_occurrence_by_its_local_name() -> None:
    facet = inheritance.view(_formed("customer"))
    customer = facet.entity(_corpus_entity("Customer"))
    assert customer is not None
    assert _value_object_names(customer.applicable_value_objects) == ["address"]
    found = customer.applicable_value_object("address")
    assert found is not None
    assert found.identity.path == ("address",)


def test_persistence_is_the_effective_root_owned_mode() -> None:
    facet = _corpus("animal")
    assert _view(facet, "Dog").persistence is PersistenceMode.READ_WRITE
    scalars = inheritance.view(_formed("scalars"))
    read_only = scalars.entity(_corpus_entity("ScalarThing"))
    assert read_only is not None
    assert read_only.persistence is PersistenceMode.READ_ONLY


def test_a_family_inherits_the_root_declared_persistence() -> None:
    root = identity("Archive")
    entry = identity("ArchiveEntry")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("archive"),
                persistence=PersistenceMode.READ_ONLY,
                attributes=(key(root),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=entry,
                inheritance=ConcreteSubtype(ExactEntityReference(root), "entry"),
            ),
        )
    )
    facet = inheritance.view(model)
    for position in (root, entry):
        view = facet.entity(position)
        assert view is not None
        assert view.persistence is PersistenceMode.READ_ONLY


# --------------------------------------------------------------------------
# One owner per family fact: the root's Metadata and its key Attribute.
# --------------------------------------------------------------------------

# A three-level table-per-hierarchy family, and the table-per-concrete-subtype
# families that carry an explicit version and bitemporal axes on their roots.
_FAMILY_ROOTS: Final[dict[str, str]] = {
    "animal": "Animal",
    "appliance": "Appliance",
    "rate": "Rate",
}


@pytest.mark.parametrize(("stem", "root_name"), sorted(_FAMILY_ROOTS.items()))
def test_every_position_in_a_family_shares_its_roots_metadata_and_key_attribute(
    stem: str, root_name: str
) -> None:
    model = _formed(stem)
    facet = inheritance.view(model)
    root = model.entity(_corpus_entity(root_name))
    assert root is not None
    key = root.attribute("id")
    assert key is not None
    members = [
        entity.identity
        for entity in model.entities
        if _view(facet, entity.identity.name).root == root.identity
    ]
    assert len(members) > 2
    for member in members:
        assert inheritance.root_metadata(facet, model, member) is root, member
        assert _view(facet, member.name).primary_key is key, member


def test_a_standalone_entitys_key_is_the_attribute_it_declares() -> None:
    model = _formed("animal")
    person = model.entity(_corpus_entity("Person"))
    assert person is not None
    assert inheritance.root_metadata(inheritance.view(model), model, person.identity) is person
    assert _view(inheritance.view(model), "Person").primary_key is person.attribute("id")


def test_a_family_listed_descendants_first_derives_its_key_once_at_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _formed("animal")
    metadata = DescendantsFirst(model)
    listed = [entity.identity.name for entity in metadata.entities]
    assert listed.index("Dog") < listed.index("Pet") < listed.index("Animal")
    derived = record_root_derivations(monkeypatch, inheritance_compile, "_primary_key")
    facet = compile_facet(metadata)
    assert sorted(derived, key=_canonical) == sorted(family_roots(model), key=_canonical)
    root = model.entity(_corpus_entity("Animal"))
    assert root is not None
    for name in ("Animal", "Pet", "Dog", "Cat", "WildBoar"):
        assert _view(facet, name).primary_key is root.attribute("id"), name


def _canonical(identity: EntityIdentity) -> tuple[str, str]:
    return identity.sort_key


# --------------------------------------------------------------------------
# Position projection.
# --------------------------------------------------------------------------


def test_an_entitys_supersets_equal_its_own_one_member_position() -> None:
    model = _formed("animal")
    facet = inheritance.view(model)
    for entity in model.entities:
        view = facet.entity(entity.identity)
        assert view is not None
        projected = facet.position([entity.identity])
        assert projected is not None
        assert view.superset_attributes == projected.superset_attributes
        assert view.superset_value_objects == projected.superset_value_objects
        assert view.concrete_subtypes == projected.concrete_subtypes


def test_a_superset_lists_ancestors_first_then_the_effective_set() -> None:
    facet = _corpus("animal")
    assert _attribute_names(_view(facet, "Animal").superset_attributes) == [
        "id",
        "name",
        "ownerId",
        "licenseId",
        "indoor",
        "barkVolume",
        "tuskLength",
    ]


def test_a_narrowed_position_projects_only_the_branches_it_denotes() -> None:
    facet = _corpus("animal")
    projected = facet.position([_corpus_entity("Pet")])
    assert projected is not None
    assert _names(projected.concrete_subtypes) == ["Cat", "Dog"]
    assert _attribute_names(projected.superset_attributes) == [
        "id",
        "name",
        "ownerId",
        "licenseId",
        "indoor",
        "barkVolume",
    ]


def test_overlapping_and_duplicate_members_denote_their_union() -> None:
    facet = _corpus("animal")
    union = facet.position(
        [_corpus_entity("Pet"), _corpus_entity("Dog"), _corpus_entity("Dog")],
    )
    single = facet.position([_corpus_entity("Pet")])
    assert union is not None
    assert single is not None
    assert union.concrete_subtypes == single.concrete_subtypes
    assert union.superset_attributes == single.superset_attributes


def test_a_position_contributes_each_declaring_entity_exactly_once() -> None:
    facet = _corpus("animal")
    projected = facet.position([_corpus_entity("Cat"), _corpus_entity("WildBoar")])
    assert projected is not None
    identities = [member.identity for member in projected.superset_attributes]
    assert len(identities) == len(set(identities))
    assert _attribute_names(projected.superset_attributes) == [
        "id",
        "name",
        "ownerId",
        "licenseId",
        "indoor",
        "tuskLength",
    ]


def test_a_position_is_absent_for_an_unknown_member_or_two_families() -> None:
    facet = _corpus("animal")
    assert facet.position([EntityIdentity("elsewhere", "Dog")]) is None
    assert facet.position([_corpus_entity("Dog"), _corpus_entity("Person")]) is None
    assert facet.position([]) is None


def test_a_standalone_entity_forms_a_position_only_alone() -> None:
    model = _formed("orders")
    facet = inheritance.view(model)
    first, second = (entity.identity for entity in model.entities[:2])
    alone = facet.position([first])
    assert alone is not None
    assert alone.concrete_subtypes == (first,)
    assert facet.position([first, second]) is None


def test_a_position_with_no_concrete_subtype_projects_empty_sequences() -> None:
    # A CHILDLESS abstract subtype: the family composes a concrete elsewhere, so it
    # forms (a family composing none of them does not), yet this position's own
    # descent reaches no row-owning node and projects nothing.
    root = identity("Root")
    orphan = identity("Orphan")
    real = identity("Real")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                attributes=(key(root),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=orphan,
                inheritance=AbstractSubtype(ExactEntityReference(root)),
            ),
            Declaration(
                identity=real,
                container=Table("real"),
                inheritance=ConcreteSubtype(ExactEntityReference(root)),
            ),
        )
    )
    projected = inheritance.view(model).position([orphan])
    assert projected is not None
    assert projected.concrete_subtypes == ()
    assert projected.superset_attributes == ()
    assert projected.superset_value_objects == ()


# --------------------------------------------------------------------------
# Value Object supersets.
# --------------------------------------------------------------------------


def _shape(name: str) -> ValueObjectShapeDeclaration:
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration(name, type=STRING),),
    )


def test_a_superset_collects_value_objects_down_the_same_contribution_order() -> None:
    root = identity("Vessel")
    tanker = identity("Tanker")
    ferry = identity("Ferry")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("vessel"),
                attributes=(key(root),),
                value_objects=(
                    ValueObjectOccurrenceDeclaration(
                        name="hull",
                        storage=Column("hull"),
                        shape=_shape("material"),
                        multiplicity=Multiplicity.ONE,
                    ),
                ),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=tanker,
                value_objects=(
                    ValueObjectOccurrenceDeclaration(
                        name="cargo", storage=Column("cargo"), shape=_shape("grade")
                    ),
                ),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "tanker"),
            ),
            Declaration(
                identity=ferry,
                value_objects=(
                    ValueObjectOccurrenceDeclaration(
                        name="deck", storage=Column("deck"), shape=_shape("label")
                    ),
                ),
                inheritance=ConcreteSubtype(ExactEntityReference(root), "ferry"),
            ),
        )
    )
    facet = inheritance.view(model)
    view = facet.entity(root)
    assert view is not None
    assert _value_object_names(view.superset_value_objects) == ["hull", "deck", "cargo"]
    assert _value_object_names(view.applicable_value_objects) == ["hull"]
    tanker_view = facet.entity(tanker)
    assert tanker_view is not None
    assert _value_object_names(tanker_view.applicable_value_objects) == ["hull", "cargo"]


# --------------------------------------------------------------------------
# Family declaration streams.
# --------------------------------------------------------------------------

_DORMANT_ATTRIBUTES: Final = [
    (ROOT, "id"),
    (ROOT, "title"),
    (LIVE, "liveValue"),
    (DORMANT_CHILD, "childZeta"),
    (DORMANT_CHILD, "childAlpha"),
    (DORMANT, "dormantValue"),
]
_DORMANT_VALUE_OBJECTS: Final = [
    (ROOT, "summary"),
    (LIVE, "liveDetail"),
    (DORMANT_CHILD, "childDetail"),
    (DORMANT, "dormantDetail"),
]


def _family(facet: InheritanceFacet, root: EntityIdentity) -> InheritanceFamilyView:
    found = facet.family(root)
    assert found is not None, root
    return found


def _entity(facet: InheritanceFacet, identity: EntityIdentity) -> InheritanceEntityView:
    found = facet.entity(identity)
    assert found is not None, identity
    return found


def _attribute_owners(members: Sequence[AttributeMetadata]) -> list[tuple[EntityIdentity, str]]:
    return [(member.identity.entity, member.identity.name) for member in members]


def _value_object_owners(
    members: Sequence[ValueObjectMetadata],
) -> list[tuple[EntityIdentity, str]]:
    return [(member.identity.entity, member.identity.path[-1]) for member in members]


@pytest.mark.parametrize("strategy", ["tph", "tpcs"])
def test_a_family_stream_appends_dormant_participants_child_before_parent(
    strategy: Literal["tph", "tpcs"],
) -> None:
    family = _family(inheritance.view(form_metamodel(dormant_family(strategy))), ROOT)
    assert _attribute_owners(family.attributes) == _DORMANT_ATTRIBUTES
    assert _value_object_owners(family.value_objects) == _DORMANT_VALUE_OBJECTS


def test_a_root_projection_is_the_prefix_of_its_family_stream() -> None:
    facet = inheritance.view(form_metamodel(dormant_family("tph")))
    family = _family(facet, ROOT)
    root = _entity(facet, ROOT)
    for stream, prefix in (
        (family.attributes, root.superset_attributes),
        (family.value_objects, root.superset_value_objects),
    ):
        assert 0 < len(prefix) < len(stream)
        assert all(member is stream[index] for index, member in enumerate(prefix))


def test_dormant_participants_keep_empty_projections() -> None:
    facet = inheritance.view(form_metamodel(dormant_family("tph")))
    for dormant in (DORMANT, DORMANT_CHILD):
        view = _entity(facet, dormant)
        projected = facet.position([dormant])
        assert projected is not None
        for answer in (view, projected):
            assert tuple(answer.concrete_subtypes) == (), dormant
            assert tuple(answer.superset_attributes) == (), dormant
            assert tuple(answer.superset_value_objects) == (), dormant


def test_every_family_participant_contributes_its_accepted_members_once() -> None:
    model = form_metamodel(dormant_family("tph"))
    family = _family(inheritance.view(model), ROOT)
    identities = [member.identity for member in (*family.attributes, *family.value_objects)]
    assert len(identities) == len(set(identities))
    for attribute in family.attributes:
        declared = model.entity(attribute.identity.entity)
        assert declared is not None
        assert declared.attribute(attribute.identity.name) is attribute
    for value_object in family.value_objects:
        declared = model.entity(value_object.identity.entity)
        assert declared is not None
        assert declared.value_object(value_object.identity.path[-1]) is value_object


def test_a_family_listed_descendants_first_compiles_the_same_stream() -> None:
    model = form_metamodel(dormant_family("tph"))
    metadata = DescendantsFirst(model)
    listed = [entity.identity for entity in metadata.entities]
    assert listed.index(DORMANT_CHILD) < listed.index(DORMANT) < listed.index(ROOT)
    expected = _family(inheritance.view(model), ROOT)
    compiled = _family(compile_facet(metadata), ROOT)
    for stream, reference in (
        (compiled.attributes, expected.attributes),
        (compiled.value_objects, expected.value_objects),
    ):
        assert len(stream) == len(reference)
        assert all(left is right for left, right in zip(stream, reference, strict=True))


def test_a_family_stream_with_a_dormant_suffix_is_a_complete_sequence() -> None:
    facet = inheritance.view(form_metamodel(dormant_family("tph")))
    attributes = _family(facet, ROOT).attributes
    boundary = len(_entity(facet, ROOT).superset_attributes)
    expected = tuple(attributes)
    assert _attribute_owners(expected) == _DORMANT_ATTRIBUTES
    assert len(attributes) == len(expected)
    assert all(attributes[index] is member for index, member in enumerate(expected))
    for index in (boundary - 1, boundary, -1, -len(expected)):
        assert attributes[index] is expected[index], index
    for outside in (len(expected), -len(expected) - 1):
        with pytest.raises(IndexError):
            attributes[outside]
    for window in (
        slice(None),
        slice(boundary - 1, boundary + 1),
        slice(1, -1),
        slice(None, None, -2),
    ):
        assert tuple(attributes[window]) == expected[window], window
    assert list(attributes) == list(attributes) == list(expected)
    assert list(reversed(attributes)) == list(reversed(expected))
    assert attributes.index(expected[boundary]) == boundary
    assert expected[-1] in attributes


@pytest.mark.parametrize(
    ("stem", "root_name", "attribute_names", "value_object_names"),
    [
        (
            "animal",
            "Animal",
            ["id", "name", "ownerId", "licenseId", "indoor", "barkVolume", "tuskLength"],
            [],
        ),
        (
            "document",
            "Document",
            ["id", "title", "folderId", "currency", "amountDue", "body", "paidAmount"],
            ["annotation"],
        ),
    ],
)
def test_a_family_without_dormant_participants_streams_its_root_supersets(
    stem: str, root_name: str, attribute_names: list[str], value_object_names: list[str]
) -> None:
    facet = _corpus(stem)
    root = _view(facet, root_name)
    family = _family(facet, root.entity)
    assert family.attributes is root.superset_attributes
    assert family.value_objects is root.superset_value_objects
    assert _attribute_names(family.attributes) == attribute_names
    assert _value_object_names(family.value_objects) == value_object_names


def test_a_standalone_entitys_projection_and_stream_are_its_declared_tuples() -> None:
    model = _formed("customer")
    facet = inheritance.view(model)
    customer = model.entity(_corpus_entity("Customer"))
    assert customer is not None
    assert customer.declared_value_objects
    view = _view(facet, "Customer")
    projected = facet.position([customer.identity])
    assert projected is not None
    family = _family(facet, customer.identity)
    for answer in (
        (view.superset_attributes, view.superset_value_objects),
        (projected.superset_attributes, projected.superset_value_objects),
        (family.attributes, family.value_objects),
    ):
        assert answer[0] is customer.declared_attributes
        assert answer[1] is customer.declared_value_objects


def test_a_family_stream_is_absent_for_every_identity_but_a_root() -> None:
    animal = _corpus("animal")
    assert animal.family(EntityIdentity("elsewhere", "Animal")) is None
    assert animal.family(_corpus_entity("Pet")) is None
    assert animal.family(_corpus_entity("Dog")) is None
    dormant_facet = inheritance.view(form_metamodel(dormant_family("tph")))
    assert dormant_facet.family(DORMANT) is None
    assert dormant_facet.family(LIVE) is None


# --------------------------------------------------------------------------
# The compiler's own contract.
# --------------------------------------------------------------------------


def _fake_entity(name: str, parent: str | None, *, concrete: bool) -> fake.FakeEntity:
    entity = EntityIdentity(None, name)
    declared = (
        None
        if parent is None
        else (
            ConcreteSubtype(EntityIdentity(None, parent))
            if concrete
            else AbstractSubtype(EntityIdentity(None, parent))
        )
    )
    return fake.FakeEntity(
        entity,
        declared_container=Table(name.lower()),
        declared_attributes=(
            AttributeMetadata(
                identity=AttributeIdentity(entity, "id"),
                type=INT64,
                storage=Column("id"),
            ),
        ),
        inheritance=declared,
    )


def test_a_cyclic_ancestry_is_a_compiler_contract_failure() -> None:
    # Validation rejects a cycle, so meeting one here means the compiler was
    # handed a candidate no accepted model can be: it raises for the formation
    # runner to classify rather than looping or publishing a facet.
    metadata = fake.FakeMetamodel(
        (_fake_entity("Pet", "Paw", concrete=False), _fake_entity("Paw", "Pet", concrete=False))
    )
    with pytest.raises(RuntimeError, match="unresolvable or cyclic"):
        compile_facet(metadata)


def test_an_ancestry_reaching_no_abstract_root_is_a_compiler_contract_failure() -> None:
    metadata = fake.FakeMetamodel(
        (
            _fake_entity("Widget", None, concrete=False),
            _fake_entity("Gadget", "Widget", concrete=True),
        )
    )
    with pytest.raises(RuntimeError, match="reaches no abstract root"):
        compile_facet(metadata)


@pytest.mark.parametrize("keys", [0, 2])
def test_a_root_without_exactly_one_key_is_a_compiler_contract_failure(keys: int) -> None:
    # Validation proves every accepted family declares exactly one key on its
    # root, so any other count means the compiler was handed metadata no
    # accepted model can be.
    widget = EntityIdentity(None, "Widget")
    metadata = fake.FakeMetamodel(
        (
            fake.FakeEntity(
                widget,
                declared_container=Table("widget"),
                declared_attributes=tuple(key(widget, f"id{index}") for index in range(keys)),
            ),
        )
    )
    with pytest.raises(RuntimeError, match=f"declares {keys} primary-key Attributes"):
        compile_facet(metadata)


def test_the_facet_copies_no_attribute_or_value_object_metadata() -> None:
    model = _formed("animal")
    facet = inheritance.view(model)
    declared = model.entity(_corpus_entity("Pet"))
    assert declared is not None
    (license_id,) = declared.declared_attributes
    dog = _view(facet, "Dog")
    assert license_id in dog.applicable_attributes
    assert dog.applicable_attribute("licenseId") is license_id
    assert license_id in _view(facet, "Animal").superset_attributes


def test_an_alternate_implementation_compiles_the_same_answers() -> None:
    # The compiler reads the metadata protocols only, so an accepted graph the
    # descriptor path never touched compiles into the same trivial views.
    facet = compile_facet(fake.parity_model())
    view = facet.entity(fake.ACCOUNT)
    assert view is not None
    assert view.root == fake.ACCOUNT
    assert view.primary_key.identity == AttributeIdentity(fake.ACCOUNT, "id")
    assert view.concrete_subtypes == (fake.ACCOUNT,)
    assert view.container == Table("account")
    assert _value_object_names(view.superset_value_objects) == ["contact"]
    audit = facet.entity(fake.AUDIT)
    assert audit is not None
    assert audit.persistence is PersistenceMode.READ_ONLY
    assert audit.strategy is None


def test_a_value_object_identity_survives_the_projection() -> None:
    facet = compile_facet(fake.parity_model())
    view = facet.entity(fake.ACCOUNT)
    assert view is not None
    (contact,) = view.superset_value_objects
    assert contact.identity == ValueObjectIdentity(fake.ACCOUNT, ("contact",))
    assert contact.attribute("email") is not None
    nested = contact.value_object("address")
    assert nested is not None
    assert nested.identity == ValueObjectIdentity(fake.ACCOUNT, ("contact", "address"))
    assert nested.attribute("street") is not None
    assert ValueObjectAttributeIdentity(nested.identity, "street") == nested.attributes[0].identity
