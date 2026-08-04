"""Independent foundational Index-identity oracle (m-metamodel).

A frontend hands Model Formation the Entity's derived primary-key Index ahead
of its authored ones, so an authored Index bearing the derived name is simply a
second Index of one Identity. The refusal turns on the name alone: matching the
components the derivation would have produced is still authoring the
primary-key Index, and the same rule refuses two authored Indices sharing one
name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .storage_layout import derived_primary_key_index
from .value_object_resolve import RejectionError

METAMODEL_INDEX_IDENTITY_DUPLICATE = "metamodel-index-identity-duplicate"
MODEL_REJECTED_RULES: frozenset[str] = frozenset({METAMODEL_INDEX_IDENTITY_DUPLICATE})


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
