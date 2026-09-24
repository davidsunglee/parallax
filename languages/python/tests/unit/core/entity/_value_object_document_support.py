"""A live Value Object's document, composed the way a write stores it.

A write prepares an occurrence from its live carrier through the borrowed
authoring door, then encodes the prepared value through the codec, so a test
grading the stored document reaches both steps rather than a serializer of its
own.
"""

from __future__ import annotations

from parallax.core.base import FrozenMap
from parallax.core.document_codec._authoring import BORROWED_SOURCE_ACCESS, prepare_authoring
from parallax.core.document_codec._document import encode_managed_document
from parallax.core.entity import ValueObject, shape_of
from parallax.core.unit_work.instructions import (
    _coerce_typed_leaf,  # pyright: ignore[reportPrivateUsage] - the typed write's own leaf coercion, so the document is the one a write stores
)


def stored_document(value: ValueObject) -> FrozenMap[str, object]:
    """``value``'s document as a typed write stores it."""
    shape = shape_of(type(value)).document_shape
    prepared = prepare_authoring(
        shape,
        value,
        source_access=BORROWED_SOURCE_ACCESS,
        normalize_leaf=_coerce_typed_leaf,
    )
    assert not prepared.failures, prepared.failures
    return encode_managed_document(shape, prepared.value)
