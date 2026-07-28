"""``parallax.core.storage_layout`` enforcement scope (m-storage-layout).

Storage Layout validates independent physical Table ownership and physical
Column uniqueness, then compiles one immutable canonical layout per accepted
Table. Consumers retrieve the facet through :func:`view`; this module is the
supported advanced import path and is not re-exported from ``parallax.core``.
"""

from __future__ import annotations

from parallax.core.storage_layout._compile import (
    MODEL_COMPILER,
    StorageLayoutModelCompiler,
    compile_facet,
)
from parallax.core.storage_layout._facet import (
    FACET_KEY,
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DiscriminatorAssignment,
    EntityLayoutView,
    InheritanceDiscriminator,
    PositionBranch,
    PositionColumn,
    PositionLayoutView,
    StorageLayoutFacet,
    TableLayout,
    view,
)
from parallax.core.storage_layout._rules import (
    COLUMN_COLLISION,
    ISSUE_CODES,
    RULE_SET,
    STORAGE_LAYOUT_MODULE,
    TABLE_MAPPING_COLLISION,
    StorageLayoutRuleSet,
)

__all__ = [
    "COLUMN_COLLISION",
    "FACET_KEY",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "RULE_SET",
    "STORAGE_LAYOUT_MODULE",
    "TABLE_MAPPING_COLLISION",
    "ColumnContributor",
    "ColumnSlot",
    "ColumnTier",
    "DiscriminatorAssignment",
    "EntityLayoutView",
    "InheritanceDiscriminator",
    "PositionBranch",
    "PositionColumn",
    "PositionLayoutView",
    "StorageLayoutFacet",
    "StorageLayoutModelCompiler",
    "StorageLayoutRuleSet",
    "TableLayout",
    "compile_facet",
    "view",
]
