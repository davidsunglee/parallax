"""Descriptor document parsing (m-descriptor).

Hand-rolled, snake-to-camel-aware reading of the canonical
``metamodel.schema.json`` document shape into the frozen metamodel records.
Python record fields are snake_case; canonical descriptor keys are camelCase.

``parse_document`` reads a descriptor document (JSON- or YAML-derived) into
records and stops there: cross-entity references keep their authored spelling,
because resolving them belongs to the foundational resolver behind the
``m-metamodel`` Unresolved seam. The canonical minimal document an accepted
model emits back is ``_export``'s answer, over the accepted Metamodel rather
than over these records.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from parallax.core.metamodel import default_column_name, derive_temporal_structure
from parallax.descriptor._errors import DescriptorError
from parallax.descriptor._records import (
    TEMPORAL_DIMENSIONS,
    AsOfAxisMetadata,
    Attribute,
    DefiningRelationship,
    DocumentLayout,
    Entity,
    Index,
    Inheritance,
    InheritanceRole,
    Layout,
    Metamodel,
    Multiplicity,
    NestedValueObject,
    OrderByTerm,
    Persistence,
    PkGenerator,
    PkStrategy,
    RelationshipCardinality,
    RelationshipDeclaration,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
    Temporality,
    ValueObject,
    ValueObjectAttribute,
)

__all__ = ["parse_document"]

_PERSISTENCE_MODES: frozenset[str] = frozenset({"read-write", "read-only"})
_PK_STRATEGIES: frozenset[str] = frozenset({"application-assigned", "max", "sequence"})
_REL_CARDINALITIES: frozenset[str] = frozenset({"one-to-one", "many-to-one", "one-to-many"})
_VO_CARDINALITIES: frozenset[str] = frozenset({"one", "many"})
_TEMPORALITIES: frozenset[str] = frozenset({"nontemporal", "transaction-time", "bitemporal"})
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
    return int(value)


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
# Parse (document shape to records).                                           #
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
        column=default_column_name(name) if column is None else column,
        primary_key=primary_key,
        nullable=_bool(m, "nullable", default=False, where=f"{where}.{name}"),
        max_length=_opt_int(m, "maxLength", f"{where}.{name}"),
        read_only=_bool(m, "readOnly", default=False, where=f"{where}.{name}"),
        optimistic_locking=_bool(m, "optimisticLocking", default=False, where=f"{where}.{name}"),
        pk_generator=(
            _pk_from(pk, f"{where}.{name}")
            if pk is not None
            else (PkGenerator(strategy="none") if primary_key else None)
        ),
    )


def _order_by_from(value: object, where: str) -> OrderByTerm:
    m = _mapping(value, where)
    _closed(m, frozenset({"attribute", "direction", "nulls"}), where)
    direction = m.get("direction", "asc")
    if direction not in ("asc", "desc"):
        raise DescriptorError(f"{where}: `direction` must be 'asc' or 'desc'")
    nulls = m.get("nulls", "last")
    if nulls not in ("first", "last"):
        raise DescriptorError(f"{where}: `nulls` must be 'first' or 'last'")
    return OrderByTerm(attr=_str(m, "attribute", where), direction=direction, nulls=nulls)


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


def _temporal_structure(
    temporality: Temporality | None,
) -> tuple[tuple[Attribute, ...], tuple[AsOfAxisMetadata, ...]]:
    """The endpoint Attributes and As-Of Axes a Temporality Profile derives.

    Every endpoint is a non-nullable Timestamp over the framework-fixed physical
    column the shared derivation supplies — not over ``defaultColumn``, which
    would fold ``txStart`` to ``tx_start`` rather than ``in_z``.
    """
    axes = derive_temporal_structure(temporality)
    attributes = tuple(
        Attribute(name=endpoint.name, type="timestamp", column=endpoint.column)
        for axis in axes
        for endpoint in (axis.start, axis.end)
    )
    return attributes, tuple(
        AsOfAxisMetadata(
            dimension=TEMPORAL_DIMENSIONS[axis.dimension],
            start_attribute=axis.start.name,
            end_attribute=axis.end.name,
        )
        for axis in axes
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
    default_column = default_column_name(name)
    return ValueObject(
        name=name,
        column=None if column in (None, default_column) else column,
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
                "layout",
                "temporality",
                "attributes",
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

    temporality = _temporality_from(m, where)
    authored = tuple(
        _attribute_from(item, f"{where}.attributes")
        for item in _list(m.get("attributes", []), where)
    )
    endpoints, as_of = _temporal_structure(temporality)
    attributes = (*authored, *endpoints)
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
    entity = Entity(
        name=name,
        namespace=_opt_str(m, "namespace", where),
        table=_opt_str(m, "table", where),
        persistence=_persistence_from(m, where),
        layout=_layout_from(m, where),
        temporality=temporality,
        attributes=attributes,
        as_of_axes=as_of,
        relationships=relationships,
        indices=indices,
        value_objects=value_objects,
        inheritance=inheritance,
    )
    return entity


def _persistence_from(m: Mapping[str, object], where: str) -> Persistence | None:
    """The `persistence` mode the document declares, or ``None`` when it omits it.

    Omission is preserved rather than resolved to the Read Write default: the
    default and an inherited mode are both spelled by absence, and only the
    document itself distinguishes them from a declaration.
    """
    if "persistence" not in m:
        return None
    value = m["persistence"]
    if not isinstance(value, str):
        raise DescriptorError(f"{where}: `persistence` must be a string")
    return cast("Persistence", _enum(value, _PERSISTENCE_MODES, "persistence", where))


def _temporality_from(m: Mapping[str, object], where: str) -> Temporality | None:
    """The Temporality Profile the document declares, or ``None`` when it omits it.

    Omission is preserved rather than resolved to Non-Temporal for the same
    reason as `persistence`: the profile is family-wide and root-owned, so
    absence is the default on a root and the inherit signal on a descendant, and
    only the document distinguishes either from a declaration.
    """
    if "temporality" not in m:
        return None
    value = m["temporality"]
    if not isinstance(value, str):
        raise DescriptorError(f"{where}: `temporality` must be a string")
    return cast("Temporality", _enum(value, _TEMPORALITIES, "temporality", where))


def _layout_from(m: Mapping[str, object], where: str) -> Layout | None:
    """The Storage Layout the document declares, or ``None`` when it omits it.

    Omission is the only spelling of Columns storage, so there is no `columns`
    member to read and absence is preserved rather than resolved: on a
    standalone entity or a family root it means Columns, and on a descendant it
    means inherit.
    """
    if "layout" not in m:
        return None
    layout = _mapping(m["layout"], f"{where}.layout")
    _closed(layout, frozenset({"document"}), f"{where}.layout")
    if "document" not in layout:
        raise DescriptorError(f"{where}.layout: `document` is required")
    document = _mapping(layout["document"], f"{where}.layout.document")
    _closed(document, frozenset({"column"}), f"{where}.layout.document")
    return DocumentLayout(column=_str(document, "column", f"{where}.layout.document"))


def _parsed_entities(document: Mapping[str, object]) -> tuple[Entity, ...]:
    """The document's entity records in authoring order, references untouched.

    The single-``entity`` and ``entities`` forms are mutually exclusive, and an
    empty model is rejected here — the source, not a later seam, is where a
    frontend owns emptiness.
    """
    _closed(document, frozenset({"entity", "entities"}), "descriptor")
    has_single = "entity" in document
    has_many = "entities" in document
    if has_single == has_many:
        raise DescriptorError("descriptor must declare exactly one of `entity` or `entities`")
    if has_single:
        return (_entity_from(document["entity"]),)
    entities = tuple(_entity_from(item) for item in _list(document["entities"], "entities"))
    if not entities:
        raise DescriptorError("`entities` must not be empty")
    return entities


def parse_document(document: Mapping[str, object]) -> Metamodel:
    """Parse a descriptor document into records without resolving references.

    Every Entity Reference keeps its authored relative or qualified spelling and
    no relationship is paired, so parsing reports only shape defects. Whether
    the references resolve, whether a relationship pairs, and every other
    model-wide question belong to Model Formation.
    """
    return Metamodel(entities=_parsed_entities(document))
