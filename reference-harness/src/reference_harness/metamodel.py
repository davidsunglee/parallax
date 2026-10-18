"""Independent foundational oracles (m-metamodel): Index identity and the
temporal endpoint-name reservation.

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

from .storage_layout import derived_primary_key_index
from .temporality import TEMPORAL_MEMBERS, temporal_axes
from .value_object_resolve import RejectionError

METAMODEL_INDEX_IDENTITY_DUPLICATE = "metamodel-index-identity-duplicate"
METAMODEL_TEMPORAL_MEMBER_RESERVED = "metamodel-temporal-member-reserved"
MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {METAMODEL_INDEX_IDENTITY_DUPLICATE, METAMODEL_TEMPORAL_MEMBER_RESERVED}
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
