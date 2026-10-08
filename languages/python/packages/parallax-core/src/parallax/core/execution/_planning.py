from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import batch_write, opt_lock
from parallax.core.entity import DomainModel, EntityGraphConstruction, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.execution._concurrency import CONCURRENCY
from parallax.core.execution._keyed_sql import collapse_group_key
from parallax.core.execution._publication import ModelSelection, check_edition, select_model
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.unit_work import NO_AUDIT, WritePlanner
from parallax.core.write_payload import LayoutPayloadPreparer

__all__ = ["build_write_planner", "prepare_model"]


def prepare_model(model: DomainModel, *, edition: str) -> ModelSelection:
    """Prepare one complete immutable model selection without database I/O."""
    check_edition(edition)
    if not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(
            f"prepare_model takes a Domain Model — one composed from Entity Classes, or one a "
            f"descriptor produced — not {model!r}"
        )
    catalog = CatalogedModel(model_of(model))
    classes = class_index(model)
    return select_model(
        model,
        edition=edition,
        catalog=catalog,
        construction=(None if classes is None else EntityGraphConstruction(catalog, classes)),
        codec=EntityRowCodec(catalog),
        planner=build_write_planner(catalog.meta),
        evidence_policy_for=opt_lock.view(catalog.meta).required_key,
    )


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
    """One ``WritePlanner`` for ``model``, wired with production strategies and
    the model's write payload preparer, which every flush it plans is lowered
    through.

    Called once per prepared model selection (:func:`prepare_model`) and
    identically by the conformance engine's compile lane, so the two lanes plan
    and prepare through the same deterministic computation.
    """
    return WritePlanner(
        model,
        batching=_BatchingAdapter(),
        concurrency=CONCURRENCY,
        audit=NO_AUDIT,
        payloads=LayoutPayloadPreparer(model),
    )
