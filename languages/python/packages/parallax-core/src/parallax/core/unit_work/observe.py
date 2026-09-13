"""The closed Write Observation algebra (m-unit-work).

A Write Observation is the database evidence a surviving write against existing
state retains. Absence is **structural**: an insert and an unversioned
Non-Temporal write carry no observation value at all, rather than a null one, so
there is no ``NoObservation``, no nullable observation flowing downstream, and no
representable "a version *and* a predecessor" or "neither" state. A required
observation that is missing is a planning error, raised while the step is being
settled, in **both** concurrency modes.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from parallax.core.metamodel import (
    AttributeMetadata,
    NestedValueObjectMetadata,
    ValueObjectMetadata,
)

__all__ = [
    "EntityStateRow",
    "PredecessorRow",
    "TemporalObservation",
    "VersionObservation",
    "WriteObservation",
]


type _Occurrence = ValueObjectMetadata | NestedValueObjectMetadata


class _Layout(Protocol):
    @property
    def attributes(self) -> tuple[AttributeMetadata, ...]: ...

    @property
    def occurrences(self) -> tuple[ValueObjectMetadata, ...]: ...


class _State(Protocol):
    @property
    def member_row(self) -> tuple[object, ...]: ...


class EntityStateRow(Mapping[str, object]):
    """A read-only view of one already-decoded Entity State.

    The view retains either its source mapping or one positional member row by
    reference. It exists so observation and publication can share one state
    without rebuilding or detaching every member into another row-sized
    dictionary. Nested Value Objects are exposed through mapping views over the
    same positional state.
    """

    __slots__ = ("_absent", "_declared", "_keys", "_members", "_values")

    _declared: tuple[_Occurrence | None, ...]
    _members: Mapping[str, object] | None

    def __init__(self, members: Mapping[str, object]) -> None:
        self._members = members
        self._keys: tuple[str, ...] = ()
        self._values: tuple[object, ...] = ()
        self._declared = ()
        self._absent: object | None = None

    @classmethod
    def over_state(cls, layout: _Layout, state: _State, *, absent: object) -> EntityStateRow:
        return cls.over_members(layout, state.member_row, absent=absent)

    @classmethod
    def over_members(
        cls, layout: _Layout, values: tuple[object, ...], *, absent: object
    ) -> EntityStateRow:
        """View one positional member row through its physical storage keys."""
        attributes = layout.attributes
        occurrences = layout.occurrences
        keys = tuple(member.storage.name for member in (*attributes, *occurrences))
        if len(keys) != len(values):
            raise ValueError("an Entity State row layout must align with its member state")
        row = object.__new__(cls)
        row._members = None
        row._keys = keys
        row._values = values
        row._declared = (*((None,) * len(attributes)), *occurrences)
        row._absent = absent
        return row

    def __getitem__(self, key: str) -> object:
        if self._members is not None:
            return self._members[key]
        try:
            position = self._keys.index(key)
        except ValueError:
            raise KeyError(key) from None
        value = self._values[position]
        declared = self._declared[position]
        return value if declared is None else _occurrence_value(value, declared, self._absent)

    def __iter__(self) -> Iterator[str]:
        if self._members is not None:
            return iter(self._members)
        return (
            key
            for key, value in zip(self._keys, self._values, strict=True)
            if value is not self._absent
        )

    def __len__(self) -> int:
        return sum(1 for _key in self)


class _EntityDocumentRow(Mapping[str, object]):
    """A mapping view over one positional Value Object member row."""

    __slots__ = ("_absent", "_declared", "_keys", "_values")

    _declared: tuple[_Occurrence | None, ...]
    _keys: tuple[str, ...]

    def __init__(
        self, values: tuple[object, ...], declared: _Occurrence, absent: object | None
    ) -> None:
        attributes = declared.attributes
        occurrences = declared.value_objects
        self._values = values
        self._declared = (
            *((None,) * len(attributes)),
            *occurrences,
        )
        self._keys = (
            *(member.identity.name for member in attributes),
            *(member.identity.path[-1] for member in occurrences),
        )
        self._absent = absent

    def __getitem__(self, key: str) -> object:
        try:
            position = self._keys.index(key)
        except ValueError:
            raise KeyError(key) from None
        value = self._values[position]
        if value is self._absent:
            raise KeyError(key)
        declared = self._declared[position]
        return value if declared is None else _occurrence_value(value, declared, self._absent)

    def __iter__(self) -> Iterator[str]:
        return (
            key
            for key, value in zip(self._keys, self._values, strict=True)
            if value is not self._absent
        )

    def __len__(self) -> int:
        return sum(1 for _key in self)


def _occurrence_value(value: object, declared: _Occurrence, absent: object | None) -> object:
    if value is None or value is absent:
        return value
    if declared.multiplicity.name == "MANY":
        if not isinstance(value, tuple):  # pragma: no cover - accepted Page state is positional
            raise TypeError("a Many Value Object Entity State is positional")
        rows = cast("tuple[object, ...]", value)
        if any(  # pragma: no cover - accepted Page state is positional
            not isinstance(item, tuple) for item in rows
        ):
            raise TypeError("a Many Value Object Entity State is positional")
        return tuple(
            _EntityDocumentRow(cast("tuple[object, ...]", item), declared, absent) for item in rows
        )
    if not isinstance(value, tuple):  # pragma: no cover - accepted Page state is positional
        raise TypeError("a Value Object Entity State is positional")
    return _EntityDocumentRow(cast("tuple[object, ...]", value), declared, absent)


@dataclass(frozen=True, slots=True)
class VersionObservation:
    """The optimistic-lock version a versioned Non-Temporal row was read at."""

    observed_version: int


@dataclass(frozen=True, slots=True)
class PredecessorRow:
    """The complete, immutable persisted state a Temporal Observation retains.

    ``members`` holds every applicable member of the observed row by its declared
    name — every scalar Attribute, every complete Value Object occurrence, the
    complete primary key, every temporal bound, and every audit value — and no
    generated-value expression. Completeness is required because temporal
    expansion carries members the authored mutation never mentioned, and because
    a later decorator must tell carried state from changed state without a second
    read.

    ``document`` is the raw Structured Column document the observing read
    returned, retained beside the member state and never as an entry in it, so a
    successor is built by patching what the row actually held rather than by
    re-encoding the members this model happens to declare. The value is the read's
    own, unchanged; what this row keeps of it is a private portable JSON copy
    through :func:`~parallax.core.base.detach_json_container`. It is **absent** —
    not empty — under `Columns`
    layout, where the row has no Structured Column, and absent likewise for an
    observation whose source read no row; the member map stays purely logical
    either way, so a consumer iterating members can never surface the document as
    a result field or an Entity member.
    """

    members: EntityStateRow | Mapping[str, object]
    document: object | None = None

    def __post_init__(self) -> None:
        members = self.members
        if not isinstance(members, EntityStateRow):
            object.__setattr__(self, "members", EntityStateRow(dict(members)))
        if not self.members:
            raise ValueError("a Predecessor Row carries the observed row's complete state")

    def member(self, name: str) -> object:
        """The observed value of one member, by its declared name."""
        return self.members[name]


@dataclass(frozen=True, slots=True)
class TemporalObservation:
    """The predecessor milestone a temporal close addresses, gates on, and
    carries state forward from.

    Transaction-Time-Only and Bitemporal entities have identical observation
    requirements; the accepted Temporal Facet, not a variant per temporal flavor,
    decides which topology applies.
    """

    predecessor: PredecessorRow


type WriteObservation = VersionObservation | TemporalObservation
"""The closed algebra of database evidence a write against existing state
retains."""
