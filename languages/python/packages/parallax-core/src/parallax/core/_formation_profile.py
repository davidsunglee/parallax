"""The built-in Model Formation composition root.

The one place that names every contributor Parallax ships. It supplies the
Formation Manifest — immutable identity, Issue Code, facet, and dependency data
— separately from the Formation Profile that supplies the matching
implementations, so a contributor that is imported but undeclared, or declared
but unsupplied, fails drift checking instead of quietly changing what a model
means. Every contributor is imported explicitly here; nothing registers itself,
and no manifest row is derived from a contributor object.

This module is a composition root, not a public surface: it is the only core
module permitted to import contributors from several enforcement scopes at once,
and it exposes no behavior of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import INHERITANCE_MODULE
from parallax.core.inheritance import ISSUE_CODES as INHERITANCE_ISSUE_CODES
from parallax.core.inheritance import MODEL_COMPILER as INHERITANCE_COMPILER
from parallax.core.inheritance import RULE_SET as INHERITANCE_RULE_SET
from parallax.core.metamodel import (
    METADATA_COMPILER,
    METAMODEL_MODULE,
    RESOLVER_ISSUE_CODES,
    Metamodel,
    UnresolvedMetamodel,
)
from parallax.core.model_formation import (
    FIXED_RESOLVER,
    METADATA_COMPILER_REQUIRED,
    MODEL_FORMATION_MODULE,
    REQUIRED_RULE_SET,
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
from parallax.core.opt_lock import FACET_KEY as OPT_LOCK_FACET_KEY
from parallax.core.opt_lock import ISSUE_CODES as OPT_LOCK_ISSUE_CODES
from parallax.core.opt_lock import MODEL_COMPILER as OPT_LOCK_COMPILER
from parallax.core.opt_lock import OPT_LOCK_MODULE
from parallax.core.opt_lock import RULE_SET as OPT_LOCK_RULE_SET
from parallax.core.relationship import FACET_KEY as RELATIONSHIP_FACET_KEY
from parallax.core.relationship import ISSUE_CODES as RELATIONSHIP_ISSUE_CODES
from parallax.core.relationship import MODEL_COMPILER as RELATIONSHIP_COMPILER
from parallax.core.relationship import RELATIONSHIP_MODULE
from parallax.core.relationship import RULE_SET as RELATIONSHIP_RULE_SET
from parallax.core.storage_layout import FACET_KEY as STORAGE_LAYOUT_FACET_KEY
from parallax.core.storage_layout import ISSUE_CODES as STORAGE_LAYOUT_ISSUE_CODES
from parallax.core.storage_layout import MODEL_COMPILER as STORAGE_LAYOUT_COMPILER
from parallax.core.storage_layout import RULE_SET as STORAGE_LAYOUT_RULE_SET
from parallax.core.storage_layout import STORAGE_LAYOUT_MODULE
from parallax.core.temporal_read import FACET_KEY as TEMPORAL_FACET_KEY
from parallax.core.temporal_read import MODEL_COMPILER as TEMPORAL_COMPILER
from parallax.core.temporal_read import TEMPORAL_READ_MODULE
from parallax.core.value_object import ISSUE_CODES as VALUE_OBJECT_ISSUE_CODES
from parallax.core.value_object import RULE_SET as VALUE_OBJECT_RULE_SET
from parallax.core.value_object import VALUE_OBJECT_MODULE

__all__ = ["BUILTIN_MANIFEST", "BUILTIN_PROFILE", "MetamodelValidationError", "form_metamodel"]
# `MetamodelValidationError` is the error `form_metamodel` raises; re-exported
# here so a caller granted only this composition root (never `m-model-formation`
# directly) can catch the one error its own `form_metamodel` call can produce.

_PK_GEN_MODULE: Final[ModuleIdentity] = "m-pk-gen"
"""The one manifest owner this file names without importing it.

Primary-key generation contributes neither a Rule Set nor a compiler — its
invalid generator states are unconstructible in normalized Metadata — so it has
nothing to supply and no reason to be imported here. Its row still belongs in the
manifest, because catalog completeness is measured against the manifest rather
than against whichever contributors happen to exist."""

BUILTIN_MANIFEST: Final[FormationManifest] = FormationManifest(
    (
        FormationManifestEntry(
            owner=METAMODEL_MODULE,
            rule_set=FIXED_RESOLVER,
            issue_codes=RESOLVER_ISSUE_CODES,
            compiler=METADATA_COMPILER_REQUIRED,
        ),
        FormationManifestEntry(
            owner=_PK_GEN_MODULE,
            required_modules=frozenset({METAMODEL_MODULE}),
        ),
        FormationManifestEntry(
            owner=INHERITANCE_MODULE,
            rule_set=REQUIRED_RULE_SET,
            issue_codes=INHERITANCE_ISSUE_CODES,
            compiler=ModelCompilerRequirement(INHERITANCE_FACET_KEY),
            required_modules=frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE}),
        ),
        FormationManifestEntry(
            owner=STORAGE_LAYOUT_MODULE,
            rule_set=REQUIRED_RULE_SET,
            issue_codes=STORAGE_LAYOUT_ISSUE_CODES,
            compiler=ModelCompilerRequirement(STORAGE_LAYOUT_FACET_KEY),
            required_modules=frozenset(
                {METAMODEL_MODULE, MODEL_FORMATION_MODULE, INHERITANCE_MODULE}
            ),
            required_facets=frozenset({INHERITANCE_FACET_KEY}),
        ),
        FormationManifestEntry(
            owner=VALUE_OBJECT_MODULE,
            rule_set=REQUIRED_RULE_SET,
            issue_codes=VALUE_OBJECT_ISSUE_CODES,
            required_modules=frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE}),
        ),
        FormationManifestEntry(
            owner=RELATIONSHIP_MODULE,
            rule_set=REQUIRED_RULE_SET,
            issue_codes=RELATIONSHIP_ISSUE_CODES,
            compiler=ModelCompilerRequirement(RELATIONSHIP_FACET_KEY),
            required_modules=frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE}),
        ),
        FormationManifestEntry(
            owner=TEMPORAL_READ_MODULE,
            compiler=ModelCompilerRequirement(TEMPORAL_FACET_KEY),
            required_modules=frozenset(
                {METAMODEL_MODULE, MODEL_FORMATION_MODULE, INHERITANCE_MODULE}
            ),
            required_facets=frozenset({INHERITANCE_FACET_KEY}),
        ),
        FormationManifestEntry(
            owner=OPT_LOCK_MODULE,
            rule_set=REQUIRED_RULE_SET,
            issue_codes=OPT_LOCK_ISSUE_CODES,
            compiler=ModelCompilerRequirement(OPT_LOCK_FACET_KEY),
            required_modules=frozenset(
                {
                    METAMODEL_MODULE,
                    MODEL_FORMATION_MODULE,
                    INHERITANCE_MODULE,
                    TEMPORAL_READ_MODULE,
                }
            ),
            required_facets=frozenset({INHERITANCE_FACET_KEY, TEMPORAL_FACET_KEY}),
        ),
    )
)
"""The contract data every built-in formation is measured against."""


@dataclass(frozen=True, slots=True)
class _BuiltinProfile:
    """The built-in contributor implementations, in manifest order."""

    rule_sets: tuple[ModelRuleSet, ...]
    metadata_compiler: MetadataCompiler
    model_compilers: tuple[ModelCompiler[Any], ...]


BUILTIN_PROFILE: Final[_BuiltinProfile] = _BuiltinProfile(
    rule_sets=(
        INHERITANCE_RULE_SET,
        STORAGE_LAYOUT_RULE_SET,
        VALUE_OBJECT_RULE_SET,
        RELATIONSHIP_RULE_SET,
        OPT_LOCK_RULE_SET,
    ),
    metadata_compiler=METADATA_COMPILER,
    model_compilers=(
        INHERITANCE_COMPILER,
        STORAGE_LAYOUT_COMPILER,
        RELATIONSHIP_COMPILER,
        TEMPORAL_COMPILER,
        OPT_LOCK_COMPILER,
    ),
)
"""The implementations matching :data:`BUILTIN_MANIFEST` row for row."""


def form_metamodel(unresolved: UnresolvedMetamodel) -> Metamodel:
    """Form ``unresolved`` with the built-in manifest and profile.

    The single entry point every Parallax frontend reaches formation through, so
    a descriptor-backed and a class-backed model are formed by exactly the same
    contributors in exactly the same order.
    """
    return form(unresolved, BUILTIN_MANIFEST, BUILTIN_PROFILE)
