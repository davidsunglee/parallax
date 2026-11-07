"""What a peer commit between two statements of one read does to a page-scope read.

Under Read Committed each statement has its own snapshot, so one logical row can
arrive with two observations. A Page holding them falls back, so every position
keeps what it observed, and a conflict within one root raises as it does at root
scope. Under Repeatable Read the statements agree and the Page shares.

The statements a peer falls between are one dependency wave apart, so the commit
lands between them however a wave pipelines.
"""

from __future__ import annotations

from typing import Any, Final, cast

import pytest

from parallax.core import MANY_TO_ONE, ONE_TO_MANY, Attr, DomainModel, Entity, Rel, attr, rel
from parallax.core.db_port import IsolationLevel
from parallax.core.entity import model_of
from parallax.snapshot import SharingScope, Snapshot, SnapshotConsistencyError, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root
from tests.api._statement_interleaving import AfterReadStatement


class Child(Entity, table="isolation_child"):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    value: Attr[str] = attr(max_length=8)


class Parent(Entity, table="isolation_parent"):
    id: Attr[int] = attr(primary_key=True)
    children: Rel[tuple[Child, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), order_by=("id",)
    )


class Hop(Entity, table="isolation_hop"):
    id: Attr[int] = attr(primary_key=True)
    child_id: Attr[int | None]
    parent_id: Attr[int | None]
    child: Rel[Child | None] = rel(cardinality=MANY_TO_ONE, join=("child_id", "id"))
    parent: Rel[Parent | None] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class Root(Entity, table="isolation_root"):
    id: Attr[int] = attr(primary_key=True)
    child_id: Attr[int | None]
    parent_id: Attr[int | None]
    hop_id: Attr[int | None]
    child: Rel[Child | None] = rel(cardinality=MANY_TO_ONE, join=("child_id", "id"))
    parent: Rel[Parent | None] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))
    hop: Rel[Hop | None] = rel(cardinality=MANY_TO_ONE, join=("hop_id", "id"))


_MODEL: Final = DomainModel(Child, Parent, Hop, Root)
_CHILD_TWICE: Final = (
    Root.where(Root.all).include(Root.child, Root.hop.child).order_by(Root.id.asc())
)
_CHILDREN_TWICE: Final = (
    Root.where(Root.all)
    .include(Root.parent.children, Root.hop.parent.children)
    .order_by(Root.id.asc())
)
_CHANGE_CHILD: Final = "update isolation_child set value = 'new' where id = 9"
_ADD_CHILD: Final = "insert into isolation_child (id, parent_id, value) values (10, 7, 'new')"


def _root(
    root_id: int, *, child: int | None = None, parent: int | None = None, hop: int | None = None
) -> dict[str, object]:
    return {"id": root_id, "childId": child, "parentId": parent, "hopId": hop}


_ONE_ROOT_PER_PATH: Final = (_root(1, child=9), _root(2, hop=5))
_A_ROOT_ON_BOTH_PATHS: Final = (_root(1, child=9, hop=5), _root(2, child=9))
_ONE_PARENT_ROOT_PER_PATH: Final = (_root(1, parent=7), _root(2, hop=5))


def _read(
    profile_run: Any,
    query: Any,
    roots: tuple[dict[str, object], ...],
    *,
    after_table: str,
    peer_sql: str,
    isolation: IsolationLevel,
    sharing_scope: SharingScope,
) -> Snapshot[Any]:
    """``query`` read at ``sharing_scope`` from a fresh seed, with ``peer_sql``
    committed right after the first read of ``after_table``."""
    profile_run.reset(
        model_of(_MODEL),
        {
            "Child": [{"id": 9, "parentId": 7, "value": "old"}],
            "Parent": [{"id": 7}],
            "Hop": [{"id": 5, "childId": 9, "parentId": 7}],
            "Root": list(roots),
        },
    )

    def commit() -> None:
        control = profile_run.control()
        try:
            control.execute_write(peer_sql, ())
        finally:
            control.close()

    interleaving = AfterReadStatement(lambda sql: after_table in sql, commit)
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=interleaving)
    ).using_database_login()
    snapshot = db.read_only(
        lambda tx: tx.find(query, sharing_scope=sharing_scope), isolation=isolation
    )
    assert interleaving.fired
    assert interleaving.failures == []
    return snapshot


def _children_seen(snapshot: Snapshot[Any]) -> list[str]:
    first, second = snapshot.results()
    return [first.child.value, second.hop.child.value]


def _wire_children_seen(snapshot: Snapshot[Any]) -> list[str]:
    first, second = cast("list[Any]", snapshot.wire().results())
    return [first["child"]["value"], second["hop"]["child"]["value"]]


def _child_nodes(snapshot: Snapshot[Any]) -> int:
    first, second = snapshot.results()
    return len({id(first), id(second), id(second.hop), id(first.child), id(second.hop.child)})


@pytest.mark.parametrize("sharing_scope", ["root", "page"])
def test_a_stored_difference_across_roots_is_preserved_at_read_committed(
    profile_run: Any, sharing_scope: SharingScope
) -> None:
    snapshot = _read(
        profile_run,
        _CHILD_TWICE,
        _ONE_ROOT_PER_PATH,
        after_table="isolation_hop",
        peer_sql=_CHANGE_CHILD,
        isolation="read_committed",
        sharing_scope=sharing_scope,
    )

    assert _children_seen(snapshot) == ["old", "new"]
    assert _wire_children_seen(snapshot) == ["old", "new"]


def test_a_repeatable_read_page_shares_past_a_peer_commit(profile_run: Any) -> None:
    def read(sharing_scope: SharingScope) -> Snapshot[Any]:
        return _read(
            profile_run,
            _CHILD_TWICE,
            _ONE_ROOT_PER_PATH,
            after_table="isolation_hop",
            peer_sql=_CHANGE_CHILD,
            isolation="repeatable_read",
            sharing_scope=sharing_scope,
        )

    at_page = read("page")

    assert _children_seen(at_page) == ["old", "old"]
    assert _wire_children_seen(at_page) == ["old", "old"]
    assert _child_nodes(at_page) == 4
    assert _child_nodes(read("root")) == 5


def test_a_conflict_within_one_root_raises_as_it_does_at_root_scope(profile_run: Any) -> None:
    def conflict(sharing_scope: SharingScope) -> SnapshotConsistencyError:
        with raises_contextualized(SnapshotConsistencyError) as raised:
            _read(
                profile_run,
                _CHILD_TWICE,
                _A_ROOT_ON_BOTH_PATHS,
                after_table="isolation_hop",
                peer_sql=_CHANGE_CHILD,
                isolation="read_committed",
                sharing_scope=sharing_scope,
            )
        return raised.value

    at_page = conflict("page")
    at_root = conflict("root")

    assert at_page.code == at_root.code == "snapshot-fetched-row-conflict"
    assert at_page.object_key == at_root.object_key
    assert at_page.members == at_root.members
    assert at_page.fetched_rows == at_root.fetched_rows


@pytest.mark.parametrize("sharing_scope", ["root", "page"])
def test_a_membership_difference_across_roots_is_preserved_at_read_committed(
    profile_run: Any, sharing_scope: SharingScope
) -> None:
    snapshot = _read(
        profile_run,
        _CHILDREN_TWICE,
        _ONE_PARENT_ROOT_PER_PATH,
        after_table="isolation_child",
        peer_sql=_ADD_CHILD,
        isolation="read_committed",
        sharing_scope=sharing_scope,
    )

    first, second = snapshot.results()
    assert [child.id for child in first.parent.children] == [9]
    assert [child.id for child in second.hop.parent.children] == [9, 10]
    wire_first, wire_second = cast("list[Any]", snapshot.wire().results())
    assert [child["id"] for child in wire_first["parent"]["children"]] == [9]
    assert [child["id"] for child in wire_second["hop"]["parent"]["children"]] == [9, 10]
