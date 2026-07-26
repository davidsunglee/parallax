"""The Metamodel Hub: one explicit, sealed model over a fixed source.

``MetamodelHub(*classes)`` returns a fully sealed hub or raises. There is no
``seal()`` operation and no unsealed, sealing, or rejected state, so every hub a
caller can name is authoritative and no model-dependent operation performs a
lifecycle check.

Construction runs one fixed sequence: left-to-right argument validation, whole-
model formation, and — for a class-backed hub — the Python realization phase,
which checks relationship annotation agreement and then claims the complete
class set atomically. A hub under construction belongs to the thread building
it: nothing else can name it until the claim publishes the Metamodel Binding
that retains it. So the hub assigns its own state before claiming, and the
atomic claim is at once the last step that can fail and the only step that
makes anything observable — a failure anywhere leaves neither a half-built hub
nor an orphaned class claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core._formation_profile import form_metamodel
from parallax.core.entity._binding import MetamodelBinding, claim
from parallax.core.entity._declaration import declaration_of, is_entity_class, members_of
from parallax.core.entity._errors import (
    METAMODEL_CLASS_NOT_BOUND,
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

__all__ = ["MetamodelHub", "SealedModel", "sealed_model"]


@dataclass(frozen=True, slots=True)
class _ClassSource:
    """The class-backed frontend's Unresolved Metamodel.

    Entity Classes *are* their own declarations, so the source is the validated
    argument tuple itself: nothing is adapted, mirrored, or copied.
    """

    entities: tuple[UnresolvedEntityDeclaration, ...]


class MetamodelHub:
    """One sealed model, composed from a fixed source.

    A class-backed hub additionally binds each Entity Class to its Entity
    Identity for that class object's lifetime; a descriptor-backed hub creates no
    binding. Both expose the identical compiler-owned accepted metadata.
    """

    __slots__ = ("_binding", "_model")

    _model: Metamodel
    _binding: MetamodelBinding | None

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
        ``entity-relationship-annotation-mismatch`` on annotation disagreement
        and :class:`~parallax.core.entity.MetamodelStateError` with
        ``metamodel-class-already-bound`` when another sealed hub already owns
        any of these classes.
        """
        entity_classes = _validated(classes)
        model = form_metamodel(_ClassSource(classes))
        _reject_annotation_mismatches(entity_classes, model)
        binding = MetamodelBinding(
            model=model,
            classes={cls: declaration_of(cls).identity for cls in entity_classes},
            owner=self,
        )
        self._publish(model, binding)
        claim(binding)

    @classmethod
    def _from_unresolved(cls, source: UnresolvedMetamodel) -> MetamodelHub:
        """Seal ``source`` into a fixed-source hub with no Entity Class binding.

        The private, versioned first-party seam the Descriptor Frontend reaches
        hub construction through. It is not a supported third-party extension
        point, and no registration, discovery, or lazy-import mechanism supplies
        it.
        """
        model = form_metamodel(source)
        hub = cls.__new__(cls)
        hub._publish(model, None)
        return hub

    def _publish(self, model: Metamodel, binding: MetamodelBinding | None) -> None:
        """Complete the hub's own state while it is still private to its builder."""
        self._model = model
        self._binding = binding

    @property
    def entities(self) -> Sequence[EntityMetadata]:
        """Every Entity's accepted local metadata, in canonical Entity order."""
        return self._model.entities

    def meta(self, key: type | str | EntityIdentity) -> EntityMetadata:
        """The accepted local metadata ``key`` names within this model.

        ``key`` is an Entity Class of this hub, a canonical spelling
        (``"sales.Order"``, or a bare ``"Order"`` for an unnamespaced Entity), or
        an :class:`EntityIdentity`. All three answer the same object.

        Raises :class:`MetamodelLookupError` with
        ``metamodel-invalid-entity-reference`` for a string that is not a
        canonical spelling, ``metamodel-class-not-bound`` for a class this hub
        did not claim, and ``metamodel-entity-not-found`` when the key is
        well-formed but names no Entity here.
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
        identity = None if self._binding is None else self._binding.identity_of(key)
        if identity is None:
            raise MetamodelLookupError(
                code=METAMODEL_CLASS_NOT_BOUND,
                message=(
                    f"{key.__name__} is not bound to this hub; a class belongs to the one "
                    "hub that claimed it, and a descriptor-backed hub claims none"
                ),
            )
        return identity


@dataclass(frozen=True, slots=True)
class SealedModel:
    """What one sealed hub holds, for a first-party runtime that is not the hub.

    Temporary support for the Snapshot composition root, which still connects to
    an accepted ``Metamodel`` rather than to the hub itself; ``binding`` is
    absent exactly for a descriptor-backed hub, whose model names no class.

    Reachable only through this private module — ``parallax.core.entity`` exports
    neither this class nor :func:`sealed_model` — so the pair advertises nothing
    and its planned removal breaks no supported import.
    """

    model: Metamodel
    binding: MetamodelBinding | None


def sealed_model(hub: MetamodelHub) -> SealedModel:
    """The accepted Metamodel and Metamodel Binding ``hub`` sealed.

    A free function rather than a method: reading a hub's own model is a
    first-party runtime seam, not part of the developer surface, which is
    ``meta(...)`` and ``entities`` alone.
    """
    return SealedModel(hub._model, hub._binding)  # pyright: ignore[reportPrivateUsage]


def _validated(classes: tuple[UnresolvedEntityDeclaration, ...]) -> tuple[type, ...]:
    """The argument tuple as Entity Classes, checked left to right."""
    if not classes:
        raise MetamodelDefinitionError(
            code=METAMODEL_EMPTY,
            message="a hub composes at least one Entity Class",
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
