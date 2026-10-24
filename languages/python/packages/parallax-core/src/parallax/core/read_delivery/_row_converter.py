from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    ManagedValue,
    NeutralType,
)
from parallax.core.db_port import Row
from parallax.core.deep_fetch import ResolvedReadProjection
from parallax.core.document_codec import locate_raw_entity_member
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Occurrence,
)
from parallax.core.read_delivery._convert import EntityReadMapping, register_reduced_row
from parallax.core.read_delivery._page import ABSENT, LogicalKey, PageBuilder, SourceLevel
from parallax.core.read_delivery._row_decoding import member_classifiers, row_identity
from parallax.core.sql_gen._inheritance import ReadResultContract
from parallax.core.wire import encode_wire
from parallax.core.write_plan.observe import occurrence_value

__all__ = ["ReadRowConverter", "RowPublisher", "bind"]


@dataclass(frozen=True, slots=True)
class ReadRowConverter:
    """One compiled read's result contract together with the entity mappings its
    rows convert under.

    The whole of what a read lane needs to turn driver rows into projections:
    convert a raw provider row and observe it, with no mapping, contract,
    classified-member set, or finding crossing the call. A lane that named any
    of those would be coordinating a shape it does not own, and would be the
    second place the pairing of a row with its own mapping could go wrong.

    Everything it is built from is private for that reason: the mapping table
    is reachable only through conversion, so nothing outside can read a mapping,
    replace one, or hold the contract apart from the mappings bound with it.
    """

    _contract: ReadResultContract
    _mappings_by_entity: Mapping[EntityIdentity, EntityReadMapping]

    def convert_row(
        self,
        row: Row,
        builder: PageBuilder,
        *,
        source: SourceLevel,
    ) -> tuple[int, EntityIdentity, object | None, str | None]:
        """Register one provider row in ``builder``, answering its projection
        index, the Entity it resolved to, its shared document, and its
        `familyVariant` spelling.

        A row whose mapping needs no state reduction registers its witness as its
        member row. Any other row is claimed now, with its identity and
        correlation values judged for page assembly, and the rest of its
        payload judged when its Page-owned state is first needed.
        """
        resolved, variant, unknown, document = row_identity(self._contract, row)
        mapping = self._mappings_by_entity[resolved]
        if mapping.direct_row is not None:
            selected = mapping.direct_row(row)
            witness = (
                cast("tuple[object, ...]", selected)
                if len(mapping.result_ordinals) != 1
                else (selected,)
            )
            classifiable = mapping.every_member_present
        else:
            classifiable = 0
            layout = mapping.layout
            ordinals = mapping.result_ordinals
            document_members = mapping.document_member_names
            witness_values: list[object] = [ABSENT] * len(layout.members)
            for position in range(layout.attribute_count):
                document_member = document_members[position]
                if document_member is not None:
                    witness_values[position] = (
                        SQL_NULL
                        if document is None
                        else locate_raw_entity_member(
                            cast("DocumentValue", document), document_member
                        )
                    )
                elif (ordinal := ordinals[position]) is not None:
                    witness_values[position] = row[ordinal]
                else:
                    continue
                classifiable |= 1 << position
            for position, projected in enumerate(
                mapping.projected_by_position, start=layout.attribute_count
            ):
                if not projected:
                    continue
                document_member = document_members[position]
                if document_member is not None:
                    witness_values[position] = (
                        SQL_NULL
                        if document is None
                        else locate_raw_entity_member(
                            cast("DocumentValue", document), document_member
                        )
                    )
                elif (ordinal := ordinals[position]) is not None:
                    witness_values[position] = row[ordinal]
                else:
                    # A requested occurrence this row's Entity carries no
                    # source for reads as stored SQL NULL.
                    witness_values[position] = None
                    continue
                classifiable |= 1 << position
            witness = tuple(witness_values)
        if not mapping.requires_state_reduction and unknown is None:
            layout = mapping.layout
            primary_key = witness[layout.primary_key[0]]
            key = (
                None
                if primary_key is ABSENT
                else LogicalKey(layout.family, primary_key, mapping.temporal_start_values(witness))
            )
            ref = builder.add_claim(source, layout, key, witness, witness, (), witness)
        else:
            ref = register_reduced_row(
                witness,
                mapping,
                builder,
                source=source,
                classifiable=classifiable,
                unknown_family_tag=unknown,
            )
        return ref, resolved, document, variant

    def row_publisher(self) -> RowPublisher:
        """Open one Page's flat-row publisher; what it derives dies with it."""
        return RowPublisher(self._contract, self._mappings_by_entity)


class RowPublisher:
    """Publishes one Page's flat rows, deriving one operation per concrete
    Entity and `familyVariant` pair on first sight of that pair."""

    __slots__ = ("_contract", "_mappings_by_entity", "_operations")

    def __init__(
        self,
        contract: ReadResultContract,
        mappings_by_entity: Mapping[EntityIdentity, EntityReadMapping],
    ) -> None:
        self._contract = contract
        self._mappings_by_entity = mappings_by_entity
        self._operations: dict[tuple[EntityIdentity, str | None], _RowOperation] = {}

    def publish(
        self, concrete: EntityIdentity, row: tuple[object, ...], variant: str | None
    ) -> dict[str, object]:
        """One positional member row of ``concrete`` as its result-keyed flat row."""
        pair = (concrete, variant)
        operation = self._operations.get(pair)
        if operation is None:
            operation = self._operations[pair] = _row_operation(
                self._contract, self._mappings_by_entity[concrete], variant
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
    kept: list[tuple[int, str, NeutralType | None, Occurrence | None]] = []
    encoded: list[tuple[int, str, NeutralType | None, Occurrence | None]] = []
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
) -> ReadRowConverter:
    """Bind one compiled read's ``contract`` and resolved ``projection`` to
    ``model``: one mapping per Entity its rows can resolve to.

    Paid once per compiled read, which is where the state belongs — the member
    layouts are the model's and the projected occurrences and member sources
    are this statement's, and no row of the read can change either. Raises
    ``ValueError`` where the contract's sources are laid out for another
    member order than ``model``'s.
    An occurrence is projected exactly where ``projection`` selects its
    identity, including for an Entity outside the read's position.
    ``correlation_members`` are the members this read's rows route by; a read
    routed by a different selection is bound separately.
    """
    return ReadRowConverter(
        contract,
        MappingProxyType(
            {
                identity: _entity_read_mapping(
                    model, identity, contract, projection, correlation_members
                )
                for identity in contract.resolvable
            }
        ),
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
