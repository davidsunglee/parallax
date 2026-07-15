"""``parallax.snapshot.wrap`` — frozen developer-surface node wrapping (COR-3
Phase 7 increment 6a; spec §3/§4).

Converts one materialized neutral graph
(:class:`~parallax.snapshot.materialize.Node`) into frozen instances of the
caller's own REGISTERED entity classes — the ``Snapshot[T]`` node vocabulary.
Construction goes through Pydantic's ``model_construct`` (skips validation —
the rows already passed through the database) plus the implementation-private
``object.__setattr__`` backdoor (spec §3's own wording) so:

- a back-reference cycle can be closed by reusing the already-wrapped ancestor
  instance rather than re-validating or re-building it (graph-local identity,
  keyed by the neutral :class:`~parallax.snapshot.materialize.Node`'s own
  python identity — the SAME node the assembler already deduplicated);
- a relationship outside the include set is set to the private ``UNLOADED``
  sentinel, which the ``Rel`` descriptor's instance access translates into
  :class:`~parallax.core.entity.expressions.UnloadedRelationshipError`;
- a narrowed include's view lives in a private per-node mapping
  (``__parallax_narrowed__``), read by ``parallax.core.narrowed`` — never a
  regular field, since it never marks the broad relationship loaded;
- a temporal node's whole-graph :class:`~parallax.core.temporal_read.Pin` and
  its own milestone :class:`~parallax.core.temporal_read.Edge` are attached
  under the private ``__parallax_pin__`` / ``__parallax_edge__`` slots
  ``pin_of`` / ``edge_of`` already read.

Polymorphic children materialize as their CONCRETE classes: ``familyVariant``,
when the neutral row carries it, names the concrete entity directly; a
single-resolved-position level (no ``familyVariant`` key) uses the level's own
declared/default entity — resolved here from each parent node's OWN declared
relationship, never re-derived from level bookkeeping the caller would
otherwise have to thread through.

Hashability is conditional, exactly per spec §3: this module does nothing
special to make a node hashable or to guard against one — a back-reference
that closes a cycle makes the derived (Pydantic frozen-model) hash
non-terminating, so such nodes are shareable but not hashable; forcing safety
here would contradict the documented contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core import inheritance
from parallax.core.descriptor import Entity, Metamodel, Relationship, ValueObject
from parallax.core.entity import entity_registry, wire_names_of
from parallax.core.entity.expressions import UNLOADED
from parallax.core.entity.value_object import ValueObject as ValueObjectBase
from parallax.core.entity.value_object import wire_names_of as vo_wire_names_of
from parallax.core.temporal_read import Pin, milestone_edge
from parallax.snapshot import materialize

__all__ = ["wrap_graph"]

_NARROWED_ATTR = "__parallax_narrowed__"
_PIN_ATTR = "__parallax_pin__"
_EDGE_ATTR = "__parallax_edge__"


def wrap_graph(
    nodes: Sequence[materialize.Node], root_entity: str, meta: Metamodel, pin: Pin
) -> tuple[object, ...]:
    """Wrap one materialized graph's root nodes (and, transitively, everything
    reachable through them) into frozen instances of the caller's registered
    entity classes, attaching the SAME whole-graph ``pin`` to every temporal
    node reached."""
    cache: dict[int, object] = {}
    return tuple(_wrap(node, root_entity, meta, pin, cache) for node in nodes)


def _concrete_entity_name(node: materialize.Node, default_entity: str) -> str:
    variant = node.fields.get("familyVariant")
    return variant if isinstance(variant, str) else default_entity


def _family_relationships(meta: Metamodel, entity: Entity) -> tuple[Relationship, ...]:
    """``entity``'s own declared relationships PLUS every inheritance-family
    sibling's (a TPH/TPCS family shares its root's/siblings' declared
    relationships in principle; today's corpus declares relationships only on
    the non-participant OWNER side, but this stays family-complete for any
    future participant-declared relationship)."""
    if entity.inheritance is None:
        return entity.relationships
    root = inheritance.family_root(meta, entity)
    collected: list[Relationship] = list(entity.relationships)
    for candidate in meta.entities:
        if candidate.name == entity.name or candidate.inheritance is None:
            continue
        try:
            if inheritance.family_root(meta, candidate).name == root.name:
                collected.extend(candidate.relationships)
        except ValueError:  # pragma: no cover - guards a malformed family
            continue
    return tuple(collected)


def _wrap(
    node: materialize.Node,
    default_entity: str,
    meta: Metamodel,
    pin: Pin,
    cache: dict[int, object],
) -> object:
    key = id(node)
    cached = cache.get(key)
    if cached is not None:
        return cached

    concrete_name = _concrete_entity_name(node, default_entity)
    registry = entity_registry()
    cls = registry.get(concrete_name)
    if cls is None:
        raise LookupError(
            f"{concrete_name!r} has no registered Parallax entity class; import it before "
            "wrapping a Snapshot[T] result"
        )
    entity_record = meta.entity(concrete_name)
    instance = cls.model_construct()
    cache[key] = instance

    names = wire_names_of(cls)
    for column, value in node.fields.items():
        if column == "familyVariant":
            continue
        py_name = names.column_to_py.get(column)
        if py_name is None:
            continue  # a relationship attach key, handled below
        object.__setattr__(instance, py_name, _wrap_member(value, entity_record, column, meta))

    relationships = _family_relationships(meta, entity_record)
    narrowed_views: dict[str, object] = {}
    for relationship in relationships:
        rel_name = relationship.name
        py_name = names.relationship_py.get(rel_name)
        # `py_name` is only absent for a SIBLING-declared relationship this
        # concrete class's own MRO does not carry (no corpus/fixture today
        # declares one — every relationship rides the family's non-participant
        # owner side); the narrowed-view scan below still applies to it.
        if py_name is not None:  # pragma: no branch
            if rel_name in node.fields:
                loaded = _wrap_related(
                    node.fields[rel_name], relationship.related_entity, meta, pin, cache
                )
                object.__setattr__(instance, py_name, loaded)
            else:
                object.__setattr__(instance, py_name, UNLOADED)
        prefix = f"{rel_name}["
        for field_key, field_value in node.fields.items():
            if field_key.startswith(prefix):
                narrowed_views[field_key] = _wrap_related(
                    field_value, relationship.related_entity, meta, pin, cache
                )

    if narrowed_views:
        object.__setattr__(instance, _NARROWED_ATTR, narrowed_views)

    if entity_record.as_of_attributes:
        object.__setattr__(instance, _PIN_ATTR, pin)
        object.__setattr__(instance, _EDGE_ATTR, milestone_edge(entity_record, node.fields))

    return instance


def _wrap_related(
    value: object, default_entity: str, meta: Metamodel, pin: Pin, cache: dict[int, object]
) -> object:
    if value is None:
        return None
    if isinstance(value, list):
        items = cast("list[object]", value)
        return tuple(
            _wrap(cast("materialize.Node", item), default_entity, meta, pin, cache)
            for item in items
        )
    return _wrap(cast("materialize.Node", value), default_entity, meta, pin, cache)


def _wrap_member(value: object, entity: Entity, column: str, meta: Metamodel) -> object:
    """A scalar member passes through; a value-object member's decoded nested
    dict wraps into its declared ``ValueObject`` subclass (or a tuple of them,
    ``cardinality: many``) — the SAME instances-only contract the write side
    enforces (spec §2)."""
    vo = next((v for v in _family_value_objects(meta, entity) if v.column == column), None)
    if vo is None:
        return value
    vo_class = _vo_class_for(entity, vo.name)
    if vo.cardinality == "many":
        items = cast("list[Mapping[str, object] | None]", value) if isinstance(value, list) else []
        return tuple(_wrap_vo(item, vo_class) for item in items if item is not None)
    return _wrap_vo(cast("Mapping[str, object] | None", value), vo_class)


def _family_value_objects(meta: Metamodel, entity: Entity) -> tuple[ValueObject, ...]:
    if entity.inheritance is None:
        return entity.value_objects
    root = inheritance.family_root(meta, entity)
    collected: list[ValueObject] = list(entity.value_objects)
    for candidate in meta.entities:
        if candidate.name == entity.name or candidate.inheritance is None:
            continue
        try:
            if inheritance.family_root(meta, candidate).name == root.name:
                collected.extend(candidate.value_objects)
        except ValueError:  # pragma: no cover - guards a malformed family
            continue
    return tuple(collected)


def _vo_class_for(entity: Entity, vo_name: str) -> type[ValueObjectBase]:
    registry = entity_registry()
    cls = registry.get(entity.name)
    if cls is not None:
        names = wire_names_of(cls)
        py_name = names.name_to_py.get(vo_name)
        if py_name is not None:
            vo_class = names.vo_classes.get(py_name)
            if vo_class is not None:
                return cast("type[ValueObjectBase]", vo_class)
    raise LookupError(  # pragma: no cover - guards an internally-inconsistent registry
        f"{entity.name}.{vo_name}: no registered ValueObject class for this value-object member"
    )


def _wrap_vo(document: Mapping[str, object] | None, vo_class: type[ValueObjectBase]) -> object:
    if document is None:
        return None
    names = vo_wire_names_of(vo_class)
    kwargs: dict[str, object] = {}
    for canonical, py_name in names.name_to_py.items():
        if canonical not in document:
            continue
        raw = document[canonical]
        nested_cls = names.nested_classes.get(py_name)
        if nested_cls is not None:
            if isinstance(raw, list):
                raw_items = cast("list[object]", raw)
                kwargs[py_name] = tuple(
                    _wrap_vo(cast("Mapping[str, object] | None", item), nested_cls)
                    for item in raw_items
                    if item is not None
                )
            else:
                kwargs[py_name] = _wrap_vo(cast("Mapping[str, object] | None", raw), nested_cls)
        else:
            kwargs[py_name] = raw
    return vo_class(**kwargs)
