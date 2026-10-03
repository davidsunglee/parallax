from __future__ import annotations

from typing import Any

from .inheritance import resolve_effective_definition
from .references import entity_identity, resolve_definition
from .value_object_resolve import RejectionError

RELATIONSHIP_JOIN_TYPE_MISMATCH = "relationship-join-type-mismatch"
MODEL_REJECTED_RULES: frozenset[str] = frozenset({RELATIONSHIP_JOIN_TYPE_MISMATCH})


def _endpoint_type(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], name: str
) -> str | None:
    effective = resolve_effective_definition(entity_defs, entity_identity(owner))
    return next(
        (
            attribute["type"]
            for attribute in effective.get("attributes", [])
            if attribute["name"] == name
        ),
        None,
    )


def validate_relationship_types(entity_defs: list[dict[str, Any]]) -> None:
    """Compare schema-valid defining joins after inheritance validation.

    Missing references are outside this validator's ownership and produce no type verdict.
    """
    for owner in entity_defs:
        for relationship in owner.get("relationships", []):
            join = relationship.get("join")
            if join is None:
                continue
            try:
                target = resolve_definition(entity_defs, owner, join["target"]["entity"])
            except KeyError:
                continue
            source_type = _endpoint_type(entity_defs, owner, join["source"])
            target_type = _endpoint_type(entity_defs, target, join["target"]["attribute"])
            if source_type is not None and target_type is not None and source_type != target_type:
                raise RejectionError(
                    RELATIONSHIP_JOIN_TYPE_MISMATCH,
                    f"{entity_identity(owner)}.{relationship['name']}: "
                    f"{entity_identity(owner)}.{join['source']} ({source_type}) and "
                    f"{entity_identity(target)}.{join['target']['attribute']} ({target_type}) "
                    "have unequal declared neutral types",
                )
