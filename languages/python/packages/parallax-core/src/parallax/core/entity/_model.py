"""The Domain Model: one explicit, sealed model over a fixed source.

``DomainModel(*classes)`` returns a fully sealed model or raises. There is no
``seal()`` operation and no unsealed, sealing, or rejected state, so every model
a caller can name is authoritative and no model-dependent operation performs a
lifecycle check.

Construction runs one fixed sequence: left-to-right argument validation, whole-
model formation, and — for a class-backed model — the Python realization phase,
which checks relationship annotation agreement. A Domain Model binds nothing and
owns no identity, so an Entity Class participates in as many models as compose
it and construction has no synchronization point. What a class-backed model
holds is an index of the classes it composed, which exists so a materializing
runtime can decide which class a returned row instantiates. The same class may
legitimately mean different things in two models: partial inheritance families
compose, so an Entity's effective concrete-subtype set is a per-model fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core._formation_profile import form_metamodel
from parallax.core.entity._declaration import declaration_of, is_entity_class, members_of
from parallax.core.entity._errors import (
    METAMODEL_DUPLICATE_ENTITY_CLASS,
    METAMODEL_EMPTY,
    METAMODEL_ENTITY_NOT_FOUND,
    METAMODEL_INVALID_ENTITY_CLASS,
    METAMODEL_INVALID_ENTITY_REFERENCE,
    EntityDefinitionError,
    MetamodelDefinitionError,
    MetamodelLookupError,
)
from parallax.core.inheritance import InheritanceFacet
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    RelationshipIdentity,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedMetamodel,
)
from parallax.core.relationship import view as relationship_view

__all__ = ["ClassIndex", "DomainModel", "class_index", "model_of"]


@dataclass(frozen=True, slots=True)
class _ClassSource:
    """The class-backed frontend's Unresolved Metamodel.

    Entity Classes *are* their own declarations, so the source is the validated
    argument tuple itself: nothing is adapted, mirrored, or copied.
    """

    entities: tuple[UnresolvedEntityDeclaration, ...]


@dataclass(frozen=True, slots=True)
class ClassIndex:
    """The immutable bidirectional Entity Identity to Entity Class index one
    class-backed Domain Model composed.

    It exists for materialization — deciding which class a returned row
    instantiates — and is never an authorization structure: a class appears here
    because this model composed it, never because it belongs to this model.
    """

    by_class: Mapping[type, EntityIdentity]
    by_identity: Mapping[EntityIdentity, type]

    def identity_of(self, cls: type) -> EntityIdentity | None:
        """The Entity Identity ``cls`` was composed under here, or ``None``."""
        return self.by_class.get(cls)

    def class_of(self, identity: EntityIdentity) -> type | None:
        """The Entity Class composed under ``identity`` here, or ``None``."""
        return self.by_identity.get(identity)


class DomainModel:
    """One sealed model, composed from a fixed source.

    A class-backed model additionally holds the index of the Entity Classes it
    composed; a descriptor-backed model composes none and holds none. Both expose
    the identical compiler-owned accepted metadata.
    """

    __slots__ = ("_classes", "_graph_construction", "_model", "_row_codec")

    _model: Metamodel
    _classes: ClassIndex | None
    _graph_construction: object | None
    """The Entity Graph Construction collaboration this model reached, created on
    first reach. It is typed as opaque here because the construction seam depends
    on this module and never the reverse; what fills the slot is
    ``parallax.core.entity._graph_construction.graph_construction_of``."""
    _row_codec: object | None
    """The Entity Row Codec this model reached, created on first reach and typed
    opaque for its sibling's reason; what fills the slot is
    ``parallax.core.entity._row_codec.row_codec_of``.

    One slot per capability rather than one composite or one keyed bag: read
    materialization crosses graph construction alone and write preparation
    crosses the codec alone, so nothing wants the pair as a value."""

    def __init__(self, *classes: UnresolvedEntityDeclaration) -> None:
        """Compose ``classes`` into one sealed model, or raise.

        Each argument is a domain Entity Class, which is its own
        ``UnresolvedEntityDeclaration``. Arguments are checked left to right:
        an empty call raises :class:`MetamodelDefinitionError` with
        ``metamodel-empty``, a non-Entity-Class argument with
        ``metamodel-invalid-entity-class``, and a repeated class object with
        ``metamodel-duplicate-entity-class`` — the latter two carrying the
        zero-based argument index. Two *distinct* classes declaring one Entity
        Identity are valid input and become a whole-model issue instead.

        Formation raises :class:`~parallax.core.model_formation.
        MetamodelValidationError` on model defects; realization raises
        :class:`EntityDefinitionError` with
        ``entity-relationship-annotation-mismatch`` on annotation disagreement.
        """
        entity_classes = _validated(classes)
        model = form_metamodel(_ClassSource(classes))
        _reject_annotation_mismatches(entity_classes, model)
        self._publish(model, _class_index(entity_classes))

    @classmethod
    def _from_unresolved(cls, source: UnresolvedMetamodel) -> DomainModel:
        """Seal ``source`` into a fixed-source model composing no Entity Class.

        The private, versioned first-party seam the Descriptor Frontend reaches
        model construction through. It is not a supported third-party extension
        point, and no registration, discovery, or lazy-import mechanism supplies
        it.
        """
        model = form_metamodel(source)
        domain = cls.__new__(cls)
        domain._publish(model, None)
        return domain

    def _publish(self, model: Metamodel, classes: ClassIndex | None) -> None:
        """Complete the model's own state in one step."""
        self._model = model
        self._classes = classes
        self._graph_construction = None
        self._row_codec = None

    @property
    def entities(self) -> Sequence[EntityMetadata]:
        """Every Entity's accepted local metadata, in canonical Entity order."""
        return self._model.entities

    def meta(self, key: type | str | EntityIdentity) -> EntityMetadata:
        """The accepted local metadata ``key`` names within this model.

        ``key`` is an Entity Class this model composed, a canonical spelling
        (``"sales.Order"``, or a bare ``"Order"`` for an unnamespaced Entity), or
        an :class:`EntityIdentity`. All three answer the same object.

        Raises :class:`MetamodelLookupError` with
        ``metamodel-invalid-entity-reference`` for a string that is not a
        canonical spelling, and ``metamodel-entity-not-found`` when the key is
        well-formed but names no Entity here — a class this model did not compose
        included, since a class names an Entity of the models that composed it
        and of no other.
        """
        identity = self._identity(key)
        metadata = self._model.entity(identity)
        if metadata is None:
            raise MetamodelLookupError(
                code=METAMODEL_ENTITY_NOT_FOUND,
                message=f"this model declares no Entity {identity.canonical!r}",
            )
        return metadata

    def _identity(self, key: type | str | EntityIdentity) -> EntityIdentity:
        if isinstance(key, EntityIdentity):
            return key
        if isinstance(key, str):
            return _parsed_identity(key)
        identity = None if self._classes is None else self._classes.identity_of(key)
        if identity is None:
            raise MetamodelLookupError(
                code=METAMODEL_ENTITY_NOT_FOUND,
                message=(
                    f"this model composed no Entity Class {key.__name__}; a class names an "
                    "Entity of the models that composed it and of no other"
                ),
            )
        return identity


def model_of(model: DomainModel) -> Metamodel:
    """The accepted Metamodel ``model`` sealed.

    A free function rather than a property: reading the accepted model out of a
    Domain Model is a first-party runtime seam, not part of the developer
    surface, which is ``meta(...)`` and ``entities`` alone.
    """
    return model._model  # pyright: ignore[reportPrivateUsage] - first-party seam reads the model's own sealed metamodel


def class_index(model: DomainModel) -> ClassIndex | None:
    """``model``'s Entity Class index, absent exactly for a descriptor-backed one.

    The companion of :func:`model_of` for the one capability that needs classes:
    a runtime that instantiates result rows. Reachable only through this private
    module — ``parallax.core.entity`` exports neither function — so the pair is
    first-party support rather than developer surface.
    """
    return model._classes  # pyright: ignore[reportPrivateUsage] - first-party seam reads the model's own class index


def _class_index(classes: Sequence[type]) -> ClassIndex:
    """The bidirectional index over ``classes`` and the identities they declare."""
    by_class = {cls: declaration_of(cls).identity for cls in classes}
    return ClassIndex(
        by_class=MappingProxyType(dict(by_class)),
        by_identity=MappingProxyType({identity: cls for cls, identity in by_class.items()}),
    )


def _validated(classes: tuple[UnresolvedEntityDeclaration, ...]) -> tuple[type, ...]:
    """The argument tuple as Entity Classes, checked left to right."""
    if not classes:
        raise MetamodelDefinitionError(
            code=METAMODEL_EMPTY,
            message="a domain model composes at least one Entity Class",
        )
    seen: set[UnresolvedEntityDeclaration] = set()
    checked: list[type] = []
    for index, candidate in enumerate(classes):
        if not isinstance(candidate, type) or not is_entity_class(candidate):
            raise MetamodelDefinitionError(
                code=METAMODEL_INVALID_ENTITY_CLASS,
                message=f"argument {index} is not a domain Entity Class: {candidate!r}",
                index=index,
            )
        if candidate in seen:
            raise MetamodelDefinitionError(
                code=METAMODEL_DUPLICATE_ENTITY_CLASS,
                message=f"argument {index} repeats {candidate.__name__}",
                index=index,
            )
        seen.add(candidate)
        checked.append(candidate)
    return tuple(checked)


def _parsed_identity(spelling: str) -> EntityIdentity:
    """The Entity Identity a canonical spelling denotes.

    Exactly the inverse of :attr:`EntityIdentity.canonical`: the last dot
    separates an optional namespace from the dot-free name, so a bare spelling
    can only name an unnamespaced Entity.
    """
    namespace, dot, name = spelling.rpartition(".")
    if not name or (dot and not namespace):
        raise MetamodelLookupError(
            code=METAMODEL_INVALID_ENTITY_REFERENCE,
            message=(
                f"{spelling!r} is not a canonical Entity spelling "
                "(`<namespace>.<name>`, or `<name>` when unnamespaced)"
            ),
        )
    return EntityIdentity(namespace or None, name)


def _reject_annotation_mismatches(classes: Sequence[type], model: Metamodel) -> None:
    """Reject every ``Rel`` annotation shape the accepted model contradicts.

    The whole annotation shape must agree with the compiled direction: a Many
    direction is spelled ``Rel[tuple[T, ...]]``, a One direction is scalar, and a
    scalar carries ``| None`` exactly where a loaded-null answer is possible — a
    defining to-one over a nullable join source, and every reverse to-one. Each
    disagreement is collected rather than raised, so one error reports them all
    in canonical order.
    """
    directions = relationship_view(model)
    families = inheritance_view(model)
    findings: list[tuple[tuple[str, str, str], str, str]] = []
    for cls in classes:
        shapes = members_of(cls).relationship_shapes
        for declared in declaration_of(cls).relationships:
            compiled = directions.relationship(declared.identity)
            if compiled is None:  # pragma: no cover - an accepted model compiles every direction
                continue
            annotation = shapes[declared.identity.name]
            multiplicity = compiled.cardinality.target
            nullable = multiplicity is Multiplicity.ONE and (
                not isinstance(declared, UnresolvedDefiningRelationshipDeclaration)
                or _nullable_source(declared.join.source, families)
            )
            if (annotation.multiplicity, annotation.nullable) == (multiplicity, nullable):
                continue
            findings.append(
                (
                    _order_key(declared.identity),
                    f"{cls.__name__}.{annotation.py_name}",
                    f"spells {_spelling(annotation.multiplicity, annotation.nullable)} but the "
                    f"accepted model requires {_spelling(multiplicity, nullable)}",
                )
            )
    if findings:
        findings.sort()
        raise EntityDefinitionError(
            code="entity-relationship-annotation-mismatch",
            message="every `Rel` annotation shape must agree with the accepted model:\n"
            + "\n".join(f"  {member} {detail}" for _, member, detail in findings),
        )


def _order_key(identity: RelationshipIdentity) -> tuple[str, str, str]:
    """The canonical report position of one relationship, composed from Entity order."""
    return (*identity.source_entity.sort_key, identity.name)


def _nullable_source(source: AttributeIdentity, families: InheritanceFacet) -> bool:
    """Whether a defining join's source Attribute admits a null, so the direction
    can answer loaded-null. Resolved family-effectively: the source may be
    declared on an ancestor and addressed at a descendant."""
    view = families.entity(source.entity)
    if view is None:  # pragma: no cover - the source Entity is in the accepted model
        return False
    attribute = view.applicable_attribute(source.name)
    return attribute is not None and attribute.nullable


def _spelling(multiplicity: Multiplicity, nullable: bool) -> str:
    if multiplicity is Multiplicity.MANY:
        return "Rel[tuple[T, ...]]"
    return "Rel[T | None]" if nullable else "Rel[T]"
