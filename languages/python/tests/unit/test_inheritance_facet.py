"""m-inheritance: the compiled Inheritance Facet and its typed view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

import pytest
from _metamodel_support import Declaration, identity, key, source

from _support import fake_metamodel as fake
from parallax.conformance import case_format
from parallax.core import inheritance
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import INT64, STRING
from parallax.core.inheritance import (
    FACET_KEY,
    INHERITANCE_MODULE,
    MODEL_COMPILER,
    RULE_SET,
    InheritanceEntityView,
    InheritanceFacet,
    compile_facet,
)
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
from parallax.core.model_formation import (
    MODEL_FORMATION_MODULE,
    ModelCompilerRequirement,
    RequiredRuleSet,
)
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

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


def test_the_facet_offers_only_entity_and_position_lookup() -> None:
    facet = _corpus("animal")
    assert {name for name in dir(facet) if not name.startswith("_")} == {"entity", "position"}


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
    assert dog.applicable_relationship("animals") is None
    person = _view(facet, "Person")
    assert person.applicable_relationship("pets") is not None
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
# A concrete position nested under another concrete position: a table-per-
# concrete-subtype family may place a concrete subtype under a concrete parent.
# Parent owns `parent_tbl` and is itself Child's parent; Child owns `child_tbl`.
# The two members answer different questions and are deliberately not derivable
# from each other: `container` is the ONE container a read or write of the
# position's own rows targets, while `concrete_subtypes` is every concrete node
# at or below it. For Parent those disagree — its own `parent_tbl` against
# {Child, Parent} — and that is the contract, not an unsettled answer: a read of
# a polymorphic position derives its branch tables by mapping each effective
# concrete through THAT concrete's own `container`, never by reaching for the
# position's own.
# --------------------------------------------------------------------------


def test_a_concrete_positions_own_container_is_not_its_effective_set() -> None:
    root = identity("Root")
    parent = identity("Parent")
    child = identity("Child")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                attributes=(key(root),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=parent,
                container=Table("parent_tbl"),
                inheritance=ConcreteSubtype(ExactEntityReference(root)),
            ),
            Declaration(
                identity=child,
                container=Table("child_tbl"),
                inheritance=ConcreteSubtype(ExactEntityReference(parent)),
            ),
        )
    )
    facet = inheritance.view(model)
    root_view = facet.entity(root)
    parent_view = facet.entity(parent)
    child_view = facet.entity(child)
    assert root_view is not None
    assert parent_view is not None
    assert child_view is not None
    assert root_view.container is None
    assert _names(root_view.concrete_subtypes) == ["Child", "Parent"]
    assert parent_view.container == Table("parent_tbl")
    assert _names(parent_view.concrete_subtypes) == ["Child", "Parent"]
    assert child_view.container == Table("child_tbl")
    assert _names(child_view.concrete_subtypes) == ["Child"]


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
