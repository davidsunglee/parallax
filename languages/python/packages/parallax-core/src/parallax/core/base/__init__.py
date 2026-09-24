from __future__ import annotations

import datetime as dt
import enum
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Self, TypeGuard, cast, overload

from parallax.core.base._inference import infer_neutral_type
from parallax.core.base._neutral import (
    BOOLEAN,
    BYTES,
    DATE,
    FLOAT32,
    FLOAT64,
    INT32,
    INT64,
    JSON,
    STRING,
    TIME,
    TIMESTAMP,
    UUID,
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    ManagedValue,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
    coerce_neutral_input,
    matches_neutral_type,
    nearest_float_at_width,
    utc_instant,
)

__all__ = [
    "BOOLEAN",
    "BYTES",
    "DATE",
    "FLOAT32",
    "FLOAT64",
    "INFINITY",
    "INFINITY_LITERAL",
    "INT32",
    "INT64",
    "JSON",
    "SQL_NULL",
    "STRING",
    "TIME",
    "TIMESTAMP",
    "UUID",
    "Boolean",
    "Bytes",
    "Date",
    "Decimal",
    "DocumentRead",
    "DocumentReadOrdinals",
    "DocumentValue",
    "Float32",
    "Float64",
    "FrozenMap",
    "InstantError",
    "Int32",
    "Int64",
    "Json",
    "ManagedValue",
    "NeutralType",
    "PresentDocument",
    "SqlNull",
    "String",
    "TemporalBound",
    "Time",
    "Timestamp",
    "UnknownFamilyTag",
    "Uuid",
    "admits_stored_scalar",
    "adopt_frozen_map",
    "coerce_neutral_input",
    "detach_json_container",
    "frozen_map_json_backing",
    "inert_scalar",
    "infer_neutral_type",
    "is_document_value",
    "matches_neutral_type",
    "nearest_float_at_width",
    "normalize_instant",
    "retain_document_value",
    "unwrap_document_read",
]


class FrozenMap[K, V](Mapping[K, V]):
    """An immutable mapping whose recursively retained values are safe to share.

    Public construction owns a copy of the supplied mapping and recursively
    retains nested mappings and sequences. Trusted core producers use the
    module-private adoption seam after constructing final safe storage.
    """

    __slots__ = ("__values",)
    __values: dict[K, V]

    def __init__(self, source: Mapping[K, V]) -> None:
        values = {key: cast("V", retain_document_value(value)) for key, value in source.items()}
        object.__setattr__(self, "_FrozenMap__values", values)

    def __getitem__(self, key: K) -> V:
        return self.__values[key]

    # The Mapping mixin swallows a KeyError raised by the probe key's own
    # __hash__ or __eq__; the guards keep that contract at no cost on the
    # non-raising path.
    def __contains__(self, key: object, /) -> bool:
        try:
            return key in self.__values
        except KeyError:
            return False

    @overload
    def get(self, key: K, /) -> V | None: ...
    @overload
    def get(self, key: K, default: V, /) -> V: ...
    @overload
    def get[D](self, key: K, default: D, /) -> V | D: ...
    def get(self, key: K, default: object = None, /) -> object:
        try:
            return self.__values.get(key, default)
        except KeyError:
            return default

    def __iter__(self) -> Iterator[K]:
        return iter(self.__values)

    def __len__(self) -> int:
        return len(self.__values)

    def __repr__(self) -> str:
        return f"FrozenMap({self.__values!r})"

    def __eq__(self, other: object) -> bool:
        return _document_values_equal(self, other)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise TypeError("a FrozenMap is immutable")

    def __delattr__(self, _name: str) -> None:
        raise TypeError("a FrozenMap is immutable")

    def __init_subclass__(cls) -> None:
        raise TypeError("FrozenMap does not support subclassing")


def adopt_frozen_map[K, V](values: dict[K, V]) -> FrozenMap[K, V]:
    adopted = cast("FrozenMap[K, V]", object.__new__(FrozenMap))
    object.__setattr__(adopted, "_FrozenMap__values", values)
    return adopted


def frozen_map_json_backing[K, V](value: FrozenMap[K, V]) -> dict[K, V]:
    """Return exact carrier storage for the adapter's synchronous JSON encoder."""
    if type(value) is not FrozenMap:
        raise TypeError("only the core FrozenMap carrier exposes serializer backing")
    return cast("dict[K, V]", object.__getattribute__(value, "_FrozenMap__values"))


def _document_values_equal(left: object, right: object) -> bool:
    left_is_mapping = type(left) in (dict, FrozenMap)
    right_is_mapping = type(right) in (dict, FrozenMap)
    if left_is_mapping or right_is_mapping:
        if not left_is_mapping or not right_is_mapping:
            return False
        left_mapping = cast("Mapping[object, object]", left)
        right_mapping = cast("Mapping[object, object]", right)
        return len(left_mapping) == len(right_mapping) and all(
            key in right_mapping and _document_values_equal(value, right_mapping[key])
            for key, value in left_mapping.items()
        )
    left_is_sequence = type(left) in (list, tuple)
    right_is_sequence = type(right) in (list, tuple)
    if left_is_sequence or right_is_sequence:
        if not left_is_sequence or not right_is_sequence:
            return False
        left_sequence = cast("Sequence[object]", left)
        right_sequence = cast("Sequence[object]", right)
        return len(left_sequence) == len(right_sequence) and all(
            _document_values_equal(a, b) for a, b in zip(left_sequence, right_sequence, strict=True)
        )
    return left == right


def retain_document_value(value: object) -> object:
    """Recursively own document containers, reusing already-owned subtrees."""
    if type(value) is FrozenMap:
        return cast("FrozenMap[object, object]", value)
    if isinstance(value, Mapping):
        source = cast("Mapping[object, object]", value)
        return adopt_frozen_map(
            {key: retain_document_value(nested) for key, nested in source.items()}
        )
    if type(value) is tuple:
        source = cast("tuple[object, ...]", value)
        retained = tuple(retain_document_value(nested) for nested in source)
        return source if all(a is b for a, b in zip(retained, source, strict=True)) else retained
    if isinstance(value, tuple):
        source = cast("tuple[object, ...]", value)
        return tuple(retain_document_value(nested) for nested in source)
    if isinstance(value, list):
        return tuple(retain_document_value(nested) for nested in cast("list[object]", value))
    return value


type DocumentValue = (
    bool
    | int
    | float
    | str
    | list[DocumentValue]
    | dict[str, DocumentValue]
    | tuple[DocumentValue, ...]
    | FrozenMap[str, DocumentValue]
    | None
)
"""A portable JSON data-model value, including bare JSON null."""


class SqlNull:
    """A structured-document result whose SQL column is NULL.

    Sameness is identity: :data:`SQL_NULL` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[SqlNull | None] = None

    def __new__(cls) -> SqlNull:
        if SqlNull._instance is None:
            SqlNull._instance = super().__new__(cls)
        return SqlNull._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("SqlNull admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "SQL_NULL"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "SQL_NULL"


SQL_NULL: Final[SqlNull] = SqlNull()


@dataclass(frozen=True, slots=True)
class PresentDocument:
    """A non-SQL-null structured-document result, including JSON null."""

    document: DocumentValue


type DocumentRead = SqlNull | PresentDocument
"""The provider-neutral structured-document read transport."""

type DocumentReadOrdinals = tuple[int, int]
"""Adjacent zero-based ``(presence, document)`` projection ordinals."""


def unwrap_document_read(value: DocumentRead) -> DocumentValue | None:
    """Return a document carrier's payload, mapping SQL NULL to ``None``."""
    return None if isinstance(value, SqlNull) else value.document


def is_document_value(value: object) -> TypeGuard[DocumentValue]:
    """Whether ``value`` belongs to the portable JSON data model."""
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if type(value) in (list, tuple):
        return all(is_document_value(item) for item in cast("Sequence[object]", value))
    if type(value) in (dict, FrozenMap):
        return all(
            isinstance(key, str) and is_document_value(item)
            for key, item in cast("Mapping[object, object]", value).items()
        )
    return False


def detach_json_container(value: object) -> object:
    """Recursively copy JSON-shaped containers into plain ``dict`` and ``list`` values.

    Mapping and sequence implementations may be immutable views owned by another
    boundary. The returned tree shares no container with ``value``; scalar values
    pass through unchanged. Strings and bytes are scalars, not JSON arrays.
    """
    if isinstance(value, Mapping):
        return {
            key: detach_json_container(item)
            for key, item in cast("Mapping[str, object]", value).items()
        }
    if isinstance(value, (list, tuple)):
        return [detach_json_container(item) for item in cast("Sequence[object]", value)]
    return value


# The canonical literal for the open upper bound in golden SQL and table state.
INFINITY_LITERAL: Final[str] = "infinity"


class TemporalBound(enum.Enum):
    """The open upper bound of a temporal interval — the database's native
    infinity (m-core), distinct from every finite instant and from ``None``."""

    INFINITY = "infinity"


# The native-infinity sentinel for a temporal interval's open upper bound.
INFINITY: Final[TemporalBound] = TemporalBound.INFINITY


class InstantError(ValueError):
    """A ``timestamp`` value violates the m-core UTC / precision rules, or names
    no instant a UTC ``datetime`` holds."""


def inert_scalar(value: object) -> object:
    """``value`` in a form its reader cannot mutate.

    A byte-like carrier is copied, because a ``bytearray`` or a ``memoryview``
    hands its reader the buffer a provider still owns; every other scalar is
    already immutable and passes through as itself.
    """
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return value


@dataclass(frozen=True, slots=True)
class Admission:
    """One stored scalar's read-contract verdict, and what a rejection judged.

    ``rejected`` is the value a negative verdict was formed about — the evidence
    a diagnosis of it publishes — and is ``None`` for an admitted one. The
    decoding reason behind that value stays unpublished.
    """

    admitted: bool
    rejected: object = None


_ADMITTED: Final[Admission] = Admission(True)
"""The one positive verdict, so a conforming scalar allocates nothing."""


@dataclass(frozen=True, slots=True)
class UnknownFamilyTag:
    """A stored discriminator that resolved to no composed concrete subtype.

    Carried on a materialized row only where that is what happened, so its
    presence IS the verdict and ``stored_value`` is the evidence behind it. A
    flag beside a value would let the two disagree, and no resting value could
    stand for "the tag resolved": a stored ``NULL`` discriminator is itself an
    unknown tag a diagnosis publishes.
    """

    stored_value: object


def admits_stored_scalar(
    value: object,
    declared: NeutralType,
    *,
    nullable: bool,
    temporal_end: bool,
) -> Admission:
    """Whether one decoded stored scalar satisfies its logical read contract.

    SQL NULL is admitted only by a nullable Attribute, the native infinity
    sentinel only by a temporal end Attribute, and every other value must
    inhabit the Attribute's declared Neutral Type.
    """
    if value is None:
        admitted = nullable
    elif value is INFINITY:
        admitted = temporal_end
    else:
        admitted = matches_neutral_type(value, declared)
    return _ADMITTED if admitted else Admission(False, value)


def normalize_instant(value: dt.datetime) -> dt.datetime:
    """Normalize a ``timestamp`` to the m-core boundary form: UTC, microsecond.

    A naive datetime carries no offset and is rejected; an aware value is
    converted to UTC. ``datetime`` already
    caps precision at the microsecond, so no sub-microsecond truncation is
    possible for a ``datetime`` input.

    Total over every :class:`datetime.datetime`, which is what makes this a
    boundary rather than a step on the way to one. A value the ``timestamp``
    space has no member for earns the same verdict every other unusable one
    does rather than escaping as whatever the conversion itself raises: an
    aware value at the representational edge — ``datetime.min`` east of UTC,
    ``datetime.max`` west of it — names an instant no UTC ``datetime`` holds,
    and a ``tzinfo`` answering no offset or one outside the day ``datetime``
    arithmetic admits places its value on no timeline at all.
    """
    instant = utc_instant(value)
    if instant is not None:
        return instant
    if value.tzinfo is None:
        raise InstantError("a naive datetime is not a valid `timestamp`; attach a tzinfo")
    raise InstantError(
        f"{value!r} is not a valid `timestamp`: no UTC datetime names its instant — an aware "
        "value at the representational edge, or a tzinfo answering no usable offset"
    )
