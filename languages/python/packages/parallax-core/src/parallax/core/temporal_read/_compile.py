"""The Temporal Facet's Model Compiler (m-temporal-read).

Compilation runs only after every Rule Set accepted the candidate, so it decides
no validity and emits no issue: it asks the Inheritance Facet for each Entity's
family root and classifies that root's declared axes. This module contributes no
Rule Set, because every axis defect is already owned elsewhere — malformed axes
by ``m-metamodel``'s foundational rules, root ownership by ``m-inheritance``.

Reaching a state those rules ruled out — including the unsupported
Valid-Time-Only formation, which no frontend can express and no shape variant can
hold — raises, so the formation runner reports a compiler contract failure rather
than publishing a facet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import InheritanceFacet, root_metadata
from parallax.core.metamodel import (
    CompiledMetadata,
    EntityMetadata,
    FacetKey,
    TemporalDimension,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.temporal_read._facet import (
    FACET_KEY,
    NON_TEMPORAL,
    TEMPORAL_READ_MODULE,
    Bitemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
    temporal_facet,
)

__all__ = ["MODEL_COMPILER", "TemporalReadModelCompiler", "compile_facet"]


def compile_facet(metadata: CompiledMetadata, inheritance: InheritanceFacet) -> TemporalFacet:
    """Compile every accepted Entity's effective temporal shape."""
    return temporal_facet(
        {
            entity.identity: _shape(root_metadata(inheritance, metadata, entity.identity))
            for entity in metadata.entities
        }
    )


def _shape(root: EntityMetadata) -> TemporalShape:
    """The temporal shape ``root``'s declared axes describe.

    A family declaring Valid Time without Transaction Time is the unsupported
    Valid-Time-Only formation; frontends reject it before formation and the shape
    algebra cannot represent it, so meeting one here is an impossible state.
    """
    valid_time = root.as_of_axis(TemporalDimension.VALID_TIME)
    transaction_time = root.as_of_axis(TemporalDimension.TRANSACTION_TIME)
    if transaction_time is None:
        if valid_time is None:
            return NON_TEMPORAL
        raise RuntimeError(
            f"Entity {root.identity.canonical!r} declares Valid Time without Transaction "
            "Time, which is the unsupported Valid-Time-Only formation"
        )
    if valid_time is None:
        return TransactionTimeOnly(transaction_time)
    return Bitemporal(valid_time, transaction_time)


def _required_inheritance(required_facets: Mapping[FacetKey[Any], object]) -> InheritanceFacet:
    """The Inheritance Facet this compiler declared it requires.

    The runner supplies exactly the declared facets under the manifest's own
    keys, so a mapping that answers otherwise is a formation seam defect rather
    than a model one.
    """
    supplied = required_facets.get(INHERITANCE_FACET_KEY)
    if not INHERITANCE_FACET_KEY.accepts(supplied):
        raise RuntimeError("the required Inheritance Facet was not supplied under its own key")
    return supplied


class TemporalReadModelCompiler:
    """This module's Model Compiler: one facet, the Inheritance Facet, no issues."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this compiler."""
        return TEMPORAL_READ_MODULE

    @property
    def facet_key(self) -> FacetKey[TemporalFacet]:
        """The key the compiled facet is installed under."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The facets this compiler reads: a family's root supplies its axes."""
        return frozenset({INHERITANCE_FACET_KEY})

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> TemporalFacet:
        """Compile ``metadata``'s effective temporal shapes into the per-Entity facet."""
        return compile_facet(metadata, _required_inheritance(required_facets))


MODEL_COMPILER: Final[TemporalReadModelCompiler] = TemporalReadModelCompiler()
"""The single Model Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""
