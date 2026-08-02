"""Canonical model identities and lexical Entity references (m-metamodel).

Every accepted reference and every facet key is one of these structured values
rather than a name string. Identities are inert: they name a model position and
say nothing about whether that position exists, which is foundational
resolution's answer.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AttributeIdentity",
    "AttributeReference",
    "EntityIdentity",
    "EntityReference",
    "ExactEntityReference",
    "IndexIdentity",
    "MemberIdentity",
    "RelationshipIdentity",
    "RelationshipReference",
    "RelativeEntityReference",
    "ValueObjectAttributeIdentity",
    "ValueObjectIdentity",
    "resolve_entity_reference",
]


@dataclass(frozen=True, slots=True)
class EntityIdentity:
    """An Entity's canonical model-wide identity.

    A namespace is either absent or nonempty, so the two spellings of "no
    namespace" cannot both exist; an empty namespace raises :class:`ValueError`.
    The name grammar (nonempty and dot-free) is a foundational resolution rule
    rather than a construction constraint, so an ill-formed declared identity
    can still locate its own issue.
    """

    namespace: str | None
    name: str

    def __post_init__(self) -> None:
        if self.namespace is not None and not self.namespace:
            raise ValueError("an Entity namespace is either absent or nonempty")

    @property
    def canonical(self) -> str:
        """The exact spelling ``<namespace>.<name>``, or ``<name>`` when ownerless."""
        return self.name if self.namespace is None else f"{self.namespace}.{self.name}"

    @property
    def sort_key(self) -> tuple[str, str]:
        """The ascending ``(namespace or "", name)`` codepoint key Entity sets enumerate by."""
        return (self.namespace or "", self.name)


@dataclass(frozen=True, slots=True)
class AttributeIdentity:
    """One Attribute of one Entity.

    ``entity`` is the Entity the Attribute is *addressed at*, which is the
    declaring Entity for a declaration and the named position for a reference
    that reaches an inherited Attribute through a descendant: a join target of
    ``{entity: Pet, attribute: ownerId}`` resolves to
    ``AttributeIdentity(Pet, "ownerId")`` even though ``ownerId`` is declared on
    ``Pet``'s ancestor. The two Identities for one inherited Attribute are
    therefore distinct values, and neither asserts where it was declared.

    An empty name raises :class:`ValueError`.
    """

    entity: EntityIdentity
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("an Attribute name is nonempty")


@dataclass(frozen=True, slots=True)
class RelationshipIdentity:
    """One Relationship declared by its source Entity; an empty name raises
    :class:`ValueError`."""

    source_entity: EntityIdentity
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Relationship name is nonempty")


@dataclass(frozen=True, slots=True)
class IndexIdentity:
    """One Index of one Entity; an empty name raises :class:`ValueError`."""

    entity: EntityIdentity
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("an Index name is nonempty")


@dataclass(frozen=True, slots=True)
class ValueObjectIdentity:
    """One Value Object occurrence, addressed by its containment path.

    A path of length one is a top-level occurrence; a longer path is a nested
    one. Reusing one shape at several paths yields several identities. An empty
    path, or one with an empty segment, raises :class:`ValueError`.
    """

    entity: EntityIdentity
    path: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("a Value Object containment path is nonempty")
        if not all(self.path):
            raise ValueError("every Value Object containment path segment is nonempty")


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeIdentity:
    """One scalar Attribute of one Value Object occurrence; an empty name raises
    :class:`ValueError`."""

    value_object: ValueObjectIdentity
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Value Object Attribute name is nonempty")


type MemberIdentity = AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity
"""The closed union of the identity types addressing one logical member.

A member is a top-level Attribute, a Value Object occurrence at any containment
depth, or a scalar field inside one. Relationships, Indices, and Temporal
Dimensions are not members in this sense and are not arms.

The union names no new identity and adds no lookup: it is the addressing
vocabulary a consumer uses to denote a member without caring where that member
is stored, and it is what ``m-storage-layout`` accepts when it answers where a
member lives. It is the successor to dotted-string member addressing — every
authored ``Entity.occurrence.field`` string denotes exactly one member identity —
without changing any serialized form, since no descriptor or operation position
accepts one as a value.
"""


@dataclass(frozen=True, slots=True)
class RelativeEntityReference:
    """A bare declaration name resolved in its declaring Entity's namespace; an
    empty name raises :class:`ValueError`."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a relative Entity reference names a nonempty Entity")


@dataclass(frozen=True, slots=True)
class ExactEntityReference:
    """An already-canonical Entity target, including an ownerless one."""

    identity: EntityIdentity


type EntityReference = RelativeEntityReference | ExactEntityReference
"""The closed reference algebra. It stores no owner, raw spelling, optional
namespace, native class, or fallback state; containment supplies the relative
scope and a qualified or class-derived target is already exact."""


@dataclass(frozen=True, slots=True)
class AttributeReference:
    """An Attribute named through an Entity Reference rather than an Identity; an
    empty name raises :class:`ValueError`."""

    entity: EntityReference
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("an Attribute reference names a nonempty Attribute")


@dataclass(frozen=True, slots=True)
class RelationshipReference:
    """A Relationship named through an Entity Reference rather than an Identity;
    an empty name raises :class:`ValueError`."""

    entity: EntityReference
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Relationship reference names a nonempty Relationship")


def resolve_entity_reference(owner: EntityIdentity, reference: EntityReference) -> EntityIdentity:
    """The Entity Identity ``reference`` denotes when declared by ``owner``.

    Purely lexical: a relative name adopts the owner's namespace and an exact
    reference passes through. There is no module-global evaluation, unique-name
    fallback, or existence check.
    """
    match reference:
        case RelativeEntityReference(name):
            return EntityIdentity(owner.namespace, name)
        case ExactEntityReference(identity):
            return identity
