from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from typing import ClassVar, Final, Literal, Self, cast

from parallax.core.internal.base import ParallaxError
from parallax.core.internal.metamodel import EntityIdentity, MemberIdentity
from parallax.core.internal.temporal_read import Edge
from parallax.core.internal.write_plan import ObjectKey

__all__ = [
    "CONTINUATION_ORDER_NOT_TOTAL",
    "MISSING_STORED_VALUE",
    "RESULT_DATA_INVALID",
    "InvalidData",
    "InvalidDataError",
    "StoredDataIssue",
    "StoredDataIssueCode",
]


type StoredDataIssueCode = Literal[
    "stored-data-required-member-absent",
    "stored-data-required-member-null",
    "stored-data-one-wrong-kind",
    "stored-data-many-wrong-kind",
    "stored-data-leaf-undecodable",
    "stored-data-attribute-null",
    "stored-data-family-tag-unknown",
    "stored-data-primary-key-null",
    "stored-data-primary-key-undecodable",
]
"""The closed stored-data issue vocabulary."""


class MissingStoredValue:
    """The evidence a traversable stored object held no member at all.

    Distinct from ``None``, which is the stored SQL or JSON null. Sameness is
    identity: :data:`MISSING_STORED_VALUE` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[MissingStoredValue | None] = None

    def __new__(cls) -> MissingStoredValue:
        if MissingStoredValue._instance is None:
            MissingStoredValue._instance = super().__new__(cls)
        return MissingStoredValue._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("MissingStoredValue admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "MISSING_STORED_VALUE"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "MISSING_STORED_VALUE"


MISSING_STORED_VALUE: Final[MissingStoredValue] = MissingStoredValue()
"""Marks a member absent from stored data, as distinct from a stored null."""


def _structural_hash(value: object) -> int:
    """``value``'s hash under the structural equality evidence compares by.

    A read-only mapping is unhashable and its equality is key-order
    insensitive, so the mapping case hashes an unordered set of member hashes;
    every other frozen shape is already hashable, and the tuple case exists only
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
    """One way stored data contradicts the model; `code` says which.

    One stored state that contradicts the model, as the public diagnosis of it.

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
    single-valued Entity Attribute under either Storage Layout, an unresolved
    family tag, and a whole stored document read in a kind it cannot be read as.
    A scalar collection keeps its own logical path, ending at the rejected
    element's position or at the collection itself for a malformed array.

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

    def __getstate__(self) -> list[object]:
        """This issue's state, with the cached hash left behind.

        Text hashing is seeded per interpreter, so a cache computed where the
        issue was pickled is not the hash an equal issue computes where it is
        read. Publication hashes every issue into a frozenset, so a cache that
        travelled would always arrive, and arrive disagreeing with equality.
        """
        return [
            None if declared.name == "_hash" else getattr(self, declared.name)
            for declared in fields(self)
        ]


@dataclass(frozen=True, slots=True)
class InvalidData[T]:
    """One result root that stored data contradicted, with the issues found.

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


INTERPRETER_OWNED_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {"__cause__", "__context__", "__notes__", "__suppress_context__", "__traceback__"}
)
"""The attributes of an exception the INTERPRETER owns rather than its author.

An exception frozen by hand leaves exactly these writable, so chaining,
tracebacks, and notes behave as they do on any exception.
"""

RESULT_DATA_INVALID: Final = "result-data-invalid"
"""The code of a result accessor's refusal of roots holding invalid stored data."""

CONTINUATION_ORDER_NOT_TOTAL: Final = "snapshot-stream-continuation-order-not-total"
"""The code of a streamed delivery's refusal to continue past two roots stored
at one Continuation Order coordinate."""


class InvalidDataError(ParallaxError):
    """Stored data contradicts the model, so Parallax cannot read it as valid or revise it.

    Under :data:`RESULT_DATA_INVALID`, a default accessor refused a result:
    :attr:`invalid_data` is nonempty, in result order, and is the refusal's
    sole machine-readable report, with no flattened issue collection and no
    second name for the same tuple. :attr:`edition` is the Model Edition the
    result was read under, supplied by that result's owner: a refusal is
    delayed until an accessor is reached, so the stamp travels with it rather
    than being looked up again, and the validators that judged the stored data
    need no edition at all. Under any other code there is no result, so
    :attr:`invalid_data` is empty and :attr:`edition` is ``None``.

    Under :data:`CONTINUATION_ORDER_NOT_TOTAL`, a streamed delivery met two
    adjacent roots stored at one Continuation Order coordinate, and
    :attr:`coordinate` is an inert copy of where they stood, positionally
    aligned with the order's terms: readable and comparable, with no public
    constructor turning it back into pagination authority, and kept out of the
    message, the default repr, and default logging. Under any other code it is
    ``None``. The constructor refuses any pairing of a code and these fields
    other than the ones described here.

    The constructor settles every field, and every later attribute assignment
    or deletion is refused — including the inherited ``args`` :func:`str`
    reads — so the wording can never describe results the report no longer
    carries. The records get that immutability from ``frozen=True``, which an
    exception cannot use: a frozen ``__setattr__`` also refuses
    :meth:`add_note`, and ``__slots__`` restricts nothing while
    :class:`BaseException` carries an instance dictionary. Freezing by hand
    instead leaves the state the interpreter owns — chaining, traceback, and
    notes — writable, and refuses everything else. Being a ``__setattr__`` is
    also what bounds it: an instance-dictionary write, ``object.__setattr__``,
    and a subclass replacing it reach past this refusal exactly as they reach
    past ``frozen=True``, and are outside the contract for the same reason.
    """

    _invalid_data: tuple[InvalidData[object], ...]
    _edition: str | None
    _coordinate: tuple[object, ...] | None

    def __init__(
        self,
        code: str,
        message: str,
        *,
        invalid_data: Iterable[InvalidData[object]] = (),
        edition: str | None = None,
        coordinate: tuple[object, ...] | None = None,
    ) -> None:
        records = tuple(invalid_data)
        if (code == CONTINUATION_ORDER_NOT_TOTAL) != (coordinate is not None):
            raise ValueError(
                f"a {CONTINUATION_ORDER_NOT_TOTAL} refusal, and only one, carries a coordinate"
            )
        if code == RESULT_DATA_INVALID:
            if not records or edition is None:
                raise ValueError(
                    f"a {RESULT_DATA_INVALID} refusal carries at least one record and an edition"
                )
        elif records or edition is not None:
            raise ValueError(
                f"only a {RESULT_DATA_INVALID} refusal carries invalid-data records or an edition"
            )
        super().__init__(code, message)
        object.__setattr__(self, "_invalid_data", records)
        object.__setattr__(self, "_edition", edition)
        object.__setattr__(self, "_coordinate", coordinate)

    def __setattr__(self, name: str, value: object) -> None:
        if name not in INTERPRETER_OWNED_ATTRIBUTES:
            raise AttributeError(f"InvalidDataError is frozen; cannot assign {name!r}")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name not in INTERPRETER_OWNED_ATTRIBUTES:
            raise AttributeError(f"InvalidDataError is frozen; cannot delete {name!r}")
        super().__delattr__(name)

    @property
    def invalid_data(self) -> tuple[InvalidData[object], ...]:
        return self._invalid_data

    @property
    def edition(self) -> str | None:
        return self._edition

    @property
    def coordinate(self) -> tuple[object, ...] | None:
        return self._coordinate
