from __future__ import annotations

from typing import Any, cast

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.core.entity import model_of
from parallax.snapshot import ExecutionFailure, connect
from parallax.snapshot.materialize import SnapshotConsistencyError
from tests._support.db_port import Read, ScriptedAdapter
from tests._support.root_ownership import own_root
from tests._support.tpcs_inverse_models import (
    INVERSE_MODEL,
    LINK_ROW,
    PARENT_ROWS,
    InverseAlpha,
    InverseLink,
    InverseOwner,
    InverseParent,
)


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize("reverse", [False, True], ids=["alpha-first", "beta-first"])
@pytest.mark.parametrize("streamed", [False, True], ids=["eager", "streamed"])
def test_equal_key_roots_resolve_the_shared_child_inverse_locally(
    wire: bool, reverse: bool, streamed: bool
) -> None:
    rows = list(reversed(PARENT_ROWS)) if reverse else PARENT_ROWS
    port = ScriptedAdapter(Read(rows=rows), Read(rows=[LINK_ROW]))
    db = own_root(connect(port, INVERSE_MODEL)).using_database_login()
    query = InverseParent.where(InverseParent.all).include(InverseParent.links.parent)
    wire_query: dict[str, Any] = {
        "target": "InverseParent",
        "predicate": {"all": {}},
        "includes": [{"segments": [{"rel": "InverseParent.links"}, {"rel": "InverseLink.parent"}]}],
    }
    if streamed:
        query = query.order_by(InverseParent.label.desc() if reverse else InverseParent.label.asc())
        wire_query["orderBy"] = [
            {"attr": "InverseParent.label", "direction": "desc" if reverse else "asc"}
        ]
        with (
            db.wire.stream(wire_query, batch_size=3)
            if wire
            else db.stream(query, batch_size=3) as stream
        ):
            roots = list(stream)
    else:
        roots = db.wire.find(wire_query).results() if wire else db.find(query).results()
    assert len(roots) == 2
    for root, row in zip(cast("list[Any]", roots), rows, strict=True):
        if wire:
            assert root["familyVariant"] == row["family_variant"]
            assert root["links"][0]["parent"]["label"] == row["label"]
            assert "links" not in root["links"][0]["parent"]
        else:
            assert type(root).__name__ == row["family_variant"]
            assert root.links[0].parent is root
    assert len(port.calls) == 2


def test_narrowed_inverse_admits_only_its_selected_concrete() -> None:
    port = ScriptedAdapter(Read(rows=PARENT_ROWS), Read(rows=[LINK_ROW]))
    db = own_root(connect(port, INVERSE_MODEL)).using_database_login()
    roots = db.wire.find(
        {
            "target": "InverseParent",
            "predicate": {"all": {}},
            "includes": [
                {
                    "segments": [
                        {"rel": "InverseParent.links"},
                        {"rel": "InverseLink.parent", "narrowTo": ["InverseAlpha"]},
                    ]
                }
            ],
        }
    ).results()
    rendered = cast("list[dict[str, Any]]", roots)
    assert rendered[0]["links"][0]["parent[InverseAlpha]"]["label"] == "alpha"
    assert rendered[1]["links"][0]["parent[InverseAlpha]"] is None
    assert len(port.calls) == 2


def test_guarded_include_leaves_the_other_equal_key_root_unloaded() -> None:
    port = ScriptedAdapter(Read(rows=PARENT_ROWS), Read(rows=[LINK_ROW]))
    db = own_root(connect(port, INVERSE_MODEL)).using_database_login()
    alpha, beta = (
        db.find(InverseParent.where(InverseParent.all).include(InverseAlpha.links.parent))
        .wire()
        .results()
    )
    assert cast("dict[str, Any]", alpha)["links"][0]["parent"]["label"] == "alpha"
    assert "links" not in beta
    assert len(port.calls) == 2


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize("streamed", [False, True], ids=["eager", "streamed"])
@pytest.mark.parametrize("to_one", [False, True], ids=["to-many", "to-one"])
def test_public_broad_tpcs_children_report_same_root_witness_conflict(
    profile_run: Any, wire: bool, streamed: bool, to_one: bool
) -> None:
    profile_run.reset(
        model_of(INVERSE_MODEL),
        {
            "InverseOwner": [{"id": 10}],
            "InverseAlpha": [{"id": 1, "label": "alpha", "ownerId": 10}],
            "InverseBeta": [{"id": 1, "label": "beta", "ownerId": 10}],
            "InverseLink": [{"id": 11, "parentId": 1}],
        },
    )
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, INVERSE_MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()
    query = (
        InverseLink.where(InverseLink.all)
        .include(InverseLink.parent)
        .order_by(InverseLink.id.asc())
        if to_one
        else InverseOwner.where(InverseOwner.all)
        .include(InverseOwner.parents)
        .order_by(InverseOwner.id.asc())
    )
    target = "InverseLink" if to_one else "InverseOwner"
    wire_query: dict[str, Any] = {
        "target": target,
        "predicate": {"all": {}},
        "orderBy": [{"attr": f"{target}.id"}],
        "includes": [{"segments": [{"rel": f"{target}.{'parent' if to_one else 'parents'}"}]}],
    }
    with pytest.raises(ExecutionFailure) as failure:
        if streamed:
            with (
                db.wire.stream(wire_query, batch_size=3)
                if wire
                else db.stream(query, batch_size=3) as stream
            ):
                list(stream)
        elif wire:
            db.wire.find(wire_query).results()
        else:
            db.find(query).results()
    conflict = failure.value.__cause__
    assert isinstance(conflict, SnapshotConsistencyError)
    assert conflict.code == "snapshot-projection-conflict"
    assert conflict.coordinates == ()
    assert conflict.occurrences == ((1, 0), (1, 1))
    assert observation.round_trips == 2


@pytest.mark.parametrize("streamed", [False, True], ids=["eager", "streamed"])
def test_public_wire_deeper_inverse_reuses_each_broad_child_on_a_live_database(
    profile_run: Any, streamed: bool
) -> None:
    profile_run.reset(
        model_of(INVERSE_MODEL),
        {
            "InverseOwner": [{"id": 10}],
            "InverseAlpha": [{"id": 1, "label": "alpha", "ownerId": 10}],
            "InverseBeta": [{"id": 2, "label": "beta", "ownerId": 10}],
            "InverseLink": [{"id": 11, "parentId": 1}, {"id": 12, "parentId": 2}],
        },
    )
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, INVERSE_MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()
    query: dict[str, Any] = {
        "target": "InverseOwner",
        "predicate": {"all": {}},
        "orderBy": [{"attr": "InverseOwner.id"}],
        "includes": [
            {
                "segments": [
                    {"rel": "InverseOwner.parents"},
                    {"rel": "InverseParent.links"},
                    {"rel": "InverseLink.parent"},
                ]
            }
        ],
    }
    if streamed:
        with db.wire.stream(query, batch_size=3) as stream:
            roots = list(stream)
    else:
        roots = db.wire.find(query).results()
    (owner,) = roots
    parents = cast("list[dict[str, Any]]", owner["parents"])
    assert {(parent["id"], parent["familyVariant"]) for parent in parents} == {
        (1, "InverseAlpha"),
        (2, "InverseBeta"),
    }
    for parent in parents:
        (link,) = parent["links"]
        assert link["parent"]["id"] == parent["id"]
        assert link["parent"]["familyVariant"] == parent["familyVariant"]
        assert link["parent"]["label"] == parent["label"]
        assert "links" not in link["parent"]
    assert observation.round_trips == 3


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize("streamed", [False, True], ids=["eager", "streamed"])
def test_public_broad_to_one_child_reuses_the_root_link_as_its_inverse(
    profile_run: Any, wire: bool, streamed: bool
) -> None:
    profile_run.reset(
        model_of(INVERSE_MODEL),
        {
            "InverseAlpha": [{"id": 1, "label": "alpha", "ownerId": None}],
            "InverseLink": [{"id": 11, "parentId": 1}],
        },
    )
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, INVERSE_MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()
    query = (
        InverseLink.where(InverseLink.all)
        .include(InverseLink.parent.links)
        .order_by(InverseLink.id.asc())
    )
    if streamed:
        with (
            db.wire.stream(query, batch_size=3)
            if wire
            else db.stream(query, batch_size=3) as stream
        ):
            roots = list(stream)
    else:
        roots = db.wire.find(query).results() if wire else db.find(query).results()
    (link,) = cast("list[Any]", roots)
    if wire:
        assert link["parent"]["familyVariant"] == "InverseAlpha"
        assert link["parent"]["links"] == [{"id": 11, "parentId": 1}]
    else:
        assert isinstance(link.parent, InverseAlpha)
        assert link.parent.links == (link,)
        assert link.parent.links[0] is link
    assert observation.round_trips == 3
