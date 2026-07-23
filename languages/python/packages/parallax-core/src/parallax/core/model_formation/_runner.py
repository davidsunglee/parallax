"""The deterministic Model Formation runner (m-model-formation).

One entry point drives the whole gated progression: drift-check the profile
against the manifest, resolve once, validate, compile, publish. Every ordering
decision is taken from the manifest rather than from the profile or from
emission order, so permuting frontend input, rule emission, or profile order
cannot change the reported issue sequence or the compiler schedule. Nothing is
published until every step succeeds — there is no partial Metamodel and no
partial facet set.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from types import MappingProxyType
from typing import Any, Final, TypeGuard

from parallax.core.metamodel import (
    METAMODEL_MODULE,
    CandidateMetamodel,
    CompiledMetadata,
    FacetKey,
    IssueCode,
    Metamodel,
    MetamodelIssue,
    Rejected,
    Resolved,
    UnresolvedMetamodel,
    accept_metamodel,
    is_candidate_metamodel,
    is_compiled_metadata,
    resolve,
    sort_issues,
)
from parallax.core.model_formation._contributors import (
    FormationProfile,
    ModelCompiler,
    ModelRuleSet,
)
from parallax.core.model_formation._errors import (
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
    FormationContractCode,
    FormationContractError,
    MetamodelValidationError,
)
from parallax.core.model_formation._manifest import (
    FixedResolver,
    FormationManifest,
    FormationManifestEntry,
    MetadataCompilerRequirement,
    ModelCompilerRequirement,
    ModuleIdentity,
    RequiredRuleSet,
)

__all__ = ["form"]

_KEBAB_CASE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def form(
    unresolved: UnresolvedMetamodel,
    manifest: FormationManifest,
    profile: FormationProfile,
) -> Metamodel:
    """Form ``unresolved`` into an accepted Metamodel under ``manifest``/``profile``.

    Raises :class:`MetamodelValidationError` when the model is invalid, carrying
    every foundational or semantic issue in canonical order, and
    :class:`FormationContractError` when the profile, manifest, or a contributor
    breaks its own contract. The two never substitute for each other.
    """
    _check_profile_drift(manifest, profile)
    candidate = _resolve_once(manifest, unresolved)
    issues = _run_rule_sets(manifest, profile, candidate)
    if issues:
        raise MetamodelValidationError(issues)
    metadata = _compile_metadata(profile, candidate)
    return accept_metamodel(metadata, _compile_facets(manifest, profile, metadata))


def _drift(message: str, owner: ModuleIdentity | None = None) -> FormationContractError:
    return FormationContractError(FORMATION_PROFILE_DRIFT, message, owner=owner)


@contextmanager
def _contract_reads(
    code: FormationContractCode, message: str, owner: ModuleIdentity | None = None
) -> Generator[None]:
    """Classify anything raised while reading a contributor's own contract.

    Every ``owner``, ``issue_codes``, ``facet_key``, and ``requires`` member is
    arbitrary contributor code, so reading one can raise. Such a failure is a
    statement about the contributor, never about the model: it leaves the block
    as a :class:`FormationContractError` under ``code`` with the original
    exception preserved. A contract error the block raised deliberately keeps
    its own more specific code.
    """
    try:
        yield
    except FormationContractError:
        raise
    except Exception as error:
        raise FormationContractError(code, message, owner=owner, cause=error) from error


def _issue_code_prefix(owner: ModuleIdentity) -> str:
    """The mandatory Issue Code prefix for ``owner``: its catalog stem plus a hyphen."""
    return f"{owner.removeprefix('m-')}-"


def _well_formed_code(code: IssueCode, owner: ModuleIdentity) -> bool:
    """Whether ``code`` is nonempty kebab-case carrying ``owner``'s catalog stem."""
    return _KEBAB_CASE.fullmatch(code) is not None and code.startswith(_issue_code_prefix(owner))


def _first_offender(required: Sequence[ModuleIdentity], supplied: Sequence[ModuleIdentity]) -> str:
    """The lowest owner the two multisets disagree about; the caller proved they do."""
    expected = Counter(required)
    actual = Counter(supplied)
    return min((expected - actual) + (actual - expected))


def _check_profile_drift(manifest: FormationManifest, profile: FormationProfile) -> None:
    """Run the nine drift checks in their fixed order, failing on the first.

    The order is what makes a drift diagnostic deterministic: a profile with
    several defects always reports the earliest one. Reading the profile is
    itself part of the check, so a contributor whose contract members raise is
    reported as drift rather than escaping as its own exception.
    """
    entries = manifest.entries
    with _contract_reads(
        FORMATION_PROFILE_DRIFT, "reading the Formation Profile's contract raised"
    ):
        _check_metadata_compiler(entries, profile)
        rule_sets = _check_rule_set_presence(entries, profile)
        _check_declared_issue_codes(entries, rule_sets)
        _check_issue_code_grammar(entries)
        _check_single_code_ownership(entries)
        compilers = _check_model_compiler_presence(entries, profile)
        _check_compiler_keys(profile)
        _check_facet_dependencies(entries)
        _check_declared_edges(entries, compilers)


def _check_metadata_compiler(
    entries: Sequence[FormationManifestEntry], profile: FormationProfile
) -> None:
    owners = [
        entry.owner for entry in entries if isinstance(entry.compiler, MetadataCompilerRequirement)
    ]
    if owners != [METAMODEL_MODULE]:
        raise _drift(
            f"the manifest demands Metadata Compilers from {owners}, not exactly one "
            f"owned by {METAMODEL_MODULE!r}"
        )
    supplied = profile.metadata_compiler.owner
    if supplied != METAMODEL_MODULE:
        raise _drift(f"the supplied Metadata Compiler declares owner {supplied!r}", owner=supplied)


def _check_rule_set_presence(
    entries: Sequence[FormationManifestEntry], profile: FormationProfile
) -> Mapping[ModuleIdentity, ModelRuleSet]:
    resolvers = [entry.owner for entry in entries if isinstance(entry.rule_set, FixedResolver)]
    if resolvers != [METAMODEL_MODULE]:
        raise _drift(
            f"the manifest names fixed-resolver rows {resolvers}, not exactly one "
            f"owned by {METAMODEL_MODULE!r}"
        )
    required = sorted(
        entry.owner for entry in entries if isinstance(entry.rule_set, RequiredRuleSet)
    )
    supplied = sorted(rule_set.owner for rule_set in profile.rule_sets)
    if supplied != required:
        raise _drift(
            f"the profile supplies Rule Sets from {supplied}; the manifest requires {required}",
            owner=_first_offender(required, supplied),
        )
    return {rule_set.owner: rule_set for rule_set in profile.rule_sets}


def _check_declared_issue_codes(
    entries: Sequence[FormationManifestEntry], rule_sets: Mapping[ModuleIdentity, ModelRuleSet]
) -> None:
    for entry in entries:
        if not isinstance(entry.rule_set, RequiredRuleSet):
            continue
        declared = frozenset(rule_sets[entry.owner].issue_codes)
        if declared != entry.issue_codes:
            raise _drift(
                f"the Rule Set declares {sorted(declared)}; the manifest declares "
                f"{sorted(entry.issue_codes)}",
                owner=entry.owner,
            )


def _check_issue_code_grammar(entries: Sequence[FormationManifestEntry]) -> None:
    for entry in entries:
        for code in sorted(entry.issue_codes):
            if not _well_formed_code(code, entry.owner):
                raise FormationContractError(
                    FORMATION_ISSUE_CODE_INVALID,
                    f"Issue Code {code!r} is not kebab-case prefixed with "
                    f"{_issue_code_prefix(entry.owner)!r}",
                    owner=entry.owner,
                )


def _check_single_code_ownership(entries: Sequence[FormationManifestEntry]) -> None:
    owner_of: dict[IssueCode, ModuleIdentity] = {}
    for entry in entries:
        for code in sorted(entry.issue_codes):
            claimed = owner_of.setdefault(code, entry.owner)
            if claimed != entry.owner:
                raise _drift(
                    f"Issue Code {code!r} is also claimed by {claimed!r}", owner=entry.owner
                )


def _declared_facet_keys(
    entries: Sequence[FormationManifestEntry],
) -> Mapping[ModuleIdentity, FacetKey[Any]]:
    """Each compiling owner's facet key exactly as the manifest declares it.

    This is the only key the runner ever validates or installs a facet under. A
    key's identity is its owner alone, so a compiler-supplied key that satisfies
    every drift check may still carry an ``accepts`` its owner never wrote;
    resolving the key by owner here leaves the compiler no say in the check its
    own result is measured against.
    """
    return {
        entry.owner: entry.compiler.facet_key
        for entry in entries
        if isinstance(entry.compiler, ModelCompilerRequirement)
    }


def _check_model_compiler_presence(
    entries: Sequence[FormationManifestEntry], profile: FormationProfile
) -> Mapping[ModuleIdentity, ModelCompiler[Any]]:
    required = _declared_facet_keys(entries)
    supplied: dict[ModuleIdentity, ModelCompiler[Any]] = {}
    for compiler in profile.model_compilers:
        if compiler.owner not in required:
            raise _drift(
                "the profile supplies a Model Compiler the manifest does not require",
                owner=compiler.owner,
            )
        supplied.setdefault(compiler.owner, compiler)
    missing = sorted(set(required) - set(supplied))
    if missing:
        raise FormationContractError(
            FORMATION_FACET_MISSING,
            f"the profile supplies no Model Compiler for {missing}",
            owner=missing[0],
        )
    for owner, compiler in supplied.items():
        if compiler.facet_key != required[owner]:
            raise _drift(
                f"the Model Compiler installs {compiler.facet_key}; the manifest "
                f"declares {required[owner]}",
                owner=owner,
            )
    return supplied


def _check_compiler_keys(profile: FormationProfile) -> None:
    seen: set[FacetKey[Any]] = set()
    for compiler in profile.model_compilers:
        key = compiler.facet_key
        if key in seen:
            raise FormationContractError(
                FORMATION_FACET_DUPLICATE,
                f"{key} is installed more than once",
                owner=compiler.owner,
            )
        seen.add(key)
        if key.owner != compiler.owner:
            raise _drift(
                f"the Model Compiler installs {key}, which another module owns",
                owner=compiler.owner,
            )


def _check_facet_dependencies(entries: Sequence[FormationManifestEntry]) -> None:
    """Prove every required facet is compiled and the requirement graph is acyclic."""
    owner_of: dict[FacetKey[Any], ModuleIdentity] = {}
    requires: dict[FacetKey[Any], frozenset[FacetKey[Any]]] = {}
    for entry in entries:
        if isinstance(entry.compiler, ModelCompilerRequirement):
            owner_of[entry.compiler.facet_key] = entry.owner
            requires[entry.compiler.facet_key] = entry.required_facets
    for entry in entries:
        for key in sorted(entry.required_facets, key=lambda facet: facet.owner):
            if key not in requires:
                raise FormationContractError(
                    FORMATION_FACET_MISSING,
                    f"{entry.owner} requires {key}, which no manifest row compiles",
                    owner=key.owner,
                )
    installed: set[FacetKey[Any]] = set()
    pending = dict(requires)
    while pending:
        ready = [key for key, needed in pending.items() if needed <= installed]
        if not ready:
            raise _drift(
                "the declared facet dependency graph has a cycle",
                owner=min(owner_of[key] for key in pending),
            )
        for key in ready:
            del pending[key]
        installed.update(ready)


def _check_declared_edges(
    entries: Sequence[FormationManifestEntry],
    compilers: Mapping[ModuleIdentity, ModelCompiler[Any]],
) -> None:
    for entry in entries:
        for key in sorted(entry.required_facets, key=lambda facet: facet.owner):
            if key.owner not in entry.required_modules:
                raise _drift(
                    f"{entry.owner} requires {key} without declaring {key.owner!r} "
                    "among its required modules",
                    owner=entry.owner,
                )
        if not isinstance(entry.compiler, ModelCompilerRequirement):
            continue
        declared = frozenset(compilers[entry.owner].requires)
        if declared != entry.required_facets:
            raise _drift(
                f"the Model Compiler requires {sorted(declared, key=lambda facet: facet.owner)}; "
                f"the manifest declares "
                f"{sorted(entry.required_facets, key=lambda facet: facet.owner)}",
                owner=entry.owner,
            )


def _is_untyped_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    """Whether ``value`` is a tuple, narrowing its elements no further than ``object``."""
    return isinstance(value, tuple)


# The builtin containers whose whole purpose is in-place mutation. A facet is an
# immutable derived view, so returning one of these is a compiler defect. This is
# the floor no facet owner can lower; which immutable values are that owner's
# facet is its own key's decision.
_MUTABLE_FACET_TYPES: Final[tuple[type, ...]] = (list, dict, set, bytearray)


def _issue_sequence(returned: object) -> tuple[MetamodelIssue, ...] | None:
    """``returned`` as the immutable issue sequence a contributor must produce.

    ``None`` when it is a mutable collection or carries a non-issue element:
    immutability is part of the return type, not an implementation preference.
    """
    if not _is_untyped_tuple(returned):
        return None
    issues = tuple(element for element in returned if isinstance(element, MetamodelIssue))
    return issues if len(issues) == len(returned) else None


def _resolver_codes(manifest: FormationManifest) -> frozenset[IssueCode]:
    return next(
        entry.issue_codes for entry in manifest.entries if isinstance(entry.rule_set, FixedResolver)
    )


def _invoke_resolver(unresolved: UnresolvedMetamodel) -> object:
    """The fixed resolver's return value, invoked exactly once.

    The ``object`` result type is deliberate: the runner validates what the
    resolver returned rather than assuming it honored its own declared type, so
    a resolver defect surfaces as a contract failure instead of an attribute
    error somewhere downstream.
    """
    try:
        return resolve(unresolved)
    except Exception as error:
        raise FormationContractError(
            FORMATION_RESOLVER_FAILED,
            "the fixed resolver raised instead of returning a resolution result",
            owner=METAMODEL_MODULE,
            cause=error,
        ) from error


def _resolve_once(
    manifest: FormationManifest, unresolved: UnresolvedMetamodel
) -> CandidateMetamodel:
    """Resolve ``unresolved`` into the candidate every later step shares.

    A rejection ends formation here: no Rule Set and no compiler observes a model
    whose references did not resolve.
    """
    result = _invoke_resolver(unresolved)
    if isinstance(result, Resolved):
        candidate = result.candidate
        if not is_candidate_metamodel(candidate):
            raise FormationContractError(
                FORMATION_RESOLVER_RESULT_INVALID,
                "the fixed resolver resolved to a value that is not a Candidate Metamodel",
                owner=METAMODEL_MODULE,
            )
        return candidate
    issues = _issue_sequence(result.issues) if isinstance(result, Rejected) else None
    if not issues:
        raise FormationContractError(
            FORMATION_RESOLVER_RESULT_INVALID,
            "the fixed resolver returned neither a candidate nor a nonempty immutable "
            "issue sequence",
            owner=METAMODEL_MODULE,
        )
    _check_emitted(METAMODEL_MODULE, _resolver_codes(manifest), issues, set())
    raise MetamodelValidationError(sort_issues(issues))


def _check_emitted(
    owner: ModuleIdentity,
    declared: frozenset[IssueCode],
    issues: Sequence[MetamodelIssue],
    seen: set[MetamodelIssue],
) -> None:
    """Hold one emitter to its declared codes and to distinct issue identities."""
    for issue in issues:
        if not _well_formed_code(issue.code, owner):
            raise FormationContractError(
                FORMATION_ISSUE_CODE_INVALID,
                f"emitted Issue Code {issue.code!r} is not kebab-case prefixed with "
                f"{_issue_code_prefix(owner)!r}",
                owner=owner,
            )
        if issue.code not in declared:
            raise FormationContractError(
                FORMATION_ISSUE_UNDECLARED,
                f"emitted Issue Code {issue.code!r} is outside the declared set",
                owner=owner,
            )
        if issue in seen:
            raise FormationContractError(
                FORMATION_ISSUE_DUPLICATE,
                f"issue identity ({issue.code!r}, {issue.location}) was already emitted",
                owner=owner,
            )
        seen.add(issue)


def _run_rule_sets(
    manifest: FormationManifest, profile: FormationProfile, candidate: CandidateMetamodel
) -> tuple[MetamodelIssue, ...]:
    """Invoke every Rule Set once, in manifest order, over the same candidate."""
    with _contract_reads(FORMATION_PROFILE_DRIFT, "reading the profile's Rule Sets raised"):
        rule_sets = {rule_set.owner: rule_set for rule_set in profile.rule_sets}
    seen: set[MetamodelIssue] = set()
    aggregate: list[MetamodelIssue] = []
    for entry in manifest.entries:
        if not isinstance(entry.rule_set, RequiredRuleSet):
            continue
        rule_set = rule_sets[entry.owner]
        try:
            returned: object = rule_set.validate(candidate)
        except Exception as error:
            raise FormationContractError(
                FORMATION_RULE_SET_FAILED,
                "the Rule Set raised instead of returning its issue sequence",
                owner=entry.owner,
                cause=error,
            ) from error
        issues = _issue_sequence(returned)
        if issues is None:
            raise FormationContractError(
                FORMATION_RULE_SET_RESULT_INVALID,
                "the Rule Set returned a mutable collection or a non-issue element",
                owner=entry.owner,
            )
        _check_emitted(entry.owner, entry.issue_codes, issues, seen)
        aggregate.extend(issues)
    return sort_issues(aggregate)


def _compile_metadata(profile: FormationProfile, candidate: CandidateMetamodel) -> CompiledMetadata:
    """Compile the accepted candidate into the one graph the Metamodel will own.

    Drift checking established the compiler's owner, so a defect here is always
    ``formation-compiler-failed``: the compiler raised, or handed back something
    that is not Compiled Metadata.
    """
    with _contract_reads(
        FORMATION_COMPILER_FAILED,
        "reading the Metadata Compiler's contract raised",
        owner=METAMODEL_MODULE,
    ):
        compiler = profile.metadata_compiler
        owner = compiler.owner
    try:
        metadata: object = compiler.compile(candidate)
    except Exception as error:
        raise FormationContractError(
            FORMATION_COMPILER_FAILED,
            "the Metadata Compiler failed on an accepted candidate",
            owner=owner,
            cause=error,
        ) from error
    if not is_compiled_metadata(metadata):
        raise FormationContractError(
            FORMATION_COMPILER_FAILED,
            "the Metadata Compiler returned a value that is not Compiled Metadata",
            owner=owner,
        )
    return metadata


def _compilation_order(
    declared: Mapping[ModuleIdentity, FacetKey[Any]], profile: FormationProfile
) -> list[ModelCompiler[Any]]:
    """Model Compilers in topological facet order, ascending owner breaking ties.

    Drift checking proved every requirement is compiled and the declared graph is
    acyclic, so a stable profile always leaves some compiler eligible. A profile
    whose contract members answer differently on a second read invalidates that
    proof, which is drift rather than an exhausted-iterator error.
    """
    with _contract_reads(
        FORMATION_PROFILE_DRIFT, "reading the Model Compilers' ordering contract raised"
    ):
        remaining = sorted(profile.model_compilers, key=lambda compiler: compiler.owner)
        installed: set[FacetKey[Any]] = set()
        order: list[ModelCompiler[Any]] = []
        while remaining:
            position = next(
                (
                    index
                    for index, compiler in enumerate(remaining)
                    if frozenset(compiler.requires) <= installed
                ),
                None,
            )
            if position is None:
                raise _drift(
                    "no Model Compiler is eligible; the profile's requirements no longer "
                    "match the drift-checked contract",
                    owner=min(compiler.owner for compiler in remaining),
                )
            eligible = remaining.pop(position)
            installed.add(declared[eligible.owner])
            order.append(eligible)
    return order


def _compile_facets(
    manifest: FormationManifest, profile: FormationProfile, metadata: CompiledMetadata
) -> Mapping[FacetKey[Any], object]:
    """Compile the complete facet set, publishing none of it until all succeed.

    Every key here is the manifest's, resolved by owner: a compiler names its own
    facet and its prerequisites with keys that compare equal to the declared ones
    however their acceptance checks answer, so trusting one would let a compiler
    decide whether its own result is a facet, or hand a peer another module's key
    carrying a check that module never wrote. Each compiler receives a read-only
    mapping of exactly the facets it declared, keyed the way the manifest
    declares them, and its result is installed only after the owning module's own
    acceptance check accepted it.
    """
    declared = _declared_facet_keys(manifest.entries)
    facets: dict[FacetKey[Any], object] = {}
    for compiler in _compilation_order(declared, profile):
        with _contract_reads(
            FORMATION_COMPILER_FAILED, "reading a Model Compiler's contract raised"
        ):
            owner = compiler.owner
            key = declared[owner]
            required = MappingProxyType(
                {
                    declared[needed.owner]: facets[needed]
                    for needed in sorted(compiler.requires, key=lambda facet: facet.owner)
                }
            )
        try:
            facet = compiler.compile(metadata, required)
        except Exception as error:
            raise FormationContractError(
                FORMATION_COMPILER_FAILED,
                "the Model Compiler failed on accepted metadata",
                owner=owner,
                cause=error,
            ) from error
        if isinstance(facet, _MUTABLE_FACET_TYPES):
            raise FormationContractError(
                FORMATION_COMPILER_FAILED,
                "the Model Compiler returned a mutable collection as its facet",
                owner=owner,
            )
        with _contract_reads(
            FORMATION_COMPILER_FAILED, "the facet key's own acceptance check raised", owner=owner
        ):
            accepted = key.accepts(facet)
        if not accepted:
            raise FormationContractError(
                FORMATION_COMPILER_FAILED,
                f"the Model Compiler returned a value {key.owner!r} does not accept as its facet",
                owner=owner,
            )
        facets[key] = facet
    return MappingProxyType(facets)
