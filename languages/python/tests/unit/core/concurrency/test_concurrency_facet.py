"""m-concurrency: the Rule Set, the compiled Concurrency Facet, and its typed accessor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

import pytest

from parallax.conformance import case_format
from parallax.core import concurrency, inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import INT64
from parallax.core.concurrency import (
    RULE_SET,
    ConcurrencyFacet,
    ExplicitVersion,
    TransactionTimeVersion,
)
from parallax.core.concurrency import _compile as concurrency_compile
from parallax.core.concurrency._compile import compile_facet
from parallax.core.concurrency._facet import UNVERSIONED
from parallax.core.concurrency._rules import MULTIPLE_VERSION_ATTRIBUTES, TEMPORAL_EXPLICIT_VERSION
from parallax.core.inheritance import _compile as inheritance_compile
from parallax.core.metamodel import (
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
    MetamodelValidationError,
)
from parallax.core.temporal_read import _compile as temporal_read_compile
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._parse import parse_document
from tests._support import fake_metadata as fake
from tests.unit._metamodel_support import (
    Declaration,
    accepted,
    identity,
    instant,
    key,
    source,
)
from tests.unit.core._family_owner_support import (
    DescendantsFirst,
    family_roots,
    record_root_derivations,
)

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


def _facet(stem: str) -> ConcurrencyFacet:
    return concurrency.concurrency_facet_of(_formed(stem))


def _version(entity: EntityIdentity, name: str = "version") -> AttributeMetadata:
    """An Attribute this Entity declares as its version."""
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
    """The version-declaration issues a resolvable model is rejected with."""
    return tuple(RULE_SET.validate(accepted(source(*declarations))))


def _codes(*declarations: UnresolvedEntityDeclaration) -> list[IssueCode]:
    return [issue.code for issue in _issues(*declarations)]


# --------------------------------------------------------------------------
# The facet's surface.
# --------------------------------------------------------------------------


def test_the_facet_offers_only_its_four_questions() -> None:
    assert {name for name in dir(_facet("account")) if not name.startswith("_")} == {
        "effective_strategy",
        "settles_against",
        "version_attribute",
        "version_source",
    }


# --------------------------------------------------------------------------
# Version sources over the corpus.
# --------------------------------------------------------------------------


def test_an_unversioned_non_temporal_entity_has_the_unversioned_source() -> None:
    facet = _facet("animal")
    for name in ("Animal", "Pet", "Dog", "Cat", "WildBoar", "Person"):
        assert facet.version_source(_corpus_entity(name)) == UNVERSIONED, name


def test_every_accepted_entity_has_a_version_source() -> None:
    model = _formed("appliance")
    facet = concurrency.concurrency_facet_of(model)
    assert all(facet.version_source(entity.identity) is not None for entity in model.entities)


# --------------------------------------------------------------------------
# Family uniformity.
# --------------------------------------------------------------------------


def test_every_position_in_a_versioned_family_carries_the_roots_attribute() -> None:
    facet = _facet("appliance")
    root = _corpus_entity("Appliance")
    expected = ExplicitVersion(AttributeIdentity(root, "version"))
    for name in ("Appliance", "Fridge", "Oven"):
        assert facet.version_source(_corpus_entity(name)) == expected, name
        assert facet.version_source(_corpus_entity(name)) is facet.version_source(root), name


def test_every_position_in_a_temporal_family_carries_the_roots_axis_start() -> None:
    facet = _facet("instrument")
    root = _corpus_entity("Instrument")
    expected = TransactionTimeVersion(AttributeIdentity(root, "txStart"))
    for name in ("Instrument", "Bond", "Stock"):
        assert facet.version_source(_corpus_entity(name)) == expected, name


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
    facet = concurrency.concurrency_facet_of(model)
    assert facet.version_source(root) == UNVERSIONED
    assert facet.version_source(entry) == UNVERSIONED


# The explicit version of each strategy, and a Transaction-Time version of each
# strategy, by root.
_KEYED_FAMILY_ROOTS: Final[dict[str, str]] = {
    "appliance": "Appliance",
    "instrument": "Instrument",
    "rate": "Rate",
    "vehicle": "Vehicle",
}


@pytest.mark.parametrize(("stem", "root_name"), sorted(_KEYED_FAMILY_ROOTS.items()))
def test_every_position_in_a_family_answers_its_roots_one_version_source_object(
    stem: str, root_name: str
) -> None:
    model = _formed(stem)
    families = inheritance.inheritance_facet_of(model)
    facet = concurrency.concurrency_facet_of(model)
    root = _corpus_entity(root_name)
    source = facet.version_source(root)
    assert isinstance(source, ExplicitVersion | TransactionTimeVersion)
    members = [
        entity.identity
        for entity in model.entities
        if (view := families.entity(entity.identity)) is not None and view.root == root
    ]
    assert len(members) > 1
    for member in members:
        assert facet.version_source(member) is source, member


def test_a_family_listed_descendants_first_derives_its_version_source_once_at_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _formed("appliance")
    metadata = DescendantsFirst(model)
    listed = [entity.identity.name for entity in metadata.entities]
    assert listed.index("Oven") < listed.index("Appliance")
    derived = record_root_derivations(monkeypatch, concurrency_compile, "_version_source")
    families = inheritance_compile.compile_facet(metadata)
    facet = compile_facet(
        metadata, families, temporal_read_compile.compile_facet(metadata, families)
    )
    assert sorted(derived, key=_canonical) == sorted(family_roots(model), key=_canonical)
    source = facet.version_source(_corpus_entity("Appliance"))
    assert isinstance(source, ExplicitVersion)
    for name in ("Fridge", "Oven"):
        assert facet.version_source(_corpus_entity(name)) is source, name


def _canonical(identity: EntityIdentity) -> tuple[str, str]:
    return identity.sort_key


# --------------------------------------------------------------------------
# concurrency-multiple-version-attributes.
# --------------------------------------------------------------------------


def test_two_version_attributes_on_one_entity_are_rejected() -> None:
    (issue,) = _issues(
        Declaration(
            identity=_LEDGER,
            container=Table("ledger"),
            attributes=(key(_LEDGER), _version(_LEDGER), _version(_LEDGER, "revision")),
        )
    )
    assert issue.code == MULTIPLE_VERSION_ATTRIBUTES
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
# concurrency-temporal-explicit-version.
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
    assert issue.code == TEMPORAL_EXPLICIT_VERSION
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


def test_the_two_versioned_variants_are_mutually_exclusive_by_rejection() -> None:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(_temporal_versioned()))
    assert [issue.code for issue in raised.value.issues] == [TEMPORAL_EXPLICIT_VERSION]


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
        MULTIPLE_VERSION_ATTRIBUTES,
        TEMPORAL_EXPLICIT_VERSION,
        TEMPORAL_EXPLICIT_VERSION,
    ]
    assert len(set(issues)) == len(issues)


# --------------------------------------------------------------------------
# The compiler's own contract.
# --------------------------------------------------------------------------


def test_an_entity_the_inheritance_facet_does_not_cover_is_a_contract_failure() -> None:
    # The Inheritance Facet covers every accepted Entity, so one compiled over a
    # different graph is a formation seam defect: the compiler raises rather than
    # inventing a family for the Entity it cannot place.
    metadata = fake.parity_metadata()
    narrower = fake.FakeCompiledMetadata([entity for entity in metadata.entities[:1]])
    complete = inheritance_compile.compile_facet(metadata)
    partial = inheritance_compile.compile_facet(narrower)
    with pytest.raises(RuntimeError, match="Inheritance Facet view"):
        compile_facet(metadata, partial, temporal_read_compile.compile_facet(metadata, complete))


def test_an_alternate_implementation_compiles_the_same_answers() -> None:
    # The compiler reads the metadata protocols and the two facets only, so an
    # accepted graph the descriptor path never touched compiles into the same
    # version sources.
    metadata = fake.parity_metadata()
    inheritance_facet = inheritance_compile.compile_facet(metadata)
    facet = compile_facet(
        metadata,
        inheritance_facet,
        temporal_read_compile.compile_facet(metadata, inheritance_facet),
    )
    assert facet.version_source(fake.ACCOUNT) == UNVERSIONED
    assert facet.version_source(fake.AUDIT) == TransactionTimeVersion(
        AttributeIdentity(fake.AUDIT, "txStart")
    )
    assert facet.version_source(EntityIdentity("elsewhere", "Account")) is None


def test_the_facet_copies_no_attribute_metadata() -> None:
    model = _formed("appliance")
    root = model.entity(_corpus_entity("Appliance"))
    assert root is not None
    version = root.attribute("version")
    assert version is not None
    fridge = concurrency.concurrency_facet_of(model).version_source(_corpus_entity("Fridge"))
    assert isinstance(fridge, ExplicitVersion)
    assert fridge.attribute == version.identity
