"""Deriving one Physical Index Name per Index definition, and detecting collisions.

A name is ``pxi_<readable-prefix>_<fingerprint>``. The prefix exists to be read
by a person looking at a catalog; the fingerprint is what makes the name unique,
so only the prefix is ever shortened. Every input is the definition's own — the
physical Table, the declaring Entity Identity, the authored Index name, its
ordered components, and its uniqueness — so a definition's name does not move
when an unrelated Index is added beside it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence

from parallax.core.dialect import Dialect, PhysicalIndexName
from parallax.core.metamodel import IndexLocation, canonical_location_key
from parallax.evolution.schema_delta._physical import IndexDefinition
from parallax.evolution.schema_delta._values import (
    CollidingIndex,
    CollisionGroup,
    IndexPresence,
)

__all__ = [
    "collision_groups",
    "physical_index_name",
    "readable_prefix",
]

_NAMESPACE = "pxi"
"""The prefix every generated name opens with, so a catalog reader can tell a
generated Index from an authored constraint at a glance."""

_FINGERPRINT_VERSION = "pxi-1"
"""Opens the hashed field sequence, so a later change to what is hashed produces
different names by construction rather than by coincidence."""

_FINGERPRINT_HEX = 32
"""The first 128 bits of SHA-256, as lowercase hexadecimal."""

_EMPTY_PREFIX = "index"
"""What a readable input carrying no letter or digit at all becomes."""

_UNIQUE_MARKER = {True: "unique", False: "non-unique"}

_PRESENCE: Mapping[tuple[bool, bool], IndexPresence] = {
    (True, False): IndexPresence.EARLIER,
    (False, True): IndexPresence.LATER,
    (True, True): IndexPresence.BOTH,
}


def readable_prefix(fields: Iterable[str]) -> str:
    """The human-readable half of a name, from the facts it is derived over.

    ASCII letters lowercase, digits stay, and every maximal run of anything else
    — including the boundary between two fields — becomes one underscore, which
    is then trimmed from both ends. A readable input with nothing to keep becomes
    ``index`` rather than an empty run of underscores.
    """
    kept: list[str] = []
    separated = False
    for character in " ".join(fields):
        if character.isascii() and character.isalnum():
            if separated and kept:
                kept.append("_")
            separated = False
            kept.append(character.lower())
        else:
            separated = True
    return "".join(kept) or _EMPTY_PREFIX


def _fingerprint(definition: IndexDefinition) -> str:
    """The first 128 bits of SHA-256 over the definition's versioned facts.

    Each field is length-prefixed before it is hashed, so no two distinct field
    sequences can concatenate to the same bytes — which is what makes the digest
    a function of the STRUCTURE rather than of a joined string.
    """
    entity = definition.index.entity
    fields = (
        _FINGERPRINT_VERSION,
        definition.table.name,
        entity.namespace or "",
        entity.name,
        definition.index.name,
        str(len(definition.components)),
        *(f"{component.entity.canonical}.{component.name}" for component in definition.components),
        _UNIQUE_MARKER[definition.unique],
    )
    digest = hashlib.sha256()
    for field in fields:
        encoded = field.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()[:_FINGERPRINT_HEX]


def physical_index_name(definition: IndexDefinition, dialect: Dialect) -> PhysicalIndexName:
    """``definition``'s name, shortened to fit ``dialect``'s identifier limit.

    Only the readable prefix is truncated; the fingerprint is never. The
    transliterated prefix is ASCII, so a character budget and a byte budget are
    the same budget, and the trim-and-fallback rules are re-applied afterwards so
    a shortened name never ends in the separator the cut landed on.
    """
    fingerprint = _fingerprint(definition)
    entity = definition.index.entity
    prefix = readable_prefix(
        (
            definition.table.name,
            entity.canonical,
            definition.index.name,
            _UNIQUE_MARKER[definition.unique],
        )
    )
    fixed = len(_NAMESPACE) + len(fingerprint) + 2  # the two joining underscores
    budget = max(dialect.max_identifier_bytes - fixed, 0)
    kept = prefix[:budget].strip("_") or _EMPTY_PREFIX
    return PhysicalIndexName(f"{_NAMESPACE}_{kept}_{fingerprint}")


def collision_groups(
    names: Mapping[IndexDefinition, PhysicalIndexName],
    earlier: Sequence[IndexDefinition],
    later: Sequence[IndexDefinition],
) -> tuple[CollisionGroup, ...]:
    """Every Physical Index Name two or more distinct definitions derived.

    Ordered by name; each group's definitions in canonical logical-identity
    order, each naming the endpoints it occurs in, so a report reads as a
    complete account of the clash rather than as the first pair found.
    """
    grouped: dict[PhysicalIndexName, list[IndexDefinition]] = {}
    for definition, name in names.items():
        grouped.setdefault(name, []).append(definition)
    in_earlier = frozenset(earlier)
    in_later = frozenset(later)
    return tuple(
        CollisionGroup(
            name=name,
            definitions=tuple(
                CollidingIndex(
                    table=definition.table,
                    index=definition.index,
                    components=definition.components,
                    unique=definition.unique,
                    presence=_PRESENCE[(definition in in_earlier, definition in in_later)],
                )
                for definition in sorted(
                    definitions,
                    key=lambda held: (
                        canonical_location_key(IndexLocation(held.index)),
                        held.table.name,
                    ),
                )
            ),
        )
        for name, definitions in sorted(grouped.items(), key=lambda entry: entry[0].value)
        if len(definitions) > 1
    )
