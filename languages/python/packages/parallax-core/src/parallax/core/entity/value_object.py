"""The ``ValueObject`` class frontend (D-7 value-object spelling, spec §2/§5).

A ``ValueObject`` subclass is a frozen, metaclass-light Pydantic model whose
``Attr[T]`` fields declare either a scalar neutral-typed member or a nested
``ValueObject`` subclass (``cardinality: one``) / ``tuple[VOClass, ...]``
(``cardinality: many``). Its class-level attribute access yields an
:class:`~parallax.core.entity.expressions.ElementAttributeExpr` — an
ELEMENT-SCOPED expression (no leading entity prefix), valid inside a
relationship or value-object quantifier's ``where=``/interior predicates
(``Phone.type == "home"`` inside ``.any(...)``).

An entity declares a value-object member via an ordinary ``Attr[VOClass]`` (or
``Attr[tuple[VOClass, ...]]``) field (``parallax.core.entity.base`` detects this
and routes it into the compiled ``EntityRecord.value_objects`` rather than
``attributes`` — the metaclass threads the VO class's own compiled structure
into the owning entity's record exactly as the ``EntityConfig.as_of`` temporal
spelling threads declared axes, per the D-7 spelling precedent).

``ValueObject`` carries no table, primary key, or relationships — value objects
have no identity (m-value-object contract). This scope depends only on
``parallax.core.descriptor`` and ``parallax.core.entity.expressions``; it
introduces no new module-DAG edge (both are already-permitted dependencies of
the entity/statement frontend).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import UnionType
from typing import Any, ClassVar, Literal, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.descriptor import UNSET, NestedValueObject, ValueObjectAttribute
from parallax.core.descriptor.neutral_type import infer_neutral_type as _infer_neutral_type_lookup
from parallax.core.descriptor.neutral_type import snake_to_camel as _snake_to_camel
from parallax.core.entity.errors import EntityDefinitionError, ReservedNameError
from parallax.core.entity.expressions import Attr, ElementAttr

__all__ = [
    "ValueObject",
    "ValueObjectMeta",
    "ValueObjectStructure",
    "VoField",
    "VoFieldSpec",
    "structure_of",
    "to_document",
    "vo_field_info",
    "vo_instance_validator",
    "wire_names_of",
]

_RESERVED: frozenset[str] = frozenset({"model_construct", "model_copy", "model_dump"})


@dataclass(frozen=True, slots=True)
class VoFieldSpec:
    """The declared metadata of one value-object member."""

    name: str | None = None
    nullable: bool = False
    type: str | None = None
    default: object = UNSET


def VoField(
    *,
    name: str | None = None,
    nullable: bool = False,
    type: str | None = None,
    default: object = UNSET,
) -> Any:
    """Declare a value-object member's descriptor metadata (mirrors ``Field``)."""
    return VoFieldSpec(name=name, nullable=nullable, type=type, default=default)


@dataclass(frozen=True, slots=True)
class ValueObjectStructure:
    """One ``ValueObject`` class's compiled structure (attributes + nested VOs) —
    the shape a containing entity or value object wraps with its OWN
    ``name``/``nullable``/``cardinality``/``column`` (a VO class carries no
    identity of its own; the containing field decides all of that)."""

    attributes: tuple[ValueObjectAttribute, ...]
    value_objects: tuple[NestedValueObject, ...]


@dataclass(frozen=True, slots=True)
class VoWireNames:
    """Per-``ValueObject``-class canonical-name <-> python-field-name maps, the
    snapshot node wrapper and the write-row document builder both need.
    ``nested_classes`` maps a NESTED-value-object field's own python name to
    its declared class (``cardinality: many`` fields keep their ELEMENT
    class, not the ``tuple[...]`` wrapper)."""

    name_to_py: dict[str, str]
    py_to_name: dict[str, str]
    nested_classes: dict[str, type]


_VO_STRUCTURE: dict[type, ValueObjectStructure] = {}
_VO_WIRE_NAMES: dict[type, VoWireNames] = {}


def structure_of(cls: type) -> ValueObjectStructure:
    """The compiled structure of a ``ValueObject`` subclass."""
    structure = _VO_STRUCTURE.get(cls)
    if structure is None:
        raise EntityDefinitionError(f"{cls!r} is not a compiled ValueObject class")
    return structure


def wire_names_of(cls: type) -> VoWireNames:
    """The canonical-name <-> python-field-name maps of a ``ValueObject`` subclass."""
    names = _VO_WIRE_NAMES.get(cls)
    if names is None:
        raise EntityDefinitionError(f"{cls!r} is not a compiled ValueObject class")
    return names


def _infer_neutral_type(inner: object, py_name: str) -> str:
    # `parallax.core.descriptor.infer_neutral_type` is error-neutral (shared
    # with the Entity frontend, which this module cannot import back from
    # without cycling); this classifies its own unresolved-type /
    # needs-precision cases into the ValueObject frontend's own message text.
    neutral = _infer_neutral_type_lookup(inner)
    if neutral is None:
        raise EntityDefinitionError(
            f"value-object member {py_name!r}: cannot infer a neutral type from {inner!r}; "
            "pass VoField(type=...)"
        )
    if neutral == "decimal":
        raise EntityDefinitionError(
            f"value-object member {py_name!r}: a decimal needs an explicit precision — "
            "pass VoField(type='decimal(p,s)')"
        )
    return neutral


def _strip_optional(annotation: object) -> object:
    """Unwrap ``X | None`` (a nullable declared field, spec §2) to ``X`` — a
    value-object member's own nullability is DESCRIPTOR metadata
    (``VoField(nullable=True)`` / ``Field(nullable=True)``), never encoded in
    the Python type union the VO-detection below inspects."""
    origin = get_origin(annotation)
    if origin is UnionType or origin is Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def vo_instance_validator(py_name: str, vo_class: type, cardinality: str) -> Any:
    """A Pydantic ``mode="before"`` field validator enforcing python.md §2's
    value-object input policy: "the VO class instance; never a raw dict".
    Pydantic's own nested-``BaseModel`` field validation happily COERCES a
    plain ``dict`` into the declared model even under ``strict=True`` (no
    built-in switch rejects it), so this explicit isinstance check is the
    enforcement point — shared by the entity frontend (a top-level ``Attr[VO]``
    field) and the ``ValueObject`` frontend itself (a nested VO-in-VO field).
    Returns ``Any`` — the decorator-composed classmethod's own type is a
    Pydantic implementation detail this frontend does not model further.
    """

    def _validate(_cls: type, value: object) -> object:
        # Pydantic's own `field_validator` distinguishes a `(cls, value)`
        # signature from a bare `(value, info)` one ONLY via
        # `isinstance(func, classmethod)`; an unwrapped plain function here is
        # silently reinterpreted as the latter (the unused `_cls` parameter
        # would then receive `value`, and `value` would receive Pydantic's own
        # `ValidationInfo`) — hence the explicit `classmethod(...)` wrap
        # below, even though this validator never reads `cls`.
        if value is None:
            return value
        if cardinality == "many":
            if not isinstance(value, tuple):
                raise TypeError(
                    f"{py_name}: a cardinality-many value-object member requires a "
                    f"tuple of {vo_class.__name__!r} instances, not {type(value).__name__!r} "
                    "(never a raw dict/list)"
                )
            items = cast("tuple[object, ...]", value)
            for item in items:
                if not isinstance(item, vo_class):
                    raise TypeError(
                        f"{py_name}: element {item!r} is not a {vo_class.__name__!r} instance "
                        "(value objects are instances only, never a raw dict)"
                    )
            return items
        if not isinstance(value, vo_class):
            raise TypeError(
                f"{py_name}: a value-object member requires a {vo_class.__name__!r} instance, "
                f"not {type(value).__name__!r} (never a raw dict)"
            )
        return value

    bound = cast("Any", classmethod(_validate))
    return field_validator(py_name, mode="before")(bound)


def vo_field_info(inner: object) -> tuple[type, Literal["one", "many"]] | None:
    """Whether ``inner`` is a nested ``ValueObject`` subclass (cardinality
    ``one``) or ``tuple[VOClass, ...]`` (cardinality ``many``) — either bare or
    wrapped in ``| None`` (a nullable member)."""
    candidate = _strip_optional(inner)
    if isinstance(candidate, type) and issubclass(candidate, ValueObject):
        return candidate, "one"
    origin = get_origin(candidate)
    if origin is tuple:
        args = get_args(candidate)
        if (
            len(args) == 2
            and args[1] is Ellipsis
            and isinstance(args[0], type)
            and issubclass(args[0], ValueObject)
        ):
            return args[0], "many"
    return None


class ValueObjectMeta(ModelMetaclass):
    """Metaclass compiling a ``ValueObject`` class body into a
    :class:`ValueObjectStructure` (D-7 value-object spelling)."""

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        if not any(isinstance(base, ValueObjectMeta) for base in bases):
            return super().__new__(mcs, cls_name, bases, namespace, **kwargs)

        annotations: dict[str, Any] = dict(namespace.get("__annotations__", {}))
        globalns = _module_globalns(namespace)
        attributes: list[ValueObjectAttribute] = []
        nested: list[NestedValueObject] = []
        name_to_py: dict[str, str] = {}
        py_to_name: dict[str, str] = {}
        nested_classes: dict[str, type] = {}

        for py_name, annotation in list(annotations.items()):
            if get_origin(annotation) is ClassVar:
                continue
            inner = _attr_inner(annotation, globalns)
            if inner is None:
                raise EntityDefinitionError(
                    f"value-object field {py_name!r} must be annotated Attr[...], "
                    f"not {annotation!r}"
                )
            if py_name in _RESERVED or py_name.startswith("model_"):
                raise ReservedNameError(f"value-object field {py_name!r} reuses a reserved name")
            value = namespace.get(py_name)
            spec = value if isinstance(value, VoFieldSpec) else VoFieldSpec()
            canonical = spec.name if spec.name is not None else _snake_to_camel(py_name)
            if canonical in name_to_py:
                raise EntityDefinitionError(f"{cls_name}: two fields resolve to {canonical!r}")
            name_to_py[canonical] = py_name
            py_to_name[py_name] = canonical

            annotations[py_name] = inner
            if spec.default is not UNSET:
                namespace[py_name] = spec.default
            else:
                namespace.pop(py_name, None)

            vo_info = vo_field_info(inner)
            if vo_info is not None:
                vo_class, cardinality = vo_info
                nested_classes[py_name] = vo_class
                namespace[f"_validate_vo_{py_name}"] = vo_instance_validator(
                    py_name, vo_class, cardinality
                )
                sub = structure_of(vo_class)
                nested.append(
                    NestedValueObject(
                        name=canonical,
                        nullable=spec.nullable,
                        cardinality=cardinality,
                        attributes=sub.attributes,
                        value_objects=sub.value_objects,
                    )
                )
            else:
                neutral = (
                    spec.type if spec.type is not None else _infer_neutral_type(inner, py_name)
                )
                attributes.append(
                    ValueObjectAttribute(name=canonical, type=neutral, nullable=spec.nullable)
                )

        namespace["__annotations__"] = annotations
        cls = super().__new__(mcs, cls_name, bases, namespace, **kwargs)
        for py_name in list(name_to_py.values()):
            canonical = py_to_name[py_name]
            setattr(cls, py_name, ElementAttr(canonical, py_name))
        _VO_STRUCTURE[cls] = ValueObjectStructure(
            attributes=tuple(attributes), value_objects=tuple(nested)
        )
        _VO_WIRE_NAMES[cls] = VoWireNames(
            name_to_py=name_to_py, py_to_name=py_to_name, nested_classes=nested_classes
        )
        return cls


def _module_globalns(namespace: dict[str, Any]) -> dict[str, Any]:
    module_name = namespace.get("__module__")
    module = sys.modules.get(module_name) if isinstance(module_name, str) else None
    return dict(getattr(module, "__dict__", {}))


def _attr_inner(annotation: object, globalns: dict[str, Any]) -> object | None:
    """Unwrap an ``Attr[T]`` annotation (live or stringized) to its inner ``T``."""
    if isinstance(annotation, str):
        text = annotation.strip()
        if text.startswith("Attr[") and text.endswith("]"):
            inner_text = text[len("Attr[") : -1]
            try:
                # Trusted input: the developer's own annotation source, already
                # executed as a class body (mirrors entity/base.py's own resolver).
                return eval(inner_text, globalns)
            except (NameError, AttributeError, SyntaxError, TypeError):
                return inner_text
        return None
    if get_origin(annotation) is Attr:
        return get_args(annotation)[0]
    return None


class ValueObject(BaseModel, metaclass=ValueObjectMeta):
    """The frozen base every Parallax value-object class extends.

    Instances are the only legal ``json``-column input (python.md §2): a
    caller may never assign a raw ``dict`` where a value-object member is
    declared — the entity's own Pydantic field type is the ``ValueObject``
    subclass (or ``tuple[VOClass, ...]``), so construction/validation already
    enforces this.
    """

    model_config = ConfigDict(frozen=True)


def to_document(value: ValueObject | None) -> dict[str, object] | None:
    """Serialize a ``ValueObject`` instance to its canonical nested-dict document
    (canonical member names) — a write input's json-column value. ``None``
    passes through unchanged (an absent/nullable value object). Filtered by
    Pydantic's own ``model_fields_set`` alone (D-33), mirroring ``full_row``'s
    own top-level policy exactly: a member the caller never populated (relying
    on its declared default) is OMITTED, never bound as an explicit ``null``
    the corpus's own narrower document never authors; a member the caller
    explicitly set — even to a value equal to its own default — still renders
    (the same explicit-vs-defaulted distinction ``full_row`` draws). This
    filtering is UNCONDITIONAL on the member's own descriptor-declared
    nullability: a DESCRIPTOR-required member the caller never set is OMITTED
    exactly like an optional one, never coerced into rendering (e.g.
    ``to_document(ContactGeo())`` — every member absent — is ``{}``, not a
    document padded with placeholder nulls). This is deliberate, not an
    oversight: ``parallax.conformance.vo_models`` (e.g. ``ContactPoint``,
    ``ContactGeo``, ``CustomerGeo``) declares its descriptor-required members
    Python-optional (defaulted to ``None``) precisely so a caller CAN
    construct a structurally-incomplete instance — refusing one is
    ``parallax.core.unit_work.write_validate.validate_write``'s job, never
    this serializer's: an omitted (or explicit-``null``) required scalar
    attribute classifies to ``write-required-attribute-missing``, an omitted
    (or explicit-``null``) required nested value object to
    ``write-required-value-object-missing`` (the shared
    ``parallax.core.descriptor.vo_document.vo_document_violation`` walk treats
    "absent key" and "explicit null" identically, so this function's own
    omit-vs-null choice never changes which rule fires). Applied recursively:
    a nested ``ValueObject`` member and each ``tuple[VOClass, ...]`` element
    filter by their OWN ``model_fields_set`` via this same function."""
    if value is None:
        return None
    names = wire_names_of(type(value))
    fields_set = value.model_fields_set
    document: dict[str, object] = {}
    for py_name, canonical in names.py_to_name.items():
        if py_name not in fields_set:
            continue
        raw = getattr(value, py_name)
        if isinstance(raw, ValueObject):
            document[canonical] = to_document(raw)
        elif isinstance(raw, tuple):
            raw_items = cast("tuple[object, ...]", raw)
            document[canonical] = [
                to_document(item) if isinstance(item, ValueObject) else item for item in raw_items
            ]
        else:
            document[canonical] = raw
    return document
