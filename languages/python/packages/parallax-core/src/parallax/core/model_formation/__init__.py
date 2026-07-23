"""``parallax.core.model_formation`` enforcement scope (m-model-formation).

Deterministic composition of module-owned model rules and compilers. This scope
owns the Formation Manifest data types, the contributor protocols, the two
formation failure families, and the runner that drives one formation from an
Unresolved Metamodel to an accepted Metamodel. It owns no semantic rule and no
Issue Code, imports no contributor implementation, and performs no discovery:
it learns what a formation consists of only from the immutable manifest an
explicit composition root hands it. ``m-model-formation`` depends only on
``m-metamodel``.

Import-time registration, decorators, entry points, plugins, ambient registries,
and mutable contributor lists have no place here by construction — a
contributor the manifest does not declare is drift, not configuration.
"""

from __future__ import annotations

from parallax.core.model_formation._contributors import (
    FormationProfile,
    MetadataCompiler,
    ModelCompiler,
    ModelRuleSet,
)
from parallax.core.model_formation._errors import (
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
    FormationContractCode,
    FormationContractError,
    MetamodelValidationError,
)
from parallax.core.model_formation._manifest import (
    FIXED_RESOLVER,
    METADATA_COMPILER_REQUIRED,
    REQUIRED_RULE_SET,
    CompilerRequirement,
    FixedResolver,
    FormationManifest,
    FormationManifestEntry,
    MetadataCompilerRequirement,
    ModelCompilerRequirement,
    ModuleIdentity,
    RequiredRuleSet,
    RuleSetRequirement,
)
from parallax.core.model_formation._runner import form

__all__ = [
    "FIXED_RESOLVER",
    "FORMATION_COMPILER_FAILED",
    "FORMATION_CONTRACT_CODES",
    "FORMATION_FACET_DUPLICATE",
    "FORMATION_FACET_MISSING",
    "FORMATION_ISSUE_CODE_INVALID",
    "FORMATION_ISSUE_DUPLICATE",
    "FORMATION_ISSUE_UNDECLARED",
    "FORMATION_PROFILE_DRIFT",
    "FORMATION_RESOLVER_FAILED",
    "FORMATION_RESOLVER_RESULT_INVALID",
    "FORMATION_RULE_SET_FAILED",
    "FORMATION_RULE_SET_RESULT_INVALID",
    "METADATA_COMPILER_REQUIRED",
    "REQUIRED_RULE_SET",
    "CompilerRequirement",
    "FixedResolver",
    "FormationContractCode",
    "FormationContractError",
    "FormationManifest",
    "FormationManifestEntry",
    "FormationProfile",
    "MetadataCompiler",
    "MetadataCompilerRequirement",
    "MetamodelValidationError",
    "ModelCompiler",
    "ModelCompilerRequirement",
    "ModelRuleSet",
    "ModuleIdentity",
    "RequiredRuleSet",
    "RuleSetRequirement",
    "form",
]
