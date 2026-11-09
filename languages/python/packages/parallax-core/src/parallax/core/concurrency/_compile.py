from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

from parallax.core.concurrency._facet import (
    CONCURRENCY_MODULE,
    FACET_KEY,
    UNVERSIONED,
    ConcurrencyFacet,
    ExplicitVersion,
    TransactionTimeVersion,
    VersionSource,
    concurrency_facet,
)
from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import InheritanceFacet, root_metadata
from parallax.core.metamodel import (
    CompiledMetadata,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.temporal_read import FACET_KEY as TEMPORAL_FACET_KEY
from parallax.core.temporal_read import (
    Bitemporal,
    NonTemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
)

__all__ = ["MODEL_COMPILER"]


def compile_facet(
    metadata: CompiledMetadata, inheritance: InheritanceFacet, temporal: TemporalFacet
) -> ConcurrencyFacet:
    """Compile every accepted Entity's version source from its family root.

    Each family's source is derived once, from its root, and every descendant's
    entry is that same object.
    """
    families = [
        (entity.identity, root_metadata(inheritance, metadata, entity.identity))
        for entity in metadata.entities
    ]
    sources: dict[EntityIdentity, VersionSource] = {}
    for entity, root in families:
        if root.identity == entity:
            sources[entity] = _version_source(root, _shape(temporal, entity))
    for entity, root in families:
        if root.identity != entity:
            sources[entity] = sources[root.identity]
    return concurrency_facet(sources)


def _shape(temporal: TemporalFacet, entity: EntityIdentity) -> TemporalShape:
    """``entity``'s effective temporal shape, which the Temporal Facet answers for all."""
    return cast(TemporalShape, temporal.shape(entity))


def _version_source(root: EntityMetadata, shape: TemporalShape) -> VersionSource:
    """The version source a family with this root and this shape carries."""
    match shape:
        case TransactionTimeOnly(transaction_time) | Bitemporal(_, transaction_time):
            return TransactionTimeVersion(transaction_time.start_attribute)
        case NonTemporal():
            return _explicit_version(root)


def _explicit_version(root: EntityMetadata) -> VersionSource:
    """The version Attribute ``root`` declares, or the unversioned source; a
    root declaring more than one was already rejected."""
    versions = [member for member in root.declared_attributes if member.optimistic_locking]
    if not versions:
        return UNVERSIONED
    return ExplicitVersion(versions[0].identity)


def _required_facets(
    required_facets: Mapping[FacetKey[Any], object],
) -> tuple[InheritanceFacet, TemporalFacet]:
    """The two facets this compiler declared it requires, which the runner
    supplies under the manifest's own keys."""
    return (
        cast(InheritanceFacet, required_facets[INHERITANCE_FACET_KEY]),
        cast(TemporalFacet, required_facets[TEMPORAL_FACET_KEY]),
    )


class ConcurrencyModelCompiler:
    """This module's Model Compiler: one facet, two prerequisite facets, no issues."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this compiler."""
        return CONCURRENCY_MODULE

    @property
    def facet_key(self) -> FacetKey[ConcurrencyFacet]:
        """The key the compiled facet is installed under."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The facets this compiler reads: the family root and its temporal shape."""
        return frozenset({INHERITANCE_FACET_KEY, TEMPORAL_FACET_KEY})

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> ConcurrencyFacet:
        """Compile ``metadata``'s version sources into the per-Entity facet."""
        inheritance, temporal = _required_facets(required_facets)
        return compile_facet(metadata, inheritance, temporal)


MODEL_COMPILER: Final[ConcurrencyModelCompiler] = ConcurrencyModelCompiler()
"""The single Model Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""
