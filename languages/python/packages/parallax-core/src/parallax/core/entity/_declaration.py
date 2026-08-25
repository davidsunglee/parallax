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
from parallax.core.entity._expressions import AttributeRef, RelationshipRef, snake_to_camel
from parallax.core.entity._members import (
    AbstractSubtype,
    Attr,
    AttrSpec,
    ConcreteSubtype,
    DefiningRelSpec,
    Document,
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
    DerivedAxis,
    EntityIdentity,
    EntityReference,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Max,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    NullPlacement,
    PersistenceMode,
    RelationshipIdentity,
    RelationshipReference,
    RelativeEntityReference,
    Sequence,
    StorageContainer,
    StorageLayout,
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
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    default_column_name,
    derive_primary_key_index,
    derive_temporal_structure,
    designate_framework_owned,
    resolve_entity_reference,
    temporality_profile,
    value_object_metadata,
)
from parallax.core.metamodel import AbstractSubtype as AcceptedAbstractSubtype
from parallax.core.metamodel import ConcreteSubtype as AcceptedConcreteSubtype
from parallax.core.metamodel import Document as AcceptedDocument
from parallax.core.metamodel._temporal_structure import TEMPORAL_MEMBERS

__all__ = [
    "DECLARATION_MEMBER_NAMES",
    "FRAMEWORK_MINT",
    "FRAMEWORK_NAME_PREFIX",
    "LIFECYCLE_STATE_SLOT",
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
is never a Domain Model candidate.
"""

FRAMEWORK_NAME_PREFIX: Final = "__parallax_"
"""The prefix carried by the framework's own private bindings, which no
declaration of any kind may author: the class markers the engine puts on a
declared class, the private slots it puts on an instance, and the
``__parallax_document__`` renderer every Value Object serializes itself through.

The framework's public bindings sit outside this prefix, and each is reserved by
the rule that owns it rather than by this one: the copy verb ``edit``, the pickle
entry point ``__reduce_ex__``, and the query-root and introspection spellings by
name (:data:`RESERVED_MEMBER_NAMES`), Pydantic's ``model_config`` by the
``model_*`` namespace rule, and the injected temporal members by the
canonical-name rule that runs on a family extending a temporal root. What the
prefix covers is only what a declaration never names, which is why reserving the
whole prefix rather than enumerating it stays correct as markers and slots are
added, and why the reservation can be total: it applies to every Entity and Value
Object class body alike, and only a framework root — the framework declaring
itself — binds under it.

What it protects is that no class body shadows one of those bindings: a body
binding under one of these names answers every ordinary read the framework's own
value would answer, and a ``functools.cached_property`` spelled under one is
worse than a shadow — the edit surface reads a derived cache off the class, so
such a binding would have an edited copy recompute the author's answer in place
of the state it carried. The rule reads the class body as authored, which makes
it an authoring rule and not a barrier: a name a descriptor's ``__set_name__``
installs is outside the pre-creation namespace scan this rule performs, and a
name assigned once the class exists is outside class-creation checks altogether.
Auditing the constructed class would catch the descriptor and still not prevent
the later assignment, which is why the rule stays where the collision is
written."""

_KIND: Final = "__parallax_kind__"
_AXES: Final = "__parallax_framework_axes__"
_DECLARATION: Final = "__parallax_declaration__"
_MEMBERS: Final = "__parallax_members__"
_SHAPE: Final = "__parallax_shape__"

LIFECYCLE_STATE_SLOT: Final = "__parallax_lifecycle__"
"""The one per-instance slot a materialized node's lifecycle state occupies.

Entity Graph Construction attaches whatever opaque value the constructing
lifecycle's state factory returned and never interprets it, so a lifecycle
package's own state — the Snapshot slice's views, pin, and edge, or a future
managed slice's entirely different record — travels under one name that Entity
neither reads nor exposes. One slot rather than a per-fact family is what keeps
Entity free of every lifecycle's vocabulary.

The value lands in the instance ``__dict__`` through ``object.__setattr__``,
alongside field values but outside the Pydantic field set, so it is invisible to
canonical serialization, equality, and ``repr``. Pickling is the one conversion
it does not merely disappear from: the instance dictionary is what a pickle
carries, and a lifecycle's private record of a live read has no truthful form on
the other side of a process boundary, so a value holding this slot is refused at
the pickle entry point rather than quietly emptied of it. Emptying is what
remains for the conversions that reach ``Entity.__getstate__`` without passing
that entry point."""

_ATTR_TEXT = re.compile(r"^Attr\[(?P<inner>.+)\]$", re.DOTALL)
_REL_TEXT = re.compile(r"^Rel\[(?P<inner>.+)\]$", re.DOTALL)
_OPTIONAL_TEXT = re.compile(r"^Optional\[(?P<inner>.+)\]$", re.DOTALL)
_TUPLE_TEXT = re.compile(r"^tuple\[(?P<inner>.+)\]$", re.DOTALL)

DECLARATION_MEMBER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "identity",
        "container",
        "persistence",
        "layout",
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

_COPY_VERB_NAME: Final = "edit"
"""The instance-level copy verb both frontends install.

A declared member of this name installs its descriptor over the verb and silently
disables editing for that class, which is the same harm on either kind — so this
is one of the two public framework bindings reserved against an Entity Class and
a Value Object Class alike.
"""

_PICKLE_ENTRY_NAME: Final = "__reduce_ex__"
"""The pickle entry point, which the framework owns on either kind.

``pickle``'s own dispatch reaches a value through this one name; ``__reduce__``
and ``__getstate__`` are what ``object.__reduce_ex__`` consults once it has been
entered. So this is where an Entity refuses to let a materialized node's
lifecycle state cross a process boundary, and a class body authoring the name
would replace that refusal rather than run after it. Reserving exactly this name
is also what keeps the other two authorable: an authored ``__reduce__`` or
``__getstate__`` still runs, downstream of a guard that has already passed. What
the reservation cannot reach is a caller who replaces the dispatch itself, which
is a choice made at the pickling site rather than in a class body.

The reservation holds on a Value Object Class for the reason the copy verb's
does — what a value of either kind becomes outside the process is derived from
instance state the framework owns, so neither kind authors the door it leaves
through.
"""

# The reserved query-root and introspection spellings plus the declaration
# members above. A member reusing one either loses to the metaclass declaration at
# class level or wins over the frontend's own binding, so the collision is
# rejected where it is authored. Every name here is part of the Entity surface: a
# Value Object Class carries no query root and no declaration, so the family is
# Entity-only, and only the copy verb beside it holds on both kinds.
RESERVED_MEMBER_NAMES: Final[frozenset[str]] = frozenset(
    {
        "all",
        "where",
        "narrow",
        "include",
        "as_of",
        "as_of_range",
        "history",
        "meta",
        "descriptor",
        _COPY_VERB_NAME,
        *DECLARATION_MEMBER_NAMES,
    }
)


def _python_spelling(canonical: str) -> str:
    """The Python member spelling a framework member's canonical name comes from.

    The authoring boundary converts a member's Python spelling to its canonical
    name with :func:`snake_to_camel`, and the shared convention table declares
    the framework's own members canonically, so the spelling an author reads and
    queries through is that conversion inverted — the same lowercase-and-split
    fold :func:`default_column_name` applies.
    """
    return default_column_name(canonical)


STANDARD_TEMPORAL_NAMES: Final[tuple[str, ...]] = tuple(
    _python_spelling(endpoint.name)
    for _, endpoints in sorted(TEMPORAL_MEMBERS.items(), key=lambda item: item[0].value)
    for endpoint in endpoints
)
"""The framework temporal member names as Python spells them, in canonical axis order."""

_RESERVED_TEMPORAL_NAMES: Final[frozenset[str]] = frozenset(
    endpoint.name for endpoints in TEMPORAL_MEMBERS.values() for endpoint in endpoints
)


@dataclass(frozen=True, slots=True)
class EntityHeader:
    """The seven class-header keywords, exactly as the class statement spelled them.

    Deliberately untyped: the metaclass types the keywords for the developer's
    type checker, while the engine still has to validate what a dynamically
    created class actually passed, and each rejection carries a stable code.
    """

    table: object = None
    name: object = None
    namespace: object = None
    persistence: object = None
    layout: object = None
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
    layout: StorageLayout | None
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
    members: dict[str, AttributeMetadata | ValueObjectMetadata]
    """Each Python member name to the accepted Metadata its declaration built —
    the same object the ``Attr`` descriptor installs, so a rule stated over a
    member reaches the identical facts from a name and from an expression."""
    pk_py: frozenset[str]
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
    """Whether ``candidate`` is a domain Entity Class — a model candidate.

    The total, nonthrowing counterpart of :func:`declaration_of`. A framework
    root carries the Entity kind marker but no declaration, so it answers false
    here exactly as it is refused as a Domain Model argument.
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
    ignored_types: tuple[type, ...] = (),
) -> type:
    """Build one declared class, rejecting anything outside the grammar.

    Every Parallax class is implicitly frozen, so the engine sets the Pydantic
    configuration itself and forwards no class-header keyword to Pydantic. A
    framework root carries markers only: no identity, no declaration payload, no
    header rules, and it is never a Domain Model candidate.

    ``ignored_types`` is the frontend's own class-body descriptor vocabulary —
    a query-root descriptor a frontend base installs is a class attribute
    Pydantic would otherwise refuse as an unannotated field at import time. The
    engine still owns the configuration; a frontend contributes only the types
    its own bases install. It reaches ONLY a framework root's own configuration,
    the one body that installs such a descriptor: a declared class body carries
    members and nothing else, so it keeps Pydantic's unannotated-attribute
    rejection whole rather than inheriting a blanket exemption for a type it
    never binds.
    """
    if mint is None:
        # Every declared kind, and before the configuration below, which itself
        # binds a reserved ``model_*`` name: the rejection is about what the
        # class body authored. Only a framework root is exempt, because the
        # framework's own markers and slots are what the reservation protects.
        _reject_shadowed_class_names(cls_name, ns, kind)
    ns["model_config"] = ConfigDict(
        frozen=True, ignored_types=ignored_types if mint is not None else ()
    )
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

    On Python 3.13 the live annotation objects sit eagerly in
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
    return _resolve_deferred(annotate)  # pragma: no cover - deferred namespace only on 3.14+


def _resolve_deferred(annotate: object) -> dict[str, object]:
    """Recover deferred (PEP 649 / PEP 749) class-body annotations.

    Reached only on Python 3.14+, where a class declared without
    ``from __future__ import annotations`` carries an ``__annotate_func__``
    instead of an eager ``__annotations__`` mapping; 3.13 always takes
    the eager path. Evaluated in ``VALUE`` format to recover the same live
    objects the eager path returns. The ``sys.version_info`` guard is a
    static-typing shim that keeps the 3.14-only ``annotationlib`` import off
    Pyright's 3.13 path; it is never taken at runtime because this function runs
    only on 3.14+.
    """
    if sys.version_info < (3, 14):  # pragma: no cover - typing shim; runs only on 3.14+
        return {}
    import annotationlib  # pragma: no cover - Python 3.14+ only (PEP 649 / PEP 749)

    return dict(  # pragma: no cover - Python 3.14+ only (PEP 649 / PEP 749)
        annotationlib.call_annotate_function(annotate, annotationlib.Format.VALUE)
    )


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

    A relationship target is read as a spelling and never evaluated: the composed
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
        _reject_reserved(where, py_name, DeclarationKind.VALUE_OBJECT)
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

    _install_fields(annotations, ns, shapes, nested_classes, many_py, framework_owned=frozenset())
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
    if axes:
        _reject_temporal_redeclaration(cls_name, annotations, ns)
    if shape_owner:
        _inject_temporal_members(annotations, ns, axes)
    axis_members = _axis_metadata(identity, axes) if shape_owner else ()

    attributes: list[AttributeMetadata] = []
    relationships: list[UnresolvedRelationshipDeclaration] = []
    occurrences: list[ValueObjectOccurrenceDeclaration] = []
    # Each installed descriptor's own member Metadata, which is what makes an
    # assignment judgeable without a model. A Value Object occurrence is expanded
    # through the compiler's own seam, so a descriptor carries the identical shape
    # the accepted model publishes.
    members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
    column_to_py: dict[str, str] = {}
    name_to_py: dict[str, str] = {}
    py_to_name: dict[str, str] = {}
    relationship_py: dict[str, str] = {}
    relationship_shapes: dict[str, RelationshipAnnotation] = {}
    pk_py: set[str] = set()
    vo_classes: dict[str, type] = {}
    many_py: set[str] = set()
    shapes: dict[str, _Shape] = {}
    canonical_seen: set[str] = set()

    for py_name, annotation in list(annotations.items()):
        where = f"{cls_name}.{py_name}"
        _reject_reserved(where, py_name, DeclarationKind.ENTITY)
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
        column = (
            attr_spec.column if attr_spec.column is not None else default_column_name(canonical)
        )
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
            occurrence = ValueObjectOccurrenceDeclaration(
                name=canonical,
                storage=Column(column),
                shape=shape_of(vo_class).shape,
                multiplicity=shape.multiplicity,
                nullable=shape.nullable,
            )
            occurrences.append(occurrence)
            members[canonical] = value_object_metadata(identity, occurrence)
            continue
        if shape.multiplicity is Multiplicity.MANY:
            raise EntityDefinitionError(
                code="entity-annotation-invalid",
                message=f"{where}: only a Value Object occurrence is spelled `tuple[X, ...]`",
            )
        if attr_spec.primary_key is not NOT_PRIMARY_KEY:
            pk_py.add(py_name)
            _reject_incompatible_generation(attr_spec.primary_key, shape.base, where)
        attribute = _attribute(identity, canonical, column, attr_spec, shape, where)
        attributes.append(attribute)
        members[canonical] = attribute

    # Both frontends derive the designation through the one shared rule, and the
    # descriptors installed below carry the designated Metadata — which is what
    # lets a class composed into no model judge an assignment the way the whole
    # model would.
    declared_attributes = designate_framework_owned(attributes, axis_members)
    members.update({attribute.identity.name: attribute for attribute in declared_attributes})
    framework_owned_py = frozenset(
        name_to_py[attribute.identity.name]
        for attribute in declared_attributes
        if attribute.framework_owned
    )
    _install_fields(
        annotations, ns, shapes, vo_classes, many_py, framework_owned=framework_owned_py
    )
    container = _container(cls_name, header)
    ns[_DECLARATION] = EntityDeclaration(
        identity=identity,
        container=container,
        persistence=_persistence(cls_name, header),
        layout=_layout(cls_name, header),
        attributes=declared_attributes,
        relationships=tuple(relationships),
        value_objects=tuple(occurrences),
        as_of_axes=axis_members,
        inheritance=_accepted_inheritance(role, parent),
        indices=_indices(
            identity, container, declared_attributes, axis_members, header.indices, py_to_name
        ),
    )
    ns[_MEMBERS] = MemberNames(
        column_to_py=column_to_py,
        name_to_py=name_to_py,
        py_to_name=py_to_name,
        relationship_py=relationship_py,
        relationship_shapes=relationship_shapes,
        members={py_name: members[canonical] for py_name, canonical in py_to_name.items()},
        pk_py=frozenset(pk_py),
        vo_classes=vo_classes,
    )
    cls = _pydantic_class(mcs, cls_name, bases, ns)
    # Every reference this class hands out is seeded with the Entity's EXACT
    # canonical spelling, so everything downstream that re-emits it — a
    # serialized query, a durable write document — carries an identity two
    # namespaces sharing a local name cannot confuse. Nothing downstream builds
    # a spelling of its own; they all re-emit this one.
    for py_name, canonical in py_to_name.items():
        setattr(
            cls,
            py_name,
            Attr(AttributeRef(identity.canonical, canonical), py_name, members[canonical]),
        )
    for canonical, py_name in relationship_py.items():
        setattr(
            cls,
            py_name,
            Rel(
                RelationshipRef(identity.canonical, canonical),
                py_name,
                _target_spelling(identity, tuple(relationships), canonical),
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


def _layout(cls_name: str, header: EntityHeader) -> StorageLayout | None:
    """The Storage Layout this class itself declares, with its name resolved.

    ``Document`` carries no payload in the common case, so the class object
    reads as naturally as an instance. The conventional column name is supplied
    here rather than left to a consumer, so accepted metadata never carries an
    unresolved one; whether this class may declare a layout at all is a
    family-wide question formation answers.
    """
    declared: object = header.layout
    if declared is Document:
        declared = Document()
    if declared is None:
        return None
    if not isinstance(declared, Document):
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{cls_name}: layout= takes Document or Document(column=...), got {declared!r}",
        )
    # A frozen dataclass records its payload without checking it, so the declared
    # field type is a promise to the type checker rather than a fact about what a
    # header actually passed.
    column = cast("object", declared.column)
    if not isinstance(column, str) or not column:
        raise EntityDefinitionError(
            code="entity-header-invalid-value",
            message=f"{cls_name}: Document(column=) takes a nonempty string, got {column!r}",
        )
    return AcceptedDocument(Column(column))


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
    identity: EntityIdentity,
    container: StorageContainer | None,
    attributes: tuple[AttributeMetadata, ...],
    as_of_axes: tuple[AsOfAxisMetadata, ...],
    declared: object,
    py_to_name: dict[str, str],
) -> tuple[IndexMetadata, ...]:
    """The derived primary-key Index followed by the declared ones.

    A declared component names a Python member; an unknown name lowers through
    the deterministic conversion so foundational resolution can locate and report
    it. The primary-key Index is never declared, so the two sets are disjoint.
    """
    derived = derive_primary_key_index(
        entity=identity, container=container, attributes=attributes, as_of_axes=as_of_axes
    )
    authored = _declared_indices(identity, declared, py_to_name)
    return authored if derived is None else (derived, *authored)


def _declared_indices(
    identity: EntityIdentity, declared: object, py_to_name: dict[str, str]
) -> tuple[IndexMetadata, ...]:
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


def _reject_reserved(where: str, py_name: str, kind: DeclarationKind) -> None:
    reason = _reserved_name_reason(py_name, kind)
    if reason is not None:
        raise EntityDefinitionError(
            code="entity-reserved-member-name", message=f"{where}: {reason}"
        )


def _reject_shadowed_class_names(
    cls_name: str, ns: dict[str, object], kind: DeclarationKind
) -> None:
    """Reject a class-body name that would take a reserved class-level name.

    The declaration surface answers only names the class object does not already
    carry, so a body binding — a member's declaration value, a method, or a class
    variable — reusing one makes the declaration unreachable rather than merely
    shadowing it. An annotation-only member is caught by the member walk instead,
    which is why both frontends run both checks.

    The ``model_*`` prefix is checked here for the same reason it is checked
    there: an unannotated ``def model_copy`` is a binding rather than a declared
    member, and admitting it would reinstate a copy door the edit surface
    refuses. This runs against the body as authored, before the engine installs
    its own configuration under one of those names — which is also what lets the
    framework's own prefix be reserved against the body while the engine keeps
    binding markers under it.
    """
    for name in sorted(ns):
        reason = _reserved_name_reason(name, kind)
        if reason is not None:
            raise EntityDefinitionError(
                code="entity-reserved-member-name", message=f"{cls_name}.{name}: {reason}"
            )


def _reserved_name_reason(py_name: str, kind: DeclarationKind) -> str | None:
    """Why a class body of ``kind`` may not author ``py_name``, or ``None``.

    The reservations that hold whatever a declaration is come first: the
    framework's own prefix (:data:`FRAMEWORK_NAME_PREFIX`), because what a binding
    under it takes is one of the framework's own private bindings rather than a
    member surface; Pydantic's namespace, because both kinds are Pydantic models;
    the copy verb, because both kinds install one; and the pickle entry point,
    because it is where ``pickle``'s own dispatch enters either kind. Only the
    Entity surface names follow.
    """
    if py_name.startswith(FRAMEWORK_NAME_PREFIX):
        return (
            f"the `{FRAMEWORK_NAME_PREFIX}` prefix names the framework's own private bindings — "
            "its class markers, its instance slots, and the renderer a Value Object serializes "
            "itself through — which a declaration may not bind"
        )
    if py_name.startswith("model_"):
        return "the `model_*` namespace is reserved by Pydantic"
    if py_name == _COPY_VERB_NAME:
        return (
            f"reuses the instance-level copy verb `{_COPY_VERB_NAME}`, which a declared member "
            "of that name would overwrite"
        )
    if py_name == _PICKLE_ENTRY_NAME:
        return (
            f"reuses `{_PICKLE_ENTRY_NAME}`, the pickle entry point the framework owns — an "
            "authored one runs before the refusal that keeps a materialized node's lifecycle "
            "state from crossing a process boundary; author `__reduce__` or `__getstate__` "
            "instead, both of which still run"
        )
    if kind is DeclarationKind.ENTITY and py_name in RESERVED_MEMBER_NAMES:
        return "reuses a reserved query-root or introspection name"
    return None


def _reject_temporal_redeclaration(
    cls_name: str, annotations: dict[str, object], ns: dict[str, object]
) -> None:
    """Reject a class-body name below a temporal base that takes a framework temporal name.

    The reservation is on the *canonical* name the body would resolve to, so one
    rule covers the Python spelling the framework injects, a literal canonical
    spelling, and an explicit ``name=`` that renames onto one. It runs before the
    injection so a redeclaration can never be silently overwritten.
    """
    declared = sorted(
        py_name
        for py_name in set(annotations) | set(ns)
        if _body_canonical_name(py_name, ns.get(py_name)) in _RESERVED_TEMPORAL_NAMES
    )
    if declared:
        raise EntityDefinitionError(
            code="entity-reserved-member-name",
            message=(
                f"{cls_name}.{declared[0]}: the framework temporal base supplies the standard "
                "temporal members family-wide"
            ),
        )


def _body_canonical_name(py_name: str, value: object) -> str:
    if isinstance(value, (AttrSpec, DefiningRelSpec, ReverseRelSpec)) and value.name is not None:
        return value.name
    return snake_to_camel(py_name)


def _inject_temporal_members(
    annotations: dict[str, object], ns: dict[str, object], axes: tuple[TemporalDimension, ...]
) -> None:
    """Append the framework temporal members after every authored one.

    The shared derivation supplies the endpoints, so a class declaration and a
    descriptor declaring the same Temporality Profile reach the seam carrying the
    same members in the same canonical axis order — Valid Time first.
    """
    for axis in _derived_axes(axes):
        for endpoint in (axis.start, axis.end):
            py_name = _python_spelling(endpoint.name)
            annotations[py_name] = Attr[_dt.datetime]
            ns[py_name] = AttrSpec(column=endpoint.column)


def _axis_metadata(
    identity: EntityIdentity, axes: tuple[TemporalDimension, ...]
) -> tuple[AsOfAxisMetadata, ...]:
    return tuple(
        AsOfAxisMetadata(
            dimension=axis.dimension,
            start_attribute=AttributeIdentity(identity, axis.start.name),
            end_attribute=AttributeIdentity(identity, axis.end.name),
        )
        for axis in _derived_axes(axes)
    )


def _derived_axes(axes: tuple[TemporalDimension, ...]) -> tuple[DerivedAxis, ...]:
    """The As-Of Axes the temporal base's dimensions derive.

    A framework temporal base selects dimensions where a descriptor spells a
    profile, so the dimensions are routed back through the profile they name to
    reach the one derivation both frontends share.
    """
    return derive_temporal_structure(temporality_profile(axes))


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
        UnresolvedRelationshipOrder(
            snake_to_camel(term.member),
            term.direction,
            term.nulls if term.nulls is not None else NullPlacement.NULLS_LAST,
        )
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
    module globals — the composed candidate set is the only scope.
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


def _target_spelling(
    identity: EntityIdentity,
    relationships: tuple[UnresolvedRelationshipDeclaration, ...],
    canonical: str,
) -> str:
    """The canonical spelling of the Entity a declared relationship points at.

    Purely lexical, exactly as reference resolution is: a relative target adopts
    the declaring Entity's namespace and an exact one passes through. Keeping the
    namespace is what lets a path continuing past this hop name its target
    unambiguously when a second namespace declares the same local name.
    """
    for member in relationships:
        if member.identity.name != canonical:
            continue
        reference = (
            member.join.target.entity
            if isinstance(member, UnresolvedDefiningRelationshipDeclaration)
            else member.reverse_of.entity
        )
        return resolve_entity_reference(identity, reference).canonical
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
    framework_owned: frozenset[str],
) -> None:
    """Rewrite the class body into ordinary Pydantic field declarations.

    ``Attr[T]`` collapses to ``T`` so Pydantic builds an inner-typed field, the
    declaration value leaves the namespace, and a member whose absence is
    representable takes the matching Python default: ``None`` for a nullable
    member or a framework-owned one, and the empty tuple for a Many occurrence.

    A framework-owned member is defaulted because the caller never supplies its
    value and is refused for trying, so requiring one at construction would make
    the Entity unconstructible; the value the framework supplies arrives by
    hydration, which builds through Pydantic's validation-free path.
    """
    for py_name, shape in shapes.items():
        annotations[py_name] = _field_annotation(shape)
        if shape.multiplicity is Multiplicity.MANY:
            ns[py_name] = ()
        elif shape.nullable or py_name in framework_owned:
            ns[py_name] = None
        else:
            ns.pop(py_name, None)
    for py_name in framework_owned:
        ns[f"_reject_framework_owned_{py_name}"] = _framework_owned_validator(py_name)
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


def _framework_owned_validator(py_name: str) -> Any:
    """A ``mode="before"`` validator refusing a caller-authored framework-owned value.

    The refusal belongs at construction, where the mistake is, rather than
    several steps later when a row is derived. It raises ``ValueError`` so
    Pydantic reports it as an ordinary ``ValidationError`` alongside every other
    rejection of that call — construction is not an edit, so it is deliberately
    not the edit family's refusal. Hydration is unaffected: it builds through
    ``model_construct`` and never reaches the validating constructor.

    A defaulted member skips its validators, so omitting the member is how a
    caller legitimately constructs one.
    """

    def _validate(_cls: type, value: object) -> object:
        # Pydantic distinguishes a `(cls, value)` validator from a `(value, info)`
        # one only by `isinstance(func, classmethod)`, hence the explicit wrap
        # below even though this validator never reads `cls`.
        raise ValueError(
            f"{py_name}: framework-owned members are supplied by the framework and are never "
            "authored — omit it and let the write path stamp it"
        )

    bound = cast("Any", classmethod(_validate))
    return field_validator(py_name, mode="before")(bound)


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
