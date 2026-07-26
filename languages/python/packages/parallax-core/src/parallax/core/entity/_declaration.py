"""The shared Pydantic metaclass engine behind both class frontends.

One engine parses class headers and member annotations for Entity and Value
Object declarations alike and builds the frozen declaration payload eagerly, so
an Entity Class satisfies ``UnresolvedEntityDeclaration`` the moment it exists
and a Value Object Class carries its reusable shape the moment it exists. No
descriptor record graph, registry, or registered callback participates.

The engine imports neither frontend. A framework root identifies itself with the
:data:`FRAMEWORK_MINT` capability token this module owns, and its reserved
temporal axes travel on a marker read off the MRO, so "which base did this
declaration extend" is answered by reading attributes rather than by comparing
class identities the engine would have to import.
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import enum
import re
import sys
from dataclasses import dataclass
from types import NoneType, UnionType
from typing import Any, ClassVar, Final, ForwardRef, Union, cast, get_args, get_origin

from pydantic import ConfigDict, field_validator
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.base import FLOAT32, INT32, Decimal, Float32, Int32, NeutralType
from parallax.core.base import infer_neutral_type as _infer_neutral_type
from parallax.core.entity._errors import EntityDefinitionError
from parallax.core.entity._expressions import AttributeRef, RelationshipRef
from parallax.core.entity._members import (
    AbstractSubtype,
    Attr,
    AttrSpec,
    ConcreteSubtype,
    DefiningRelSpec,
    ElementAttr,
    IndexSpec,
    InheritanceRole,
    Rel,
    RelSpec,
    ReverseRelSpec,
)
from parallax.core.metamodel import (
    NOT_PRIMARY_KEY,
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    AttributePrimaryKey,
    AttributeReference,
    Column,
    EntityIdentity,
    EntityReference,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Max,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    PersistenceMode,
    RelationshipIdentity,
    RelationshipReference,
    RelativeEntityReference,
    Sequence,
    StorageContainer,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedInheritance,
    UnresolvedRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.metamodel import AbstractSubtype as AcceptedAbstractSubtype
from parallax.core.metamodel import ConcreteSubtype as AcceptedConcreteSubtype

__all__ = [
    "DECLARATION_MEMBER_NAMES",
    "FRAMEWORK_MINT",
    "RESERVED_MEMBER_NAMES",
    "STANDARD_TEMPORAL_NAMES",
    "DeclarationKind",
    "EntityDeclaration",
    "EntityHeader",
    "MemberNames",
    "RelationshipAnnotation",
    "ValueObjectShape",
    "build_class",
    "declaration_of",
    "inherited_axes",
    "is_declared_class",
    "is_entity_class",
    "members_of",
    "shape_of",
    "snake_to_camel",
]


class DeclarationKind(enum.Enum):
    """Which frontend a declaration belongs to."""

    ENTITY = "entity"
    VALUE_OBJECT = "value_object"


FRAMEWORK_MINT: Final = object()
"""Capability token authorizing an inert framework-root class.

Only the two frontend modules hold it. It guards against a mistyped header
rather than against a determined caller: anyone willing to import a private
module can obtain it, and the result is an inert class that declares nothing and
is never a hub candidate.
"""

_KIND: Final = "__parallax_kind__"
_AXES: Final = "__parallax_framework_axes__"
_DECLARATION: Final = "__parallax_declaration__"
_MEMBERS: Final = "__parallax_members__"
_SHAPE: Final = "__parallax_shape__"

_ATTR_TEXT = re.compile(r"^Attr\[(?P<inner>.+)\]$", re.DOTALL)
_REL_TEXT = re.compile(r"^Rel\[(?P<inner>.+)\]$", re.DOTALL)
_OPTIONAL_TEXT = re.compile(r"^Optional\[(?P<inner>.+)\]$", re.DOTALL)
_TUPLE_TEXT = re.compile(r"^tuple\[(?P<inner>.+)\]$", re.DOTALL)

DECLARATION_MEMBER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "identity",
        "container",
        "persistence",
        "attributes",
        "relationships",
        "value_objects",
        "as_of_axes",
        "inheritance",
        "indices",
    }
)
"""The ``UnresolvedEntityDeclaration`` members the Entity metaclass publishes on
the class object itself."""

# The reserved query-root and introspection spellings, plus the declaration
# members above. A member reusing one would be shadowed by the metaclass
# declaration at class level, so the collision is rejected where it is authored.
RESERVED_MEMBER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "where",
        "narrow",
        "include",
        "as_of",
        "as_of_range",
        "history",
        "meta",
        "descriptor",
        *DECLARATION_MEMBER_NAMES,
    }
)

STANDARD_TEMPORAL_NAMES: Final[tuple[str, ...]] = (
    "valid_start",
    "valid_end",
    "tx_start",
    "tx_end",
)
"""The reserved framework temporal member names, in canonical axis order."""

# Each axis's conventional member names over the stable physical columns.
_TEMPORAL_MEMBERS: Final[dict[TemporalDimension, tuple[tuple[str, str], tuple[str, str]]]] = {
    TemporalDimension.VALID_TIME: (("valid_start", "from_z"), ("valid_end", "thru_z")),
    TemporalDimension.TRANSACTION_TIME: (("tx_start", "in_z"), ("tx_end", "out_z")),
}


@dataclass(frozen=True, slots=True)
class EntityHeader:
    """The six class-header keywords, exactly as the class statement spelled them.

    Deliberately untyped: the metaclass types the keywords for the developer's
    type checker, while the engine still has to validate what a dynamically
    created class actually passed, and each rejection carries a stable code.
    """

    table: object = None
    name: object = None
    namespace: object = None
    persistence: object = None
    inheritance: object = None
    indices: object = ()


@dataclass(frozen=True, slots=True)
class EntityDeclaration:
    """One Entity Class's complete local declaration.

    The exact ``UnresolvedEntityDeclaration`` shape: reference-free facts are
    already their final Metadata values, and only relationship and inheritance
    references remain unresolved.
    """

    identity: EntityIdentity
    container: StorageContainer | None
    persistence: PersistenceMode | None
    attributes: tuple[AttributeMetadata, ...]
    relationships: tuple[UnresolvedRelationshipDeclaration, ...]
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...]
    as_of_axes: tuple[AsOfAxisMetadata, ...]
    inheritance: UnresolvedInheritance | None
    indices: tuple[IndexMetadata, ...]


@dataclass(frozen=True, slots=True)
class RelationshipAnnotation:
    """The shape one ``Rel[...]`` annotation spells, kept for realization.

    Multiplicity and optionality are Python facts the declaration itself does
    not carry: the model derives a direction's multiplicity from cardinality and
    its loaded-null answer from the join, so agreement between the two can only
    be checked once an accepted model exists.
    """

    py_name: str
    multiplicity: Multiplicity
    nullable: bool


@dataclass(frozen=True, slots=True)
class MemberNames:
    """One Entity Class's own Python-side member facts.

    The name correspondences and the relationship annotation shapes are built
    from the same walk the declaration is built from, so neither can drift from
    the declared member it belongs to. Merging a family's maps across the MRO
    belongs to the caller.
    """

    column_to_py: dict[str, str]
    name_to_py: dict[str, str]
    py_to_name: dict[str, str]
    relationship_py: dict[str, str]
    relationship_shapes: dict[str, RelationshipAnnotation]
    pk_py: frozenset[str]
    framework_owned_py: frozenset[str]
    axis_governed_py: frozenset[str]
    vo_classes: dict[str, type]


@dataclass(frozen=True, slots=True)
class ValueObjectShape:
    """One Value Object Class's reusable shape and its member correspondences.

    ``shape`` carries a single Shape Key minted once per class, so every
    occurrence of the class reuses one declaration node — exactly the reuse the
    formation-time reuse and containment-cycle rules are stated over.
    """

    shape: ValueObjectShapeDeclaration
    name_to_py: dict[str, str]
    py_to_name: dict[str, str]
    nested_classes: dict[str, type]
    many_py: frozenset[str]


def snake_to_camel(name: str) -> str:
    """The canonical camelCase member name a snake_case declaration name denotes."""
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def declaration_of(cls: type) -> EntityDeclaration:
    """``cls``'s own Entity declaration, or a loud rejection when it has none."""
    declaration = cls.__dict__.get(_DECLARATION)
    if not isinstance(declaration, EntityDeclaration):
        raise EntityDefinitionError(
            code="entity-base-invalid",
            message=f"{cls.__name__} is not a Parallax Entity Class",
        )
    return declaration


def members_of(cls: type) -> MemberNames:
    """``cls``'s own declared member correspondences (never an ancestor's)."""
    names = cls.__dict__.get(_MEMBERS)
    if not isinstance(names, MemberNames):
        raise EntityDefinitionError(
            code="entity-base-invalid",
            message=f"{cls.__name__} is not a Parallax Entity Class",
        )
    return names


def shape_of(cls: type) -> ValueObjectShape:
    """``cls``'s reusable Value Object shape, or a loud rejection when it has none."""
    shape = cls.__dict__.get(_SHAPE)
    if not isinstance(shape, ValueObjectShape):
        raise EntityDefinitionError(
            code="entity-annotation-invalid",
            message=f"{cls.__name__} is not a Parallax Value Object Class",
        )
    return shape


def is_declared_class(candidate: object, kind: DeclarationKind) -> bool:
    """Whether ``candidate`` is a class this engine built for ``kind``."""
    return isinstance(candidate, type) and getattr(candidate, _KIND, None) is kind


def is_entity_class(candidate: object) -> bool:
    """Whether ``candidate`` is a domain Entity Class — a hub candidate.

    The total, nonthrowing counterpart of :func:`declaration_of`. A framework
    root carries the Entity kind marker but no declaration, so it answers false
    here exactly as it is refused as a hub argument.
    """
    return is_declared_class(candidate, DeclarationKind.ENTITY) and isinstance(
        cast("type", candidate).__dict__.get(_DECLARATION), EntityDeclaration
    )


def inherited_axes(bases: tuple[type, ...]) -> tuple[TemporalDimension, ...]:
    """The reserved temporal axes this declaration inherits from its framework root.

    Read off the MRO by marker, so no frontend class object is imported or
    compared by identity — the fact travels with whichever root was extended.
    """
    for base in bases:
        for entry in base.__mro__:
            axes = entry.__dict__.get(_AXES)
            if axes is not None:
                return cast("tuple[TemporalDimension, ...]", axes)
    return ()


def build_class(
    mcs: type,
    cls_name: str,
    bases: tuple[type, ...],
    ns: dict[str, object],
    *,
    kind: DeclarationKind,
    mint: object | None,
    axes: tuple[TemporalDimension, ...],
    header: EntityHeader | None,
) -> type:
    """Build one declared class, rejecting anything outside the grammar.

    Every Parallax class is implicitly frozen, so the engine sets the Pydantic
    configuration itself and forwards no class-header keyword to Pydantic. A
    framework root carries markers only: no identity, no declaration payload, no
    header rules, and it is never a hub candidate.
    """
    ns["model_config"] = ConfigDict(frozen=True)
    if mint is not None:
        if mint is not FRAMEWORK_MINT:
            raise EntityDefinitionError(
                code="entity-header-unknown-option",
                message=f"{cls_name}: '_mint' is not a declaration option",
            )
        ns[_KIND] = kind
        ns[_AXES] = axes
        return _pydantic_class(mcs, cls_name, bases, ns)
    if kind is DeclarationKind.ENTITY:
        return _build_entity(mcs, cls_name, bases, ns, header or EntityHeader())
    return _build_value_object(mcs, cls_name, bases, ns)


def _pydantic_class(
    mcs: type, cls_name: str, bases: tuple[type, ...], ns: dict[str, object]
) -> type:
    return ModelMetaclass.__new__(
        cast("type[ModelMetaclass]", mcs), cls_name, bases, cast("dict[str, Any]", ns)
    )


# --------------------------------------------------------------------------- #
# Class-body annotations
# --------------------------------------------------------------------------- #


def _class_body_annotations(ns: dict[str, object]) -> dict[str, object]:
    """The class-body annotations, read from the metaclass namespace cross-version.

    On Python 3.12/3.13 the live annotation objects sit eagerly in
    ``__annotations__``. Under PEP 649 / PEP 749 the namespace carries a deferred
    ``__annotate_func__`` instead. The result is always a fresh mapping the
    caller may mutate.
    """
    eager = ns.get("__annotations__")
    if isinstance(eager, dict):
        return dict(cast("dict[str, object]", eager))
    annotate = ns.pop("__annotate_func__", None)
    if annotate is None:
        return {}
    return _resolve_deferred(annotate)


def _resolve_deferred(annotate: object) -> dict[str, object]:
    """Recover deferred (PEP 649 / PEP 749) class-body annotations.

    Evaluated in ``VALUE`` format to recover the same live objects the eager path
    returns. The version guard also keeps the 3.14-only import off the
    type-checked path, which is pinned to 3.12.
    """
    if sys.version_info < (3, 14):
        return {}
    import annotationlib  # 3.14 stdlib (PEP 649 / PEP 749)

    return dict(annotationlib.call_annotate_function(annotate, annotationlib.Format.VALUE))


def _module_globals(ns: dict[str, object]) -> dict[str, Any]:
    module_name = ns.get("__module__")
    module = sys.modules.get(module_name) if isinstance(module_name, str) else None
    return dict(getattr(module, "__dict__", {}))


def _resolve(text: str, globalns: dict[str, Any], localns: dict[str, object]) -> object | None:
    """A stringized annotation fragment as a live object, or ``None``.

    Resolved against the class body before module globals, so a Value Object
    shape declared lexically inside its owner resolves under
    ``from __future__ import annotations``. The source is the developer's own
    annotation, already executed as a class body.
    """
    try:
        return eval(text, globalns, dict(localns))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Annotation shapes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Shape:
    """One member annotation's resolved shape.

    ``base`` is the live inner type when it resolved, and ``spelling`` carries
    the textual inner instead for a relationship target that does not exist yet.
    """

    base: object
    spelling: str | None
    multiplicity: Multiplicity
    nullable: bool


def _classify(
    annotation: object, globalns: dict[str, Any], localns: dict[str, object]
) -> tuple[str, object] | None:
    """The member kind and raw inner of a class-body annotation.

    ``class_var`` is the third kind and declares no member. It is classified here
    rather than by the callers because a class variable is a live typing form on
    one annotation path and text on the other, and the two paths must pass over
    the same declarations.
    """
    if isinstance(annotation, str):
        text = annotation.strip()
        if (match := _ATTR_TEXT.match(text)) is not None:
            return "attr", match.group("inner")
        if (match := _REL_TEXT.match(text)) is not None:
            return "rel", match.group("inner")
        resolved = _resolve(text, globalns, localns)
        return None if resolved is None else _classify(resolved, globalns, localns)
    origin = get_origin(annotation)
    if origin is Attr:
        return "attr", get_args(annotation)[0]
    if origin is Rel:
        return "rel", get_args(annotation)[0]
    if annotation is ClassVar or origin is ClassVar:
        return "class_var", None
    return None


def _annotation_text(inner: object) -> str | None:
    """The spelling behind an unevaluated annotation fragment, if it is one.

    A ``ForwardRef`` and a quoted fragment are one fact reached by the two
    annotation paths: a name the class body wrote as text.
    """
    if isinstance(inner, ForwardRef):
        return inner.__forward_arg__.strip()
    if isinstance(inner, str):
        return _unquote(inner)
    return None


def _shape_of_annotation(
    inner: object,
    *,
    where: str,
    globalns: dict[str, Any],
    localns: dict[str, object],
    relationship_target: bool,
) -> _Shape:
    """The multiplicity, optionality, and inner type an annotation declares.

    A relationship target is read as a spelling and never evaluated: the hub
    candidate set is the only scope a target resolves in, so a class object is
    Exact and every text form is a name — qualified or relative to the declaring
    Entity — however the annotation path happened to deliver it. Every other
    annotation names a Python type, so a spelling is resolved against the class
    body before module globals.
    """
    text = _annotation_text(inner)
    if text is None:
        return _live_shape(
            inner,
            where=where,
            globalns=globalns,
            localns=localns,
            relationship_target=relationship_target,
        )
    if relationship_target:
        return _text_shape(text, where=where)
    return _live_shape(
        _resolved(text, where=where, globalns=globalns, localns=localns),
        where=where,
        globalns=globalns,
        localns=localns,
        relationship_target=relationship_target,
    )


def _resolved(
    text: str, *, where: str, globalns: dict[str, Any], localns: dict[str, object]
) -> object:
    resolved = _resolve(text, globalns, localns)
    if resolved is None:
        raise EntityDefinitionError(
            code="entity-annotation-invalid",
            message=f"{where}: cannot resolve the annotation {text!r}",
        )
    return resolved


def _live_shape(
    inner: object,
    *,
    where: str,
    globalns: dict[str, Any],
    localns: dict[str, object],
    relationship_target: bool,
) -> _Shape:
    multiplicity = Multiplicity.ONE
    nullable = False
    origin = get_origin(inner)
    if origin is UnionType or origin is Union:
        members = [arg for arg in get_args(inner) if arg is not NoneType]
        if len(members) != 1 or len(get_args(inner)) != 2:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: only an `X | None` union is a declarable annotation",
            )
        inner = members[0]
        nullable = True
        origin = get_origin(inner)
    if origin is tuple:
        args = get_args(inner)
        if len(args) != 2 or args[1] is not Ellipsis:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: a many member is spelled `tuple[X, ...]`",
            )
        inner = args[0]
        multiplicity = Multiplicity.MANY
    text = _annotation_text(inner)
    if text is not None:
        if relationship_target:
            return _Shape(None, text, multiplicity, nullable)
        inner = _resolved(text, where=where, globalns=globalns, localns=localns)
    return _Shape(inner, None, multiplicity, nullable)


def _text_shape(text: str, *, where: str) -> _Shape:
    """The shape a relationship-target spelling declares.

    The wrappers are stripped in the order the live reading strips them, so one
    spelling declares one shape whichever path delivered it.
    """
    body = text.strip()
    nullable = False
    if (match := _OPTIONAL_TEXT.match(body)) is not None:
        body = _unquote(match.group("inner"))
        nullable = True
    elif "|" in body:
        members = [part.strip() for part in body.split("|")]
        named = [part for part in members if part != "None"]
        if len(members) != 2 or len(named) != 1:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: only an `X | None` union is a declarable annotation",
            )
        body = _unquote(named[0])
        nullable = True
    multiplicity = Multiplicity.ONE
    if (match := _TUPLE_TEXT.match(body)) is not None:
        head, _, tail = match.group("inner").rpartition(",")
        if tail.strip() != "...":
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: a many relationship is spelled `tuple[Target, ...]`",
            )
        body = _unquote(head)
        multiplicity = Multiplicity.MANY
    return _Shape(None, body, multiplicity, nullable)


def _unquote(text: str) -> str:
    body = text.strip()
    if len(body) >= 2 and body[0] in "\"'" and body[-1] == body[0]:
        return body[1:-1].strip()
    return body


# --------------------------------------------------------------------------- #
# Scalar members
# --------------------------------------------------------------------------- #


def _scalar_type(base: object, spec: AttrSpec, where: str) -> NeutralType:
    """The Neutral Type a scalar member declares.

    The annotation names the family and the declaration narrows it: ``type=``
    selects the 32-bit member of the two two-variant families, and
    ``precision=``/``scale=`` supply the parametric Decimal variant's required
    parameters.
    """
    if spec.type is not None:
        if isinstance(spec.type, Int32) and base is int:
            return INT32
        if isinstance(spec.type, Float32) and base is float:
            return FLOAT32
        raise EntityDefinitionError(
            code="entity-option-context-invalid",
            message=(
                f"{where}: type= narrows an `Attr[int]` to Int32 or an `Attr[float]` to "
                "Float32 and applies to no other annotation"
            ),
        )
    if base is _decimal.Decimal:
        if spec.precision is None or spec.scale is None:
            raise EntityDefinitionError(
                code="entity-option-context-invalid",
                message=f"{where}: a decimal member declares precision= and scale=",
            )
        try:
            return Decimal(spec.precision, spec.scale)
        except ValueError as error:
            raise EntityDefinitionError(
                code="entity-option-invalid-value", message=f"{where}: {error}"
            ) from error
    if spec.precision is not None:
        raise EntityDefinitionError(
            code="entity-option-context-invalid",
            message=f"{where}: precision= and scale= apply only to a decimal member",
        )
    neutral = _infer_neutral_type(base)
    if neutral is None:
        raise EntityDefinitionError(
            code="entity-annotation-invalid",
            message=f"{where}: {base!r} is not a declarable member type",
        )
    return neutral


def _reject_entity_only_options(spec: AttrSpec, where: str, *, allow_column: bool) -> None:
    """Reject the options a Value Object member has no place for.

    A Value Object attribute carries no storage, key, generation, locking, or
    length bound; only a top-level occurrence owns a Storage Location, so
    ``column=`` is admitted exactly there.
    """
    offending = [
        option
        for option, present in (
            ("primary_key", spec.primary_key is not NOT_PRIMARY_KEY),
            ("column", spec.column is not None and not allow_column),
            ("max_length", spec.max_length is not None),
            ("read_only", spec.read_only),
            ("optimistic_locking", spec.optimistic_locking),
        )
        if present
    ]
    if offending:
        raise EntityDefinitionError(
            code="entity-option-context-invalid",
            message=f"{where}: {', '.join(offending)} is an Entity-only option",
        )


# --------------------------------------------------------------------------- #
# Value Object classes
# --------------------------------------------------------------------------- #


def _build_value_object(
    mcs: type, cls_name: str, bases: tuple[type, ...], ns: dict[str, object]
) -> type:
    if len(bases) != 1 or not is_declared_class(bases[0], DeclarationKind.VALUE_OBJECT):
        raise EntityDefinitionError(
            code="entity-base-invalid",
            message=f"{cls_name}: a Value Object Class extends exactly one ValueObject base",
        )
    annotations = _class_body_annotations(ns)
    globalns = _module_globals(ns)
    attributes: list[ValueObjectAttributeDeclaration] = []
    nested: list[NestedValueObjectOccurrenceDeclaration] = []
    py_to_name: dict[str, str] = {}
    canonical_seen: set[str] = set()
    nested_classes: dict[str, type] = {}
    many_py: set[str] = set()
    shapes: dict[str, _Shape] = {}

    for py_name, annotation in list(annotations.items()):
        where = f"{cls_name}.{py_name}"
        if py_name.startswith("model_"):
            raise EntityDefinitionError(
                code="entity-reserved-member-name",
                message=f"{where}: the `model_*` namespace is reserved by Pydantic",
            )
        classified = _classify(annotation, globalns, ns)
        if classified is not None and classified[0] == "class_var":
            continue
        if classified is None or classified[0] != "attr":
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: a Value Object member is annotated Attr[...]",
            )
        spec = cast("AttrSpec", _member_spec(ns.get(py_name), where, expect="attr"))
        shape = _shape_of_annotation(
            classified[1], where=where, globalns=globalns, localns=ns, relationship_target=False
        )
        canonical = _declared_name(spec, py_name)
        if canonical in canonical_seen:
            raise EntityDefinitionError(
                code="entity-canonical-name-collision",
                message=f"{cls_name}: two members resolve to the canonical name {canonical!r}",
            )
        canonical_seen.add(canonical)
        py_to_name[py_name] = canonical
        shapes[py_name] = shape
        _reject_entity_only_options(spec, where, allow_column=False)

        if is_declared_class(shape.base, DeclarationKind.VALUE_OBJECT):
            if spec.type is not None or spec.precision is not None:
                raise EntityDefinitionError(
                    code="entity-option-context-invalid",
                    message=f"{where}: a Value Object occurrence declares no scalar type",
                )
            nested_class = cast("type", shape.base)
            nested_classes[py_name] = nested_class
            if shape.multiplicity is Multiplicity.MANY:
                many_py.add(py_name)
            nested.append(
                NestedValueObjectOccurrenceDeclaration(
                    name=canonical,
                    shape=shape_of(nested_class).shape,
                    multiplicity=shape.multiplicity,
                    nullable=shape.nullable,
                )
            )
            continue
        if shape.multiplicity is Multiplicity.MANY:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: only a Value Object occurrence is spelled `tuple[X, ...]`",
            )
        attributes.append(
            ValueObjectAttributeDeclaration(
                name=canonical,
                type=_scalar_type(shape.base, spec, where),
                nullable=shape.nullable,
            )
        )

    _install_fields(annotations, ns, shapes, nested_classes, many_py, axis_governed=frozenset())
    ns[_SHAPE] = ValueObjectShape(
        shape=ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=tuple(attributes),
            value_objects=tuple(nested),
        ),
        name_to_py={canonical: py_name for py_name, canonical in py_to_name.items()},
        py_to_name=py_to_name,
        nested_classes=nested_classes,
        many_py=frozenset(many_py),
    )
    cls = _pydantic_class(mcs, cls_name, bases, ns)
    for py_name, canonical in py_to_name.items():
        setattr(cls, py_name, ElementAttr(canonical, py_name))
    return cls


# --------------------------------------------------------------------------- #
# Entity classes
# --------------------------------------------------------------------------- #


def _build_entity(
    mcs: type,
    cls_name: str,
    bases: tuple[type, ...],
    ns: dict[str, object],
    header: EntityHeader,
) -> type:
    parent = _domain_parent(cls_name, bases)
    role = _inheritance_role(cls_name, header, parent)
    identity = EntityIdentity(_namespace(cls_name, header), _entity_name(cls_name, header))
    axes = inherited_axes(bases)
    shape_owner = parent is None and bool(axes)

    annotations = _class_body_annotations(ns)
    globalns = _module_globals(ns)
    _reject_shadowed_class_names(cls_name, ns)
    if axes:
        _reject_temporal_redeclaration(cls_name, annotations, ns)
    if shape_owner:
        _inject_temporal_members(annotations, ns, axes)
    axis_members = _axis_metadata(identity, axes) if shape_owner else ()
    axis_names = {
        name
        for axis in axis_members
        for name in (axis.start_attribute.name, axis.end_attribute.name)
    }

    attributes: list[AttributeMetadata] = []
    relationships: list[UnresolvedRelationshipDeclaration] = []
    occurrences: list[ValueObjectOccurrenceDeclaration] = []
    column_to_py: dict[str, str] = {}
    name_to_py: dict[str, str] = {}
    py_to_name: dict[str, str] = {}
    relationship_py: dict[str, str] = {}
    relationship_shapes: dict[str, RelationshipAnnotation] = {}
    pk_py: set[str] = set()
    framework_owned_py: set[str] = set()
    axis_governed_py: set[str] = set()
    vo_classes: dict[str, type] = {}
    many_py: set[str] = set()
    shapes: dict[str, _Shape] = {}
    canonical_seen: set[str] = set()

    for py_name, annotation in list(annotations.items()):
        where = f"{cls_name}.{py_name}"
        _reject_reserved(where, py_name, axes, injected=py_name in STANDARD_TEMPORAL_NAMES)
        classified = _classify(annotation, globalns, ns)
        if classified is None:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: a member is annotated Attr[...] or Rel[...]",
            )
        member_kind, inner = classified
        if member_kind == "class_var":
            continue
        spec = _member_spec(ns.get(py_name), where, expect=member_kind)
        shape = _shape_of_annotation(
            inner,
            where=where,
            globalns=globalns,
            localns=ns,
            relationship_target=member_kind == "rel",
        )
        canonical = _declared_name(spec, py_name)
        if canonical in canonical_seen:
            raise EntityDefinitionError(
                code="entity-canonical-name-collision",
                message=f"{cls_name}: two members resolve to the canonical name {canonical!r}",
            )
        canonical_seen.add(canonical)

        if member_kind == "rel":
            del annotations[py_name]  # a relationship is never a stored Pydantic field
            ns.pop(py_name, None)
            relationships.append(
                _relationship(identity, canonical, cast("RelSpec", spec), shape, where)
            )
            relationship_py[canonical] = py_name
            relationship_shapes[canonical] = RelationshipAnnotation(
                py_name=py_name, multiplicity=shape.multiplicity, nullable=shape.nullable
            )
            continue

        attr_spec = cast("AttrSpec", spec)
        py_to_name[py_name] = canonical
        name_to_py[canonical] = py_name
        shapes[py_name] = shape
        column = attr_spec.column if attr_spec.column is not None else canonical
        column_to_py[column] = py_name

        if is_declared_class(shape.base, DeclarationKind.VALUE_OBJECT):
            if attr_spec.primary_key is not NOT_PRIMARY_KEY or attr_spec.optimistic_locking:
                raise EntityDefinitionError(
                    code="entity-option-context-invalid",
                    message=f"{where}: a Value Object occurrence carries no key or version",
                )
            vo_class = cast("type", shape.base)
            vo_classes[py_name] = vo_class
            if shape.multiplicity is Multiplicity.MANY:
                many_py.add(py_name)
            occurrences.append(
                ValueObjectOccurrenceDeclaration(
                    name=canonical,
                    storage=Column(column),
                    shape=shape_of(vo_class).shape,
                    multiplicity=shape.multiplicity,
                    nullable=shape.nullable,
                )
            )
            continue
        if shape.multiplicity is Multiplicity.MANY:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: only a Value Object occurrence is spelled `tuple[X, ...]`",
            )
        if attr_spec.primary_key is not NOT_PRIMARY_KEY:
            pk_py.add(py_name)
            _reject_incompatible_generation(attr_spec.primary_key, shape.base, where)
        if attr_spec.optimistic_locking:
            framework_owned_py.add(py_name)
        if canonical in axis_names:
            axis_governed_py.add(py_name)
        attributes.append(_attribute(identity, canonical, column, attr_spec, shape, where))

    _install_fields(
        annotations, ns, shapes, vo_classes, many_py, axis_governed=frozenset(axis_governed_py)
    )
    ns[_DECLARATION] = EntityDeclaration(
        identity=identity,
        container=_container(cls_name, header),
        persistence=_persistence(cls_name, header),
        attributes=tuple(attributes),
        relationships=tuple(relationships),
        value_objects=tuple(occurrences),
        as_of_axes=axis_members,
        inheritance=_accepted_inheritance(role, parent),
        indices=_indices(identity, header.indices, py_to_name),
    )
    ns[_MEMBERS] = MemberNames(
        column_to_py=column_to_py,
        name_to_py=name_to_py,
        py_to_name=py_to_name,
        relationship_py=relationship_py,
        relationship_shapes=relationship_shapes,
        pk_py=frozenset(pk_py),
        framework_owned_py=frozenset(framework_owned_py),
        axis_governed_py=frozenset(axis_governed_py),
        vo_classes=vo_classes,
    )
    cls = _pydantic_class(mcs, cls_name, bases, ns)
    for py_name, canonical in py_to_name.items():
        setattr(cls, py_name, Attr(AttributeRef(identity.name, canonical), py_name))
    for canonical, py_name in relationship_py.items():
        setattr(
            cls,
            py_name,
            Rel(
                RelationshipRef(identity.name, canonical),
                py_name,
                _target_name(tuple(relationships), canonical),
            ),
        )
    return cls


def _attribute(
    identity: EntityIdentity,
    canonical: str,
    column: str,
    spec: AttrSpec,
    shape: _Shape,
    where: str,
) -> AttributeMetadata:
    """One scalar Attribute, with the value layer's own refusals reclassified.

    Attribute Metadata refuses a bounded length on a non-text member, which is a
    declaration-context defect rather than an internal failure.
    """
    try:
        return AttributeMetadata(
            identity=AttributeIdentity(identity, canonical),
            type=_scalar_type(shape.base, spec, where),
            storage=Column(column),
            primary_key=spec.primary_key,
            nullable=shape.nullable,
            max_length=spec.max_length,
            read_only=spec.read_only,
            optimistic_locking=spec.optimistic_locking,
        )
    except ValueError as error:
        raise EntityDefinitionError(
            code="entity-option-context-invalid", message=f"{where}: {error}"
        ) from error


def _domain_parent(cls_name: str, bases: tuple[type, ...]) -> type | None:
    """The single domain Entity base this declaration extends, or ``None``.

    Exactly one Parallax base is legal and a non-Parallax mixin is outside the
    grammar, so both the count and the shape of ``bases`` are checked here.
    """
    invalid = EntityDefinitionError(
        code="entity-base-invalid",
        message=(
            f"{cls_name}: an Entity Class extends exactly one Parallax base — a framework "
            "root (Entity, TxTemporal, Bitemporal) or one domain Entity parent"
        ),
    )
    if len(bases) != 1 or not is_declared_class(bases[0], DeclarationKind.ENTITY):
        raise invalid
    return bases[0] if _DECLARATION in bases[0].__dict__ else None


def _container(cls_name: str, header: EntityHeader) -> StorageContainer | None:
    if header.table is None:
        return None
    if not isinstance(header.table, str) or not header.table:
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{cls_name}: table= takes a nonempty string, got {header.table!r}",
        )
    return Table(header.table)


def _persistence(cls_name: str, header: EntityHeader) -> PersistenceMode | None:
    if header.persistence is None or isinstance(header.persistence, PersistenceMode):
        return header.persistence
    raise EntityDefinitionError(
        code="entity-header-invalid-value",
        message=f"{cls_name}: persistence= takes READ_ONLY, got {header.persistence!r}",
    )


def _entity_name(cls_name: str, header: EntityHeader) -> str:
    if header.name is None:
        return cls_name
    if not isinstance(header.name, str) or not header.name or "." in header.name:
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{cls_name}: name= takes a nonempty dot-free string, got {header.name!r}",
        )
    return header.name


def _namespace(cls_name: str, header: EntityHeader) -> str | None:
    if header.namespace is None:
        return None
    if not isinstance(header.namespace, str) or not header.namespace:
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{cls_name}: namespace= takes a nonempty string, got {header.namespace!r}",
        )
    return header.namespace


def _inheritance_role(
    cls_name: str, header: EntityHeader, parent: type | None
) -> InheritanceRole | None:
    """The normalized inheritance role, with the bare class spellings accepted.

    ``AbstractSubtype`` and ``ConcreteSubtype`` carry no payload in the common
    case, so the class object reads as naturally as an instance. A payload-
    carrying variant has no such reading, so a root's strategy is checked here
    rather than left to fail later as an unmatched pattern.
    """
    role: object = header.inheritance
    if role is AbstractSubtype:
        role = AbstractSubtype()
    elif role is ConcreteSubtype:
        role = ConcreteSubtype()
    if role is not None and not isinstance(role, (AbstractRoot, AbstractSubtype, ConcreteSubtype)):
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=(
                f"{cls_name}: inheritance= takes AbstractRoot(...), AbstractSubtype, or "
                f"ConcreteSubtype(...), got {role!r}"
            ),
        )
    if isinstance(role, AbstractRoot):
        # A frozen dataclass records its payload without checking it, so the
        # declared field type is a promise to the type checker rather than a
        # fact about what a header actually passed.
        strategy = cast("object", role.strategy)
        if not isinstance(strategy, (TablePerHierarchy, TablePerConcreteSubtype)):
            raise EntityDefinitionError(
                code="entity-header-invalid-value",
                message=(
                    f"{cls_name}: AbstractRoot(...) takes TablePerHierarchy(...) or "
                    f"TABLE_PER_CONCRETE_SUBTYPE, got {strategy!r}"
                ),
            )
    if parent is None:
        if isinstance(role, (AbstractSubtype, ConcreteSubtype)):
            raise EntityDefinitionError(
                code="entity-header-invalid-value",
                message=(
                    f"{cls_name}: a subtype role needs a domain Entity parent; subclass the "
                    "family's root"
                ),
            )
        if role is None and header.table is None:
            raise EntityDefinitionError(
                code="entity-header-missing-option",
                message=f"{cls_name}: a standalone Entity declares table=",
            )
    elif role is None:
        raise EntityDefinitionError(
            code="entity-base-invalid",
            message=(
                f"{cls_name}: a domain-Entity subclass declares inheritance=; a role is never "
                "implicit"
            ),
        )
    return role


def _accepted_inheritance(
    role: InheritanceRole | None, parent: type | None
) -> UnresolvedInheritance | None:
    """The accepted inheritance position, with the parent supplied by subclassing."""
    match role:
        case None:
            return None
        case AbstractRoot():
            return role
        case AbstractSubtype():
            return AcceptedAbstractSubtype(_parent_reference(parent))
        case ConcreteSubtype(tag_value):
            return AcceptedConcreteSubtype(_parent_reference(parent), tag_value)


def _parent_reference(parent: type | None) -> EntityReference:
    if parent is None:  # pragma: no cover - a subtype role without a parent is rejected earlier
        raise EntityDefinitionError(
            code="entity-base-invalid", message="a subtype role needs a domain Entity parent"
        )
    return ExactEntityReference(declaration_of(parent).identity)


def _indices(
    identity: EntityIdentity, declared: object, py_to_name: dict[str, str]
) -> tuple[IndexMetadata, ...]:
    """The declared indices, with components lowered to Attribute Identities.

    A component names a Python member; an unknown name lowers through the
    deterministic conversion so foundational resolution can locate and report it.
    """
    if not isinstance(declared, tuple):
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{identity.name}: indices= takes a tuple of index(...) values",
        )
    entries = cast("tuple[object, ...]", declared)
    if any(not isinstance(entry, IndexSpec) for entry in entries):
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{identity.name}: indices= takes a tuple of index(...) values",
        )
    specs = cast("tuple[IndexSpec, ...]", entries)
    return tuple(
        IndexMetadata(
            identity=IndexIdentity(identity, spec.name),
            attributes=tuple(
                AttributeIdentity(identity, py_to_name.get(member, snake_to_camel(member)))
                for member in spec.members
            ),
            unique=spec.unique,
        )
        for spec in specs
    )


def _declared_name(spec: AttrSpec | RelSpec, py_name: str) -> str:
    return spec.name if spec.name is not None else snake_to_camel(py_name)


def _member_spec(value: object, where: str, *, expect: str) -> AttrSpec | RelSpec:
    """The assignment slot's declaration value, or the default for an empty slot.

    The slot holds one factory value matching the annotation and nothing else: a
    bare value, or the wrong factory for the annotation, is rejected here.
    """
    if expect == "attr":
        if value is None:
            return AttrSpec()
        if isinstance(value, AttrSpec):
            return value
        if isinstance(value, (DefiningRelSpec, ReverseRelSpec)):
            raise EntityDefinitionError(
                code="entity-member-value-invalid",
                message=f"{where}: a rel(...) value under an Attr[...] annotation",
            )
        raise EntityDefinitionError(
            code="entity-member-value-invalid",
            message=f"{where}: an Attr[...] member holds at most one attr(...) value",
        )
    if isinstance(value, (DefiningRelSpec, ReverseRelSpec)):
        return value
    if isinstance(value, AttrSpec):
        raise EntityDefinitionError(
            code="entity-member-value-invalid",
            message=f"{where}: an attr(...) value under a Rel[...] annotation",
        )
    raise EntityDefinitionError(
        code="entity-member-value-invalid",
        message=f"{where}: a Rel[...] member declares exactly one rel(...) value",
    )


def _reject_reserved(
    where: str, py_name: str, axes: tuple[TemporalDimension, ...], *, injected: bool
) -> None:
    if py_name in RESERVED_MEMBER_NAMES or py_name.startswith("model_"):
        raise EntityDefinitionError(
            code="entity-reserved-member-name",
            message=f"{where}: reuses a reserved query-root or introspection name",
        )
    if axes and py_name in STANDARD_TEMPORAL_NAMES and not injected:
        raise EntityDefinitionError(  # pragma: no cover - caught by the earlier body scan
            code="entity-reserved-member-name",
            message=f"{where}: the framework supplies the standard temporal members",
        )


def _reject_shadowed_class_names(cls_name: str, ns: dict[str, object]) -> None:
    """Reject a class-body name that would take a reserved class-level name.

    The declaration surface answers only names the class object does not already
    carry, so a body binding — a member's declaration value, a method, or a class
    variable — reusing one makes the declaration unreachable rather than merely
    shadowing it. An annotation-only member is caught by the member walk instead.
    """
    taken = sorted(RESERVED_MEMBER_NAMES & set(ns))
    if taken:
        raise EntityDefinitionError(
            code="entity-reserved-member-name",
            message=f"{cls_name}.{taken[0]}: reuses a reserved query-root or introspection name",
        )


def _reject_temporal_redeclaration(
    cls_name: str, annotations: dict[str, object], ns: dict[str, object]
) -> None:
    declared = sorted(set(STANDARD_TEMPORAL_NAMES) & (set(annotations) | set(ns)))
    if declared:
        raise EntityDefinitionError(
            code="entity-reserved-member-name",
            message=(
                f"{cls_name}.{declared[0]}: the framework temporal base supplies the standard "
                "temporal members family-wide"
            ),
        )


def _inject_temporal_members(
    annotations: dict[str, object], ns: dict[str, object], axes: tuple[TemporalDimension, ...]
) -> None:
    """Append the framework temporal members after every authored one.

    Canonical axis order — Valid Time first — so the shape owner's declaration
    reads exactly as a hand-authored body would.
    """
    for dimension in sorted(axes, key=lambda axis: axis.value):
        for py_name, column in _TEMPORAL_MEMBERS[dimension]:
            annotations[py_name] = Attr[_dt.datetime]
            ns[py_name] = AttrSpec(name=py_name, column=column)


def _axis_metadata(
    identity: EntityIdentity, axes: tuple[TemporalDimension, ...]
) -> tuple[AsOfAxisMetadata, ...]:
    return tuple(
        AsOfAxisMetadata(
            dimension=dimension,
            start_attribute=AttributeIdentity(identity, _TEMPORAL_MEMBERS[dimension][0][0]),
            end_attribute=AttributeIdentity(identity, _TEMPORAL_MEMBERS[dimension][1][0]),
        )
        for dimension in sorted(axes, key=lambda axis: axis.value)
    )


def _reject_incompatible_generation(
    primary_key: AttributePrimaryKey, base: object, where: str
) -> None:
    """A generating strategy needs an integral member (m-pk-gen)."""
    generation = getattr(primary_key, "generation", None)
    if isinstance(generation, (Max, Sequence)) and base is not int:
        raise EntityDefinitionError(
            code="entity-option-context-invalid",
            message=f"{where}: Max and Sequence generation require an integer member",
        )


def _relationship(
    identity: EntityIdentity, canonical: str, spec: RelSpec, shape: _Shape, where: str
) -> UnresolvedRelationshipDeclaration:
    if shape.multiplicity is Multiplicity.MANY and shape.nullable:
        raise EntityDefinitionError(
            code="entity-annotation-invalid",
            message=f"{where}: a to-many relationship is never `| None` — loaded-empty is `()`",
        )
    target = _entity_reference(shape, where)
    relationship = RelationshipIdentity(identity, canonical)
    order_by = tuple(
        UnresolvedRelationshipOrder(snake_to_camel(term.member), term.direction)
        for term in spec.order_by
    )
    if isinstance(spec, ReverseRelSpec):
        return UnresolvedReverseRelationshipDeclaration(
            identity=relationship,
            reverse_of=RelationshipReference(entity=target, name=snake_to_camel(spec.reverse_of)),
            order_by=order_by,
        )
    return UnresolvedDefiningRelationshipDeclaration(
        identity=relationship,
        cardinality=spec.cardinality,
        join=UnresolvedRelationshipJoin(
            source=AttributeIdentity(identity, snake_to_camel(spec.join[0])),
            target=AttributeReference(entity=target, name=snake_to_camel(spec.join[1])),
        ),
        dependent=spec.dependent,
        order_by=order_by,
    )


def _entity_reference(shape: _Shape, where: str) -> EntityReference:
    """The Entity Reference a ``Rel[T]`` annotation names.

    A class target and a qualified string are already exact; a bare string is
    relative to the declaring Entity's namespace. Resolution never consults
    module globals — the hub candidate set is the only scope.
    """
    if shape.base is not None:
        if not isinstance(shape.base, type) or _DECLARATION not in shape.base.__dict__:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: a relationship target is an Entity Class or its name",
            )
        return ExactEntityReference(declaration_of(shape.base).identity)
    namespace, dot, name = (shape.spelling or "").rpartition(".")
    if not name:
        raise EntityDefinitionError(
            code="entity-annotation-invalid",
            message=f"{where}: a relationship target names a nonempty Entity",
        )
    if not dot:
        return RelativeEntityReference(name)
    return ExactEntityReference(EntityIdentity(namespace, name))


def _target_name(
    relationships: tuple[UnresolvedRelationshipDeclaration, ...], canonical: str
) -> str:
    """The canonical Entity name a declared relationship points at."""
    for member in relationships:
        if member.identity.name != canonical:
            continue
        reference = (
            member.join.target.entity
            if isinstance(member, UnresolvedDefiningRelationshipDeclaration)
            else member.reverse_of.entity
        )
        match reference:
            case ExactEntityReference(target):
                return target.name
            case RelativeEntityReference(name):
                return name
    return canonical  # pragma: no cover - every installed descriptor has its declaration


# --------------------------------------------------------------------------- #
# Pydantic field installation
# --------------------------------------------------------------------------- #


def _install_fields(
    annotations: dict[str, object],
    ns: dict[str, object],
    shapes: dict[str, _Shape],
    vo_classes: dict[str, type],
    many_py: set[str],
    *,
    axis_governed: frozenset[str],
) -> None:
    """Rewrite the class body into ordinary Pydantic field declarations.

    ``Attr[T]`` collapses to ``T`` so Pydantic builds an inner-typed field, the
    declaration value leaves the namespace, and a member whose absence is
    representable takes the matching Python default: ``None`` for a nullable
    member or a framework-stamped axis member, and the empty tuple for a Many
    occurrence.
    """
    for py_name, shape in shapes.items():
        annotations[py_name] = _field_annotation(shape)
        if shape.multiplicity is Multiplicity.MANY:
            ns[py_name] = ()
        elif shape.nullable or py_name in axis_governed:
            ns[py_name] = None
        else:
            ns.pop(py_name, None)
    for py_name, vo_class in vo_classes.items():
        multiplicity = Multiplicity.MANY if py_name in many_py else Multiplicity.ONE
        ns[f"_validate_vo_{py_name}"] = _value_object_validator(py_name, vo_class, multiplicity)
    ns["__annotations__"] = annotations


def _field_annotation(shape: _Shape) -> object:
    inner = cast("type", shape.base)
    if shape.multiplicity is Multiplicity.MANY:
        return tuple[inner, ...]
    if shape.nullable:
        return inner | None
    return inner


def _value_object_validator(py_name: str, vo_class: type, multiplicity: Multiplicity) -> Any:
    """A ``mode="before"`` validator enforcing "a Value Object member is an instance".

    Pydantic coerces a plain mapping into a declared nested model even under
    strict mode, so this explicit check is the enforcement point for spec §2's
    Value Object input policy.
    """

    def _validate(_cls: type, value: object) -> object:
        # Pydantic distinguishes a `(cls, value)` validator from a `(value, info)`
        # one only by `isinstance(func, classmethod)`, hence the explicit wrap
        # below even though this validator never reads `cls`.
        if value is None:
            return value
        if multiplicity is Multiplicity.MANY:
            if not isinstance(value, tuple):
                raise TypeError(
                    f"{py_name}: a many Value Object member requires a tuple of "
                    f"{vo_class.__name__!r} instances, not {type(value).__name__!r}"
                )
            items = cast("tuple[object, ...]", value)
            for item in items:
                if not isinstance(item, vo_class):
                    raise TypeError(
                        f"{py_name}: element {item!r} is not a {vo_class.__name__!r} instance "
                        "(Value Objects are instances only, never a raw mapping)"
                    )
            return items
        if not isinstance(value, vo_class):
            raise TypeError(
                f"{py_name}: a Value Object member requires a {vo_class.__name__!r} instance, "
                f"not {type(value).__name__!r} (never a raw mapping)"
            )
        return value

    bound = cast("Any", classmethod(_validate))
    return field_validator(py_name, mode="before")(bound)
