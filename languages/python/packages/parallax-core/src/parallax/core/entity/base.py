"""The entity base class and its metaclass (support scope, definition half).

Developers author frozen Pydantic entity classes; a ``ModelMetaclass`` subclass
unwraps the ``Attr[T]`` / ``Rel[T]`` annotations so Pydantic builds ordinary
inner-typed fields, installs the typed class-level descriptors, and compiles the
class body into a canonical :class:`~parallax.core.descriptor.Entity` record.
Reserved-name and canonical-name-collision checks run at class-definition time.
The class carries no information absent from the descriptor schema.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import re
import uuid as _uuid
from dataclasses import dataclass
from typing import Any, ClassVar, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.descriptor import UNSET
from parallax.core.descriptor import Attribute as AttributeRecord
from parallax.core.descriptor import Entity as EntityRecord
from parallax.core.descriptor import Relationship as RelationshipRecord
from parallax.core.entity.errors import (
    EntityDefinitionError,
    NameCollisionError,
    ReservedNameError,
)
from parallax.core.entity.expressions import Attr, AttributeRef, Rel, RelationshipRef
from parallax.core.entity.fields import FieldSpec, RelationshipSpec

__all__ = [
    "Entity",
    "EntityConfig",
    "EntityMeta",
    "camel_to_snake",
    "entity_record_of",
    "entity_registry",
    "snake_to_camel",
]

# Names reserved for the query root and introspection surface, plus the Pydantic
# ``model_*`` space; a field may not reuse them (rejected at class definition).
_RESERVED: frozenset[str] = frozenset(
    {"where", "narrow", "include", "as_of", "as_of_range", "history", "meta", "descriptor"}
)

_NEUTRAL_FROM_PY: dict[type, str] = {
    bool: "boolean",
    int: "int64",
    float: "float64",
    str: "string",
    bytes: "bytes",
    _dt.date: "date",
    _dt.time: "time",
    _dt.datetime: "timestamp",
    _uuid.UUID: "uuid",
    _decimal.Decimal: "decimal",
}

_ATTR_STR = re.compile(r"^Attr\[(?P<inner>.+)\]$", re.DOTALL)
_REL_STR = re.compile(r"^Rel\[(?P<inner>.+)\]$", re.DOTALL)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# The metamodel registry: canonical entity name -> the class that declared it,
# and the class -> its compiled metamodel record (kept off the class itself so
# the descriptor stays invisible to the public attribute surface).
_REGISTRY: dict[str, type[BaseModel]] = {}
_ENTITY_BY_CLASS: dict[type, EntityRecord] = {}

# A declared attribute captured during the annotation pass.
_AttrDecl = tuple[str, object, FieldSpec]
_RelDecl = tuple[str, object, RelationshipSpec]


@dataclass(frozen=True, slots=True)
class EntityConfig:
    """Storage configuration declared in an entity class body via ``__parallax__``."""

    table: str | None = None
    namespace: str | None = None
    mutability: str = "read-only"


def snake_to_camel(name: str) -> str:
    """Convert a snake_case field name to its canonical camelCase identifier."""
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def camel_to_snake(name: str) -> str:
    """Convert a CamelCase entity name to its default snake_case table name."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def entity_registry() -> dict[str, type[BaseModel]]:
    """A copy of the entity registry keyed by canonical entity name."""
    return dict(_REGISTRY)


def entity_record_of(cls: type) -> EntityRecord | None:
    """The compiled metamodel record for an entity class, or ``None``."""
    return _ENTITY_BY_CLASS.get(cls)


def _unwrap(annotation: object) -> tuple[str | None, object]:
    """Classify an annotation as ``attr`` / ``rel`` / plain and return its inner type."""
    if isinstance(annotation, str):
        if (match := _ATTR_STR.match(annotation.strip())) is not None:
            return "attr", match.group("inner")
        if (match := _REL_STR.match(annotation.strip())) is not None:
            return "rel", match.group("inner")
        return None, annotation
    origin = get_origin(annotation)
    if origin is Attr:
        return "attr", get_args(annotation)[0]
    if origin is Rel:
        return "rel", get_args(annotation)[0]
    return None, annotation


def _infer_neutral_type(inner: object, py_name: str) -> str:
    if isinstance(inner, type) and inner in _NEUTRAL_FROM_PY:
        neutral = _NEUTRAL_FROM_PY[inner]
        if neutral == "decimal":
            raise EntityDefinitionError(
                f"attribute {py_name!r}: a decimal needs an explicit precision — "
                "pass Field(type='decimal(p,s)')"
            )
        return neutral
    raise EntityDefinitionError(
        f"attribute {py_name!r}: cannot infer a neutral type from {inner!r}; pass Field(type=...)"
    )


def _attribute_of(decl: _AttrDecl) -> AttributeRecord:
    py_name, inner, spec = decl
    canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
    neutral = spec.type if spec.type is not None else _infer_neutral_type(inner, py_name)
    return AttributeRecord(
        name=canonical,
        type=neutral,
        column=spec.column if spec.column is not None else py_name,
        primary_key=spec.primary_key,
        nullable=spec.nullable,
        max_length=spec.max_length,
        read_only=spec.read_only,
        optimistic_locking=spec.optimistic_locking,
        pk_generator=spec.pk_generator,
        default=spec.default,
    )


def _relationship_of(decl: _RelDecl) -> RelationshipRecord:
    py_name, _inner, spec = decl
    canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
    return RelationshipRecord(
        name=canonical,
        related_entity=spec.related_entity,
        cardinality=spec.cardinality,
        join=spec.join,
        reverse_name=spec.reverse_name,
        dependent=spec.dependent,
        foreign_key=spec.foreign_key,
        order_by=spec.order_by,
    )


def _reject_reserved(py_name: str) -> None:
    if py_name in _RESERVED or py_name.startswith("model_"):
        raise ReservedNameError(f"field {py_name!r} reuses a reserved name")


def _reject_collisions(
    attributes: tuple[AttributeRecord, ...], relationships: tuple[RelationshipRecord, ...]
) -> None:
    seen: set[str] = set()
    for name in (*(a.name for a in attributes), *(r.name for r in relationships)):
        if name in seen:
            raise NameCollisionError(f"two fields resolve to the same canonical name {name!r}")
        seen.add(name)


def _check_mutability(value: str) -> str:
    if value not in ("read-only", "transactional"):
        raise EntityDefinitionError(
            f"mutability must be 'read-only' or 'transactional', got {value!r}"
        )
    return value


class EntityMeta(ModelMetaclass):
    """Metaclass compiling an entity class body into a metamodel record."""

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        if not any(isinstance(base, EntityMeta) for base in bases):
            return super().__new__(mcs, cls_name, bases, namespace, **kwargs)

        config = namespace.get("__parallax__")
        if config is not None and not isinstance(config, EntityConfig):
            raise EntityDefinitionError("`__parallax__` must be an EntityConfig")
        config = config if isinstance(config, EntityConfig) else EntityConfig()

        annotations: dict[str, Any] = dict(namespace.get("__annotations__", {}))
        attr_decls: list[_AttrDecl] = []
        rel_decls: list[_RelDecl] = []

        for py_name, annotation in list(annotations.items()):
            if get_origin(annotation) is ClassVar:
                continue
            kind, inner = _unwrap(annotation)
            _reject_reserved(py_name)
            value = namespace.get(py_name)
            if kind == "attr":
                annotations[py_name] = inner  # Attr[T] -> T for Pydantic
                spec = value if isinstance(value, FieldSpec) else FieldSpec()
                if spec.default is not UNSET:
                    namespace[py_name] = spec.default
                else:
                    namespace.pop(py_name, None)
                attr_decls.append((py_name, inner, spec))
            elif kind == "rel":
                if not isinstance(value, RelationshipSpec):
                    raise EntityDefinitionError(
                        f"relationship {py_name!r} needs `= Relationship(...)`"
                    )
                del annotations[py_name]  # relationships are not stored scalar fields
                namespace.pop(py_name, None)
                rel_decls.append((py_name, inner, value))
            else:
                raise EntityDefinitionError(
                    f"field {py_name!r} must be annotated Attr[...] or Rel[...], not {annotation!r}"
                )

        namespace["__annotations__"] = annotations

        # Compile the metamodel record BEFORE Pydantic builds the model, so a
        # neutral-type / relationship rejection is a Parallax error rather than a
        # downstream Pydantic schema-generation failure.
        attributes = tuple(_attribute_of(decl) for decl in attr_decls)
        relationships = tuple(_relationship_of(decl) for decl in rel_decls)
        _reject_collisions(attributes, relationships)
        if not attributes:
            raise EntityDefinitionError(f"entity {cls_name!r} declares no attributes")
        entity = EntityRecord(
            name=cls_name,
            namespace=config.namespace,
            table=config.table if config.table is not None else camel_to_snake(cls_name),
            mutability=cast("Any", _check_mutability(config.mutability)),
            attributes=attributes,
            relationships=relationships,
        )

        cls = super().__new__(mcs, cls_name, bases, namespace, **kwargs)
        for py_name, _inner, spec in attr_decls:
            canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
            setattr(cls, py_name, Attr(AttributeRef(cls_name, canonical), py_name))
        for py_name, _inner, rel_spec in rel_decls:
            canonical = rel_spec.name if rel_spec.name is not None else snake_to_camel(py_name)
            setattr(cls, py_name, Rel(RelationshipRef(cls_name, canonical), py_name))
        _REGISTRY[cls_name] = cast("type[BaseModel]", cls)
        _ENTITY_BY_CLASS[cls] = entity
        return cls


class Entity(BaseModel, metaclass=EntityMeta):
    """The frozen base every Parallax entity extends."""

    model_config = ConfigDict(frozen=True)
