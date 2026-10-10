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
from parallax.core.object_query import validate_object_query
from parallax.core.object_query.serde import deserialize
from parallax.core.read_delivery._fetch import attach_children
from parallax.core.read_delivery._page import Page, page_rows, release_page_rows, root_last_uses
from parallax.core.temporal_read import Pin
from parallax.snapshot import SnapshotConsistencyError
from parallax.snapshot._publication._root import RootView
from tests._support.tpcs_inverse_models import INVERSE_MODEL, LINK_ROW, PARENT_ROWS
from tests.unit.snapshot._snapshot_page_support import PageFixture


def _forward_plan(target: str, relationship: str) -> deep_fetch.ObjectQueryPlan:
    meta = model_of(INVERSE_MODEL)
    query = deserialize(
        {
            "target": target,
            "predicate": {"true": {}},
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


_PARENT_KEY = "InverseLink.parentId"
_BOTH_PARENTS = {"InverseLink.parent": ("InverseAlpha", "InverseBeta")}


def test_deferred_inverse_reuses_the_canonical_grouped_claim_and_overwritten_views() -> None:
    fixture = PageFixture(
        INVERSE_MODEL,
        "InverseOwner.parents",
        "InverseParent.links",
        references={"InverseLink.parent": ("InverseAlpha",)},
    )
    owner = fixture.node("InverseOwner", {"id": 10})
    first = fixture.node("InverseAlpha", PARENT_ROWS[0])
    duplicate = fixture.node("InverseAlpha", PARENT_ROWS[0])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(owner, "InverseOwner.parents", (first,))
    fixture.attach(owner, "InverseOwner.parents", (duplicate,))
    fixture.attach(first, "InverseParent.links", (link,))
    fixture.attach(duplicate, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    root = RootView(fixture.page(owner))
    assert [entity.name for entity in root.order] == ["InverseOwner", "InverseAlpha", "InverseLink"]
    slot = root.view_layout(2).index_of[fixture.view_key("InverseLink.parent")]
    assert root.view(2, slot) == 1


def test_an_inverse_neither_reaches_an_unrelated_root_nor_extends_its_lifetime() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    alpha = fixture.node("InverseAlpha", PARENT_ROWS[0])
    beta = fixture.node("InverseBeta", PARENT_ROWS[1])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(alpha, "InverseParent.links", (link,))
    fixture.attach(beta, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    page = fixture.page(alpha, beta)
    rows = page_rows(page)
    last_uses = root_last_uses(page)
    assert tuple(last_uses[0]) == (1, 1, 1)
    first = RootView(page, 0)
    slot = first.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert first.view(1, slot) == 0
    first.release_finished_page_rows(0, last_uses)
    assert rows.view_rows[link]
    second = RootView(page, 1)
    assert second.order[0].name == "InverseBeta"
    assert second.view(1, slot) == 0
    second.release_finished_page_rows(1, last_uses)
    assert all(not row for row in rows.member_rows)
    assert not rows.view_rows[beta] and not rows.view_rows[link]
    assert all(rows.judged_states.singleton(logical) is None for logical in range(len(rows.claims)))
    release_page_rows(page)
    assert not rows.view_rows


def test_a_later_root_resolves_an_inverse_to_a_released_claim_to_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    other = fixture.node("InverseBeta", {**PARENT_ROWS[1], "id": 2})
    released = fixture.node("InverseAlpha", PARENT_ROWS[0])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(released, "InverseParent.links", (link,))
    fixture.attach(other, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    page = fixture.page(released, other)
    rows = page_rows(page)
    logical = rows.logical_ids[released]
    last_uses = root_last_uses(page)
    first = RootView(page, 0)
    slot = first.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert first.view(1, slot) == 0
    first.release_finished_page_rows(0, last_uses)
    assert rows.claims[logical] == other
    second = RootView(page, 1)
    assert [entity.name for entity in second.order] == ["InverseBeta", "InverseLink"]
    assert second.view(1, slot) is None


def test_an_inverse_to_a_grouped_claim_this_root_never_reached_is_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    other = fixture.node("InverseBeta", {**PARENT_ROWS[1], "id": 2})
    for row in PARENT_ROWS:
        fixture.node(str(row["family_variant"]), row)
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(other, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    root = RootView(fixture.page(other), 0)
    slot = root.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert root.view(1, slot) is None


def test_every_root_of_a_multi_root_view_resolves_its_edges_and_inverse_to_its_own_nodes() -> None:
    fixture = PageFixture(
        INVERSE_MODEL,
        "InverseParent.links",
        references={"InverseLink.parent": ("InverseAlpha",)},
    )
    parents = (
        fixture.node("InverseAlpha", PARENT_ROWS[0]),
        fixture.node("InverseAlpha", PARENT_ROWS[0]),
    )
    link = fixture.node("InverseLink", LINK_ROW)
    for parent in parents:
        fixture.attach(parent, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    root = RootView(fixture.page(*parents), defer_states=True)
    links = root.view_layout(0).index_of[fixture.view_key("InverseParent.links")]
    parent = root.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert root.roots == (0, 2)
    assert [(root.view(node, links), root.view(node + 1, parent)) for node in (0, 2)] == [
        ((1,), 0),
        ((3,), 2),
    ]


def test_an_inverse_resolves_only_to_a_reached_node_its_targets_admit() -> None:
    fixture = PageFixture(
        INVERSE_MODEL, "InverseParent.links", references={"InverseLink.parent": ("InverseBeta",)}
    )
    alpha = fixture.node("InverseAlpha", PARENT_ROWS[0])
    beta = fixture.node("InverseBeta", PARENT_ROWS[1])
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(alpha, "InverseParent.links", (link,))
    fixture.attach(beta, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    page = fixture.page(alpha, beta)
    excluded = RootView(page, 0)
    slot = excluded.view_layout(1).index_of[fixture.view_key("InverseLink.parent")]
    assert excluded.view(1, slot) is None
    assert RootView(page, 1).view(1, slot) == 0


def test_an_inverse_whose_key_is_null_is_loaded_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, references=_BOTH_PARENTS)
    link = fixture.node("InverseLink", {**LINK_ROW, "parent_id": None})
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    root = RootView(fixture.page(link))
    assert (
        root.view(0, root.view_layout(0).index_of[fixture.view_key("InverseLink.parent")]) is None
    )


def test_an_inverse_naming_no_claim_on_the_page_is_refused() -> None:
    fixture = PageFixture(INVERSE_MODEL, references=_BOTH_PARENTS)
    link = fixture.node("InverseLink", LINK_ROW)
    with pytest.raises(ValueError, match="no already-converted"):
        fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)


def test_an_inverse_is_refused_on_a_slot_holding_projections() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseLink.parent")
    fixture.node("InverseAlpha", PARENT_ROWS[0])
    link = fixture.node("InverseLink", LINK_ROW)
    with pytest.raises(ValueError, match="holds projections"):
        fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)


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


_FIRST_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_SECOND_START = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_THIRD_START = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)
_TEMPORAL_PIN = Pin(valid_time=_SECOND_START, tx_time=_FIRST_START)
_TEMPORAL_PARENT = "TemporalLink.parent"


def _temporal_fixture() -> PageFixture:
    return PageFixture(
        DomainModel(TemporalParent, TemporalLink),
        "TemporalParent.links",
        references={_TEMPORAL_PARENT: ("TemporalParent",)},
    )


def _temporal_parent(fixture: PageFixture, start: dt.datetime) -> int:
    """One claim of the single temporal parent key, at ``start``."""
    return fixture.node(
        "TemporalParent",
        {
            "id": 1,
            "from_z": start,
            "thru_z": dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
            "in_z": _FIRST_START,
            "out_z": dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
        },
    )


def _temporal_link(fixture: PageFixture, *parents: int) -> int:
    link = fixture.node("TemporalLink", {"id": 11, "parent_id": 1})
    for parent in parents:
        fixture.attach(parent, "TemporalParent.links", (link,))
    return link


def _reference(fixture: PageFixture, link: int) -> None:
    fixture.attach_reference(link, _TEMPORAL_PARENT, "TemporalParent", "TemporalLink.parentId")


def _coordinate_distinct_parents() -> tuple[PageFixture, tuple[int, ...], int]:
    """Two claims of one temporal parent key at distinct coordinates, both
    attaching one link whose inverse names them both."""
    fixture = _temporal_fixture()
    parents = tuple(_temporal_parent(fixture, start) for start in (_FIRST_START, _SECOND_START))
    link = _temporal_link(fixture, *parents)
    _reference(fixture, link)
    return fixture, parents, link


def _resolved_parent(page: Page, position: int, fixture: PageFixture) -> object:
    root = RootView(page, position)
    link = len(root.order) - 1
    return root.view(link, root.view_layout(link).index_of[fixture.view_key(_TEMPORAL_PARENT)])


def test_inverse_lookup_keeps_coordinate_distinct_claims_until_root_local_resolution() -> None:
    fixture, roots, _link = _coordinate_distinct_parents()
    page = fixture.page(*roots, pin=_TEMPORAL_PIN)
    assert page_rows(page).logical_ids[roots[0]] != page_rows(page).logical_ids[roots[1]]
    for position in (0, 1):
        assert _resolved_parent(page, position, fixture) == 0


def test_every_coordinate_distinct_claim_of_one_key_resolves_its_own_inverse() -> None:
    fixture = _temporal_fixture()
    distinct = tuple(
        _temporal_parent(fixture, start) for start in (_FIRST_START, _SECOND_START, _THIRD_START)
    )
    repeated = _temporal_parent(fixture, _SECOND_START)
    roots = (*distinct, repeated)
    _reference(fixture, _temporal_link(fixture, *roots))
    page = fixture.page(*roots, pin=_TEMPORAL_PIN)
    logical_ids = page_rows(page).logical_ids
    assert len({logical_ids[parent] for parent in distinct}) == len(distinct)
    assert logical_ids[repeated] == logical_ids[distinct[1]]
    for position in range(len(roots)):
        assert _resolved_parent(page, position, fixture) == 0


def test_an_inverse_keeps_the_claims_its_key_held_when_it_was_written() -> None:
    fixture = _temporal_fixture()
    earlier = tuple(_temporal_parent(fixture, start) for start in (_FIRST_START, _SECOND_START))
    link = _temporal_link(fixture, *earlier)
    _reference(fixture, link)
    later = _temporal_parent(fixture, _THIRD_START)
    fixture.attach(later, "TemporalParent.links", (link,))
    page = fixture.page(*earlier, later, pin=_TEMPORAL_PIN)
    assert [_resolved_parent(page, position, fixture) for position in range(3)] == [0, 0, None]


def test_an_inverse_to_coordinate_distinct_claims_this_root_never_reached_is_null() -> None:
    fixture, _parents, link = _coordinate_distinct_parents()
    root = RootView(fixture.page(link, pin=_TEMPORAL_PIN), 0)
    assert root.order[0].name == "TemporalLink"
    assert root.view(0, root.view_layout(0).index_of[fixture.view_key(_TEMPORAL_PARENT)]) is None
