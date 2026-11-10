from __future__ import annotations

from typing import Any

from .inheritance import resolve_effective_definition
from .references import entity_identity, resolve_definition
from .value_object_resolve import RejectionError

RELATIONSHIP_JOIN_SOURCE_INVALID = "relationship-join-source-invalid"
RELATIONSHIP_JOIN_TYPE_MISMATCH = "relationship-join-type-mismatch"
RELATIONSHIP_CARDINALITY_JOIN_MISMATCH = "relationship-cardinality-join-mismatch"
RELATIONSHIP_REVERSE_INCONSISTENT = "relationship-reverse-inconsistent"
RELATIONSHIP_DEFINING_DUPLICATE = "relationship-defining-duplicate"
RELATIONSHIP_ORDER_ON_TO_ONE = "relationship-order-on-to-one"
RELATIONSHIP_ORDER_ATTRIBUTE_INVALID = "relationship-order-attribute-invalid"
MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        RELATIONSHIP_JOIN_SOURCE_INVALID,
        RELATIONSHIP_JOIN_TYPE_MISMATCH,
        RELATIONSHIP_CARDINALITY_JOIN_MISMATCH,
        RELATIONSHIP_REVERSE_INCONSISTENT,
        RELATIONSHIP_DEFINING_DUPLICATE,
        RELATIONSHIP_ORDER_ON_TO_ONE,
        RELATIONSHIP_ORDER_ATTRIBUTE_INVALID,
    }
)


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


# (source, target) multiplicity of each defining cardinality; a reverse direction
# exchanges them.
_SIDES: dict[str, tuple[str, str]] = {
    "one-to-one": ("one", "one"),
    "many-to-one": ("many", "one"),
    "one-to-many": ("one", "many"),
}


def _endpoint(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], name: str
) -> dict[str, Any] | None:
    effective = resolve_effective_definition(entity_defs, entity_identity(owner))
    return next(
        (attribute for attribute in effective.get("attributes", []) if attribute["name"] == name),
        None,
    )


def _check_order(
    entity_defs: list[dict[str, Any]],
    site: str,
    relationship: dict[str, Any],
    target: dict[str, Any],
    target_side: str,
) -> None:
    order_by = relationship.get("orderBy") or []
    for term in order_by:
        ordered = _endpoint(entity_defs, target, term["attribute"])
        if ordered is not None and ordered.get("multiplicity") == "many":
            raise RejectionError(
                RELATIONSHIP_ORDER_ATTRIBUTE_INVALID,
                f"{site}: ordering term {term['attribute']!r} names a scalar collection, "
                "which has no whole-collection ordering",
            )
    if order_by and target_side == "one":
        raise RejectionError(
            RELATIONSHIP_ORDER_ON_TO_ONE,
            f"{site}: a direction whose target Multiplicity is One declares an ordering",
        )


def _check_defining(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], relationship: dict[str, Any]
) -> None:
    site = f"{entity_identity(owner)}.{relationship['name']}"
    join = relationship["join"]
    source = _endpoint(entity_defs, owner, join["source"])
    if source is None:
        raise RejectionError(
            RELATIONSHIP_JOIN_SOURCE_INVALID,
            f"{site}: join source {join['source']!r} names no Attribute of "
            f"{entity_identity(owner)}",
        )
    target_entity = resolve_definition(entity_defs, owner, join["target"]["entity"])
    target = _endpoint(entity_defs, target_entity, join["target"]["attribute"])
    source_side, target_side = _SIDES[relationship["cardinality"]]
    keyed_one_side = (source_side == "one" and source.get("primaryKey") is True) or (
        target_side == "one" and target is not None and target.get("primaryKey") is True
    )
    if not keyed_one_side:
        raise RejectionError(
            RELATIONSHIP_CARDINALITY_JOIN_MISMATCH,
            f"{site}: no side {relationship['cardinality']} declares One is joined on its "
            "Entity's primary key",
        )
    _check_order(entity_defs, site, relationship, target_entity, target_side)


def _check_reverse(
    entity_defs: list[dict[str, Any]], owner: dict[str, Any], relationship: dict[str, Any]
) -> None:
    site = f"{entity_identity(owner)}.{relationship['name']}"
    peer_reference, _, peer_name = relationship["reverseOf"].rpartition(".")
    peer_owner = resolve_definition(entity_defs, owner, peer_reference)
    peer = next(item for item in peer_owner.get("relationships", []) if item["name"] == peer_name)
    if "join" not in peer:
        return
    defining_target = resolve_definition(entity_defs, peer_owner, peer["join"]["target"]["entity"])
    if defining_target is not owner:
        raise RejectionError(
            RELATIONSHIP_REVERSE_INCONSISTENT,
            f"{site}: its defining peer {entity_identity(peer_owner)}.{peer_name} targets "
            f"{entity_identity(defining_target)}, not {entity_identity(owner)}",
        )
    reverse_target_side, _ = _SIDES[peer["cardinality"]]
    _check_order(entity_defs, site, relationship, peer_owner, reverse_target_side)


def validate_relationship_declarations(entity_defs: list[dict[str, Any]]) -> None:
    """Judge each resolved relationship declaration's own coherence.

    Runs after the foundational resolver, so every reference here resolves. A
    reverse naming another reverse derives nothing from it and is judged no
    further.
    """
    claims: dict[tuple[int, str], str] = {}
    for owner in entity_defs:
        for relationship in owner.get("relationships", []):
            if "join" in relationship:
                _check_defining(entity_defs, owner, relationship)
                continue
            _check_reverse(entity_defs, owner, relationship)
            peer_reference, _, peer_name = relationship["reverseOf"].rpartition(".")
            claim = (id(resolve_definition(entity_defs, owner, peer_reference)), peer_name)
            site = f"{entity_identity(owner)}.{relationship['name']}"
            if claim in claims:
                raise RejectionError(
                    RELATIONSHIP_DEFINING_DUPLICATE,
                    f"{site} and {claims[claim]} both reverse {relationship['reverseOf']}",
                )
            claims[claim] = site
