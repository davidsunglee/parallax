"""Independent foundational oracles (m-metamodel): Entity identity, reference
resolution, member and primary-key structure, Index identity and components, and
the temporal endpoint-name reservation.

A frontend hands Model Formation the Entity's derived primary-key Index ahead
of its authored ones, so an authored Index bearing the derived name is simply a
second Index of one Identity. The refusal turns on the name alone: matching the
components the derivation would have produced is still authoring the
primary-key Index, and the same rule refuses two authored Indices sharing one
name.

The four temporal endpoint names belong to framework endpoints in every Entity's
top-level member namespace, whatever its Temporality Profile. Only the endpoints
the Entity's own profile derives may bear them; Value Object members are outside
the reservation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .inheritance import Family, inheritance_of
from .references import resolve_definition
from .storage_layout import derived_primary_key_index
from .temporality import TEMPORAL_MEMBERS, temporal_axes
from .value_object_resolve import RejectionError

METAMODEL_DUPLICATE_ENTITY_IDENTITY = "metamodel-duplicate-entity-identity"
METAMODEL_UNRESOLVED_ENTITY_REFERENCE = "metamodel-unresolved-entity-reference"
METAMODEL_UNRESOLVED_ATTRIBUTE_REFERENCE = "metamodel-unresolved-attribute-reference"
METAMODEL_UNRESOLVED_RELATIONSHIP_REFERENCE = "metamodel-unresolved-relationship-reference"
METAMODEL_LOCAL_MEMBER_COLLISION = "metamodel-local-member-collision"
METAMODEL_PRIMARY_KEY_MISSING = "metamodel-primary-key-missing"
METAMODEL_PRIMARY_KEY_MULTIPLE = "metamodel-primary-key-multiple"
METAMODEL_INDEX_IDENTITY_DUPLICATE = "metamodel-index-identity-duplicate"
METAMODEL_INDEX_ATTRIBUTE_MISSING = "metamodel-index-attribute-missing"
METAMODEL_INDEX_ATTRIBUTE_NOT_LOCAL = "metamodel-index-attribute-not-local"
METAMODEL_INDEX_ATTRIBUTE_DUPLICATE = "metamodel-index-attribute-duplicate"
METAMODEL_TEMPORAL_MEMBER_RESERVED = "metamodel-temporal-member-reserved"
MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        METAMODEL_DUPLICATE_ENTITY_IDENTITY,
        METAMODEL_UNRESOLVED_ENTITY_REFERENCE,
        METAMODEL_UNRESOLVED_ATTRIBUTE_REFERENCE,
        METAMODEL_UNRESOLVED_RELATIONSHIP_REFERENCE,
        METAMODEL_LOCAL_MEMBER_COLLISION,
        METAMODEL_PRIMARY_KEY_MISSING,
        METAMODEL_PRIMARY_KEY_MULTIPLE,
        METAMODEL_INDEX_IDENTITY_DUPLICATE,
        METAMODEL_INDEX_ATTRIBUTE_MISSING,
        METAMODEL_INDEX_ATTRIBUTE_NOT_LOCAL,
        METAMODEL_INDEX_ATTRIBUTE_DUPLICATE,
        METAMODEL_TEMPORAL_MEMBER_RESERVED,
    }
)

_RESERVED_TEMPORAL_NAMES: frozenset[str] = frozenset(
    endpoint.name for endpoints in TEMPORAL_MEMBERS.values() for endpoint in endpoints
)


def _identity(definition: Mapping[str, Any]) -> str:
    namespace = definition.get("namespace")
    name = definition["name"]
    return name if namespace is None else f"{namespace}.{name}"


def _index_names(definition: Mapping[str, Any]) -> list[str]:
    derived = derived_primary_key_index(definition)
    names = [] if derived is None else [str(derived["name"])]
    names.extend(
        str(declared["name"])
        for declared in definition.get("indices", []) or []
        if isinstance(declared, dict)
    )
    return names


def validate_index_identities(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a model whose Entity carries two Indices of one name."""
    for definition in entity_defs:
        if not isinstance(definition, dict):
            continue
        claimed: set[str] = set()
        for name in _index_names(definition):
            if name in claimed:
                raise RejectionError(
                    METAMODEL_INDEX_IDENTITY_DUPLICATE,
                    f"Entity {_identity(definition)} bears two Indices named {name!r}",
                )
            claimed.add(name)


def validate_temporal_member_names(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a top-level member bearing a temporal endpoint name it is not.

    ``entity_defs`` carry their derived endpoints
    (:func:`~reference_harness.temporality.derive_temporal_structure`), so an
    Attribute named after an endpoint the definition's own profile derives is that
    endpoint. An authored duplicate of one is the descriptor's own
    ``temporal-attribute-declared`` defect, outside this rule.
    """
    for definition in entity_defs:
        if not isinstance(definition, dict):
            continue
        derived = {
            endpoint.name
            for axis in temporal_axes(definition)
            for endpoint in (axis.start, axis.end)
        }
        members = [
            (str(member.get("name")), kind)
            for kind in ("attributes", "relationships", "valueObjects")
            for member in definition.get(kind, []) or []
            if isinstance(member, dict)
        ]
        for name, kind in members:
            if name not in _RESERVED_TEMPORAL_NAMES:
                continue
            if kind == "attributes" and name in derived:
                continue
            raise RejectionError(
                METAMODEL_TEMPORAL_MEMBER_RESERVED,
                f"Entity {_identity(definition)} declares {kind} member {name!r}, a name "
                f"reserved for a framework temporal endpoint",
            )


def _definitions(entity_defs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [definition for definition in entity_defs if isinstance(definition, dict)]


def _declared(definition: Mapping[str, Any], member: str) -> list[dict[str, Any]]:
    return [item for item in definition.get(member, []) or [] if isinstance(item, dict)]


def validate_entity_identities(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse two declarations resolving to one Entity Identity."""
    seen: set[str] = set()
    for definition in _definitions(entity_defs):
        identity = _identity(definition)
        if identity in seen:
            raise RejectionError(
                METAMODEL_DUPLICATE_ENTITY_IDENTITY,
                f"two Entity declarations resolve to the Identity {identity}",
            )
        seen.add(identity)


def _refuse_repeated_name(owner: str, names: list[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise RejectionError(
                METAMODEL_LOCAL_MEMBER_COLLISION,
                f"{owner} declares two local members named {name!r}",
            )
        seen.add(name)


def _validate_shape_members(owner: str, shape: Mapping[str, Any]) -> None:
    nested = _declared(shape, "valueObjects")
    _refuse_repeated_name(
        owner,
        [str(item.get("name")) for item in (*_declared(shape, "attributes"), *nested)],
    )
    for occurrence in nested:
        _validate_shape_members(f"{owner}.{occurrence.get('name')}", occurrence)


def validate_local_members(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a name two local members share in one navigable namespace.

    An Entity's Attributes, Relationships, and top-level Value Object occurrences
    share its namespace; a Value Object's scalars and nested occurrences share the
    shape's own. Redeclaring an inherited member is Inheritance's rule, not this
    one.
    """
    for definition in _definitions(entity_defs):
        identity = _identity(definition)
        _refuse_repeated_name(
            identity,
            [
                str(member.get("name"))
                for kind in ("attributes", "relationships", "valueObjects")
                for member in _declared(definition, kind)
            ],
        )
        for occurrence in _declared(definition, "valueObjects"):
            _validate_shape_members(f"{identity}.{occurrence.get('name')}", occurrence)


def _applicable_attribute_names(family: Family, definition: dict[str, Any]) -> set[str]:
    """The Attribute names declared at ``definition`` or inherited along its
    (cycle-guarded) ancestry."""
    return {
        str(attribute.get("name"))
        for ancestor in family.ancestry(family.key_of(definition))
        for attribute in _declared(family.defs[ancestor], "attributes")
    }


def _resolve_entity(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], reference: str
) -> dict[str, Any]:
    try:
        return resolve_definition(entity_defs, owner, reference)
    except KeyError:
        raise RejectionError(
            METAMODEL_UNRESOLVED_ENTITY_REFERENCE,
            f"{_identity(owner)} references Entity {reference!r}, which resolves to no "
            f"declared Entity",
        ) from None


def _refuse_unresolved_attribute(
    family: Family, target: dict[str, Any], name: str, site: str
) -> None:
    if name not in _applicable_attribute_names(family, target):
        raise RejectionError(
            METAMODEL_UNRESOLVED_ATTRIBUTE_REFERENCE,
            f"{site} names Attribute {name!r}, which {_identity(target)} neither declares "
            f"nor inherits",
        )


def validate_references(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a relationship reference that resolves to nothing.

    A defining join's target Entity and Attribute, a reverse declaration's peer
    Entity and Relationship, and each ordering term resolve here. A join's source
    is an Identity on the declaring Entity rather than a reference, so its validity
    is Relationship's rule; an inheritance parent is Inheritance's.
    """
    definitions = _definitions(entity_defs)
    family = Family(definitions)
    for owner in definitions:
        for relationship in _declared(owner, "relationships"):
            site = f"{_identity(owner)}.{relationship.get('name')}"
            join = relationship.get("join")
            if isinstance(join, dict):
                target = _resolve_entity(definitions, owner, str(join["target"]["entity"]))
                _refuse_unresolved_attribute(family, target, str(join["target"]["attribute"]), site)
            else:
                peer_entity, _, peer_name = str(relationship["reverseOf"]).rpartition(".")
                target = _resolve_entity(definitions, owner, peer_entity)
                if peer_name not in {
                    str(peer.get("name")) for peer in _declared(target, "relationships")
                }:
                    raise RejectionError(
                        METAMODEL_UNRESOLVED_RELATIONSHIP_REFERENCE,
                        f"{site} reverses {peer_name!r}, which {_identity(target)} does not "
                        f"declare",
                    )
            for term in relationship.get("orderBy", []) or []:
                _refuse_unresolved_attribute(family, target, str(term["attribute"]), site)


def validate_primary_keys(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse a standalone Entity declaring no, or more than one, primary-key
    Attribute. An inheritance participant's key is its family's rule."""
    for definition in _definitions(entity_defs):
        if inheritance_of(definition) is not None:
            continue
        keys = [
            attribute
            for attribute in _declared(definition, "attributes")
            if attribute.get("primaryKey") is True
        ]
        if not keys:
            raise RejectionError(
                METAMODEL_PRIMARY_KEY_MISSING,
                f"standalone Entity {_identity(definition)} declares no primary-key Attribute",
            )
        if len(keys) > 1:
            raise RejectionError(
                METAMODEL_PRIMARY_KEY_MULTIPLE,
                f"standalone Entity {_identity(definition)} declares {len(keys)} primary-key "
                f"Attributes",
            )


def validate_index_components(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse an authored Index component that is repeated, names no Attribute,
    or names one the Entity inherits rather than declares."""
    definitions = _definitions(entity_defs)
    family = Family(definitions)
    for definition in definitions:
        local = {str(attribute.get("name")) for attribute in _declared(definition, "attributes")}
        applicable = _applicable_attribute_names(family, definition)
        for index in _declared(definition, "indices"):
            site = f"Index {index.get('name')!r} of {_identity(definition)}"
            seen: set[str] = set()
            for component in index.get("attributes", []) or []:
                name = str(component)
                if name in seen:
                    raise RejectionError(
                        METAMODEL_INDEX_ATTRIBUTE_DUPLICATE,
                        f"{site} names Attribute {name!r} more than once",
                    )
                seen.add(name)
                if name in local:
                    continue
                if name in applicable:
                    raise RejectionError(
                        METAMODEL_INDEX_ATTRIBUTE_NOT_LOCAL,
                        f"{site} names inherited Attribute {name!r}; components are local",
                    )
                raise RejectionError(
                    METAMODEL_INDEX_ATTRIBUTE_MISSING,
                    f"{site} names {name!r}, which is no Attribute of the Entity",
                )


def validate_foundations(entity_defs: Sequence[Mapping[str, Any]]) -> None:
    """Run every foundational resolver oracle, ahead of any semantic rule set."""
    validate_entity_identities(entity_defs)
    validate_local_members(entity_defs)
    validate_references(entity_defs)
    validate_primary_keys(entity_defs)
    validate_index_identities(entity_defs)
    validate_index_components(entity_defs)
    validate_temporal_member_names(entity_defs)
