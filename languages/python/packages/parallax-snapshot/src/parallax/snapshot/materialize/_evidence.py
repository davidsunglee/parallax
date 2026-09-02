"""The one walk that turns a rejected internal value into public evidence.

Three seams judge stored data — the document codec, direct-scalar admission, and
family-tag resolution — and each captures what it rejected in the vocabulary it
judged in. This is where those vocabularies become the one public one and where
the result is frozen, in a single traversal: translating and freezing apart would
cost a second walk and leave an intermediate frozen form nobody holds.

The product is ordinary immutable Python, with no frozen-dict type of its own,
and it is the judging row's candidate rather than the copy a diagnosis is
guaranteed to carry: where two rows judge one occurrence alike, the graph builder
keeps the copy that arrived first and drops the later equal one, so exactly one
survives. Every seam above that decision shares the surviving object by reference
rather than translating or detaching its own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from parallax.core.base import inert_scalar
from parallax.core.document_codec import MISSING
from parallax.snapshot.materialize._invalid import MISSING_STORED_VALUE

__all__ = ["freeze_evidence"]


def freeze_evidence(value: object) -> object:
    """``value`` as the judging row's immutable candidate for public evidence.

    The codec's absence marker becomes the public one — a genuinely absent
    member reads :data:`~parallax.snapshot.materialize.MISSING_STORED_VALUE` —
    while a stored SQL or JSON null needs no translation: every judging seam
    captures one as the ordinary ``None`` a caller reads it as. Arrays become
    tuples, objects become detached read-only mappings, and every scalar — the
    null included — is left inert.

    Decoded document structure has no cycles, so the walk carries no memo, and
    an array is a ``list`` or a ``tuple`` rather than any sequence — the same
    reading :func:`~parallax.core.base.detach_json_container` takes of the JSON
    data model, which is what keeps text and byte-likes whole scalars here.
    """
    if value is MISSING:
        return MISSING_STORED_VALUE
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: freeze_evidence(item)
                for key, item in cast("Mapping[str, object]", value).items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_evidence(item) for item in cast("Sequence[object]", value))
    return inert_scalar(value)
