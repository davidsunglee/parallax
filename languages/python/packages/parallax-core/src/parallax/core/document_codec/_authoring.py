from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast, runtime_checkable

from parallax.core.base import NeutralType, adopt_frozen_map, retain_document_value
from parallax.core.metamodel import (
    Leaf,
    MemberShape,
    Multiplicity,
    Occurrence,
    VoDocumentViolation,
)

__all__ = [
    "BORROWED_SOURCE_ACCESS",
    "MAPPING_SOURCE_ACCESS",
    "LeafNormalizer",
    "PreparedAuthoring",
    "PreparedMemberAuthoring",
    "SourceAccess",
    "prepare_authoring",
    "prepare_member_authoring",
    "validate_authoring",
    "validate_member_authoring",
]


type LeafNormalizer = Callable[[NeutralType, object, str], tuple[object, bool]]


class SourceAccess(Protocol):
    """Read document names, named members, and collection elements from a source."""

    def names(self, source: object, /) -> Iterable[str] | None: ...

    def member(self, source: object, name: str, /) -> object: ...

    def elements(self, source: object, /) -> Iterable[object] | None: ...


@runtime_checkable
class _BorrowedDocument(Protocol):
    def __parallax_authoring_names__(self) -> Iterable[str]: ...

    def __parallax_authoring_member__(self, name: str, /) -> object: ...


@dataclass(frozen=True, slots=True)
class _MappingSourceAccess:
    def names(self, source: object, /) -> Iterable[str] | None:
        if not isinstance(source, Mapping):
            return None
        return cast("Mapping[str, object]", source).keys()

    def member(self, source: object, name: str, /) -> object:
        return cast("Mapping[str, object]", source)[name]

    def elements(self, source: object, /) -> Iterable[object] | None:
        if not isinstance(source, Sequence) or isinstance(
            source, str | bytes | bytearray | memoryview
        ):
            return None
        return cast("Sequence[object]", source)


@dataclass(frozen=True, slots=True)
class _BorrowedSourceAccess:
    def names(self, source: object, /) -> Iterable[str] | None:
        if isinstance(source, _BorrowedDocument):
            return source.__parallax_authoring_names__()
        return MAPPING_SOURCE_ACCESS.names(source)

    def member(self, source: object, name: str, /) -> object:
        if isinstance(source, _BorrowedDocument):
            return source.__parallax_authoring_member__(name)
        return MAPPING_SOURCE_ACCESS.member(source, name)

    def elements(self, source: object, /) -> Iterable[object] | None:
        return MAPPING_SOURCE_ACCESS.elements(source)


MAPPING_SOURCE_ACCESS: SourceAccess = _MappingSourceAccess()
BORROWED_SOURCE_ACCESS: SourceAccess = _BorrowedSourceAccess()
_NO_FAILURES: Mapping[int, VoDocumentViolation] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class PreparedAuthoring:
    """One owned managed document and its sparse top-level authoring failures."""

    value: Mapping[str, object]
    failures: Mapping[int, VoDocumentViolation]


@dataclass(frozen=True, slots=True)
class PreparedMemberAuthoring:
    """One prepared member value and its optional structural failure."""

    value: object
    failure: VoDocumentViolation | None


def prepare_authoring(
    shape: MemberShape,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str = "",
    fill_missing_many: bool = True,
    allow_root_markers: bool = False,
) -> PreparedAuthoring:
    """Prepare one authored document directly into recursively immutable storage."""
    value, failures, _present = _author_document(
        shape,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=True,
        fill_missing_many=fill_missing_many,
        allow_markers=allow_root_markers,
    )
    assert value is not None
    return PreparedAuthoring(value=value, failures=failures)


def validate_authoring(
    shape: MemberShape,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str = "",
    allow_root_markers: bool = False,
) -> Mapping[int, VoDocumentViolation]:
    """Validate one authored document without constructing managed occurrence output."""
    _value, failures, _present = _author_document(
        shape,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=False,
        fill_missing_many=False,
        allow_markers=allow_root_markers,
    )
    return failures


def prepare_member_authoring(
    member: Leaf | Occurrence,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str = "",
    allow_marker: bool = False,
) -> PreparedMemberAuthoring:
    """Prepare one already-resolved authored member without a wrapper document."""
    if isinstance(member, Leaf):
        if source is None:
            return PreparedMemberAuthoring(None, None)
        if allow_marker and _is_marker(source):
            return PreparedMemberAuthoring(retain_document_value(source), None)
        managed, valid = normalize_leaf(member.type, source, path)
        failure = None
        if not valid:
            failure = VoDocumentViolation("", "type-mismatch", managed, member.type)
        return PreparedMemberAuthoring(managed, failure)
    value, failure = _author_occurrence(
        member,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=True,
    )
    return PreparedMemberAuthoring(value, failure)


def validate_member_authoring(
    member: Leaf | Occurrence,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str = "",
    allow_marker: bool = False,
) -> VoDocumentViolation | None:
    """Validate one already-resolved member without constructing occurrence output."""
    if isinstance(member, Leaf):
        if source is None:
            return None
        if allow_marker and _is_marker(source):
            return None
        managed, valid = normalize_leaf(member.type, source, path)
        if valid:
            return None
        return VoDocumentViolation("", "type-mismatch", managed, member.type)
    _value, failure = _author_occurrence(
        member,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=False,
    )
    return failure


def _author_document(
    shape: MemberShape,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    produce: bool,
    fill_missing_many: bool,
    source_names: Iterable[str] | None = None,
    allow_markers: bool = False,
) -> tuple[Mapping[str, object] | None, Mapping[int, VoDocumentViolation], int]:
    names = source_names if source_names is not None else source_access.names(source)
    if names is None:
        raise TypeError("an authored document source must expose named members")

    values: dict[str, object] | None = {} if produce else None
    failures: dict[int, VoDocumentViolation] | None = None
    present = 0
    for name in names:
        position = shape.position(name)
        if position is None:
            continue
        present |= 1 << position
        member = shape.members[position]
        raw = source_access.member(source, name)
        member_path = _joined(path, name)
        if isinstance(member, Leaf):
            if raw is None:
                managed = None
                valid = True
            elif allow_markers and _is_marker(raw):
                managed = retain_document_value(raw)
                valid = True
            else:
                managed, valid = normalize_leaf(member.type, raw, member_path)
            if values is not None:
                values[name] = managed
            if not valid:
                if failures is None:
                    failures = {}
                failures[position] = VoDocumentViolation("", "type-mismatch", managed, member.type)
            continue

        managed, violation = _author_occurrence(
            member,
            raw,
            source_access=source_access,
            normalize_leaf=normalize_leaf,
            path=member_path,
            produce=produce,
        )
        if values is not None:
            values[name] = managed
        if violation is not None:
            if failures is None:
                failures = {}
            failures[position] = violation

    if values is not None and fill_missing_many:
        for position, member in enumerate(shape.members):
            if not present & (1 << position) and _is_many(member):
                values[member.name] = ()

    prepared = None if values is None else adopt_frozen_map(values)
    return prepared, _NO_FAILURES if failures is None else MappingProxyType(failures), present


def _author_occurrence(
    occurrence: Occurrence,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    produce: bool,
) -> tuple[object, VoDocumentViolation | None]:
    if source is None:
        return None, None
    if occurrence.multiplicity is Multiplicity.MANY:
        elements = source_access.elements(source)
        if elements is None:
            retained = retain_document_value(source) if produce else source
            return retained, VoDocumentViolation("", "not-a-list", source)
        prepared: list[object] | None = [] if produce else None
        first: VoDocumentViolation | None = None
        for index, element in enumerate(elements):
            value, violation = _author_occurrence_document(
                occurrence.shape,
                element,
                source_access=source_access,
                normalize_leaf=normalize_leaf,
                path=f"{path}[{index}]",
                produce=produce,
            )
            if prepared is not None:
                prepared.append(value)
            if first is None and violation is not None:
                first = _prefixed(f"[{index}]", violation)
        return (() if prepared is None else tuple(prepared)), first
    return _author_occurrence_document(
        occurrence.shape,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=produce,
    )


def _author_occurrence_document(
    shape: MemberShape,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    produce: bool,
) -> tuple[object, VoDocumentViolation | None]:
    names = source_access.names(source)
    if names is None:
        retained = retain_document_value(source) if produce else source
        return retained, VoDocumentViolation("", "not-a-document", source)
    value, failures, present = _author_document(
        shape,
        source,
        source_access=source_access,
        normalize_leaf=normalize_leaf,
        path=path,
        produce=produce,
        fill_missing_many=True,
        source_names=names,
        allow_markers=False,
    )
    violation = _first_document_violation(shape, source, source_access, failures, present)
    return (source if value is None else value), violation


def _first_document_violation(
    shape: MemberShape,
    source: object,
    source_access: SourceAccess,
    failures: Mapping[int, VoDocumentViolation],
    present: int,
) -> VoDocumentViolation | None:
    for position, member in enumerate(shape.members):
        if not present & (1 << position):
            if isinstance(member, Leaf) and not member.nullable:
                return VoDocumentViolation(member.name, "attribute-missing")
            if isinstance(member, Occurrence):
                if member.multiplicity is Multiplicity.MANY:
                    continue
                if not member.nullable:
                    return VoDocumentViolation(member.name, "value-object-missing")
            continue
        value = source_access.member(source, member.name)
        if value is None:
            if isinstance(member, Leaf) and not member.nullable:
                return VoDocumentViolation(member.name, "attribute-missing")
            if isinstance(member, Occurrence) and not member.nullable:
                return VoDocumentViolation(member.name, "value-object-missing")
            continue
        failure = failures.get(position)
        if failure is not None:
            return _prefixed(member.name, failure)
    return None


def _prefixed(prefix: str, violation: VoDocumentViolation) -> VoDocumentViolation:
    if not violation.path:
        path = prefix
    elif violation.path.startswith("["):
        path = f"{prefix}{violation.path}"
    else:
        path = f"{prefix}.{violation.path}"
    return VoDocumentViolation(path, violation.reason, violation.value, violation.declared_type)


def _joined(base: str, name: str) -> str:
    return name if not base else f"{base}.{name}"


def _is_many(member: Leaf | Occurrence) -> bool:
    return isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY


def _is_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    keys = frozenset(cast("Mapping[object, object]", value))
    return keys in (frozenset({"computed"}), frozenset({"increment"}))
