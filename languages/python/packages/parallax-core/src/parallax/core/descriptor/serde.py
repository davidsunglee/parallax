"""Descriptor serde (m-descriptor).

Hand-rolled, snake-to-camel-aware serialization between the frozen metamodel
records and the canonical ``metamodel.schema.json`` document shape. Python
record fields are snake_case; canonical descriptor keys are camelCase.

``deserialize`` reads a descriptor document (JSON- or YAML-derived) into records;
``serialize`` re-emits the **canonical minimal** form, dropping every optional
key whose value equals its schema default and normalizing the two ``pkGenerator``
spellings and the single-vs-multi ``entity``/``entities`` form. ``canonicalize``
composes the two, giving the fixpoint the no-drift guard and round-trip tests
compare against: ``serialize(deserialize(canonical)) == canonical``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    UNSET,
    AsOfAttribute,
    Attribute,
    Axis,
    Cardinality,
    Entity,
    Index,
    Inheritance,
    InheritanceRole,
    Metamodel,
    Mutability,
    NestedValueObject,
    OrderByTerm,
    PkGenerator,
    PkStrategy,
    Relationship,
    RelationshipCardinality,
    Temporal,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = ["canonicalize", "deserialize", "serialize"]

_MUTABILITIES: frozenset[str] = frozenset({"read-only", "transactional"})
_TEMPORALS: frozenset[str] = frozenset(
    {"non-temporal", "unitemporal-processing", "unitemporal-business", "bitemporal"}
)
_PK_STRATEGIES: frozenset[str] = frozenset({"none", "max", "sequence"})
_REL_CARDINALITIES: frozenset[str] = frozenset(
    {"one-to-one", "many-to-one", "one-to-many", "many-to-many"}
)
_VO_CARDINALITIES: frozenset[str] = frozenset({"one", "many"})
_AXES: frozenset[str] = frozenset({"processing", "business"})
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


# --------------------------------------------------------------------------- #
# Deserialize.                                                                 #
# --------------------------------------------------------------------------- #
def _pk_from(value: object, where: str) -> PkGenerator:
    if isinstance(value, str):
        strategy = cast("PkStrategy", _enum(value, _PK_STRATEGIES, "pkGenerator", where))
        return PkGenerator(strategy=strategy)
    m = _mapping(value, f"{where}.pkGenerator")
    raw = _str(m, "strategy", where)
    strategy = cast("PkStrategy", _enum(raw, _PK_STRATEGIES, "strategy", where))
    return PkGenerator(
        strategy=strategy,
        sequence_name=_opt_str(m, "sequenceName", where),
        batch_size=_opt_int(m, "batchSize", where),
        initial_value=_opt_int(m, "initialValue", where),
        increment_size=_opt_int(m, "incrementSize", where),
    )


def _attribute_from(value: object, where: str) -> Attribute:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    pk = m.get("pkGenerator")
    return Attribute(
        name=name,
        type=_str(m, "type", f"{where}.{name}"),
        column=_str(m, "column", f"{where}.{name}"),
        primary_key=_bool(m, "primaryKey", default=False, where=f"{where}.{name}"),
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        max_length=_opt_int(m, "maxLength", f"{where}.{name}"),
        read_only=_bool(m, "readOnly", default=False, where=f"{where}.{name}"),
        optimistic_locking=_bool(m, "optimisticLocking", default=False, where=f"{where}.{name}"),
        pk_generator=_pk_from(pk, f"{where}.{name}") if pk is not None else None,
        default=m.get("default", UNSET),
    )


def _order_by_from(value: object, where: str) -> OrderByTerm:
    m = _mapping(value, where)
    direction = m.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise DescriptorError(f"{where}: `direction` must be 'asc' or 'desc'")
    return OrderByTerm(attr=_str(m, "attr", where), direction=direction)


def _relationship_from(value: object, where: str) -> Relationship:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    order_by_raw = m.get("orderBy")
    order_by = (
        tuple(
            _order_by_from(item, f"{where}.{name}.orderBy") for item in _list(order_by_raw, where)
        )
        if order_by_raw is not None
        else ()
    )
    cardinality = cast(
        "RelationshipCardinality",
        _enum(_str(m, "cardinality", f"{where}.{name}"), _REL_CARDINALITIES, "cardinality", where),
    )
    return Relationship(
        name=name,
        related_entity=_str(m, "relatedEntity", f"{where}.{name}"),
        cardinality=cardinality,
        join=_str(m, "join", f"{where}.{name}"),
        reverse_name=_opt_str(m, "reverseName", f"{where}.{name}"),
        dependent=_bool(m, "dependent", default=False, where=f"{where}.{name}"),
        foreign_key=_opt_str(m, "foreignKey", f"{where}.{name}"),
        order_by=order_by,
    )


def _index_from(value: object, where: str) -> Index:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    attrs = tuple(str(item) for item in _list(m.get("attributes"), f"{where}.{name}"))
    return Index(name=name, attributes=attrs, unique=_bool(m, "unique", default=False, where=where))


def _as_of_from(value: object, where: str) -> AsOfAttribute:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    axis = cast("Axis", _enum(_str(m, "axis", f"{where}.{name}"), _AXES, "axis", where))
    default = m.get("default", "now")
    if default != "now":
        raise DescriptorError(f"{where}.{name}: only `default: now` is defined")
    infinity = m.get("infinity", "infinity")
    if infinity != "infinity":
        raise DescriptorError(f"{where}.{name}: `infinity` must be 'infinity'")
    return AsOfAttribute(
        name=name,
        from_column=_str(m, "fromColumn", f"{where}.{name}"),
        to_column=_str(m, "toColumn", f"{where}.{name}"),
        axis=axis,
        to_is_inclusive=_bool(m, "toIsInclusive", default=False, where=f"{where}.{name}"),
    )


def _inheritance_from(value: object, where: str) -> Inheritance:
    m = _mapping(value, f"{where}.inheritance")
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
    tag_column = (
        _str(_mapping(tag, f"{where}.tag"), "column", f"{where}.tag") if tag is not None else None
    )
    return Inheritance(
        role=role,
        strategy=strategy,
        parent=_opt_str(m, "parent", where),
        tag_column=tag_column,
        tag_value=_opt_str(m, "tagValue", where),
    )


def _vo_attribute_from(value: object, where: str) -> ValueObjectAttribute:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    return ValueObjectAttribute(
        name=name,
        type=_str(m, "type", f"{where}.{name}"),
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
    )


def _vo_cardinality(m: Mapping[str, object], where: str) -> Cardinality:
    return cast(
        "Cardinality",
        _enum(str(m.get("cardinality", "one")), _VO_CARDINALITIES, "cardinality", where),
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
    name = _str(m, "name", where)
    attrs, nested = _vo_children(m, f"{where}.{name}")
    return NestedValueObject(
        name=name,
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        cardinality=_vo_cardinality(m, f"{where}.{name}"),
        attributes=attrs,
        value_objects=nested,
    )


def _value_object_from(value: object, where: str) -> ValueObject:
    m = _mapping(value, where)
    name = _str(m, "name", where)
    mapping = str(m.get("mapping", "json"))
    if mapping != "json":
        raise DescriptorError(f"{where}.{name}: only the `json` value-object mapping is defined")
    attrs, nested = _vo_children(m, f"{where}.{name}")
    return ValueObject(
        name=name,
        column=_str(m, "column", f"{where}.{name}"),
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        cardinality=_vo_cardinality(m, f"{where}.{name}"),
        attributes=attrs,
        value_objects=nested,
    )


def _entity_from(value: object) -> Entity:
    m = _mapping(value, "entity")
    name = _str(m, "name", "entity")
    where = f"entity {name}"

    attributes = tuple(
        _attribute_from(item, f"{where}.attributes")
        for item in _list(m.get("attributes", []), where)
    )
    as_of_raw = m.get("asOfAttributes")
    as_of = (
        tuple(_as_of_from(item, f"{where}.asOfAttributes") for item in _list(as_of_raw, where))
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
    mutability = cast(
        "Mutability",
        _enum(str(m.get("mutability", "read-only")), _MUTABILITIES, "mutability", where),
    )

    entity = Entity(
        name=name,
        namespace=_opt_str(m, "namespace", where),
        table=_opt_str(m, "table", where),
        mutability=mutability,
        attributes=attributes,
        as_of_attributes=as_of,
        relationships=relationships,
        indices=indices,
        value_objects=value_objects,
        inheritance=inheritance,
    )
    authored = m.get("temporal")
    if authored is not None:
        _enum(str(authored), _TEMPORALS, "temporal", where)
        if authored != entity.temporal:
            raise DescriptorError(
                f"{where}: declared temporal {authored!r} disagrees with the as-of axes "
                f"(derived {entity.temporal!r})"
            )
    return entity


def deserialize(document: Mapping[str, object]) -> Metamodel:
    """Parse a descriptor document into a :class:`Metamodel`."""
    has_single = "entity" in document
    has_many = "entities" in document
    if has_single == has_many:
        raise DescriptorError("descriptor must declare exactly one of `entity` or `entities`")
    if has_single:
        return Metamodel(entities=(_entity_from(document["entity"]),))
    entities = tuple(_entity_from(item) for item in _list(document["entities"], "entities"))
    if not entities:
        raise DescriptorError("`entities` must not be empty")
    return Metamodel(entities=entities)


# --------------------------------------------------------------------------- #
# Serialize (canonical minimal form).                                          #
# --------------------------------------------------------------------------- #
def _pk_to_json(pk: PkGenerator) -> object:
    extras: dict[str, object] = {}
    if pk.sequence_name is not None:
        extras["sequenceName"] = pk.sequence_name
    if pk.batch_size is not None:
        extras["batchSize"] = pk.batch_size
    if pk.initial_value is not None:
        extras["initialValue"] = pk.initial_value
    if pk.increment_size is not None:
        extras["incrementSize"] = pk.increment_size
    if not extras:
        return pk.strategy
    return {"strategy": pk.strategy, **extras}


def _attribute_to_json(attr: Attribute) -> dict[str, object]:
    out: dict[str, object] = {"name": attr.name, "type": attr.type, "column": attr.column}
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
        out["pkGenerator"] = _pk_to_json(attr.pk_generator)
    if attr.default is not UNSET:
        out["default"] = attr.default
    return out


def _order_by_to_json(term: OrderByTerm) -> dict[str, object]:
    out: dict[str, object] = {"attr": term.attr}
    if term.direction != "asc":
        out["direction"] = term.direction
    return out


def _relationship_to_json(rel: Relationship) -> dict[str, object]:
    out: dict[str, object] = {
        "name": rel.name,
        "relatedEntity": rel.related_entity,
        "cardinality": rel.cardinality,
        "join": rel.join,
    }
    if rel.reverse_name is not None:
        out["reverseName"] = rel.reverse_name
    if rel.dependent:
        out["dependent"] = True
    if rel.foreign_key is not None:
        out["foreignKey"] = rel.foreign_key
    if rel.order_by:
        out["orderBy"] = [_order_by_to_json(term) for term in rel.order_by]
    return out


def _index_to_json(index: Index) -> dict[str, object]:
    out: dict[str, object] = {"name": index.name, "attributes": list(index.attributes)}
    if index.unique:
        out["unique"] = True
    return out


def _as_of_to_json(axis: AsOfAttribute) -> dict[str, object]:
    out: dict[str, object] = {
        "name": axis.name,
        "fromColumn": axis.from_column,
        "toColumn": axis.to_column,
        "axis": axis.axis,
    }
    if axis.to_is_inclusive:
        out["toIsInclusive"] = True
    return out


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
    if vo.cardinality != "one":
        out["cardinality"] = vo.cardinality
    if vo.attributes:
        out["attributes"] = [_vo_attribute_to_json(a) for a in vo.attributes]
    if vo.value_objects:
        out["valueObjects"] = [_nested_vo_to_json(n) for n in vo.value_objects]
    return out


def _value_object_to_json(vo: ValueObject) -> dict[str, object]:
    out: dict[str, object] = {"name": vo.name, "column": vo.column}
    if vo.nullable:
        out["nullable"] = True
    if vo.cardinality != "one":
        out["cardinality"] = vo.cardinality
    if vo.attributes:
        out["attributes"] = [_vo_attribute_to_json(a) for a in vo.attributes]
    if vo.value_objects:
        out["valueObjects"] = [_nested_vo_to_json(n) for n in vo.value_objects]
    return out


def _entity_to_json(entity: Entity) -> dict[str, object]:
    out: dict[str, object] = {"name": entity.name}
    if entity.namespace is not None:
        out["namespace"] = entity.namespace
    if entity.table is not None:
        out["table"] = entity.table
    if entity.mutability != "read-only":
        out["mutability"] = entity.mutability
    temporal: Temporal = entity.temporal
    if temporal != "non-temporal":
        out["temporal"] = temporal
    if entity.attributes:
        out["attributes"] = [_attribute_to_json(a) for a in entity.attributes]
    if entity.as_of_attributes:
        out["asOfAttributes"] = [_as_of_to_json(a) for a in entity.as_of_attributes]
    if entity.relationships:
        out["relationships"] = [_relationship_to_json(r) for r in entity.relationships]
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
