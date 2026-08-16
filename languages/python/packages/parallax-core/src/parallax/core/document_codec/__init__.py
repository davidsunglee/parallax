"""``parallax.core.document_codec`` enforcement scope (m-document-codec).

The portable representation of every neutral value stored inside a structured
document, and the in-memory operations that build, read, and patch such a document.
The module is **pure**: it performs no I/O, holds no connection, imports no driver, and
emits no SQL, and it contains no dialect or database-adapter seam — a codec value
crosses that seam already portable.

It owns two document kinds at once — a Value Object occurrence's own document under
conventional Columns layout, and the shared Structured Column of a Relational Document
Layout Entity — because a ``Decimal`` inside a Value Object and a ``Decimal`` inside an
Entity document are the same six characters, so the two cannot drift apart and no
consumer needs to know which kind it holds.

Consumers retrieve nothing through a facet: every operation is a pure function of its
arguments. This module is the supported import path and is not re-exported from
``parallax.core``.
"""

from __future__ import annotations

from parallax.core.document_codec._document import (
    UNAVAILABLE,
    DecodedMember,
    DocumentFinding,
    DocumentFindingCode,
    DocumentPatch,
    DocumentPathSegment,
    LocatedMemberInput,
    SetLeaf,
    SetValue,
    Unavailable,
    apply_patches,
    comparison_text,
    decode_located_member_classified,
    decode_occurrence_classified,
    decode_path,
    decode_path_classified,
    encode_candidate,
    encode_document,
    encode_many,
    locate_entity_member,
    reduce_declared_members,
    reduce_declared_members_classified,
)
from parallax.core.document_codec._leaf import LeafEncodingError, encode_leaf, is_text_compared
from parallax.core.document_codec._shape import (
    MISSING,
    NULL,
    DocumentMember,
    DocumentShape,
    ExplicitNull,
    Leaf,
    Missing,
    Occurrence,
    Presence,
    Present,
    entity_shape,
    occurrence_shape,
    shape_of_declaration,
)

__all__ = [
    "MISSING",
    "NULL",
    "UNAVAILABLE",
    "DecodedMember",
    "DocumentFinding",
    "DocumentFindingCode",
    "DocumentMember",
    "DocumentPatch",
    "DocumentPathSegment",
    "DocumentShape",
    "ExplicitNull",
    "Leaf",
    "LeafEncodingError",
    "LocatedMemberInput",
    "Missing",
    "Occurrence",
    "Presence",
    "Present",
    "SetLeaf",
    "SetValue",
    "Unavailable",
    "apply_patches",
    "comparison_text",
    "decode_located_member_classified",
    "decode_occurrence_classified",
    "decode_path",
    "decode_path_classified",
    "encode_candidate",
    "encode_document",
    "encode_leaf",
    "encode_many",
    "entity_shape",
    "is_text_compared",
    "locate_entity_member",
    "occurrence_shape",
    "reduce_declared_members",
    "reduce_declared_members_classified",
    "shape_of_declaration",
]
