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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from parallax.core.dialect import Dialect, PhysicalIndexName
from parallax.core.metamodel import (
    AttributeIdentity,
    IndexIdentity,
    IndexLocation,
    Table,
    canonical_location_key,
)
from parallax.evolution.schema_delta._physical import IndexDefinition
from parallax.evolution.schema_delta._values import (
    CollidingIndex,
    CollisionGroup,
    IndexPresence,
)

__all__ = [
    "NamedIndex",
    "census",
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


@dataclass(frozen=True, slots=True)
class NamedIndex:
    """One physical Index definition, its derived name, and where it occurs."""

    name: PhysicalIndexName
    definition: IndexDefinition
    presence: IndexPresence


def census(
    earlier: Sequence[IndexDefinition],
    later: Sequence[IndexDefinition],
    dialect: Dialect,
) -> tuple[NamedIndex, ...]:
    """Every Index that exists during some prefix of the statements, named once.

    An Index both endpoints define is ONE entry rather than two. The facts a name
    is derived over are exactly the facts that decide whether two definitions are
    the same physical object, so a Column whose stored domain widened beneath an
    Index leaves that Index itself untouched — and two definitions still sharing
    an entry's name while differing in one of those facts are the collision this
    census exists to expose.
    """
    entries: dict[tuple[PhysicalIndexName, _Identity], NamedIndex] = {}
    for definitions, presence in ((earlier, IndexPresence.EARLIER), (later, IndexPresence.LATER)):
        for definition in definitions:
            name = physical_index_name(definition, dialect)
            key = (name, _identity(definition))
            held = entries.get(key)
            entries[key] = NamedIndex(
                name=name,
                definition=definition,
                presence=IndexPresence.BOTH if held is not None else presence,
            )
    return tuple(entries.values())


type _Identity = tuple[Table, IndexIdentity, tuple[AttributeIdentity, ...], bool]


def _identity(definition: IndexDefinition) -> _Identity:
    """The facts a Physical Index Name is derived over, as a comparable key."""
    return (definition.table, definition.index, definition.components, definition.unique)


def collision_groups(census: Sequence[NamedIndex]) -> tuple[CollisionGroup, ...]:
    """Every Physical Index Name two or more distinct definitions derived.

    Ordered by name; each group's definitions in canonical logical-identity
    order, each naming the endpoints it occurs in, so a report reads as a
    complete account of the clash rather than as the first pair found.
    """
    grouped: dict[PhysicalIndexName, list[NamedIndex]] = {}
    for entry in census:
        grouped.setdefault(entry.name, []).append(entry)
    return tuple(
        CollisionGroup(
            name=name,
            definitions=tuple(
                CollidingIndex(
                    table=entry.definition.table,
                    index=entry.definition.index,
                    components=entry.definition.components,
                    unique=entry.definition.unique,
                    presence=entry.presence,
                )
                for entry in sorted(
                    entries,
                    key=lambda held: (
                        canonical_location_key(IndexLocation(held.definition.index)),
                        held.definition.table.name,
                    ),
                )
            ),
        )
        for name, entries in sorted(grouped.items(), key=lambda entry: entry[0].value)
        if len(entries) > 1
    )
