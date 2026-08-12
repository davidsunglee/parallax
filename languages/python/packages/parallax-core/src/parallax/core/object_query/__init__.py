"""``parallax.core.object_query`` enforcement scope (m-object-query).

The Object Query: the non-recursive query value that selects and returns full
objects, its clause values, its canonical serde, and its model-aware validation.
Every clause is a sibling of every other, so ``orderBy`` over an eager fetch has
no spelling here rather than a rejection rule.

``m-object-query`` depends only on ``m-predicate``, ``m-metamodel``, and
``m-inheritance``. The three modules that REALIZE its clauses — ``m-temporal-read``
for Temporal Selection, ``m-deep-fetch`` for Includes, ``m-sql`` for ordering and
the cap — depend on it and never the reverse: a clause's value belongs to the
query, and the behavior realizing it belongs to its own module.

The typed authoring surface (:mod:`parallax.core.object_query._fluent`) is
deliberately absent from this interface. It is generic over Entity Classes and so
reaches the Entity frontend, which every one of those three execution modules must
NOT reach; keeping it out of this package's own imports is what makes that
structural rather than asserted. The developer-facing names it owns are re-exported
by ``parallax.core.entity`` and the package root.
"""

from __future__ import annotations

from parallax.core.object_query._canonical import canonical_includes, object_query, subtype_spelling
from parallax.core.object_query._nodes import (
    LATEST,
    TX_TIME,
    VALID_TIME,
    AsOf,
    AsOfRange,
    EntityQuery,
    History,
    IncludePath,
    IncludeSegment,
    Latest,
    MutationSelection,
    ObjectQueryNode,
    OrderKey,
    TemporalDimension,
    TemporalDimensionConstant,
    TemporalSelection,
)
from parallax.core.object_query.serde import ObjectQueryError, deserialize, serialize
from parallax.core.object_query.validate import query_entities, validate_object_query

__all__ = [
    "LATEST",
    "TX_TIME",
    "VALID_TIME",
    "AsOf",
    "AsOfRange",
    "EntityQuery",
    "History",
    "IncludePath",
    "IncludeSegment",
    "Latest",
    "MutationSelection",
    "ObjectQueryError",
    "ObjectQueryNode",
    "OrderKey",
    "TemporalDimension",
    "TemporalDimensionConstant",
    "TemporalSelection",
    "canonical_includes",
    "deserialize",
    "object_query",
    "query_entities",
    "serialize",
    "subtype_spelling",
    "validate_object_query",
]
