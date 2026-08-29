"""Assembling a Snapshot Graph from materialized rows, and comparing it as authored.

A graph is what an instance-form read publishes: nodes keyed by declared member
name, related objects attached under the view key the hop they arrived through
owns, and Value Object occurrences carried by their owner rather than fetched
beside it. This module builds that structure from rows the levels already
materialized and compares it to ``then.graph``.

Comparison is where the result form's kinds are told apart: an entity result set
and a relationship collection are multisets, a ``many`` Value Object member's
document order is semantic, and a to-one view that reached no row holds a node
position carrying ``null`` — which equals ``null`` and nothing else, so a loaded
empty stays distinct from a node.

A milestone set states ``then.graphs`` instead of one graph, and its partition
interpretation lives here once for both the eager read that materializes a graph
per milestone and the streamed delivery that publishes each root at its own edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any

from ..case import Case, Entity, Model
from ..case_assertions import CaseFailure, multiset_matches, scalars_equal
from ..inheritance import Family, resolve_root_source_set
from . import includes, materialize


def _refuse_unpublished_roots(case: Case, root_rows: Sequence[materialize.PublishedRow]) -> None:
    """Refuse roots that did not come from the materialization seam.

    A graph node is built from what the read published, so a root that reached
    here without the derivation the seam owns would carry storage into the
    assembled graph — a raw discriminator, a branch literal, an undecoded
    document — and the comparison against ``then.graph`` would grade a physical
    row against a logical one.
    """
    if all(isinstance(row, materialize.PublishedRow) for row in root_rows):
        return
    raise CaseFailure(
        f"{case.path.name}: a Snapshot Graph is assembled from the roots a read "
        f"PUBLISHED, but these did not come through the materialization seam "
        f"(materialize_read / materialize_navigated), so they may still carry storage "
        f"the read never asked for."
    )


# --- nodes and assembly ------------------------------------------------------


def graph_node(case: Case, entity: Entity, row: dict[str, Any]) -> dict[str, Any]:
    """One materialized node keyed the way `then.graph` keys one.

    A graph leaf is keyed by the DECLARED member name (`m-case-format` *Graph
    keys*), while a read row arrives keyed by its physical column, so the
    attribute half is renamed here. Value Object occurrences and relationship
    views are already name-keyed by
    :func:`..materialize.materialize_variant_owner_node` and the assembly, and
    `familyVariant` names no declared member, so both pass through.

    Both the occurrence decode and the rename map come from the node's OWN
    concrete Entity where the row states one: an abstract-root read narrows each
    node to its variant's declared columns, two concrete siblings may spell one
    column name for two different members, and an occurrence a single concrete
    declares is invisible from the abstract position the read targeted. A
    polymorphic level that projects no variant is read at an abstract position
    that declares none of its descendants' own members, so the model's remaining
    declarations fill what that position cannot name — never overriding what it
    can.
    """
    model = case.model
    concrete = materialize.variant_entity(model, entity, row)
    node = materialize.materialize_variant_owner_node(case, entity, row)
    names = {attribute["column"]: attribute["name"] for attribute in concrete.attributes}
    for other in model.entities:
        for attribute in other.attributes:
            names.setdefault(attribute["column"], attribute["name"])
    return {names.get(key, key): value for key, value in node.items()}


def assemble_graph(
    case: Case,
    query: dict[str, Any],
    steps: list[includes.FetchStep],
    root_rows: Sequence[materialize.PublishedRow],
    children_by_step: dict[includes.HopKey, dict[Any, list[dict[str, Any]]]],
) -> dict[str, list[dict[str, Any]]]:
    """Build the root-keyed object graph following the deep-fetch paths.

    Each path is walked hop by hop; at each hop the child rows for a given parent are
    attached under the hop's VIEW KEY — the ordinary relationship name for a broad
    hop, the derived ``<rel>[<Concrete>,<Concrete>]`` for a narrowed one (m-deep-fetch).
    A path-root guard contributes no key of its own: it withholds the path's whole
    attachment from the root objects it excludes, so an unguarded object's view stays
    UNSET rather than empty — the observable difference between "no such related row"
    and "this object never participated".

    The roots are what the read PUBLISHED, so they arrive from the materialization
    seam; the child rows are the levels' own and are materialized by
    :mod:`.includes` as each level is executed.
    """
    _refuse_unpublished_roots(case, root_rows)
    root_entity = includes.deepfetch_root_entity(case.model, query)
    family = Family(case.model.entity_defs)
    root_position = includes.deepfetch_root_position(query)
    step_by_hopkey = {step.hop_key: step for step in steps}

    # Build per-view row registries keyed by primary key so a shared hop (e.g.
    # Order.items consumed by two paths) reuses the same child objects, while two
    # DISTINCT views over one relationship (a broad and a narrowed hop, or two
    # narrowed hops) keep independent node sets. Nodes key by (view, entity, pk).
    def pk_attr(entity: Entity) -> str:
        for attribute in entity.attributes:
            if attribute.get("primaryKey"):
                return attribute["name"]
        return entity.attributes[0]["name"]

    registry: dict[tuple[str, str, Any], dict[str, Any]] = {}

    def node_for(view: str, entity: Entity, raw_row: dict[str, Any]) -> dict[str, Any]:
        pk_col = includes.column_of(entity, pk_attr(entity))
        key = (view, entity.name, materialize.coerce_identity_key(raw_row[pk_col]))
        if key not in registry:
            # Instance-form graph node: decode + project each top-level value-object
            # document column into its declared composite, at EVERY level (root AND
            # child), so a VO-bearing deep-fetch child materializes its document with
            # the owner exactly as a root value-object read does (m-value-object /
            # m-sql "Read projection", slot 4).
            registry[key] = graph_node(case, entity, raw_row)
        return registry[key]

    root_nodes = [node_for("", root_entity, row) for row in root_rows]

    for path in includes.deepfetch_paths_raw(query):
        root_source = resolve_root_source_set(family, root_position, path)
        parent_nodes = root_nodes
        parent_hop: includes.HopKey | None = None
        for index, segment in enumerate(path["segments"]):
            hop = includes.resolve_hop(
                family, segment, parent=parent_hop, root_source=root_source if index == 0 else None
            )
            step = step_by_hopkey[hop.key]
            admitted = includes.guarded_parents(case, step, parent_nodes)
            bucket = children_by_step[step.hop_key]

            next_nodes: list[dict[str, Any]] = []
            for parent_node in admitted:
                # A materialized node is keyed by declared member name, so the
                # correlation member is addressed by name rather than by column.
                parent_key = materialize.coerce_identity_key(parent_node.get(step.parent_attr))
                matched = bucket.get(parent_key, [])
                child_nodes = [node_for(step.view_key, step.child_entity, row) for row in matched]
                if step.to_many:
                    parent_node[step.view_key] = child_nodes
                else:
                    parent_node[step.view_key] = child_nodes[0] if child_nodes else None
                next_nodes.extend(child_nodes)
            parent_nodes = next_nodes
            parent_hop = hop.key

    return {root_entity.name: root_nodes}


# --- comparison --------------------------------------------------------------


def graphs_equal(
    left: Mapping[str, list[Any]],
    right: Mapping[str, list[Any]],
    model: Model | None = None,
) -> bool:
    """Compare assembled graphs while preserving semantic collection order.

    Entity result sets and relationship collections are multisets. A Value
    Object occurrence with ``multiplicity: many`` is different: its authored
    document order is semantic, so its elements compare positionally. Passing
    the model enables that distinction; the model-free form remains useful for
    generic graph comparison that contains relationships only.

    A node position holds ``None`` where a to-one view is loaded and empty
    (`m-case-format`: a to-one member is a single node or null), at the top
    level as well as nested — the nodes a step's `expectGraph` states are the
    ones a to-one hop reached, so a loaded-null one arrives as a top-level
    ``None``. Null equals null and nothing else, which is what keeps
    loaded-null distinct from a node.
    """

    def equal_value(a: Any, b: Any) -> bool:
        if isinstance(a, dict) or isinstance(b, dict):
            if not isinstance(a, dict) or not isinstance(b, dict):
                return False
            if a.keys() != b.keys():
                return False
            return all(equal_value(a[key], b[key]) for key in a)

        if isinstance(a, list) or isinstance(b, list):
            if not isinstance(a, list) or not isinstance(b, list):
                return False
            return multiset_matches(a, b, equal_value)

        return scalars_equal(a, b, None)

    if model is None:
        return equal_value(left, right)

    def equal_value_object_member(a: Any, b: Any, declaration: dict[str, Any]) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
            return False
        nested_by_name = {nested["name"]: nested for nested in declaration.get("valueObjects", [])}
        return all(
            equal_value_object(a[key], b[key], nested_by_name[key])
            if key in nested_by_name
            else scalars_equal(a[key], b[key], None)
            for key in a
        )

    def equal_value_object(a: Any, b: Any, declaration: dict[str, Any]) -> bool:
        if declaration.get("multiplicity", "one") == "many":
            if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
                return False
            return all(
                equal_value_object_member(left_item, right_item, declaration)
                for left_item, right_item in zip(a, b, strict=True)
            )
        if a is None or b is None:
            return a is None and b is None
        return equal_value_object_member(a, b, declaration)

    def equal_entity_node(a: Any, b: Any, entity: Entity) -> bool:
        if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
            return False
        value_objects = {
            value_object["name"]: value_object for value_object in entity.value_objects
        }
        relationships = {
            relationship["name"]: relationship for relationship in entity.relationship_metadata
        }
        for key in a:
            if key in value_objects:
                if not equal_value_object(a[key], b[key], value_objects[key]):
                    return False
                continue

            relationship_name = key.split("[", 1)[0]
            relationship = relationships.get(relationship_name)
            if relationship is None:
                if not scalars_equal(a[key], b[key], None):
                    return False
                continue

            target = model.entity(relationship["join"]["target"]["entity"])
            if relationship["cardinality"] == "one-to-many":
                if not isinstance(a[key], list) or not isinstance(b[key], list):
                    return False
                if not multiset_matches(a[key], b[key], partial(equal_entity_node, entity=target)):
                    return False
                continue

            if a[key] is None or b[key] is None:
                if a[key] is not None or b[key] is not None:
                    return False
            elif not equal_entity_node(a[key], b[key], target):
                return False
        return True

    def equal_node_or_null(a: Any, b: Any, entity: Entity) -> bool:
        if a is None or b is None:
            return a is None and b is None
        return equal_entity_node(a, b, entity)

    if left.keys() != right.keys():
        return False
    for entity_name in left:
        entity = model.entity(entity_name)
        if not multiset_matches(
            left[entity_name], right[entity_name], partial(equal_node_or_null, entity=entity)
        ):
            return False
    return True


# --- milestone sets ----------------------------------------------------------


def assert_milestone_partition(
    case: Case,
    root_entity: Entity,
    root_rows: Sequence[dict[str, Any]],
    nodes: Sequence[dict[str, Any]],
    graph_specs: list[dict[str, Any]],
) -> None:
    """Assert ``then.graphs`` against milestone rows and the nodes built from them.

    Shared by the two ways a milestone set reaches a result: one whole read that
    materializes a graph per milestone, and one streamed delivery that publishes
    each milestone root on its own at its own edge pin. What `then.graphs` states
    is the same either way — which milestones the read reached and what each
    carries — so the partition, its disjointness, and the per-graph comparison are
    one oracle, and ``nodes`` is positionally aligned with ``root_rows``.
    """
    # An as-of attribute's from-column is the edge coordinate a pin keys on (per axis,
    # keyed by the ATTRIBUTE name the pin uses — `transaction-time` / `valid-time`).
    from_column_by_attr = {
        axis["dimension"]: axis["start_column"] for axis in root_entity.temporal_runtime_axes
    }

    # The declared graphs PARTITION the milestone set: every root row belongs to
    # EXACTLY ONE graph, so the pins must be pairwise disjoint. `owner` records which
    # graph index claimed each root-row index; a second claim on any row is a loud
    # overlap failure (this is the fundamental partition guarantee — it catches both a
    # literally-duplicate pin dict and two distinct pins that happen to match the same
    # rows). `seen_pins` additionally rejects an identical pin dict up front for a
    # sharper diagnostic than the row-overlap message.
    owner: dict[int, int] = {}
    seen_pins: dict[tuple[tuple[str, str], ...], int] = {}
    for graph_index, spec in enumerate(graph_specs):
        pin = spec["pin"]
        expected = spec["graph"]
        for attr_name in pin:
            if attr_name not in from_column_by_attr:
                raise CaseFailure(
                    f"{case.path.name}: then.graphs[{graph_index}].pin names as-of attribute "
                    f"{attr_name!r}, which {root_entity.name} does not declare "
                    f"(declared: {sorted(from_column_by_attr)})."
                )
        pin_key = tuple(sorted(pin.items()))
        if pin_key in seen_pins:
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{graph_index}] repeats the pin declared by "
                f"then.graphs[{seen_pins[pin_key]}] ({pin!r}); each milestone MUST be "
                f"edge-pinned by exactly one graph — the pins MUST be pairwise disjoint."
            )
        seen_pins[pin_key] = graph_index
        group = [
            index
            for index, row in enumerate(root_rows)
            if all(
                scalars_equal(row.get(from_column_by_attr[name]), coordinate, None)
                for name, coordinate in pin.items()
            )
        ]
        if not group:
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{graph_index}] pin {pin!r} matched no milestone "
                f"row; each declared graph MUST be edge-pinned to a real milestone's "
                f"from-instant."
            )
        overlap = [index for index in group if index in owner]
        if overlap:
            shared = [dict(root_rows[index]) for index in overlap]
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{graph_index}] (pin {pin!r}) claims milestone "
                f"row(s) already claimed by then.graphs[{owner[overlap[0]]}] — the "
                f"declared graphs MUST partition the milestone set, so every row belongs "
                f"to EXACTLY ONE graph (no overlapping pins).\n"
                f"  shared: {shared!r}"
            )
        for index in group:
            owner[index] = graph_index
        assembled = {root_entity.name: [nodes[index] for index in group]}
        if not graphs_equal(assembled, expected, case.model):
            raise CaseFailure(
                f"{case.path.name}: then.graphs[{graph_index}] (pin {pin!r}) assembled graph "
                f"!= expected.\n"
                f"  assembled: {assembled!r}\n"
                f"  expected:  {expected!r}"
            )

    if len(owner) != len(root_rows):
        stray = [row for index, row in enumerate(root_rows) if index not in owner]
        raise CaseFailure(
            f"{case.path.name}: {len(stray)} milestone row(s) matched no then.graphs "
            f"pin — every milestone MUST be edge-pinned into exactly one graph.\n"
            f"  unmatched: {stray!r}"
        )
