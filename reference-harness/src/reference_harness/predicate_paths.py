"""Independent predicate path and scope resolution over raw descriptor entities.

A predicate path (`m-predicate`) is read from a SCOPE: the queried Entity
position, which spells its paths Entity-qualified (`Order.customer.active`); an
Entity position a scope binds — a to-many relationship's element or a
path-targeted narrowing's target — which spells them relative (`sku`); the
element a `many` value-object quantifier binds, also relative; or the scalar a
scalar-collection quantifier binds, which has no fields at all. A path follows
single value objects and to-one relationships and stops at the member it names:
a scalar field, a value object, or a relationship.

This module answers that resolution from the descriptor dictionaries a case's
model declares, independently of any language implementation, for the harness
callers that need it: the pre-SQL rejection walk, the literal preflight, and the
reference-class collection. Each failure raises the
:class:`~reference_harness.value_object_resolve.RejectionError` naming the rule
`m-case-format` assigns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .inheritance import (
    ATTRIBUTE_OUTSIDE_ACTIVE_POSITION,
    NARROW_OUTSIDE_POSITION,
    REFERENCE_AMBIGUOUS_ENTITY_NAME,
    SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
    Family,
)
from .references import split_reference
from .value_object_resolve import (
    PATH_CROSSES_MANY,
    PATH_UNKNOWN_MEMBER,
    PREDICATE_SUBJECT_OUTSIDE_SCOPE,
    RejectionError,
)

__all__ = [
    "ElementScope",
    "EntityScope",
    "FieldTerminal",
    "RelationshipTerminal",
    "ScalarScope",
    "Scope",
    "Terminal",
    "ValueObjectTerminal",
    "check_position",
    "resolve_path",
]


@dataclass(frozen=True, slots=True)
class EntityScope:
    """An Entity position: ``key`` is the declared Entity, ``position`` its
    effective concrete set here, ``bound`` whether paths are relative, and
    ``outside_rule`` the rule a broadening narrow of this position raises."""

    key: str
    position: tuple[str, ...]
    bound: bool
    outside_rule: str = NARROW_OUTSIDE_POSITION


@dataclass(frozen=True, slots=True)
class ElementScope:
    """The element a `many` value-object quantifier binds."""

    value_object: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScalarScope:
    """The scalar a scalar-collection quantifier binds."""

    attribute: dict[str, Any]


type Scope = EntityScope | ElementScope | ScalarScope


@dataclass(frozen=True, slots=True)
class FieldTerminal:
    """A scalar field — or scalar collection — a path ends on."""

    attribute: dict[str, Any]

    @property
    def kind(self) -> str:
        return "a scalar collection" if _many(self.attribute) else "a scalar field"


@dataclass(frozen=True, slots=True)
class ValueObjectTerminal:
    value_object: dict[str, Any]

    @property
    def kind(self) -> str:
        return "a many value object" if _many(self.value_object) else "a single value object"


@dataclass(frozen=True, slots=True)
class RelationshipTerminal:
    """A relationship a path ends on: ``target`` is the related Entity's key."""

    target: str
    many: bool

    @property
    def kind(self) -> str:
        return "a to-many relationship" if self.many else "a to-one relationship"


type Terminal = FieldTerminal | ValueObjectTerminal | RelationshipTerminal


def _many(member: dict[str, Any]) -> bool:
    return member.get("multiplicity", "one") == "many"


def resolve_path(family: Family, scope: Scope, path: str) -> Terminal:
    """What ``path`` names from ``scope``, or the rule its resolution violates."""
    named, members = split_reference(path)
    if isinstance(scope, ScalarScope):
        raise RejectionError(
            PREDICATE_SUBJECT_OUTSIDE_SCOPE,
            f"{path!r} names a field, but a scalar-collection quantifier binds a scalar",
        )
    if isinstance(scope, ElementScope):
        if named is not None:
            raise RejectionError(
                PREDICATE_SUBJECT_OUTSIDE_SCOPE,
                f"{path!r} is Entity-qualified inside a value-object quantifier",
            )
        return _walk_value_object(path, members, scope.value_object)
    if named is None:
        if not scope.bound:
            raise RejectionError(
                PREDICATE_SUBJECT_OUTSIDE_SCOPE,
                f"{path!r} is relative at the queried position",
            )
        return _walk_entity(family, path, members, scope.key, scope.position, named_head=False)
    if scope.bound:
        raise RejectionError(
            PREDICATE_SUBJECT_OUTSIDE_SCOPE,
            f"{path!r} is Entity-qualified inside a bound scope",
        )
    ambiguous = family.defs.ambiguous_spellings(named)
    if ambiguous:
        raise RejectionError(
            REFERENCE_AMBIGUOUS_ENTITY_NAME,
            f"{path!r}: the bare entity spelling {named!r} is shared by {list(ambiguous)}",
        )
    if named not in family.defs:
        raise RejectionError(PATH_UNKNOWN_MEMBER, f"{path!r} names no declared entity {named!r}")
    key = family.defs.canonical_key(named)
    check_position(family, key, scope.position, path)
    return _walk_entity(family, path, members, key, scope.position, named_head=True)


def check_position(family: Family, key: str, position: tuple[str, ...], reference: str) -> None:
    """Refuse a member of ``key`` addressed where ``position`` is not within it:
    inside ``key``'s own family a narrowing could remedy it, outside nothing can."""
    possessing = set(family.effective_concrete_set(key))
    if set(position) <= possessing:
        return
    root = family.root_of(key) or key
    if set(position) <= set(family.effective_concrete_set(root)):
        raise RejectionError(
            SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
            f"{reference!r} reads {key!r}, whose concrete-subtype set is {sorted(possessing)}; "
            f"the position {sorted(position)} is not narrowed within it",
        )
    raise RejectionError(
        ATTRIBUTE_OUTSIDE_ACTIVE_POSITION,
        f"{reference!r} reads {key!r}, which shares no inheritance family with the position "
        f"{sorted(position)}",
    )


def _declared(definition: dict[str, Any], kind: str, name: str) -> dict[str, Any] | None:
    for member in definition.get(kind, []) or []:
        if isinstance(member, dict) and member.get("name") == name:
            return member
    return None


def _applicable(family: Family, key: str, name: str) -> tuple[str, str, dict[str, Any]] | None:
    """The member ``name`` that ``key`` or an ancestor declares."""
    for ancestor in reversed(family.ancestry(key)):
        definition = family.defs[ancestor]
        for kind in ("attributes", "valueObjects", "relationships"):
            member = _declared(definition, kind, name)
            if member is not None:
                return ancestor, kind, member
    return None


def _family_member(
    family: Family, key: str, position: tuple[str, ...], name: str, path: str
) -> tuple[str, str, dict[str, Any]] | None:
    """The member ``name`` any Entity of ``key``'s family declares, refused
    unless that declaring Entity is within ``position``."""
    root = family.root_of(key) or key
    for candidate in family.order:
        if (family.root_of(candidate) or candidate) != root:
            continue
        definition = family.defs[candidate]
        for kind in ("attributes", "valueObjects", "relationships"):
            member = _declared(definition, kind, name)
            if member is not None:
                check_position(family, candidate, position, path)
                return candidate, kind, member
    return None


def _walk_entity(
    family: Family,
    path: str,
    members: tuple[str, ...],
    key: str,
    position: tuple[str, ...],
    *,
    named_head: bool,
) -> Terminal:
    for index, name in enumerate(members):
        last = index == len(members) - 1
        found = (
            _applicable(family, key, name)
            if named_head and index == 0
            else _family_member(family, key, position, name, path)
        )
        if found is None:
            raise RejectionError(
                PATH_UNKNOWN_MEMBER, f"{path!r}: {name!r} names no declared member of {key!r}"
            )
        declaring, kind, member = found
        if kind == "attributes":
            if not last:
                raise RejectionError(
                    PATH_UNKNOWN_MEMBER, f"{path!r}: {name!r} is a scalar but the path continues"
                )
            return FieldTerminal(member)
        if kind == "valueObjects":
            if last:
                return ValueObjectTerminal(member)
            if _many(member):
                raise _crosses(path, name)
            return _walk_value_object(path, members[index + 1 :], member)
        target, many = _relationship(family, declaring, member)
        if last:
            return RelationshipTerminal(target, many)
        if many:
            raise _crosses(path, name)
        key = target
        position = tuple(family.effective_concrete_set(target))
    raise AssertionError("a predicate path names at least one member")  # pragma: no cover


def _walk_value_object(
    path: str, members: tuple[str, ...] | list[str], container: dict[str, Any]
) -> Terminal:
    for index, name in enumerate(members):
        last = index == len(members) - 1
        attribute = _declared(container, "attributes", name)
        if attribute is not None:
            if not last:
                raise RejectionError(
                    PATH_UNKNOWN_MEMBER, f"{path!r}: {name!r} is a scalar but the path continues"
                )
            return FieldTerminal(attribute)
        nested = _declared(container, "valueObjects", name)
        if nested is None:
            raise RejectionError(
                PATH_UNKNOWN_MEMBER, f"{path!r}: {name!r} names no declared member"
            )
        if last:
            return ValueObjectTerminal(nested)
        if _many(nested):
            raise _crosses(path, name)
        container = nested
    raise AssertionError("a predicate path names at least one member")  # pragma: no cover


def _crosses(path: str, name: str) -> RejectionError:
    return RejectionError(
        PATH_CROSSES_MANY,
        f"{path!r}: {name!r} holds many objects, so the path cannot continue past it",
    )


_TARGET_MANY = {"one-to-many": True, "many-to-one": False, "one-to-one": False}
_REVERSE_MANY = {"one-to-many": False, "many-to-one": True, "one-to-one": False}


def _relationship(family: Family, declaring: str, member: dict[str, Any]) -> tuple[str, bool]:
    """The related Entity's key, and whether the direction reaches many of them."""
    join = member.get("join")
    if isinstance(join, dict):
        target = family.defs.canonical_key(join["target"]["entity"])
        return target, _TARGET_MANY[member["cardinality"]]
    owner, _, peer_name = str(member["reverseOf"]).rpartition(".")
    owner_key = family.defs.canonical_key(owner)
    peer = _declared(family.defs[owner_key], "relationships", peer_name) or {}
    return owner_key, _REVERSE_MANY[peer.get("cardinality", "one-to-one")]
