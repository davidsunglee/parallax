"""The Snapshot Database doors over a prepared model (`execution.md`).

Preparation itself, and the Serving Model, are execution's
(``tests/unit/core/execution/test_publication.py``). What is graded here is what
the Snapshot doors add: a static model is prepared once per connection under an
edition of its own, a descriptor-backed model connects but refuses a Typed read
before any I/O, and nothing a request path reaches derives anything once the
model has been prepared.

Docker-free, against the shared recording port.
"""

from __future__ import annotations

from typing import Final

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core.entity import DomainModel
from parallax.core.entity import _graph_construction as graph_construction_module
from parallax.core.entity import _layout as layout_module
from parallax.core.entity import _row_codec as row_codec_module
from parallax.core.metamodel import UnresolvedEntityDeclaration
from parallax.snapshot import Database, SnapshotConnectionError, Transaction, connect
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write
from tests._support.root_ownership import own_root
from tests.unit._transact_support import FIXED, NEW_ROW, new_account

_ACCOUNT: Final = mm.ACCOUNT_MODEL


class _ClasslessSource:
    """A descriptor-frontend formation input composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (mm.Account,)


def _descriptor_backed() -> DomainModel:
    return DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam


def _refuse_every_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every per-Entity derivation fail from here on, so anything a request
    path still derives is a failure rather than a cost."""

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a per-Entity derivation ran after preparation")

    monkeypatch.setattr(layout_module.LayoutCatalog, "_build", refuse)
    monkeypatch.setattr(row_codec_module, "_row_facts", refuse)
    monkeypatch.setattr(graph_construction_module, "_entity_facts", refuse)


def test_nothing_fallible_remains_after_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    port = ScriptedAdapter(Read(rows=[NEW_ROW]), Transact(Write()))
    db = own_root(connect(port, _ACCOUNT, clock=FixedClock(FIXED))).using_database_login()
    _refuse_every_derivation(monkeypatch)

    assert db.find(mm.Account.where(mm.Account.id == 7)).result().owner == "Newton"

    def insert(tx: Transaction) -> None:
        tx.insert(new_account())

    db.transact(insert)


def test_a_descriptor_backed_connection_still_refuses_a_typed_read_before_io() -> None:
    db = own_root(
        Database.connect(ScriptedAdapter(), _descriptor_backed(), clock=FixedClock(FIXED))
    ).using_database_login()
    with pytest.raises(SnapshotConnectionError, match="snapshot-class-backed-model-required"):
        db.find(mm.Account.where(mm.Account.id == 7))


# --------------------------------------------------------------------------- #
# The static connection prepares once, under an edition of its own.            #
# --------------------------------------------------------------------------- #


def test_a_static_connection_prepares_once_under_a_generated_edition() -> None:
    first = own_root(
        connect(ScriptedAdapter(Transact(), Transact()), _ACCOUNT, clock=FixedClock(FIXED))
    ).using_database_login()
    second = own_root(
        connect(ScriptedAdapter(Transact()), _ACCOUNT, clock=FixedClock(FIXED))
    ).using_database_login()
    editions = {db.transact(lambda tx: tx.edition) for db in (first, second)}
    assert len(editions) == 2
    assert all(edition.startswith("static-") for edition in editions)
    # Fixed for the connection's life: a second invocation adopts the same one.
    assert first.transact(lambda tx: tx.edition) in editions
