"""Real compiled reads, bound as a read plan binds them, and the positional rows
they convert, for unit suites that convert driver rows without a database.

Conversion is graded through the same ``bind`` plus ``ReadRowConverter.convert_row``
boundary every production read crosses. These helpers only compile, bind, and lay
cells out by result key; witness extraction and stored-value judgment stay in
production code.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from parallax.core import predicate as oa
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel, entity_by_name
from parallax.core.object_query import AsOf, TemporalSelection
from parallax.core.object_query._nodes import TemporalDimension
from parallax.core.read_delivery._page import PageBuilder, SourceLevel
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.sql_gen._inheritance import ResultContract
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.temporal_read import view as temporal_view
from tests._support.sql import compile_read

__all__ = [
    "bound_cells",
    "bound_read",
    "carrying",
    "compiled_read",
    "convert_cells",
    "result_row",
]


def _latest(
    model: Metamodel, identity: EntityIdentity
) -> dict[TemporalDimension, TemporalSelection]:
    """The as-of-latest selection on every As-Of Axis ``identity``'s family declares."""
    shape = temporal_view(model).shape(identity)
    if isinstance(shape, Bitemporal):
        return {"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")}
    if isinstance(shape, TransactionTimeOnly):
        return {"transaction-time": AsOf("latest")}
    return {}


_COMPILED: dict[tuple[int, str | EntityIdentity], tuple[Metamodel, CompiledRead]] = {}


def compiled_read(model: Metamodel, entity: str | EntityIdentity) -> CompiledRead:
    """The instance-form read of every ``entity`` row as of latest, compiled once
    per model and Entity as a find compiles it. ``entity`` is a bare declared name
    or an exact identity."""
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
                model,
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
) -> ReadRowConverter:
    """:func:`compiled_read` bound against ``model`` routing by
    ``correlation_members``, once per model, Entity, and selection, as a read
    plan's cache keeps one bound read per statement shape."""
    address = (id(model), entity, correlation_members)
    held = _BOUND.get(address)
    if held is None or held[0] is not model:
        compiled = compiled_read(model, entity)
        held = _BOUND[address] = (
            model,
            bind(
                CatalogedModel(model),
                compiled.result_contract,
                compiled.projected_documents,
                correlation_members=correlation_members,
            ),
        )
    return held[1]


def result_row(contract: ResultContract, cells: Mapping[str, object]) -> Row:
    """``cells`` laid out in ``contract``'s result order, as a port returns a
    provider row; a cell ``cells`` leaves unnamed is NULL."""
    unknown = set(cells) - set(contract.result_keys)
    assert not unknown, f"{sorted(unknown)} are not result keys of {contract.result_keys}"
    return tuple(cells.get(key) for key in contract.result_keys)


def carrying(contract: ResultContract, cells: Mapping[str, object]) -> tuple[ResultContract, Row]:
    """``contract`` narrowed to the result cells ``cells`` carries, beside
    ``cells`` as its positional row.

    The narrowed contract keeps ``contract``'s own result keys in their order,
    less any ``cells`` leaves out, then adds any other cell ``cells`` names: a
    statement that projected no cell for a member, or one more for it.
    """
    keys = (
        *(key for key in contract.result_keys if key in cells),
        *(key for key in cells if key not in contract.index_by_key),
    )
    return replace(contract, result_keys=keys), tuple(cells[key] for key in keys)


def bound_cells(
    model: CatalogedModel,
    compiled: CompiledRead,
    cells: Mapping[str, object],
    *,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> tuple[ReadRowConverter, Row]:
    """``compiled``'s contract :func:`carrying` ``cells``, bound against ``model``
    routing by ``correlation_members``, beside its positional row."""
    contract, row = carrying(compiled.result_contract, cells)
    return (
        bind(
            model,
            contract,
            compiled.projected_documents,
            correlation_members=correlation_members,
        ),
        row,
    )


def convert_cells(
    model: CatalogedModel,
    compiled: CompiledRead,
    cells: Mapping[str, object],
    builder: PageBuilder,
    *,
    source: SourceLevel,
    correlation_members: tuple[AttributeIdentity, ...] = (),
) -> int:
    """Convert ``cells`` into ``builder`` through :func:`bound_cells`, answering
    the projection index."""
    prepared, row = bound_cells(model, compiled, cells, correlation_members=correlation_members)
    return prepared.convert_row(row, builder, source=source)[0]
