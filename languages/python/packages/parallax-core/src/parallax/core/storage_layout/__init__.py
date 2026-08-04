"""``parallax.core.storage_layout`` enforcement scope (m-storage-layout).

Storage Layout validates independent physical Table ownership, physical Column
uniqueness, and the consequences of the declared Storage Layout, then compiles
one immutable canonical layout per accepted Table. The compiled layout answers
both physical questions — which slot does this contributor own — and logical
ones — where does this member live. Consumers retrieve the facet through
:func:`view`; this module is the supported advanced import path and is not
re-exported from ``parallax.core``.
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
    DirectColumn,
    DiscriminatorAssignment,
    DocumentPath,
    EntityLayoutView,
    InheritanceDiscriminator,
    MemberPlacement,
    PositionBranch,
    PositionColumn,
    PositionLayoutView,
    RelationalDocument,
    StorageLayoutFacet,
    TableLayout,
    view,
)
from parallax.core.storage_layout._rules import (
    COLUMN_COLLISION,
    DOCUMENT_MEMBER_COLUMN_OVERRIDE,
    INDEX_OVER_DOCUMENT_MEMBER,
    ISSUE_CODES,
    RULE_SET,
    STORAGE_LAYOUT_MODULE,
    TABLE_MAPPING_COLLISION,
    StorageLayoutRuleSet,
)

__all__ = [
    "COLUMN_COLLISION",
    "DOCUMENT_MEMBER_COLUMN_OVERRIDE",
    "FACET_KEY",
    "INDEX_OVER_DOCUMENT_MEMBER",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "RULE_SET",
    "STORAGE_LAYOUT_MODULE",
    "TABLE_MAPPING_COLLISION",
    "ColumnContributor",
    "ColumnSlot",
    "ColumnTier",
    "DirectColumn",
    "DiscriminatorAssignment",
    "DocumentPath",
    "EntityLayoutView",
    "InheritanceDiscriminator",
    "MemberPlacement",
    "PositionBranch",
    "PositionColumn",
    "PositionLayoutView",
    "RelationalDocument",
    "StorageLayoutFacet",
    "StorageLayoutModelCompiler",
    "StorageLayoutRuleSet",
    "TableLayout",
    "compile_facet",
    "view",
]
