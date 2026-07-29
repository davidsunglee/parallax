"""m-temporal-read: the compiled Temporal Facet and its typed view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, identity, instant, key, source

from _support import fake_metamodel as fake
from parallax.conformance import case_format
from parallax.core import inheritance, opt_lock, relationship, temporal_read
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import INHERITANCE_MODULE
from parallax.core.inheritance import MODEL_COMPILER as INHERITANCE_COMPILER
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeIdentity,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    Metamodel,
    Table,
    TablePerHierarchy,
    TemporalDimension,
)
from parallax.core.model_formation import (
    FORMATION_COMPILER_FAILED,
    FORMATION_FACET_DUPLICATE,
    FORMATION_FACET_MISSING,
    MODEL_FORMATION_MODULE,
    FormationContractError,
    MetadataCompiler,
    ModelCompiler,
    ModelCompilerRequirement,
    ModelRuleSet,
    form,
)
from parallax.core.opt_lock import MODEL_COMPILER as OPT_LOCK_COMPILER
from parallax.core.relationship import MODEL_COMPILER as RELATIONSHIP_COMPILER
from parallax.core.storage_layout import MODEL_COMPILER as STORAGE_LAYOUT_COMPILER
from parallax.core.temporal_read import (
    FACET_KEY,
    NON_TEMPORAL,
    TEMPORAL_READ_MODULE,
    Bitemporal,
    TemporalFacet,
    TransactionTimeOnly,
    compile_facet,
)
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

_MODELS = case_format.find_repo_root() / "core" / "compatibility" / "models"
_CORPUS_NAMESPACE: Final[str] = "parallax.compatibility"

_VALID_TIME = TemporalDimension.VALID_TIME
_TX_TIME = TemporalDimension.TRANSACTION_TIME


def _formed(stem: str) -> Metamodel:
    """The accepted model a corpus descriptor forms into."""
    document = case_format.safe_load_yaml((_MODELS / f"{stem}.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return form_metamodel(
        unresolved_metamodel(parse_document(cast("Mapping[str, object]", document)))
    )


def _corpus_entity(name: str) -> EntityIdentity:
    return EntityIdentity(_CORPUS_NAMESPACE, name)


def _shape(facet: TemporalFacet, name: str) -> object:
    found = facet.shape(_corpus_entity(name))
    assert found is not None, name
    return found


@dataclass(frozen=True, slots=True)
class _Profile:
    """A Formation Profile whose compiler set the caller chooses."""

    rule_sets: tuple[ModelRuleSet, ...]
    metadata_compiler: MetadataCompiler
    model_compilers: tuple[ModelCompiler[Any], ...]


def _profile(*compilers: ModelCompiler[Any]) -> _Profile:
    """The built-in profile with ``compilers`` in place of its own compiler set."""
    return _Profile(
        rule_sets=tuple(BUILTIN_PROFILE.rule_sets),
        metadata_compiler=BUILTIN_PROFILE.metadata_compiler,
        model_compilers=compilers,
    )


def _valid_time_only() -> Sequence[Declaration]:
    """A model declaring Valid Time and no Transaction Time.

    Nothing in formation rejects this shape — the descriptor schema and the
    Python framework bases are what exclude it — so it is the input that reaches
    the compiler's impossible-state boundary.
    """
    entity = identity("Correction")
    return (
        Declaration(
            identity=entity,
            container=Table("correction"),
            attributes=(key(entity), instant(entity, "valid_start"), instant(entity, "valid_end")),
            as_of_axes=(
                AsOfAxisMetadata(
                    dimension=_VALID_TIME,
                    start_attribute=AttributeIdentity(entity, "valid_start"),
                    end_attribute=AttributeIdentity(entity, "valid_end"),
                ),
            ),
        ),
    )


# --------------------------------------------------------------------------
# The module's formation contract.
# --------------------------------------------------------------------------


def test_the_builtin_manifest_declares_this_modules_compiler_and_no_rule_set() -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == TEMPORAL_READ_MODULE)
    assert entry.rule_set is None
    assert entry.issue_codes == frozenset()
    assert entry.compiler == ModelCompilerRequirement(FACET_KEY)
    assert entry.required_facets == frozenset({INHERITANCE_FACET_KEY})
    assert entry.required_modules == frozenset(
        {METAMODEL_MODULE, MODEL_FORMATION_MODULE, INHERITANCE_MODULE}
    )
    assert all(rule_set.owner != TEMPORAL_READ_MODULE for rule_set in BUILTIN_PROFILE.rule_sets)
    assert temporal_read.MODEL_COMPILER in BUILTIN_PROFILE.model_compilers
    assert temporal_read.MODEL_COMPILER.owner == TEMPORAL_READ_MODULE
    assert temporal_read.MODEL_COMPILER.facet_key == FACET_KEY
    assert temporal_read.MODEL_COMPILER.requires == frozenset({INHERITANCE_FACET_KEY})


def test_the_temporal_row_follows_relationship_and_precedes_opt_lock() -> None:
    # Manifest entry order is the spec table's order, and this file's row is its
    # sixth.
    owners = [entry.owner for entry in BUILTIN_MANIFEST.entries]
    assert owners.index("m-relationship") < owners.index(TEMPORAL_READ_MODULE)
    assert owners.index(TEMPORAL_READ_MODULE) < owners.index("m-opt-lock")


def test_a_formed_model_serves_its_facet_through_the_typed_view() -> None:
    model = _formed("balance")
    assert temporal_read.view(model) is model.facet(FACET_KEY)


def test_the_facet_offers_only_shape_and_axis_lookup() -> None:
    facet = temporal_read.view(_formed("balance"))
    assert {name for name in dir(facet) if not name.startswith("_")} == {"shape", "axis"}


# --------------------------------------------------------------------------
# Shapes over the corpus.
# --------------------------------------------------------------------------


def test_a_non_temporal_entity_has_the_non_temporal_shape() -> None:
    facet = temporal_read.view(_formed("animal"))
    for name in ("Animal", "Pet", "Dog", "Cat", "WildBoar", "Person"):
        assert _shape(facet, name) == NON_TEMPORAL, name


def test_a_transaction_time_only_entity_carries_that_one_axis() -> None:
    model = _formed("balance")
    balance = model.entity(_corpus_entity("Balance"))
    assert balance is not None
    shape = temporal_read.view(model).shape(balance.identity)
    assert isinstance(shape, TransactionTimeOnly)
    assert shape.transaction_time is balance.as_of_axis(_TX_TIME)


def test_a_bitemporal_entity_carries_valid_time_before_transaction_time() -> None:
    model = _formed("position")
    position = model.entity(_corpus_entity("Position"))
    assert position is not None
    shape = temporal_read.view(model).shape(position.identity)
    assert isinstance(shape, Bitemporal)
    assert shape.valid_time is position.as_of_axis(_VALID_TIME)
    assert shape.transaction_time is position.as_of_axis(_TX_TIME)


def test_axis_lookup_answers_only_the_dimensions_the_shape_declares() -> None:
    facet = temporal_read.view(_formed("balance"))
    balance = _corpus_entity("Balance")
    assert facet.axis(balance, _TX_TIME) is not None
    assert facet.axis(balance, _VALID_TIME) is None
    animals = temporal_read.view(_formed("animal"))
    assert animals.axis(_corpus_entity("Dog"), _TX_TIME) is None
    assert animals.axis(_corpus_entity("Dog"), _VALID_TIME) is None


def test_axis_lookup_answers_both_dimensions_of_a_bitemporal_shape() -> None:
    model = _formed("position")
    facet = temporal_read.view(model)
    position = _corpus_entity("Position")
    shape = facet.shape(position)
    assert isinstance(shape, Bitemporal)
    assert facet.axis(position, _VALID_TIME) is shape.valid_time
    assert facet.axis(position, _TX_TIME) is shape.transaction_time


def test_every_accepted_entity_has_a_shape_and_a_miss_returns_absence() -> None:
    model = _formed("instrument")
    facet = temporal_read.view(model)
    assert all(facet.shape(entity.identity) is not None for entity in model.entities)
    assert facet.shape(EntityIdentity("elsewhere", "Bond")) is None
    assert facet.axis(EntityIdentity("elsewhere", "Bond"), _TX_TIME) is None


# --------------------------------------------------------------------------
# Family uniformity.
# --------------------------------------------------------------------------


def test_every_position_in_a_family_answers_with_its_roots_axes() -> None:
    model = _formed("instrument")
    facet = temporal_read.view(model)
    root = model.entity(_corpus_entity("Instrument"))
    assert root is not None
    for name in ("Instrument", "Bond", "Stock"):
        shape = facet.shape(_corpus_entity(name))
        assert isinstance(shape, Bitemporal), name
        assert shape.valid_time is root.as_of_axis(_VALID_TIME), name
        assert shape.transaction_time is root.as_of_axis(_TX_TIME), name


def test_a_descendant_axis_keeps_the_declaring_roots_attribute_identities() -> None:
    facet = temporal_read.view(_formed("instrument"))
    axis = facet.axis(_corpus_entity("Bond"), _TX_TIME)
    assert axis is not None
    assert axis.start_attribute == AttributeIdentity(_corpus_entity("Instrument"), "tx_start")
    assert axis.end_attribute == AttributeIdentity(_corpus_entity("Instrument"), "tx_end")


def test_a_family_formed_by_hand_shares_one_shape() -> None:
    root = identity("Ledger")
    entry = identity("LedgerEntry")
    model = form_metamodel(
        source(
            Declaration(
                identity=root,
                container=Table("ledger"),
                attributes=(key(root), instant(root, "tx_start"), instant(root, "tx_end")),
                as_of_axes=(
                    AsOfAxisMetadata(
                        dimension=_TX_TIME,
                        start_attribute=AttributeIdentity(root, "tx_start"),
                        end_attribute=AttributeIdentity(root, "tx_end"),
                    ),
                ),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=entry,
                inheritance=ConcreteSubtype(ExactEntityReference(root), "entry"),
            ),
        )
    )
    facet = temporal_read.view(model)
    assert facet.shape(root) == facet.shape(entry)
    assert facet.axis(entry, _TX_TIME) == facet.axis(root, _TX_TIME)


# --------------------------------------------------------------------------
# Valid-Time-Only is unrepresentable.
# --------------------------------------------------------------------------


def _axis(dimension: TemporalDimension) -> AsOfAxisMetadata:
    entity = identity("Correction")
    return AsOfAxisMetadata(
        dimension=dimension,
        start_attribute=AttributeIdentity(entity, "start"),
        end_attribute=AttributeIdentity(entity, "end"),
    )


def test_no_shape_variant_holds_valid_time_without_transaction_time() -> None:
    with pytest.raises(ValueError, match="Transaction-Time axis"):
        TransactionTimeOnly(_axis(_VALID_TIME))
    with pytest.raises(ValueError, match="Valid-Time axis"):
        Bitemporal(_axis(_TX_TIME), _axis(_TX_TIME))
    with pytest.raises(ValueError, match="Transaction-Time axis"):
        Bitemporal(_axis(_VALID_TIME), _axis(_VALID_TIME))


def test_a_valid_time_only_family_is_a_compiler_contract_failure() -> None:
    # No frontend can author this shape, so the compiler treats it the way its
    # siblings treat any impossible state: it raises for the runner to classify
    # rather than inventing a shape the algebra does not have.
    with pytest.raises(FormationContractError) as raised:
        form_metamodel(source(*_valid_time_only()))
    assert raised.value.code == FORMATION_COMPILER_FAILED
    assert raised.value.owner == TEMPORAL_READ_MODULE
    assert isinstance(raised.value.cause, RuntimeError)
    assert "Valid-Time-Only" in str(raised.value.cause)


# --------------------------------------------------------------------------
# The compiler's own contract.
# --------------------------------------------------------------------------


def test_the_compiler_requires_the_inheritance_facet_under_its_own_key() -> None:
    metadata = fake.parity_model()
    with pytest.raises(RuntimeError, match="Inheritance Facet"):
        temporal_read.MODEL_COMPILER.compile(metadata, {})


def test_an_entity_the_inheritance_facet_does_not_cover_is_a_contract_failure() -> None:
    # The Inheritance Facet covers every accepted Entity, so a required facet
    # compiled over a different graph is a formation seam defect: the compiler
    # raises rather than inventing a family for the Entity it cannot place.
    metadata = fake.parity_model()
    narrower = fake.FakeMetamodel([entity for entity in metadata.entities[:1]])
    with pytest.raises(RuntimeError, match="Inheritance Facet view"):
        compile_facet(metadata, inheritance.compile_facet(narrower))


def test_an_alternate_implementation_compiles_the_same_answers() -> None:
    # The compiler reads the metadata protocols only, so an accepted graph the
    # descriptor path never touched compiles into the same shapes.
    metadata = fake.parity_model()
    facet = compile_facet(metadata, inheritance.compile_facet(metadata))
    assert facet.shape(fake.ACCOUNT) == NON_TEMPORAL
    audit = facet.shape(fake.AUDIT)
    assert isinstance(audit, TransactionTimeOnly)
    assert audit.transaction_time.start_attribute == AttributeIdentity(fake.AUDIT, "tx_start")
    assert facet.axis(fake.AUDIT, _VALID_TIME) is None


# --------------------------------------------------------------------------
# Facet dependency ordering and the complete facet set.
# --------------------------------------------------------------------------


def test_a_profile_missing_the_required_inheritance_compiler_fails_before_execution() -> None:
    profile = _profile(
        RELATIONSHIP_COMPILER,
        STORAGE_LAYOUT_COMPILER,
        temporal_read.MODEL_COMPILER,
        OPT_LOCK_COMPILER,
    )
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_time_only()), BUILTIN_MANIFEST, profile)
    assert raised.value.code == FORMATION_FACET_MISSING
    assert raised.value.owner == INHERITANCE_MODULE


def test_a_profile_installing_one_facet_key_twice_fails_before_execution() -> None:
    profile = _profile(
        INHERITANCE_COMPILER,
        RELATIONSHIP_COMPILER,
        STORAGE_LAYOUT_COMPILER,
        temporal_read.MODEL_COMPILER,
        temporal_read.MODEL_COMPILER,
        OPT_LOCK_COMPILER,
    )
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_time_only()), BUILTIN_MANIFEST, profile)
    assert raised.value.code == FORMATION_FACET_DUPLICATE
    assert raised.value.owner == TEMPORAL_READ_MODULE


def test_an_accepted_model_installs_the_complete_facet_set_at_once() -> None:
    model = _formed("balance")
    assert inheritance.view(model) is not None
    assert relationship.view(model) is not None
    assert temporal_read.view(model) is not None
    assert opt_lock.view(model) is not None
