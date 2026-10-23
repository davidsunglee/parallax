from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Final, cast

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
    locate_raw_entity_member,
    occurrence_shape,
    prepared_raw_member_classifier,
)
from parallax.core.metamodel import AttributeMetadata, EntityIdentity
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
    "member_classifier",
    "member_sources",
    "publication_keys",
    "raw_member",
    "row_coordinates",
    "row_identity",
]

type MemberClassifier = Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]

_NO_KEYS: Final[Mapping[str, str]] = MappingProxyType({})
_NO_PATHS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})
_NOTHING_CLASSIFIED: Final[frozenset[str]] = frozenset()


def row_identity(
    contract: ReadResultContract, row: Row
) -> tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]:
    """The Entity ``row`` names, its `familyVariant` spelling, the stored tag no
    composed concrete claimed, and the row's shared document.

    Raises ``KeyError`` for a carrier the contract gives no result cell.
    """
    if len(row) != len(contract.result_keys):
        raise _arity_error(len(contract.result_keys), len(row))
    source = contract.row_identity
    shared = contract.shared_document
    # An isinstance chain rather than a class-pattern match: this runs per row,
    # and the match costs several times as much.
    if isinstance(source, FixedRowIdentity):
        if shared is None:
            return source.entity, None, None, None
        return (
            source.entity,
            None,
            None,
            unwrap_document_read(_document_read(row[contract.index_by_key[shared.column]])),
        )
    index_by_key = contract.index_by_key
    if isinstance(source, TaggedRowIdentity):
        raw = row[index_by_key[source.column]]
        answer = source.by_tag.get(raw)
        entity, variant, unknown = (
            (source.root, None, UnknownFamilyTag(raw)) if answer is None else answer
        )
        if shared is None:
            return entity, variant, unknown, None
        return (
            entity,
            variant,
            unknown,
            unwrap_document_read(_document_read(row[index_by_key[shared.column]])),
        )
    entity, variant, unknown = source.by_spelling[row[index_by_key[source.column]]]
    if shared is None:
        return entity, variant, unknown, None
    document_key = source.result_keys.get(entity, _NO_KEYS).get(shared.column, shared.column)
    return (
        entity,
        variant,
        unknown,
        unwrap_document_read(_document_read(row[index_by_key[document_key]])),
    )


def raw_member(
    contract: ReadResultContract, row: Row, resolved: EntityIdentity, key: str
) -> object:
    """``key``'s raw stored value on a row resolving to ``resolved``: located in
    the row's shared document when that document carries the member, and read
    from the row's own result cell otherwise.

    Raises ``KeyError`` for a key the row carries neither way.
    """
    shared = contract.shared_document
    if shared is not None:
        try:
            document_read = _value(contract, row, _result_key(contract, resolved, shared.column))
            entry = shared.by_entity.get(resolved)
            return _shared_member(
                document_read, _NO_PATHS if entry is None else entry.member_paths, key
            )
        except KeyError:
            pass
    return _value(contract, row, _result_key(contract, resolved, key))


def _shared_member(
    document_read: object, member_paths: Mapping[str, tuple[str, ...]], key: str
) -> object:
    path = member_paths.get(key)
    if path is None:
        raise KeyError(key)
    document = _document_read(document_read)
    if isinstance(document, SqlNull):
        return document
    return locate_raw_entity_member(document.document, path[0])


def member_classifier(
    contract: ReadResultContract, resolved: EntityIdentity, key: str
) -> MemberClassifier:
    """The prepared, row-independent decoding walk of one classified member of a
    row resolving to ``resolved``, building positional output.

    A member the shared document carries is located in it and decoded by its
    DECLARED Neutral Type through the codec, not by the JSON value's own shape;
    one absent or explicitly null in the document reads as `None`, the same one
    logical answer a NULL Column gives. Any other member is read from its own
    document Column against its declared definition. Raises ``KeyError`` for a
    member neither carries.
    """
    shared = contract.shared_document
    if shared is not None:
        entry = shared.by_entity.get(resolved)
        try:
            return _located_classifier(
                None if entry is None else entry.shape,
                _NO_PATHS if entry is None else entry.member_paths,
                key,
            )
        except KeyError:
            pass
    direct = contract.direct_documents
    if direct is None:
        raise KeyError(key)
    member = next(
        (item for item in direct.by_entity.get(resolved, ()) if item.storage.name == key),
        None,
    )
    if member is None:
        raise KeyError(key)
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


def _located_classifier(
    shape: MemberShape | None,
    member_paths: Mapping[str, tuple[str, ...]],
    key: str,
) -> MemberClassifier:
    if shape is None:
        raise KeyError(key)
    path = member_paths.get(key)
    if path is None:
        raise KeyError(key)
    classifier = prepared_raw_member_classifier(
        shape, path[0], build_object=build_positional_object, build_many=build_positional_many
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


def member_sources(
    contract: ReadResultContract, resolved: EntityIdentity, keys: tuple[str, ...]
) -> tuple[
    frozenset[str],
    tuple[int | None, ...],
    tuple[MemberClassifier | None, ...],
    tuple[str | None, ...],
]:
    """Where each of ``keys`` is read on a row resolving to ``resolved``.

    Answers the keys whose document carriers require classification, then for
    each key its positional result ordinal, its positional-output classifier,
    and its direct key in the row's unwrapped shared document. A classified key
    has no ordinal, an unclassified one no classifier, and a key no result cell
    carries no ordinal either.
    """
    classified = contract.classified_by_entity.get(resolved, _NOTHING_CLASSIFIED)
    index_by_key = contract.index_by_key
    shared = contract.shared_document
    entry = None if shared is None else shared.by_entity.get(resolved)
    member_paths = _NO_PATHS if entry is None else entry.member_paths
    return (
        classified,
        tuple(
            None if key in classified else index_by_key.get(_result_key(contract, resolved, key))
            for key in keys
        ),
        tuple(
            member_classifier(contract, resolved, key) if key in classified else None
            for key in keys
        ),
        tuple(None if (path := member_paths.get(key)) is None else path[0] for key in keys),
    )


def row_coordinates(
    contract: ReadResultContract, rows: Sequence[Row]
) -> tuple[ContinuationCoordinate | None, ...]:
    """Each row's Continuation Order coordinate; absence for every row of a read
    that pages through nothing."""
    aliases = contract.coordinate_reads
    if not aliases:
        return (None,) * len(rows)
    return tuple(_coordinate(contract, row, aliases) for row in rows)


def _coordinate(
    contract: ReadResultContract, row: Row, aliases: tuple[str, ...]
) -> ContinuationCoordinate:
    _require_arity(contract, row)
    return ContinuationCoordinate(
        tuple(inert_scalar(_value(contract, row, alias)) for alias in aliases)
    )


def publication_keys(
    contract: ReadResultContract, resolved: EntityIdentity, variant: str | None
) -> tuple[str, ...]:
    """The logical flat-row keys a row resolving to ``resolved`` publishes once
    its identity and documents are decoded, in result order.

    A tag column and a union's per-branch aliases leave the row, a union
    branch's aliases are renamed to the keys they carry, the shared Structured
    Column gives way to its siblings' padding, and coordinate aliases are
    dropped.
    """
    values: dict[str, object] = {key: None for key in contract.result_keys}
    match contract.row_identity:
        case FixedRowIdentity():
            pass
        case TaggedRowIdentity(column=column):
            values.pop(column)
        case LiteralRowIdentity() as source:
            _publish_literal(source, values, variant)
    shared = contract.shared_document
    if shared is not None:
        values.pop(_result_key(contract, resolved, shared.column), None)
        entry = shared.by_entity.get(resolved)
        if entry is not None:
            values.update(dict.fromkeys(entry.padding))
    for alias in contract.coordinate_reads:
        values.pop(alias, None)
    return tuple(values)


def _publish_literal(
    source: LiteralRowIdentity, values: dict[str, object], variant: str | None
) -> None:
    # The moved values are lifted before the drop, so an alias may be both a
    # source and discarded.
    if variant is None:  # pragma: no cover - a literal resolution always names its branch
        raise SqlGenError("a union row must name its resolved family variant")
    values[source.column] = variant
    spelling = cast("str", values.pop(source.column))
    moved = tuple(
        (rendered_key, values[alias])
        for alias, rendered_key in source.renames[spelling]
        if alias in values
    )
    for alias in source.drop:
        values.pop(alias, None)
    for rendered_key, value in moved:
        values[rendered_key] = value


def _result_key(contract: ReadResultContract, entity: EntityIdentity, rendered_key: str) -> str:
    """The provider key carrying one resolved Entity's ``rendered_key``: a union
    result alias for a branch-local key, and the key itself otherwise."""
    source = contract.row_identity
    if isinstance(source, LiteralRowIdentity):
        return source.result_keys.get(entity, _NO_KEYS).get(rendered_key, rendered_key)
    return rendered_key


def _require_arity(contract: ReadResultContract, row: Row) -> None:
    if len(row) != len(contract.result_keys):
        raise _arity_error(len(contract.result_keys), len(row))


def _arity_error(arity: int, width: int) -> ValueError:
    return ValueError(f"result key count {arity} does not match row arity {width}")


def _value(contract: ReadResultContract, row: Row, key: str) -> object:
    try:
        return row[contract.index_by_key[key]]
    except KeyError as error:
        raise KeyError(key) from error


def _document_read(document_read: object) -> SqlNull | PresentDocument:
    if not isinstance(document_read, (SqlNull, PresentDocument)):
        raise _not_a_document_read(document_read)
    return document_read


def _not_a_document_read(value: object) -> SqlGenError:
    return SqlGenError(f"the database port returned {type(value).__name__}, not a DocumentRead")
