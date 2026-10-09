from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast, runtime_checkable

from parallax.core.base import adopt_frozen_map, retain_document_value
from parallax.core.metamodel import (
    AuthoringViolation,
    Leaf,
    MemberShape,
    Multiplicity,
    Occurrence,
)

__all__ = [
    "BORROWED_SOURCE_ACCESS",
    "MAPPING_SOURCE_ACCESS",
    "SourceAccess",
    "prepare_authoring",
    "prepare_member_authoring",
    "validate_member_authoring",
]


type LeafNormalizer = Callable[[Leaf, object, str], tuple[object, bool]]
"""Normalize one scalar value of ``leaf.type`` at ``path``, answering the managed
value and whether it is valid. A ``many`` leaf's normalizer is called once per
element with that same leaf, so it never reads the leaf's multiplicity."""


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
_NO_FAILURES: Mapping[int, AuthoringViolation] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class PreparedDocumentAuthoring:
    """One owned managed document and its sparse top-level authoring failures."""

    value: Mapping[str, object]
    failures: Mapping[int, AuthoringViolation]


@dataclass(frozen=True, slots=True)
class PreparedMemberAuthoring:
    """One prepared member value and its optional structural failure."""

    value: object
    failure: AuthoringViolation | None


def prepare_authoring(
    shape: MemberShape,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str = "",
    fill_missing_many: bool = True,
    allow_root_markers: bool = False,
) -> PreparedDocumentAuthoring:
    """Prepare one authored document directly into recursively immutable storage."""
    value, failures, _present, _nulls = _author_document(
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
    return PreparedDocumentAuthoring(value=value, failures=failures)


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
        managed, failure = _author_leaf(
            member,
            source,
            source_access=source_access,
            normalize_leaf=normalize_leaf,
            path=path,
            allow_marker=allow_marker,
            produce=True,
        )
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
) -> AuthoringViolation | None:
    """Validate one already-resolved member without constructing its output."""
    if isinstance(member, Leaf):
        if member.multiplicity is Multiplicity.MANY:
            _value, failure = _author_scalar_many(
                member,
                source,
                source_access=source_access,
                normalize_leaf=normalize_leaf,
                path=path,
                produce=False,
            )
            return failure
        if source is None:
            return None
        if allow_marker and _is_marker(source):
            return None
        managed, valid = normalize_leaf(member, source, path)
        if valid:
            return None
        return AuthoringViolation("", "type-mismatch", managed, member.type)
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
) -> tuple[Mapping[str, object] | None, Mapping[int, AuthoringViolation], int, int]:
    """The authored document, its per-position failures, and two position bit
    masks: the members the source names, and those of them it holds as null."""
    names = source_names if source_names is not None else source_access.names(source)
    if names is None:
        raise TypeError("an authored document source must expose named members")

    values: dict[str, object] | None = {} if produce else None
    failures: dict[int, AuthoringViolation] | None = None
    present = 0
    nulls = 0
    for name in names:
        position = shape.position(name)
        if position is None:
            continue
        present |= 1 << position
        member = shape.members[position]
        raw = source_access.member(source, name)
        if raw is None:
            nulls |= 1 << position
        member_path = _joined(path, name)
        if isinstance(member, Leaf):
            managed, violation = _author_leaf(
                member,
                raw,
                source_access=source_access,
                normalize_leaf=normalize_leaf,
                path=member_path,
                allow_marker=allow_markers,
                produce=produce,
            )
        else:
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
        values.update(
            {
                member.name: ()
                for position, member in enumerate(shape.members)
                if not present & (1 << position) and _is_many(member)
            }
        )

    prepared = None if values is None else adopt_frozen_map(values)
    reported = _NO_FAILURES if failures is None else MappingProxyType(failures)
    return prepared, reported, present, nulls


def _author_leaf(
    leaf: Leaf,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    allow_marker: bool,
    produce: bool,
) -> tuple[object, AuthoringViolation | None]:
    if leaf.multiplicity is Multiplicity.MANY:
        return _author_scalar_many(
            leaf,
            source,
            source_access=source_access,
            normalize_leaf=normalize_leaf,
            path=path,
            produce=produce,
        )
    if source is None:
        return None, None
    if allow_marker and _is_marker(source):
        return retain_document_value(source), None
    managed, valid = normalize_leaf(leaf, source, path)
    if valid:
        return managed, None
    return managed, AuthoringViolation("", "type-mismatch", managed, leaf.type)


def _author_scalar_many(
    leaf: Leaf,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    produce: bool,
) -> tuple[object, AuthoringViolation | None]:
    """One scalar collection: its ordered managed tuple when ``produce``, and its
    first violation. Validation alone retains no element and builds no tuple.

    A null collection is left to the caller's nullability judgement, exactly as
    a null scalar is; a null element is a type mismatch, because elements are
    never nullable."""
    if source is None:
        return None, None
    elements = source_access.elements(source)
    if elements is None:
        retained = retain_document_value(source) if produce else source
        return retained, AuthoringViolation("", "not-a-list", source)
    prepared: list[object] | None = [] if produce else None
    first: AuthoringViolation | None = None
    for index, element in enumerate(elements):
        if element is None:
            managed: object = None
            valid = False
        else:
            managed, valid = normalize_leaf(leaf, element, f"{path}[{index}]")
        if prepared is not None:
            prepared.append(managed)
        if first is None and not valid:
            first = AuthoringViolation(f"[{index}]", "type-mismatch", managed, leaf.type)
    return (() if prepared is None else tuple(prepared)), first


def _author_occurrence(
    occurrence: Occurrence,
    source: object,
    *,
    source_access: SourceAccess,
    normalize_leaf: LeafNormalizer,
    path: str,
    produce: bool,
) -> tuple[object, AuthoringViolation | None]:
    if source is None:
        return None, None
    if occurrence.multiplicity is Multiplicity.MANY:
        elements = source_access.elements(source)
        if elements is None:
            retained = retain_document_value(source) if produce else source
            return retained, AuthoringViolation("", "not-a-list", source)
        prepared: list[object] | None = [] if produce else None
        first: AuthoringViolation | None = None
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
) -> tuple[object, AuthoringViolation | None]:
    names = source_access.names(source)
    if names is None:
        retained = retain_document_value(source) if produce else source
        return retained, AuthoringViolation("", "not-a-document", source)
    value, failures, present, nulls = _author_document(
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
    violation = _first_document_violation(shape, failures, present, nulls)
    return (source if value is None else value), violation


def _first_document_violation(
    shape: MemberShape,
    failures: Mapping[int, AuthoringViolation],
    present: int,
    nulls: int,
) -> AuthoringViolation | None:
    """The first violation in canonical member order: a required member the
    document omits or holds as null, or a held member's own failure.

    An omitted ``many`` occurrence is its empty collection, so it is never missing.
    """
    for position, member in enumerate(shape.members):
        bit = 1 << position
        if present & bit and not nulls & bit:
            failure = failures.get(position)
            if failure is not None:
                return _prefixed(member.name, failure)
        elif not member.nullable and (present & bit or not _is_many(member)):
            reason = "attribute-missing" if isinstance(member, Leaf) else "value-object-missing"
            return AuthoringViolation(member.name, reason)
    return None


def _prefixed(prefix: str, violation: AuthoringViolation) -> AuthoringViolation:
    if not violation.path:
        path = prefix
    elif violation.path.startswith("["):
        path = f"{prefix}{violation.path}"
    else:
        path = f"{prefix}.{violation.path}"
    return AuthoringViolation(path, violation.reason, violation.value, violation.declared_type)


def _joined(base: str, name: str) -> str:
    return name if not base else f"{base}.{name}"


def _is_many(member: Leaf | Occurrence) -> bool:
    return member.multiplicity is Multiplicity.MANY


def _is_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    keys = frozenset(cast("Mapping[object, object]", value))
    return keys in (frozenset({"computed"}), frozenset({"increment"}))
