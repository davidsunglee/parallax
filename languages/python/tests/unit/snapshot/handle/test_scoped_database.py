"""The Snapshot Database Root and ScopedDatabase facade boundaries.

What a root and its Execution Scopes share and derive is execution's
(``tests/unit/core/execution/test_scope.py``); what is graded here is the
facade: which object offers which verbs, that a ScopedDatabase is immutable and
built only by authority selection, and its positional-only arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.snapshot import Database, ScopedDatabase
from tests._support.db_port import ScriptedAdapter
from tests.unit._transact_support import ACCOUNT, FIXED


def test_root_and_scope_expose_disjoint_ownership_and_execution_surfaces() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    scoped = root.using_database_login()

    assert not hasattr(root, "find")
    assert not hasattr(root, "stream")
    assert not hasattr(root, "wire")
    assert not hasattr(root, "read_rows")
    assert not hasattr(root, "transact")
    assert not hasattr(scoped, "close")
    assert not hasattr(scoped, "__enter__")
    assert not hasattr(scoped, "using_principal")
    assert not hasattr(scoped, "using_database_login")
    # The facade composes its Execution Scope rather than inheriting it, so the
    # scope's internal read and delivery operations are no user method.
    for internal in ("read", "begin", "validated", "page"):
        assert not hasattr(scoped, internal)


def test_scopes_are_immutable_and_only_roots_can_construct_them() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    scoped = root.using_database_login()

    with pytest.raises(TypeError, match="authority selection"):
        ScopedDatabase()
    with pytest.raises(AttributeError, match="immutable"):
        scoped.extra = "changed"


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def test_required_scope_arguments_are_positional_only() -> None:
    root = Database.connect(ScriptedAdapter(), ACCOUNT, clock=FixedClock(FIXED))
    principal = _Principal("alice", "role-a")
    scoped = root.using_database_login()

    with pytest.raises(TypeError):
        cast("Any", root.using_principal)(principal=principal)

    def no_op(_tx: Any) -> None:
        return None

    with pytest.raises(TypeError):
        cast("Any", scoped.transact)(fn=no_op)
