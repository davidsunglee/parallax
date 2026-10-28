from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast

from parallax.core.base import NeutralType, NeutralTypeMismatch, ScalarConverter
from parallax.core.metamodel import (
    AuthoringViolation,
    MemberDefinition,
    MemberShape,
    Multiplicity,
    ScalarDefinition,
)
from parallax.core.wire import WireDecodingError

__all__ = [
    "BORROWED_DOCUMENTS",
    "MAPPING_DOCUMENTS",
    "AuthoringCatalog",
    "AuthoringLane",
    "AuthoringPlan",
    "AuthoringRefusal",
    "DocumentAccess",
    "PreparedAuthoringRow",
    "RootPolicy",
]


class DocumentAccess(Protocol):
    """How one lane reads the nested documents and collections it authors.

    ``document`` answers a document's member values in ``shape`` order, with
    ``absent`` where the source states none, or ``None`` for a source that is no
    document. ``elements`` and ``scalar_elements`` answer a collection's members,
    or ``None`` for a carrier the lane does not accept as that collection.
    """

    def document(
        self, source: object, shape: MemberShape, absent: object, /
    ) -> tuple[object, ...] | None: ...

    def elements(self, source: object, /) -> Sequence[object] | None: ...

    def scalar_elements(self, source: object, /) -> Sequence[object] | None: ...


def _mapping_document(
    source: object, shape: MemberShape, absent: object
) -> tuple[object, ...] | None:
    if not isinstance(source, Mapping):
        return None
    mapping = cast("Mapping[str, object]", source)
    return tuple(mapping.get(member.name, absent) for member in shape.members)


def _sequence_elements(source: object) -> Sequence[object] | None:
    if not isinstance(source, Sequence) or isinstance(source, str | bytes | bytearray | memoryview):
        return None
    return cast("Sequence[object]", source)


@dataclass(frozen=True, slots=True)
class _MappingDocuments:
    def document(
        self, source: object, shape: MemberShape, absent: object, /
    ) -> tuple[object, ...] | None:
        return _mapping_document(source, shape, absent)

    def elements(self, source: object, /) -> Sequence[object] | None:
        return _sequence_elements(source)

    def scalar_elements(self, source: object, /) -> Sequence[object] | None:
        return _sequence_elements(source)


@dataclass(frozen=True, slots=True)
class _BorrowedDocuments:
    """Typed authoring: a live Value Object answers through its authoring hooks,
    and a scalar collection is exactly a ``tuple``."""

    def document(
        self, source: object, shape: MemberShape, absent: object, /
    ) -> tuple[object, ...] | None:
        if isinstance(source, Mapping):
            return _mapping_document(cast("Mapping[str, object]", source), shape, absent)
        names_of = getattr(type(source), "__parallax_authoring_names__", None)
        member_of = getattr(type(source), "__parallax_authoring_member__", None)
        if names_of is None or member_of is None:
            return None
        authored = frozenset(cast("Iterable[str]", names_of(source)))
        return tuple(
            member_of(source, member.name) if member.name in authored else absent
            for member in shape.members
        )

    def elements(self, source: object, /) -> Sequence[object] | None:
        return _sequence_elements(source)

    def scalar_elements(self, source: object, /) -> Sequence[object] | None:
        if type(source) is not tuple:
            return None
        return cast("tuple[object, ...]", source)


MAPPING_DOCUMENTS: Final[DocumentAccess] = _MappingDocuments()
BORROWED_DOCUMENTS: Final[DocumentAccess] = _BorrowedDocuments()


@dataclass(frozen=True, slots=True)
class PreparedAuthoringRow:
    """One authored row's stated members: their owned cells packed in member
    order, and a mask with one bit per stated member, an explicit null
    included."""

    cells: tuple[object, ...]
    presence: int


class AuthoringRefusal(Exception):
    """The first member a row's authoring refuses, in member order.

    ``position`` is the refused top-level member, ``violation`` the finding
    relative to it, and ``cause`` the lane's own conversion failure where one
    raised it. The finding owns no wording; its caller renders one.
    """

    def __init__(
        self, position: int, violation: AuthoringViolation, cause: Exception | None
    ) -> None:
        super().__init__(violation)
        self.position = position
        self.violation = violation
        self.cause = cause


type RootPolicy = Callable[[int, Mapping[str, object]], object]
"""What a top-level scalar position's marker-shaped document authors: the
planned value it stands for, or the caller's own refusal."""


class _Refused(Exception):
    def __init__(self, violation: AuthoringViolation, cause: Exception | None) -> None:
        super().__init__(violation)
        self.violation = violation
        self.cause = cause


_CONVERSION_FAILURES: Final = (NeutralTypeMismatch, WireDecodingError)
_MARKER_KEYS: Final = frozenset({"computed", "increment"})


@dataclass(frozen=True, slots=True)
class AuthoringLane:
    """One producer's scalar conversion and document reading."""

    converter_for: Callable[[NeutralType], ScalarConverter]
    access: DocumentAccess


class AuthoringCatalog:
    """A model's authoring plans for its lanes: one converter per lane and
    distinct Neutral Type, and one plan per shape object serving every lane,
    compiled on first request.

    A lane is named by its index in ``lanes``. ``absent`` is the marker a
    nested occurrence's omitted member keeps, the same one accepted Entity
    State spells absence with.
    """

    __slots__ = ("_converters", "_plans", "absent", "lanes")

    def __init__(self, lanes: tuple[AuthoringLane, ...], *, absent: object) -> None:
        self.lanes = lanes
        self.absent = absent
        self._converters: dict[tuple[int, NeutralType], ScalarConverter] = {}
        self._plans: dict[int, AuthoringPlan] = {}

    def plan(self, shape: MemberShape) -> AuthoringPlan:
        """The plan authoring documents of ``shape``."""
        held = self._plans.get(id(shape))
        if held is not None and held.shape is shape:
            return held
        plan = self._plans[id(shape)] = AuthoringPlan(shape, self)
        return plan

    def converter(self, lane: int, declared: NeutralType) -> ScalarConverter:
        key = (lane, declared)
        converter = self._converters.get(key)
        if converter is None:
            converter = self._converters[key] = self.lanes[lane].converter_for(declared)
        return converter


class AuthoringPlan:
    """One shape walked against each lane's converters.

    A complete row is judged in member order, so a missing required member
    and an inadmissible value are refused in the one pass, the first one met
    first. A nested occurrence's cells keep the read side's full-width
    positional form, its omitted members holding the catalog's ``absent``.

    Each lane's position holds its scalar's converter or its occurrence's
    plan, shared with every other plan of the catalog, so a plan owns nothing
    per member beyond those references.
    """

    __slots__ = ("_absent", "_lanes", "_many", "_scalar", "_steps", "shape")

    def __init__(self, shape: MemberShape, catalog: AuthoringCatalog) -> None:
        self.shape = shape
        self._absent = catalog.absent
        self._lanes = catalog.lanes
        members = shape.members
        self._steps: tuple[ScalarConverter | AuthoringPlan, ...] = tuple(
            catalog.converter(lane, member.type)
            if isinstance(member, ScalarDefinition)
            else catalog.plan(member.shape)
            for lane in range(len(catalog.lanes))
            for member in members
        )
        self._many = _mask(member.multiplicity is Multiplicity.MANY for member in members)
        self._scalar = _mask(
            isinstance(member, ScalarDefinition) and member.multiplicity is Multiplicity.ONE
            for member in members
        )

    def authored_values(self, payload: Mapping[str, object]) -> tuple[object, ...]:
        """``payload``'s members in this plan's order, ``absent`` where it names
        none."""
        absent = self._absent
        return tuple(payload.get(member.name, absent) for member in self.shape.members)

    def complete_row(
        self,
        raws: Iterable[object],
        *,
        lane: int,
        required: int,
        omitted: int = 0,
        root: RootPolicy | None = None,
    ) -> PreparedAuthoringRow:
        """The owned cells ``lane`` authors for a row stating every member it
        carries.

        ``raws`` holds one value per member, ``absent`` where the row states
        none. A member in ``omitted`` is read as unstated. An unstated ``many``
        member is its empty collection, and an unstated or null member in
        ``required`` is refused. ``root`` authors a marker-shaped document at a
        top-level scalar.

        Raises :class:`AuthoringRefusal` for the first refused member.
        """
        absent = self._absent
        many = self._many
        scalar = self._scalar
        width = len(self.shape.members)
        base = lane * width
        cells: list[object] = []
        presence = 0
        position = -1
        for position, raw in enumerate(raws):
            bit = 1 << position
            if raw is absent or omitted & bit:
                if many & bit:
                    cells.append(())
                    presence |= bit
                elif required & bit:
                    raise self._missing(position)
                continue
            if raw is None:
                if (required | many) & bit:
                    raise self._missing(position)
                cells.append(None)
            elif scalar & bit:
                cells.append(self._top_level_scalar(base, position, raw, root))
            else:
                try:
                    cells.append(self._structured(lane, position, raw))
                except _Refused as refused:
                    raise AuthoringRefusal(position, refused.violation, refused.cause) from None
            presence |= bit
        if position + 1 != width:
            raise ValueError("a complete row states one value per member of its shape")
        return PreparedAuthoringRow(tuple(cells), presence)

    def document(self, source: object, lane: int) -> tuple[object, ...]:
        """One nested document's full-width cells as ``lane`` authors them,
        raising the internal refusal its enclosing member reports."""
        absent = self._absent
        values = self._lanes[lane].access.document(source, self.shape, absent)
        if values is None:
            raise _Refused(AuthoringViolation("", "not-a-document", source), None)
        members = self.shape.members
        cells: list[object] | None = None
        for position, raw in enumerate(values):
            if raw is absent or raw is None:
                cell = self._unstated(position, raw)
            else:
                try:
                    cell = self._converted(lane, position, raw)
                except _Refused as refused:
                    raise _Refused(
                        _prefixed(members[position].name, refused.violation), refused.cause
                    ) from None
            if cell is not raw:
                cells = cells if cells is not None else list(values)
                cells[position] = cell
        return values if cells is None else tuple(cells)

    def documents(self, source: object, lane: int) -> tuple[object, ...]:
        """A ``many`` occurrence's documents' full-width cells as ``lane``
        authors them, raising the internal refusal its enclosing member
        reports."""
        elements = self._lanes[lane].access.elements(source)
        if elements is None:
            raise _Refused(AuthoringViolation("", "not-a-list", source), None)
        converted: list[object] = []
        for index, element in enumerate(elements):
            try:
                converted.append(self.document(element, lane))
            except _Refused as refused:
                raise _Refused(_prefixed(f"[{index}]", refused.violation), refused.cause) from None
        return tuple(converted)

    def _top_level_scalar(
        self, base: int, position: int, raw: object, root: RootPolicy | None
    ) -> object:
        if root is not None and _is_marker(raw):
            return root(position, cast("Mapping[str, object]", raw))
        try:
            return cast("ScalarConverter", self._steps[base + position])(raw)
        except _CONVERSION_FAILURES as failure:
            raise AuthoringRefusal(
                position, _mismatch("", self.shape.members[position], raw, failure), failure
            ) from None

    def _missing(self, position: int) -> AuthoringRefusal:
        member = self.shape.members[position]
        return AuthoringRefusal(position, AuthoringViolation("", _missing_reason(member)), None)

    def _converted(self, lane: int, position: int, raw: object) -> object:
        if not self._scalar >> position & 1:
            return self._structured(lane, position, raw)
        step = self._steps[lane * len(self.shape.members) + position]
        try:
            return cast("ScalarConverter", step)(raw)
        except _CONVERSION_FAILURES as failure:
            raise _Refused(
                _mismatch("", self.shape.members[position], raw, failure), failure
            ) from None

    def _structured(self, lane: int, position: int, raw: object) -> object:
        """A collection or occurrence member's owned cell."""
        step = self._steps[lane * len(self.shape.members) + position]
        many = self._many >> position & 1
        if isinstance(step, AuthoringPlan):
            return step.documents(raw, lane) if many else step.document(raw, lane)
        member = cast("ScalarDefinition", self.shape.members[position])
        return _scalar_collection(step, member.type, self._lanes[lane].access, raw)

    def _unstated(self, position: int, raw: object) -> object:
        """A nested member's cell when its document states it as null or not
        at all."""
        member = self.shape.members[position]
        if raw is not None:
            if self._many >> position & 1:
                return ()
            if member.nullable:
                return raw
        elif member.nullable:
            return None
        raise _Refused(AuthoringViolation(member.name, _missing_reason(member)), None)


def _scalar_collection(
    convert: ScalarConverter, declared: NeutralType, access: DocumentAccess, source: object
) -> tuple[object, ...]:
    elements = access.scalar_elements(source)
    if elements is None:
        raise _Refused(AuthoringViolation("", "not-a-list", source), None)
    converted: list[object] = []
    for index, element in enumerate(elements):
        if element is None:
            raise _Refused(AuthoringViolation(f"[{index}]", "type-mismatch", None, declared), None)
        try:
            converted.append(convert(element))
        except _CONVERSION_FAILURES as failure:
            raise _Refused(
                AuthoringViolation(
                    f"[{index}]", "type-mismatch", _managed(element, failure), declared
                ),
                failure,
            ) from None
    return tuple(converted)


def _mismatch(
    path: str, member: MemberDefinition, raw: object, failure: Exception
) -> AuthoringViolation:
    declared = member.type if isinstance(member, ScalarDefinition) else None
    return AuthoringViolation(path, "type-mismatch", _managed(raw, failure), declared)


def _managed(raw: object, failure: Exception) -> object:
    return failure.managed if isinstance(failure, NeutralTypeMismatch) else raw


def _missing_reason(
    member: MemberDefinition,
) -> Literal["attribute-missing", "value-object-missing"]:
    return "attribute-missing" if isinstance(member, ScalarDefinition) else "value-object-missing"


def _prefixed(prefix: str, violation: AuthoringViolation) -> AuthoringViolation:
    if not violation.path:
        path = prefix
    elif violation.path.startswith("["):
        path = f"{prefix}{violation.path}"
    else:
        path = f"{prefix}.{violation.path}"
    return AuthoringViolation(path, violation.reason, violation.value, violation.declared_type)


def _mask(flags: Iterable[bool]) -> int:
    mask = 0
    for position, flag in enumerate(flags):
        if flag:
            mask |= 1 << position
    return mask


def _is_marker(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    document = cast("Mapping[object, object]", value)
    return len(document) == 1 and next(iter(document)) in _MARKER_KEYS
