from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, cast

from parallax.core.internal.database_binding._authored import (
    DatabaseLocation,
    DatabaseSequence,
    DatabaseTable,
)
from parallax.core.internal.database_binding._errors import (
    BINDING_DEFINITION_REJECTED,
    BindingError,
    BindingIssue,
    BindingPath,
)
from parallax.core.internal.metamodel import EntityIdentity

__all__ = [
    "BINDING_BACKEND_MISMATCH",
    "BINDING_ENTITY_KEY_INVALID",
    "BINDING_FIELD_MISSING",
    "BINDING_FIELD_UNKNOWN",
    "BINDING_FORMAT_VERSION",
    "BINDING_IDENTIFIER_INVALID",
    "BINDING_NAMESPACE_KEY_INVALID",
    "BINDING_SEQUENCE_KEY_INVALID",
    "BINDING_SYNTAX_INVALID",
    "BINDING_VALUE_INVALID",
    "BINDING_VERSION_UNSUPPORTED",
    "BindingParts",
    "LocationCodec",
    "binding_document",
    "binding_from_document",
]

BINDING_FORMAT_VERSION: Final = 1
"""The one binding document format version this codec reads and writes."""

BINDING_SYNTAX_INVALID: Final = "binding-syntax-invalid"
"""The binding text is not well-formed in its declared format."""
BINDING_FIELD_UNKNOWN: Final = "binding-field-unknown"
"""A document object carries a key its section does not define."""
BINDING_FIELD_MISSING: Final = "binding-field-missing"
"""A required key is absent."""
BINDING_VALUE_INVALID: Final = "binding-value-invalid"
"""A value has the wrong shape, such as a string where an object belongs."""
BINDING_VERSION_UNSUPPORTED: Final = "binding-version-unsupported"
"""``format_version`` names a format this codec does not read."""
BINDING_BACKEND_MISMATCH: Final = "binding-backend-mismatch"
"""``backend`` names a backend other than the binding type's own."""
BINDING_ENTITY_KEY_INVALID: Final = "binding-entity-key-invalid"
"""An ``entities`` key is not an exact canonical Entity identity."""
BINDING_NAMESPACE_KEY_INVALID: Final = "binding-namespace-key-invalid"
"""A ``namespaces`` key is not an Entity Namespace."""
BINDING_SEQUENCE_KEY_INVALID: Final = "binding-sequence-key-invalid"
"""A ``sequences`` key is not a nonempty allocator key."""
BINDING_IDENTIFIER_INVALID: Final = "binding-identifier-invalid"
"""A physical identifier component is empty."""

# `identity.schema.json` `$defs/namespaceSegment` and the canonical spelling of
# `$defs/entityName`: a binding names owners exactly, never relative to a model.
_NAMESPACE: Final = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*")
_CANONICAL_ENTITY: Final = re.compile(
    r"(?:[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*\.)?[A-Z][A-Za-z0-9]*"
)

_TOP_LEVEL_KEYS: Final = frozenset(
    {"format_version", "backend", "default", "namespaces", "entities", "sequences"}
)
_TABLE_NAME_KEY: Final = "table"
_SEQUENCE_NAME_KEY: Final = "sequence"


@dataclass(frozen=True, slots=True, kw_only=True)
class LocationCodec[L: DatabaseLocation, T: DatabaseTable, S: DatabaseSequence]:
    """One backend's typed binding values and the document keys of its location.

    ``keys`` are the keys a location object carries; a table or sequence entry
    carries all of them or none beside its ``table`` or ``sequence`` key. The
    callables only build or read values: every validation is the codec's.
    """

    backend: str
    keys: tuple[str, ...]
    location_type: type[L]
    table_type: type[T]
    sequence_type: type[S]
    load: Callable[[Mapping[str, str]], L]
    dump: Callable[[L], Mapping[str, object]]
    table: Callable[[L | None, str | None], T]
    sequence: Callable[[L | None, str | None], S]


@dataclass(frozen=True, slots=True)
class BindingParts[L, T, S]:
    """A binding's normalized parts: frozen, canonically ordered maps."""

    default: L | None
    namespaces: Mapping[str, L]
    entities: Mapping[EntityIdentity, T]
    sequences: Mapping[str, S]


class _Unrepresentable:
    """Stands in for a typed argument of the wrong type, which no document position accepts."""

    __slots__ = ()


_UNREPRESENTABLE: Final = _Unrepresentable()


def binding_document[L: DatabaseLocation, T: DatabaseTable, S: DatabaseSequence](
    codec: LocationCodec[L, T, S],
    *,
    default: object = None,
    namespaces: object = None,
    entities: object = None,
    sequences: object = None,
) -> dict[str, object]:
    """The document that typed binding parts spell, without judging them.

    Serializing a canonical binding and normalizing a typed construction both
    project through here, so a typed value the codec refuses is reported at the
    path its document spelling would carry. Empty sections are omitted.
    """
    document: dict[str, object] = {"format_version": BINDING_FORMAT_VERSION}
    document["backend"] = codec.backend
    if default is not None:
        document["default"] = _location_fields(codec, default)
    sections: tuple[tuple[str, object, str | None], ...] = (
        ("namespaces", namespaces, None),
        ("entities", entities, _TABLE_NAME_KEY),
        ("sequences", sequences, _SEQUENCE_NAME_KEY),
    )
    for key, section, name_key in sections:
        if section is None:
            continue
        if not isinstance(section, Mapping):
            document[key] = _UNREPRESENTABLE
            continue
        entries = cast("Mapping[object, object]", section)
        if entries:
            document[key] = {
                _document_key(entry_key): (
                    _location_fields(codec, value)
                    if name_key is None
                    else _entry_fields(codec, value, name_key)
                )
                for entry_key, value in entries.items()
            }
    return document


def _document_key(key: object) -> object:
    return key.canonical if isinstance(key, EntityIdentity) else key


def _location_fields(codec: LocationCodec[Any, Any, Any], value: object) -> object:
    if not isinstance(value, codec.location_type):
        return _UNREPRESENTABLE
    return dict(codec.dump(value))


def _entry_fields(codec: LocationCodec[Any, Any, Any], value: object, name_key: str) -> object:
    entry_type: type[DatabaseTable | DatabaseSequence] = (
        codec.table_type if name_key == _TABLE_NAME_KEY else codec.sequence_type
    )
    if not isinstance(value, entry_type):
        return _UNREPRESENTABLE
    fields: dict[str, object] = {}
    location = value.location
    if location is not None:
        fields.update(codec.dump(location))
    if value.name is not None:
        fields[name_key] = value.name
    return fields


def binding_from_document[L: DatabaseLocation, T: DatabaseTable, S: DatabaseSequence](
    document: object, codec: LocationCodec[L, T, S]
) -> BindingParts[L, T, S]:
    """Normalize ``document`` for ``codec``'s backend, or raise :class:`BindingError`.

    Every definition problem in the document is reported together, except that
    an unreadable ``format_version`` or a foreign ``backend`` stops judging the
    sections whose shape they decide.
    """
    reader = _Reader(codec)
    parts = reader.parts(document)
    if reader.issues or parts is None:
        raise BindingError(BINDING_DEFINITION_REJECTED, reader.issues)
    return parts


class _Reader[L: DatabaseLocation, T: DatabaseTable, S: DatabaseSequence]:
    __slots__ = ("codec", "issues")

    def __init__(self, codec: LocationCodec[L, T, S]) -> None:
        self.codec = codec
        self.issues: list[BindingIssue] = []

    def _issue(self, code: str, path: BindingPath, message: str) -> None:
        self.issues.append(BindingIssue(code, path, message=message))

    def parts(self, document: object) -> BindingParts[L, T, S] | None:
        if not isinstance(document, Mapping):
            self._issue(BINDING_VALUE_INVALID, (), "a binding document is an object")
            return None
        fields = cast("Mapping[object, object]", document)
        for key in fields:
            if key not in _TOP_LEVEL_KEYS:
                self._issue(BINDING_FIELD_UNKNOWN, (_segment(key),), "not a binding section")
        if not self._envelope(fields):
            return None
        default = self._optional_location(fields, "default")
        namespaces = self._section(fields, "namespaces", self._namespace_key, self._location)
        entities = self._section(fields, "entities", self._entity_key, self._table)
        sequences = self._section(fields, "sequences", self._sequence_key, self._sequence)
        return BindingParts(
            default,
            _frozen(namespaces, key=lambda name: name),
            _frozen(entities, key=lambda identity: identity.sort_key),
            _frozen(sequences, key=lambda name: name),
        )

    def _envelope(self, fields: Mapping[object, object]) -> bool:
        readable = True
        if "format_version" not in fields:
            self._issue(
                BINDING_FIELD_MISSING, ("format_version",), "the format version is required"
            )
            readable = False
        else:
            version = fields["format_version"]
            if type(version) is not int or version != BINDING_FORMAT_VERSION:
                self._issue(
                    BINDING_VERSION_UNSUPPORTED,
                    ("format_version",),
                    f"only format version {BINDING_FORMAT_VERSION} is read, got {version!r}",
                )
                readable = False
        if "backend" not in fields:
            self._issue(BINDING_FIELD_MISSING, ("backend",), "the backend is required")
            readable = False
        elif fields["backend"] != self.codec.backend:
            self._issue(
                BINDING_BACKEND_MISMATCH,
                ("backend",),
                f"this binding reads {self.codec.backend!r}, got {fields['backend']!r}",
            )
            readable = False
        return readable

    def _optional_location(self, fields: Mapping[object, object], key: str) -> L | None:
        if key not in fields:
            return None
        return self._location(fields[key], (key,))

    def _section[K, V](
        self,
        fields: Mapping[object, object],
        key: str,
        read_key: Callable[[object, BindingPath], K | None],
        read_value: Callable[[object, BindingPath], V | None],
    ) -> dict[K, V]:
        if key not in fields:
            return {}
        section = fields[key]
        if not isinstance(section, Mapping):
            self._issue(BINDING_VALUE_INVALID, (key,), "a binding section is an object")
            return {}
        entries: dict[K, V] = {}
        for raw_key, raw_value in cast("Mapping[object, object]", section).items():
            path = (key, _segment(raw_key))
            parsed_key = read_key(raw_key, path)
            value = read_value(raw_value, path)
            if parsed_key is not None and value is not None:
                entries[parsed_key] = value
        return entries

    def _namespace_key(self, key: object, path: BindingPath) -> str | None:
        if isinstance(key, str) and _NAMESPACE.fullmatch(key):
            return key
        self._issue(BINDING_NAMESPACE_KEY_INVALID, path, "not an Entity Namespace")
        return None

    def _entity_key(self, key: object, path: BindingPath) -> EntityIdentity | None:
        if isinstance(key, str) and _CANONICAL_ENTITY.fullmatch(key):
            namespace, _, name = key.rpartition(".")
            return EntityIdentity(namespace or None, name)
        self._issue(BINDING_ENTITY_KEY_INVALID, path, "not an exact canonical Entity identity")
        return None

    def _sequence_key(self, key: object, path: BindingPath) -> str | None:
        if isinstance(key, str) and key:
            return key
        self._issue(BINDING_SEQUENCE_KEY_INVALID, path, "not a nonempty allocator key")
        return None

    def _object(self, value: object, path: BindingPath) -> Mapping[object, object] | None:
        if isinstance(value, Mapping):
            return cast("Mapping[object, object]", value)
        self._issue(BINDING_VALUE_INVALID, path, "expected an object")
        return None

    def _identifier(self, value: object, path: BindingPath) -> str | None:
        if not isinstance(value, str):
            self._issue(BINDING_VALUE_INVALID, path, "an identifier is a string")
            return None
        if not value:
            self._issue(BINDING_IDENTIFIER_INVALID, path, "an identifier is nonempty")
            return None
        return value

    def _unknown_fields(
        self, fields: Mapping[object, object], allowed: tuple[str, ...], path: BindingPath
    ) -> None:
        for key in fields:
            if key not in allowed:
                self._issue(BINDING_FIELD_UNKNOWN, (*path, _segment(key)), "not a field here")

    def _location_components(
        self, fields: Mapping[object, object], path: BindingPath
    ) -> dict[str, str] | None:
        components: dict[str, str] = {}
        complete = True
        for key in self.codec.keys:
            if key not in fields:
                self._issue(BINDING_FIELD_MISSING, (*path, key), "a location names every component")
                complete = False
                continue
            component = self._identifier(fields[key], (*path, key))
            if component is None:
                complete = False
            else:
                components[key] = component
        return components if complete else None

    def _location(self, value: object, path: BindingPath) -> L | None:
        fields = self._object(value, path)
        if fields is None:
            return None
        self._unknown_fields(fields, self.codec.keys, path)
        components = self._location_components(fields, path)
        return None if components is None else self.codec.load(components)

    def _entry(
        self, value: object, path: BindingPath, name_key: str
    ) -> tuple[L | None, str | None] | None:
        fields = self._object(value, path)
        if fields is None:
            return None
        self._unknown_fields(fields, (*self.codec.keys, name_key), path)
        valid = True
        location: L | None = None
        if any(key in fields for key in self.codec.keys):
            components = self._location_components(fields, path)
            if components is None:
                valid = False
            else:
                location = self.codec.load(components)
        name: str | None = None
        if name_key in fields:
            name = self._identifier(fields[name_key], (*path, name_key))
            valid = valid and name is not None
        return (location, name) if valid else None

    def _table(self, value: object, path: BindingPath) -> T | None:
        entry = self._entry(value, path, _TABLE_NAME_KEY)
        return None if entry is None else self.codec.table(*entry)

    def _sequence(self, value: object, path: BindingPath) -> S | None:
        entry = self._entry(value, path, _SEQUENCE_NAME_KEY)
        return None if entry is None else self.codec.sequence(*entry)


def _segment(key: object) -> str:
    return key if isinstance(key, str) else repr(key)


def _frozen[K, V](
    entries: dict[K, V], *, key: Callable[[K], str | tuple[str, str]]
) -> Mapping[K, V]:
    return MappingProxyType({entry: entries[entry] for entry in sorted(entries, key=key)})
