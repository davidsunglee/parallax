from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import Final

from parallax.core.base import Boolean, Int32, Int64, NeutralType, String

__all__ = [
    "ENCODE",
    "ENCODE_MANY",
    "OCCURRENCE",
    "PASS",
    "PASS_MANY",
    "WireEntityFacts",
    "WireModelFacts",
    "WireOccurrenceFacts",
    "scalar_encoding",
]

PASS: Final = 0
"""A scalar whose managed value is already its canonical Wire spelling."""
ENCODE: Final = 1
"""A scalar spelled through the delivery's Wire encoder."""
PASS_MANY: Final = 2
"""A scalar collection whose every element is already canonical."""
ENCODE_MANY: Final = 3
"""A scalar collection whose elements are spelled through the encoder."""
OCCURRENCE: Final = 4
"""A nested Value Object occurrence, rendered through its own facts."""

_CANONICAL_AS_MANAGED: Final = (Boolean, Int32, Int64, String)


def scalar_encoding(neutral_type: NeutralType, *, many: bool) -> int:
    """How one scalar member of ``neutral_type`` renders: its managed value
    unchanged, where the codec spells every value of the type as itself, or
    through the encoder."""
    if isinstance(neutral_type, _CANONICAL_AS_MANAGED):
        return PASS_MANY if many else PASS
    return ENCODE_MANY if many else ENCODE


class WireOccurrenceFacts:
    """How one Value Object occurrence renders, prepared once per model.

    ``keys``, ``encodings`` and ``details`` describe each member of the
    occurrence's shape in shape order: its field key, its encoding, and the
    Neutral Type an encoded scalar is spelled at or the nested facts an
    :data:`OCCURRENCE` member renders through. ``many`` says the occurrence is a
    collection of records.
    """

    __slots__ = ("details", "encodings", "keys", "many")

    def __init__(
        self,
        *,
        many: bool,
        keys: tuple[str, ...],
        encodings: tuple[int, ...],
        details: tuple[NeutralType | WireOccurrenceFacts, ...],
    ) -> None:
        self.many = many
        self.keys = keys
        self.encodings = encodings
        self.details = details


class WireEntityFacts:
    """How one Entity's member row renders, prepared once per model.

    The Attributes come first in the member row, keyed, encoded and typed by
    the three parallel tuples; the family variant spelling follows them in the
    rendered mapping, then each Value Object occurrence under its own key.
    """

    __slots__ = (
        "attribute_encodings",
        "attribute_keys",
        "attribute_types",
        "family_variant",
        "occurrences",
    )

    def __init__(
        self,
        *,
        attribute_keys: tuple[str, ...],
        attribute_encodings: tuple[int, ...],
        attribute_types: tuple[NeutralType, ...],
        family_variant: str | None,
        occurrences: tuple[tuple[str, WireOccurrenceFacts], ...],
    ) -> None:
        self.attribute_keys = attribute_keys
        self.attribute_encodings = attribute_encodings
        self.attribute_types = attribute_types
        self.family_variant = family_variant
        self.occurrences = occurrences


class WireModelFacts:
    """Every Entity's :class:`WireEntityFacts` for one prepared model, by its
    concrete identity.

    Equality is identity: two preparations of one model hold two
    interchangeable sets of facts, and a consumer memoizing what it derives
    from them keys on the set it was handed.
    """

    __slots__ = ("_entities",)

    def __init__(self, entities: Mapping[Hashable, WireEntityFacts]) -> None:
        self._entities = entities

    def entity(self, concrete: Hashable) -> WireEntityFacts:
        """``concrete``'s facts; raises :class:`KeyError` for an Entity the
        model does not declare."""
        return self._entities[concrete]
