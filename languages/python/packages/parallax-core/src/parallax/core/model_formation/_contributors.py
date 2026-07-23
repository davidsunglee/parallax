"""The contributor protocols an explicit composition root supplies (m-model-formation).

Each protocol is one collaboration direction and nothing else: a Rule Set emits
issues and no facet, a compiler produces one value and no issue channel. That
split is what keeps a semantic defect in the model distinguishable from a defect
in the code that inspects it. Protocols are deliberately not
``runtime_checkable`` — a contributor is matched to its manifest row by declared
owner, never by a structural presence test.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from parallax.core.metamodel import (
    CandidateMetamodel,
    CompiledMetadata,
    FacetKey,
    IssueCode,
    MetamodelIssue,
)
from parallax.core.model_formation._manifest import ModuleIdentity

__all__ = [
    "FormationProfile",
    "MetadataCompiler",
    "ModelCompiler",
    "ModelRuleSet",
]


class ModelRuleSet(Protocol):
    """One module's semantic validation of a Candidate Metamodel.

    ``validate`` reports every defect it finds rather than the first, and returns
    an immutable sequence: immutability is part of the contract, so a Rule Set
    that hands back a mutable collection is a contract failure. Emitting a code
    outside ``issue_codes`` is likewise a contract failure, never a model issue.
    """

    @property
    def owner(self) -> ModuleIdentity: ...
    @property
    def issue_codes(self) -> frozenset[IssueCode]: ...
    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]: ...


class MetadataCompiler(Protocol):
    """The one compiler that turns an accepted candidate into Compiled Metadata.

    It runs only after every Rule Set accepted the candidate, so it has no issue
    channel and decides no semantic validity.
    """

    @property
    def owner(self) -> ModuleIdentity: ...
    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata: ...


class ModelCompiler[T](Protocol):
    """One module's compiler for its single typed facet.

    ``requires`` names the facets this compiler reads; the runner supplies
    exactly those, already compiled, and orders compilers so the requirement
    holds. A compiler returns one facet value and never an issue, a metadata
    patch, or a partial Entity update.
    """

    @property
    def owner(self) -> ModuleIdentity: ...
    @property
    def facet_key(self) -> FacetKey[T]: ...
    @property
    def requires(self) -> frozenset[FacetKey[Any]]: ...
    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> T: ...


class FormationProfile(Protocol):
    """The complete set of contributor implementations one formation runs.

    The profile carries implementations; the Formation Manifest carries the
    contract they are measured against. Nothing here is discovered, registered,
    or mutated after composition.
    """

    @property
    def rule_sets(self) -> Sequence[ModelRuleSet]: ...
    @property
    def metadata_compiler(self) -> MetadataCompiler: ...
    @property
    def model_compilers(self) -> Sequence[ModelCompiler[Any]]: ...
