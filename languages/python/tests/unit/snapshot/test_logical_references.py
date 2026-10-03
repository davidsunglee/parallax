from __future__ import annotations

import datetime as dt

import pytest

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    DomainModel,
    Entity,
    Rel,
    attr,
    deep_fetch,
    rel,
)
from parallax.core.entity import model_of
from parallax.core.metamodel import EntityIdentity
from parallax.core.object_query import validate_object_query
from parallax.core.object_query.serde import deserialize
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._read import attach_children
from parallax.snapshot.materialize import RootView, SnapshotConsistencyError
from parallax.snapshot.materialize._page import page_rows, release_page_rows, root_last_uses
from tests._support.tpcs_inverse_models import INVERSE_MODEL, LINK_ROW, PARENT_ROWS
from tests.unit.snapshot._snapshot_page_support import PageFixture


def _forward_plan(target: str, relationship: str) -> deep_fetch.ObjectQueryPlan:
    meta = model_of(INVERSE_MODEL)
    query = deserialize(
        {
            "target": target,
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": relationship}]}],
        }
    )
    entity = meta.entity(query.target)
    assert entity is not None
    return deep_fetch.plan(
        validate_object_query(entity, query, meta),
        meta,
        projection=deep_fetch.ReadProjectionRequest("all", True),
    )


@pytest.mark.parametrize("to_one", [False, True], ids=["to-many", "to-one"])
@pytest.mark.parametrize("reverse", [False, True])
def test_forward_fanback_preserves_same_logical_concrete_witnesses(
    to_one: bool, reverse: bool
) -> None:
    target = "InverseLink" if to_one else "InverseOwner"
    relationship = f"{target}.{'parent' if to_one else 'parents'}"
    meta = model_of(INVERSE_MODEL)
    plan = _forward_plan(target, relationship)
    (step,) = plan.fetch_steps
    assert isinstance(step, deep_fetch.QueryFetchStep)
    fixture = PageFixture(INVERSE_MODEL, relationship)
    root = fixture.node(target, LINK_ROW if to_one else {"id": 10})
    rows = list(reversed(PARENT_ROWS)) if reverse else PARENT_ROWS
    children = tuple(fixture.node(str(row["family_variant"]), row) for row in rows)
    attach_children(fixture.builder, meta, plan.includes, step, (root,), children)
    with pytest.raises(SnapshotConsistencyError) as conflict:
        RootView(fixture.page(root))
    assert conflict.value.code == "snapshot-projection-conflict"
    assert conflict.value.coordinates == ()
    assert conflict.value.occurrences == ((0, 1), (0, 2))


def test_deferred_inverse_reuses_the_canonical_grouped_claim_and_overwritten_views() -> None:
    fixture = PageFixture(
        INVERSE_MODEL, "InverseOwner.parents", "InverseParent.links", "InverseLink.parent"
    )
    owner = fixture.node("InverseOwner", {"id": 10})
    first = fixture.node("InverseAlpha", PARENT_ROWS[0])
    duplicate = fixture.node("InverseAlpha", PARENT_ROWS[0])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(owner, "InverseOwner.parents", (first,))
    fixture.attach(owner, "InverseOwner.parents", (duplicate,))
    fixture.attach(first, "InverseParent.links", (link,))
    fixture.attach(duplicate, "InverseParent.links", (link,))
    reference = fixture.builder.reference(
        EntityIdentity(None, "InverseParent"), 1, frozenset({EntityIdentity(None, "InverseAlpha")})
    )
    assert reference is not None
    fixture.builder.write_view(link, fixture.view_key("InverseLink.parent"), reference)
    root = RootView(fixture.page(owner))
    assert [entity.name for entity in root.order] == ["InverseOwner", "InverseAlpha", "InverseLink"]
    slot = root.view_layout(2).index_of[fixture.view_key("InverseLink.parent")]
    assert root.view(2, slot) == 1


@pytest.mark.parametrize("to_many", [False, True])
def test_an_inverse_neither_reaches_an_unrelated_root_nor_extends_its_lifetime(
    to_many: bool,
) -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", "InverseLink.parent")
    alpha = fixture.node("InverseAlpha", PARENT_ROWS[0])
    beta = fixture.node("InverseBeta", PARENT_ROWS[1])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(alpha, "InverseParent.links", (link,))
    fixture.attach(beta, "InverseParent.links", (link,))
    reference = fixture.builder.reference(
        EntityIdentity(None, "InverseParent"),
        1,
        frozenset({EntityIdentity(None, "InverseAlpha"), EntityIdentity(None, "InverseBeta")}),
        to_many=to_many,
    )
    assert reference is not None
    fixture.builder.write_view(link, fixture.view_key("InverseLink.parent"), reference)
    page = fixture.page(alpha, beta)
    rows = page_rows(page)
    last_uses = root_last_uses(page)
    assert tuple(last_uses[0]) == (1, 1, 1)
    first = RootView(page, 0)
    slot = first.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert first.view(1, slot) == ((0,) if to_many else 0)
    first.release_finished_page_rows(0, last_uses)
    assert rows.view_rows[link]
    second = RootView(page, 1)
    assert second.order[0].name == "InverseBeta"
    assert second.view(1, slot) == ((0,) if to_many else 0)
    second.release_finished_page_rows(1, last_uses)
    assert all(not row for row in rows.member_rows)
    assert not rows.view_rows[beta] and not rows.view_rows[link]
    assert all(rows.judged_states.singleton(logical) is None for logical in range(len(rows.claims)))
    release_page_rows(page)
    assert not rows.view_rows


def test_to_one_selection_among_distinct_logical_targets_remains_unchanged() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseLink.parent")
    link = fixture.node("InverseLink", LINK_ROW)
    first = fixture.node("InverseAlpha", PARENT_ROWS[0])
    other = fixture.node("InverseBeta", {**PARENT_ROWS[1], "id": 2})
    fixture.builder.write_to_one(link, fixture.view_key("InverseLink.parent"), (first, other))
    root = RootView(fixture.page(link))
    assert [entity.name for entity in root.order] == ["InverseLink", "InverseAlpha"]


class TemporalParent(Bitemporal, table="temporal_parent"):
    id: Attr[int] = attr(primary_key=True)
    links: Rel[tuple[TemporalLink, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "parent_id"))


class TemporalLink(Entity, table="temporal_link"):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int]
    parent: Rel[TemporalParent | None] = rel(reverse_of="links")


def test_inverse_lookup_keeps_coordinate_distinct_claims_until_root_local_resolution() -> None:
    fixture = PageFixture(
        DomainModel(TemporalParent, TemporalLink), "TemporalParent.links", "TemporalLink.parent"
    )
    first_start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    second_start = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    roots = tuple(
        fixture.node(
            "TemporalParent",
            {
                "id": 1,
                "from_z": start,
                "thru_z": dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
                "in_z": first_start,
                "out_z": dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
            },
        )
        for start in (first_start, second_start)
    )
    link = fixture.node("TemporalLink", {"id": 11, "parent_id": 1})
    for root in roots:
        fixture.attach(root, "TemporalParent.links", (link,))
    identity = EntityIdentity(None, "TemporalParent")
    reference = fixture.builder.reference(identity, 1, frozenset({identity}))
    assert reference is not None and len(reference.logicals) == 2
    fixture.builder.write_view(link, fixture.view_key("TemporalLink.parent"), reference)
    page = fixture.page(*roots, pin=Pin(valid_time=second_start, tx_time=first_start))
    assert page_rows(page).logical_ids[roots[0]] != page_rows(page).logical_ids[roots[1]]
    for position in (0, 1):
        root = RootView(page, position)
        slot = root.view_layout(1).index_of[fixture.view_key("TemporalLink.parent")]
        assert root.view(1, slot) == 0
