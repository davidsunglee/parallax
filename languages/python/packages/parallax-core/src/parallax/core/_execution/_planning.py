from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core import batch_write, opt_lock
from parallax.core._execution._concurrency import CONCURRENCY
from parallax.core._execution._keyed_sql import collapse_group_key
from parallax.core._execution._publication import ModelSelection, check_edition, select_model
from parallax.core._execution._unit_work.preparation import WritePreparation
from parallax.core._execution._unit_work.strategy import NO_AUDIT
from parallax.core._execution._unit_work.write_planner import WritePlanner
from parallax.core.entity import DomainModel, EntityGraphConstruction
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.read_delivery._page import ABSENT
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan.managed_row import ManagedRow

__all__ = ["build_write_planner", "build_write_preparation", "prepare_model"]


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
    if classes is None:
        construction = None
        positional = None
    else:
        construction = EntityGraphConstruction(catalog, classes)
        positional = _proven_classes(classes.by_identity, construction)
    return select_model(
        model,
        edition=edition,
        catalog=catalog,
        classes=classes,
        construction=construction,
        preparation=build_write_preparation(catalog.meta, positional=positional),
        planner=build_write_planner(catalog.meta),
        evidence_policy_for=opt_lock.view(catalog.meta).required_key,
    )


def _proven_classes(
    classes: Mapping[EntityIdentity, type], construction: EntityGraphConstruction
) -> dict[EntityIdentity, type]:
    """Each Entity's class whose member order ``construction`` proved equal to
    its Entity's own."""
    return {
        identity: cls for identity, cls in classes.items() if construction.proves(cls, identity)
    }


@dataclass(frozen=True, slots=True)
class _BatchingAdapter:
    """``m-batch-write``'s collapse-eligibility policy plus the layout-derived
    batch key, structurally satisfying ``BatchingStrategy``."""

    def collapses(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        mutation: str,
        rows: Sequence[ManagedRow],
    ) -> bool:
        return batch_write.collapses(model, entity, mutation, [_by_name(row) for row in rows])

    def batch_key(
        self, model: Metamodel, entity: EntityMetadata, mutation: str, row: ManagedRow
    ) -> object:
        return collapse_group_key(model, entity, mutation, row)


def _by_name(row: ManagedRow) -> dict[str, object]:
    members = row.selection.members.shape.members
    return {members[position].name: cell for position, cell in row.stated_cells()}


def build_write_preparation(
    model: Metamodel, *, positional: Mapping[EntityIdentity, type] | None = None
) -> WritePreparation:
    """The one ``WritePreparation`` every write of ``model`` is admitted
    against, its rows marking an omitted member as accepted Entity State does.

    ``positional`` names the Entity Classes whose correspondence with their
    Entity's member order the caller has proven, so their instances are read
    by position.

    Called once per prepared model selection (:func:`prepare_model`) and
    identically by the conformance engine's case lanes, so both lanes judge
    and represent a write through the same preparation.
    """
    return WritePreparation(model, absent=ABSENT, positional=positional)


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
