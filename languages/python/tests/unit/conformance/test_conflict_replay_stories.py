"""The Usage Guide's conflict-replay story, over a fake port.

The story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_conflict_replay.py` executes it against real Postgres. This is
the database-free half — the same call over a scripted port, whose concurrent
writer commits inside the first attempt — so a snippet that stopped compiling,
or a conflict that stopped being replayed, fails on the first run of the fast
suite.
"""

from __future__ import annotations

from decimal import Decimal

from parallax.conformance import conflict_replay_stories
from parallax.conformance.class_models import MODELS
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)

_ROW = {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}
_PEERS = {**_ROW, "balance": Decimal("999.00"), "version": 2}


def test_the_documented_story_replays_the_overtaken_credit_from_a_fresh_read() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_ROW]), Transact(Read(rows=[_ROW]), Write()), Write(affected=0)),
        Transact(Read(rows=[_PEERS]), Write()),
        Read(rows=[{**_PEERS, "balance": Decimal("1024.00"), "version": 3}]),
    )
    report = (
        conflict_replay_stories.a_credit_overtaken_by_another_writer_is_replayed_from_a_fresh_read(
            port, MODELS["account"]
        )
    )
    assert report.balances_read == (Decimal("250.00"), Decimal("999.00"))
    assert report.balance == Decimal("1024.00")
    boundaries = [
        type(call) for call in port.calls if isinstance(call, BeginCall | CommitCall | RollbackCall)
    ]
    assert boundaries == [
        BeginCall,
        BeginCall,
        CommitCall,
        RollbackCall,
        BeginCall,
        CommitCall,
    ]
    peer, first, replayed = (call for call in port.calls if isinstance(call, WriteCall))
    assert first.binds == (Decimal("275.00"), 2, 2, 1)
    assert peer.binds == (Decimal("999.00"), 2, 2, 1)
    assert replayed.binds == (Decimal("1024.00"), 3, 2, 2)


def test_the_snippet_the_usage_guide_renders_is_the_source_that_ran() -> None:
    snippet = conflict_replay_stories.conflict_replay_snippet()
    assert "tx.find(query).result()" in snippet
    assert "db.transact(credit)" in snippet
    assert "retry_optimistic_conflicts" not in snippet
