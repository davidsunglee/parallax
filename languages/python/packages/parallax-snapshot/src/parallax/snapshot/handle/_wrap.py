"""``parallax.snapshot.handle._wrap`` — frozen developer-surface node wrapping
(spec §3/§4).

Private handle implementation, never re-exported through
``parallax.snapshot.handle``'s own ``__init__.py``: ``_read`` is its only
caller, and the frozen graphs it builds reach callers as ``Snapshot`` roots.

Converts one materialized neutral graph
(:class:`~parallax.snapshot.materialize.Node`) into frozen instances of the
Entity Classes the caller's own hub bound — the ``Snapshot[T]`` node vocabulary.
Construction goes through Pydantic's ``model_construct`` (skips validation —
the rows already passed through the database) plus the implementation-private
``object.__setattr__`` backdoor (spec §3's own wording) so:

- **graph-local identity is resolved HERE, at the developer-facing wrap, keyed
  by the LOGICAL identity triple** (``~parallax.snapshot.materialize.identity_key``:
  family-normalized name + primary key — coordinate-omitted, safe within one
  graph's single pin, m-snapshot-read "Graph-local identity resolution"), never
  by a neutral :class:`~parallax.snapshot.materialize.Node`'s own python
  identity. A discovery pass (:func:`_discover`) walks the WHOLE per-view forest
  once, groups every ``Node`` object by its logical key, and merges each group's
  fields into ONE union view (:func:`_merged_fields`, first-seen wins) BEFORE any
  frozen instance is built, so a diamond's later-encountered sibling's own loaded
  relationships and attribute superset are never lost (spec §3 "projections
  targeting the same key merge into one node"); the per-view ``Node.fields``
  dicts themselves are never mutated, so the wire `then.graph` rendering stays
  byte-identical;
- a relationship outside the include set is set to the private ``UNLOADED``
  sentinel, which the ``Rel`` descriptor's instance access translates into
  :class:`~parallax.core.entity.UnloadedRelationshipError`;
- a narrowed include's view lives in a private per-node mapping
  (``__parallax_narrowed__``), read by ``parallax.core.narrowed`` — never a
  regular field, since it never marks the broad relationship loaded;
- a temporal node's whole-graph :class:`~parallax.core.temporal_read.Pin` and
  its own milestone :class:`~parallax.core.temporal_read.Edge` are attached
  under the private ``__parallax_pin__`` / ``__parallax_edge__`` slots
  ``pin_of`` / ``edge_of`` already read.

Physical and relationship facts come from the accepted Metamodel and its facets:
each row's own concrete Entity resolves through ``m-metamodel`` name lookup, its
navigable relationships through the Relationship Facet, its family-effective
value objects and declaring root through the Inheritance Facet, and its concrete
Python class through the Metamodel Binding's Identity-to-Class index.

Polymorphic children materialize as their CONCRETE classes: ``familyVariant``,
when the neutral row carries it, names the concrete entity directly; a
single-resolved-position level (no ``familyVariant`` key) uses the node's OWN
``~parallax.snapshot.materialize.Node.resolved_entity`` instead. The parent's own
declared relationship target survives only as the LAST-resort default for a
defensively (test-only) hand-built ``Node`` that carries no ``resolved_entity``
at all.

Hashability is conditional, exactly per spec §3: this module does nothing
special to make a node hashable or to guard against one — a back-reference
that closes a cycle makes the derived (Pydantic frozen-model) hash
non-terminating, so such nodes are shareable but not hashable; forcing safety
here would contradict the documented contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core import inheritance, relationship
from parallax.core.entity import UNLOADED, MetamodelBinding, shape_of, wire_names_of
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import ValueObject as ValueObjectBase
from parallax.core.metamodel import (
    EntityMetadata,
    Metamodel,
    Multiplicity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import Pin, milestone_edge
from parallax.snapshot import materialize

__all__ = ["wrap_graph"]

_NARROWED_ATTR = "__parallax_narrowed__"
_PIN_ATTR = "__parallax_pin__"
_EDGE_ATTR = "__parallax_edge__"


@dataclass(frozen=True, slots=True)
class _Wrapping:
    """Everything one :func:`wrap_graph` call holds constant across its recursion.

    ``model`` and ``binding`` are one hub's two faces — the accepted metadata and
    the Identity-to-Class index it published — and only the composition root ever
    pairs them, so carrying them together is what keeps one hub's index from
    resolving classes for another hub's model. ``pin`` is the whole-graph as-of
    coordinate every temporal node reached receives; ``merged`` is the finished
    discovery pass; and ``cache`` is the graph-local identity map the recursion
    itself fills, so a logical row wraps to exactly one instance however many
    paths reach it.
    """

    model: Metamodel
    binding: MetamodelBinding | None
    pin: Pin
    merged: Mapping[object, Mapping[str, object]]
    cache: dict[object, object]

    def class_of(self, entity: EntityMetadata) -> type:
        """The Entity Class this hub bound ``entity`` to.

        Wrapping is a class-requiring capability, so a model whose hub claimed no
        class — every descriptor-backed hub — refuses here rather than earlier:
        the neutral-row read path itself needs no class.
        """
        cls = None if self.binding is None else self.binding.class_of(entity.identity)
        if cls is None:
            raise LookupError(
                f"{entity.identity.canonical!r} is bound to no Entity Class; compose a "
                "class-backed hub before wrapping a Snapshot[T] result"
            )
        return cls


def wrap_graph(
    nodes: Sequence[materialize.Node],
    root_entity: str,
    model: Metamodel,
    pin: Pin,
    binding: MetamodelBinding | None,
) -> tuple[object, ...]:
    """Wrap one materialized graph's root nodes (and, transitively, everything
    reachable through them) into frozen instances of the Entity Classes
    ``binding`` claimed, attaching the SAME whole-graph ``pin`` to every temporal
    node reached.

    ``binding`` is absent for a descriptor-backed model, which names no class at
    all; every node then fails the class lookup, because wrapping is exactly the
    capability that requires one.

    Two passes: :func:`_discover` walks the whole per-view forest once,
    grouping every distinct ``Node`` object by its logical identity key, then
    :func:`_merged_fields` unions each group's fields into the one logical view
    :func:`_wrap` actually builds a frozen instance from. The second pass carries
    its whole coordinated state in one :class:`_Wrapping`.
    """
    groups: dict[object, list[materialize.Node]] = {}
    visited: set[int] = set()
    for node in nodes:
        _discover(node, root_entity, model, visited, groups)
    wrapping = _Wrapping(
        model=model, binding=binding, pin=pin, merged=_merged_fields(groups), cache={}
    )
    return tuple(_wrap(node, root_entity, wrapping) for node in nodes)


def _concrete_entity_name(node: materialize.Node, default_entity: str) -> str:
    """``node``'s own concrete entity name: a row-carried ``familyVariant``
    names it directly (a 2+-concrete union-all position); else the assembler's
    own statically-resolved ``node.resolved_entity`` (a single-resolved-position
    table-per-concrete-subtype row, which carries no `familyVariant` at all);
    ``default_entity`` (the caller's declared relationship target / root —
    possibly abstract) survives only as the defensive fallback for a hand-built
    ``Node`` no assembler ever populated ``resolved_entity`` on."""
    variant = node.fields.get("familyVariant")
    if isinstance(variant, str):
        return variant
    return node.resolved_entity if node.resolved_entity is not None else default_entity


def _entity(model: Metamodel, name: str) -> EntityMetadata:
    metadata = entity_by_name(model, name)
    if metadata is None:  # pragma: no cover - a materialized row's concrete is always declared
        raise LookupError(f"{name!r} names no Entity of this model")
    return metadata


def _relationships(model: Metamodel, entity: EntityMetadata) -> tuple[RelationshipMetadata, ...]:
    """``entity``'s navigable relationship directions (the Relationship Facet's
    own per-Entity value): today's corpus declares relationships only on the
    non-participant owner side, so an Entity's own directions are its complete
    navigable set."""
    directions = relationship.view(model).relationships(entity.identity)
    return tuple(directions) if directions is not None else ()


def _identity_cache_key(node: materialize.Node, concrete_name: str, model: Metamodel) -> object:
    """The wrap-time dedup/merge key: the LOGICAL identity triple (family-normalized
    name + primary key) when the (resolved) entity declares one, else the
    ``Node``'s own python identity — the same defensive fallback
    ``~parallax.snapshot.materialize.identity_key`` documents for an entity
    with no declared primary key (none exists in the corpus today)."""
    return materialize.identity_key(model, concrete_name, node.fields) or id(node)


def _discover_related(
    value: object,
    default_entity: str,
    model: Metamodel,
    visited: set[int],
    groups: dict[object, list[materialize.Node]],
) -> None:
    """Discovery's own ``_wrap_related`` mirror: dispatch one relationship's
    attached value (``None`` / a to-many list / a single to-one ``Node``) into
    :func:`_discover`, never building anything."""
    if value is None:
        return
    if isinstance(value, list):
        for item in cast("list[object]", value):
            _discover(cast("materialize.Node", item), default_entity, model, visited, groups)
        return
    _discover(cast("materialize.Node", value), default_entity, model, visited, groups)


def _discover(
    node: materialize.Node,
    default_entity: str,
    model: Metamodel,
    visited: set[int],
    groups: dict[object, list[materialize.Node]],
) -> None:
    """Walk the WHOLE per-view neutral forest reachable from ``node``, grouping
    every distinct ``Node`` python object by its logical identity key (the
    merge's phase 1). ``visited`` guards a back-reference cycle (the assembler
    reuses the SAME ancestor ``Node`` object); two SIBLING levels reaching the
    same row (m-snapshot-read-001's diamond) are two DIFFERENT objects and both
    land in the group.
    """
    node_id = id(node)
    if node_id in visited:
        return
    visited.add(node_id)
    concrete_name = _concrete_entity_name(node, default_entity)
    key = _identity_cache_key(node, concrete_name, model)
    groups.setdefault(key, []).append(node)
    entity = _entity(model, concrete_name)
    for direction in _relationships(model, entity):
        rel_name = direction.identity.name
        target_name = direction.join.target.entity.name
        if rel_name in node.fields:
            _discover_related(node.fields[rel_name], target_name, model, visited, groups)
        prefix = f"{rel_name}["
        for field_key, field_value in node.fields.items():
            if field_key.startswith(prefix):
                _discover_related(field_value, target_name, model, visited, groups)


def _merged_fields(
    groups: Mapping[object, list[materialize.Node]],
) -> dict[object, dict[str, object]]:
    """One UNION field-dict per logical identity key: every field key present on
    ANY sibling ``Node`` sharing that key contributes (first-seen — discovery
    order — wins on a key more than one sibling carries, so a relationship or
    narrowed view loaded on two paths wires exactly once, never double-wired;
    m-snapshot-read: materializing the attribute/relationship superset is
    conforming). The per-view ``Node.fields`` dicts are never mutated — only
    this derived mapping feeds the frozen instance the wrap builds."""
    merged: dict[object, dict[str, object]] = {}
    for key, members in groups.items():
        fields: dict[str, object] = {}
        for member in members:
            for field_key, field_value in member.fields.items():
                fields.setdefault(field_key, field_value)
        merged[key] = fields
    return merged


def _wrap(node: materialize.Node, default_entity: str, wrapping: _Wrapping) -> object:
    model = wrapping.model
    concrete_name = _concrete_entity_name(node, default_entity)
    key = _identity_cache_key(node, concrete_name, model)
    cached = wrapping.cache.get(key)
    if cached is not None:
        return cached

    entity = _entity(model, concrete_name)
    cls = cast("type[EntityBase]", wrapping.class_of(entity))
    instance = cls.model_construct()
    wrapping.cache[key] = instance

    # The merged (logical, union) view for this key — computed once by the
    # discovery pass before any instance existed — never this node's OWN
    # (possibly narrower) per-view fields directly.
    fields = wrapping.merged.get(key, node.fields)

    names = wire_names_of(cls)
    for column, value in fields.items():
        if column == "familyVariant":
            continue
        py_name = names.column_to_py.get(column)
        if py_name is None:
            continue  # a relationship attach key, handled below
        object.__setattr__(instance, py_name, _wrap_member(value, entity, column, wrapping))

    directions = _relationships(model, entity)
    narrowed_views: dict[str, object] = {}
    for direction in directions:
        rel_name = direction.identity.name
        target_name = direction.join.target.entity.name
        py_name = names.relationship_py.get(rel_name)
        # `py_name` is only absent for a SIBLING-declared relationship this
        # concrete class's own MRO does not carry (no corpus/fixture today
        # declares one); the narrowed-view scan below still applies to it.
        if py_name is not None:  # pragma: no branch
            if rel_name in fields:
                loaded = _wrap_related(fields[rel_name], target_name, wrapping)
                object.__setattr__(instance, py_name, loaded)
            else:
                object.__setattr__(instance, py_name, UNLOADED)
        prefix = f"{rel_name}["
        for field_key, field_value in fields.items():
            if field_key.startswith(prefix):
                narrowed_views[field_key] = _wrap_related(field_value, target_name, wrapping)

    if narrowed_views:
        object.__setattr__(instance, _NARROWED_ATTR, narrowed_views)

    # A temporal inheritance participant declares its as-of axes on the family
    # root (m-inheritance "Inherited members"), never re-declares them locally
    # on a concrete descendant — the Inheritance Facet resolves the entity that
    # actually carries them (a TPH/TPCS concrete node gets its pin/edge attached
    # from the root's axes).
    declaring = _declaring(model, entity)
    if declaring.declared_as_of_axes:
        object.__setattr__(instance, _PIN_ATTR, wrapping.pin)
        object.__setattr__(instance, _EDGE_ATTR, milestone_edge(declaring, fields))

    return instance


def _declaring(model: Metamodel, entity: EntityMetadata) -> EntityMetadata:
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity
    root = model.entity(position.root)
    return entity if root is None else root


def _wrap_related(value: object, default_entity: str, wrapping: _Wrapping) -> object:
    if value is None:
        return None
    if isinstance(value, list):
        items = cast("list[object]", value)
        return tuple(
            _wrap(cast("materialize.Node", item), default_entity, wrapping) for item in items
        )
    return _wrap(cast("materialize.Node", value), default_entity, wrapping)


def _wrap_member(value: object, entity: EntityMetadata, column: str, wrapping: _Wrapping) -> object:
    """A scalar member passes through; a value-object member's decoded nested
    dict wraps into its declared ``ValueObject`` subclass (or a tuple of them,
    ``multiplicity: many``) — the SAME instances-only contract the write side
    enforces (spec §2)."""
    vo = next(
        (v for v in _family_value_objects(wrapping.model, entity) if v.storage.name == column), None
    )
    if vo is None:
        return value
    vo_class = _vo_class_for(entity, vo.identity.path[-1], wrapping)
    if vo.multiplicity is Multiplicity.MANY:
        items = cast("list[Mapping[str, object] | None]", value) if isinstance(value, list) else []
        return tuple(_wrap_vo(item, vo_class) for item in items if item is not None)
    return _wrap_vo(cast("Mapping[str, object] | None", value), vo_class)


def _family_value_objects(
    model: Metamodel, entity: EntityMetadata
) -> tuple[ValueObjectMetadata, ...]:
    view = inheritance.view(model).entity(entity.identity)
    return () if view is None else tuple(view.applicable_value_objects)


def _vo_class_for(
    entity: EntityMetadata, vo_name: str, wrapping: _Wrapping
) -> type[ValueObjectBase]:
    names = wire_names_of(wrapping.class_of(entity))
    py_name = names.name_to_py.get(vo_name)
    vo_class = None if py_name is None else names.vo_classes.get(py_name)
    if vo_class is None:
        raise LookupError(
            f"{entity.identity.name}.{vo_name}: the bound Entity Class declares no "
            "Value Object member here"
        )
    return cast("type[ValueObjectBase]", vo_class)


def _wrap_vo(document: Mapping[str, object] | None, vo_class: type[ValueObjectBase]) -> object:
    """One stored document as a frozen Value Object instance.

    Built through ``model_construct``, exactly as an Entity node is: a stored
    document is what the database holds rather than authored input, so a member
    the row omits, nulls, or stores in the wrong shape materializes as absent
    instead of failing validation — the same absence collapse every nested read
    applies. Every declared member is therefore supplied (a Many occurrence's
    non-array storage included, as the empty tuple), while ``model_fields_set``
    names only the members the document actually carried, so the omission policy
    :func:`~parallax.core.entity.to_document` applies is preserved.
    """
    if document is None:
        return None
    shape = shape_of(vo_class)
    values: dict[str, object] = {}
    present: set[str] = set()
    for canonical, py_name in shape.name_to_py.items():
        many = py_name in shape.many_py
        if canonical not in document:
            values[py_name] = () if many else None
            continue
        present.add(py_name)
        raw = document[canonical]
        nested_cls = shape.nested_classes.get(py_name)
        if nested_cls is None:
            values[py_name] = raw
        elif many:
            items = cast("list[object]", raw) if isinstance(raw, list) else []
            values[py_name] = tuple(
                _wrap_vo(cast("Mapping[str, object] | None", item), nested_cls)
                for item in items
                if item is not None
            )
        else:
            values[py_name] = _wrap_vo(cast("Mapping[str, object] | None", raw), nested_cls)
    return vo_class.model_construct(present, **values)
