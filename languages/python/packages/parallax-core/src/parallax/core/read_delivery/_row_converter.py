from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

from parallax.core.base import ManagedValue, NeutralType
from parallax.core.db_port import Row
from parallax.core.deep_fetch import ResolvedReadProjection
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    OccurrenceDefinition,
)
from parallax.core.read_delivery._convert import EntityReadMapping
from parallax.core.read_delivery._page import ABSENT, PageBuilder, SourceLevel
from parallax.core.read_delivery._row_decoding import (
    fixed_entity,
    member_classifiers,
    require_arity,
    row_identity,
    row_variants,
)
from parallax.core.read_delivery._row_recording import (
    RecordRow,
    located_stored_values,
    record_deferred,
    record_judged,
    record_trusted,
    record_trusted_singleton,
)
from parallax.core.sql_gen._inheritance import ReadResultContract
from parallax.core.wire import encode_wire
from parallax.core.write_plan.observe import occurrence_value

__all__ = ["FetchedRowObserver", "ReadRowConverter", "RowPublisher", "bind"]


class FetchedRowObserver(Protocol):
    """What recording reports about each fetched row it registers."""

    def observe_fetched_row(
        self, fetched_row: int, entity: EntityIdentity, document: object | None, /
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ReadRowConverter:
    """One compiled read's result contract together with the entity mappings its
    rows record under, and how each is recorded.

    The whole of what a read lane needs to turn driver rows into fetched rows:
    record a raw provider row and observe it, with no mapping, contract,
    classified-member set, or finding crossing the call. A lane that named any
    of those would be coordinating a shape it does not own, and would be the
    second place the pairing of a row with its own mapping could go wrong.

    Everything it is built from is private for that reason: the mapping table
    is reachable only through recording, so nothing outside can read a mapping,
    replace one, or hold the contract apart from the mappings bound with it.
    ``_record_trusted`` records a row nothing host-checks or classifies and
    ``_record_reduced`` every other row, both chosen when the read was bound;
    ``_fixed`` is the mapping of a read whose every row names one Entity with
    no shared document, which skips identity resolution per row.
    """

    _contract: ReadResultContract
    _mappings_by_entity: Mapping[EntityIdentity, EntityReadMapping]
    _record_trusted: RecordRow
    _record_reduced: RecordRow
    _fixed: EntityReadMapping | None
    _operations: Mapping[tuple[EntityIdentity, str | None], _RowOperation] | None

    def record_row(
        self,
        row: Row,
        builder: PageBuilder,
        *,
        source: SourceLevel,
    ) -> tuple[int, EntityIdentity, object | None, str | None]:
        """Record one provider row in ``builder``, answering its fetched row
        index, the Entity it resolved to, its shared document, and its
        `familyVariant` spelling."""
        fixed = self._fixed
        if fixed is not None:
            require_arity(self._contract, row)
            resolved, variant, unknown, document = fixed.concrete_entity, None, None, None
            mapping = fixed
        else:
            resolved, variant, unknown, document = row_identity(self._contract, row)
            mapping = self._mappings_by_entity[resolved]
        direct = mapping.direct_row
        if direct is not None:
            selected = direct(row)
            stored_values = (
                cast("tuple[object, ...]", selected)
                if len(mapping.result_ordinals) != 1
                else (selected,)
            )
            classifiable = mapping.every_member_present
        else:
            stored_values, classifiable = located_stored_values(mapping, row, document)
        record = (
            self._record_trusted
            if not mapping.requires_state_reduction and unknown is None
            else self._record_reduced
        )
        return (
            record(mapping, stored_values, classifiable, unknown, builder, source),
            resolved,
            document,
            variant,
        )

    def record_rows(
        self,
        rows: Iterable[Row],
        builder: PageBuilder,
        source: SourceLevel,
        observer: FetchedRowObserver | None,
    ) -> tuple[int, ...]:
        """Record ``rows`` into ``builder`` at ``source``, reporting each to
        ``observer`` while its row is still live, and answer their fetched row
        indices in row order.

        Each row is reported under its OWN resolved concrete Entity, together
        with its raw shared document. ``observer`` is ``None`` for a read that
        records nothing about its rows, which then makes no call per row.
        """
        fixed = self._fixed
        if fixed is None:
            refs: list[int] = []
            for row in rows:
                ref, resolved, document, _variant = self.record_row(row, builder, source=source)
                refs.append(ref)
                if observer is not None:
                    observer.observe_fetched_row(ref, resolved, document)
            return tuple(refs)
        return self._record_fixed(fixed, rows, builder, source, observer)

    def _record_fixed(
        self,
        mapping: EntityReadMapping,
        rows: Iterable[Row],
        builder: PageBuilder,
        source: SourceLevel,
        observer: FetchedRowObserver | None,
    ) -> tuple[int, ...]:
        """Record a fixed-identity read's rows, each under ``mapping`` with its
        arity still checked."""
        contract = self._contract
        width = len(contract.slots)
        record = self._record_reduced if mapping.requires_state_reduction else self._record_trusted
        direct = mapping.direct_row
        single = len(mapping.result_ordinals) == 1
        every_member = mapping.every_member_present
        concrete = mapping.concrete_entity
        refs: list[int] = []
        append = refs.append
        for row in rows:
            if len(row) != width:
                require_arity(contract, row)
            if direct is None:
                stored_values, classifiable = located_stored_values(mapping, row, None)
                ref = record(mapping, stored_values, classifiable, None, builder, source)
            elif single:
                ref = record(mapping, (direct(row),), every_member, None, builder, source)
            else:
                ref = record(
                    mapping,
                    cast("tuple[object, ...]", direct(row)),
                    every_member,
                    None,
                    builder,
                    source,
                )
            append(ref)
            if observer is not None:
                observer.observe_fetched_row(ref, concrete, None)
        return tuple(refs)

    def row_publisher(self) -> RowPublisher:
        """The flat-row publisher of a read bound with its row operations.

        Raises :class:`ValueError` for a read bound without them."""
        operations = self._operations
        if operations is None:
            raise ValueError("this read was bound without row operations")
        return RowPublisher(operations)


class RowPublisher:
    """Publishes flat rows through the operations its read bound, one per
    concrete Entity and `familyVariant` pair."""

    __slots__ = ("_operations",)

    def __init__(
        self, operations: Mapping[tuple[EntityIdentity, str | None], _RowOperation]
    ) -> None:
        self._operations = operations

    def publish(
        self, concrete: EntityIdentity, row: tuple[object, ...], variant: str | None
    ) -> dict[str, object]:
        """One positional member row of ``concrete`` as its result-keyed flat row."""
        return self._operations[concrete, variant](row)


@dataclass(frozen=True, slots=True)
class _RowOperation:
    members: tuple[tuple[int, str, NeutralType | None, OccurrenceDefinition | None], ...]
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
    contract: ReadResultContract, mapping: EntityReadMapping, variant: str | None
) -> _RowOperation:
    """How rows resolving to ``mapping``'s Entity under ``variant`` publish.

    Key order is observable: kept members in layout order, then encoded
    Attributes under their encoded keys, then the remaining publication keys as
    null, then `familyVariant`. Those keys are, in cell order, every cell that
    stays in each resolved row, then this Entity's own cells that publish only
    for it, then the shared document's sibling padding.
    """
    layout = mapping.layout
    slots = contract.slots
    ordinals = mapping.result_ordinals
    members = layout.member_selection.bindings
    kept: list[tuple[int, str, NeutralType | None, OccurrenceDefinition | None]] = []
    encoded: list[tuple[int, str, NeutralType | None, OccurrenceDefinition | None]] = []
    for position, attribute in enumerate(layout.attributes):
        if mapping.encoded_positions >> position & 1:
            encoded.append(
                (position, _scalar_key(contract, ordinals[position]), attribute.type, None)
            )
        else:
            kept.append((position, attribute.storage.name, None, None))
    kept.extend(
        (position, occurrence.storage.name, None, occurrence.definition)
        for position, occurrence in enumerate(layout.occurrences, start=len(layout.attributes))
    )
    keys = dict.fromkeys(
        slot.padding_key for slot in slots if slot is not None and slot.padding_key is not None
    )
    for ordinal, position in sorted(
        (ordinal, position) for position, ordinal in enumerate(ordinals) if ordinal is not None
    ):
        slot = slots[ordinal]
        if slot is None or slot.padding_key is None:
            keys.setdefault(
                members[position].storage.name
                if slot is None or slot.scalar is None
                else slot.scalar.publication_key
            )
    shared = contract.shared_document
    entry = None if shared is None else shared.by_entity.get(mapping.concrete_entity)
    if entry is not None:
        keys.update(dict.fromkeys(entry.padding))
    return _RowOperation((*kept, *encoded), tuple(keys), variant)


def _scalar_key(contract: ReadResultContract, ordinal: int | None) -> str:
    slot = None if ordinal is None else contract.slots[ordinal]
    if slot is None or slot.scalar is None:  # pragma: no cover - an encoded cell is a scalar's
        raise ValueError("an encoded Attribute is read from a scalar cell")
    return slot.scalar.publication_key


def bind(
    model: CatalogedModel,
    contract: ReadResultContract,
    projection: ResolvedReadProjection,
    *,
    correlation_members: tuple[AttributeIdentity, ...] = (),
    singleton: bool = False,
    acquisition: bool = False,
    row_operations: bool = False,
) -> ReadRowConverter:
    """Bind one compiled read's ``contract`` and resolved ``projection`` to
    ``model``: one mapping per Entity its rows can resolve to, and how each row
    is recorded.

    Paid once per compiled read, which is where the state belongs — the member
    layouts are the model's and the projected occurrences and member sources
    are this statement's, and no row of the read can change either. Raises
    ``ValueError`` where the contract's sources are laid out for another
    member order than ``model``'s.
    An occurrence is projected exactly where ``projection`` selects its
    identity, including for an Entity outside the read's position.
    ``correlation_members`` are the members this read's rows route by; a read
    routed by a different selection is bound separately.

    A ``singleton`` read is one whose level records each row key at most once
    on its Page, so a row needs no comparison before it is judged: unless the
    read is a write's ``acquisition``, whose occurrences stay unjudged by
    contract, every row is judged as it is recorded. Every other row's payload
    judgment is deferred. ``row_operations`` prepares the flat-row publication
    of each Entity and `familyVariant` pair the contract can resolve a row to.
    """
    mappings = MappingProxyType(
        {
            identity: _entity_read_mapping(
                model, identity, contract, projection, correlation_members
            )
            for identity in contract.resolvable
        }
    )
    fixed = fixed_entity(contract)
    return ReadRowConverter(
        contract,
        mappings,
        record_trusted_singleton if singleton else record_trusted,
        record_judged if singleton and not acquisition else record_deferred,
        None if fixed is None else mappings[fixed],
        MappingProxyType(
            {
                pair: _row_operation(contract, mappings[pair[0]], pair[1])
                for pair in row_variants(contract)
                if pair[0] in mappings
            }
        )
        if row_operations
        else None,
    )


def _entity_read_mapping(
    model: CatalogedModel,
    identity: EntityIdentity,
    contract: ReadResultContract,
    projection: ResolvedReadProjection,
    correlation_members: tuple[AttributeIdentity, ...],
) -> EntityReadMapping:
    layout = model.layouts.entity(identity)
    sources = contract.sources(identity)
    if sources.selection is not layout.member_selection and tuple(
        sources.selection.identities
    ) != tuple(layout.members):
        raise ValueError(
            f"{identity.canonical}: the read's member sources are not this model's member order"
        )
    ordinals = sources.cell_ordinals()
    document_members = sources.document_member_names()
    slots = contract.slots
    return EntityReadMapping(
        layout,
        projection,
        ordinals,
        member_classifiers(contract, identity, layout.member_selection.bindings, document_members),
        document_members,
        sum(
            1 << position
            for position, ordinal in enumerate(ordinals[: layout.attribute_count])
            if ordinal is not None
            and (slot := slots[ordinal]) is not None
            and slot.scalar is not None
            and slot.scalar.encoded
        ),
        correlation_members,
    )
