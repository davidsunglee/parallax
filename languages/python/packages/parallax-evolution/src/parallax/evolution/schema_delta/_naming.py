from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from parallax.core.dialect import Dialect, PhysicalIndexName
from parallax.core.metamodel import (
    AttributeIdentity,
    Column,
    IndexIdentity,
    IndexLocation,
    ModelLocationKey,
    Table,
    canonical_location_key,
)
from parallax.evolution.schema_delta._order import order_key
from parallax.evolution.schema_delta._physical import (
    CreateIndex,
    DropIndex,
    IndexDefinition,
    TemporalBackingIndex,
)
from parallax.evolution.schema_delta._values import (
    CollidingIndex,
    CollidingTemporalConstraint,
    CollisionGroup,
    IndexPresence,
)

__all__ = [
    "census",
    "collision_groups",
    "physical_index_name",
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
    definition: IndexDefinition | TemporalBackingIndex
    presence: IndexPresence


def census(
    earlier: Sequence[IndexDefinition],
    later: Sequence[IndexDefinition],
    dialect: Dialect,
    *,
    earlier_temporal: Sequence[TemporalBackingIndex] = (),
    later_temporal: Sequence[TemporalBackingIndex] = (),
) -> tuple[NamedIndex, ...]:
    """Every Index either endpoint defines, named once and told where it occurs.

    An Index both endpoints define is ONE entry rather than two. The facts a name
    is derived over are exactly the facts that decide whether two definitions are
    the same physical object, so a Column whose stored domain moved beneath an
    Index leaves that Index itself untouched — and two definitions still sharing
    an entry's name while differing in one of those facts are the candidate
    collision this census exists to expose.

    Comparing the definitions is also what establishes each one's intended
    lifetime, before any name-keyed plan exists: an entry present at one endpoint
    alone is the one the delta creates or drops, and one present at both is an
    object the database holds throughout.

    The Indices backing temporal primary keys and exclusions share the same
    namespace and enter under the names their Table Layouts compiled, never a
    name derived here.
    """
    entries: dict[tuple[PhysicalIndexName, _Identity], NamedIndex] = {}

    def enter(
        name: PhysicalIndexName,
        definition: IndexDefinition | TemporalBackingIndex,
        presence: IndexPresence,
    ) -> None:
        key = (name, _identity(definition))
        held = entries.get(key)
        entries[key] = NamedIndex(
            name=name,
            definition=definition,
            presence=IndexPresence.BOTH if held is not None else presence,
        )

    for definitions, temporal, presence in (
        (earlier, earlier_temporal, IndexPresence.EARLIER),
        (later, later_temporal, IndexPresence.LATER),
    ):
        for definition in definitions:
            enter(physical_index_name(definition, dialect), definition, presence)
        for backing in temporal:
            enter(backing.name, backing, presence)
    return tuple(entries.values())


type _Identity = (
    tuple[Table, IndexIdentity, tuple[AttributeIdentity, ...], bool]
    | tuple[Table, str, tuple[Column, ...]]
)


def _identity(definition: IndexDefinition | TemporalBackingIndex) -> _Identity:
    """The facts a Physical Index Name is derived over, as a comparable key."""
    if isinstance(definition, TemporalBackingIndex):
        return (definition.table, definition.kind, definition.columns)
    return (definition.table, definition.index, definition.components, definition.unique)


def collision_groups(
    census: Sequence[NamedIndex], surviving: Collection[Table]
) -> tuple[CollisionGroup, ...]:
    """Every Physical Index Name two coexisting distinct definitions derived.

    A shared name is a clash only where the database would hold both definitions
    at once during some prefix of the delta. That question is asked of the
    definitions and of the ordering rule, never of the emitted statements: a plan
    is built by telling definitions apart BY their derived names, so under a
    collision the create and the drop that would bound two lifetimes are exactly
    the statements it fails to emit. ``surviving`` is the Tables the later
    endpoint still holds, because an Index the delta does not carry a Table
    forward for is never dropped and so is present throughout.

    Ordered by name; each group's authored definitions in canonical
    logical-identity order and its temporal constraints by Table and kind,
    each naming the endpoints it occurs in, so a report reads as a complete
    account of the clash rather than as the first pair found.
    """
    grouped: dict[PhysicalIndexName, list[NamedIndex]] = {}
    for entry in census:
        grouped.setdefault(entry.name, []).append(entry)
    return tuple(
        CollisionGroup(name, *_reported(entries))
        for name, entries in sorted(grouped.items(), key=lambda entry: entry[0].value)
        if _coexist(entries, surviving)
    )


def _reported(
    entries: Sequence[NamedIndex],
) -> tuple[tuple[CollidingIndex, ...], tuple[CollidingTemporalConstraint, ...]]:
    authored: list[tuple[tuple[ModelLocationKey, str], CollidingIndex]] = []
    temporal: list[tuple[tuple[str, str], CollidingTemporalConstraint]] = []
    for entry in entries:
        definition = entry.definition
        if isinstance(definition, TemporalBackingIndex):
            temporal.append(
                (
                    (definition.table.name, definition.kind),
                    CollidingTemporalConstraint(
                        table=definition.table,
                        kind=definition.kind,
                        columns=definition.columns,
                        presence=entry.presence,
                    ),
                )
            )
        else:
            authored.append(
                (
                    (
                        canonical_location_key(IndexLocation(definition.index)),
                        definition.table.name,
                    ),
                    CollidingIndex(
                        table=definition.table,
                        index=definition.index,
                        components=definition.components,
                        unique=definition.unique,
                        presence=entry.presence,
                    ),
                )
            )
    authored.sort(key=lambda held: held[0])
    temporal.sort(key=lambda held: held[0])
    return (
        tuple(report for _, report in authored),
        tuple(report for _, report in temporal),
    )


def _coexist(entries: Sequence[NamedIndex], surviving: Collection[Table]) -> bool:
    """Whether two of these definitions are ever objects in the database at once."""
    return any(
        _overlap(one, other, surviving)
        for position, one in enumerate(entries)
        for other in entries[position + 1 :]
    )


def _overlap(one: NamedIndex, other: NamedIndex, surviving: Collection[Table]) -> bool:
    """Whether the database holds both of these definitions during some prefix.

    A definition either endpoint holds while the other does not is the only one
    whose lifetime is bounded at all, so a pair can be disjoint only when one is
    dropped and the other created — and only when the drop is emitted first. Two
    definitions the earlier endpoint both holds are already there before the first
    statement, and two the later endpoint both holds are both there after the
    last. A temporal constraint's backing Index is never dropped, so it bounds no
    lifetime and coexists with every other definition sharing its name.
    """
    dropped, created = (one, other) if one.presence is IndexPresence.EARLIER else (other, one)
    return not (
        isinstance(dropped.definition, IndexDefinition)
        and isinstance(created.definition, IndexDefinition)
        and dropped.presence is IndexPresence.EARLIER
        and created.presence is IndexPresence.LATER
        and dropped.definition.table in surviving
        and _drop_precedes_create(
            dropped.definition, dropped.name, created.definition, created.name
        )
    )


def _drop_precedes_create(
    dropped: IndexDefinition,
    dropped_name: PhysicalIndexName,
    created: IndexDefinition,
    created_name: PhysicalIndexName,
) -> bool:
    """Whether the delta's own statement order emits the drop before the create.

    The order key is a function of the Table, the operation kind, and the member
    addressed, all of which a definition carries, so the two statements can be
    ranked against each other without the plan that would emit them. Asking the
    owner of the order rather than restating it here is what keeps the two from
    drifting apart.
    """
    return order_key(DropIndex(definition=dropped, name=dropped_name, caused_by=())) < order_key(
        CreateIndex(definition=created, name=created_name, caused_by=())
    )
