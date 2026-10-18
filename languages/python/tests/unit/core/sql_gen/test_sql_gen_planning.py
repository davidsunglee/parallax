"""Statement planning decisions, read without rendering SQL."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from parallax.core import inheritance, storage_layout
from parallax.core import predicate as oa
from parallax.core.metamodel import Metamodel
from parallax.core.predicate._perspective import (
    AtPerspective,
    LatestPerspective,
    TemporalPerspective,
)
from parallax.core.predicate._resolved import (
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRelationship,
)
from parallax.core.sql_gen._planning import (
    plan_relationship_candidates,
    shared_relationship_is_eligible,
)
from parallax.core.temporal_read import Bitemporal
from parallax.core.temporal_read import view as temporal_view
from tests.unit._corpus_model_support import model, target
from tests.unit.core.sql_gen._badge_model_support import badge_model, temporal_badge_model

ORDERS = model("orders")
DOCUMENT = model("document")
POLICY = model("policy")


def _to_many(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    resolved = oa.validate_predicate(target(model, source), oa.Quantifier("any", path), model)
    assert isinstance(resolved, ResolvedQuantifier)
    assert isinstance(resolved.collection, ResolvedRelationship)
    return resolved.collection


def _to_one(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    resolved = oa.validate_predicate(target(model, source), oa.Presence("exists", path), model)
    assert isinstance(resolved, ResolvedPresence)
    assert isinstance(resolved.target, ResolvedRelationship)
    return resolved.target


def _eligible(model: Metamodel, hop: ResolvedRelationship, visibility: TemporalPerspective) -> bool:
    facet, storage = inheritance.view(model), storage_layout.view(model)
    seen = dataclasses.replace(hop, temporal_visibility=visibility)
    candidates = plan_relationship_candidates(
        seen, position=None, meta=model, facet=facet, storage=storage
    )
    return shared_relationship_is_eligible(seen, candidates, facet=facet, storage=storage)


_INSTANT = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _seen(model: Metamodel, name: str, *, valid: bool, tx: bool) -> TemporalPerspective:
    """``name``'s visibility: Latest on each axis flagged, else At one instant."""
    shape = temporal_view(model).shape(target(model, name).identity)
    assert isinstance(shape, Bitemporal)
    return TemporalPerspective(
        valid_time=(
            LatestPerspective(shape.valid_time)
            if valid
            else AtPerspective(shape.valid_time, _INSTANT)
        ),
        transaction_time=(
            LatestPerspective(shape.transaction_time)
            if tx
            else AtPerspective(shape.transaction_time, _INSTANT)
        ),
    )


def test_a_physical_unique_key_the_correlation_fixes_proves_a_non_temporal_hop() -> None:
    hop = _to_one(ORDERS, "OrderItem", "OrderItem.order")
    assert _eligible(ORDERS, hop, TemporalPerspective())


@pytest.mark.parametrize("unique", [True, False])
def test_a_nullable_correlated_column_is_proven_only_by_a_unique_key(unique: bool) -> None:
    family = badge_model(unique=unique)
    hop = _to_one(family, "Holder", "Holder.badge")
    assert _eligible(family, hop, TemporalPerspective()) is unique


@pytest.mark.parametrize(
    ("valid", "tx"),
    [(True, True), (False, True), (True, False), (False, False)],
    ids=["latest-latest", "at-latest", "latest-at", "at-at"],
)
def test_a_temporal_hop_correlated_by_its_logical_key_is_proven_at_any_perspective(
    valid: bool, tx: bool
) -> None:
    # Latest ends complete the physical key; an instant fixes no end, so the
    # logical key and the perspective's one milestone per axis prove it instead.
    hop = _to_one(POLICY, "Claim", "Claim.coverage")
    assert _eligible(POLICY, hop, _seen(POLICY, "Coverage", valid=valid, tx=tx))


@pytest.mark.parametrize("latest", [True, False], ids=["latest", "at"])
def test_a_temporal_hop_off_its_logical_key_needs_a_unique_key_the_correlation_fixes(
    latest: bool,
) -> None:
    for unique in (True, False):
        family = temporal_badge_model(unique=unique)
        hop = _to_one(family, "Holder", "Holder.badge")
        visibility = _seen(family, "Badge", valid=latest, tx=latest)
        assert _eligible(family, hop, visibility) is unique


def test_several_physical_candidates_are_never_proven_unique() -> None:
    hop = _to_many(DOCUMENT, "Folder", "Folder.documents")
    facet, storage = inheritance.view(DOCUMENT), storage_layout.view(DOCUMENT)
    candidates = plan_relationship_candidates(
        hop, position=None, meta=DOCUMENT, facet=facet, storage=storage
    )
    assert len(candidates.branches) > 1
    assert not _eligible(DOCUMENT, hop, TemporalPerspective())
