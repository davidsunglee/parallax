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

from dataclasses import dataclass, field
from typing import Final, Literal

from parallax.core.metamodel import default_column_name
from parallax.descriptor._errors import DescriptorError

__all__ = [
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

Temporal = Literal[
    "non-temporal",
    "transaction-time-only",
    "bitemporal",
]
PkStrategy = Literal["none", "max", "sequence"]
RelationshipCardinality = Literal["one-to-one", "many-to-one", "one-to-many"]
Multiplicity = Literal["one", "many"]
TemporalDimension = Literal["validTime", "transactionTime"]
InheritanceRole = Literal["root", "abstract-subtype", "concrete-subtype"]


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

    ``layout`` reads the same way and for the same reason: it is family-wide and
    root-owned, and ``None`` is both the Columns default on a root and the
    inherit signal on a descendant.
    """

    name: str
    namespace: str | None = None
    table: str | None = None
    persistence: Persistence | None = None
    layout: Layout | None = None
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
        ``as_of_axes`` only.

        For an inheritance participant this is a **structural, non-flattening**
        view, not necessarily the family's effective one: an abstract-subtype or
        concrete-subtype legitimately declares no axes of its own even when its
        family is temporal (only the root may declare ``asOfAxes`` —
        `m-inheritance` "Inherited members"). Every consumer that needs the
        entity's EFFECTIVE classification within its family (introspection,
        validation, write classification, …) **MUST** use
        :func:`effective_temporal` instead (`m-descriptor` "the `asOfAxes`
        children an entity declares" — ADR 0026); this property alone is not
        family-aware because a bare :class:`Entity` carries no sibling context to
        resolve one.
        """
        axes = {axis.dimension for axis in self.as_of_axes}
        if not axes:
            return "non-temporal"
        if axes == {"validTime", "transactionTime"}:
            return "bitemporal"
        if axes == {"transactionTime"}:
            return "transaction-time-only"
        raise DescriptorError(
            f"entity {self.canonical_name!r}: Valid-Time-Only is deferred; "
            "a validTime dimension requires transactionTime"
        )

    @property
    def is_temporal(self) -> bool:
        """Whether the entity's OWN LOCAL ``as_of_axes`` is non-empty.

        Same local/structural caveat as :attr:`temporal`: use
        :func:`effective_as_of_axes` (or ``bool(...)`` of it) for an
        inheritance participant's family-effective temporality.
        """
        return bool(self.as_of_axes)

    @property
    def canonical_name(self) -> str:
        """The exact Entity spelling used for model-wide identity and lookup."""
        return self.name if self.namespace is None else f"{self.namespace}.{self.name}"


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
    """
    inheritance = entity.inheritance
    if inheritance is None:
        return entity
    by_name = metamodel.by_name
    current = entity
    seen: set[str] = set()
    while True:
        current_inheritance = current.inheritance
        if current_inheritance is None or current_inheritance.role == "root":
            return current
        parent = current_inheritance.parent
        if parent is None or current.name in seen or parent not in by_name:
            return entity
        seen.add(current.name)
        current = by_name[parent]


def family_root_name(metamodel: Metamodel, entity: Entity) -> str | None:
    """The name of ``entity``'s family root, or ``None`` if it has none.

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
    return resolved.name


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
