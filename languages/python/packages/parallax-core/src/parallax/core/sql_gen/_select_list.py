from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, NamedTuple

from parallax.core.base import JSON, DocumentReadOrdinals, NeutralType
from parallax.core.deep_fetch import ResolvedReadProjection
from parallax.core.dialect import Dialect, RenderedScalarCell, ScalarResult, scalar_result
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import AttributeMetadata, EntityIdentity, ValueObjectMetadata
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._inheritance import (
    CellSource,
    DocumentMemberSource,
    DriverRowSlot,
    EntitySources,
    LiteralRowIdentity,
    MemberSource,
    ProjectedColumn,
    ReadResultContract,
    SingleTableReadPlan,
    TpcsUnionBranchColumn,
    TpcsUnionReadPlan,
    entity_view,
    resolvable_entities,
)
from parallax.core.sql_gen._seek import LoweredTerm
from parallax.core.storage_layout import (
    ColumnContributor,
    InheritanceDiscriminator,
    RelationalDocument,
)

__all__ = ["SelectListBuilder"]


@dataclass(frozen=True, slots=True)
class _Coordinate:
    """The capture cell of one Continuation Order term."""

    alias: str


@dataclass(frozen=True, slots=True)
class _VariantLiteral:
    """A union branch's `familyVariant` subtype-name literal."""


_VARIANT_LITERAL: Final = _VariantLiteral()
_NO_RESIDENTS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})
_VARIANT_ALIAS: Final = "family_variant"

type _Role = ColumnContributor | _Coordinate | _VariantLiteral


class _Cell(NamedTuple):
    """One logical select-list cell as emitted.

    ``alias`` is the name an enclosing select addresses it by, and
    ``publication_key`` the key its value publishes under. A ``document`` cell
    occupies a presence/value pair wherever its list expands pairs, and its
    presence cell is anonymous.
    """

    alias: str
    role: _Role
    document: bool
    publication_key: str
    neutral_type: NeutralType | None
    scalar: ScalarResult | None


class SelectListBuilder:
    """One select list under construction: its SQL, its binds, its physical
    document-read pairs, and what each folded cell carries, emitted together.

    Compilation state: a compiled read retains only the result contract and
    statement it produces, never the builder.
    """

    __slots__ = (
        "_binds",
        "_cells",
        "_dialect",
        "_document_pairs",
        "_document_reads",
        "_parts",
    )

    def __init__(self, dialect: Dialect, *, document_pairs: bool = True) -> None:
        self._dialect = dialect
        self._document_pairs = document_pairs
        self._parts: list[str] = []
        self._binds: list[object] = []
        self._cells: list[_Cell] = []
        self._document_reads: list[DocumentReadOrdinals] = []

    @property
    def sql(self) -> str:
        return ", ".join(self._parts)

    @property
    def binds(self) -> tuple[object, ...]:
        """The emitted cells' binds, in select-list order."""
        return tuple(self._binds)

    @property
    def document_reads(self) -> tuple[DocumentReadOrdinals, ...]:
        """The physical presence/value ordinals of every emitted document pair."""
        return tuple(self._document_reads)

    def emit(self, column: ProjectedColumn, *, table_alias: str) -> None:
        """One planned single-Table column against ``table_alias``."""
        if column.document:
            self._emit_document(
                *self._dialect.render_document_pair(
                    self._dialect.qualified(table_alias, column.column)
                ),
                _Cell(column.column, column.contributor, True, column.column, None, None),
            )
        elif column.type is None:
            self._append(
                self._dialect.qualified(table_alias, column.column),
                _Cell(column.column, column.contributor, False, column.column, None, None),
            )
        else:
            self._emit_scalar(
                self._dialect.render_scalar(table_alias, column.column, column.type),
                column.contributor,
                column.type,
            )

    def emit_branch(self, column: TpcsUnionBranchColumn, *, table_alias: str) -> None:
        """One union contributor as one table-per-concrete-subtype branch
        selects it: its own Column where the branch owns one, and the typed
        `NULL` placeholder its siblings pad with otherwise, both under the
        union's allocated alias."""
        alias = column.result_alias
        if column.document:
            cell = _Cell(alias, column.contributor, True, column.column, None, None)
            if not column.owned:
                placeholder = f"cast(null as {self._dialect.null_cast(JSON, None)}) {alias}"
                self._emit_document("false", placeholder, cell)
                return
            presence, document = self._dialect.render_document_pair(
                self._dialect.qualified(table_alias, column.column)
            )
            self._emit_document(
                presence, document if alias == column.column else f"{document} {alias}", cell
            )
            return
        if column.type is None:  # pragma: no cover - formation types every scalar contributor
            raise SqlGenError("a table-per-concrete-subtype scalar contributor has no type")
        if column.owned:
            self._emit_scalar(
                self._dialect.render_scalar(
                    table_alias, column.column, column.type, output_alias=alias
                ),
                column.contributor,
                column.type,
            )
            return
        result = scalar_result(column.column, column.type)
        cast_type = self._dialect.null_cast(column.type, column.max_length)
        self._append(
            f"cast(null as {cast_type}) {alias}",
            _Cell(alias, column.contributor, False, result.publication_key, column.type, result),
        )

    def emit_variant(self, variant: str) -> None:
        """A union branch's `familyVariant` literal.

        The settled TPH/TPCS asymmetry: a union projects the variant NAME per
        branch directly, since there is no discriminator slot to derive it from.
        """
        self._append(
            f"'{variant}' {_VARIANT_ALIAS}",
            _Cell(_VARIANT_ALIAS, _VARIANT_LITERAL, False, _VARIANT_ALIAS, None, None),
        )

    def emit_coordinate(self, term: LoweredTerm, expression: str) -> None:
        """The hidden cell capturing ``term``'s coordinate as ``expression``,
        which is what the statement orders by."""
        role = _Coordinate(term.alias)
        self._append(
            f"{expression} {term.alias}", _Cell(term.alias, role, False, term.alias, None, None)
        )

    def select_through(self, alias: str, *, document_pairs: bool = True) -> SelectListBuilder:
        """An enclosing select over this list as the derived table ``alias``.

        Each cell is referenced by the name this list gave it, so nothing is
        rendered or encoded again; a document cell becomes a presence/value
        pair exactly where the enclosing list expands pairs.
        """
        outer = SelectListBuilder(self._dialect, document_pairs=document_pairs)
        for cell in self._cells:
            reference = self._dialect.qualified(alias, cell.alias)
            if cell.document:
                outer._emit_document(*self._dialect.render_document_pair(reference), cell)
            else:
                outer._append(reference, cell)
        return outer

    def require_agreement(self, other: SelectListBuilder) -> None:
        """Refuse ``other`` unless it yields the same cells as this list.

        Two branches of one union, or the ordinary and NULL-tail arms of one
        read, must name, carry, and encode every cell alike; a typed `NULL`
        placeholder answers for its contributor exactly as an owner does.
        """
        if len(other._cells) != len(self._cells) or other.document_reads != self.document_reads:
            raise SqlGenError("two select lists of one read disagree on their cells")
        for mine, theirs in zip(self._cells, other._cells, strict=True):
            if mine != theirs:
                raise SqlGenError(
                    f"two select lists of one read disagree on the cell {mine.alias!r}"
                )

    def scalar_cells(self) -> Mapping[ColumnContributor, tuple[str, ScalarResult]]:
        """Each scalar cell's alias and scalar facts, by the contributor it
        carries; a select over this list names a member by that alias."""
        return {
            cell.role: (cell.alias, cell.scalar)
            for cell in self._cells
            if cell.scalar is not None and not isinstance(cell.role, (_Coordinate, _VariantLiteral))
        }

    def selected_scalar(self, contributor: ColumnContributor) -> tuple[str, NeutralType]:
        """The alias and type of the scalar cell carrying ``contributor``."""
        for cell in self._cells:
            if cell.role == contributor and cell.neutral_type is not None:
                return cell.alias, cell.neutral_type
        raise SqlGenError(f"{contributor} has no scalar cell in the read's select list")

    def result_contract(
        self,
        shape: SingleTableReadPlan | TpcsUnionReadPlan,
        facet: InheritanceFacet,
        projection: ResolvedReadProjection,
        coordinates: Sequence[LoweredTerm],
    ) -> ReadResultContract:
        """The one result contract of a read whose final select list this is.

        Every carrier the plan requires is located among the emitted cells:
        the row identity's, the shared document, one capture cell per term of
        ``coordinates``, and a source for every member the plan fetches for
        each concrete of the position. A requirement no cell meets refuses the
        read here, as do two cells under one addressable name and two members
        one Entity would publish under one key.
        """
        identity_ordinal: int | None = None
        shared_ordinal: int | None = None
        coordinate_ordinals: list[int] = []
        by_contributor: dict[ColumnContributor, int] = {}
        addressed: set[str] = set()
        slots: list[DriverRowSlot | None] = []
        padded: dict[str, int] = {}
        encoded: set[int] = set()
        # A union read narrowing each row to its own branch pads no sibling.
        narrow = isinstance(shape.row_identity, LiteralRowIdentity) and (
            shape.row_identity.narrow_to_owned
        )
        for ordinal, cell in enumerate(self._cells):
            if cell.alias in addressed:
                raise ValueError(f"duplicate result key {cell.alias!r}")
            addressed.add(cell.alias)
            role = cell.role
            if isinstance(role, _Coordinate):
                coordinate_ordinals.append(ordinal)
            elif isinstance(role, (_VariantLiteral, InheritanceDiscriminator)):
                identity_ordinal = ordinal
            elif isinstance(role, RelationalDocument):
                shared_ordinal = ordinal
            else:
                by_contributor[role] = ordinal
                slots.append(_slot(cell, ordinal, narrow=narrow, padded=padded, encoded=encoded))
                continue
            slots.append(None)
        if [self._cells[ordinal].alias for ordinal in coordinate_ordinals] != [
            term.alias for term in coordinates
        ]:
            raise SqlGenError("the read's select list does not capture its ordering terms")
        position = frozenset(shape.concrete_types)
        sources = _SourceFactory(by_contributor, self._cells, shared_ordinal, shape, projection)
        entity_sources: list[EntitySources] = []
        for entity in resolvable_entities(shape.concrete_types, shape.row_identity):
            selection = entity_view(facet, entity).member_selection
            entry = EntitySources(
                entity,
                selection,
                sources.of(entity, selection.bindings, planned=entity in position),
            )
            if encoded:
                _refuse_colliding_publication(entry, self._cells, padded)
            entity_sources.append(entry)
        return ReadResultContract(
            shape.row_identity,
            shape.shared_document,
            shape.direct_documents,
            tuple(entity_sources),
            tuple(slots),
            identity_ordinal,
            shared_ordinal,
            tuple(coordinate_ordinals),
        )

    def _emit_scalar(
        self,
        rendered: RenderedScalarCell,
        contributor: ColumnContributor,
        neutral_type: NeutralType,
    ) -> None:
        self._binds.extend(rendered.binds)
        self._append(
            rendered.select_sql,
            _Cell(
                rendered.output_alias,
                contributor,
                False,
                rendered.scalar_result.publication_key,
                neutral_type,
                rendered.scalar_result,
            ),
        )

    def _emit_document(self, presence: str, document: str, cell: _Cell) -> None:
        if not self._document_pairs:
            self._append(document, cell)
            return
        physical = len(self._parts)
        self._document_reads.append((physical, physical + 1))
        self._parts.extend((presence, document))
        self._cells.append(cell)

    def _append(self, sql: str, cell: _Cell) -> None:
        self._parts.append(sql)
        self._cells.append(cell)


def _slot(
    cell: _Cell, ordinal: int, *, narrow: bool, padded: dict[str, int], encoded: set[int]
) -> DriverRowSlot | None:
    """Value cell ``ordinal``'s publication facts, recording its padding key in
    ``padded`` and its ordinal in ``encoded`` where they apply.

    A cell keeps its place in every resolved row's flat publication where its
    name is its own publication key, unless the read narrows each row to what
    its own branch owns; a renamed or encoded union alias publishes only for
    its owners.
    """
    scalar = cell.scalar
    if scalar is not None and scalar.encoded:
        encoded.add(ordinal)
    if narrow or cell.alias != cell.publication_key:
        return None if scalar is None else DriverRowSlot(scalar, None)
    padded[cell.publication_key] = ordinal
    return DriverRowSlot(scalar, cell.publication_key)


class _SourceFactory:
    """Member sources of one contract, sharing one immutable record per cell
    and per document location."""

    __slots__ = (
        "_by_contributor",
        "_cell_sources",
        "_cells",
        "_documents",
        "_projection",
        "_shape",
        "_shared_ordinal",
    )

    def __init__(
        self,
        by_contributor: Mapping[ColumnContributor, int],
        cells: Sequence[_Cell],
        shared_ordinal: int | None,
        shape: SingleTableReadPlan | TpcsUnionReadPlan,
        projection: ResolvedReadProjection,
    ) -> None:
        self._by_contributor = by_contributor
        self._cells = cells
        self._shared_ordinal = shared_ordinal
        self._shape = shape
        self._projection = projection
        self._cell_sources: dict[int, CellSource] = {}
        self._documents: dict[str, DocumentMemberSource] = {}

    def of(
        self,
        entity: EntityIdentity,
        members: Sequence[AttributeMetadata | ValueObjectMetadata],
        *,
        planned: bool,
    ) -> tuple[MemberSource | None, ...]:
        """``entity``'s members' sources: for a ``planned`` concrete of the
        position, each fetched member's own cell or its shared-document
        location, and for an Entity outside the position each cell carrying
        one of its own members under that member's own spelling."""
        if not planned:
            return tuple(self._unplanned(member) for member in members)
        shared = self._shape.shared_document
        entry = None if shared is None else shared.by_entity.get(entity)
        residents = _NO_RESIDENTS if entry is None else entry.member_paths
        return tuple(self._planned(entity, member, residents) for member in members)

    def _unplanned(self, member: AttributeMetadata | ValueObjectMetadata) -> CellSource | None:
        ordinal = self._by_contributor.get(member.identity)
        if ordinal is None:
            return None
        scalar = self._cells[ordinal].scalar
        return None if scalar is not None and scalar.encoded else self._cell(ordinal)

    def _planned(
        self,
        entity: EntityIdentity,
        member: AttributeMetadata | ValueObjectMetadata,
        residents: Mapping[str, tuple[str, ...]],
    ) -> MemberSource | None:
        # A member with a Column of its own contributes the cell it is read
        # from; one placed in the shared Structured Column contributes none and
        # is read where the planned fan-out locates it.
        ordinal = self._by_contributor.get(member.identity)
        if ordinal is not None:
            return self._cell(ordinal)
        path = residents.get(member.storage.name)
        if path is not None:
            return self._document(path[0])
        if isinstance(member, AttributeMetadata) or self._projection.includes_value_object(
            member.identity
        ):
            raise SqlGenError(
                f"{entity.canonical}: the read's select list carries no source for "
                f"the fetched member {member.storage.name!r}"
            )
        return None

    def _cell(self, ordinal: int) -> CellSource:
        source = self._cell_sources.get(ordinal)
        if source is None:
            source = self._cell_sources[ordinal] = CellSource(ordinal)
        return source

    def _document(self, member_name: str) -> DocumentMemberSource:
        if self._shared_ordinal is None:
            raise SqlGenError("a document resident is read without its shared document")
        source = self._documents.get(member_name)
        if source is None:
            source = self._documents[member_name] = DocumentMemberSource(
                self._shared_ordinal, member_name
            )
        return source


def _refuse_colliding_publication(
    entry: EntitySources, cells: Sequence[_Cell], padded: Mapping[str, int]
) -> None:
    """Refuse a read whose rows of ``entry.entity`` would publish two cells
    under one key: an encoded member's key beside another cell spelling it,
    whether that cell is the Entity's own or a sibling's ``padded`` one. Only
    an encoded key can meet another cell's, since every other key is its own
    cell's spelling and the union allocates aliases outside every spelling."""
    claims = [
        (
            scalar.publication_key
            if (scalar := cells[source.ordinal].scalar) is not None and scalar.encoded
            else member.storage.name,
            source.ordinal,
        )
        for member, source in zip(entry.selection.bindings, entry.sources, strict=True)
        if isinstance(source, CellSource)
    ]
    own = {ordinal for _key, ordinal in claims}
    published: set[str] = set()
    for key, _ordinal in claims:
        if key in published or padded.get(key, _ordinal) not in own:
            raise ValueError(f"duplicate result key {key!r}")
        published.add(key)
