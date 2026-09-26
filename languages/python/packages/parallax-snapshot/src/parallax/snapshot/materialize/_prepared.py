from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    ManagedValue,
    NeutralType,
    UnknownFamilyTag,
)
from parallax.core.db_port import Row
from parallax.core.document_codec import DocumentFinding, MemberShape, locate_raw_entity_member
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Occurrence,
    ValueObjectMetadata,
)
from parallax.core.unit_work.observe import occurrence_value
from parallax.core.wire import encode_wire
from parallax.snapshot.materialize._convert import (
    AttributeReadContract,
    LevelContext,
    build_positional_many,
    build_positional_object,
    convert_deferred,
)
from parallax.snapshot.materialize._page import ABSENT, LogicalKey, PageBuilder
from parallax.snapshot.materialize._views import SourceLevel

__all__ = ["PreparedRead", "RowPublisher", "bind"]


class _CompiledRead(Protocol):
    """What a prepared read reads off the compiled read it is bound to."""

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]: ...

    @property
    def projected_documents(self) -> tuple[ValueObjectMetadata, ...]: ...

    def attribute_reads(self, entity: EntityIdentity) -> tuple[AttributeReadContract, ...]: ...

    def row_identity(
        self, row: Row | Mapping[str, object]
    ) -> tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]: ...

    def raw_member_of(
        self, row: Row | Mapping[str, object], resolved: EntityIdentity, key: str
    ) -> object: ...

    def raw_member_classifier(
        self,
        resolved: EntityIdentity,
        key: str,
        *,
        build_object: Callable[[MemberShape, Iterable[object]], object] | None = None,
        build_many: Callable[[Iterable[object]], object] | None = None,
    ) -> Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]: ...

    def raw_member_location(self, resolved: EntityIdentity, key: str) -> str | None: ...

    def classified_members(self, resolved: EntityIdentity) -> frozenset[str]: ...

    def raw_member_ordinal(self, resolved: EntityIdentity, key: str) -> int | None: ...

    def publication_keys(
        self, resolved: EntityIdentity, variant: str | None
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class PreparedRead:
    """One compiled read together with the levels its rows convert under.

    The whole of what a read lane needs to turn driver rows into projections:
    convert a raw provider row and observe it, with no level, contract,
    classified-member set, or finding crossing the call. A lane that named any
    of those would be coordinating a shape it does not own, and would be the
    second place the pairing of a row with its own level could go wrong.

    Both halves it is built from are private for that reason: the level table is
    reachable only through conversion, so nothing outside can read a level,
    replace one, or hold the compiled read apart from the levels bound with it.
    """

    _compiled: _CompiledRead
    _levels: Mapping[EntityIdentity, LevelContext]

    def convert_driver(
        self,
        row: Row | Mapping[str, object],
        builder: PageBuilder,
        *,
        source: SourceLevel,
        correlation_members: tuple[AttributeIdentity, ...] = (),
    ) -> tuple[int, EntityIdentity, object | None, str | None]:
        """Convert one provider row without allocating a per-row carrier."""
        resolved, variant, unknown, document = self._compiled.row_identity(row)
        level = self._levels[resolved]
        if isinstance(row, tuple) and level.direct_row is not None:
            selected = level.direct_row(row)
            witness = (
                cast("tuple[object, ...]", selected)
                if len(level.result_ordinals) != 1
                else (selected,)
            )
            if not level.requires_state_reduction and unknown is None:
                layout = level.layout
                primary_key = witness[layout.primary_key[0]]
                key = (
                    None
                    if primary_key is ABSENT
                    else LogicalKey(
                        layout.family,
                        primary_key,
                        tuple(witness[position] for position in layout.temporal_starts),
                    )
                )
                ref = builder.add_claim(
                    source,
                    layout,
                    key,
                    witness,
                    witness,
                    (),
                    witness,
                )
                return ref, resolved, document, variant
            classifiable = (1 << len(witness)) - 1
        else:
            classifiable = 0
            layout = level.layout
            witness_values: list[object] = [ABSENT] * len(layout.members)
            for position, attribute in enumerate(level.layout.attributes):
                key = (
                    attribute.storage.name
                    if not level.attribute_reads
                    else level.attribute_reads[position].result_key
                )
                document_member = (
                    level.document_member_names[position] if level.document_member_names else None
                )
                if document_member is not None:
                    raw = (
                        SQL_NULL
                        if document is None
                        else locate_raw_entity_member(
                            cast("DocumentValue", document), document_member
                        )
                    )
                    present = True
                else:
                    ordinal = level.result_ordinals[position] if level.result_ordinals else None
                    raw, present = self._raw_driver_presence(row, resolved, key, ordinal=ordinal)
                witness_values[position] = raw
                if present:
                    classifiable |= 1 << position
            for position, (occurrence, projected) in enumerate(
                zip(level.layout.occurrences, level.projected_by_position, strict=True),
                start=len(level.layout.attributes),
            ):
                if not projected:
                    continue
                key = occurrence.storage.name
                document_member = (
                    level.document_member_names[position] if level.document_member_names else None
                )
                if document_member is not None:
                    raw = (
                        SQL_NULL
                        if document is None
                        else locate_raw_entity_member(
                            cast("DocumentValue", document), document_member
                        )
                    )
                    present = True
                else:
                    ordinal = level.result_ordinals[position] if level.result_ordinals else None
                    raw, present = self._raw_driver_presence(
                        row, resolved, key, ordinal=ordinal, default=None
                    )
                witness_values[position] = raw
                if present:
                    classifiable |= 1 << position
            witness = tuple(witness_values)
        ref = convert_deferred(
            witness,
            level,
            builder,
            source=source,
            classifiable=classifiable,
            unknown_family_tag=unknown,
            correlation_members=correlation_members,
        )
        return ref, resolved, document, variant

    def _raw_driver_presence(
        self,
        row: Row | Mapping[str, object],
        resolved: EntityIdentity,
        key: str,
        *,
        ordinal: int | None = None,
        default: object = ABSENT,
    ) -> tuple[object, bool]:
        if isinstance(row, tuple) and ordinal is not None:
            return row[ordinal], True
        try:
            return self._compiled.raw_member_of(row, resolved, key), True
        except KeyError:
            return default, False

    def row_publisher(self) -> RowPublisher:
        """Open one Page's flat-row publisher; what it derives dies with it."""
        return RowPublisher(self._compiled, self._levels)


class RowPublisher:
    """Publishes one Page's flat rows, deriving one operation per concrete
    Entity and `familyVariant` pair on first sight of that pair."""

    __slots__ = ("_compiled", "_levels", "_operations")

    def __init__(
        self, compiled: _CompiledRead, levels: Mapping[EntityIdentity, LevelContext]
    ) -> None:
        self._compiled = compiled
        self._levels = levels
        self._operations: dict[tuple[EntityIdentity, str | None], _RowOperation] = {}

    def publish(
        self, concrete: EntityIdentity, row: tuple[object, ...], variant: str | None
    ) -> dict[str, object]:
        """One positional member row of ``concrete`` as its result-keyed flat row."""
        pair = (concrete, variant)
        operation = self._operations.get(pair)
        if operation is None:
            operation = self._operations[pair] = _row_operation(
                self._levels[concrete], self._compiled.publication_keys(concrete, variant), variant
            )
        return operation(row)


@dataclass(frozen=True, slots=True)
class _RowOperation:
    members: tuple[tuple[int, str, NeutralType | None, Occurrence | None], ...]
    keys: tuple[str, ...]
    variant: str | None

    def __call__(self, row: tuple[object, ...]) -> dict[str, object]:
        values: dict[str, object] = {}
        for position, key, encoded, occurrence in self.members:
            value = row[position]
            if value is ABSENT:
                continue
            if occurrence is not None:
                value = occurrence_value(value, occurrence, ABSENT)
            elif encoded is not None and value is not None:
                value = encode_wire(encoded, cast("ManagedValue", value))
            values[key] = value
        for key in self.keys:
            values.setdefault(key, None)
        if self.variant is not None:
            values["familyVariant"] = self.variant
        return values


def _row_operation(
    level: LevelContext, keys: tuple[str, ...], variant: str | None
) -> _RowOperation:
    # Key order is observable: kept members in layout order, then renamed
    # Attributes, then publication-key padding, then `familyVariant`. An
    # Attribute's own result key wins over its storage key, which may be another
    # Attribute's result key.
    layout = level.layout
    reads = level.attribute_reads
    published = frozenset(keys)
    kept: list[tuple[int, str, NeutralType | None, Occurrence | None]] = []
    renamed: list[tuple[int, str, NeutralType | None, Occurrence | None]] = []
    for position, attribute in enumerate(layout.attributes):
        storage = attribute.storage.name
        if not reads:
            kept.append((position, storage, None, None))
            continue
        read = reads[position]
        result = read.result_key
        encoded = attribute.type if read.encoded else None
        if result != storage and result in published:
            renamed.append((position, result, encoded, None))
        else:
            kept.append((position, storage, encoded if storage in published else None, None))
    kept.extend(
        (position, occurrence.storage.name, None, occurrence.definition)
        for position, occurrence in enumerate(layout.occurrences, start=len(layout.attributes))
    )
    return _RowOperation((*kept, *renamed), keys, variant)


def bind(
    model: CatalogedModel,
    compiled: _CompiledRead,
    *,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> PreparedRead:
    """Prepare ``compiled`` against ``model``: one level per Entity it can resolve.

    Paid once per compiled read, which is where the state belongs — the member
    layouts are the model's and the projected documents and Attribute contracts
    are this statement's, and no row of the read can change either.
    """
    return PreparedRead(
        compiled,
        MappingProxyType(
            {
                identity: _level_context(model, compiled, identity, correlation_members)
                for identity in compiled.resolvable
            }
        ),
    )


def _level_context(
    model: CatalogedModel,
    compiled: _CompiledRead,
    identity: EntityIdentity,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> LevelContext:
    layout = model.layouts.entity(identity)
    reads = compiled.attribute_reads(identity)
    keys = tuple(
        attribute.storage.name if not reads else reads[position].result_key
        for position, attribute in enumerate(layout.attributes)
    ) + tuple(occurrence.storage.name for occurrence in layout.occurrences)
    classified = compiled.classified_members(identity)
    return LevelContext(
        layout,
        compiled.projected_documents,
        reads,
        classified,
        tuple(compiled.raw_member_ordinal(identity, key) for key in keys),
        classifiers=tuple(
            compiled.raw_member_classifier(
                identity,
                key,
                build_object=build_positional_object,
                build_many=build_positional_many,
            )
            if key in classified
            else None
            for key in keys
        ),
        document_member_names=tuple(compiled.raw_member_location(identity, key) for key in keys),
        routing_members=correlation_members,
    )
