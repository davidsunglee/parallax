"""Shared operation-tag vocabularies for walkers that inspect entity references.

The operation schema distinguishes scalar attribute references from value-object
paths. Several validators walk those two reference sites for different purposes,
so the tag sets live here rather than being copied into each walker.
"""

from __future__ import annotations

ATTRIBUTE_REFERENCE_TAGS = frozenset(
    {
        "eq",
        "notEq",
        "greaterThan",
        "greaterThanEquals",
        "lessThan",
        "lessThanEquals",
        "between",
        "isNull",
        "isNotNull",
        "like",
        "notLike",
        "startsWith",
        "endsWith",
        "contains",
        "in",
        "notIn",
    }
)

PATH_REFERENCE_TAGS = frozenset(
    {
        "nestedEq",
        "nestedNotEq",
        "nestedGt",
        "nestedGte",
        "nestedLt",
        "nestedLte",
        "nestedIn",
        "nestedIsNull",
        "nestedIsNotNull",
        "nestedExists",
        "nestedNotExists",
    }
)
