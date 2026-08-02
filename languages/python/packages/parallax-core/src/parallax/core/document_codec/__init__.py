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
    DocumentPatch,
    SetLeaf,
    SetOccurrence,
    apply_patches,
    comparison_text,
    decode_path,
    encode_candidate,
    encode_document,
    encode_many,
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
    occurrence_shape,
    shape_of_declaration,
)

__all__ = [
    "MISSING",
    "NULL",
    "DocumentMember",
    "DocumentPatch",
    "DocumentShape",
    "ExplicitNull",
    "Leaf",
    "LeafEncodingError",
    "Missing",
    "Occurrence",
    "Presence",
    "Present",
    "SetLeaf",
    "SetOccurrence",
    "apply_patches",
    "comparison_text",
    "decode_path",
    "encode_candidate",
    "encode_document",
    "encode_leaf",
    "encode_many",
    "is_text_compared",
    "occurrence_shape",
    "shape_of_declaration",
]
