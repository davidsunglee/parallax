"""m-opt-lock: the Rule Set, the compiled Optimistic Lock Facet, and its typed view."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, instant, key, source

from _support import fake_metamodel as fake
from parallax.conformance import case_format
from parallax.core import inheritance, opt_lock, temporal_read
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import INT64
from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import INHERITANCE_MODULE
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    NOT_PRIMARY_KEY,
    AbstractRoot,
    AsOfAxisLocation,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    EntityLocation,
    ExactEntityReference,
    IssueCode,
    Metamodel,
    MetamodelIssue,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedEntityDeclaration,
)
from parallax.core.model_formation import (
    MODEL_FORMATION_MODULE,
    MetamodelValidationError,
    ModelCompilerRequirement,
    RequiredRuleSet,
)
from parallax.core.opt_lock import (
    FACET_KEY,
    ISSUE_CODES,
    MULTIPLE_ATTRIBUTES,
    OPT_LOCK_MODULE,
    RULE_SET,
    TEMPORAL_EXPLICIT_ATTRIBUTE,
    UNVERSIONED,
    ExplicitVersion,
    OptimisticLockFacet,
    TransactionTimeDerived,
    compile_facet,
)
from parallax.core.temporal_read import FACET_KEY as TEMPORAL_FACET_KEY
from parallax.core.temporal_read import TEMPORAL_READ_MODULE
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"
_CORPUS_NAMESPACE: Final[str] = "parallax.compatibility"

_TX_TIME = TemporalDimension.TRANSACTION_TIME
_LEDGER = identity("Ledger")


def _formed(stem: str) -> Metamodel:
    """The accepted model a corpus descriptor forms into."""
    document = case_format.safe_load_yaml((_MODELS / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return form_metamodel(
        unresolved_metamodel(parse_document(cast("Mapping[str, object]", document)))
    )


def _corpus_entity(name: str) -> EntityIdentity:
    return EntityIdentity(_CORPUS_NAMESPACE, name)


def _facet(stem: str) -> OptimisticLockFacet:
    return opt_lock.view(_formed(stem))


def _version(entity: EntityIdentity, name: str = "version") -> AttributeMetadata:
    """An Attribute this Entity declares as its optimistic-lock version."""
    return AttributeMetadata(
        identity=AttributeIdentity(entity, name),
        type=INT64,
        storage=Column(name),
        primary_key=NOT_PRIMARY_KEY,
        optimistic_locking=True,
    )


def _axis(entity: EntityIdentity) -> AsOfAxisMetadata:
    return AsOfAxisMetadata(
        dimension=_TX_TIME,
        start_attribute=AttributeIdentity(entity, "txStart"),
        end_attribute=AttributeIdentity(entity, "txEnd"),
    )


def _issues(*declarations: UnresolvedEntityDeclaration) -> tuple[MetamodelIssue, ...]:
    """The optimistic-locking issues a resolvable model is rejected with."""
    return tuple(RULE_SET.validate(accepted(source(*declarations))))


def _codes(*declarations: UnresolvedEntityDeclaration) -> list[IssueCode]:
    return [issue.code for issue in _issues(*declarations)]


# --------------------------------------------------------------------------
# The module's formation contract.
# --------------------------------------------------------------------------


def test_the_builtin_manifest_declares_this_modules_rule_set_and_compiler() -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == OPT_LOCK_MODULE)
    assert isinstance(entry.rule_set, RequiredRuleSet)
    assert entry.issue_codes == ISSUE_CODES
    assert entry.compiler == ModelCompilerRequirement(FACET_KEY)
    assert entry.required_facets == frozenset({INHERITANCE_FACET_KEY, TEMPORAL_FACET_KEY})
    assert entry.required_modules == frozenset(
        {METAMODEL_MODULE, MODEL_FORMATION_MODULE, INHERITANCE_MODULE, TEMPORAL_READ_MODULE}
    )
    assert RULE_SET in BUILTIN_PROFILE.rule_sets
    assert opt_lock.MODEL_COMPILER in BUILTIN_PROFILE.model_compilers
    assert opt_lock.MODEL_COMPILER.owner == OPT_LOCK_MODULE
    assert opt_lock.MODEL_COMPILER.facet_key == FACET_KEY
    assert opt_lock.MODEL_COMPILER.requires == frozenset(
        {INHERITANCE_FACET_KEY, TEMPORAL_FACET_KEY}
    )


def test_the_opt_lock_row_is_the_manifests_last() -> None:
    # Manifest entry order is the spec table's order, and this file's row closes
    # it — its compiler requires both facets compiled above it.
    assert BUILTIN_MANIFEST.entries[-1].owner == OPT_LOCK_MODULE


def test_a_formed_model_serves_its_facet_through_the_typed_view() -> None:
    model = _formed("account")
    assert opt_lock.view(model) is model.facet(FACET_KEY)


def test_the_facet_offers_only_key_lookup() -> None:
    assert {name for name in dir(_facet("account")) if not name.startswith("_")} == {"key"}


def test_the_owned_code_set_is_closed() -> None:
    assert sorted(ISSUE_CODES) == [MULTIPLE_ATTRIBUTES, TEMPORAL_EXPLICIT_ATTRIBUTE]


# --------------------------------------------------------------------------
# Keys over the corpus.
# --------------------------------------------------------------------------


def test_an_unversioned_non_temporal_entity_has_the_unversioned_key() -> None:
    facet = _facet("animal")
    for name in ("Animal", "Pet", "Dog", "Cat", "WildBoar", "Person"):
        assert facet.key(_corpus_entity(name)) == UNVERSIONED, name


def test_a_version_attribute_becomes_the_explicit_key() -> None:
    account = _corpus_entity("Account")
    assert _facet("account").key(account) == ExplicitVersion(AttributeIdentity(account, "version"))


def test_a_transaction_time_entity_derives_its_key_from_the_milestone_start() -> None:
    balance = _corpus_entity("Balance")
    assert _facet("balance").key(balance) == TransactionTimeDerived(
        AttributeIdentity(balance, "txStart")
    )


def test_a_bitemporal_entity_derives_its_key_from_transaction_time_alone() -> None:
    position = _corpus_entity("Position")
    assert _facet("position").key(position) == TransactionTimeDerived(
        AttributeIdentity(position, "txStart")
    )


def test_every_accepted_entity_has_a_key_and_a_miss_returns_absence() -> None:
    model = _formed("appliance")
    facet = opt_lock.view(model)
    assert all(facet.key(entity.identity) is not None for entity in model.entities)
    assert facet.key(EntityIdentity("elsewhere", "Fridge")) is None


def test_the_key_accessor_refuses_an_unrecognized_entity() -> None:
    # The consumer whose domain is the three variants themselves reads the key
    # through this, so a miss must raise rather than normalize: an Entity this
    # model does not carry has no declared version source, and answering
    # `Unversioned` for it would let a write claim an object on the strength of
    # what was missing.
    model = _formed("appliance")
    with pytest.raises(KeyError, match="no Optimistic Key"):
        opt_lock.optimistic_key(model, EntityIdentity("elsewhere", "Fridge"))
    assert opt_lock.optimistic_key(model, _corpus_entity("Fridge")) == opt_lock.view(model).key(
        _corpus_entity("Fridge")
    )


# --------------------------------------------------------------------------
# Family uniformity.
# --------------------------------------------------------------------------


def test_every_position_in_a_versioned_family_carries_the_roots_attribute() -> None:
    facet = _facet("appliance")
    root = _corpus_entity("Appliance")
    expected = ExplicitVersion(AttributeIdentity(root, "version"))
    for name in ("Appliance", "Fridge", "Oven"):
        assert facet.key(_corpus_entity(name)) == expected, name


def test_every_position_in_a_temporal_family_carries_the_roots_axis_start() -> None:
    facet = _facet("instrument")
    root = _corpus_entity("Instrument")
    expected = TransactionTimeDerived(AttributeIdentity(root, "txStart"))
    for name in ("Instrument", "Bond", "Stock"):
        assert facet.key(_corpus_entity(name)) == expected, name


def test_an_unversioned_family_is_unversioned_at_every_position() -> None:
    root = identity("Archive")
    entry = identity("ArchiveEntry")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("archive"),
                attributes=(key(root),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=entry,
                inheritance=ConcreteSubtype(ExactEntityReference(root), "entry"),
            ),
        )
    )
    facet = opt_lock.view(model)
    assert facet.key(root) == UNVERSIONED
    assert facet.key(entry) == UNVERSIONED


# --------------------------------------------------------------------------
# opt-lock-multiple-attributes.
# --------------------------------------------------------------------------


def test_two_version_attributes_on_one_entity_are_rejected() -> None:
    (issue,) = _issues(
        Declaration(
            identity=_LEDGER,
            container=Table("ledger"),
            attributes=(key(_LEDGER), _version(_LEDGER), _version(_LEDGER, "revision")),
        )
    )
    assert issue.code == MULTIPLE_ATTRIBUTES
    assert issue.location == EntityLocation(_LEDGER)
    assert issue.related == (
        AttributeLocation(AttributeIdentity(_LEDGER, "version")),
        AttributeLocation(AttributeIdentity(_LEDGER, "revision")),
    )


def test_one_version_attribute_is_accepted() -> None:
    assert (
        _codes(
            Declaration(
                identity=_LEDGER,
                container=Table("ledger"),
                attributes=(key(_LEDGER), _version(_LEDGER)),
            )
        )
        == []
    )


def test_a_root_and_a_descendant_each_declaring_one_is_left_to_inheritance() -> None:
    # Root ownership is `m-inheritance`'s rule, so this module reads one
    # position's own declarations and reports one defect once rather than once
    # per position that inherits it.
    root = identity("Vehicle")
    car = identity("Car")
    declarations = (
        Declaration(
            identity=root,
            container=Table("vehicle"),
            attributes=(key(root), _version(root)),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=car,
            attributes=(_version(car, "carVersion"),),
            inheritance=ConcreteSubtype(ExactEntityReference(root), "car"),
        ),
    )
    assert _codes(*declarations) == []
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(*declarations))
    assert [issue.code for issue in raised.value.issues] == [
        "inheritance-optimistic-locking-not-root-owned"
    ]


# --------------------------------------------------------------------------
# opt-lock-temporal-explicit-attribute.
# --------------------------------------------------------------------------


def _temporal_versioned() -> UnresolvedEntityDeclaration:
    return Declaration(
        identity=_LEDGER,
        container=Table("ledger"),
        attributes=(
            key(_LEDGER),
            _version(_LEDGER),
            instant(_LEDGER, "txStart"),
            instant(_LEDGER, "txEnd"),
        ),
        as_of_axes=(_axis(_LEDGER),),
    )


def test_a_transaction_time_entity_declaring_a_version_attribute_is_rejected() -> None:
    (issue,) = _issues(_temporal_versioned())
    assert issue.code == TEMPORAL_EXPLICIT_ATTRIBUTE
    assert issue.location == AttributeLocation(AttributeIdentity(_LEDGER, "version"))
    assert issue.related == (AsOfAxisLocation(_LEDGER, _TX_TIME),)


def test_a_temporal_entity_without_a_version_attribute_is_accepted() -> None:
    assert (
        _codes(
            Declaration(
                identity=_LEDGER,
                container=Table("ledger"),
                attributes=(
                    key(_LEDGER),
                    instant(_LEDGER, "txStart"),
                    instant(_LEDGER, "txEnd"),
                ),
                as_of_axes=(_axis(_LEDGER),),
            )
        )
        == []
    )


def test_the_two_keyed_variants_are_mutually_exclusive_by_rejection() -> None:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(_temporal_versioned()))
    assert [issue.code for issue in raised.value.issues] == [TEMPORAL_EXPLICIT_ATTRIBUTE]


def test_every_defect_of_one_entity_is_reported_in_canonical_order() -> None:
    issues = _issues(
        Declaration(
            identity=_LEDGER,
            container=Table("ledger"),
            attributes=(
                key(_LEDGER),
                _version(_LEDGER),
                _version(_LEDGER, "revision"),
                instant(_LEDGER, "txStart"),
                instant(_LEDGER, "txEnd"),
            ),
            as_of_axes=(_axis(_LEDGER),),
        )
    )
    assert [issue.code for issue in issues] == [
        MULTIPLE_ATTRIBUTES,
        TEMPORAL_EXPLICIT_ATTRIBUTE,
        TEMPORAL_EXPLICIT_ATTRIBUTE,
    ]
    assert len(set(issues)) == len(issues)


# --------------------------------------------------------------------------
# The compiler's own contract.
# --------------------------------------------------------------------------


def test_the_compiler_requires_both_facets_under_their_own_keys() -> None:
    metadata = fake.parity_model()
    inheritance_facet = inheritance.compile_facet(metadata)
    with pytest.raises(RuntimeError, match="Inheritance Facet"):
        opt_lock.MODEL_COMPILER.compile(metadata, {})
    with pytest.raises(RuntimeError, match="Temporal Facet"):
        opt_lock.MODEL_COMPILER.compile(metadata, {INHERITANCE_FACET_KEY: inheritance_facet})


def test_an_entity_a_required_facet_does_not_cover_is_a_contract_failure() -> None:
    # Both required facets cover every accepted Entity, so one compiled over a
    # different graph is a formation seam defect: the compiler raises rather than
    # inventing a family or a shape for the Entity it cannot place.
    metadata = fake.parity_model()
    narrower = fake.FakeMetamodel([entity for entity in metadata.entities[:1]])
    complete = inheritance.compile_facet(metadata)
    partial = inheritance.compile_facet(narrower)
    with pytest.raises(RuntimeError, match="Inheritance Facet view"):
        compile_facet(metadata, partial, temporal_read.compile_facet(metadata, complete))
    with pytest.raises(RuntimeError, match="Temporal Facet shape"):
        compile_facet(metadata, complete, temporal_read.compile_facet(narrower, partial))


def test_a_root_declaring_two_version_attributes_is_a_compiler_contract_failure() -> None:
    # Validation rejects a second version Attribute, so meeting one here means
    # the compiler was handed metadata no accepted model can be: it raises for
    # the formation runner to classify rather than picking one.
    entity = EntityIdentity(None, "Ledger")
    metadata = fake.FakeMetamodel(
        (
            fake.FakeEntity(
                entity,
                declared_container=Table("ledger"),
                declared_attributes=(
                    attribute(entity, "id"),
                    _version(entity),
                    _version(entity, "revision"),
                ),
            ),
        )
    )
    inheritance_facet = inheritance.compile_facet(metadata)
    temporal = temporal_read.compile_facet(metadata, inheritance_facet)
    with pytest.raises(RuntimeError, match="version"):
        compile_facet(metadata, inheritance_facet, temporal)


def test_an_alternate_implementation_compiles_the_same_answers() -> None:
    # The compiler reads the metadata protocols and the two facets only, so an
    # accepted graph the descriptor path never touched compiles into the same
    # keys.
    metadata = fake.parity_model()
    inheritance_facet = inheritance.compile_facet(metadata)
    facet = compile_facet(
        metadata, inheritance_facet, temporal_read.compile_facet(metadata, inheritance_facet)
    )
    assert facet.key(fake.ACCOUNT) == UNVERSIONED
    assert facet.key(fake.AUDIT) == TransactionTimeDerived(AttributeIdentity(fake.AUDIT, "txStart"))
    assert facet.key(EntityIdentity("elsewhere", "Account")) is None


def test_the_facet_copies_no_attribute_metadata() -> None:
    model = _formed("appliance")
    root = model.entity(_corpus_entity("Appliance"))
    assert root is not None
    version = root.attribute("version")
    assert version is not None
    fridge = opt_lock.view(model).key(_corpus_entity("Fridge"))
    assert isinstance(fridge, ExplicitVersion)
    assert fridge.attribute == version.identity
