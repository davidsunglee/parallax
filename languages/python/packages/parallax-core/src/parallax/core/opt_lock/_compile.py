"""The Optimistic Lock Facet's Model Compiler (m-opt-lock).

Compilation runs only after every Rule Set accepted the candidate, so it decides
no validity and emits no issue: it asks the Inheritance Facet for each Entity's
family root and the Temporal Facet for that family's shape, then reads whichever
of the two version sources applies. The Transaction-Time shape wins by
construction rather than by precedence — a temporal family declaring a version
Attribute was already rejected — so the two keyed variants stay mutually
exclusive.

Reaching a state validation ruled out raises, so the formation runner reports a
compiler contract failure rather than publishing a facet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    CompiledMetadata,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.opt_lock._facet import (
    FACET_KEY,
    OPT_LOCK_MODULE,
    UNVERSIONED,
    ExplicitVersion,
    OptimisticKey,
    OptimisticLockFacet,
    TransactionTimeDerived,
    optimistic_lock_facet,
)
from parallax.core.temporal_read import FACET_KEY as TEMPORAL_FACET_KEY
from parallax.core.temporal_read import (
    Bitemporal,
    NonTemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
)

__all__ = ["MODEL_COMPILER", "OptimisticLockModelCompiler", "compile_facet"]


def compile_facet(
    metadata: CompiledMetadata, inheritance: InheritanceFacet, temporal: TemporalFacet
) -> OptimisticLockFacet:
    """Compile every accepted Entity's optimistic key from its family root."""
    return optimistic_lock_facet(
        {
            entity.identity: _key(
                _root(metadata, inheritance, entity.identity),
                _shape(temporal, entity.identity),
            )
            for entity in metadata.entities
        }
    )


def _root(
    metadata: CompiledMetadata, inheritance: InheritanceFacet, entity: EntityIdentity
) -> EntityMetadata:
    """The Entity whose declarations fix the whole family's key.

    The Inheritance Facet covers every accepted Entity and its root is one of
    them, so an absent view or an unreachable root is a state formation output
    cannot be in.
    """
    position = inheritance.entity(entity)
    root = None if position is None else metadata.entity(position.root)
    if root is None:
        raise RuntimeError(
            f"Entity {entity.canonical!r} has no Inheritance Facet view, or names a "
            "family root the accepted Metamodel does not contain"
        )
    return root


def _shape(temporal: TemporalFacet, entity: EntityIdentity) -> TemporalShape:
    """``entity``'s effective temporal shape, which the Temporal Facet answers for all."""
    shape = temporal.shape(entity)
    if shape is None:
        raise RuntimeError(
            f"Entity {entity.canonical!r} has no Temporal Facet shape, which every "
            "accepted Entity carries"
        )
    return shape


def _key(root: EntityMetadata, shape: TemporalShape) -> OptimisticKey:
    """The optimistic key a family with this root and this shape carries."""
    match shape:
        case TransactionTimeOnly(transaction_time) | Bitemporal(_, transaction_time):
            return TransactionTimeDerived(transaction_time.start_attribute)
        case NonTemporal():
            return _explicit_key(root)


def _explicit_key(root: EntityMetadata) -> OptimisticKey:
    """The version Attribute ``root`` declares, or the unversioned key.

    A root declaring more than one was already rejected, so meeting a second here
    is a state no accepted model can be in.
    """
    versions = [member for member in root.declared_attributes if member.optimistic_locking]
    if not versions:
        return UNVERSIONED
    if len(versions) > 1:
        raise RuntimeError(
            f"Entity {root.identity.canonical!r} declares {len(versions)} version "
            "Attributes, which validation should have rejected"
        )
    return ExplicitVersion(versions[0].identity)


def _required_facets(
    required_facets: Mapping[FacetKey[Any], object],
) -> tuple[InheritanceFacet, TemporalFacet]:
    """The two facets this compiler declared it requires.

    The runner supplies exactly the declared facets under the manifest's own
    keys, so a mapping that answers otherwise is a formation seam defect rather
    than a model one.
    """
    inheritance = required_facets.get(INHERITANCE_FACET_KEY)
    if not INHERITANCE_FACET_KEY.accepts(inheritance):
        raise RuntimeError("the required Inheritance Facet was not supplied under its own key")
    temporal = required_facets.get(TEMPORAL_FACET_KEY)
    if not TEMPORAL_FACET_KEY.accepts(temporal):
        raise RuntimeError("the required Temporal Facet was not supplied under its own key")
    return inheritance, temporal


class OptimisticLockModelCompiler:
    """This module's Model Compiler: one facet, two prerequisite facets, no issues."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this compiler."""
        return OPT_LOCK_MODULE

    @property
    def facet_key(self) -> FacetKey[OptimisticLockFacet]:
        """The key the compiled facet is installed under."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The facets this compiler reads: the family root and its temporal shape."""
        return frozenset({INHERITANCE_FACET_KEY, TEMPORAL_FACET_KEY})

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> OptimisticLockFacet:
        """Compile ``metadata``'s optimistic keys into the per-Entity facet."""
        inheritance, temporal = _required_facets(required_facets)
        return compile_facet(metadata, inheritance, temporal)


MODEL_COMPILER: Final[OptimisticLockModelCompiler] = OptimisticLockModelCompiler()
"""The single Model Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""
