"""The Snapshot Database doors over a prepared model (`execution.md`).

Preparation itself, and the Serving Model, are execution's
(``tests/unit/core/_execution/test_publication.py``). What is graded here is what
the Snapshot doors add: a static model is prepared once per connection under an
edition of its own, a descriptor-backed model connects but refuses a Typed read
before any I/O, and nothing a request path reaches derives anything once the
model has been prepared. Also the order each read verb judges what it is handed
in — lifecycle re-entry first, then the connection's capability, then the
query, with a stream judging its own arguments at the call and its model at
entry — and the edition a failed standalone delivery names.

Docker-free, against the shared recording port.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import UsageError
from parallax.core._execution import _planning as planning_module
from parallax.core._execution._unit_work import preparation as preparation_module
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.entity import _graph_construction as graph_construction_module
from parallax.core.entity import _layout as layout_module
from parallax.core.execution_lifecycle import (
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProvider,
    RootExecution,
)
from parallax.core.metamodel import UnresolvedEntityDeclaration
from parallax.snapshot import Database, ScopedDatabase, TxnContext, connect
from tests._support import mirrored_models as mm
from tests._support.db_port import Read, RefusingAdapter, ScriptedAdapter, Transact, Write
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root
from tests.unit._transact_support import FIXED, NEW_ROW, new_account

_ACCOUNT: Final = mm.ACCOUNT_MODEL


class _ClasslessSource:
    """A descriptor-frontend formation input composing no Entity Class."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (mm.Account, mm.Branch)


def _descriptor_backed() -> DomainModel:
    return DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam


def _refuse_every_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every per-Entity derivation fail from here on, so anything a request
    path still derives is a failure rather than a cost."""

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a per-Entity derivation ran after preparation")

    monkeypatch.setattr(layout_module.LayoutCatalog, "_build", refuse)
    monkeypatch.setattr(preparation_module, "_entity_preparation", refuse)
    monkeypatch.setattr(graph_construction_module, "_entity_facts", refuse)
    monkeypatch.setattr(planning_module, "_wire_entity_facts", refuse)


def test_nothing_fallible_remains_after_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    port = ScriptedAdapter(Read(rows=[NEW_ROW]), Transact(Write()))
    db = own_root(connect(port, _ACCOUNT, clock=FixedClock(FIXED))).using_database_login()
    _refuse_every_derivation(monkeypatch)

    assert db.find(mm.Account.where(mm.Account.id == 7)).result().owner == "Newton"

    def insert(tx: TxnContext) -> None:
        tx.insert(new_account())

    db.transact(insert)


def test_a_wire_read_and_a_typed_projection_derive_nothing_after_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = ScriptedAdapter(Read(rows=[NEW_ROW]), Read(rows=[NEW_ROW]))
    db = own_root(connect(port, _ACCOUNT, clock=FixedClock(FIXED))).using_database_login()
    _refuse_every_derivation(monkeypatch)
    query = mm.Account.where(mm.Account.id == 7)

    assert db.wire.find(query).result()["owner"] == "Newton"
    assert db.find(query).wire().result()["owner"] == "Newton"


def test_a_descriptor_backed_connection_still_refuses_a_typed_read_before_io() -> None:
    db = own_root(
        Database.connect(ScriptedAdapter(), _descriptor_backed(), clock=FixedClock(FIXED))
    ).using_database_login()
    with raises_code(
        UsageError,
        "snapshot-class-backed-model-required",
        match="snapshot-class-backed-model-required",
    ):
        db.find(mm.Account.where(mm.Account.id == 7))


def _classless(
    adapter: DatabaseAdapter[Any], *, lifecycle_provider: ExecutionLifecycleProvider | None = None
) -> ScopedDatabase:
    return own_root(
        Database.connect(
            adapter,
            _descriptor_backed(),
            clock=FixedClock(FIXED),
            lifecycle_provider=lifecycle_provider,
        )
    ).using_database_login()


def test_a_classless_connection_refuses_a_typed_read_before_it_reads_the_query() -> None:
    # The query omits the Valid-Time selection its Bitemporal target requires,
    # which reading it would refuse; the connection's capability is judged first.
    with raises_code(UsageError, "snapshot-class-backed-model-required"):
        _classless(RefusingAdapter()).find(mm.Branch.where(mm.Branch.id == 1))


def test_a_classless_typed_stream_is_refused_at_entry_and_opens_no_root() -> None:
    recorder = RecordingLifecycleProvider()
    stream = _classless(RefusingAdapter(), lifecycle_provider=recorder).stream(
        mm.Account.where(mm.Account.id == 7)
    )

    with raises_code(UsageError, "snapshot-class-backed-model-required"):
        stream.__enter__()
    assert recorder.roots == ()


class _ReenteringProvider:
    """Runs ``work`` from inside the opening of every root and records what each
    call answered."""

    def __init__(self) -> None:
        self.work: list[Callable[[], object]] = []
        self.answered: list[str] = []

    def open(self, execution: RootExecution, /) -> None:
        del execution
        for call in self.work:
            try:
                call()
            except Exception as refusal:
                self.answered.append(getattr(refusal, "code", type(refusal).__name__))
            else:
                self.answered.append("accepted")

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        del error


def test_a_call_from_a_lifecycle_context_is_refused_before_its_model_or_query_is_judged() -> None:
    # Each call would earn a refusal of its own outside the context: a Typed read
    # of a classless model, a Wire spelling no deserializer accepts, and a page
    # size no stream takes.
    provider = _ReenteringProvider()
    db = _classless(ScriptedAdapter(Read(rows=[NEW_ROW])), lifecycle_provider=provider)
    target = mm.Account.identity.canonical
    malformed: Any = {"target": target}
    provider.work = [
        lambda: db.find(mm.Account.where(mm.Account.id == 7)),
        lambda: db.wire.find(malformed),
        lambda: db.stream(mm.Account.where(mm.Account.id == 7), batch_size=0),
        lambda: db.wire.stream(malformed),
    ]

    db.wire.find({"target": target, "predicate": {"true": {}}}).result()

    assert provider.answered == ["lifecycle-reentered"] * 4


def test_a_standalone_stream_failure_names_the_edition_its_delivery_was_served_under() -> None:
    failure = DatabaseError(category=None, native_code=None, message="the later page failed")
    port = ScriptedAdapter(Read(rows=[NEW_ROW, {**NEW_ROW, "id": 8}]), Read(raises=failure))
    db = own_root(connect(port, _ACCOUNT, clock=FixedClock(FIXED))).using_database_login()

    with db.stream(mm.Account.where(mm.Account.id >= 7), batch_size=1) as stream:
        edition = stream.edition
        with pytest.raises(DatabaseError) as raised:
            list(stream)

    assert raised.value.__notes__ == [f"raised in a stream under model edition {edition!r}"]


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
