"""The in-band invalid-result surface a classified read publishes (m-snapshot-read).

A result element is ``T | InvalidData[T]``: a root whose whole requested include
tree conforms is delivered as itself, and a root some stored state contradicted
is delivered as the record here. Classification is root-granular — an issue
anywhere in a root's requested include tree makes that root invalid — so nothing
below a root is ever pruned or unioned.

The record carries diagnoses, positions, and the immutable evidence of what was
rejected — never authority: no decoding cause, no mutable details, and no
observation address. Its locators answer *which* result element is invalid, not
what a caller may then write, and the evidence it carries is reachable only by
explicit attribute access.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final, Self, cast

from parallax.core.metamodel import EntityIdentity, MemberIdentity
from parallax.core.temporal_read import Edge
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._graph import StoredDataIssueCode

__all__ = [
    "MISSING_STORED_VALUE",
    "InvalidData",
    "InvalidDataError",
    "MissingStoredValue",
    "StoredDataIssue",
]


class MissingStoredValue:
    """The evidence a traversable stored object held no member at all.

    Distinct from ``None``, which is the stored SQL or JSON null. Sameness is
    identity: :data:`MISSING_STORED_VALUE` is the one instance, and it stays that
    one instance through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING_STORED_VALUE"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "MISSING_STORED_VALUE"


MISSING_STORED_VALUE: Final[MissingStoredValue] = MissingStoredValue()


def _structural_hash(value: object) -> int:
    """``value``'s hash under the structural equality evidence compares by.

    A read-only mapping is unhashable and its equality is key-order
    insensitive, so the mapping arm hashes an unordered set of member hashes;
    every other frozen shape is already hashable, and the tuple arm exists only
    so a tuple holding a mapping stays reachable.
    """
    if isinstance(value, Mapping):
        return hash(
            frozenset(
                (key, _structural_hash(item))
                for key, item in cast("Mapping[object, object]", value).items()
            )
        )
    if isinstance(value, tuple):
        return hash(tuple(_structural_hash(item) for item in cast("tuple[object, ...]", value)))
    return hash(value)


@dataclass(frozen=True, slots=True)
class StoredDataIssue:
    """One stored state that contradicts the model, as the public diagnosis of it.

    ``entity`` is the concrete Entity the violation was judged against, which for
    an unresolved family tag is the queried family root — the only case with no
    ``member``, because a discriminator is no declared domain member.

    ``object_key`` names the affected root or included Entity and is absent
    exactly where no identity decoded: an invalid primary key, or a family tag
    naming no concrete subtype. It is deliberately unlike
    :attr:`InvalidData.object_key`, which always names the RESULT root: reaching
    one included Entity from several roots repeats this diagnosis in each root's
    record while identifying the same affected object.

    ``path`` is the entity-relative logical path of the rejected occurrence,
    keeping declared member names distinct from integer array positions. It is
    empty where the member identity already locates the occurrence exactly: a
    direct Entity Attribute under either Storage Layout, an unresolved family
    tag, and a whole stored document read in a kind it cannot be read as.

    ``stored_value`` is the provider-normalized logical value that was judged
    and rejected, immutable and detached from every provider carrier: arrays
    read as tuples, objects as read-only mappings, stored SQL or JSON null as
    ``None``, and a member genuinely absent from a traversable object as
    :data:`MISSING_STORED_VALUE`. It is diagnostic evidence and nothing else —
    reachable by explicit attribute access and in a debugger, kept out of the
    default repr, and granting no write, repair, observation, key, or storage
    authority.

    Both fields participate in equality, so repeated reach to one occurrence
    collapses in a frozenset while different paths or different evidence stay
    distinct. Structured evidence is unhashable and compares insensitively to
    object key order, so the hash is derived structurally from what the evidence
    holds, and cached because a frozenset asks for it once per membership test.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: MemberIdentity | None = None
    object_key: ObjectKey | None = None
    path: tuple[str | int, ...] = field(kw_only=True)
    stored_value: object = field(kw_only=True, repr=False)
    _hash: int | None = field(default=None, init=False, compare=False, repr=False)

    def __hash__(self) -> int:
        cached = self._hash
        if cached is None:
            cached = hash(
                (
                    self.code,
                    self.entity,
                    self.member,
                    self.object_key,
                    self.path,
                    _structural_hash(self.stored_value),
                )
            )
            object.__setattr__(self, "_hash", cached)
        return cached


@dataclass(frozen=True, slots=True)
class InvalidData[T]:
    """One result root some stored state contradicted, in the position it occupied.

    ``data`` is the complete hydrated root wherever every value could be produced
    without inventing one, and ``None`` where it could not — a leaf outside its
    declared type, a non-nullable Attribute holding SQL NULL, an unknown family
    tag, or an undecodable primary key. Hydration never repairs: a caller may
    author a corrective write from a hydrated root, and Parallax authors none.

    ``issues`` is unordered because a diagnosis is a fact rather than a sequence:
    reaching one affected object through several include paths does not duplicate
    it, and two identical diagnoses whose affected object cannot be identified
    collapse because nothing distinguishes them. Human-readable formatting sorts
    codes for presentation only.

    ``object_key`` identifies this result root across its states when its primary
    key decoded; ``version`` is present for a decoded explicitly versioned root
    and ``edge`` for a decoded temporal one, so the two never appear together.
    ``ordinal`` is always this element's zero-based position in the ordered
    result, including when the other locators are available.
    """

    issues: frozenset[StoredDataIssue]
    data: T | None
    object_key: ObjectKey | None
    version: int | None
    edge: Edge | None
    ordinal: int


_EXCEPTION_MACHINERY: Final[frozenset[str]] = frozenset(
    {"__cause__", "__context__", "__notes__", "__suppress_context__", "__traceback__"}
)


class InvalidDataError(RuntimeError):
    """A default accessor's refusal of a result carrying invalid stored data.

    :attr:`invalid_data` is nonempty, in result order, and is the exception's
    sole machine-readable report: there is no singular code, no flattened issue
    collection, no cause, and no second name for the same tuple. The
    constructor settles it together with the message derived from it, and every
    later assignment or deletion is refused — including the inherited ``args``
    :func:`str` reads — so the wording can never describe results the report no
    longer carries.

    The two records get that immutability from ``frozen=True``, which an
    exception cannot use: a frozen ``__setattr__`` also refuses
    :meth:`add_note`, and ``__slots__`` restricts nothing while
    :class:`BaseException` carries an instance dictionary. Freezing by hand
    instead leaves the state the interpreter owns — chaining, traceback, and
    notes — writable, and refuses everything else.
    """

    _invalid_data: tuple[InvalidData[object], ...]

    def __init__(self, invalid_data: Iterable[InvalidData[object]]) -> None:
        records = tuple(invalid_data)
        if not records:
            raise ValueError("an invalid-data refusal carries at least one record")
        codes = sorted({issue.code for record in records for issue in record.issues})
        super().__init__(
            f"{len(records)} result root(s) hold invalid stored data ({', '.join(codes)})"
        )
        object.__setattr__(self, "_invalid_data", records)

    def __setattr__(self, name: str, value: object) -> None:
        if name not in _EXCEPTION_MACHINERY:
            raise AttributeError(f"InvalidDataError is frozen; cannot assign {name!r}")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name not in _EXCEPTION_MACHINERY:
            raise AttributeError(f"InvalidDataError is frozen; cannot delete {name!r}")
        super().__delattr__(name)

    @property
    def invalid_data(self) -> tuple[InvalidData[object], ...]:
        """The invalid result roots this refusal reports, in result order."""
        return self._invalid_data
