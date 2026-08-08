"""Metamodel records (m-descriptor).

The neutral, frozen ``slots`` dataclasses that make up a parsed model
descriptor — an in-memory instance of ``core/schemas/metamodel.schema.json``.
Every record is immutable and shareable; derived facts, such as an entity's
effective ``temporal`` classification, are computed accessors, never re-authored
fields. Physical table shape is not among them: these records stay the frontend
input a model forms from, and ``m-storage-layout`` composes the physical answer.
Within ``m-descriptor``, they are the substrate for descriptor operations; no
other behavioural scope reads them directly. The entity frontend's own adapter
and the conformance engine's
raw-descriptor seams answer structural family questions here — through
:func:`declaring_entity`, :func:`family_root_name`, and
:func:`concrete_descendant_names` — for a document that has not formed, or
never will.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from parallax.core.metamodel import TemporalDimension as CanonicalTemporalDimension
from parallax.core.metamodel import default_column_name

__all__ = [
    "TEMPORAL_DIMENSIONS",
    "UNSET",
    "AsOfAxisMetadata",
    "Attribute",
    "DefiningRelationship",
    "DocumentLayout",
    "Entity",
    "Index",
    "Inheritance",
    "InheritanceRole",
    "Layout",
    "Metamodel",
    "Multiplicity",
    "NestedValueObject",
    "OrderByTerm",
    "Persistence",
    "PkGenerator",
    "PkStrategy",
    "Relationship",
    "RelationshipCardinality",
    "RelationshipDeclaration",
    "RelationshipJoin",
    "RelationshipTarget",
    "ReverseRelationship",
    "Temporal",
    "TemporalDimension",
    "Temporality",
    "Unset",
    "ValueObject",
    "ValueObjectAttribute",
    "concrete_descendant_names",
    "declaring_entity",
    "effective_as_of_axes",
    "effective_temporal",
    "family_root_name",
]

Persistence = Literal["read-write", "read-only"]
"""The Persistence Mode an entity declares: whether Parallax accepts writes for
its family. Read Write is the semantic default a standalone entity or family
root falls back to when it declares none, so the two spellings are a declaration
and never a computed effective mode."""

Temporality = Literal["nontemporal", "transaction-time", "bitemporal"]
"""The Temporality Profile an entity declares: the temporal shape its family
carries. Every As-Of Axis, its two endpoint attributes, and their framework-fixed
columns are derived from it, so it is the only temporal fact a descriptor
spells."""

Temporal = Literal[
    "non-temporal",
    "transaction-time-only",
    "bitemporal",
]
PkStrategy = Literal["none", "max", "sequence"]
RelationshipCardinality = Literal["one-to-one", "many-to-one", "one-to-many"]
Multiplicity = Literal["one", "many"]
TemporalDimension = Literal["valid-time", "transaction-time"]
InheritanceRole = Literal["root", "abstract-subtype", "concrete-subtype"]

TEMPORAL_DIMENSIONS: Final[Mapping[CanonicalTemporalDimension, TemporalDimension]] = (
    MappingProxyType(
        {
            CanonicalTemporalDimension.VALID_TIME: "valid-time",
            CanonicalTemporalDimension.TRANSACTION_TIME: "transaction-time",
        }
    )
)
"""How a descriptor spells each canonical Temporal Dimension."""


class Unset:
    """Sentinel for an absent optional value distinct from ``None``.

    A declared default of ``None`` is a real default, so absence needs a marker
    of its own that ``None`` cannot serve as.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNSET"


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class PkGenerator:
    """A primary-key generation strategy (m-pk-gen)."""

    strategy: PkStrategy
    sequence_name: str | None = None
    batch_size: int | None = None
    initial_value: int | None = None
    increment_size: int | None = None

    @property
    def generates(self) -> bool:
        """Whether the strategy allocates a key the caller did not supply."""
        return self.strategy in ("max", "sequence")


@dataclass(frozen=True, slots=True)
class Attribute:
    """A scalar entity attribute mapped to one physical column.

    ``default`` is a declaration-frontend affordance that write validation reads
    to exempt an omitted value; the canonical descriptor has no such property, so
    it is neither parsed from nor written to a document.
    """

    name: str
    type: str
    column: str
    primary_key: bool = False
    nullable: bool = False
    max_length: int | None = None
    read_only: bool = False
    optimistic_locking: bool = False
    pk_generator: PkGenerator | None = None
    default: object = UNSET


@dataclass(frozen=True, slots=True)
class OrderByTerm:
    """One ordering term of a to-many relationship.

    ``nulls`` is the authored Null Placement, independent of ``direction``; the
    descriptor's omitted spelling normalizes to ``last`` here, so a canonical
    export omits it again.
    """

    attr: str
    direction: Literal["asc", "desc"] = "asc"
    nulls: Literal["first", "last"] = "last"


@dataclass(frozen=True, slots=True)
class RelationshipTarget:
    """The sole target of a defining relationship join."""

    entity: str
    attribute: str


@dataclass(frozen=True, slots=True)
class RelationshipJoin:
    """One structured source-to-target attribute equality."""

    source: str
    target: RelationshipTarget


@dataclass(frozen=True, slots=True)
class DefiningRelationship:
    """The declaration that owns one association's mapping facts."""

    name: str
    cardinality: RelationshipCardinality
    join: RelationshipJoin
    dependent: bool = False
    order_by: tuple[OrderByTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class ReverseRelationship:
    """A declaration that names, but does not repeat, a defining relationship."""

    name: str
    reverse_of: str
    order_by: tuple[OrderByTerm, ...] = ()


type RelationshipDeclaration = DefiningRelationship | ReverseRelationship


@dataclass(frozen=True, slots=True)
class Relationship:
    """One directional value from the compiled symmetric relationship facet.

    The target is ``join.target.entity``. ``reverse`` is the peer's local
    relationship name when the association is bidirectional. No descriptor-only
    target, foreign-key hint, reverse-pair map, or string join is retained.
    """

    name: str
    cardinality: RelationshipCardinality
    join: RelationshipJoin
    reverse: str | None = None
    dependent: bool = False
    order_by: tuple[OrderByTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class Index:
    """A physical index over one or more attributes."""

    name: str
    attributes: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class AsOfAxisMetadata:
    """One canonical temporal dimension over two declared Attributes."""

    dimension: TemporalDimension
    start_attribute: str
    end_attribute: str


@dataclass(frozen=True, slots=True)
class Inheritance:
    """An entity's position in a closed inheritance tree (m-inheritance)."""

    role: InheritanceRole
    strategy: Literal["table-per-hierarchy", "table-per-concrete-subtype"] | None = None
    parent: str | None = None
    tag_column: str | None = None
    tag_value: str | None = None


@dataclass(frozen=True, slots=True)
class ValueObjectAttribute:
    """A typed field of a value object; carries no per-field column."""

    name: str
    type: str
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class NestedValueObject:
    """A value object nested inside another; shares the top-level column."""

    name: str
    nullable: bool = False
    multiplicity: Multiplicity = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueObject:
    """A top-level embedded composite stored in one ``json`` document column."""

    name: str
    column: str | None = None
    nullable: bool = False
    multiplicity: Multiplicity = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()

    @property
    def storage_column(self) -> str:
        """The explicit column override or portable default for this occurrence."""
        return default_column_name(self.name) if self.column is None else self.column


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    """One shared Structured Column carrying the mapping's document-resident state.

    The column name is required here because the canonical descriptor always
    carries the resolved one: a frontend that supplies a conventional name the
    author omitted resolves it before export.
    """

    column: str


type Layout = DocumentLayout
"""The Storage Layout an entity declares. Conventional Columns storage has no
spelling — omitting `layout` is what selects it — so the only member is the
document form."""


@dataclass(frozen=True, slots=True)
class Entity:
    """One mapped entity: identity, attributes, temporal dimensions, and relations.

    ``persistence`` is the mode this entity *declares*, and ``None`` records that
    it declared none. The distinction is load-bearing: Persistence is family-wide
    and root-owned, so absence on a standalone entity or a family root means the
    Read Write default while absence on a descendant means inherit — and a
    descendant that declares any mode at all is invalid. Normalizing an omitted
    property to the default would erase the only evidence of that.

    ``layout`` and ``temporality`` read the same way and for the same reason:
    each is family-wide and root-owned, and ``None`` is both the root's default
    — Columns storage, Non-Temporal — and the inherit signal on a descendant.

    ``attributes`` and ``as_of_axes`` are the *derived* temporal structure once
    ``temporality`` names a profile: the two endpoint attributes per axis follow
    every authored attribute, and the axes reference them. Nothing else in the
    record distinguishes a derived member from an authored one, because past
    this point nothing needs to.
    """

    name: str
    namespace: str | None = None
    table: str | None = None
    persistence: Persistence | None = None
    layout: Layout | None = None
    temporality: Temporality | None = None
    attributes: tuple[Attribute, ...] = ()
    as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    relationships: tuple[RelationshipDeclaration, ...] = ()
    indices: tuple[Index, ...] = ()
    value_objects: tuple[ValueObject, ...] = ()
    inheritance: Inheritance | None = None

    @property
    def primary_key(self) -> tuple[Attribute, ...]:
        """The primary-key attributes in declaration order."""
        return tuple(attr for attr in self.attributes if attr.primary_key)

    @property
    def temporal(self) -> Temporal:
        """This entity's OWN LOCAL temporal classification, derived from its own
        ``temporality`` only.

        For an inheritance participant this is a **structural, non-flattening**
        view, not necessarily the family's effective one: an abstract-subtype or
        concrete-subtype legitimately declares no profile of its own even when
        its family is temporal (only the root may declare ``temporality`` —
        `m-inheritance` "Inherited members"). Every consumer that needs the
        entity's EFFECTIVE classification within its family (introspection,
        validation, write classification, …) **MUST** use
        :func:`effective_temporal` instead (`m-descriptor` "the `temporality` an
        entity declares" — ADR 0026); this property alone is not family-aware
        because a bare :class:`Entity` carries no sibling context to resolve one.
        """
        match self.temporality:
            case None | "nontemporal":
                return "non-temporal"
            case "transaction-time":
                return "transaction-time-only"
            case "bitemporal":
                return "bitemporal"

    @property
    def is_temporal(self) -> bool:
        """Whether the entity's OWN LOCAL ``temporality`` names any dimension.

        Same local/structural caveat as :attr:`temporal`: use
        :func:`effective_temporal` for an inheritance participant's
        family-effective temporality.
        """
        return self.temporal != "non-temporal"

    @property
    def canonical_name(self) -> str:
        """The exact Entity spelling used for model-wide identity and lookup."""
        return self.name if self.namespace is None else f"{self.namespace}.{self.name}"


def parent_identity(entity: Entity, parent: str | None) -> str | None:
    """The CANONICAL name a ``parent`` reference authored on ``entity`` names,
    or ``None`` when it names nothing.

    A dot-qualified reference is exact and a bare one is relative to the
    declaring entity's own namespace (`m-metamodel` "References and foundational
    resolution"). There is no model-wide unique-name fallback, so a bare parent
    never reaches a same-named entity of another namespace.
    """
    if parent is None or entity.namespace is None or "." in parent:
        return parent
    return f"{entity.namespace}.{parent}"


def declaring_entity(metamodel: Metamodel, entity: Entity) -> Entity:
    """The entity that actually DECLARES ``entity``'s primary key and temporal
    (as-of) axes: the family root for an inheritance participant — temporality,
    like the physical primary key, is a FAMILY-WIDE property declared only on
    the root and inherited unchanged by every abstract and concrete descendant
    (`m-inheritance` "Inherited members") — else ``entity`` itself.

    A pure metamodel-RECORD walk over the ``parent`` / ``role`` fields the
    descriptor already carries: never raises. An ancestry that does not resolve
    to a root (a cycle, an unresolvable parent) falls back to ``entity``
    unchanged — a deliberate "resolve to what it can reach" posture; the
    raw-descriptor family-invariant validator
    (``parallax.conformance._descriptor_family.validate``) is the sole authority
    on REJECTING a malformed family, not this lookup.
    ``m-descriptor`` MUST NOT depend on ``m-inheritance``
    (`core/spec/modules.md` §7 dependency graph), so this is the one place the
    ancestry-to-root walk is implemented; every caller needing a raw descriptor
    record's own declaring entity — the conformance engine's case-format
    write/read seams — composes with this rather than re-deriving it.

    Every step of the walk is by CANONICAL identity: each ``parent`` resolves
    under the exact/relative reference rule (:func:`parent_identity`) against
    the canonical spellings alone, and the cycle guard remembers canonical
    names. A local name may repeat across namespaces, so a bare one identifies
    neither the position reached nor the positions already visited — a family
    whose chain passes through two namespaces sharing a local name is valid, and
    treating the repeat as a revisit would report a cycle the descriptor does
    not declare.
    """
    inheritance = entity.inheritance
    if inheritance is None:
        return entity
    by_canonical = {candidate.canonical_name: candidate for candidate in metamodel.entities}
    current = entity
    seen: set[str] = set()
    while True:
        current_inheritance = current.inheritance
        if current_inheritance is None or current_inheritance.role == "root":
            return current
        ancestor = parent_identity(current, current_inheritance.parent)
        if ancestor is None or current.canonical_name in seen or ancestor not in by_canonical:
            return entity
        seen.add(current.canonical_name)
        current = by_canonical[ancestor]


def family_root_name(metamodel: Metamodel, entity: Entity) -> str | None:
    """The CANONICAL name of ``entity``'s family root, or ``None`` if it has none.

    Canonical rather than local because this value identifies a family: a local
    name may be declared in more than one namespace of one model, so two
    independent families whose roots share a bare name would otherwise answer
    with the same string and merge. ``Entity.canonical_name`` is the spelling
    that is unique model-wide, and it is also what :attr:`Metamodel.by_name`
    always keys, so the result stays a usable lookup key.

    ``None`` covers both a non-participant and a participant whose ancestry does
    not resolve to a root: :func:`declaring_entity` already falls back to
    ``entity`` itself for a malformed (cyclic or unresolvable) chain, and
    ``entity`` is then never a root, so checking the resolved role alone
    distinguishes the two without re-walking ``parent`` links.
    """
    if entity.inheritance is None:
        return None
    resolved = declaring_entity(metamodel, entity)
    if resolved.inheritance is None or resolved.inheritance.role != "root":
        return None
    return resolved.canonical_name


def _role_of(entity: Entity) -> InheritanceRole | None:
    """``entity``'s inheritance role, or ``None`` if it does not participate."""
    return None if entity.inheritance is None else entity.inheritance.role


def concrete_descendant_names(metamodel: Metamodel, position: str) -> frozenset[str]:
    """Every concrete-subtype name at or below the family position ``position``.

    The record-level spelling of a position's effective concrete-subtype set
    (`m-inheritance` "every concrete node at or below the position"), so a
    concrete node that is itself a parent contributes both itself and its
    concrete descendants. Walks the ``parent`` links a descriptor already
    carries and terminates on a malformed (cyclic) family rather than raising —
    rejecting one is the raw-descriptor validator's authority, not this walk's.
    """
    by_name: dict[str, Entity] = {}
    children: dict[str, list[str]] = {}
    for candidate in metamodel.entities:
        inheritance = candidate.inheritance
        if inheritance is None:
            continue
        by_name[candidate.name] = candidate
        if inheritance.parent is not None:
            children.setdefault(inheritance.parent, []).append(candidate.name)
    found: set[str] = set()
    seen: set[str] = set()
    pending = [position]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        candidate = by_name.get(current)
        if candidate is not None and _role_of(candidate) == "concrete-subtype":
            found.add(current)
        pending.extend(children.get(current, ()))
    return frozenset(found)


def effective_as_of_axes(metamodel: Metamodel, entity: Entity) -> tuple[AsOfAxisMetadata, ...]:
    """``entity``'s FAMILY-EFFECTIVE as-of axes: the declaring entity's own — the
    family root's, for an inheritance participant — never re-derived from a
    possibly-empty LOCAL ``as_of_axes`` (`m-descriptor` "For an
    inheritance participant…"; ADR 0026)."""
    return declaring_entity(metamodel, entity).as_of_axes


def effective_temporal(metamodel: Metamodel, entity: Entity) -> Temporal:
    """``entity``'s FAMILY-EFFECTIVE ``temporal`` classification — the one every
    consumer other than a non-flattening structural reader MUST use
    (`m-descriptor`; ADR 0026)."""
    return declaring_entity(metamodel, entity).temporal


@dataclass(frozen=True, slots=True)
class Metamodel:
    """A parsed model descriptor: one or more mapped entities."""

    entities: tuple[Entity, ...] = field(default_factory=tuple)

    @property
    def by_name(self) -> dict[str, Entity]:
        """Entities keyed by exact identity plus only unambiguous local aliases."""
        result = {entity.canonical_name: entity for entity in self.entities}
        local_counts: dict[str, int] = {}
        for entity in self.entities:
            local_counts[entity.name] = local_counts.get(entity.name, 0) + 1
        for entity in self.entities:
            if local_counts[entity.name] == 1:
                result[entity.name] = entity
        return result

    def entity(self, name: str) -> Entity:
        """The entity named ``name`` (raises ``KeyError`` when absent)."""
        return self.by_name[name]

    def relationships_for(self, entity: str | Entity) -> tuple[Relationship, ...]:
        """The compiled directional relationship values for one Entity."""
        from parallax.descriptor._relationship import relationships_for

        return relationships_for(self, entity)

    def relationship(self, entity: str | Entity, name: str) -> Relationship:
        """Resolve one compiled directional relationship value by local name."""
        for relationship in self.relationships_for(entity):
            if relationship.name == name:
                return relationship
        owner = self.entity(entity) if isinstance(entity, str) else entity
        raise KeyError(f"{owner.canonical_name}.{name}")
