from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping

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
    opt_lock,
    rel,
)
from parallax.core.entity import model_of
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.object_query import validate_object_query
from parallax.core.object_query.serde import deserialize
from parallax.core.read_delivery._fetch import attach_children
from parallax.core.read_delivery._page import page_rows, page_schedule
from parallax.core.temporal_read import Pin
from parallax.snapshot import SnapshotConsistencyError
from parallax.snapshot._publication._root import RootView
from tests._support.tpcs_inverse_models import INVERSE_MODEL, LINK_ROW, PARENT_ROWS
from tests.unit._root_publication_support import each_root
from tests.unit.snapshot._snapshot_page_support import PageFixture


def _concrete(row: Mapping[str, object]) -> dict[str, object]:
    """``row``, a union row naming its concrete, as that concrete's own read
    selects it."""
    return {key: value for key, value in row.items() if key != "family_variant"}


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
    children = tuple(fixture.node(str(row["family_variant"]), _concrete(row)) for row in rows)
    attach_children(fixture.builder, meta, plan.includes, step, (root,), children)
    with pytest.raises(SnapshotConsistencyError) as conflict:
        fixture.observed_roots(root)
    assert conflict.value.code == "snapshot-fetched-row-conflict"
    assert conflict.value.coordinates == ()
    assert conflict.value.fetched_rows == ((0, 1), (0, 2))


def _every_family_versioned(_entity: EntityIdentity) -> bool:
    return True


@pytest.fixture
def releasing_at_last_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """Atomic publication schedules every root family as carrying write
    evidence, which defers its states and releases each projection at its last
    use."""

    def every_family_versioned(_model: Metamodel) -> Callable[[EntityIdentity], bool]:
        return _every_family_versioned

    monkeypatch.setattr(opt_lock, "write_evidence", every_family_versioned)


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
    first = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    duplicate = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(owner, "InverseOwner.parents", (first,))
    fixture.attach(owner, "InverseOwner.parents", (duplicate,))
    fixture.attach(first, "InverseParent.links", (link,))
    fixture.attach(duplicate, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    (root,) = fixture.observed_roots(owner)
    assert root.names == ["InverseOwner", "InverseAlpha", "InverseLink"]
    slot = root.view_layouts[2].index_of[fixture.view_key("InverseLink.parent")]
    assert root.view(2, slot) == 1


@pytest.mark.usefixtures("releasing_at_last_use")
def test_an_inverse_neither_reaches_an_unrelated_root_nor_extends_its_lifetime() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    alpha = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    beta = fixture.node("InverseBeta", _concrete(PARENT_ROWS[1]))
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(alpha, "InverseParent.links", (link,))
    fixture.attach(beta, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    page = fixture.page(alpha, beta)
    rows = page_rows(page)
    schedule = page_schedule(page, _every_family_versioned, atomic=True)
    assert schedule.last_uses is not None
    assert tuple(schedule.last_uses[0]) == (1, 1, 1)
    slot = rows.schema.root_view_layout(fixture.layout_for("InverseLink")).index_of[
        fixture.view_key("InverseLink.parent")
    ]

    def after_release(root: RootView, ordinal: int) -> tuple[object, ...]:
        # The pass releases what a root finished with before publishing it.
        if ordinal == 0:
            return (root.view(1, slot), bool(rows.view_rows[link]))
        return (
            root.layout(0).concrete.name,
            root.view(1, slot),
            all(not row for row in rows.member_rows),
            not rows.view_rows[beta] and not rows.view_rows[link],
            all(
                rows.judged_states.singleton(logical) is None
                for logical in range(len(rows.fetched_rows_by_logical_row))
            ),
        )

    assert each_root(page, fixture.model, after_release, atomic=True) == [
        (0, True),
        ("InverseBeta", 0, True, True, True),
    ]
    assert not rows.view_rows


@pytest.mark.usefixtures("releasing_at_last_use")
def test_a_later_root_resolves_an_inverse_to_a_released_claim_to_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    other = fixture.node("InverseBeta", {**_concrete(PARENT_ROWS[1]), "id": 2})
    released = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(released, "InverseParent.links", (link,))
    fixture.attach(other, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    page = fixture.page(released, other)
    rows = page_rows(page)
    logical = rows.logical_rows[released]
    slot = rows.schema.root_view_layout(fixture.layout_for("InverseLink")).index_of[
        fixture.view_key("InverseLink.parent")
    ]

    def after_release(root: RootView, ordinal: int) -> tuple[object, ...]:
        names = [root.layout(node).concrete.name for node in range(len(root))]
        if ordinal == 0:
            return (root.view(1, slot), rows.fetched_rows_by_logical_row[logical])
        return (names, root.view(1, slot))

    assert each_root(page, fixture.model, after_release, atomic=True) == [
        (0, other),
        (["InverseBeta", "InverseLink"], None),
    ]


def test_an_inverse_to_a_grouped_claim_this_root_never_reached_is_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseParent.links", references=_BOTH_PARENTS)
    other = fixture.node("InverseBeta", {**_concrete(PARENT_ROWS[1]), "id": 2})
    for row in PARENT_ROWS:
        fixture.node(str(row["family_variant"]), _concrete(row))
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(other, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    (root,) = fixture.observed_roots(other)
    slot = root.view_layouts[1].index_of[fixture.view_key("InverseLink.parent")]
    assert root.view(1, slot) is None


@pytest.mark.usefixtures("releasing_at_last_use")
def test_every_root_resolves_its_edges_and_inverse_to_its_own_nodes() -> None:
    fixture = PageFixture(
        INVERSE_MODEL,
        "InverseParent.links",
        references={"InverseLink.parent": ("InverseAlpha",)},
    )
    parents = (
        fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0])),
        fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0])),
    )
    link = fixture.node("InverseLink", LINK_ROW)
    for parent in parents:
        fixture.attach(parent, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    roots = fixture.observed_roots(*parents, atomic=True)
    links = roots[0].view_layouts[0].index_of[fixture.view_key("InverseParent.links")]
    parent = roots[0].view_layouts[1].index_of[fixture.view_key("InverseLink.parent")]
    assert [(root.view(0, links), root.view(1, parent)) for root in roots] == [
        ((1,), 0),
        ((1,), 0),
    ]


def test_an_inverse_resolves_only_to_a_reached_node_its_targets_admit() -> None:
    fixture = PageFixture(
        INVERSE_MODEL, "InverseParent.links", references={"InverseLink.parent": ("InverseBeta",)}
    )
    alpha = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    beta = fixture.node("InverseBeta", _concrete(PARENT_ROWS[1]))
    link = fixture.node("InverseLink", LINK_ROW)
    fixture.attach(alpha, "InverseParent.links", (link,))
    fixture.attach(beta, "InverseParent.links", (link,))
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    excluded, admitted = fixture.observed_roots(alpha, beta)
    slot = excluded.view_layouts[1].index_of[fixture.view_key("InverseLink.parent")]
    assert excluded.view(1, slot) is None
    assert admitted.view(1, slot) == 0


def test_an_inverse_whose_key_is_null_is_loaded_null() -> None:
    fixture = PageFixture(INVERSE_MODEL, references=_BOTH_PARENTS)
    link = fixture.node("InverseLink", {**LINK_ROW, "parent_id": None})
    fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)
    (root,) = fixture.observed_roots(link)
    assert (
        root.view(0, root.view_layouts[0].index_of[fixture.view_key("InverseLink.parent")]) is None
    )


def test_an_inverse_naming_no_claim_on_the_page_is_refused() -> None:
    fixture = PageFixture(INVERSE_MODEL, references=_BOTH_PARENTS)
    link = fixture.node("InverseLink", LINK_ROW)
    with pytest.raises(ValueError, match="no already-recorded"):
        fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)


def test_an_inverse_is_refused_on_a_slot_holding_projections() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseLink.parent")
    fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    link = fixture.node("InverseLink", LINK_ROW)
    with pytest.raises(ValueError, match="holds fetched rows"):
        fixture.attach_reference(link, "InverseLink.parent", "InverseParent", _PARENT_KEY)


def test_to_one_selection_among_distinct_logical_targets_remains_unchanged() -> None:
    fixture = PageFixture(INVERSE_MODEL, "InverseLink.parent")
    link = fixture.node("InverseLink", LINK_ROW)
    first = fixture.node("InverseAlpha", _concrete(PARENT_ROWS[0]))
    other = fixture.node("InverseBeta", {**_concrete(PARENT_ROWS[1]), "id": 2})
    fixture.builder.write_to_one(link, fixture.view_key("InverseLink.parent"), (first, other))
    (root,) = fixture.observed_roots(link)
    assert root.names == ["InverseLink", "InverseAlpha"]


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


def _resolved_parents(fixture: PageFixture, *roots: int) -> list[object]:
    """Each root's link's resolved inverse, the link being its last node."""

    def resolved(root: RootView, _ordinal: int) -> object:
        link = len(root) - 1
        return root.view(link, root.view_layout(link).index_of[fixture.view_key(_TEMPORAL_PARENT)])

    return each_root(fixture.page(*roots, pin=_TEMPORAL_PIN), fixture.model, resolved)


def test_inverse_lookup_keeps_coordinate_distinct_claims_until_root_local_resolution() -> None:
    fixture, roots, _link = _coordinate_distinct_parents()
    page = fixture.page(*roots, pin=_TEMPORAL_PIN)
    assert page_rows(page).logical_rows[roots[0]] != page_rows(page).logical_rows[roots[1]]
    assert _resolved_parents(fixture, *roots) == [0, 0]


def test_every_coordinate_distinct_claim_of_one_key_resolves_its_own_inverse() -> None:
    fixture = _temporal_fixture()
    distinct = tuple(
        _temporal_parent(fixture, start) for start in (_FIRST_START, _SECOND_START, _THIRD_START)
    )
    repeated = _temporal_parent(fixture, _SECOND_START)
    roots = (*distinct, repeated)
    _reference(fixture, _temporal_link(fixture, *roots))
    page = fixture.page(*roots, pin=_TEMPORAL_PIN)
    logical_rows = page_rows(page).logical_rows
    assert len({logical_rows[parent] for parent in distinct}) == len(distinct)
    assert logical_rows[repeated] == logical_rows[distinct[1]]
    assert _resolved_parents(fixture, *roots) == [0] * len(roots)


def test_an_inverse_keeps_the_claims_its_key_held_when_it_was_written() -> None:
    fixture = _temporal_fixture()
    earlier = tuple(_temporal_parent(fixture, start) for start in (_FIRST_START, _SECOND_START))
    link = _temporal_link(fixture, *earlier)
    _reference(fixture, link)
    later = _temporal_parent(fixture, _THIRD_START)
    fixture.attach(later, "TemporalParent.links", (link,))
    assert _resolved_parents(fixture, *earlier, later) == [0, 0, None]


def test_an_inverse_to_coordinate_distinct_claims_this_root_never_reached_is_null() -> None:
    fixture, _parents, link = _coordinate_distinct_parents()
    (root,) = fixture.observed_roots(link, pin=_TEMPORAL_PIN)
    assert root.names[0] == "TemporalLink"
    assert root.view(0, root.view_layouts[0].index_of[fixture.view_key(_TEMPORAL_PARENT)]) is None
