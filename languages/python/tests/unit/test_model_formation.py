"""m-model-formation: the manifest, the contributor contracts, and the runner."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.metamodel import (
    METADATA_COMPILER,
    METAMODEL_MODULE,
    PRIMARY_KEY_MISSING,
    PRIMARY_KEY_MULTIPLE,
    RESOLVER_ISSUE_CODES,
    CandidateMetamodel,
    CompiledMetadata,
    EntityIdentity,
    EntityLocation,
    FacetKey,
    IssueCode,
    MetamodelIssue,
    Rejected,
    UnresolvedEntityDeclaration,
    UnresolvedMetamodel,
)
from parallax.core.model_formation import (
    FIXED_RESOLVER,
    FORMATION_COMPILER_FAILED,
    FORMATION_CONTRACT_CODES,
    FORMATION_FACET_DUPLICATE,
    FORMATION_FACET_MISSING,
    FORMATION_ISSUE_CODE_INVALID,
    FORMATION_ISSUE_DUPLICATE,
    FORMATION_ISSUE_UNDECLARED,
    FORMATION_PROFILE_DRIFT,
    FORMATION_RESOLVER_FAILED,
    FORMATION_RESOLVER_RESULT_INVALID,
    FORMATION_RULE_SET_FAILED,
    FORMATION_RULE_SET_RESULT_INVALID,
    METADATA_COMPILER_REQUIRED,
    REQUIRED_RULE_SET,
    FormationContractError,
    FormationManifest,
    FormationManifestEntry,
    MetadataCompiler,
    MetamodelValidationError,
    ModelCompiler,
    ModelCompilerRequirement,
    ModelRuleSet,
    ModuleIdentity,
    form,
)
from parallax.core.model_formation import _runner as runner

pytestmark = pytest.mark.unit

_ORDER = identity("Order")
_ITEM = identity("Item")

_INHERITANCE: Final[ModuleIdentity] = "m-inheritance"
_RELATIONSHIP: Final[ModuleIdentity] = "m-relationship"
_TEMPORAL: Final[ModuleIdentity] = "m-temporal-read"
_OPT_LOCK: Final[ModuleIdentity] = "m-opt-lock"

_INHERITANCE_FACET: Final[FacetKey[str]] = FacetKey(_INHERITANCE)
_RELATIONSHIP_FACET: Final[FacetKey[str]] = FacetKey(_RELATIONSHIP)
_TEMPORAL_FACET: Final[FacetKey[str]] = FacetKey(_TEMPORAL)
_OPT_LOCK_FACET: Final[FacetKey[str]] = FacetKey(_OPT_LOCK)

_CYCLE: Final[IssueCode] = "inheritance-cycle"
_SHADOWING: Final[IssueCode] = "inheritance-member-shadowing"


# --------------------------------------------------------------------------
# Hand-built formation input and contributor doubles.
# --------------------------------------------------------------------------


def _valid_model() -> Sequence[UnresolvedEntityDeclaration]:
    return (
        Declaration(identity=_ORDER, attributes=(key(_ORDER), attribute(_ORDER, "sku"))),
        Declaration(identity=_ITEM, attributes=(key(_ITEM),)),
    )


def _invalid_model() -> Sequence[UnresolvedEntityDeclaration]:
    """A model with one defect per Entity, so aggregation and order are visible."""
    return (
        Declaration(identity=_ORDER, attributes=(attribute(_ORDER, "sku"),)),
        Declaration(identity=_ITEM, attributes=(key(_ITEM, "id"), key(_ITEM, "sku"))),
    )


@dataclass(frozen=True, slots=True)
class _ExplodingSource:
    """An Unresolved Metamodel whose enumeration fails inside the resolver."""

    @property
    def entities(self) -> Sequence[UnresolvedEntityDeclaration]:
        raise RuntimeError("the frontend could not enumerate its declarations")


@dataclass(frozen=True, slots=True)
class _Profile:
    """An explicitly composed profile; every member is supplied by name."""

    rule_sets: tuple[ModelRuleSet, ...] = ()
    metadata_compiler: MetadataCompiler = METADATA_COMPILER
    model_compilers: tuple[ModelCompiler[Any], ...] = ()


def _call_log() -> list[ModuleIdentity]:
    """A fresh per-contributor invocation log."""
    return []


def _facet_log() -> dict[ModuleIdentity, tuple[str, ...]]:
    """A fresh per-compiler record of the facet owners it was handed."""
    return {}


@dataclass(frozen=True, slots=True)
class _RuleSet:
    """A Rule Set returning exactly the issues it was composed with."""

    owner: ModuleIdentity
    issue_codes: frozenset[IssueCode] = frozenset()
    emitted: tuple[MetamodelIssue, ...] = ()
    calls: list[ModuleIdentity] = field(default_factory=_call_log)

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        self.calls.append(self.owner)
        return self.emitted


@dataclass(frozen=True, slots=True)
class _MisbehavingRuleSet:
    """A Rule Set that raises, or returns something its contract forbids."""

    owner: ModuleIdentity
    issue_codes: frozenset[IssueCode] = frozenset()
    returns: object = ()
    raises: Exception | None = None

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        if self.raises is not None:
            raise self.raises
        return cast(Sequence[MetamodelIssue], self.returns)


@dataclass(frozen=True, slots=True)
class _Compiler:
    """A Model Compiler recording its invocation and the facets it was handed."""

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()
    calls: list[ModuleIdentity] = field(default_factory=_call_log)
    handed: dict[ModuleIdentity, tuple[str, ...]] = field(default_factory=_facet_log)

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        self.calls.append(self.owner)
        self.handed[self.owner] = tuple(sorted(str(name.owner) for name in required_facets))
        return f"facet of {self.owner}"


@dataclass(frozen=True, slots=True)
class _FailingCompiler:
    """A Model Compiler that raises on accepted metadata."""

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        raise RuntimeError("the compiler reached an impossible state")


@dataclass(frozen=True, slots=True)
class _MetadataCompiler:
    """A Metadata Compiler double with a settable owner and failure mode."""

    owner: ModuleIdentity = METAMODEL_MODULE
    raises: bool = False

    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata:
        if self.raises:
            raise RuntimeError("the Metadata Compiler reached an impossible state")
        return METADATA_COMPILER.compile(candidate)


def _resolver_row(
    *, issue_codes: frozenset[IssueCode] = RESOLVER_ISSUE_CODES
) -> FormationManifestEntry:
    return FormationManifestEntry(
        owner=METAMODEL_MODULE,
        rule_set=FIXED_RESOLVER,
        issue_codes=issue_codes,
        compiler=METADATA_COMPILER_REQUIRED,
    )


def _rule_set_row(owner: ModuleIdentity, *codes: IssueCode) -> FormationManifestEntry:
    return FormationManifestEntry(
        owner=owner, rule_set=REQUIRED_RULE_SET, issue_codes=frozenset(codes)
    )


def _compiler_row(
    owner: ModuleIdentity,
    facet: FacetKey[Any],
    *,
    required_facets: frozenset[FacetKey[Any]] = frozenset(),
    required_modules: frozenset[ModuleIdentity] | None = None,
) -> FormationManifestEntry:
    modules = (
        frozenset(name.owner for name in required_facets)
        if required_modules is None
        else required_modules
    )
    return FormationManifestEntry(
        owner=owner,
        compiler=ModelCompilerRequirement(facet),
        required_facets=required_facets,
        required_modules=modules,
    )


def _issue(code: IssueCode, entity: EntityIdentity = _ORDER) -> MetamodelIssue:
    return MetamodelIssue(code, EntityLocation(entity))


def _contract_failure(
    manifest: FormationManifest,
    profile: _Profile,
    code: str,
    *,
    owner: ModuleIdentity | None = None,
) -> FormationContractError:
    """Form a valid model and return the contract failure the composition raises."""
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_model()), manifest, profile)
    assert raised.value.code == code
    if owner is not None:
        assert raised.value.owner == owner
    return raised.value


# --------------------------------------------------------------------------
# The built-in composition root forms a model end to end.
# --------------------------------------------------------------------------


def test_the_builtin_manifest_declares_the_fixed_resolver_and_metadata_compiler() -> None:
    (entry,) = BUILTIN_MANIFEST.entries
    assert entry.owner == METAMODEL_MODULE
    assert entry.rule_set is FIXED_RESOLVER
    assert entry.issue_codes == RESOLVER_ISSUE_CODES
    assert entry.compiler is METADATA_COMPILER_REQUIRED
    assert BUILTIN_PROFILE.metadata_compiler is METADATA_COMPILER
    assert BUILTIN_PROFILE.rule_sets == ()
    assert BUILTIN_PROFILE.model_compilers == ()


def test_a_hand_built_model_forms_into_an_accepted_metamodel() -> None:
    model = form_metamodel(source(*_valid_model()))
    assert [entity.identity for entity in model.entities] == [_ITEM, _ORDER]
    order = model.entity(_ORDER)
    assert order is not None
    assert order.attribute("sku") is not None
    assert model.entity(EntityIdentity("parallax.test", "Absent")) is None


def test_an_invalid_model_fails_with_every_issue_in_canonical_order() -> None:
    with pytest.raises(MetamodelValidationError) as raised:
        form_metamodel(source(*_invalid_model()))
    assert [(issue.code, issue.location) for issue in raised.value.issues] == [
        (PRIMARY_KEY_MULTIPLE, EntityLocation(_ITEM)),
        (PRIMARY_KEY_MISSING, EntityLocation(_ORDER)),
    ]


def test_a_validation_failure_reports_at_least_one_issue() -> None:
    with pytest.raises(ValueError, match="at least one issue"):
        MetamodelValidationError(())


def test_the_contract_code_vocabulary_is_closed() -> None:
    assert sorted(FORMATION_CONTRACT_CODES) == [
        FORMATION_COMPILER_FAILED,
        FORMATION_FACET_DUPLICATE,
        FORMATION_FACET_MISSING,
        FORMATION_ISSUE_CODE_INVALID,
        FORMATION_ISSUE_DUPLICATE,
        FORMATION_ISSUE_UNDECLARED,
        FORMATION_PROFILE_DRIFT,
        FORMATION_RESOLVER_FAILED,
        FORMATION_RESOLVER_RESULT_INVALID,
        FORMATION_RULE_SET_FAILED,
        FORMATION_RULE_SET_RESULT_INVALID,
    ]


# --------------------------------------------------------------------------
# Manifest construction constraints.
# --------------------------------------------------------------------------


def test_a_manifest_declares_at_least_one_entry() -> None:
    with pytest.raises(ValueError, match="at least one entry"):
        FormationManifest(())


def test_a_manifest_names_each_owner_once() -> None:
    with pytest.raises(ValueError, match="names each owner once"):
        FormationManifest((_resolver_row(), _rule_set_row(METAMODEL_MODULE)))


# --------------------------------------------------------------------------
# Profile drift, in the order the checks run.
# --------------------------------------------------------------------------


def test_a_manifest_without_exactly_one_metadata_compiler_row_is_drift() -> None:
    manifest = FormationManifest((_rule_set_row(_INHERITANCE, _CYCLE),))
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE})),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT)


def test_a_metadata_compiler_owned_by_another_module_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(),))
    profile = _Profile(metadata_compiler=_MetadataCompiler(owner=_INHERITANCE))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_a_manifest_without_exactly_one_fixed_resolver_row_is_drift() -> None:
    manifest = FormationManifest(
        (
            FormationManifestEntry(owner=METAMODEL_MODULE, compiler=METADATA_COMPILER_REQUIRED),
            _rule_set_row(_INHERITANCE, _CYCLE),
        )
    )
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE})),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT)


def test_a_missing_rule_set_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    _contract_failure(manifest, _Profile(), FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_an_undeclared_rule_set_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(),))
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE})),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_a_duplicate_rule_set_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    declared = _RuleSet(_INHERITANCE, frozenset({_CYCLE}))
    _contract_failure(
        manifest,
        _Profile(rule_sets=(declared, declared)),
        FORMATION_PROFILE_DRIFT,
        owner=_INHERITANCE,
    )


def test_a_rule_set_declaring_other_codes_than_its_manifest_row_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({_SHADOWING})),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_a_declared_code_outside_its_owners_catalog_stem_is_invalid() -> None:
    manifest = FormationManifest(
        (_resolver_row(), _rule_set_row(_INHERITANCE, "value-object-empty"))
    )
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({"value-object-empty"})),))
    _contract_failure(manifest, profile, FORMATION_ISSUE_CODE_INVALID, owner=_INHERITANCE)


def test_a_malformed_declared_code_is_invalid() -> None:
    manifest = FormationManifest(
        (_resolver_row(), _rule_set_row(_INHERITANCE, "inheritance-Cycle"))
    )
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({"inheritance-Cycle"})),))
    _contract_failure(manifest, profile, FORMATION_ISSUE_CODE_INVALID, owner=_INHERITANCE)


def test_two_rows_claiming_one_issue_code_is_drift() -> None:
    """One catalog stem nested inside another lets two owners spell one code legally."""
    shared: IssueCode = "opt-lock-multiple-attributes"
    manifest = FormationManifest(
        (_resolver_row(), _rule_set_row("m-opt", shared), _rule_set_row(_OPT_LOCK, shared))
    )
    profile = _Profile(
        rule_sets=(_RuleSet("m-opt", frozenset({shared})), _RuleSet(_OPT_LOCK, frozenset({shared})))
    )
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_OPT_LOCK)


def test_an_undeclared_model_compiler_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(),))
    profile = _Profile(model_compilers=(_Compiler(_INHERITANCE, _INHERITANCE_FACET),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_a_missing_model_compiler_is_a_missing_facet() -> None:
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    _contract_failure(manifest, _Profile(), FORMATION_FACET_MISSING, owner=_INHERITANCE)


def test_a_compiler_installing_another_key_than_its_manifest_row_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    profile = _Profile(model_compilers=(_Compiler(_INHERITANCE, FacetKey(_INHERITANCE + "-alt")),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_one_facet_key_installed_twice_is_a_duplicate_facet() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(_RELATIONSHIP, _RELATIONSHIP_FACET),
        )
    )
    profile = _Profile(
        model_compilers=(
            _Compiler(_INHERITANCE, _INHERITANCE_FACET),
            _Compiler(_RELATIONSHIP, _RELATIONSHIP_FACET),
            _Compiler(_RELATIONSHIP, _RELATIONSHIP_FACET),
        )
    )
    _contract_failure(manifest, profile, FORMATION_FACET_DUPLICATE, owner=_RELATIONSHIP)


def test_a_compiler_installing_a_key_another_module_owns_is_drift() -> None:
    borrowed: FacetKey[str] = FacetKey(_RELATIONSHIP)
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, borrowed)))
    profile = _Profile(model_compilers=(_Compiler(_INHERITANCE, borrowed),))
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_requiring_a_facet_no_row_compiles_is_a_missing_facet() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_OPT_LOCK_FACET})),
        )
    )
    profile = _Profile(
        model_compilers=(_Compiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_OPT_LOCK_FACET})),)
    )
    _contract_failure(manifest, profile, FORMATION_FACET_MISSING, owner=_OPT_LOCK)


def test_a_facet_dependency_cycle_is_drift() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(
                _INHERITANCE, _INHERITANCE_FACET, required_facets=frozenset({_TEMPORAL_FACET})
            ),
            _compiler_row(
                _TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_INHERITANCE_FACET})
            ),
        )
    )
    profile = _Profile(
        model_compilers=(
            _Compiler(_INHERITANCE, _INHERITANCE_FACET, frozenset({_TEMPORAL_FACET})),
            _Compiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_INHERITANCE_FACET})),
        )
    )
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)


def test_requiring_a_facet_without_declaring_its_module_is_drift() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(
                _TEMPORAL,
                _TEMPORAL_FACET,
                required_facets=frozenset({_INHERITANCE_FACET}),
                required_modules=frozenset(),
            ),
        )
    )
    profile = _Profile(
        model_compilers=(
            _Compiler(_INHERITANCE, _INHERITANCE_FACET),
            _Compiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_INHERITANCE_FACET})),
        )
    )
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_TEMPORAL)


def test_a_compiler_requiring_other_facets_than_its_manifest_row_is_drift() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(
                _TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_INHERITANCE_FACET})
            ),
        )
    )
    profile = _Profile(
        model_compilers=(
            _Compiler(_INHERITANCE, _INHERITANCE_FACET),
            _Compiler(_TEMPORAL, _TEMPORAL_FACET),
        )
    )
    _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_TEMPORAL)


# --------------------------------------------------------------------------
# Contributor contract failures.
# --------------------------------------------------------------------------


def test_a_resolver_that_raises_is_a_contract_failure() -> None:
    with pytest.raises(FormationContractError) as raised:
        form(_ExplodingSource(), BUILTIN_MANIFEST, BUILTIN_PROFILE)
    assert raised.value.code == FORMATION_RESOLVER_FAILED
    assert raised.value.owner == METAMODEL_MODULE
    assert isinstance(raised.value.cause, RuntimeError)
    assert raised.value.__cause__ is raised.value.cause


def _returns_a_foreign_value(unresolved: UnresolvedMetamodel) -> object:
    return "not a resolution result"


def _returns_an_empty_rejection(unresolved: UnresolvedMetamodel) -> object:
    return Rejected(())


def _returns_a_mutable_rejection(unresolved: UnresolvedMetamodel) -> object:
    return Rejected([_issue(PRIMARY_KEY_MISSING)])  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "broken",
    [_returns_a_foreign_value, _returns_an_empty_rejection, _returns_a_mutable_rejection],
    ids=["foreign-value", "empty-rejection", "mutable-rejection"],
)
def test_a_resolver_result_outside_its_contract_is_a_contract_failure(
    monkeypatch: pytest.MonkeyPatch, broken: object
) -> None:
    monkeypatch.setattr(runner, "resolve", broken)
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_model()), BUILTIN_MANIFEST, BUILTIN_PROFILE)
    assert raised.value.code == FORMATION_RESOLVER_RESULT_INVALID
    assert raised.value.owner == METAMODEL_MODULE


def test_a_resolver_code_outside_its_declared_set_is_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(issue_codes=frozenset({"metamodel-index-empty"})),))
    with pytest.raises(FormationContractError) as raised:
        form(source(*_invalid_model()), manifest, BUILTIN_PROFILE)
    assert raised.value.code == FORMATION_ISSUE_UNDECLARED
    assert raised.value.owner == METAMODEL_MODULE


def test_a_rule_set_that_raises_is_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    profile = _Profile(
        rule_sets=(
            _MisbehavingRuleSet(_INHERITANCE, frozenset({_CYCLE}), raises=RuntimeError("defect")),
        )
    )
    failure = _contract_failure(manifest, profile, FORMATION_RULE_SET_FAILED, owner=_INHERITANCE)
    assert isinstance(failure.cause, RuntimeError)


@pytest.mark.parametrize(
    "returns",
    [[_issue(_CYCLE)], ("not an issue",)],
    ids=["mutable-collection", "non-issue-element"],
)
def test_a_rule_set_result_outside_its_contract_is_a_contract_failure(returns: object) -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    profile = _Profile(
        rule_sets=(_MisbehavingRuleSet(_INHERITANCE, frozenset({_CYCLE}), returns=returns),)
    )
    _contract_failure(manifest, profile, FORMATION_RULE_SET_RESULT_INVALID, owner=_INHERITANCE)


def test_an_emitted_code_outside_its_owners_stem_is_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    profile = _Profile(
        rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE}), (_issue("relationship-cycle"),)),)
    )
    _contract_failure(manifest, profile, FORMATION_ISSUE_CODE_INVALID, owner=_INHERITANCE)


def test_an_emitted_undeclared_code_is_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    profile = _Profile(
        rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE}), (_issue(_SHADOWING),)),)
    )
    _contract_failure(manifest, profile, FORMATION_ISSUE_UNDECLARED, owner=_INHERITANCE)


def test_two_equal_emitted_issues_are_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(), _rule_set_row(_INHERITANCE, _CYCLE)))
    repeated = (
        MetamodelIssue(_CYCLE, EntityLocation(_ORDER), message="one wording"),
        MetamodelIssue(_CYCLE, EntityLocation(_ORDER), message="another wording"),
    )
    profile = _Profile(rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE}), repeated),))
    _contract_failure(manifest, profile, FORMATION_ISSUE_DUPLICATE, owner=_INHERITANCE)


def test_a_metadata_compiler_failure_is_a_contract_failure() -> None:
    profile = _Profile(metadata_compiler=_MetadataCompiler(raises=True))
    failure = _contract_failure(
        BUILTIN_MANIFEST, profile, FORMATION_COMPILER_FAILED, owner=METAMODEL_MODULE
    )
    assert isinstance(failure.cause, RuntimeError)


def test_a_model_compiler_failure_publishes_nothing() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(
                _TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_INHERITANCE_FACET})
            ),
        )
    )
    first = _Compiler(_INHERITANCE, _INHERITANCE_FACET)
    profile = _Profile(
        model_compilers=(
            first,
            _FailingCompiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_INHERITANCE_FACET})),
        )
    )
    failure = _contract_failure(manifest, profile, FORMATION_COMPILER_FAILED, owner=_TEMPORAL)
    assert first.calls == [_INHERITANCE]
    assert isinstance(failure.cause, RuntimeError)


def test_no_rule_set_or_compiler_runs_when_resolution_rejects() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _rule_set_row(_INHERITANCE, _CYCLE),
            _compiler_row(_TEMPORAL, _TEMPORAL_FACET),
        )
    )
    rule_set = _RuleSet(_INHERITANCE, frozenset({_CYCLE}))
    compiler = _Compiler(_TEMPORAL, _TEMPORAL_FACET)
    profile = _Profile(rule_sets=(rule_set,), model_compilers=(compiler,))
    with pytest.raises(MetamodelValidationError):
        form(source(*_invalid_model()), manifest, profile)
    assert rule_set.calls == []
    assert compiler.calls == []


def test_no_compiler_runs_when_a_rule_set_rejects() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _rule_set_row(_INHERITANCE, _CYCLE),
            _compiler_row(_TEMPORAL, _TEMPORAL_FACET),
        )
    )
    compiler = _Compiler(_TEMPORAL, _TEMPORAL_FACET)
    profile = _Profile(
        rule_sets=(_RuleSet(_INHERITANCE, frozenset({_CYCLE}), (_issue(_CYCLE),)),),
        model_compilers=(compiler,),
    )
    with pytest.raises(MetamodelValidationError) as raised:
        form(source(*_valid_model()), manifest, profile)
    assert [issue.code for issue in raised.value.issues] == [_CYCLE]
    assert compiler.calls == []


# --------------------------------------------------------------------------
# Compilation order and atomic facet installation.
# --------------------------------------------------------------------------


def _facet_manifest() -> FormationManifest:
    return FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(_RELATIONSHIP, _RELATIONSHIP_FACET),
            _compiler_row(
                _TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_INHERITANCE_FACET})
            ),
            _compiler_row(
                _OPT_LOCK,
                _OPT_LOCK_FACET,
                required_facets=frozenset({_INHERITANCE_FACET, _TEMPORAL_FACET}),
            ),
        )
    )


def test_model_compilers_run_in_topological_order_with_ascending_owner_tiebreak() -> None:
    calls: list[ModuleIdentity] = []
    handed: dict[ModuleIdentity, tuple[str, ...]] = {}
    compilers = (
        _Compiler(
            _OPT_LOCK,
            _OPT_LOCK_FACET,
            frozenset({_INHERITANCE_FACET, _TEMPORAL_FACET}),
            calls,
            handed,
        ),
        _Compiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_INHERITANCE_FACET}), calls, handed),
        _Compiler(_RELATIONSHIP, _RELATIONSHIP_FACET, frozenset(), calls, handed),
        _Compiler(_INHERITANCE, _INHERITANCE_FACET, frozenset(), calls, handed),
    )
    model = form(source(*_valid_model()), _facet_manifest(), _Profile(model_compilers=compilers))
    assert calls == [_INHERITANCE, _RELATIONSHIP, _TEMPORAL, _OPT_LOCK]
    assert handed[_INHERITANCE] == ()
    assert handed[_TEMPORAL] == (_INHERITANCE,)
    assert handed[_OPT_LOCK] == (_INHERITANCE, _TEMPORAL)
    assert model.facet(_OPT_LOCK_FACET) == f"facet of {_OPT_LOCK}"
    assert model.facet(_RELATIONSHIP_FACET) == f"facet of {_RELATIONSHIP}"


# --------------------------------------------------------------------------
# Determinism under permutation.
# --------------------------------------------------------------------------


def test_permuting_frontend_order_does_not_change_the_issue_sequence() -> None:
    generator = random.Random(20260723)
    reports: set[tuple[str, ...]] = set()
    for _ in range(8):
        declarations = list(_invalid_model())
        generator.shuffle(declarations)
        with pytest.raises(MetamodelValidationError) as raised:
            form_metamodel(source(*declarations))
        reports.add(tuple(f"{issue.code}@{issue.location}" for issue in raised.value.issues))
    assert len(reports) == 1


def test_permuting_rule_emission_and_profile_order_does_not_change_the_issue_sequence() -> None:
    manifest = FormationManifest(
        (
            _resolver_row(),
            _rule_set_row(_INHERITANCE, _CYCLE, _SHADOWING),
            _rule_set_row(_RELATIONSHIP, "relationship-reverse-cycle"),
        )
    )
    inheritance_issues = [
        _issue(_CYCLE, _ORDER),
        _issue(_SHADOWING, _ITEM),
        _issue(_CYCLE, _ITEM),
    ]
    relationship_issues = [_issue("relationship-reverse-cycle", _ORDER)]
    generator = random.Random(20260723)
    reports: set[tuple[str, ...]] = set()
    for _ in range(8):
        generator.shuffle(inheritance_issues)
        rule_sets: list[ModelRuleSet] = [
            _RuleSet(_INHERITANCE, frozenset({_CYCLE, _SHADOWING}), tuple(inheritance_issues)),
            _RuleSet(
                _RELATIONSHIP,
                frozenset({"relationship-reverse-cycle"}),
                tuple(relationship_issues),
            ),
        ]
        generator.shuffle(rule_sets)
        with pytest.raises(MetamodelValidationError) as raised:
            form(source(*_valid_model()), manifest, _Profile(rule_sets=tuple(rule_sets)))
        reports.add(tuple(f"{issue.code}@{issue.location}" for issue in raised.value.issues))
    assert len(reports) == 1


def test_rule_sets_run_in_manifest_order_regardless_of_profile_order() -> None:
    calls: list[ModuleIdentity] = []
    manifest = FormationManifest(
        (
            _resolver_row(),
            _rule_set_row(_INHERITANCE, _CYCLE),
            _rule_set_row(_RELATIONSHIP, "relationship-reverse-cycle"),
        )
    )
    profile = _Profile(
        rule_sets=(
            _RuleSet(_RELATIONSHIP, frozenset({"relationship-reverse-cycle"}), calls=calls),
            _RuleSet(_INHERITANCE, frozenset({_CYCLE}), calls=calls),
        )
    )
    form(source(*_valid_model()), manifest, profile)
    assert calls == [_INHERITANCE, _RELATIONSHIP]
