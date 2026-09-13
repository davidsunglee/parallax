"""One compiled read's prepared half: every level its rows can convert under,
derived once where the read was compiled.

A read lane hands rows here and receives projections. What a row converts under
— the exact Entity's member layout, the position's document contributors, and
the statement's own Attribute contracts — is fixed by the model and the compiled
read together, so it is derived at :func:`bind` and shared by every row of that
read. Nothing about a row decides it; a row only names which of the prepared
levels answers it.

Every Entity the read can resolve gets its level at bind
(``CompiledRead.resolvable``), including the ones no row may ever name: a family
root an unrecognized tag falls back to, and a sibling outside a narrow whose tag
the position still maps. Preparing them all at once is what keeps this state a
property of the compiled read rather than of the rows that arrived — a level
derived on first reach would be a lazy, data-keyed cache whose cost no
preparation figure reports and whose contents depend on which rows came back.

The reference direction is one-way and load-bearing. A prepared read holds its
levels, which hold the catalog's layouts and the statement's contracts; nothing
prepared holds a row, a builder, or a Page, so a read's prepared state outlives
its rows without retaining any of them and one execution's Page cannot be
reached from the next one's preparation.

This scope may not import `m-sql`, so what a compiled read publishes is read
structurally: :class:`_CompiledRead` is the ordinal-access interface a prepared
read needs. Provider rows cross it unchanged, so the object lane allocates no
per-row lookup wrapper or mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from parallax.core.base import UnknownFamilyTag
from parallax.core.db_port import Row
from parallax.core.document_codec import DocumentFinding
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectMetadata
from parallax.snapshot.materialize._convert import (
    AttributeReadContract,
    LevelContext,
    convert_deferred,
)
from parallax.snapshot.materialize._page import ABSENT, PageBuilder
from parallax.snapshot.materialize._views import SourceLevel

__all__ = ["PreparedRead", "bind"]


class _CompiledRead(Protocol):
    """What a prepared read reads off the compiled read it is bound to."""

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]: ...

    @property
    def projected_documents(self) -> tuple[ValueObjectMetadata, ...]: ...

    def attribute_reads(self, entity: EntityIdentity) -> tuple[AttributeReadContract, ...]: ...

    def row_header(
        self, row: Row | Mapping[str, object]
    ) -> tuple[
        EntityIdentity,
        str | None,
        UnknownFamilyTag | None,
        object | None,
        object | None,
    ]: ...

    def row_identity(
        self, row: Row | Mapping[str, object]
    ) -> tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]: ...

    def raw_member_of(
        self, row: Row | Mapping[str, object], resolved: EntityIdentity, key: str
    ) -> object: ...

    def classify_member_of(
        self, row: Row | Mapping[str, object], resolved: EntityIdentity, key: str
    ) -> tuple[object, tuple[DocumentFinding, ...]]: ...


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
        witness = tuple(
            self._raw_driver(
                row,
                resolved,
                attribute.storage.name
                if not level.attribute_reads
                else level.attribute_reads[position].result_key,
            )
            for position, attribute in enumerate(level.layout.attributes)
        ) + tuple(
            self._raw_driver(row, resolved, occurrence.storage.name, default=None)
            if projected
            else ABSENT
            for occurrence, projected in zip(
                level.layout.occurrences, level.projected_by_position, strict=True
            )
        )
        ref = convert_deferred(
            witness,
            level,
            builder,
            source=source,
            load=lambda: self._driver_payload(row, resolved, level, witness),
            unknown_family_tag=unknown,
            correlation_members=correlation_members,
        )
        return ref, resolved, document, variant

    def _driver_payload(
        self,
        row: Row | Mapping[str, object],
        resolved: EntityIdentity,
        level: LevelContext,
        witness: tuple[object, ...],
    ) -> tuple[tuple[object, ...], tuple[DocumentFinding, ...], frozenset[str]]:
        values = list(witness)
        findings: list[DocumentFinding] = []
        classified: set[str] = set()
        members = (*level.layout.attributes, *level.layout.occurrences)
        for position, member in enumerate(members):
            key = (
                level.attribute_reads[position].result_key
                if position < len(level.attribute_reads)
                else member.storage.name
            )
            try:
                value, member_findings = self._compiled.classify_member_of(row, resolved, key)
            except KeyError:
                continue
            values[position] = value
            findings.extend(member_findings)
            classified.add(key)
        return tuple(values), tuple(findings), frozenset(classified)

    def _raw_driver(
        self,
        row: Row | Mapping[str, object],
        resolved: EntityIdentity,
        key: str,
        *,
        default: object = ABSENT,
    ) -> object:
        try:
            return self._compiled.raw_member_of(row, resolved, key)
        except KeyError:
            return default


def bind(model: CatalogedModel, compiled: _CompiledRead) -> PreparedRead:
    """Prepare ``compiled`` against ``model``: one level per Entity it can resolve.

    Paid once per compiled read, which is where the state belongs — the member
    layouts are the model's and the projected documents and Attribute contracts
    are this statement's, and no row of the read can change either.
    """
    return PreparedRead(
        compiled,
        {
            identity: LevelContext(
                model.layouts.entity(identity),
                compiled.projected_documents,
                compiled.attribute_reads(identity),
            )
            for identity in compiled.resolvable
        },
    )
