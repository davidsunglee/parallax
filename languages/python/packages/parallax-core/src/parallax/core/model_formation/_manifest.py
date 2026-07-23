"""The Formation Manifest's immutable contract data (m-model-formation).

The manifest is the closed, authoritative statement of what one formation is
composed of: which module owns which Issue Codes, which compiler each owner
supplies, and what each compiler depends on. It holds contract data only and
never a contributor object, so a composition root that forgot to supply an
implementation — or supplied one nobody declared — is a detectable mismatch
rather than a silent gap. Manifest entry order is the invocation order of Rule
Sets and makes drift diagnostics deterministic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Final

from parallax.core.metamodel import FacetKey, IssueCode

__all__ = [
    "FIXED_RESOLVER",
    "METADATA_COMPILER_REQUIRED",
    "REQUIRED_RULE_SET",
    "CompilerRequirement",
    "FixedResolver",
    "FormationManifest",
    "FormationManifestEntry",
    "MetadataCompilerRequirement",
    "ModelCompilerRequirement",
    "ModuleIdentity",
    "RequiredRuleSet",
    "RuleSetRequirement",
]

type ModuleIdentity = str
"""A canonical ``m-<slug>`` identity from the core module catalog."""


@dataclass(frozen=True, slots=True)
class FixedResolver:
    """The owner's validation is the fixed foundational resolver.

    The resolver is not a profile contributor, so this row declares Issue Codes
    the runner validates resolver output against while requiring no supplied
    Rule Set.
    """


@dataclass(frozen=True, slots=True)
class RequiredRuleSet:
    """The owner must supply a Model Formation Rule Set."""


type RuleSetRequirement = FixedResolver | RequiredRuleSet
"""What a manifest row demands in the Rule Set position; absence is ``None``."""

FIXED_RESOLVER: Final[FixedResolver] = FixedResolver()
REQUIRED_RULE_SET: Final[RequiredRuleSet] = RequiredRuleSet()


@dataclass(frozen=True, slots=True)
class MetadataCompilerRequirement:
    """The owner supplies the one mandatory Metadata Compiler; it has no facet."""


@dataclass(frozen=True, slots=True)
class ModelCompilerRequirement:
    """The owner supplies a Model Compiler producing the facet under ``facet_key``."""

    facet_key: FacetKey[Any]


type CompilerRequirement = MetadataCompilerRequirement | ModelCompilerRequirement
"""What a manifest row demands in the compiler position; absence is ``None``."""

METADATA_COMPILER_REQUIRED: Final[MetadataCompilerRequirement] = MetadataCompilerRequirement()


@dataclass(frozen=True, slots=True)
class FormationManifestEntry:
    """One module's complete formation contract.

    ``issue_codes`` is the owner's exclusive, complete code set: a Rule Set that
    emits anything outside it, or a second row that claims one of its codes, is
    a contract failure rather than a model issue.
    """

    owner: ModuleIdentity
    rule_set: RuleSetRequirement | None = None
    issue_codes: frozenset[IssueCode] = frozenset()
    compiler: CompilerRequirement | None = None
    required_modules: frozenset[ModuleIdentity] = frozenset()
    required_facets: frozenset[FacetKey[Any]] = frozenset()


@dataclass(frozen=True, slots=True)
class FormationManifest:
    """The nonempty ordered set of manifest entries one formation is measured against.

    An empty manifest, or one that names an owner twice, raises
    :class:`ValueError`: the runner resolves every contributor by owner, so a
    manifest that cannot answer "what does this owner contribute?" unambiguously
    is unconstructible rather than a runtime failure mode.
    """

    entries: tuple[FormationManifestEntry, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("a Formation Manifest declares at least one entry")
        repeated = sorted(
            owner
            for owner, count in Counter(entry.owner for entry in self.entries).items()
            if count > 1
        )
        if repeated:
            raise ValueError(f"a Formation Manifest names each owner once; {repeated} repeat")
