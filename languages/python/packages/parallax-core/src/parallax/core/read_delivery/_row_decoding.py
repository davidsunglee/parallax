from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import cast

from parallax.core.base import (
    PresentDocument,
    SqlNull,
    UnknownFamilyTag,
    inert_scalar,
    unwrap_document_read,
)
from parallax.core.db_port import Row
from parallax.core.document_codec import (
    DocumentFinding,
    MemberShape,
    Present,
    decode_occurrence_classified,
    decode_scalar_many_classified,
    occurrence_shape,
    prepared_raw_member_classifier,
)
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, ValueObjectMetadata
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.read_delivery._convert import build_positional_many, build_positional_object
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._inheritance import (
    FixedRowIdentity,
    LiteralRowIdentity,
    ReadResultContract,
    TaggedRowIdentity,
)

__all__ = [
    "member_classifiers",
    "resolved_variants",
    "row_coordinates",
    "row_identity",
]

type MemberClassifier = Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]


def row_identity(
    contract: ReadResultContract, row: Row
) -> tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]:
    """The Entity ``row`` names, its `familyVariant` spelling, the stored tag no
    composed concrete claimed, and the row's shared document."""
    _require_arity(contract, row)
    source = contract.row_identity
    shared = contract.shared_document_ordinal
    # An isinstance chain rather than a class-pattern match: this runs per row,
    # and the match costs several times as much.
    if isinstance(source, FixedRowIdentity):
        if shared is None:
            return source.entity, None, None, None
        return source.entity, None, None, unwrap_document_read(_document_read(row[shared]))
    raw = row[cast("int", contract.identity_ordinal)]
    if isinstance(source, TaggedRowIdentity):
        answer = source.by_tag.get(raw)
        entity, variant, unknown = (
            (source.root, None, UnknownFamilyTag(raw)) if answer is None else answer
        )
    else:
        literal: LiteralRowIdentity = source
        entity, variant, unknown = literal.by_spelling[raw]
    if shared is None:
        return entity, variant, unknown, None
    return entity, variant, unknown, unwrap_document_read(_document_read(row[shared]))


def resolved_variants(
    contract: ReadResultContract,
) -> tuple[tuple[EntityIdentity, str | None], ...]:
    """Every `(Entity, familyVariant)` pair :func:`row_identity` can answer for
    a row of this read, including the family root a tag no composed concrete
    claims resolves to."""
    match contract.row_identity:
        case FixedRowIdentity(entity=entity):
            return ((entity, None),)
        case TaggedRowIdentity(root=root, tag_pairs=pairs):
            return tuple(
                dict.fromkeys(
                    ((root, None), *((identity, spelling) for _, identity, spelling in pairs))
                )
            )
        case LiteralRowIdentity(variants=variants):
            return tuple(dict.fromkeys((identity, spelling) for spelling, identity in variants))


def member_classifiers(
    contract: ReadResultContract,
    resolved: EntityIdentity,
    members: Sequence[AttributeMetadata | ValueObjectMetadata],
    document_member_names: Sequence[str | None],
) -> tuple[MemberClassifier | None, ...]:
    """The prepared, row-independent decoding walk of each of ``members`` a row
    resolving to ``resolved`` carries in a document, building positional
    output, and absence for every other member.

    A member located in the shared document is decoded by its DECLARED Neutral
    Type through the codec, not by the JSON value's own shape; one absent or
    explicitly null in the document reads as `None`, the same one logical
    answer a NULL Column gives. A scalar collection or occurrence stored in a
    document Column of its own is read against its declared definition.
    """
    shared = contract.shared_document
    entry = None if shared is None else shared.by_entity.get(resolved)
    direct = contract.direct_documents
    own_documents = frozenset(
        member.identity for member in (() if direct is None else direct.by_entity.get(resolved, ()))
    )
    return tuple(
        _located_classifier(None if entry is None else entry.shape, name)
        if name is not None
        else _direct_classifier(member)
        if member.identity in own_documents
        else None
        for member, name in zip(members, document_member_names, strict=True)
    )


def _direct_classifier(member: AttributeMetadata | ValueObjectMetadata) -> MemberClassifier:
    if isinstance(member, AttributeMetadata):
        return _collection_classifier(member)
    occurrence = member
    shape = occurrence_shape(occurrence)

    def classify(document_read: object) -> tuple[object, tuple[DocumentFinding, ...]]:
        decoded = decode_occurrence_classified(
            shape,
            _document_read(document_read),
            multiplicity=occurrence.multiplicity,
            nullable=occurrence.nullable,
            build_object=build_positional_object,
            build_many=build_positional_many,
        )
        findings = tuple(
            replace(finding, path=(occurrence.identity.path[-1], *finding.path))
            for finding in decoded.findings
        )
        value = decoded.presence.value if isinstance(decoded.presence, Present) else None
        return value, findings

    return classify


def _located_classifier(shape: MemberShape | None, member_name: str) -> MemberClassifier:
    if shape is None:  # pragma: no cover - a located resident belongs to its owner's shape
        raise SqlGenError(f"the shared document member {member_name!r} has no shape")
    classifier = prepared_raw_member_classifier(
        shape, member_name, build_object=build_positional_object, build_many=build_positional_many
    )
    return cast("MemberClassifier", classifier)


def _collection_classifier(attribute: AttributeMetadata) -> MemberClassifier:
    leaf = attribute.definition
    name = attribute.identity.name

    def classify(document_read: object) -> tuple[object, tuple[DocumentFinding, ...]]:
        value, findings = decode_scalar_many_classified(leaf, _document_read(document_read))
        if findings:
            findings = tuple(replace(finding, path=(name, *finding.path)) for finding in findings)
        return value, findings

    return classify


def row_coordinates(
    contract: ReadResultContract, rows: Sequence[Row]
) -> tuple[ContinuationCoordinate | None, ...]:
    """Each row's Continuation Order coordinate; absence for every row of a read
    that pages through nothing."""
    ordinals = contract.coordinate_ordinals
    if not ordinals:
        return (None,) * len(rows)
    return tuple(_coordinate(contract, row, ordinals) for row in rows)


def _coordinate(
    contract: ReadResultContract, row: Row, ordinals: tuple[int, ...]
) -> ContinuationCoordinate:
    _require_arity(contract, row)
    return ContinuationCoordinate(tuple(inert_scalar(row[ordinal]) for ordinal in ordinals))


def _require_arity(contract: ReadResultContract, row: Row) -> None:
    if len(row) != len(contract.slots):
        raise ValueError(
            f"result cell count {len(contract.slots)} does not match row arity {len(row)}"
        )


def _document_read(document_read: object) -> SqlNull | PresentDocument:
    if not isinstance(document_read, (SqlNull, PresentDocument)):
        raise _not_a_document_read(document_read)
    return document_read


def _not_a_document_read(value: object) -> SqlGenError:
    return SqlGenError(f"the database port returned {type(value).__name__}, not a DocumentRead")
