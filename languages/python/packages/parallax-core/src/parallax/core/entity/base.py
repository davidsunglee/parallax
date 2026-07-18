"""The entity base class and its metaclass (support scope, definition half).

Developers author frozen Pydantic entity classes; a ``ModelMetaclass`` subclass
unwraps the ``Attr[T]`` / ``Rel[T]`` annotations so Pydantic builds ordinary
inner-typed fields, installs the typed class-level descriptors, and compiles the
class body into a canonical :class:`~parallax.core.descriptor.Entity` record.
Reserved-name and canonical-name-collision checks run at class-definition time.
The class carries no information absent from the descriptor schema.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Self, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict

# A documented, deliberate reach into Pydantic internals — the SQLAlchemy
# Mapped[T]-pattern realization technique python.md §2 pins; no public
# Pydantic seam offers a metaclass hook.
from pydantic._internal._model_construction import ModelMetaclass

from parallax.core import inheritance as _inheritance
from parallax.core.descriptor import (
    UNSET,
    AsOfAttribute,
    DescriptorError,
    validate_entity,
    validate_optimistic_locking_root_owned,
)
from parallax.core.descriptor import Attribute as AttributeRecord
from parallax.core.descriptor import Entity as EntityRecord
from parallax.core.descriptor import Inheritance as InheritanceRecord
from parallax.core.descriptor import Metamodel as MetamodelRecord
from parallax.core.descriptor import Relationship as RelationshipRecord
from parallax.core.descriptor import ValueObject as ValueObjectRecord
from parallax.core.descriptor.neutral_type import infer_neutral_type as _infer_neutral_type_lookup
from parallax.core.descriptor.neutral_type import snake_to_camel
from parallax.core.descriptor.records import Unset as _UnsetType
from parallax.core.entity._validation import require_entity_record
from parallax.core.entity.errors import (
    EntityDefinitionError,
    NameCollisionError,
    RegistryCollisionError,
    ReservedNameError,
)
from parallax.core.entity.expressions import (
    Attr,
    AttributeRef,
    Predicate,
    Rel,
    RelationshipRef,
)
from parallax.core.entity.fields import FieldSpec, RelationshipSpec
from parallax.core.entity.statement import Statement, build_statement
from parallax.core.entity.value_object import (
    ValueObject,
    structure_of,
    to_document,
    vo_field_info,
    vo_instance_validator,
)
from parallax.core.op_algebra import All, Narrow, Operation, validate_operation

__all__ = [
    "Concrete",
    "Entity",
    "EntityConfig",
    "EntityMeta",
    "EntityRegistry",
    "FamilyRoot",
    "FrameworkOwnedAxisError",
    "ModelCopyError",
    "ProvenanceError",
    "ScopedMetamodel",
    "WireNames",
    "camel_to_snake",
    "canonical_row",
    "changed_fields",
    "default_registry",
    "effective_change_set",
    "entity_record_of",
    "entity_records",
    "entity_registry",
    "full_row",
    "metamodel",
    "primary_key_row",
    "registry_of",
    "resolve_entity_class",
    "snake_to_camel",
    "wire_names_of",
]

# Names reserved for the query root and introspection surface, plus the Pydantic
# ``model_*`` space; a field may not reuse them (rejected at class definition).
_RESERVED: frozenset[str] = frozenset(
    {"where", "narrow", "include", "as_of", "as_of_range", "history", "meta", "descriptor"}
)

_ATTR_STR = re.compile(r"^Attr\[(?P<inner>.+)\]$", re.DOTALL)
_REL_STR = re.compile(r"^Rel\[(?P<inner>.+)\]$", re.DOTALL)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# The metamodel registry (ledger D-20, design doc 37 DQ7a Option A): the class
# -> its compiled metamodel record stays a single process-wide, CLASS-keyed map
# (kept off the class itself so the descriptor stays invisible to the public
# attribute surface) -- a Python class object is already collision-safe, no
# scoping needed there. Canonical NAME -> class is where a collision is
# possible (two DIFFERENT classes sharing one literal name), so THAT map is
# scoped: every entity class registers into an explicit `EntityRegistry` (the
# class-definition `registry=` keyword, `EntityMeta.__new__`), never a single
# flat dict.
_ENTITY_BY_CLASS: dict[type, EntityRecord] = {}
_REGISTRY_OF_CLASS: dict[type, EntityRegistry] = {}


class EntityRegistry:
    """An explicit, independently-collision-checked entity class registration
    scope (ledger D-20, design doc 37 DQ7a Option A, David-resolved).

    Every entity class declares (or, for an inheritance-family subclass,
    inherits from its family root) exactly one registry at class-definition
    time: ``class Person(Entity, frozen=True, registry=animals)``. Omitting
    ``registry=`` registers into the process :func:`default_registry` --
    zero-ceremony apps are unaffected, since every class this frontend ever
    compiled before D-20 landed there implicitly, under the same name.

    A registry's own canonical-name space is independently collision-checked
    (:class:`~parallax.core.entity.errors.RegistryCollisionError`): the SAME
    name registered twice in the SAME registry raises immediately and loudly,
    naming both classes -- the replacement for the historical silent
    last-write-wins module-dict write -- but the SAME name in TWO DIFFERENT
    registries coexists (the D-20 fix itself). :meth:`resolve` / :meth:`records`
    walk only this registry and its own ``parent`` chain, so an unrelated
    sibling registry's same-named class is never visible from here (never
    "every class ever compiled" -- the scoping guarantee `Entity.where` /
    ``.include`` / ``.narrow``, dynamic relationship hops, ``AttributeExpr.set``,
    and `parallax.core.entity.graph_state` all now rely on).

    ``parent`` (default: the process default registry) lets a scoped registry
    inherit everything the default registry already sees: a new registry
    typically exists to carve out ONE colliding canonical name (e.g. a second,
    differently-shaped ``Person``), not to re-declare an app's whole
    vocabulary from scratch. Pass ``parent=None`` for a fully isolated
    registry sharing nothing with the default.

    SHADOWING (S1, COR-3 Phase 7 increment 7 round-2 -- the pin the D-20
    design left implicit): declaring a name in a CHILD registry that ALSO
    exists somewhere in its own ``parent`` chain is never a collision --
    :meth:`_register`'s own collision check looks only at THIS registry's
    ``_by_name``, never the ``parent`` chain -- and the child's own entry
    SHADOWS the parent's from then on, the natural lexical-scope answer (an
    inner scope's own binding always wins over an outer one's same-named
    binding, never an error): :meth:`resolve` / :meth:`records` return the
    child's own registration; the PARENT registry itself is entirely
    unaffected (still resolves its own class under that name, to any OTHER
    caller holding a reference to it directly) -- only a lookup THROUGH the
    child sees the shadow.
    """

    __slots__ = ("_by_name", "_parent")

    def __init__(self, *, parent: EntityRegistry | None | _UnsetType = UNSET) -> None:
        self._parent: EntityRegistry | None = (
            default_registry() if isinstance(parent, _UnsetType) else parent
        )
        self._by_name: dict[str, type[BaseModel]] = {}

    def _register(self, name: str, cls: type[BaseModel]) -> None:
        """Register ``cls`` under canonical ``name`` in THIS registry's own
        scope (never the ``parent`` chain): a same-named prior registration
        in this SAME registry raises; the parent chain is never consulted or
        mutated here (a coexisting parent/foreign entry is untouched)."""
        existing = self._by_name.get(name)
        if existing is not None:
            raise RegistryCollisionError(
                f"entity name {name!r} is already registered (by {existing!r}) in this "
                f"registry; {cls!r} cannot reuse it here -- declare a distinct canonical "
                "name, or register it in a separate EntityRegistry (ledger D-20)"
            )
        self._by_name[name] = cls

    def resolve(self, name: str) -> type[BaseModel] | None:
        """The class registered under ``name`` within this registry's own
        scope: this registry's OWN registration if any, else its ``parent``'s
        -- never a sibling registry's (the D-20 scoping guarantee)."""
        cls = self._by_name.get(name)
        if cls is not None:
            return cls
        return self._parent.resolve(name) if self._parent is not None else None

    def own_names(self) -> dict[str, type[BaseModel]]:
        """A copy of THIS registry's own name -> class map (never the
        ``parent`` chain's) -- the module-scoped ``dict`` a pre-D-20 single-
        registry app's ``entity_registry()`` observed."""
        return dict(self._by_name)

    def records(self) -> dict[str, EntityRecord]:
        """Every entity record visible from this scope: the ``parent``
        chain's own, merged with this registry's own (this registry's own
        SHADOWS a same-named parent entry, mirroring :meth:`resolve`)."""
        merged: dict[str, EntityRecord] = (
            dict(self._parent.records()) if self._parent is not None else {}
        )
        merged.update(
            {
                name: _ENTITY_BY_CLASS[cls]
                for name, cls in self._by_name.items()
                if cls in _ENTITY_BY_CLASS
            }
        )
        return merged

    def metamodel(self) -> ScopedMetamodel:
        """This scope's :class:`~parallax.core.descriptor.Metamodel`, tagged
        with itself -- the D-20 wrap/meta bridge (correction 1): a caller that
        wants `db.find` (`parallax.snapshot.wrap`) to resolve THROUGH this
        registry connects a ``Database`` with THIS method's result, never a
        bare, untagged one."""
        return ScopedMetamodel(entities=tuple(self.records().values()), registry=self)


_default_registry: EntityRegistry | None = None


def default_registry() -> EntityRegistry:
    """The process-wide default :class:`EntityRegistry`: where an entity
    class lands when its declaration omits ``registry=`` (zero-ceremony)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = EntityRegistry(parent=None)
    return _default_registry


@dataclass(frozen=True, slots=True)
class ScopedMetamodel(MetamodelRecord):
    """A :class:`~parallax.core.descriptor.Metamodel` tagged with the
    :class:`EntityRegistry` that produced it (ledger D-20 correction 1's
    wrap/meta bridge): `parallax.snapshot.wrap` resolves a decoded row's class
    through THIS registry, never the process-global default, when a connected
    ``Database``'s metamodel carries one. A class-authored assembly
    (:func:`metamodel` over a NON-EMPTY class list) is ALWAYS tagged this way
    (S2, COR-3 Phase 7 increment 7 round-1 -- R4 residue fixed round-2: this
    docstring previously, incorrectly, still described a bare
    ``metamodel(classes)`` call as untagged, the pre-round-1 behavior). The
    genuinely UNSCOPED (untagged, plain) cases are narrower: a YAML-ingested
    `~parallax.core.descriptor.deserialize` result, :func:`metamodel`'s own
    EMPTY-list call (``metamodel([])`` -- no class/registry context to derive
    a scope from at all), and the introspection surface's bare-name lookup
    (`~parallax.core.entity.meta.meta("Name")`, which likewise has no class in
    hand). All three fall back to :func:`default_registry` unchanged:
    zero-ceremony apps, and the long-standing ingested-descriptor +
    installed-mirror pairing (``Database.connect(port, ingested_meta)``
    wrapping via a same-named class the DEFAULT registry independently
    holds), both keep today's behavior. Lives in ``parallax.core.entity``
    (never ``parallax.core.descriptor`` itself, which must not grow a
    dependency on entity classes -- the import-linter DAG constraint)."""

    registry: EntityRegistry | None = None


def registry_of(meta: MetamodelRecord) -> EntityRegistry:
    """The :class:`EntityRegistry` scope a connected ``Metamodel`` resolves
    classes through: its own tagged :class:`ScopedMetamodel` scope if it
    carries one, else :func:`default_registry` (ledger D-20 correction 1)."""
    if isinstance(meta, ScopedMetamodel) and meta.registry is not None:
        return meta.registry
    return default_registry()


def resolve_entity_class(meta: MetamodelRecord, name: str) -> type[BaseModel] | None:
    """The Python class ``name`` resolves to within ``meta``'s own D-20 scope
    (:func:`registry_of`) -- the sole seam `parallax.snapshot.wrap` uses to
    turn a decoded row's canonical entity name into a class, never the
    process-global registry directly."""
    return registry_of(meta).resolve(name)


class ModelCopyError(EntityDefinitionError):
    """A ``model_copy(update=...)`` call names an unassignable field (spec §3):
    unknown, primary-key, framework-owned, or a relationship."""


class ProvenanceError(ValueError):
    """An instance carries no Change Record (never produced via ``model_copy``)
    and cannot drive a sparse ``tx.update`` (spec §5)."""


class FrameworkOwnedAxisError(ValueError):
    """A fresh instance names an axis-governed attribute at construction (D-31,
    COR-3 Phase 8 increment 7 completion round): ``in_z``/``out_z`` (and,
    bitemporal, ``from_z``/``thru_z``) are stamped by the temporal write path
    itself — the milestone director derives every bound from the Clock
    Strategy and the verb's own window arguments (``business_from``/``until``
    on `insert_until`/`update_until`/`terminate_until`), never from
    caller-authored instance data. ``tx.insert``/``tx.insert_until`` raise
    this the moment the offending field is actually SET on the instance
    (``model_fields_set``) — replacing the pre-D-31 behavior of silently
    discarding it at the write path — naming the framework-owned attribute so
    the fix is obvious: omit it and let the verb stamp it (mirrors
    :class:`ModelCopyError`'s own framework-owned-field rejection tone)."""


@dataclass(frozen=True, slots=True)
class WireNames:
    """Per-class canonical <-> python-field-name maps the snapshot node wrapper,
    the write-row document builders, and the ``model_copy`` assignability guard
    all need — built once at class-compile time from the SAME declarations the
    metamodel record itself derives from, so the two can never drift.

    ``column_to_py`` (scalar attribute / value-object PHYSICAL column -> python
    field name) is what a materialized snapshot node decodes with;
    ``name_to_py`` / ``py_to_name`` (CANONICAL business name <-> python field
    name, over the same member set) is what a write-row document is built
    with; ``relationship_py`` (canonical relationship name -> python field
    name) is what the frozen-node wrapper attaches relationship values under;
    ``assignable_py`` is the ``model_copy(update=...)`` allow-list (every
    scalar/value-object python field name except ``pk_py`` and
    ``framework_owned_py``). ``axis_governed_py`` (D-31, COR-3 Phase 8
    increment 7 completion round) is the python field name(s) of the
    entity's OWN declared axis-interval scalar attributes (``in_z``/``out_z``,
    and bitemporal ``from_z``/``thru_z``) -- populated only on the family ROOT
    that actually declares ``EntityConfig(as_of=...)`` (empty for a
    non-temporal class, or a family subclass, which never declares axes
    itself -- m-inheritance "Inherited members"); :func:`full_row`'s own
    construction-time rejection consults it, never ``assignable_py`` (which
    stays UNCHANGED -- an axis field remains a legal ``model_copy`` target,
    out of this decision's scope).
    """

    column_to_py: dict[str, str]
    name_to_py: dict[str, str]
    py_to_name: dict[str, str]
    relationship_py: dict[str, str]
    assignable_py: frozenset[str]
    pk_py: frozenset[str]
    framework_owned_py: frozenset[str]
    axis_governed_py: frozenset[str]
    vo_classes: dict[str, type]


_WIRE_NAMES: dict[type, WireNames] = {}


def wire_names_of(cls: type) -> WireNames:
    """The MRO-merged :class:`WireNames` map of a Parallax entity class: its
    own declared members PLUS every Parallax-entity ancestor's (a TPH/TPCS
    family member inherits its ancestors' declared columns/relationships —
    "note TPH members share the root's table" — merged base-first so a
    subclass's own declaration wins any name clash, none expected in a
    well-formed family). Non-family classes have no Parallax-entity ancestor
    beyond themselves, so this is simply their own map."""
    if cls not in _WIRE_NAMES:
        raise EntityDefinitionError(f"{cls!r} is not a compiled Parallax entity class")
    column_to_py: dict[str, str] = {}
    name_to_py: dict[str, str] = {}
    py_to_name: dict[str, str] = {}
    relationship_py: dict[str, str] = {}
    assignable_py: set[str] = set()
    pk_py: set[str] = set()
    framework_owned_py: set[str] = set()
    axis_governed_py: set[str] = set()
    vo_classes: dict[str, type] = {}
    for ancestor in reversed(cls.__mro__):
        names = _WIRE_NAMES.get(ancestor)
        if names is None:
            continue
        column_to_py.update(names.column_to_py)
        name_to_py.update(names.name_to_py)
        py_to_name.update(names.py_to_name)
        relationship_py.update(names.relationship_py)
        assignable_py.update(names.assignable_py)
        pk_py.update(names.pk_py)
        framework_owned_py.update(names.framework_owned_py)
        axis_governed_py.update(names.axis_governed_py)
        vo_classes.update(names.vo_classes)
    return WireNames(
        column_to_py=column_to_py,
        name_to_py=name_to_py,
        py_to_name=py_to_name,
        relationship_py=relationship_py,
        assignable_py=frozenset(assignable_py),
        pk_py=frozenset(pk_py),
        framework_owned_py=frozenset(framework_owned_py),
        axis_governed_py=frozenset(axis_governed_py),
        vo_classes=vo_classes,
    )


# A declared attribute captured during the annotation pass.
_AttrDecl = tuple[str, object, FieldSpec]
_RelDecl = tuple[str, object, RelationshipSpec]
_VoDecl = tuple[str, type, Literal["one", "many"], FieldSpec]


@dataclass(frozen=True, slots=True)
class FamilyRoot:
    """The inheritance-family ROOT's own vocabulary (ledger D-7's inheritance
    class spelling, DQ2): ``strategy`` names the mapping strategy exactly as the
    descriptor spells it; ``tag`` is the shared discriminator COLUMN name
    (table-per-hierarchy only — ``None`` for table-per-concrete-subtype). A root
    class's own ``EntityConfig.table`` (if any) is the TPH family's SHARED table
    default for a concrete-subtype descendant that declares no table of its
    own — the compiled root record itself always stays tableless (the
    tableless-and-rowless role rule)."""

    strategy: Literal["table-per-hierarchy", "table-per-concrete-subtype"]
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Concrete:
    """A concrete-subtype family member's own vocabulary: ``tag_value`` is the
    row's own discriminator value (table-per-hierarchy only — ``None`` under
    table-per-concrete-subtype, which carries no tag at all)."""

    tag_value: str | None = None


@dataclass(frozen=True, slots=True)
class EntityConfig:
    """Storage configuration declared in an entity class body via ``__parallax__``.

    ``as_of`` declares the entity's temporal dimensions in the descriptor's own
    vocabulary (:class:`~parallax.core.descriptor.AsOfAttribute` — ledger D-7's
    temporal class spelling): each axis names its interval columns, and the
    effective ``temporal`` classification is derived from the declared axes
    exactly as for an ingested descriptor. The interval-bound scalar attributes
    (e.g. ``processing_from`` on ``in_z``) are declared as ordinary ``Attr``
    fields beside it, so the class carries no information absent from the
    descriptor schema. Temporal axes are family-wide, not an ordinary
    per-entity member (m-inheritance "Inherited members"): on a family
    subclass (an abstract-subtype or concrete-subtype) ``as_of`` MUST be empty
    — only the family's own root may declare it — and `_derive_inheritance`
    rejects a subclass that does, at class-definition time
    (``inheritance-temporal-axes-not-root-owned``).

    ``inheritance`` declares the same family's own vocabulary (ledger D-7,
    DQ2): a :class:`FamilyRoot` on the family's abstract root, a
    :class:`Concrete` on a concrete-subtype leaf, or ``None`` on an
    abstract-subtype interior node (its role and parent derive from the Python
    class hierarchy alone — subclassing a Parallax entity makes the subclass a
    family member; the descriptor's own tableless-and-rowless role rule decides
    abstractness).
    """

    table: str | None = None
    namespace: str | None = None
    mutability: str = "read-only"
    as_of: tuple[AsOfAttribute, ...] = ()
    inheritance: FamilyRoot | Concrete | None = None


def camel_to_snake(name: str) -> str:
    """Convert a CamelCase entity name to its default snake_case table name."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def entity_registry() -> dict[str, type[BaseModel]]:
    """A copy of the process :func:`default_registry`'s own entity registry,
    keyed by canonical entity name (unaffected by a scoped ``registry=``
    declared elsewhere -- ledger D-20). Identical to every pre-D-20 caller's
    observed behavior for a single-registry app: every class this frontend
    ever compiled without an explicit ``registry=`` lands here, exactly as
    before."""
    return default_registry().own_names()


def entity_record_of(cls: type) -> EntityRecord | None:
    """The compiled metamodel record for an entity class, or ``None``."""
    return _ENTITY_BY_CLASS.get(cls)


def entity_records() -> dict[str, EntityRecord]:
    """Every compiled metamodel record visible from the process
    :func:`default_registry`, keyed by canonical entity name (ledger D-20)."""
    return default_registry().records()


def _registry_of_class(cls: type) -> EntityRegistry:
    """``cls``'s own D-20 registration scope (:func:`default_registry` for a
    class whose declaration omitted ``registry=``, defensively too for a class
    this bookkeeping somehow never tracked). PRIVATE (R3, COR-3 Phase 7
    increment 7 round-2 -- internal machinery, never public): class-authored
    metamodel assembly (:func:`metamodel`, THIS module) derives its own scope
    from THIS per-class lookup, never the process default, whenever the
    classes given are in hand."""
    return _REGISTRY_OF_CLASS.get(cls, default_registry())


def _conflicting_classes_error(name: str, first: type, second: type) -> ValueError:
    """The shared conflicting-same-name-classes ``ValueError`` (R1, COR-3
    Phase 7 increment 7 round-2): ``first``/``second`` are two DIFFERENT
    classes that both resolve to canonical entity name ``name`` -- naming
    both classes and their own D-20 registries, since assembling one
    Metamodel from both would let EITHER'S descriptor silently stand in for
    the other's (the reviewer's exact reproduction, ``animal_owner.Person`` +
    ``read_models.Person``)."""
    return ValueError(
        f"metamodel(classes): {first!r} (registry {_registry_of_class(first)!r}) and "
        f"{second!r} (registry {_registry_of_class(second)!r}) both resolve to canonical "
        f"entity name {name!r} -- conflicting same-name classes can never share one "
        "assembled Metamodel; supply only one of them, or assemble each through its own "
        "registry's EntityRegistry.metamodel() separately (ledger D-20)"
    )


def _registry_of_classes(classes: Sequence[type]) -> EntityRegistry | None:
    """The single :class:`EntityRegistry` that resolves EVERY one of
    ``classes`` back to THAT EXACT class (R1/R3, COR-3 Phase 7 increment 7
    round-2): the seam :func:`metamodel` uses to auto-scope its own result, so
    tagging is automatic wherever the classes are in hand, never a caller's
    own reminder to reach for a specific registry's
    :meth:`EntityRegistry.metamodel` instead.

    - ``classes`` empty: ``None`` -- no class/registry context to derive a
      scope from at all (:func:`metamodel`'s own documented UNSCOPED case).
    - Otherwise: the single member of ``classes``' own DISTINCT
      :func:`_registry_of_class` set that resolves EVERY supplied class's own
      canonical name back to THAT EXACT class object (:meth:`EntityRegistry.
      resolve`) -- never merely whether it "reaches" every other registry in
      the abstract (S2's original check confirmed reachability but never that
      the reaching registry's OWN resolution agreed with what was actually
      supplied, letting a same-name shadow between the classes' own
      registries silently swap in a DIFFERENT class than the one given, R1):
      this is never a guess, only the unique registry PROVABLY resolving
      every given class correctly (e.g. ``animal_owner.Person``'s own scope
      alongside its related ``read_models`` siblings' default registry
      resolves through the NARROWER, ``Person``-owning scope -- the identical
      tag a caller assembling the SAME class set through THAT registry's own
      :meth:`EntityRegistry.metamodel` would get).

    Raises :class:`ValueError`, naming every given class, when NO single
    member's own scope resolves every supplied class back to itself --
    whether the classes' own registries are genuinely incomparable (no chain
    relation at all) or share a name via shadowing (a chain relation exists,
    but the reaching registry's own resolution disagrees with the shadowed
    supplied class) -- picking ANY one of them could silently mis-resolve
    one of the others, so this refuses to guess instead.
    """
    classes = tuple(classes)
    distinct: dict[EntityRegistry, None] = {}
    for cls in classes:
        distinct.setdefault(_registry_of_class(cls), None)
    if not distinct:
        return None
    for candidate in distinct:
        if all(candidate.resolve(cls.__name__) is cls for cls in classes):
            return candidate
    names = ", ".join(cls.__name__ for cls in classes)
    raise ValueError(
        f"metamodel(classes): {names} span {len(distinct)} incompatible EntityRegistry "
        "scopes -- no single one resolves every supplied class back to itself, so tagging "
        "the assembled Metamodel with any one of them could silently mis-resolve another "
        "(genuinely unrelated registries, or a same-name shadow between them); assemble a "
        "metamodel scoped to one explicit registry instead (EntityRegistry.metamodel()), or "
        "pass a class set whose own registries form a single, non-shadowing parent chain "
        "(ledger D-20)"
    )


def _entity_record_for(cls: type) -> EntityRecord:
    """``cls``'s compiled metamodel record, or a loud ``TypeError`` naming
    ``cls`` -- the class-branch validation :func:`~parallax.core.entity.meta.
    meta`'s ``_entity_of`` also applies to a class argument, both calling the
    shared, package-internal :func:`~parallax.core.entity._validation.
    require_entity_record` seam (never one importing the check from the
    other, which would cycle: ``meta.py`` already imports from THIS module at
    module level) since :func:`metamodel` needs it and lives here (R1/R3,
    COR-3 Phase 7 increment 7 round-2; P3, round-3)."""
    return require_entity_record(cls, entity_record_of(cls))


def metamodel(classes: Sequence[type]) -> MetamodelRecord:
    """Assemble one :class:`~parallax.core.descriptor.Metamodel` from a set of
    related entity classes.

    Automatically SCOPED (S2, COR-3 Phase 7 increment 7 round-2): tagged as a
    :class:`ScopedMetamodel` resolving through the given classes' own registry
    (:func:`_registry_of_classes`) -- tagging is automatic wherever the
    classes are in hand, so `wrap`/`resolve_entity_class` resolve a decoded
    row's class through THIS scope, never the process default, once a
    connected ``Database`` carries the result. Without this, an owner class
    declared in its own registry (e.g. ``animal_owner.Person``) would resolve
    through the process default instead, landing on that DEFAULT registry's
    own, unrelated same-named entity (``read_models.Person``) the moment it
    also happened to be imported. ``classes`` empty -- no class/registry
    context at all -- stays UNSCOPED: a bare, untagged ``Metamodel``, for
    which :func:`registry_of`'s own documented fallback resolves through the
    process default registry instead (the same untagged shape a bare
    descriptor-ingested metamodel already carries).

    Rejects loudly (R1, COR-3 Phase 7 increment 7 round-2, BLOCKING) rather
    than silently emitting two records for one canonical name: a conflicting
    same-name pair in ``classes`` -- two DIFFERENT classes that both resolve
    to the same canonical entity name -- is structurally conflicting
    regardless of which registries are involved (checked here, independently
    of :func:`_registry_of_classes`'s own registry-selection hardening, which
    additionally catches a same-name conflict shadowed between the classes'
    own registries even when the two conflicting classes are not BOTH in
    ``classes`` directly). The IDENTICAL class object repeated in ``classes``
    is never such a conflict -- merely harmless repetition -- and is
    DEDUPLICATED (P1, COR-3 Phase 7 increment 7 round-3): the assembled
    ``entities`` carries exactly ONE record per distinct class, in FIRST-
    occurrence order, never a second copy for a repeated supplied class (a
    caller composing its own class list from several sources, some of which
    may legitimately overlap, never has to de-duplicate it by hand first).

    Physically relocated here from ``parallax.core.entity.meta`` (R3, COR-3
    Phase 7 increment 7 round-2): its own auto-scoping needs
    :func:`_registry_of_classes`, now module-private -- a cross-module
    consumer touching it would need a public re-export of purely internal
    registry machinery, exactly what R3 removes. ``meta.py`` re-exports this
    SAME function unchanged (``from parallax.core.entity.base import
    metamodel``); the public import path (``parallax.core.entity.metamodel``)
    and signature are unaffected.
    """
    classes = tuple(classes)
    seen: dict[str, type] = {}
    deduped: list[type] = []
    for cls in classes:
        name = cls.__name__
        conflicting = seen.get(name)
        if conflicting is not None:
            if conflicting is not cls:
                raise _conflicting_classes_error(name, conflicting, cls)
            continue  # the identical class object repeated -- harmless, dedupe (P1)
        seen[name] = cls
        deduped.append(cls)
    entities = tuple(_entity_record_for(cls) for cls in deduped)
    scope = _registry_of_classes(deduped)
    if scope is None:
        return MetamodelRecord(entities=entities)
    return ScopedMetamodel(entities=entities, registry=scope)


def _temporal_as_of_attributes(record: EntityRecord, cls: type) -> tuple[AsOfAttribute, ...]:
    """``record``'s EFFECTIVE as-of axes for the statement frontend's
    ``.as_of()`` / ``.as_of_range()`` / ``.history()`` axis resolution: the
    family root's declared axes for an inheritance participant (temporality is
    a family-wide property, declared only on the root — m-inheritance), else
    ``record``'s own. A concrete-subtype class's own compiled record carries no
    ``as_of_attributes`` of its own when its family's axes live on the root, so
    reading it directly here would wrongly refuse ``ConcreteType.where().as_of(...)``
    as "declares no temporal dimension" for an inherited axis. Resolved within
    ``cls``'s own D-20 registry scope (never every class ever compiled).
    """
    if record.inheritance is None:
        return record.as_of_attributes
    meta = _registry_of_class(cls).metamodel()
    return _inheritance.declaring_entity(meta, record).as_of_attributes


def _serialize_member(value: object) -> object:
    """A scalar/value-object member's write-row value: a ``ValueObject``
    instance serializes to its canonical document, a tuple of them to a list
    of documents (``cardinality: many``), everything else passes through."""
    if isinstance(value, ValueObject):
        return to_document(value)
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return [to_document(item) if isinstance(item, ValueObject) else item for item in items]
    return value


def _reject_axis_governed_fields(cls_name: str, names: WireNames, fields_set: set[str]) -> None:
    """Loud construction-time rejection (D-31, COR-3 Phase 8 increment 7
    completion round): a fresh instance handed to ``tx.insert``/
    ``tx.insert_until`` may not itself SET an axis-governed attribute
    (``in_z``/``out_z``, bitemporal ``from_z``/``thru_z``) — the temporal
    write path stamps every milestone bound itself (the Clock Strategy plus,
    for the bounded ``*Until`` forms, the verb's own window arguments), so a
    caller-supplied value is never a legitimate alternative. This REPLACES the
    pre-D-31 behavior of silently discarding it at the write path (the fresh
    row's caller-authored axis value was always overwritten unconditionally
    by the milestone open/insert step, never surfaced as an error)."""
    supplied = sorted(names.axis_governed_py & fields_set)
    if supplied:
        py_name = supplied[0]
        canonical = names.py_to_name[py_name]
        raise FrameworkOwnedAxisError(
            f"{cls_name}.{py_name} ({canonical!r}): axis-governed attributes are "
            "framework-stamped at write time (the temporal write path derives every "
            "milestone bound itself) — omit it at construction and let "
            "tx.insert/tx.insert_until stamp it (D-31)"
        )


def full_row(instance: Entity) -> dict[str, object]:
    """Every member of ``instance`` the caller actually SET, keyed by CANONICAL
    name — the ``insert``/``insert_until`` Create Payload row (spec §5).
    Filtered by Pydantic's own ``model_fields_set`` (not every declared member
    unconditionally): a nullable member the caller never populated (relying
    on its declared default) is OMITTED, producing the narrower ``INSERT``
    the corpus goldens pin (never an explicit bound ``NULL``) — the same
    distinction the ingested write-instruction row already expresses
    structurally. Raises :class:`FrameworkOwnedAxisError` (D-31) when the
    caller SET an axis-governed attribute (:func:`_reject_axis_governed_fields`) —
    checked before the row is built, so a rejected instance emits no DML at all.
    """
    names = wire_names_of(type(instance))
    fields_set = instance.model_fields_set
    _reject_axis_governed_fields(type(instance).__name__, names, fields_set)
    return {
        canonical: _serialize_member(getattr(instance, py_name))
        for canonical, py_name in names.name_to_py.items()
        if py_name in fields_set
    }


def primary_key_row(instance: object) -> dict[str, object]:
    """``instance``'s primary-key members, keyed by CANONICAL name — what
    ``tx.delete`` and a sparse ``tx.update`` row key off (spec §5)."""
    names = wire_names_of(type(instance))
    return {names.py_to_name[py_name]: getattr(instance, py_name) for py_name in names.pk_py}


def canonical_row(instance: object, py_row: dict[str, object]) -> dict[str, object]:
    """Translate a python-name-keyed row to its CANONICAL-name-keyed,
    write-serialized form (value objects rendered to documents)."""
    names = wire_names_of(type(instance))
    return {
        names.py_to_name[py_name]: _serialize_member(value) for py_name, value in py_row.items()
    }


def changed_fields(instance: object) -> dict[str, object] | None:
    """``instance``'s Change Record (python field name -> EARLIEST recorded
    original across its copy chain), or ``None`` when it carries none — a
    "provenance-less" instance, never produced via ``model_copy`` (spec §5)."""
    changes = (
        instance.__dict__.get("__parallax_changes__") if hasattr(instance, "__dict__") else None
    )
    if isinstance(changes, dict):
        return cast("dict[str, object]", changes)
    return None


def effective_change_set(copy: object) -> dict[str, object]:
    """The touched-AND-different fields of an edited copy (python field name ->
    CURRENT value) — a touched field whose current value equals its recorded
    original drops out (the net-zero-chain no-op rule, spec §3/§5). Raises
    :class:`ProvenanceError` for a provenance-less instance."""
    changes = changed_fields(copy)
    if changes is None:
        raise ProvenanceError(
            f"{type(copy).__name__} carries no Change Record; derive an edited copy via "
            "`instance.model_copy(update={...})` before passing it to `tx.update`"
        )
    return {
        py_name: getattr(copy, py_name)
        for py_name, original in changes.items()
        if getattr(copy, py_name) != original
    }


def _module_globalns(namespace: dict[str, Any]) -> dict[str, Any]:
    """The declaring module's global namespace, for resolving stringized types."""
    module_name = namespace.get("__module__")
    module = sys.modules.get(module_name) if isinstance(module_name, str) else None
    return dict(getattr(module, "__dict__", {}))


def _resolve_annotation_type(inner: object, globalns: dict[str, Any]) -> object:
    """Resolve a stringized inner **attribute** type to a real object.

    Under ``from __future__ import annotations`` (or any explicit stringized
    annotation) an ``Attr[T]`` inner type arrives as a string; evaluate it against
    the declaring module's namespace so neutral-type inference sees the concrete
    ``T``. Relationship inner types are never passed here, so a forward
    relationship reference such as ``Rel["Other"]`` is left unresolved until it is
    actually needed. A name that cannot be resolved is returned unchanged, so a
    genuinely un-inferable annotation still raises the ordinary "cannot infer"
    error when no explicit ``type=`` is supplied.
    """
    if not isinstance(inner, str):
        return inner
    try:
        # Trusted input: the developer's own annotation source, already executed
        # as a class body. Mirrors typing.get_type_hints' resolution step.
        return eval(inner, globalns)
    except (NameError, AttributeError, SyntaxError, TypeError):
        return inner


def _unwrap(annotation: object, globalns: dict[str, Any]) -> tuple[str | None, object]:
    """Classify an annotation as ``attr`` / ``rel`` / plain and return its inner type."""
    if isinstance(annotation, str):
        text = annotation.strip()
        if (match := _ATTR_STR.match(text)) is not None:
            return "attr", _resolve_annotation_type(match.group("inner"), globalns)
        if (match := _REL_STR.match(text)) is not None:
            return "rel", match.group("inner")
        return None, annotation
    origin = get_origin(annotation)
    if origin is Attr:
        return "attr", _resolve_annotation_type(get_args(annotation)[0], globalns)
    if origin is Rel:
        return "rel", get_args(annotation)[0]
    return None, annotation


def _infer_neutral_type(inner: object, py_name: str) -> str:
    # `parallax.core.descriptor.infer_neutral_type` is error-neutral (shared
    # with the ValueObject frontend, which cannot import this module without
    # cycling); this classifies its own unresolved-type / needs-precision
    # cases into the Entity frontend's own message text.
    neutral = _infer_neutral_type_lookup(inner)
    if neutral is None:
        raise EntityDefinitionError(
            f"attribute {py_name!r}: cannot infer a neutral type from {inner!r}; "
            "pass Field(type=...)"
        )
    if neutral == "decimal":
        raise EntityDefinitionError(
            f"attribute {py_name!r}: a decimal needs an explicit precision — "
            "pass Field(type='decimal(p,s)')"
        )
    return neutral


def _family_parent(bases: tuple[type, ...]) -> type | None:
    """The nearest base that is ITSELF a compiled Parallax entity class, or
    ``None`` — the Python-hierarchy-derived family-membership test (ledger D-7,
    DQ2): subclassing an entity always joins its family; ``Entity`` itself is
    never registered, so no false positive arises for an ordinary declaration."""
    for base in bases:
        if base in _ENTITY_BY_CLASS:
            return base
    return None


def _resolve_registry(
    cls_name: str, registry: EntityRegistry | None, family_parent: type | None
) -> EntityRegistry:
    """This class's own D-20 registration scope: an inheritance-family member
    always shares its family root's registry (a family is one coherent
    registration scope, the SAME root-ownership discipline
    ``EntityConfig(as_of=...)`` / ``table`` already follow) — an explicit
    ``registry=`` that names a DIFFERENT one is a loud class-definition-time
    error, never a silent split-family bug. A non-family declaration uses its
    own explicit ``registry=``, or :func:`default_registry` when omitted
    (zero-ceremony)."""
    if family_parent is not None:
        parent_registry = _REGISTRY_OF_CLASS[family_parent]
        if registry is not None and registry is not parent_registry:
            raise EntityDefinitionError(
                f"{cls_name}: a family SUBCLASS cannot declare a `registry=` different from "
                "its family root's own — an inheritance family shares one registration scope "
                "(ledger D-20)"
            )
        return parent_registry
    return registry if registry is not None else default_registry()


# The TPH family's shared table default, keyed by the ROOT entity's own CLASS
# OBJECT (S1, COR-3 Phase 7 increment 7 round-2 — never the bare canonical
# NAME: two DIFFERENT registries' same-named TPH roots would otherwise
# overwrite each other's entry here, letting registry A's concrete-subtype
# descendant silently inherit registry B's table, the collision `_ENTITY_BY_
# CLASS` / `_REGISTRY_OF_CLASS` already avoid by keying on the class object —
# this map now follows the same collision-proof shape). Populated when the
# root compiles (its EntityConfig.table, possibly ``None``, written AFTER
# `cls` exists — the root's OWN `EntityMeta.__new__` call, never
# `_derive_inheritance`, which runs before `cls` is built), consumed by a
# concrete-subtype descendant that declares no table of its own (resolved to
# the root's CLASS via THIS family's own D-20 registry — never a foreign
# one, `EntityRegistry.resolve`'s own scoping guarantee).
_FAMILY_SHARED_TABLE: dict[type, str | None] = {}


def _derive_inheritance(
    cls_name: str, config: EntityConfig, family_parent: type | None, registry: EntityRegistry
) -> tuple[InheritanceRecord | None, str | None]:
    """Derive the compiled ``Inheritance`` record and this entity's own resolved
    ``table`` from the Python class hierarchy + ``EntityConfig.inheritance``
    (ledger D-7, DQ2). Returns ``(None, <default table>)`` — unchanged existing
    behavior — for a plain, non-family entity.
    """
    if family_parent is None:
        if isinstance(config.inheritance, FamilyRoot):
            # `_FAMILY_SHARED_TABLE` is populated by the CALLER (`EntityMeta.
            # __new__`, once the root's own `cls` exists to key it by) — never
            # here, which runs before `cls` is built.
            record = InheritanceRecord(
                role="root",
                strategy=config.inheritance.strategy,
                parent=None,
                tag_column=config.inheritance.tag,
                tag_value=None,
            )
            return record, None  # the root is always tableless (rowless too)
        if isinstance(config.inheritance, Concrete):
            raise EntityDefinitionError(
                f"{cls_name}: EntityConfig(inheritance=Concrete(...)) requires subclassing "
                "another Parallax entity (its family parent) — a family root declares "
                "EntityConfig(inheritance=FamilyRoot(...)) instead"
            )
        table = config.table if config.table is not None else camel_to_snake(cls_name)
        return None, table

    parent_record = _ENTITY_BY_CLASS[family_parent]
    if parent_record.inheritance is None:
        raise EntityDefinitionError(
            f"{cls_name}: subclassing {family_parent.__name__!r} makes it an inheritance-family "
            f"member, but {family_parent.__name__!r} declares no inheritance family "
            "(EntityConfig(inheritance=FamilyRoot(...)) on the family's own root) — subclassing "
            "a Parallax entity always joins its family (ledger D-7)"
        )
    try:
        temp_meta = registry.metamodel()
        root_record = _inheritance.family_root(temp_meta, parent_record)
    except ValueError as exc:  # pragma: no cover - guards a malformed family
        raise EntityDefinitionError(f"{cls_name}: {exc}") from exc
    assert root_record.inheritance is not None  # a resolved root always carries one

    if isinstance(config.inheritance, FamilyRoot):
        raise EntityDefinitionError(
            f"{cls_name}: a family SUBCLASS cannot itself declare "
            "EntityConfig(inheritance=FamilyRoot(...)) — only the family's own root does"
        )
    if config.as_of:
        # Temporal axes are family-wide metadata (the binding root-ownership
        # decision, `inheritance-temporal-axes-not-root-owned`): only the
        # family root may declare `EntityConfig(as_of=...)`; an abstract- or
        # concrete-subtype family member declaring its own — even one
        # verbatim-repeating the root's — is rejected here, at class-definition
        # time, the same way a subclass-declared `table` or `FamilyRoot` is
        # rejected above (m-inheritance "Inherited members").
        raise EntityDefinitionError(
            f"{cls_name}: a family SUBCLASS cannot declare EntityConfig(as_of=...) — "
            "temporal axes are family-wide and only the family's own root may declare "
            "them (inheritance-temporal-axes-not-root-owned)"
        )
    if isinstance(config.inheritance, Concrete):
        if config.table is not None:
            table = config.table
        elif root_record.inheritance.strategy == "table-per-hierarchy":
            # Resolved through THIS family's own D-20 registry scope (never
            # `_ENTITY_BY_CLASS`/a bare name lookup directly): the root is
            # ALWAYS already registered here by the time any of its
            # descendants compile (a Python subclass statement cannot name a
            # base class that has not finished executing), so this can never
            # cross into a foreign registry's same-named root (S1).
            root_cls = registry.resolve(root_record.name)
            assert root_cls is not None  # the root always registers into this scope
            shared = _FAMILY_SHARED_TABLE.get(root_cls)
            table = shared if shared is not None else camel_to_snake(root_record.name)
        else:  # table-per-concrete-subtype: every concrete owns its own table
            table = camel_to_snake(cls_name)
        record = InheritanceRecord(
            role="concrete-subtype",
            strategy=None,
            parent=parent_record.name,
            tag_column=None,
            tag_value=config.inheritance.tag_value,
        )
        return record, table

    # No `EntityConfig.inheritance` on a family subclass: an interior
    # abstract-subtype node — tableless and rowless (m-inheritance).
    if config.table is not None:
        raise EntityDefinitionError(
            f"{cls_name}: an abstract-subtype family member is tableless and rowless "
            "(m-inheritance); declare EntityConfig(inheritance=Concrete(...)) for a "
            "concrete (row-owning) leaf instead"
        )
    record = InheritanceRecord(
        role="abstract-subtype", strategy=None, parent=parent_record.name, tag_column=None
    )
    return record, None


def _value_object_of(decl: _VoDecl) -> ValueObjectRecord:
    py_name, vo_class, cardinality, spec = decl
    canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
    sub = structure_of(vo_class)
    return ValueObjectRecord(
        name=canonical,
        column=spec.column if spec.column is not None else py_name,
        nullable=spec.nullable,
        cardinality=cardinality,
        attributes=sub.attributes,
        value_objects=sub.value_objects,
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
    attributes: tuple[AttributeRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    value_objects: tuple[ValueObjectRecord, ...] = (),
) -> None:
    seen: set[str] = set()
    for name in (
        *(a.name for a in attributes),
        *(r.name for r in relationships),
        *(v.name for v in value_objects),
    ):
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
        *,
        registry: EntityRegistry | None = None,
        **kwargs: Any,
    ) -> type:
        if not any(isinstance(base, EntityMeta) for base in bases):
            return super().__new__(mcs, cls_name, bases, namespace, **kwargs)

        config = namespace.get("__parallax__")
        if config is not None and not isinstance(config, EntityConfig):
            raise EntityDefinitionError("`__parallax__` must be an EntityConfig")
        config = config if isinstance(config, EntityConfig) else EntityConfig()

        # D-31 (COR-3 Phase 8 increment 7 completion round): the columns this
        # class's OWN declared `as_of` axes govern (empty for a non-temporal
        # class or a family subclass, which never declares `as_of` itself —
        # m-inheritance "Inherited members") — every axis-interval scalar
        # attribute below (`in_z`/`out_z`, bitemporal `from_z`/`thru_z`)
        # becomes optional at construction, never caller-required.
        axis_columns: frozenset[str] = frozenset(
            column for aoa in config.as_of for column in (aoa.from_column, aoa.to_column)
        )

        annotations: dict[str, Any] = dict(namespace.get("__annotations__", {}))
        globalns = _module_globalns(namespace)
        attr_decls: list[_AttrDecl] = []
        rel_decls: list[_RelDecl] = []
        vo_decls: list[_VoDecl] = []

        for py_name, annotation in list(annotations.items()):
            if get_origin(annotation) is ClassVar:
                continue
            kind, inner = _unwrap(annotation, globalns)
            _reject_reserved(py_name)
            value = namespace.get(py_name)
            if kind == "attr":
                spec = value if isinstance(value, FieldSpec) else FieldSpec()
                annotations[py_name] = inner  # Attr[T] -> T for Pydantic
                column = spec.column if spec.column is not None else py_name
                if spec.default is not UNSET:
                    namespace[py_name] = spec.default
                elif column in axis_columns:
                    # D-31: axis-governed attributes are optional at
                    # construction — a Pydantic default of `None`, never
                    # validated (`model_config` sets no `validate_default`),
                    # so the DECLARED attribute type is unaffected; only an
                    # unpopulated instance's runtime value is `None` until a
                    # read materializes a real one (mirrors the established
                    # PYTHON-optional/DESCRIPTOR-required split, e.g.
                    # `ContactPoint`'s own docstring). The exported descriptor
                    # itself carries NO `default` for this attribute (`spec.default`
                    # stays `UNSET`, read by `_attribute_of` below, untouched
                    # here) — a frontend affordance only, byte-identical export.
                    namespace[py_name] = None
                else:
                    namespace.pop(py_name, None)
                vo_info = vo_field_info(inner)
                if vo_info is not None:
                    vo_class, cardinality = vo_info
                    vo_decls.append((py_name, vo_class, cardinality, spec))
                else:
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
        for vo_py_name, vo_cls, vo_cardinality, _vo_spec in vo_decls:
            namespace[f"_validate_vo_{vo_py_name}"] = vo_instance_validator(
                vo_py_name, vo_cls, vo_cardinality
            )

        # Compile the metamodel record BEFORE Pydantic builds the model, so a
        # neutral-type / relationship rejection is a Parallax error rather than a
        # downstream Pydantic schema-generation failure.
        attributes = tuple(_attribute_of(decl) for decl in attr_decls)
        relationships = tuple(_relationship_of(decl) for decl in rel_decls)
        value_objects = tuple(_value_object_of(decl) for decl in vo_decls)
        _reject_collisions(attributes, relationships, value_objects)
        family_parent = _family_parent(bases)
        resolved_registry = _resolve_registry(cls_name, registry, family_parent)
        inheritance_record, resolved_table = _derive_inheritance(
            cls_name, config, family_parent, resolved_registry
        )
        entity = EntityRecord(
            name=cls_name,
            namespace=config.namespace,
            table=resolved_table,
            mutability=cast("Any", _check_mutability(config.mutability)),
            attributes=attributes,
            as_of_attributes=config.as_of,
            relationships=relationships,
            value_objects=value_objects,
            inheritance=inheritance_record,
        )
        # Reject an invalid compiled record (bad neutral type, out-of-range
        # maxLength, optimistic-lock composition, PK-generator bounds, no
        # attributes at all outside an inheritance family, …) at definition
        # time, before the class is registered or ever exported.
        try:
            validate_entity(entity)
            if entity.inheritance is not None:
                # A family subclass declaring its OWN `optimisticLocking`
                # attribute is rejected regardless of what the root declares
                # (D-25, ADR 0027) — the same gap `_derive_inheritance` already
                # closes for `EntityConfig(as_of=...)` above, closed here for
                # the version column too. `validate_optimistic_locking_root_owned`
                # is a pure per-entity structural check — a non-root's own
                # `attributes` fully determine the verdict, so no sibling
                # records (and no temporary metamodel) are needed here.
                validate_optimistic_locking_root_owned(entity)
        except DescriptorError as exc:
            raise EntityDefinitionError(str(exc)) from exc

        cls = super().__new__(mcs, cls_name, bases, namespace, **kwargs)
        if entity.inheritance is not None and entity.inheritance.role == "root":
            # S1: keyed by `cls` itself (never the bare `cls_name`) — only
            # possible here, once `cls` exists; `_derive_inheritance` runs
            # before it does.
            _FAMILY_SHARED_TABLE[cls] = config.table
        column_to_py: dict[str, str] = {}
        name_to_py: dict[str, str] = {}
        py_to_name: dict[str, str] = {}
        pk_py: set[str] = set()
        framework_owned_py: set[str] = set()
        axis_governed_py: set[str] = set()
        for py_name, _inner, spec in attr_decls:
            canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
            column = spec.column if spec.column is not None else py_name
            setattr(
                cls, py_name, Attr(AttributeRef(cls_name, canonical), py_name, resolved_registry)
            )
            column_to_py[column] = py_name
            name_to_py[canonical] = py_name
            py_to_name[py_name] = canonical
            if spec.primary_key:
                pk_py.add(py_name)
            if spec.optimistic_locking:
                framework_owned_py.add(py_name)
            if column in axis_columns:
                axis_governed_py.add(py_name)
        vo_classes: dict[str, type] = {}
        for py_name, vo_class, _card, spec in vo_decls:
            canonical = spec.name if spec.name is not None else snake_to_camel(py_name)
            column = spec.column if spec.column is not None else py_name
            setattr(
                cls, py_name, Attr(AttributeRef(cls_name, canonical), py_name, resolved_registry)
            )
            column_to_py[column] = py_name
            name_to_py[canonical] = py_name
            py_to_name[py_name] = canonical
            vo_classes[py_name] = vo_class
        relationship_py: dict[str, str] = {}
        for py_name, _inner, rel_spec in rel_decls:
            canonical = rel_spec.name if rel_spec.name is not None else snake_to_camel(py_name)
            rel_descriptor: Rel[Any] = Rel(
                RelationshipRef(cls_name, canonical),
                py_name,
                rel_spec.related_entity,
                resolved_registry,
            )
            setattr(cls, py_name, rel_descriptor)
            relationship_py[canonical] = py_name
        resolved_registry._register(  # pyright: ignore[reportPrivateUsage]
            cls_name, cast("type[BaseModel]", cls)
        )
        _REGISTRY_OF_CLASS[cls] = resolved_registry
        _ENTITY_BY_CLASS[cls] = entity
        _WIRE_NAMES[cls] = WireNames(
            column_to_py=column_to_py,
            name_to_py=name_to_py,
            py_to_name=py_to_name,
            relationship_py=relationship_py,
            assignable_py=frozenset(py_to_name) - pk_py - framework_owned_py,
            pk_py=frozenset(pk_py),
            framework_owned_py=frozenset(framework_owned_py),
            axis_governed_py=frozenset(axis_governed_py),
            vo_classes=vo_classes,
        )
        return cls


def _entity_name_of(cls: type) -> str:
    record = entity_record_of(cls)
    return record.name if record is not None else cls.__name__


def _validate_copy_keys(cls_name: str, names: WireNames, update: Mapping[str, Any]) -> None:
    """Reject an unassignable ``model_copy(update=...)`` key (spec §3): unknown,
    primary-key, framework-owned, or relationship."""
    for py_name in update:
        if py_name in names.assignable_py:
            continue
        if py_name in names.relationship_py.values():
            raise ModelCopyError(
                f"{cls_name}.{py_name}: relationship fields are not assignable via model_copy "
                "(no cascade or association-mutation semantics to lower it to)"
            )
        if py_name in names.pk_py:
            raise ModelCopyError(f"{cls_name}.{py_name}: primary-key fields may not be assigned")
        if py_name in names.framework_owned_py:
            raise ModelCopyError(
                f"{cls_name}.{py_name}: framework-owned fields (the version column) may not "
                "be assigned"
            )
        raise ModelCopyError(f"{cls_name}.{py_name}: unknown field name")


class Entity(BaseModel, metaclass=EntityMeta):
    """The frozen base every Parallax entity extends."""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def where(cls, *predicates: Predicate) -> Statement:
        """Build a side-effect-free statement conjoining ``predicates`` (empty is find-all).

        Validates immediately via ``validate_operation`` (python.md §2): a
        subtype-declared attribute referenced outside a compatible ``narrow``
        scope raises the moment this statement is built, never later — the
        statement-level ``.narrow(...)`` clause grants no retroactive scope to
        an already-built ``where`` argument. An inheritance participant's
        temporal axes resolve through the family root
        (`_temporal_as_of_attributes`), so a concrete-subtype class's
        ``.as_of()`` / ``.as_of_range()`` / ``.history()`` accepts its
        inherited ``ConcreteType.axis`` spelling even though the class's own
        record declares no axis locally.
        """
        record = entity_record_of(cls)
        registry = _registry_of_class(cls)
        as_of = _temporal_as_of_attributes(record, cls) if record is not None else ()
        statement = build_statement(
            cls.__name__, predicates, as_of_attributes=as_of, registry=registry
        )
        validate_operation(cls.__name__, statement.predicate, registry.metamodel())
        return statement

    @classmethod
    def narrow(cls, *subtypes: type, where: Predicate | None = None) -> Predicate:
        """The scoped subtype-narrowing constructor (python.md §2):
        ``Animal.narrow(Dog, where=Dog.bark_volume > 3)``. ``entity`` is this
        class's own canonical position; ``to`` preserves the authored subtype
        list verbatim (each entry a concrete or abstract subtype class);
        ``where=`` grants attribute scope to ``to``'s declared members ONLY
        inside its own operand (omitted ⇒ ``all``). An ordinary predicate: it
        composes with ``&`` / ``|`` / ``~`` like any other, and inside a
        relationship quantifier the constructor must be called on exactly the
        relationship target — ``m-navigate``'s exact-naming rule.

        Deliberately UNVALIDATED here: this constructor's own position
        (top-level clamp vs. a relationship hop's exact-naming rule) depends on
        WHERE the caller composes it, which this call site cannot know —
        ``Entity.where(...)`` / ``.include(...)`` / a relationship
        ``.any()``/``.none()`` scope validate the FULLY assembled tree with the
        correct threaded scope once it is built, never twice with the wrong one.
        """
        to = tuple(_entity_name_of(subtype) for subtype in subtypes)
        operand: Operation = where.op if where is not None else All()
        return Predicate(Narrow(entity=cls.__name__, to=to, operand=operand))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """The validating D-16 override (python.md §3): a copy carries a Change
        Record mapping each touched field to its EARLIEST original across copy
        chains (copies of copies merge records). Also VALIDATES — Pydantic's
        own ``model_copy`` never validates ``update=`` data — applying the same
        build-time rules as construction: unknown field names, primary-key
        fields, framework-owned fields (the version column), and relationship
        fields all raise; every value passes the §2 scalar input policies (the
        merged instance is fully re-validated through the ordinary
        constructor), so an invalid edit raises at copy time, never at the
        database.
        """
        if not update:
            copied = super().model_copy(update=None, deep=deep)
            carried = dict(changed_fields(self) or {})
            object.__setattr__(copied, "__parallax_changes__", carried)
            return copied
        names = wire_names_of(type(self))
        _validate_copy_keys(type(self).__name__, names, update)
        declared = set(names.py_to_name)
        merged = {k: v for k, v in self.__dict__.items() if k in declared}
        merged.update(update)
        validated = type(self)(**merged)  # re-validates the WHOLE instance (§2 scalar policies)
        changes = dict(changed_fields(self) or {})
        for py_name in update:
            if py_name not in changes:
                changes[py_name] = getattr(self, py_name)
        object.__setattr__(validated, "__parallax_changes__", changes)
        return validated
