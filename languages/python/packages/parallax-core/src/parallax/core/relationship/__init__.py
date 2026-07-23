"""``parallax.core.relationship`` enforcement scope (m-relationship).

Relationship-specific model formation and the immutable symmetric Relationship
Facet. Accepted Entity Metadata preserves the defining-versus-reverse
declaration union exactly as authored; this scope alone validates those
declarations, pairs the two directions of one association, and compiles the
directional values behavioral modules navigate. It owns no runtime navigation,
deep fetch, SQL lowering, or cascade execution, and it reads no facet of another
module. ``m-relationship`` depends on ``m-metamodel`` and ``m-model-formation``.

Consumers reach the facet through :func:`view`, so generic facet retrieval stays
an internal formation seam.
"""

from __future__ import annotations

from parallax.core.relationship._compile import (
    MODEL_COMPILER,
    RelationshipModelCompiler,
    compile_facet,
)
from parallax.core.relationship._facet import (
    FACET_KEY,
    RELATIONSHIP_MODULE,
    RelationshipFacet,
    RelationshipMetadata,
    view,
)
from parallax.core.relationship._rules import (
    CARDINALITY_JOIN_MISMATCH,
    DEFINING_DUPLICATE,
    ISSUE_CODES,
    JOIN_SOURCE_INVALID,
    JOIN_TARGET_INVALID,
    ORDER_ATTRIBUTE_INVALID,
    ORDER_ON_TO_ONE,
    REVERSE_CYCLE,
    REVERSE_INCONSISTENT,
    REVERSE_NOT_DEFINING,
    RULE_SET,
    RelationshipRuleSet,
)

__all__ = [
    "CARDINALITY_JOIN_MISMATCH",
    "DEFINING_DUPLICATE",
    "FACET_KEY",
    "ISSUE_CODES",
    "JOIN_SOURCE_INVALID",
    "JOIN_TARGET_INVALID",
    "MODEL_COMPILER",
    "ORDER_ATTRIBUTE_INVALID",
    "ORDER_ON_TO_ONE",
    "RELATIONSHIP_MODULE",
    "REVERSE_CYCLE",
    "REVERSE_INCONSISTENT",
    "REVERSE_NOT_DEFINING",
    "RULE_SET",
    "RelationshipFacet",
    "RelationshipMetadata",
    "RelationshipModelCompiler",
    "RelationshipRuleSet",
    "compile_facet",
    "view",
]
