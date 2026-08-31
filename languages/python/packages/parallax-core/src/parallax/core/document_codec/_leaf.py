"""The document leaf seam over the canonical Wire Value table (m-document-codec,
"Portable leaf encodings").

A document leaf's spelling IS the value's canonical Wire Value, so the table lives
in :mod:`parallax.core.wire` and this module states none of its own. What it adds
is the document POSITION: a failure here names the failing member, so the caller
resolves it by name at each containment step.

The string spellings are comparison-significant, not house style. SQL compares the
six text-compared types by comparing the extracted text directly, so changing one
changes predicate and ordering results and MUST move `m-dialect`'s corresponding
decision with it rather than travel alone.
"""

from __future__ import annotations

from typing import cast

from parallax.core.base import (
    Bytes,
    Date,
    ManagedValue,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
)
from parallax.core.wire import (
    WireDecodingError,
    WireEncodingError,
    WireValue,
    decode_canonical_wire,
    encode_wire,
)

__all__ = ["LeafEncodingError", "decode_leaf", "encode_leaf", "is_text_compared"]

# The declared types whose document form is a JSON string AND whose SQL comparison is
# of the extracted text rather than of a cast (`m-dialect`). `decimal(p, s)` is a JSON
# string too and is deliberately absent: it casts with the numeric family, because its
# integer part has no fixed width, so `10.00` sorts below `9.00` as text.
_TEXT_COMPARED: tuple[type, ...] = (String, Bytes, Date, Time, Timestamp, Uuid)


class LeafEncodingError(Exception):
    """A stored leaf and the Neutral Type its member declares do not pair.

    The document-positioned reading of `m-wire`'s refusal: a value outside the
    declared value space has no spelling, and a stored leaf that is not the one
    canonical spelling of some value of that space is the encoding of nothing. The
    table is total over the type algebra and says nothing about either, and
    inventing an answer for one is exactly what the codec exists to prevent.

    ``path`` names the failing member as a SEQUENCE of declared names relative to
    whatever the caller reduced, so a consumer resolves the member by name at each
    step. A member name is any nonempty string (`m-metamodel` "Canonical
    identities and order"), so the rendered ``.``-joined spelling is ambiguous —
    a leaf named ``a.b`` and a leaf ``b`` inside an occurrence ``a`` render alike
    — and only the sequence distinguishes them. Empty for a failure at the
    reduced value itself.
    """

    def __init__(self, detail: str, *, path: tuple[str, ...] = ()) -> None:
        super().__init__(f"{'.'.join(path)}: {detail}" if path else detail)
        self.detail = detail
        self.path = path

    def under(self, name: str) -> LeafEncodingError:
        """The same failure reported one containment step out, under ``name``."""
        return LeafEncodingError(self.detail, path=(name, *self.path))


def is_text_compared(neutral_type: NeutralType) -> bool:
    """Whether a document-resident member of ``neutral_type`` compares as extracted
    text rather than through a dialect cast (`m-dialect`)."""
    return isinstance(neutral_type, _TEXT_COMPARED)


def encode_leaf(neutral_type: NeutralType, value: object) -> object:
    """``value``'s one document spelling under ``neutral_type``.

    The canonical Wire Value (`m-wire`), reported at this document position: every
    Neutral Type has exactly one spelling, so two writers of one value produce one
    document, and the result is a portable JSON value — never a driver value, a
    rendered text, or a provider-native document handle.
    """
    try:
        return encode_wire(neutral_type, cast("ManagedValue", value))
    except WireEncodingError as exc:
        raise LeafEncodingError(str(exc)) from exc


def decode_leaf(neutral_type: NeutralType, value: object) -> object:
    """The neutral value ``value`` is the document encoding of.

    :func:`encode_leaf`'s inverse, over the canonical Wire Value table's own
    codomain: a stored leaf must both name a member of the declared value space and
    be the ONE spelling that table gives that member. The second condition is what a
    parse alone does not ask, and enforcing it here is the storage-read seam's
    canonicality obligation (`m-document-codec` "Portable leaf encodings").
    """
    try:
        return decode_canonical_wire(neutral_type, cast("WireValue", value))
    except WireDecodingError as exc:
        raise LeafEncodingError(str(exc)) from exc
