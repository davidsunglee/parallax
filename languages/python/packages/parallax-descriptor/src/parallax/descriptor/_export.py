"""Canonical export over the accepted Metamodel (m-descriptor).

The inverse of ingestion: an accepted :class:`~parallax.core.metamodel.Metamodel`
becomes the canonical minimal descriptor document — the same byte-for-byte form
:func:`~parallax.descriptor._serde.canonicalize` produces from a parsed
document. Export reads only the representation-independent Metadata (identities,
closed value vocabularies, storage locations) and renews no validation: an
accepted model is exportable by contract, so the only way export fails is an
implementation defect, which surfaces as :class:`DescriptorExportError` rather
than a :class:`DescriptorError`.

Every optional key whose value equals the fact ingestion re-derives is dropped —
a column that matches its member's portable derived default, a Read Write
persistence mode, a Columns storage layout, an application-assigned generation,
and the other members of the omission set — and the single-versus-multi
``entity``/``entities`` form is chosen by entity count.
"""

from __future__ import annotations

from typing import Final, Literal

from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    ApplicationAssigned,
    AttributeMetadata,
    Cardinality,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    Document,
    EntityIdentity,
    EntityMetadata,
    IndexMetadata,
    InheritanceMetadata,
    Max,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    NullPlacement,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipOrder,
    Sequence,
    SortDirection,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    default_column_name,
    derive_primary_key_index,
    temporality_profile,
)
from parallax.descriptor._type_spelling import format_type_spelling

__all__ = ["DESCRIPTOR_EXPORT_FAILED", "DescriptorExportError", "export_document"]

DESCRIPTOR_EXPORT_FAILED: Final[str] = "descriptor-export-failed"
"""The sole code every :class:`DescriptorExportError` carries."""

type ExportTarget = Literal["document", "json", "yaml"]
"""The canonical form an export was producing when a defect interrupted it."""


class DescriptorExportError(RuntimeError):
    """A canonical export hit an implementation defect, not a model defect.

    An accepted Metamodel is exportable by contract, so export renews no
    validation and can fail only through a conversion or serialization bug.
    ``target`` names the form under production and ``cause`` retains the original
    defect, also chained natively. Like ``FormationContractError`` it is an
    adapter-defect boundary; it is never raised as, or translated to, a
    :class:`~parallax.descriptor._errors.DescriptorError`, whose subtypes are
    ingestion failures over documents. No partial output escapes, and the model
    is left unchanged.
    """

    code: str
    target: ExportTarget
    cause: BaseException

    def __init__(self, target: ExportTarget, cause: BaseException) -> None:
        self.code = DESCRIPTOR_EXPORT_FAILED
        self.target = target
        self.cause = cause
        super().__init__(f"{DESCRIPTOR_EXPORT_FAILED} [{target}]: {cause}")


def export_document(metamodel: Metamodel) -> dict[str, object]:
    """The canonical minimal descriptor document for an accepted ``metamodel``.

    Structurally equal to :func:`~parallax.descriptor._serde.canonicalize` over
    the same logical model, and deterministic: repeated exports of one accepted
    Metamodel are equal. Returns the complete document or, on an implementation
    defect, raises :class:`DescriptorExportError` with no partial output.
    """
    try:
        entities = tuple(metamodel.entities)
        if len(entities) == 1:
            return {"entity": _entity(entities[0])}
        return {"entities": [_entity(entity) for entity in entities]}
    except Exception as error:
        raise DescriptorExportError("document", error) from error


_CARDINALITIES: Final[dict[Cardinality, str]] = {
    Cardinality.ONE_TO_ONE: "one-to-one",
    Cardinality.MANY_TO_ONE: "many-to-one",
    Cardinality.ONE_TO_MANY: "one-to-many",
}

_MULTIPLICITIES: Final[dict[Multiplicity, str]] = {
    Multiplicity.ONE: "one",
    Multiplicity.MANY: "many",
}


def _entity(entity: EntityMetadata) -> dict[str, object]:
    identity = entity.identity
    out: dict[str, object] = {"name": identity.name}
    if identity.namespace is not None:
        out["namespace"] = identity.namespace
    if entity.declared_container is not None:
        out["table"] = entity.declared_container.name
    if entity.declared_persistence is PersistenceMode.READ_ONLY and not _is_family_descendant(
        entity
    ):
        out["persistence"] = "read-only"
    layout = entity.declared_layout
    if isinstance(layout, Document) and not _is_family_descendant(entity):
        out["layout"] = {"document": {"column": layout.column.name}}
    temporality = _temporality(entity)
    if temporality is not None and not _is_family_descendant(entity):
        out["temporality"] = temporality
    attributes = _authored_attributes(entity)
    if attributes:
        out["attributes"] = [_attribute(a) for a in attributes]
    if entity.declared_relationships:
        out["relationships"] = [_relationship(r) for r in entity.declared_relationships]
    indices = _authored_indices(entity)
    if indices:
        out["indices"] = [_index(i) for i in indices]
    if entity.declared_value_objects:
        out["valueObjects"] = [_value_object(v) for v in entity.declared_value_objects]
    if entity.inheritance is not None:
        out["inheritance"] = _inheritance(entity.inheritance)
    return out


def _temporality(entity: EntityMetadata) -> str | None:
    """The Temporality Profile ``entity``'s axes came from, or ``None`` for none.

    Non-Temporal is what omission means, so it is never spelled; every other
    profile is exactly the one whose derivation yields the Entity's own axes.
    """
    profile = temporality_profile(axis.dimension for axis in entity.declared_as_of_axes)
    return None if profile == "nontemporal" else profile


def _authored_attributes(entity: EntityMetadata) -> tuple[AttributeMetadata, ...]:
    """The Entity's Attributes minus the endpoints its declared axes point at.

    Canonical form spells what an author writes. Both endpoints of every axis are
    derived from the profile, so exporting them would put members in the document
    that re-importing would derive a second time. Endpoints are matched by
    Identity rather than by canonical name, which is what keeps a profile from
    ever being exported beside the very Attributes it derives.

    Identity matching removes the extra members, not every difference. The
    document language denotes an axis only through its profile, so an endpoint
    bearing a nonconventional name, or a conventional name over a nonconventional
    Column, re-imports under the canonical name over the framework-fixed Column.
    Reaching either shape takes a Metamodel built directly against the
    ``m-metamodel`` seam, which accepts an axis over any distinct pair of local
    Timestamp Attributes; every Entity a descriptor document produces carries the
    canonical pair, so export inverts ingestion exactly over that set.
    """
    derived = {
        endpoint
        for axis in entity.declared_as_of_axes
        for endpoint in (axis.start_attribute, axis.end_attribute)
    }
    return tuple(
        attribute for attribute in entity.declared_attributes if attribute.identity not in derived
    )


def _authored_indices(entity: EntityMetadata) -> tuple[IndexMetadata, ...]:
    """The Entity's Indices minus the one it derives.

    Canonical form spells what an author writes. The primary-key Index is derived
    from the declared key and axes, so exporting it would put a member in the
    document that re-importing would derive a second time.
    """
    derived = derive_primary_key_index(
        entity=entity.identity,
        container=entity.declared_container,
        attributes=entity.declared_attributes,
        as_of_axes=entity.declared_as_of_axes,
    )
    if derived is None:
        return tuple(entity.indices)
    return tuple(index for index in entity.indices if index.identity != derived.identity)


def _is_family_descendant(entity: EntityMetadata) -> bool:
    """Whether ``entity`` occupies a non-root family position.

    Persistence, Storage Layout, and the Temporality Profile are family-wide and
    root-owned, so a descendant never spells any of them in canonical form even
    when its own metadata carries one — absence there means inherit, and only the
    root ever writes the family fact.
    """
    return isinstance(entity.inheritance, (AbstractSubtype, ConcreteSubtype))


def _attribute(attribute: AttributeMetadata) -> dict[str, object]:
    out: dict[str, object] = {
        "name": attribute.identity.name,
        "type": format_type_spelling(attribute.type),
    }
    if attribute.storage.name != default_column_name(attribute.identity.name):
        out["column"] = attribute.storage.name
    if isinstance(attribute.primary_key, PrimaryKey):
        out["primaryKey"] = True
    if attribute.nullable:
        out["nullable"] = True
    if attribute.max_length is not None:
        out["maxLength"] = attribute.max_length
    if attribute.read_only:
        out["readOnly"] = True
    if attribute.optimistic_locking:
        out["optimisticLocking"] = True
    if isinstance(attribute.primary_key, PrimaryKey):
        generation = _pk_generation(attribute.primary_key.generation)
        if generation is not None:
            out["pkGeneration"] = generation
    return out


def _pk_generation(generation: PkGeneration) -> object | None:
    """The ``pkGeneration`` spelling, or ``None`` when application-assigned.

    Application Assigned is the default a bare declared key re-derives, so it is
    omitted; ``max`` is the bare strategy token; a Sequence is the object form
    with its name and every non-default sizing parameter.
    """
    match generation:
        case ApplicationAssigned():
            return None
        case Max():
            return "max"
        case Sequence():
            out: dict[str, object] = {"strategy": "sequence", "name": generation.name}
            if generation.batch_size != 1:
                out["batchSize"] = generation.batch_size
            if generation.initial_value != 1:
                out["initialValue"] = generation.initial_value
            if generation.increment_size != 1:
                out["incrementSize"] = generation.increment_size
            return out


def _relationship(relationship: RelationshipDeclaration) -> dict[str, object]:
    out: dict[str, object] = {"name": relationship.identity.name}
    if isinstance(relationship, DefiningRelationshipDeclaration):
        out["cardinality"] = _CARDINALITIES[relationship.cardinality]
        out["join"] = {
            "source": relationship.join.source.name,
            "target": {
                "entity": relationship.join.target.entity.canonical,
                "attribute": relationship.join.target.name,
            },
        }
        if relationship.dependent:
            out["dependent"] = True
    else:
        peer = relationship.reverse_of
        out["reverseOf"] = f"{peer.source_entity.canonical}.{peer.name}"
    if relationship.order_by:
        out["orderBy"] = [_order_by(term) for term in relationship.order_by]
    return out


def _order_by(term: RelationshipOrder) -> dict[str, object]:
    out: dict[str, object] = {"attribute": term.attribute.name}
    if term.direction is SortDirection.DESCENDING:
        out["direction"] = "desc"
    if term.nulls is NullPlacement.NULLS_FIRST:
        out["nulls"] = "first"
    return out


def _index(index: IndexMetadata) -> dict[str, object]:
    out: dict[str, object] = {
        "name": index.identity.name,
        "attributes": [component.name for component in index.attributes],
    }
    if index.unique:
        out["unique"] = True
    return out


def _inheritance(inheritance: InheritanceMetadata) -> dict[str, object]:
    match inheritance:
        case AbstractRoot(strategy):
            out: dict[str, object] = {}
            match strategy:
                case TablePerHierarchy(tag_column):
                    out["strategy"] = "table-per-hierarchy"
                    out["role"] = "root"
                    out["tag"] = {"column": tag_column}
                case TablePerConcreteSubtype():
                    out["strategy"] = "table-per-concrete-subtype"
                    out["role"] = "root"
            return out
        case AbstractSubtype(parent):
            return {"role": "abstract-subtype", "parent": _parent(parent)}
        case ConcreteSubtype(parent, tag_value):
            out = {"role": "concrete-subtype", "parent": _parent(parent)}
            if tag_value is not None:
                out["tagValue"] = tag_value
            return out


def _parent(parent: EntityIdentity) -> str:
    """Canonical form spells an inheritance parent exactly, as it already spells a
    relationship target and a ``reverseOf`` peer — a bare parent is legal input,
    relative to the child's namespace, but never an exported spelling."""
    return parent.canonical


def _value_object(occurrence: ValueObjectMetadata) -> dict[str, object]:
    name = occurrence.identity.path[-1]
    out: dict[str, object] = {"name": name}
    if occurrence.storage.name != default_column_name(name):
        out["column"] = occurrence.storage.name
    if occurrence.nullable:
        out["nullable"] = True
    if occurrence.multiplicity is not Multiplicity.ONE:
        out["multiplicity"] = _MULTIPLICITIES[occurrence.multiplicity]
    if occurrence.attributes:
        out["attributes"] = [_vo_attribute(a) for a in occurrence.attributes]
    if occurrence.value_objects:
        out["valueObjects"] = [_nested_value_object(n) for n in occurrence.value_objects]
    return out


def _nested_value_object(occurrence: NestedValueObjectMetadata) -> dict[str, object]:
    out: dict[str, object] = {"name": occurrence.identity.path[-1]}
    if occurrence.nullable:
        out["nullable"] = True
    if occurrence.multiplicity is not Multiplicity.ONE:
        out["multiplicity"] = _MULTIPLICITIES[occurrence.multiplicity]
    if occurrence.attributes:
        out["attributes"] = [_vo_attribute(a) for a in occurrence.attributes]
    if occurrence.value_objects:
        out["valueObjects"] = [_nested_value_object(n) for n in occurrence.value_objects]
    return out


def _vo_attribute(attribute: ValueObjectAttributeMetadata) -> dict[str, object]:
    out: dict[str, object] = {
        "name": attribute.identity.name,
        "type": format_type_spelling(attribute.type),
    }
    if attribute.nullable:
        out["nullable"] = True
    return out
