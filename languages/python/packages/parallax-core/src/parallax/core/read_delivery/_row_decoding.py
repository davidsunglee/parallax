from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
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
    DecodedMember,
    DocumentFinding,
    MemberShape,
    Present,
    decode_occurrence_classified,
    decode_scalar_many_classified,
    locate_raw_entity_member,
    occurrence_shape,
    prepared_raw_member_classifier,
)
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, Multiplicity
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.read_delivery._convert import build_positional_many, build_positional_object
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen._inheritance import ByLiteral, ByTag, FixedIdentity, ResultContract

__all__ = [
    "RowIdentityReader",
    "member_classifier",
    "member_sources",
    "publication_keys",
    "raw_member",
    "row_coordinates",
    "row_identity_reader",
]

type RowIdentityReader = Callable[
    [Row | Mapping[str, object]],
    tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None],
]
"""Answers the Entity one row names, its `familyVariant` spelling, the stored tag
no composed concrete claimed, and the row's shared document."""

type MemberClassifier = Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]

type _Identity = tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]
type _Answer = tuple[EntityIdentity, str | None, UnknownFamilyTag | None]

_NO_KEYS: Final[Mapping[str, str]] = MappingProxyType({})
_NO_PATHS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})


def row_identity_reader(contract: ResultContract) -> RowIdentityReader:
    """The reader of ``contract``'s row identities, chosen once per bound read.

    The row identity is matched and every carrier's positional ordinal resolved
    here, so a positional row costs an arity check and direct indexing. A
    contract with no result cell for a carrier reads every row by key, which
    refuses a row by the key it lacks.
    """
    source = contract.resolve
    match source:
        case FixedIdentity():
            reader = _fixed_reader(contract, source)
        case ByTag():
            reader = _tag_reader(contract, source)
        case ByLiteral():
            reader = _literal_reader(contract, source)
    if reader is not None:
        return reader

    def keyed(row: Row | Mapping[str, object]) -> _Identity:
        return _row_identity(contract, row)

    return keyed


def _fixed_reader(contract: ResultContract, source: FixedIdentity) -> RowIdentityReader | None:
    arity = len(contract.result_keys)
    entity = source.entity
    shared = contract.shared_document
    if shared is None:
        identity: _Identity = (entity, None, None, None)

        def fixed(row: Row | Mapping[str, object]) -> _Identity:
            if isinstance(row, tuple) and len(row) != arity:
                raise _arity_error(arity, len(row))
            return identity

        return fixed
    document = contract.index_by_key.get(shared.column)
    if document is None:
        return None

    def documented(row: Row | Mapping[str, object]) -> _Identity:
        if not isinstance(row, tuple):
            return _row_identity(contract, row)
        if len(row) != arity:
            raise _arity_error(arity, len(row))
        return entity, None, None, _observed_document(row[document])

    return documented


def _tag_reader(contract: ResultContract, source: ByTag) -> RowIdentityReader | None:
    arity = len(contract.result_keys)
    index_by_key = contract.index_by_key
    shared = contract.shared_document
    carrier = index_by_key.get(source.column)
    document = None if shared is None else index_by_key.get(shared.column)
    if carrier is None or (shared is not None and document is None):
        return None
    by_tag = cast("Mapping[object, _Answer]", source.by_tag)
    root = source.root

    def tagged(row: Row | Mapping[str, object]) -> _Identity:
        if not isinstance(row, tuple):
            return _row_identity(contract, row)
        if len(row) != arity:
            raise _arity_error(arity, len(row))
        raw = row[carrier]
        answer = by_tag.get(raw)
        if answer is None:
            answer = (root, None, UnknownFamilyTag(raw))
        entity, variant, unknown = answer
        return (
            entity,
            variant,
            unknown,
            None if document is None else _observed_document(row[document]),
        )

    return tagged


def _literal_reader(contract: ResultContract, source: ByLiteral) -> RowIdentityReader | None:
    arity = len(contract.result_keys)
    index_by_key = contract.index_by_key
    shared = contract.shared_document
    carrier = index_by_key.get(source.column)
    documents = (
        None
        if shared is None
        else {
            identity: ordinal
            for _spelling, identity in source.variants
            if (
                ordinal := index_by_key.get(
                    source.result_keys.get(identity, _NO_KEYS).get(shared.column, shared.column)
                )
            )
            is not None
        }
    )
    if carrier is None or (documents is not None and len(documents) != len(source.variants)):
        return None
    by_spelling = cast("Mapping[object, _Answer]", source.by_spelling)

    def literal(row: Row | Mapping[str, object]) -> _Identity:
        if not isinstance(row, tuple):
            return _row_identity(contract, row)
        if len(row) != arity:
            raise _arity_error(arity, len(row))
        entity, variant, unknown = by_spelling[row[carrier]]
        return (
            entity,
            variant,
            unknown,
            None if documents is None else _observed_document(row[documents[entity]]),
        )

    return literal


def _row_identity(contract: ResultContract, row: Row | Mapping[str, object]) -> _Identity:
    _require_arity(contract, row)
    source = contract.resolve
    match source:
        case FixedIdentity():
            resolved, variant, unknown = source.answer
        case ByTag():
            raw = _value(contract, row, source.column)
            answer = source.by_tag.get(cast("str", raw))
            resolved, variant, unknown = (
                (source.root, None, UnknownFamilyTag(raw)) if answer is None else answer
            )
        case ByLiteral():
            resolved, variant, unknown = source.by_spelling[
                cast("str", _value(contract, row, source.column))
            ]
    shared = contract.shared_document
    document = (
        None
        if shared is None
        else _observed_document(
            _value(contract, row, _result_key(contract, resolved, shared.column))
        )
    )
    return resolved, variant, unknown, document


def _observed_document(document_read: object) -> object | None:
    """Unwrap a provider-neutral document carrier for predecessor retention."""
    if not isinstance(document_read, (SqlNull, PresentDocument)):
        raise _not_a_document_read(document_read)
    return unwrap_document_read(document_read)


def raw_member(
    contract: ResultContract, row: Row | Mapping[str, object], resolved: EntityIdentity, key: str
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
    contract: ResultContract,
    resolved: EntityIdentity,
    key: str,
    *,
    build_object: Callable[[MemberShape, Iterable[object]], object] | None = None,
    build_many: Callable[[Iterable[object]], object] | None = None,
) -> MemberClassifier:
    """The prepared, row-independent decoding walk of one classified member of a
    row resolving to ``resolved``.

    A member the shared document carries is located in it and decoded by its
    DECLARED Neutral Type through the codec, not by the JSON value's own shape;
    one absent or explicitly null in the document reads as `None`, the same one
    logical answer a NULL Column gives. Any other member is read from its own
    document Column against its declared definition. Raises ``KeyError`` for a
    member neither carries; the output builders are supplied together or not at
    all.
    """
    shared = contract.shared_document
    if shared is not None:
        entry = shared.by_entity.get(resolved)
        try:
            return _located_classifier(
                None if entry is None else entry.shape,
                _NO_PATHS if entry is None else entry.member_paths,
                key,
                build_object=build_object,
                build_many=build_many,
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
        decoded = _classified_occurrence(
            shape,
            _document_read(document_read),
            multiplicity=occurrence.multiplicity,
            nullable=occurrence.nullable,
            build_object=build_object,
            build_many=build_many,
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
    *,
    build_object: Callable[[MemberShape, Iterable[object]], object] | None,
    build_many: Callable[[Iterable[object]], object] | None,
) -> MemberClassifier:
    if shape is None:
        raise KeyError(key)
    path = member_paths.get(key)
    if path is None:
        raise KeyError(key)
    if (build_object is None) != (build_many is None):
        raise ValueError("object and many output builders must be supplied together")
    classifier = (
        prepared_raw_member_classifier(shape, path[0])
        if build_object is None or build_many is None
        else prepared_raw_member_classifier(
            shape, path[0], build_object=build_object, build_many=build_many
        )
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


def _classified_occurrence(
    shape: MemberShape,
    document_read: SqlNull | PresentDocument,
    *,
    multiplicity: Multiplicity,
    nullable: bool,
    build_object: Callable[[MemberShape, Iterable[object]], object] | None = None,
    build_many: Callable[[Iterable[object]], object] | None = None,
) -> DecodedMember:
    """Classify and construct one complete occurrence exactly once."""
    if (build_object is None) != (build_many is None):
        raise ValueError("object and many output builders must be supplied together")
    if build_object is None or build_many is None:
        return decode_occurrence_classified(
            shape,
            document_read,
            multiplicity=multiplicity,
            nullable=nullable,
        )
    return decode_occurrence_classified(
        shape,
        document_read,
        multiplicity=multiplicity,
        nullable=nullable,
        build_object=build_object,
        build_many=build_many,
    )


def member_sources(
    contract: ResultContract, resolved: EntityIdentity, keys: tuple[str, ...]
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
    classified = contract.classified_by_entity.get(resolved, frozenset())
    source = contract.resolve
    renames = (
        source.result_keys.get(resolved, _NO_KEYS) if isinstance(source, ByLiteral) else _NO_KEYS
    )
    index_by_key = contract.index_by_key
    shared = contract.shared_document
    entry = None if shared is None else shared.by_entity.get(resolved)
    member_paths = _NO_PATHS if entry is None else entry.member_paths
    return (
        classified,
        tuple(
            None if key in classified else index_by_key.get(renames.get(key, key)) for key in keys
        ),
        tuple(
            member_classifier(
                contract,
                resolved,
                key,
                build_object=build_positional_object,
                build_many=build_positional_many,
            )
            if key in classified
            else None
            for key in keys
        ),
        tuple(None if (path := member_paths.get(key)) is None else path[0] for key in keys),
    )


def row_coordinates(
    contract: ResultContract, rows: Sequence[Row | Mapping[str, object]]
) -> tuple[ContinuationCoordinate | None, ...]:
    """Each row's Continuation Order coordinate; absence for every row of a read
    that pages through nothing."""
    aliases = contract.coordinate_reads
    if not aliases:
        return (None,) * len(rows)
    return tuple(_coordinate(contract, row, aliases) for row in rows)


def _coordinate(
    contract: ResultContract, row: Row | Mapping[str, object], aliases: tuple[str, ...]
) -> ContinuationCoordinate:
    _require_arity(contract, row)
    return ContinuationCoordinate(
        tuple(inert_scalar(_value(contract, row, alias)) for alias in aliases)
    )


def publication_keys(
    contract: ResultContract, resolved: EntityIdentity, variant: str | None
) -> tuple[str, ...]:
    """The logical flat-row keys a row resolving to ``resolved`` publishes once
    its identity and documents are decoded, in result order.

    A tag column and a union's per-branch aliases leave the row, a union
    branch's aliases are renamed to the keys they carry, the shared Structured
    Column gives way to its siblings' padding, and coordinate aliases are
    dropped.
    """
    values: dict[str, object] = {key: None for key in contract.result_keys}
    match contract.resolve:
        case FixedIdentity():
            pass
        case ByTag(column=column):
            values.pop(column)
        case ByLiteral() as source:
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


def _publish_literal(source: ByLiteral, values: dict[str, object], variant: str | None) -> None:
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


def _result_key(contract: ResultContract, entity: EntityIdentity, rendered_key: str) -> str:
    """The provider key carrying one resolved Entity's ``rendered_key``: a union
    result alias for a branch-local key, and the key itself otherwise."""
    source = contract.resolve
    if isinstance(source, ByLiteral):
        return source.result_keys.get(entity, _NO_KEYS).get(rendered_key, rendered_key)
    return rendered_key


def _require_arity(contract: ResultContract, row: Row | Mapping[str, object]) -> None:
    if isinstance(row, tuple) and len(row) != len(contract.result_keys):
        raise _arity_error(len(contract.result_keys), len(row))


def _arity_error(arity: int, width: int) -> ValueError:
    return ValueError(f"result key count {arity} does not match row arity {width}")


def _value(contract: ResultContract, row: Row | Mapping[str, object], key: str) -> object:
    if isinstance(row, tuple):
        try:
            return row[contract.index_by_key[key]]
        except KeyError as error:
            raise KeyError(key) from error
    return row[key]


def _document_read(document_read: object) -> SqlNull | PresentDocument:
    if not isinstance(document_read, (SqlNull, PresentDocument)):
        raise _not_a_document_read(document_read)
    return document_read


def _not_a_document_read(value: object) -> SqlGenError:
    return SqlGenError(f"the database port returned {type(value).__name__}, not a DocumentRead")
