"""The reference parse rule (m-metamodel), stated once for the whole harness.

A serialized reference carries an Entity spelling and a member path in one
string, and several harness validators need the boundary between them. The
identifier constraint makes it decidable from the text alone, so this module
owns the rule and every caller delegates rather than splitting at a dot of its
own choosing — a split at the FIRST dot reads a canonical spelling's leading
namespace segment as the Entity and resolves to the wrong Entity in silence.
"""

from __future__ import annotations

__all__ = ["entity_spelling", "split_reference"]


def split_reference(spelling: str) -> tuple[str | None, tuple[str, ...]]:
    """Split a serialized reference into its Entity spelling and member path.

    Every namespace segment begins lowercase, an Entity's local name begins
    uppercase, and every member segment begins lowercase (m-metamodel), so a
    reference carries at most one segment beginning uppercase and that segment
    is the Entity's local name. Everything up to and including it is the Entity
    spelling — bare or canonical, unresolved either way — and everything after
    it is the member path.

    The split is total and position-independent. A reference terminating at the
    Entity yields an empty member path, and an element-relative path carries no
    uppercase segment at all and so yields no Entity spelling::

        "parallax.compatibility.Order.id" -> ("parallax.compatibility.Order", ("id",))
        "Order.address.city"              -> ("Order", ("address", "city"))
        "catalog.SharedVariant"           -> ("catalog.SharedVariant", ())
        "address.city"                    -> (None, ("address", "city"))
    """
    segments = spelling.split(".")
    boundary = -1
    for index, segment in enumerate(segments):
        if segment[:1].isupper():
            boundary = index
    if boundary < 0:
        return None, tuple(segments)
    return ".".join(segments[: boundary + 1]), tuple(segments[boundary + 1 :])


def entity_spelling(reference: object) -> str | None:
    """The Entity ``reference`` names, or ``None`` when it names none.

    ``None`` covers both a non-string node and an element-relative path, which
    a caller checking an Entity spelling treats identically: there is no Entity
    to resolve.
    """
    if not isinstance(reference, str):
        return None
    return split_reference(reference)[0]
