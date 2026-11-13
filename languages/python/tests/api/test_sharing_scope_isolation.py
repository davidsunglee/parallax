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
from parallax.core.internal.db_port import IsolationLevel
from parallax.core.internal.entity import model_of
from parallax.core.internal.read_delivery import InvalidDataError
from parallax.snapshot import (
    ScopedDatabase,
    SharingScope,
    Snapshot,
    connect,
)
from tests._support.bindings import TEST_BINDING
from tests._support.errors import raises_code
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
_CHANGE_CHILD: Final = "update px.isolation_child set value = 'new' where id = 9"
_ADD_CHILD: Final = "insert into px.isolation_child (id, parent_id, value) values (10, 7, 'new')"


def _root(
    root_id: int, *, child: int | None = None, parent: int | None = None, hop: int | None = None
) -> dict[str, object]:
    return {"id": root_id, "childId": child, "parentId": parent, "hopId": hop}


_ONE_ROOT_PER_PATH: Final = (_root(1, child=9), _root(2, hop=5))
_A_ROOT_ON_BOTH_PATHS: Final = (_root(1, child=9, hop=5), _root(2, child=9))
_ONE_PARENT_ROOT_PER_PATH: Final = (_root(1, parent=7), _root(2, hop=5))
_A_LATER_ROOT_ON_BOTH_PATHS: Final = (_root(1, child=9), _root(2, child=9, hop=5))


def _interleaved_database(
    profile_run: Any,
    roots: tuple[dict[str, object], ...],
    *,
    after_table: str,
    peer_sql: str,
) -> tuple[ScopedDatabase, AfterReadStatement]:
    """A fresh seed of ``roots``, with ``peer_sql`` committed right after the first
    read of ``after_table``."""
    profile_run.reset(
        model_of(_MODEL),
        {
            "Child": [{"id": 9, "parentId": 7, "value": "old"}],
            "Parent": [{"id": 7}],
            "Hop": [{"id": 5, "childId": 9, "parentId": 7}],
            "Root": list(roots),
        },
        TEST_BINDING,
    )

    def commit() -> None:
        control = profile_run.control()
        try:
            control.execute_write(peer_sql, ())
        finally:
            control.close()

    interleaving = AfterReadStatement(lambda sql: after_table in sql, commit)
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=interleaving, binding=TEST_BINDING)
    ).using_database_login()
    return db, interleaving


def _read(
    profile_run: Any,
    query: Any,
    roots: tuple[dict[str, object], ...],
    *,
    after_table: str,
    peer_sql: str,
    isolation: IsolationLevel,
    sharing_scope: SharingScope,
    wire: bool = False,
) -> Snapshot[Any]:
    """``query`` read at ``sharing_scope`` around a peer commit. ``wire`` reads it
    through direct Wire."""
    db, interleaving = _interleaved_database(
        profile_run, roots, after_table=after_table, peer_sql=peer_sql
    )
    snapshot = db.read_only(
        lambda tx: (tx.wire if wire else tx).find(query, sharing_scope=sharing_scope),
        isolation=isolation,
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


def _child_documents(snapshot: Snapshot[Any]) -> int:
    first, second = snapshot.results()
    return len(
        {id(first), id(second), id(second["hop"]), id(first["child"]), id(second["hop"]["child"])}
    )


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


@pytest.mark.parametrize("sharing_scope", ["root", "page"])
def test_direct_wire_preserves_a_stored_difference_across_roots_at_read_committed(
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
        wire=True,
    )

    first, second = snapshot.results()
    assert [first["child"]["value"], second["hop"]["child"]["value"]] == ["old", "new"]


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


def test_a_direct_wire_repeatable_read_page_shares_past_a_peer_commit(profile_run: Any) -> None:
    def read(sharing_scope: SharingScope) -> Snapshot[Any]:
        return _read(
            profile_run,
            _CHILD_TWICE,
            _ONE_ROOT_PER_PATH,
            after_table="isolation_hop",
            peer_sql=_CHANGE_CHILD,
            isolation="repeatable_read",
            sharing_scope=sharing_scope,
            wire=True,
        )

    assert _child_documents(read("page")) == 4
    assert _child_documents(read("root")) == 5


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
def test_a_conflict_within_one_root_raises_as_it_does_at_root_scope(
    profile_run: Any, wire: bool
) -> None:
    def conflict(sharing_scope: SharingScope) -> InvalidDataError:
        with raises_code(InvalidDataError, "snapshot-fetched-row-conflict") as raised:
            _read(
                profile_run,
                _CHILD_TWICE,
                _A_ROOT_ON_BOTH_PATHS,
                after_table="isolation_hop",
                peer_sql=_CHANGE_CHILD,
                isolation="read_committed",
                sharing_scope=sharing_scope,
                wire=wire,
            )
        return raised.value

    at_page = conflict("page")
    at_root = conflict("root")

    assert at_page.args == at_root.args


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


@pytest.mark.parametrize("sharing_scope", ["root", "page"])
def test_direct_wire_preserves_a_membership_difference_across_roots_at_read_committed(
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
        wire=True,
    )

    first, second = snapshot.results()
    assert [child["id"] for child in first["parent"]["children"]] == [9]
    assert [child["id"] for child in second["hop"]["parent"]["children"]] == [9, 10]


@pytest.mark.parametrize("read", ["typed", "wire", "projected"])
def test_a_stream_conflict_raises_at_the_same_root_with_the_same_prefix(
    profile_run: Any, read: str
) -> None:
    def delivered_before_the_conflict(
        sharing_scope: SharingScope,
    ) -> tuple[list[Any], InvalidDataError]:
        db, interleaving = _interleaved_database(
            profile_run,
            _A_LATER_ROOT_ON_BOTH_PATHS,
            after_table="isolation_hop",
            peer_sql=_CHANGE_CHILD,
        )
        delivered: list[Any] = []

        def drain(tx: Any) -> None:
            reader = tx.wire if read == "wire" else tx
            with reader.stream(_CHILD_TWICE, sharing_scope=sharing_scope) as stream:
                for root in stream:
                    delivered.append(stream.wire(root) if read == "projected" else root)

        with raises_code(InvalidDataError, "snapshot-fetched-row-conflict") as raised:
            db.read_only(drain, isolation="read_committed")
        assert interleaving.fired
        assert interleaving.failures == []
        return delivered, raised.value

    at_page, conflict_at_page = delivered_before_the_conflict("page")
    at_root, conflict_at_root = delivered_before_the_conflict("root")

    assert len(at_page) == len(at_root) == 1
    assert conflict_at_page.args == conflict_at_root.args
    if read == "typed":
        assert [root.id for root in at_page] == [root.id for root in at_root] == [1]
    else:
        assert [root["id"] for root in at_page] == [root["id"] for root in at_root] == [1]
