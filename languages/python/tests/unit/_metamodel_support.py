"""Hand-built Unresolved Metamodel views for the ``m-metamodel`` suites.

The formation seam is enumeration-only, so a frontend needs nothing but a
read-only object per Entity; these two frozen records are that, and they exist
to prove the protocols require no record graph of their own. Shared by the
resolver and compiler suites.

Exported names carry no leading underscore: importing an underscored name
across modules is a ``reportPrivateUsage`` error under pyright strict, so
privacy is carried by this MODULE's underscore. Never imported by production
code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.base import INT64, TIMESTAMP, NeutralType
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    NOT_PRIMARY_KEY,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    AttributePrimaryKey,
    CandidateMetamodel,
    Column,
    EntityIdentity,
    IndexMetadata,
    IssueCode,
    MetamodelIssue,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    Rejected,
    Resolved,
    StorageContainer,
    StorageLayout,
    UnresolvedEntityDeclaration,
    UnresolvedInheritance,
    UnresolvedRelationshipDeclaration,
    ValueObjectOccurrenceDeclaration,
    default_column_name,
    resolve,
)

NAMESPACE: Final[str] = "parallax.test"


@dataclass(frozen=True, slots=True)
class Declaration:
    """One Entity exactly as a frontend would hand it to formation."""

    identity: EntityIdentity
    container: StorageContainer | None = None
    persistence: PersistenceMode | None = None
    layout: StorageLayout | None = None
    attributes: tuple[AttributeMetadata, ...] = ()
    relationships: tuple[UnresolvedRelationshipDeclaration, ...] = ()
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...] = ()
    as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    inheritance: UnresolvedInheritance | None = None
    indices: tuple[IndexMetadata, ...] = ()


@dataclass(frozen=True, slots=True)
class Source:
    """An Unresolved Metamodel over hand-built declarations."""

    entities: tuple[UnresolvedEntityDeclaration, ...]


def identity(name: str, namespace: str | None = NAMESPACE) -> EntityIdentity:
    """An Entity Identity in the suites' default namespace."""
    return EntityIdentity(namespace, name)


def attribute(
    entity: EntityIdentity,
    name: str,
    *,
    type: NeutralType = INT64,
    primary_key: AttributePrimaryKey = NOT_PRIMARY_KEY,
    column: str | None = None,
) -> AttributeMetadata:
    """An Attribute of ``entity`` whose column uses the portable default."""
    return AttributeMetadata(
        identity=AttributeIdentity(entity, name),
        type=type,
        storage=Column(default_column_name(name) if column is None else column),
        primary_key=primary_key,
    )


def key(
    entity: EntityIdentity, name: str = "id", *, generation: PkGeneration = APPLICATION_ASSIGNED
) -> AttributeMetadata:
    """A primary-key Attribute of ``entity``."""
    return attribute(entity, name, primary_key=PrimaryKey(generation))


def instant(entity: EntityIdentity, name: str) -> AttributeMetadata:
    """A Timestamp Attribute of ``entity``, suitable as an axis endpoint."""
    return attribute(entity, name, type=TIMESTAMP)


def source(*declarations: UnresolvedEntityDeclaration) -> Source:
    """An Unresolved Metamodel over ``declarations`` in frontend order."""
    return Source(declarations)


def accepted(model: Source) -> CandidateMetamodel:
    """The candidate ``model`` resolves to; fails the test when it is rejected."""
    result = resolve(model)
    if isinstance(result, Rejected):
        raise AssertionError(
            f"unexpected resolution issues: {[issue.code for issue in result.issues]}"
        )
    return result.candidate


def rejection(model: Source) -> tuple[MetamodelIssue, ...]:
    """The canonically ordered issues ``model`` is rejected with."""
    result = resolve(model)
    if isinstance(result, Resolved):
        raise AssertionError("expected resolution to reject the model")
    return result.issues


def codes(model: Source) -> tuple[IssueCode, ...]:
    """The Issue Codes ``model`` is rejected with, in canonical order."""
    return tuple(issue.code for issue in rejection(model))
