"""Real compiled reads, bound as a read plan binds them, and the positional rows
they convert, for unit suites that convert driver rows without a database.

Conversion is graded through the same ``bind`` plus ``ReadRowConverter.record_row``
boundary every production read crosses. These helpers only compile, bind, and lay
cells out by the names the compiled statement selects them under, folded as a
database port folds them; witness extraction and stored-value judgment stay in
production code.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Literal

from parallax.core.internal import predicate as oa
from parallax.core.internal.database_binding import DatabaseBinding, ResolvedBinding
from parallax.core.internal.db_port import Row
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    entity_by_name,
)
from parallax.core.internal.object_query import AsOf, TemporalSelection
from parallax.core.internal.object_query._nodes import TemporalDimension
from parallax.core.internal.read_delivery._page import PageBuilder, SourceLevel
from parallax.core.internal.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.internal.sql_gen._compile import CompiledRead
from parallax.core.internal.temporal_read import Bitemporal, TransactionTimeOnly, temporal_facet_of
from tests._support.bindings import TEST_BINDING
from tests._support.document_reads import fold_mapping_rows, folded_names
from tests._support.sql import compile_projected_read, compile_read

__all__ = [
    "bound_cells",
    "bound_read",
    "compiled_read",
    "convert_cells",
    "projected_read",
    "result_row",
    "uncarried",
]


def _latest(
    model: Metamodel, identity: EntityIdentity
) -> dict[TemporalDimension, TemporalSelection]:
    """The as-of-latest selection on every As-Of Axis ``identity``'s family declares."""
    shape = temporal_facet_of(model).shape(identity)
    if isinstance(shape, Bitemporal):
        return {"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")}
    if isinstance(shape, TransactionTimeOnly):
        return {"transaction-time": AsOf("latest")}
    return {}


_COMPILED: dict[tuple[int, str | EntityIdentity], tuple[Metamodel, CompiledRead]] = {}


def compiled_read(
    model: Metamodel, entity: str | EntityIdentity, binding: DatabaseBinding = TEST_BINDING
) -> CompiledRead:
    """The instance-form read of every ``entity`` row as of latest, compiled once
    per model and Entity as a find compiles it, under ``binding``. ``entity`` is
    a bare declared name or an exact identity."""
    address = (id(model), entity)
    held = _COMPILED.get(address)
    if held is None or held[0] is not model:
        metadata = (
            entity_by_name(model, entity) if isinstance(entity, str) else model.entity(entity)
        )
        assert metadata is not None, entity
        held = _COMPILED[address] = (
            model,
            compile_read(
                oa.TrueNode(),
                ResolvedBinding(model, binding),
                POSTGRES,
                metadata,
                temporal=_latest(model, metadata.identity) or None,
                result_form="instance",
            ),
        )
    return held[1]


_BOUND: dict[
    tuple[int, str | EntityIdentity, tuple[AttributeIdentity, ...]],
    tuple[Metamodel, ReadRowConverter],
] = {}


def bound_read(
    model: Metamodel,
    entity: str | EntityIdentity,
    *,
    correlation_members: tuple[AttributeIdentity, ...] = (),
    binding: DatabaseBinding = TEST_BINDING,
) -> ReadRowConverter:
    """:func:`compiled_read` bound against ``model`` routing by
    ``correlation_members``, once per model, Entity, and selection, as a read
    plan's cache keeps one bound read per statement shape."""
    address = (id(model), entity, correlation_members)
    held = _BOUND.get(address)
    if held is None or held[0] is not model:
        compiled = compiled_read(model, entity, binding)
        held = _BOUND[address] = (
            model,
            bind(
                CatalogedModel(model, binding),
                compiled.result_contract,
                compiled.projection,
                correlation_members=correlation_members,
            ),
        )
    return held[1]


def projected_read(
    model: Metamodel, entity: str, value_objects: Literal["none", "all"] | frozenset[str]
) -> CompiledRead:
    """The instance-form read of every ``entity`` row as of latest, fetching only
    ``value_objects``: a read whose rows carry no cell for any other occurrence."""
    metadata = entity_by_name(model, entity)
    assert metadata is not None, entity
    return compile_projected_read(
        oa.TrueNode(),
        model,
        POSTGRES,
        metadata,
        value_objects=value_objects,
        observe_structured_document=False,
        result_form="instance",
        temporal=_latest(model, metadata.identity) or None,
    )


def result_row(compiled: CompiledRead, cells: Mapping[str, object]) -> Row:
    """``cells``, named as ``compiled``'s statement selects them, as the folded
    positional row a port returns.

    Every selected cell is named, and nothing else: a SQL NULL is an explicit
    ``None``, never a cell left out.
    """
    sql = compiled.statement.sql
    names = folded_names(sql, compiled.document_reads)
    assert set(cells) == set(names), (
        f"{sorted(set(names) - set(cells))} unnamed and "
        f"{sorted(set(cells) - set(names))} unselected by {sql!r}"
    )
    (row,) = fold_mapping_rows([cells], compiled.document_reads, sql)
    return row


def uncarried(compiled: CompiledRead, *storage_names: str) -> CompiledRead:
    """``compiled`` with a result contract carrying no source for the members
    stored under ``storage_names``, as a contract leaves a member it does not
    carry; its statement, and so its rows, still select their cells."""
    contract = compiled.result_contract
    entity_sources = tuple(
        replace(
            sources,
            sources=tuple(
                None if member.storage.name in storage_names else source
                for member, source in zip(sources.selection.bindings, sources.sources, strict=True)
            ),
        )
        for sources in contract.entity_sources
    )
    return replace(compiled, result_contract=replace(contract, entity_sources=entity_sources))


def bound_cells(
    model: CatalogedModel,
    compiled: CompiledRead,
    cells: Mapping[str, object],
    *,
    correlation_members: tuple[AttributeIdentity, ...] = (),
    singleton: bool = False,
) -> tuple[ReadRowConverter, Row]:
    """``compiled`` bound against ``model`` routing by ``correlation_members``,
    as a ``singleton`` level's read where its level records each row key once,
    beside ``cells`` as its :func:`result_row`."""
    return (
        bind(
            model,
            compiled.result_contract,
            compiled.projection,
            correlation_members=correlation_members,
            singleton=singleton,
        ),
        result_row(compiled, cells),
    )


def convert_cells(
    model: CatalogedModel,
    compiled: CompiledRead,
    cells: Mapping[str, object],
    builder: PageBuilder,
    *,
    source: SourceLevel,
    correlation_members: tuple[AttributeIdentity, ...] = (),
    singleton: bool = False,
) -> int:
    """Record ``cells`` into ``builder`` through :func:`bound_cells`, answering
    the fetched row index."""
    prepared, row = bound_cells(
        model, compiled, cells, correlation_members=correlation_members, singleton=singleton
    )
    return prepared.record_row(row, builder, source=source)[0]
