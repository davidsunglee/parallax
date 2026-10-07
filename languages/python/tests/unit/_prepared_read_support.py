"""Real compiled reads, bound as a read plan binds them, for unit suites that
convert driver rows without a database.

Conversion is graded through the same ``bind`` plus ``ReadRowConverter.convert_row``
boundary every production read crosses. These helpers only compile and bind;
witness extraction and stored-value judgment stay in production code.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel, entity_by_name
from parallax.core.object_query import AsOf, TemporalSelection
from parallax.core.object_query._nodes import TemporalDimension
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.temporal_read import view as temporal_view
from tests._support.sql import compile_read

__all__ = ["bound_read", "compiled_read"]


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
                oa.All(),
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
        held = _BOUND[address] = (
            model,
            bind(
                CatalogedModel(model),
                compiled_read(model, entity),
                correlation_members=correlation_members,
            ),
        )
    return held[1]
