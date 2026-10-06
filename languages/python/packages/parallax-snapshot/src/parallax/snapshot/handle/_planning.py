from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import batch_write
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.unit_work import NO_AUDIT, WritePlanner
from parallax.snapshot.handle._concurrency import CONCURRENCY
from parallax.snapshot.handle._keyed_sql import collapse_group_key

__all__ = ["build_write_planner"]


@dataclass(frozen=True, slots=True)
class _BatchingAdapter:
    """``m-batch-write``'s collapse-eligibility policy plus the layout-derived
    physical grouping key, structurally satisfying ``BatchingStrategy``."""

    def collapses(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        mutation: str,
        rows: Sequence[Mapping[str, object]],
    ) -> bool:
        return batch_write.collapses(model, entity, mutation, rows)

    def group_key(
        self, model: Metamodel, entity: EntityMetadata, mutation: str, row: Mapping[str, object]
    ) -> object:
        return collapse_group_key(model, entity, mutation, row)


def build_write_planner(model: Metamodel) -> WritePlanner:
    """One ``WritePlanner`` for ``model``, wired with production strategies.

    Called once at the composition root (:mod:`~parallax.snapshot.handle.
    _database`) and identically by the conformance engine's compile lane, so
    the two lanes plan through the same deterministic computation.
    """
    return WritePlanner(
        model,
        batching=_BatchingAdapter(),
        concurrency=CONCURRENCY,
        audit=NO_AUDIT,
    )
