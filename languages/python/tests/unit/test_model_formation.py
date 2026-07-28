"""m-model-formation: the manifest, the contributor contracts, and the runner."""

from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, TypeGuard, cast

import pytest
from _metamodel_support import Declaration, attribute, identity, key, source

from parallax.conformance import case_format
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
    Resolved,
    UnresolvedEntityDeclaration,
    UnresolvedMetamodel,
    resolve,
)
from parallax.core.metamodel import _resolve as resolver
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
    CompilerRequirement,
    FormationContractError,
    FormationManifest,
    FormationManifestEntry,
    MetadataCompiler,
    MetamodelValidationError,
    ModelCompiler,
    ModelCompilerRequirement,
    ModelRuleSet,
    ModuleIdentity,
    RequiredRuleSet,
    form,
)
from parallax.core.model_formation import _runner as runner

pytestmark = pytest.mark.unit

_ORDER = identity("Order")
_ITEM = identity("Item")

_INHERITANCE: Final[ModuleIdentity] = "m-inheritance"
_STORAGE_LAYOUT: Final[ModuleIdentity] = "m-storage-layout"
_RELATIONSHIP: Final[ModuleIdentity] = "m-relationship"
_TEMPORAL: Final[ModuleIdentity] = "m-temporal-read"
_OPT_LOCK: Final[ModuleIdentity] = "m-opt-lock"


def _is_text(value: object) -> TypeGuard[str]:
    """The stand-in facet type check every double's key carries."""
    return isinstance(value, str)


def _accepts_everything(value: object) -> TypeGuard[str]:
    """An acceptance check that abdicates: no value it is asked about is refused."""
    return True


def _rejects_everything(value: object) -> TypeGuard[str]:
    """An acceptance check that refuses every value, its owner's own facet included."""
    return False


@dataclass(slots=True)
class _CustomMutableFacet:
    """A mutable facet outside the builtin container types the runner refuses outright."""

    entries: list[str]


_INHERITANCE_FACET: Final[FacetKey[str]] = FacetKey(_INHERITANCE, _is_text)
_RELATIONSHIP_FACET: Final[FacetKey[str]] = FacetKey(_RELATIONSHIP, _is_text)
_TEMPORAL_FACET: Final[FacetKey[str]] = FacetKey(_TEMPORAL, _is_text)
_OPT_LOCK_FACET: Final[FacetKey[str]] = FacetKey(_OPT_LOCK, _is_text)

_PERMISSIVE_INHERITANCE_FACET: Final[FacetKey[str]] = FacetKey(_INHERITANCE, _accepts_everything)
"""A key equal to ``_INHERITANCE_FACET`` whose acceptance check refuses nothing.

Key identity is the owning module alone, so this compares equal to the key the
manifest declares for ``m-inheritance`` and passes every drift check that
compares the two. It exists so a compiler can offer the runner a weaker
acceptance check than the one that module really published."""

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
class _MutableFacetCompiler:
    """A Model Compiler installing a facet the caller could still mutate."""

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        return cast(str, ["a facet nothing may rely on"])


@dataclass(frozen=True, slots=True)
class _WrongTypeFacetCompiler:
    """A Model Compiler installing a value of another type than its key promises."""

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        return cast(str, 42)


@dataclass(frozen=True, slots=True)
class _SubstitutedKeyCompiler:
    """A Model Compiler offering an equal key of its own alongside any facet value.

    Composed with a permissive key and a value the owning module's real key
    rejects, it is the whole substitution attempt: whether the value is
    installed depends only on which of the two equal keys the runner asks.
    """

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    returns: object
    requires: frozenset[FacetKey[Any]] = frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        return cast(str, self.returns)


def _key_log() -> list[FacetKey[Any]]:
    """A fresh per-compiler record of the prerequisite keys it was handed."""
    return []


@dataclass(frozen=True, slots=True)
class _KeyInspectingCompiler:
    """A Model Compiler keeping the prerequisite key objects it was handed.

    A compiler can read the acceptance check of every key in its required-facet
    mapping, so which key objects those are is observable contract surface.
    """

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()
    inspected: list[FacetKey[Any]] = field(default_factory=_key_log)

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        self.inspected.extend(required_facets)
        return f"facet of {self.owner}"


@dataclass(frozen=True, slots=True)
class _FacetMutatingCompiler:
    """A Model Compiler that tries to install a key of its own into what it was handed."""

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    requires: frozenset[FacetKey[Any]] = frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        cast(dict[FacetKey[Any], object], required_facets)[self.facet_key] = "smuggled"
        return f"facet of {self.owner}"


@dataclass(frozen=True, slots=True)
class _DriftingCompiler:
    """A Model Compiler whose requirements change after drift checking read them.

    ``requires`` answers with the manifest's declared edge set once — long enough
    to pass drift checking — and with an unsatisfiable one thereafter, which is
    the only way the drift-checked ordering proof can fail.
    """

    owner: ModuleIdentity
    facet_key: FacetKey[str]
    reads: list[int] = field(default_factory=lambda: [0])

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        self.reads[0] += 1
        return frozenset() if self.reads[0] == 1 else frozenset({FacetKey("m-absent", _is_text)})

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> str:
        return f"facet of {self.owner}"


@dataclass(frozen=True, slots=True)
class _MetadataCompiler:
    """A Metadata Compiler double with a settable owner and failure mode."""

    owner: ModuleIdentity = METAMODEL_MODULE
    raises: bool = False

    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata:
        if self.raises:
            raise RuntimeError("the Metadata Compiler reached an impossible state")
        return METADATA_COMPILER.compile(candidate)


@dataclass(frozen=True, slots=True)
class _ForeignMetadataCompiler:
    """A Metadata Compiler returning something that is not Compiled Metadata."""

    owner: ModuleIdentity = METAMODEL_MODULE

    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata:
        return cast(CompiledMetadata, object())


@dataclass(frozen=True, slots=True)
class _EmptyMetadata:
    """The whole Compiled Metadata surface over no Entity at all."""

    entities: tuple[Any, ...] = ()

    def entity(self, identity: EntityIdentity) -> None:
        return None


def _genuine_empty_metadata() -> CompiledMetadata:
    """Compiled Metadata this module produced that nonetheless holds no Entity."""
    result = resolve(source())
    assert isinstance(result, Resolved)
    return METADATA_COMPILER.compile(result.candidate)


@dataclass(frozen=True, slots=True)
class _EntitylessMetadataCompiler:
    """A Metadata Compiler answering an accepted candidate with an Entity-less graph.

    ``genuine`` selects which way the result is outside the contract: a graph
    this module really compiled but from nothing, or a foreign object presenting
    the same surface.
    """

    genuine: bool
    owner: ModuleIdentity = METAMODEL_MODULE

    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata:
        return _genuine_empty_metadata() if self.genuine else _EmptyMetadata()


@dataclass(frozen=True, slots=True)
class _UnreadableProfile:
    """A profile whose own contract members raise when the runner reads them."""

    rule_sets: tuple[ModelRuleSet, ...] = ()
    model_compilers: tuple[ModelCompiler[Any], ...] = ()

    @property
    def metadata_compiler(self) -> MetadataCompiler:
        raise RuntimeError("the composition root could not answer for its compiler")


def _resolver_row(
    *, issue_codes: frozenset[IssueCode] = RESOLVER_ISSUE_CODES
) -> FormationManifestEntry:
    return FormationManifestEntry(
        owner=METAMODEL_MODULE,
        rule_set=FIXED_RESOLVER,
        issue_codes=issue_codes,
        compiler=METADATA_COMPILER_REQUIRED,
    )


_RESOLVER_ONLY: Final[FormationManifest] = FormationManifest((_resolver_row(),))
"""A manifest of the fixed resolver alone, for the seams no contributor takes part in."""


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
    entry = BUILTIN_MANIFEST.entries[0]
    assert entry.owner == METAMODEL_MODULE
    assert entry.rule_set is FIXED_RESOLVER
    assert entry.issue_codes == RESOLVER_ISSUE_CODES
    assert entry.compiler is METADATA_COMPILER_REQUIRED
    assert BUILTIN_PROFILE.metadata_compiler is METADATA_COMPILER


def test_the_builtin_profile_supplies_exactly_the_contributors_the_manifest_declares() -> None:
    """The composition root's own drift proof, independent of which rows exist yet."""
    required = [
        entry.owner
        for entry in BUILTIN_MANIFEST.entries
        if isinstance(entry.rule_set, RequiredRuleSet)
    ]
    compiling = [
        entry.owner
        for entry in BUILTIN_MANIFEST.entries
        if isinstance(entry.compiler, ModelCompilerRequirement)
    ]
    assert sorted(rule_set.owner for rule_set in BUILTIN_PROFILE.rule_sets) == sorted(required)
    assert sorted(compiler.owner for compiler in BUILTIN_PROFILE.model_compilers) == sorted(
        compiling
    )


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
# The built-in manifest against the specification's authoritative manifest.
# --------------------------------------------------------------------------

_MANIFEST_SPEC: Final[Path] = (
    case_format.find_repo_root() / "core" / "spec" / "m-model-formation.md"
)
_BACKTICKED: Final[re.Pattern[str]] = re.compile(r"`([^`]+)`")
_FACET_KEY: Final[re.Pattern[str]] = re.compile(r"FacetKey\((m-[a-z0-9-]+)\)")


@dataclass(frozen=True, slots=True)
class _SpecRow:
    """One row of the specification's authoritative formation manifest table."""

    owner: ModuleIdentity
    rule_set: str
    issue_codes: frozenset[IssueCode]
    compiler: str
    required_modules: frozenset[ModuleIdentity]
    required_facets: frozenset[ModuleIdentity]


def _spec_rows() -> list[_SpecRow]:
    """The authoritative manifest table, read from the owning specification.

    The table is the normative content of the Formation Manifest, so reading it
    here makes a composition root that drifts from it fail this test.
    """
    text = _MANIFEST_SPEC.read_text(encoding="utf-8")
    section = text.split("## Authoritative formation manifest", 1)[1].split("\n## ", 1)[0]
    rows: list[_SpecRow] = []
    for line in section.splitlines():
        if not line.startswith("| `m-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        owner, rule_set, codes, compiler, modules, facets = cells
        rows.append(
            _SpecRow(
                owner=_BACKTICKED.findall(owner)[0],
                rule_set=rule_set,
                issue_codes=frozenset(_BACKTICKED.findall(codes)),
                compiler=compiler,
                required_modules=frozenset(_BACKTICKED.findall(modules)),
                required_facets=frozenset(_FACET_KEY.findall(facets)),
            )
        )
    return rows


def _rule_set_requirement(row: _SpecRow) -> object:
    if row.rule_set.startswith("fixed resolver"):
        return FIXED_RESOLVER
    if row.rule_set == "required":
        return REQUIRED_RULE_SET
    return None


def _compiler_requirement(row: _SpecRow) -> CompilerRequirement | None:
    if row.compiler.startswith("mandatory Metadata Compiler"):
        return METADATA_COMPILER_REQUIRED
    facets = _FACET_KEY.findall(row.compiler)
    if not facets:
        return None
    return ModelCompilerRequirement(FacetKey(facets[0], _is_text))


def test_the_specification_table_is_readable_and_complete() -> None:
    rows = _spec_rows()
    assert [row.owner for row in rows] == [
        METAMODEL_MODULE,
        "m-pk-gen",
        _INHERITANCE,
        _STORAGE_LAYOUT,
        "m-value-object",
        _RELATIONSHIP,
        _TEMPORAL,
        _OPT_LOCK,
    ]


def test_the_builtin_manifest_declares_the_specifications_rows_in_its_order() -> None:
    assert [entry.owner for entry in BUILTIN_MANIFEST.entries] == [
        row.owner for row in _spec_rows()
    ]


@pytest.mark.parametrize("row", _spec_rows(), ids=lambda row: cast("_SpecRow", row).owner)
def test_every_builtin_row_matches_its_specification_row(row: _SpecRow) -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == row.owner)
    assert entry.rule_set == _rule_set_requirement(row)
    assert entry.issue_codes == row.issue_codes
    assert entry.compiler == _compiler_requirement(row)
    assert entry.required_modules == row.required_modules
    assert {key.owner for key in entry.required_facets} == row.required_facets


def test_every_builtin_issue_code_carries_its_owners_catalog_stem() -> None:
    offenders = [
        (entry.owner, code)
        for entry in BUILTIN_MANIFEST.entries
        for code in sorted(entry.issue_codes)
        if not code.startswith(f"{entry.owner.removeprefix('m-')}-")
    ]
    assert offenders == []


def test_no_builtin_issue_code_is_claimed_by_two_owners() -> None:
    claimed: dict[IssueCode, ModuleIdentity] = {}
    collisions: list[tuple[IssueCode, ModuleIdentity, ModuleIdentity]] = []
    for entry in BUILTIN_MANIFEST.entries:
        for code in sorted(entry.issue_codes):
            owner = claimed.setdefault(code, entry.owner)
            if owner != entry.owner:
                collisions.append((code, owner, entry.owner))
    assert collisions == []


def test_the_builtin_facet_keys_are_owned_by_the_modules_that_declare_them() -> None:
    for entry in BUILTIN_MANIFEST.entries:
        if isinstance(entry.compiler, ModelCompilerRequirement):
            assert entry.compiler.facet_key.owner == entry.owner


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


def test_a_profile_that_cannot_answer_for_its_own_contract_is_drift() -> None:
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_model()), BUILTIN_MANIFEST, _UnreadableProfile())
    assert raised.value.code == FORMATION_PROFILE_DRIFT
    assert isinstance(raised.value.cause, RuntimeError)
    assert raised.value.__cause__ is raised.value.cause


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
    profile = _Profile(
        model_compilers=(_Compiler(_INHERITANCE, FacetKey(_INHERITANCE + "-alt", _is_text)),)
    )
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
    borrowed: FacetKey[str] = FacetKey(_RELATIONSHIP, _is_text)
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
    return Rejected([_issue(PRIMARY_KEY_MISSING)])  # pyright: ignore[reportArgumentType] - deliberate mutable-list payload probes Rejected's tuple contract


def _resolves_to_a_foreign_candidate(unresolved: UnresolvedMetamodel) -> object:
    return Resolved(cast(CandidateMetamodel, object()))


def _resolves_to_an_entityless_candidate(unresolved: UnresolvedMetamodel) -> object:
    return Resolved(cast(CandidateMetamodel, _EntitylessCandidate()))


def _resolves_to_foreign_declarations(unresolved: UnresolvedMetamodel) -> object:
    return Resolved(cast(CandidateMetamodel, _ForeignDeclarationCandidate()))


@dataclass(frozen=True, slots=True)
class _EntitylessCandidate:
    """A Candidate Metamodel shape carrying no Entity at all.

    Formation input is nonempty, so an empty candidate is a resolver defect
    rather than a model with nothing in it.
    """

    entities: tuple[Any, ...] = ()

    def entity(self, identity: EntityIdentity) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _ForeignDeclarationCandidate:
    """A Candidate Metamodel shape whose Entity sequence holds a foreign value.

    The outer shape answers every structural question a duck-typed check can
    ask, so only the seam that knows where a candidate comes from can refuse it.
    """

    entities: tuple[Any, ...] = (object(),)

    def entity(self, identity: EntityIdentity) -> None:
        return None


@pytest.mark.parametrize(
    "broken",
    [
        _returns_a_foreign_value,
        _returns_an_empty_rejection,
        _returns_a_mutable_rejection,
        _resolves_to_a_foreign_candidate,
        _resolves_to_an_entityless_candidate,
        _resolves_to_foreign_declarations,
    ],
    ids=[
        "foreign-value",
        "empty-rejection",
        "mutable-rejection",
        "foreign-candidate",
        "entityless-candidate",
        "foreign-declarations",
    ],
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
        form(source(*_invalid_model()), manifest, _Profile())
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


def _emits_one_issue_twice(declaration: object) -> list[MetamodelIssue]:
    """A resolver check that reports one defect twice from a single declaration."""
    return [_issue(PRIMARY_KEY_MISSING), _issue(PRIMARY_KEY_MISSING)]


def test_a_resolver_that_emits_one_issue_twice_is_a_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fixed resolver is held to distinct issue identities like every other emitter.

    Resolution collapses only the defects a legal model makes reachable along
    several paths, and it does so where each is discovered. Its aggregate is not
    exempt: a check that reports one defect twice from one declaration is a
    contract failure the runner reports, not something resolution absorbs.
    """
    monkeypatch.setattr(resolver, "_primary_key_issues", _emits_one_issue_twice)
    with pytest.raises(FormationContractError) as raised:
        form(source(*_valid_model()), BUILTIN_MANIFEST, BUILTIN_PROFILE)
    assert raised.value.code == FORMATION_ISSUE_DUPLICATE
    assert raised.value.owner == METAMODEL_MODULE


def test_a_metadata_compiler_failure_is_a_contract_failure() -> None:
    profile = _Profile(metadata_compiler=_MetadataCompiler(raises=True))
    failure = _contract_failure(
        _RESOLVER_ONLY, profile, FORMATION_COMPILER_FAILED, owner=METAMODEL_MODULE
    )
    assert isinstance(failure.cause, RuntimeError)


def test_a_metadata_compiler_returning_a_foreign_value_is_a_contract_failure() -> None:
    profile = _Profile(metadata_compiler=_ForeignMetadataCompiler())
    failure = _contract_failure(
        _RESOLVER_ONLY, profile, FORMATION_COMPILER_FAILED, owner=METAMODEL_MODULE
    )
    assert failure.cause is None


@pytest.mark.parametrize("genuine", [True, False], ids=["genuine", "foreign"])
def test_a_metadata_compiler_returning_an_entityless_graph_is_a_contract_failure(
    genuine: bool,
) -> None:
    """An accepted candidate is nonempty, so metadata over no Entity is impossible.

    Each returned value answers the whole Compiled Metadata surface, so either
    would otherwise be published as an accepted Metamodel holding no Entity.
    """
    profile = _Profile(metadata_compiler=_EntitylessMetadataCompiler(genuine))
    failure = _contract_failure(
        _RESOLVER_ONLY, profile, FORMATION_COMPILER_FAILED, owner=METAMODEL_MODULE
    )
    assert failure.cause is None


def test_an_empty_frontend_source_is_refused_at_the_resolver_seam() -> None:
    """Formation begins from a nonempty source, and every frontend rejects an
    empty one before this seam; resolving one anyway yields no candidate at all,
    which the seam reports rather than compiling a model with nothing in it."""
    with pytest.raises(FormationContractError) as raised:
        form(source(), BUILTIN_MANIFEST, BUILTIN_PROFILE)
    assert raised.value.code == FORMATION_RESOLVER_RESULT_INVALID
    assert raised.value.owner == METAMODEL_MODULE


def test_a_model_compiler_returning_a_mutable_collection_is_a_contract_failure() -> None:
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    profile = _Profile(model_compilers=(_MutableFacetCompiler(_INHERITANCE, _INHERITANCE_FACET),))
    failure = _contract_failure(manifest, profile, FORMATION_COMPILER_FAILED, owner=_INHERITANCE)
    assert failure.cause is None


def test_a_model_compiler_returning_another_type_than_its_key_promises_fails() -> None:
    """A facet key's type parameter is erased, so its owner's own check decides.

    The returned value is immutable and perfectly ordinary; only the facet
    owner knows it is not the facet the key stands for.
    """
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    profile = _Profile(model_compilers=(_WrongTypeFacetCompiler(_INHERITANCE, _INHERITANCE_FACET),))
    failure = _contract_failure(manifest, profile, FORMATION_COMPILER_FAILED, owner=_INHERITANCE)
    assert failure.cause is None


@pytest.mark.parametrize(
    "returns",
    [42, _CustomMutableFacet(["a facet nothing may rely on"])],
    ids=["wrong-type", "custom-mutable"],
)
def test_a_model_compiler_cannot_substitute_its_own_acceptance_check(returns: object) -> None:
    """A facet key is equal to any key naming its owner, however that key answers.

    A compiler therefore passes every drift check while supplying a key whose
    acceptance check refuses nothing, and only the manifest's key carries the
    check its owner really published. The refused values are the two the weaker
    check hides: one of another type entirely, and one the caller could still
    mutate but that is none of the builtin containers refused outright.
    """
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    profile = _Profile(
        model_compilers=(
            _SubstitutedKeyCompiler(_INHERITANCE, _PERMISSIVE_INHERITANCE_FACET, returns),
        )
    )
    failure = _contract_failure(manifest, profile, FORMATION_COMPILER_FAILED, owner=_INHERITANCE)
    assert failure.cause is None


def test_a_model_compiler_cannot_refuse_the_facet_its_own_module_accepts() -> None:
    """The manifest's acceptance check is the whole check, not the stricter of two.

    Supplying a key that refuses everything is a compiler passing a verdict on
    its own result; what it returned is the facet the module's declared key
    accepts, so formation installs it and the model serves it.
    """
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    refusing: FacetKey[str] = FacetKey(_INHERITANCE, _rejects_everything)
    profile = _Profile(model_compilers=(_Compiler(_INHERITANCE, refusing),))
    model = form(source(*_valid_model()), manifest, profile)
    assert model.facet(_INHERITANCE_FACET) == f"facet of {_INHERITANCE}"


def test_a_model_compiler_is_handed_the_manifests_key_for_every_facet_it_requires() -> None:
    """Prerequisite keys reach a compiler as the manifest declares them.

    A compiler names what it requires with keys of its own, and equality cannot
    tell those apart from the ones the required modules published. Handing back
    the compiler's own keys would let one module present another module's key
    with an acceptance check that module never wrote.
    """
    manifest = FormationManifest(
        (
            _resolver_row(),
            _compiler_row(_INHERITANCE, _INHERITANCE_FACET),
            _compiler_row(
                _TEMPORAL, _TEMPORAL_FACET, required_facets=frozenset({_INHERITANCE_FACET})
            ),
        )
    )
    inspecting = _KeyInspectingCompiler(
        _TEMPORAL, _TEMPORAL_FACET, frozenset({_PERMISSIVE_INHERITANCE_FACET})
    )
    profile = _Profile(model_compilers=(_Compiler(_INHERITANCE, _INHERITANCE_FACET), inspecting))
    form(source(*_valid_model()), manifest, profile)
    assert [handed.accepts for handed in inspecting.inspected] == [_is_text]


def test_a_model_compiler_cannot_mutate_the_facets_it_was_handed() -> None:
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
            _FacetMutatingCompiler(_TEMPORAL, _TEMPORAL_FACET, frozenset({_INHERITANCE_FACET})),
        )
    )
    failure = _contract_failure(manifest, profile, FORMATION_COMPILER_FAILED, owner=_TEMPORAL)
    assert isinstance(failure.cause, TypeError)


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


def test_a_profile_whose_requirements_move_after_drift_checking_is_drift() -> None:
    manifest = FormationManifest((_resolver_row(), _compiler_row(_INHERITANCE, _INHERITANCE_FACET)))
    profile = _Profile(model_compilers=(_DriftingCompiler(_INHERITANCE, _INHERITANCE_FACET),))
    failure = _contract_failure(manifest, profile, FORMATION_PROFILE_DRIFT, owner=_INHERITANCE)
    assert "no Model Compiler is eligible" in str(failure)


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
