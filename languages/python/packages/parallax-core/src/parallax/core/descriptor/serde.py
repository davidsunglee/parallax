"""Descriptor serde (m-descriptor).

Hand-rolled, snake-to-camel-aware serialization between the frozen metamodel
records and the canonical ``metamodel.schema.json`` document shape. Python
record fields are snake_case; canonical descriptor keys are camelCase.

``deserialize`` reads a descriptor document (JSON- or YAML-derived) into records;
``serialize`` re-emits the **canonical minimal** form, dropping every optional
key whose value equals its schema default and normalizing ``pkGeneration`` plus
the single-vs-multi ``entity``/``entities`` form. ``canonicalize``
composes the two, giving the fixpoint the no-drift guard and round-trip tests
compare against: ``serialize(deserialize(canonical)) == canonical``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal, cast

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    UNSET,
    AsOfAxisMetadata,
    Attribute,
    DefiningRelationship,
    Entity,
    Index,
    Inheritance,
    InheritanceRole,
    Metamodel,
    Multiplicity,
    NestedValueObject,
    OrderByTerm,
    PkGenerator,
    PkStrategy,
    RelationshipCardinality,
    RelationshipDeclaration,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = ["canonicalize", "deserialize", "serialize"]

_PERSISTENCE_MODES: frozenset[str] = frozenset({"read-write", "read-only"})
_PK_STRATEGIES: frozenset[str] = frozenset({"application-assigned", "max", "sequence"})
_REL_CARDINALITIES: frozenset[str] = frozenset({"one-to-one", "many-to-one", "one-to-many"})
_VO_CARDINALITIES: frozenset[str] = frozenset({"one", "many"})
_AXES: frozenset[str] = frozenset({"validTime", "transactionTime"})
_ROLES: frozenset[str] = frozenset({"root", "abstract-subtype", "concrete-subtype"})
_STRATEGIES: frozenset[str] = frozenset({"table-per-hierarchy", "table-per-concrete-subtype"})


# --------------------------------------------------------------------------- #
# Typed extraction helpers (the descriptor document carries `object` values).  #
# --------------------------------------------------------------------------- #
def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DescriptorError(f"{where}: expected a mapping, got {type(value).__name__}")
    return cast("Mapping[str, object]", value)


def _list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise DescriptorError(f"{where}: expected a list, got {type(value).__name__}")
    return cast("list[object]", value)


def _str(m: Mapping[str, object], key: str, where: str) -> str:
    value = m.get(key)
    if not isinstance(value, str):
        raise DescriptorError(f"{where}: `{key}` must be a string")
    return value


def _opt_str(m: Mapping[str, object], key: str, where: str) -> str | None:
    value = m.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DescriptorError(f"{where}: `{key}` must be a string")
    return value


def _bool(m: Mapping[str, object], key: str, *, default: bool, where: str) -> bool:
    value = m.get(key, default)
    if not isinstance(value, bool):
        raise DescriptorError(f"{where}: `{key}` must be a boolean")
    return value


def _opt_int(m: Mapping[str, object], key: str, where: str) -> int | None:
    value = m.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise DescriptorError(f"{where}: `{key}` must be an integer")
    return value


def _enum(value: str, allowed: frozenset[str], key: str, where: str) -> str:
    if value not in allowed:
        raise DescriptorError(f"{where}: `{key}` must be one of {sorted(allowed)}, got {value!r}")
    return value


def _closed(m: Mapping[str, object], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(m) - allowed)
    if unknown:
        rendered = ", ".join(f"`{key}`" for key in unknown)
        raise DescriptorError(f"{where}: unknown properties: {rendered}")


# --------------------------------------------------------------------------- #
# Deserialize.                                                                 #
# --------------------------------------------------------------------------- #
def _pk_from(value: object, where: str) -> PkGenerator:
    if isinstance(value, str):
        wire_strategy = _enum(value, _PK_STRATEGIES, "pkGeneration", where)
        strategy = cast(
            "PkStrategy", "none" if wire_strategy == "application-assigned" else wire_strategy
        )
        return PkGenerator(strategy=strategy)
    m = _mapping(value, f"{where}.pkGeneration")
    _closed(
        m,
        frozenset({"strategy", "name", "batchSize", "initialValue", "incrementSize"}),
        f"{where}.pkGeneration",
    )
    raw = _str(m, "strategy", where)
    _enum(raw, _PK_STRATEGIES, "strategy", where)
    if raw != "sequence":
        raise DescriptorError(f"{where}: object pkGeneration requires `strategy: sequence`")
    batch_size = _opt_int(m, "batchSize", where)
    initial_value = _opt_int(m, "initialValue", where)
    increment_size = _opt_int(m, "incrementSize", where)
    return PkGenerator(
        strategy="sequence",
        sequence_name=_str(m, "name", where),
        batch_size=1 if batch_size is None else batch_size,
        initial_value=1 if initial_value is None else initial_value,
        increment_size=1 if increment_size is None else increment_size,
    )


def _attribute_from(value: object, where: str) -> Attribute:
    m = _mapping(value, where)
    _closed(
        m,
        frozenset(
            {
                "name",
                "type",
                "column",
                "primaryKey",
                "nullable",
                "maxLength",
                "readOnly",
                "optimisticLocking",
                "pkGeneration",
                "default",
            }
        ),
        where,
    )
    name = _str(m, "name", where)
    pk = m.get("pkGeneration")
    column = _opt_str(m, "column", f"{where}.{name}")
    primary_key = _bool(m, "primaryKey", default=False, where=f"{where}.{name}")
    if pk is not None and not primary_key:
        raise DescriptorError(f"{where}.{name}: `pkGeneration` requires `primaryKey: true`")
    return Attribute(
        name=name,
        type=_str(m, "type", f"{where}.{name}"),
        column=name if column is None else column,
        primary_key=primary_key,
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        max_length=_opt_int(m, "maxLength", f"{where}.{name}"),
        read_only=_bool(m, "readOnly", default=False, where=f"{where}.{name}"),
        optimistic_locking=_bool(m, "optimisticLocking", default=False, where=f"{where}.{name}"),
        pk_generator=_pk_from(pk, f"{where}.{name}") if pk is not None else None,
        default=m.get("default", UNSET),
    )


def _order_by_from(value: object, where: str) -> OrderByTerm:
    m = _mapping(value, where)
    _closed(m, frozenset({"attribute", "direction"}), where)
    direction = m.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise DescriptorError(f"{where}: `direction` must be 'asc' or 'desc'")
    return OrderByTerm(attr=_str(m, "attribute", where), direction=direction)


def _relationship_from(value: object, where: str) -> RelationshipDeclaration:
    m = _mapping(value, where)
    _closed(
        m,
        frozenset({"name", "cardinality", "join", "reverseOf", "dependent", "orderBy"}),
        where,
    )
    name = _str(m, "name", where)
    order_by_raw = m.get("orderBy")
    order_by = (
        tuple(
            _order_by_from(item, f"{where}.{name}.orderBy") for item in _list(order_by_raw, where)
        )
        if order_by_raw is not None
        else ()
    )
    reverse_of = _opt_str(m, "reverseOf", f"{where}.{name}")
    if reverse_of is not None:
        repeated = sorted(set(m) & {"cardinality", "join", "dependent"})
        if repeated:
            raise DescriptorError(
                f"{where}.{name}: reverse relationship repeats defining properties: "
                + ", ".join(f"`{key}`" for key in repeated)
            )
        if "." not in reverse_of:
            raise DescriptorError(f"{where}.{name}: `reverseOf` must name Entity.relationship")
        return ReverseRelationship(
            name=name,
            reverse_of=reverse_of,
            order_by=order_by,
        )

    cardinality = cast(
        "RelationshipCardinality",
        _enum(
            _str(m, "cardinality", f"{where}.{name}"),
            _REL_CARDINALITIES,
            "cardinality",
            where,
        ),
    )
    join = _mapping(m.get("join"), f"{where}.{name}.join")
    _closed(join, frozenset({"source", "target"}), f"{where}.{name}.join")
    target = _mapping(join.get("target"), f"{where}.{name}.join.target")
    _closed(target, frozenset({"entity", "attribute"}), f"{where}.{name}.join.target")
    source_attribute = _str(join, "source", f"{where}.{name}.join")
    target_ref = _str(target, "entity", f"{where}.{name}.join.target")
    target_attribute = _str(target, "attribute", f"{where}.{name}.join.target")
    return DefiningRelationship(
        name=name,
        cardinality=cardinality,
        join=RelationshipJoin(
            source=source_attribute,
            target=RelationshipTarget(
                entity=target_ref,
                attribute=target_attribute,
            ),
        ),
        dependent=_bool(m, "dependent", default=False, where=f"{where}.{name}"),
        order_by=order_by,
    )


def _index_from(value: object, where: str) -> Index:
    m = _mapping(value, where)
    _closed(m, frozenset({"name", "attributes", "unique"}), where)
    name = _str(m, "name", where)
    attrs = tuple(str(item) for item in _list(m.get("attributes"), f"{where}.{name}"))
    return Index(name=name, attributes=attrs, unique=_bool(m, "unique", default=False, where=where))


def _as_of_from(value: object, where: str) -> AsOfAxisMetadata:
    m = _mapping(value, where)
    _closed(m, frozenset({"dimension", "startAttribute", "endAttribute"}), where)
    dimension = _enum(_str(m, "dimension", where), _AXES, "dimension", where)
    start_attribute = _str(m, "startAttribute", where)
    end_attribute = _str(m, "endAttribute", where)
    return AsOfAxisMetadata(
        dimension=cast("Literal['validTime', 'transactionTime']", dimension),
        start_attribute=start_attribute,
        end_attribute=end_attribute,
    )


def _tag_column(value: object, where: str) -> str:
    tag = _mapping(value, f"{where}.tag")
    _closed(tag, frozenset({"column"}), f"{where}.tag")
    return _str(tag, "column", f"{where}.tag")


def _inheritance_from(value: object, where: str) -> Inheritance:
    m = _mapping(value, f"{where}.inheritance")
    _closed(m, frozenset({"strategy", "role", "parent", "tag", "tagValue"}), where)
    role = cast("InheritanceRole", _enum(_str(m, "role", where), _ROLES, "role", where))
    strategy_raw = _opt_str(m, "strategy", where)
    strategy = (
        cast(
            "Literal['table-per-hierarchy', 'table-per-concrete-subtype']",
            _enum(strategy_raw, _STRATEGIES, "strategy", where),
        )
        if strategy_raw is not None
        else None
    )
    tag = m.get("tag")
    tag_column = _tag_column(tag, where) if tag is not None else None
    return Inheritance(
        role=role,
        strategy=strategy,
        parent=_opt_str(m, "parent", where),
        tag_column=tag_column,
        tag_value=_opt_str(m, "tagValue", where),
    )


def _vo_attribute_from(value: object, where: str) -> ValueObjectAttribute:
    m = _mapping(value, where)
    _closed(m, frozenset({"name", "type", "nullable"}), where)
    name = _str(m, "name", where)
    return ValueObjectAttribute(
        name=name,
        type=_str(m, "type", f"{where}.{name}"),
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
    )


def _vo_multiplicity(m: Mapping[str, object], where: str) -> Multiplicity:
    value = m.get("multiplicity", "one")
    if not isinstance(value, str):
        raise DescriptorError(f"{where}: `multiplicity` must be a string")
    return cast(
        "Multiplicity",
        _enum(value, _VO_CARDINALITIES, "multiplicity", where),
    )


def _vo_children(
    m: Mapping[str, object], where: str
) -> tuple[tuple[ValueObjectAttribute, ...], tuple[NestedValueObject, ...]]:
    attrs_raw = m.get("attributes")
    attrs = (
        tuple(_vo_attribute_from(item, f"{where}.attributes") for item in _list(attrs_raw, where))
        if attrs_raw is not None
        else ()
    )
    nested_raw = m.get("valueObjects")
    nested = (
        tuple(_nested_vo_from(item, f"{where}.valueObjects") for item in _list(nested_raw, where))
        if nested_raw is not None
        else ()
    )
    return attrs, nested


def _nested_vo_from(value: object, where: str) -> NestedValueObject:
    m = _mapping(value, where)
    _closed(
        m,
        frozenset({"name", "nullable", "multiplicity", "attributes", "valueObjects"}),
        where,
    )
    name = _str(m, "name", where)
    attrs, nested = _vo_children(m, f"{where}.{name}")
    return NestedValueObject(
        name=name,
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        multiplicity=_vo_multiplicity(m, f"{where}.{name}"),
        attributes=attrs,
        value_objects=nested,
    )


def _value_object_from(value: object, where: str) -> ValueObject:
    m = _mapping(value, where)
    _closed(
        m,
        frozenset({"name", "column", "nullable", "multiplicity", "attributes", "valueObjects"}),
        where,
    )
    name = _str(m, "name", where)
    attrs, nested = _vo_children(m, f"{where}.{name}")
    column = _opt_str(m, "column", f"{where}.{name}")
    return ValueObject(
        name=name,
        column=None if column in (None, name) else column,
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        multiplicity=_vo_multiplicity(m, f"{where}.{name}"),
        attributes=attrs,
        value_objects=nested,
    )


def _entity_from(value: object) -> Entity:
    m = _mapping(value, "entity")
    _closed(
        m,
        frozenset(
            {
                "name",
                "namespace",
                "table",
                "persistence",
                "attributes",
                "asOfAxes",
                "relationships",
                "indices",
                "valueObjects",
                "inheritance",
            }
        ),
        "entity",
    )
    name = _str(m, "name", "entity")
    where = f"entity {name}"

    attributes = tuple(
        _attribute_from(item, f"{where}.attributes")
        for item in _list(m.get("attributes", []), where)
    )
    as_of_raw = m.get("asOfAxes")
    as_of = (
        tuple(_as_of_from(item, f"{where}.asOfAxes") for item in _list(as_of_raw, where))
        if as_of_raw is not None
        else ()
    )
    rel_raw = m.get("relationships")
    relationships = (
        tuple(_relationship_from(item, f"{where}.relationships") for item in _list(rel_raw, where))
        if rel_raw is not None
        else ()
    )
    idx_raw = m.get("indices")
    indices = (
        tuple(_index_from(item, f"{where}.indices") for item in _list(idx_raw, where))
        if idx_raw is not None
        else ()
    )
    vo_raw = m.get("valueObjects")
    value_objects = (
        tuple(_value_object_from(item, f"{where}.valueObjects") for item in _list(vo_raw, where))
        if vo_raw is not None
        else ()
    )
    inheritance = (
        _inheritance_from(m["inheritance"], where) if m.get("inheritance") is not None else None
    )
    persistence_value = m.get("persistence", "read-write")
    if not isinstance(persistence_value, str):
        raise DescriptorError(f"{where}: `persistence` must be a string")
    persistence = _enum(persistence_value, _PERSISTENCE_MODES, "persistence", where)
    mutability = "transactional" if persistence == "read-write" else "read-only"

    entity = Entity(
        name=name,
        namespace=_opt_str(m, "namespace", where),
        table=_opt_str(m, "table", where),
        mutability=mutability,
        attributes=attributes,
        as_of_axes=as_of,
        relationships=relationships,
        indices=indices,
        value_objects=value_objects,
        inheritance=inheritance,
    )
    return entity


def _resolved_relationship_entities(entities: tuple[Entity, ...]) -> tuple[Entity, ...]:
    def canonical_name(entity: Entity) -> str:
        return entity.name if entity.namespace is None else f"{entity.namespace}.{entity.name}"

    by_identity = {canonical_name(entity): entity for entity in entities}

    def resolve(owner: Entity, reference: str) -> Entity:
        identity = (
            reference
            if "." in reference
            else (reference if owner.namespace is None else f"{owner.namespace}.{reference}")
        )
        try:
            return by_identity[identity]
        except KeyError as exc:
            raise DescriptorError(
                f"entity {canonical_name(owner)!r} references unknown entity {reference!r}"
            ) from exc

    def attribute(entity: Entity, attribute_name: str) -> Attribute:
        current = entity
        seen: set[str] = set()
        while canonical_name(current) not in seen:
            seen.add(canonical_name(current))
            for candidate in current.attributes:
                if candidate.name == attribute_name:
                    return candidate
            inheritance = current.inheritance
            if inheritance is None or inheritance.parent is None:
                break
            current = resolve(current, inheritance.parent)
        raise DescriptorError(
            f"entity {canonical_name(entity)} has no applicable attribute {attribute_name!r}"
        )

    for entity in entities:
        for axis in entity.as_of_axes:
            attribute(entity, axis.start_attribute)
            attribute(entity, axis.end_attribute)

    resolved_entities: list[Entity] = []
    for entity in entities:
        resolved_relationships: list[RelationshipDeclaration] = []
        for relationship in entity.relationships:
            if isinstance(relationship, DefiningRelationship):
                target = resolve(entity, relationship.join.target.entity)
                attribute(entity, relationship.join.source)
                attribute(target, relationship.join.target.attribute)
                for term in relationship.order_by:
                    attribute(target, term.attr)
                resolved_relationships.append(
                    replace(
                        relationship,
                        join=RelationshipJoin(
                            source=relationship.join.source,
                            target=RelationshipTarget(
                                entity=canonical_name(target),
                                attribute=relationship.join.target.attribute,
                            ),
                        ),
                    )
                )
                continue

            target_ref, target_relationship = relationship.reverse_of.rsplit(".", 1)
            defining_entity = resolve(entity, target_ref)
            resolved_relationships.append(
                replace(
                    relationship,
                    reverse_of=f"{canonical_name(defining_entity)}.{target_relationship}",
                )
            )
        resolved_entities.append(
            replace(
                entity,
                relationships=tuple(resolved_relationships),
            )
        )
    resolved = tuple(resolved_entities)
    metamodel = Metamodel(entities=resolved)
    for entity in resolved:
        metamodel.relationships_for(entity)
    return resolved


def deserialize(document: Mapping[str, object]) -> Metamodel:
    """Parse a descriptor document into a :class:`Metamodel`."""
    _closed(document, frozenset({"entity", "entities"}), "descriptor")
    has_single = "entity" in document
    has_many = "entities" in document
    if has_single == has_many:
        raise DescriptorError("descriptor must declare exactly one of `entity` or `entities`")
    if has_single:
        entities = (_entity_from(document["entity"]),)
        return Metamodel(entities=_resolved_relationship_entities(entities))
    entities = tuple(_entity_from(item) for item in _list(document["entities"], "entities"))
    if not entities:
        raise DescriptorError("`entities` must not be empty")
    return Metamodel(entities=_resolved_relationship_entities(entities))


# --------------------------------------------------------------------------- #
# Serialize (canonical minimal form).                                          #
# --------------------------------------------------------------------------- #
def _pk_to_json(pk: PkGenerator) -> object:
    if pk.strategy == "none":
        return "application-assigned"
    extras: dict[str, object] = {}
    if pk.sequence_name is not None:
        extras["name"] = pk.sequence_name
    if pk.batch_size not in (None, 1):
        extras["batchSize"] = pk.batch_size
    if pk.initial_value not in (None, 1):
        extras["initialValue"] = pk.initial_value
    if pk.increment_size not in (None, 1):
        extras["incrementSize"] = pk.increment_size
    if not extras:
        return pk.strategy
    return {"strategy": pk.strategy, **extras}


def _attribute_to_json(attr: Attribute) -> dict[str, object]:
    out: dict[str, object] = {"name": attr.name, "type": attr.type}
    if attr.column != attr.name:
        out["column"] = attr.column
    if attr.primary_key:
        out["primaryKey"] = True
    if attr.nullable:
        out["nullable"] = True
    if attr.max_length is not None:
        out["maxLength"] = attr.max_length
    if attr.read_only:
        out["readOnly"] = True
    if attr.optimistic_locking:
        out["optimisticLocking"] = True
    if attr.pk_generator is not None:
        out["pkGeneration"] = _pk_to_json(attr.pk_generator)
    if attr.default is not UNSET:
        out["default"] = attr.default
    return out


def _order_by_to_json(term: OrderByTerm) -> dict[str, object]:
    out: dict[str, object] = {"attribute": term.attr}
    if term.direction != "asc":
        out["direction"] = term.direction
    return out


def _qualified_reference(reference: str, namespace: str | None) -> str:
    if "." in reference or namespace is None:
        return reference
    return f"{namespace}.{reference}"


def _relationship_to_json(rel: RelationshipDeclaration, namespace: str | None) -> dict[str, object]:
    out: dict[str, object] = {"name": rel.name}
    if isinstance(rel, ReverseRelationship):
        target_ref, target_relationship = rel.reverse_of.rsplit(".", 1)
        out["reverseOf"] = f"{_qualified_reference(target_ref, namespace)}.{target_relationship}"
    else:
        if not rel.join.source or not rel.join.target.entity or not rel.join.target.attribute:
            raise DescriptorError(f"relationship {rel.name!r} has an invalid structured join")
        target = _qualified_reference(rel.join.target.entity, namespace)
        out["cardinality"] = rel.cardinality
        out["join"] = {
            "source": rel.join.source,
            "target": {"entity": target, "attribute": rel.join.target.attribute},
        }
        if rel.dependent:
            out["dependent"] = True
    if rel.order_by:
        out["orderBy"] = [_order_by_to_json(term) for term in rel.order_by]
    return out


def _index_to_json(index: Index) -> dict[str, object]:
    out: dict[str, object] = {"name": index.name, "attributes": list(index.attributes)}
    if index.unique:
        out["unique"] = True
    return out


def _as_of_to_json(axis: AsOfAxisMetadata) -> dict[str, object]:
    return {
        "dimension": axis.dimension,
        "startAttribute": axis.start_attribute,
        "endAttribute": axis.end_attribute,
    }


def _inheritance_to_json(inh: Inheritance) -> dict[str, object]:
    out: dict[str, object] = {}
    if inh.strategy is not None:
        out["strategy"] = inh.strategy
    out["role"] = inh.role
    if inh.parent is not None:
        out["parent"] = inh.parent
    if inh.tag_column is not None:
        out["tag"] = {"column": inh.tag_column}
    if inh.tag_value is not None:
        out["tagValue"] = inh.tag_value
    return out


def _vo_attribute_to_json(attr: ValueObjectAttribute) -> dict[str, object]:
    out: dict[str, object] = {"name": attr.name, "type": attr.type}
    if attr.nullable:
        out["nullable"] = True
    return out


def _nested_vo_to_json(vo: NestedValueObject) -> dict[str, object]:
    out: dict[str, object] = {"name": vo.name}
    if vo.nullable:
        out["nullable"] = True
    if vo.multiplicity != "one":
        out["multiplicity"] = vo.multiplicity
    if vo.attributes:
        out["attributes"] = [_vo_attribute_to_json(a) for a in vo.attributes]
    if vo.value_objects:
        out["valueObjects"] = [_nested_vo_to_json(n) for n in vo.value_objects]
    return out


def _value_object_to_json(vo: ValueObject) -> dict[str, object]:
    out: dict[str, object] = {"name": vo.name}
    if vo.column is not None:
        out["column"] = vo.column
    if vo.nullable:
        out["nullable"] = True
    if vo.multiplicity != "one":
        out["multiplicity"] = vo.multiplicity
    if vo.attributes:
        out["attributes"] = [_vo_attribute_to_json(a) for a in vo.attributes]
    if vo.value_objects:
        out["valueObjects"] = [_nested_vo_to_json(n) for n in vo.value_objects]
    return out


def _entity_to_json(entity: Entity) -> dict[str, object]:
    attribute_names = {attribute.name for attribute in entity.attributes}
    for axis in entity.as_of_axes:
        missing = {
            name
            for name in (axis.start_attribute, axis.end_attribute)
            if name not in attribute_names
        }
        if missing:
            raise DescriptorError(
                f"entity {entity.name!r} has no Attribute references for {sorted(missing)!r}"
            )
    out: dict[str, object] = {"name": entity.name}
    if entity.namespace is not None:
        out["namespace"] = entity.namespace
    if entity.table is not None:
        out["table"] = entity.table
    if entity.mutability == "read-only":
        out["persistence"] = "read-only"
    if entity.attributes:
        out["attributes"] = [_attribute_to_json(a) for a in entity.attributes]
    if entity.as_of_axes:
        out["asOfAxes"] = [_as_of_to_json(a) for a in entity.as_of_axes]
    if entity.relationships:
        out["relationships"] = [
            _relationship_to_json(r, entity.namespace) for r in entity.relationships
        ]
    if entity.indices:
        out["indices"] = [_index_to_json(i) for i in entity.indices]
    if entity.value_objects:
        out["valueObjects"] = [_value_object_to_json(v) for v in entity.value_objects]
    if entity.inheritance is not None:
        out["inheritance"] = _inheritance_to_json(entity.inheritance)
    return out


def serialize(metamodel: Metamodel) -> dict[str, object]:
    """Emit the canonical minimal descriptor document for ``metamodel``."""
    if len(metamodel.entities) == 1:
        return {"entity": _entity_to_json(metamodel.entities[0])}
    return {"entities": [_entity_to_json(entity) for entity in metamodel.entities]}


def canonicalize(document: Mapping[str, object]) -> dict[str, object]:
    """The canonical minimal form of ``document`` (``serialize ∘ deserialize``)."""
    return serialize(deserialize(document))
