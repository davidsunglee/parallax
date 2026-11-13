from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from parallax.core.internal.database_binding import (
    PhysicalSequence,
    PhysicalTable,
    ResolvedBinding,
)
from parallax.core.internal.dialect import Dialect, PhysicalIndexName
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    Column,
    EntityIdentity,
    IndexIdentity,
    IndexLocation,
    ModelLocationKey,
    canonical_location_key,
)
from parallax.evolution.internal.schema_delta._order import order_key
from parallax.evolution.internal.schema_delta._physical import (
    CreateIndex,
    DropIndex,
    IndexDefinition,
    TemporalBackingIndex,
)
from parallax.evolution.internal.schema_delta._values import (
    CollidingIndex,
    CollidingRelation,
    CollidingTemporalConstraint,
    CollisionGroup,
    IndexPresence,
)

__all__ = [
    "census",
    "collision_groups",
    "physical_index_name",
    "relation_census",
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
        definition.table.physical.name,
        entity.namespace or "",
        entity.name,
        definition.index.name,
        str(len(definition.column_attributes)),
        *(
            f"{attribute.entity.canonical}.{attribute.name}"
            for attribute in definition.column_attributes
        ),
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

    The table input is the raw resolved local table name, never its qualifier.

    Only the readable prefix is truncated; the fingerprint is never. The
    transliterated prefix is ASCII, so a character budget and a byte budget are
    the same budget, and the trim-and-fallback rules are re-applied afterwards so
    a shortened name never ends in the separator the cut landed on.
    """
    fingerprint = _fingerprint(definition)
    entity = definition.index.entity
    prefix = readable_prefix(
        (
            definition.table.physical.name,
            entity.canonical,
            definition.index.name,
            _UNIQUE_MARKER[definition.unique],
        )
    )
    fixed = len(_NAMESPACE) + len(fingerprint) + 2  # the two joining underscores
    budget = max(dialect.max_identifier_bytes - fixed, 0)
    kept = prefix[:budget].strip("_") or _EMPTY_PREFIX
    return PhysicalIndexName(f"{_NAMESPACE}_{kept}_{fingerprint}")


type NameScope = tuple[str, ...] | PhysicalTable
"""Where an index name must be unique: one qualifier's relations, or one table."""


@dataclass(frozen=True, slots=True)
class NamedIndex:
    """One physical Index definition, its derived name, the scope that name is
    unique within, and where it occurs."""

    name: PhysicalIndexName
    scope: NameScope
    definition: IndexDefinition | TemporalBackingIndex
    presence: IndexPresence


def _scope(table: PhysicalTable, dialect: Dialect) -> NameScope:
    return table.qualifier if dialect.index_name_scope == "qualifier" else table


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
    namespace and enter under the names their resolved tables derived, never a
    name derived here. Each name is scoped as ``dialect`` scopes index names.
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
            scope=_scope(definition.table.physical, dialect),
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


def relation_census(
    earlier: ResolvedBinding | None, later: ResolvedBinding, dialect: Dialect
) -> tuple[CollidingRelation, ...]:
    """Every table and sequence either endpoint places, where ``dialect`` scopes
    index names to the relation namespace of a qualifier; none where it scopes
    them to one table.

    A relation both endpoints place is one entry present at both.
    """
    if dialect.index_name_scope != "qualifier":
        return ()
    entries: dict[PhysicalTable | PhysicalSequence, IndexPresence] = {}
    for resolved, presence in ((earlier, IndexPresence.EARLIER), (later, IndexPresence.LATER)):
        if resolved is None:
            continue
        relations = (
            *(table.physical for table in resolved.tables),
            *resolved.sequences.values(),
        )
        for relation in relations:
            entries[relation] = IndexPresence.BOTH if relation in entries else presence
    return tuple(
        CollidingRelation(relation=relation, presence=presence)
        for relation, presence in entries.items()
    )


type _Identity = (
    tuple[PhysicalTable, EntityIdentity, IndexIdentity, tuple[AttributeIdentity, ...], bool]
    | tuple[PhysicalTable, EntityIdentity, str, tuple[Column, ...]]
)


def _identity(definition: IndexDefinition | TemporalBackingIndex) -> _Identity:
    """The holding physical table, its mapping owner, and the definition's own
    named facts.

    The physical table and its owner, never a declared Table name, tell holding
    Tables apart, so independent mappings stay distinct physical objects and a
    table the two endpoints place differently is two objects.
    """
    if isinstance(definition, TemporalBackingIndex):
        return (
            definition.table.physical,
            definition.mapping_owner,
            definition.kind,
            definition.columns,
        )
    return (
        definition.table.physical,
        definition.mapping_owner,
        definition.index,
        definition.column_attributes,
        definition.unique,
    )


def collision_groups(
    census: Sequence[NamedIndex],
    surviving: Collection[EntityIdentity],
    relations: Sequence[CollidingRelation] = (),
) -> tuple[CollisionGroup, ...]:
    """Every Physical Index Name two coexisting distinct definitions derived, or
    one a table or sequence of ``relations`` holds in the Index's scope.

    A shared name is a clash only where the database would hold both definitions
    at once during some prefix of the delta. That question is asked of the
    definitions and of the ordering rule, never of the emitted statements: a plan
    is built by telling definitions apart BY their derived names, so under a
    collision the create and the drop that would bound two lifetimes are exactly
    the statements it fails to emit. ``surviving`` is the Tables the later
    endpoint still holds, because an Index the delta does not carry a Table
    forward for is never dropped and so is present throughout; each surviving
    Table is named by its mapping owner.

    A relation holding a name is reported whatever either lifetime. No delta
    drops a table or touches a sequence, so the one disjoint pairing is a table
    the delta creates after dropping the Index, a reuse of a derived name this
    backstop deliberately does not tell apart from a clash.

    Ordered by name; each group's authored definitions in canonical
    logical-identity order and its temporal constraints by Table and kind,
    each naming the endpoints it occurs in, so a report reads as a complete
    account of the clash rather than as the first pair found.
    """
    grouped: dict[tuple[PhysicalIndexName, NameScope], list[NamedIndex]] = {}
    for entry in census:
        grouped.setdefault((entry.name, entry.scope), []).append(entry)
    holding: dict[NameScope, list[CollidingRelation]] = {}
    for relation in relations:
        holding.setdefault(relation.relation.qualifier, []).append(relation)
    return tuple(
        CollisionGroup(name, *_reported(entries), relations=held)
        for (name, scope), entries in sorted(
            grouped.items(), key=lambda entry: _group_key(*entry[0])
        )
        if (held := _holding(holding.get(scope, ()), name)) or _coexist(entries, surviving)
    )


def _holding(
    relations: Sequence[CollidingRelation], name: PhysicalIndexName
) -> tuple[CollidingRelation, ...]:
    return tuple(held for held in relations if held.relation.name == name.value)


def _group_key(name: PhysicalIndexName, scope: NameScope) -> tuple[str, tuple[str, ...]]:
    spelled = scope if isinstance(scope, tuple) else (*scope.qualifier, scope.name)
    return (name.value, spelled)


def _reported(
    entries: Sequence[NamedIndex],
) -> tuple[tuple[CollidingIndex, ...], tuple[CollidingTemporalConstraint, ...]]:
    authored: list[tuple[tuple[ModelLocationKey, str, tuple[str, ...]], CollidingIndex]] = []
    temporal: list[tuple[tuple[str, tuple[str, ...], str], CollidingTemporalConstraint]] = []
    for entry in entries:
        definition = entry.definition
        if isinstance(definition, TemporalBackingIndex):
            temporal.append(
                (
                    (
                        definition.table.physical.name,
                        definition.table.physical.qualifier,
                        definition.kind,
                    ),
                    CollidingTemporalConstraint(
                        table=definition.table.physical,
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
                        definition.table.physical.name,
                        definition.table.physical.qualifier,
                    ),
                    CollidingIndex(
                        table=definition.table.physical,
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


def _coexist(entries: Sequence[NamedIndex], surviving: Collection[EntityIdentity]) -> bool:
    """Whether two of these definitions are ever objects in the database at once."""
    return any(
        _overlap(one, other, surviving)
        for position, one in enumerate(entries)
        for other in entries[position + 1 :]
    )


def _overlap(one: NamedIndex, other: NamedIndex, surviving: Collection[EntityIdentity]) -> bool:
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
        and dropped.definition.mapping_owner in surviving
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
