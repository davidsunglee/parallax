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
    FormationManifest,
    FormationManifestEntry,
    MetadataCompiler,
    ModelCompiler,
    ModelRuleSet,
    form,
)

__all__ = ["BUILTIN_MANIFEST", "BUILTIN_PROFILE", "form_metamodel"]

BUILTIN_MANIFEST: Final[FormationManifest] = FormationManifest(
    (
        FormationManifestEntry(
            owner=METAMODEL_MODULE,
            rule_set=FIXED_RESOLVER,
            issue_codes=RESOLVER_ISSUE_CODES,
            compiler=METADATA_COMPILER_REQUIRED,
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
    rule_sets=(),
    metadata_compiler=METADATA_COMPILER,
    model_compilers=(),
)
"""The implementations matching :data:`BUILTIN_MANIFEST` row for row."""


def form_metamodel(unresolved: UnresolvedMetamodel) -> Metamodel:
    """Form ``unresolved`` with the built-in manifest and profile.

    The single entry point every Parallax frontend reaches formation through, so
    a descriptor-backed and a class-backed model are formed by exactly the same
    contributors in exactly the same order.
    """
    return form(unresolved, BUILTIN_MANIFEST, BUILTIN_PROFILE)
