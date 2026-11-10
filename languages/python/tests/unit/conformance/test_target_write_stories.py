"""The Usage Guide's target write stories, over a fake port.

Each story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_target_write_stories.py` executes it against real Postgres. This
is the database-free half — the same call over a scripted port — so a deletion
failure other than its precondition that started counting as a refusal fails on
the first run of the fast suite.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.target_write_stories import (
    reviewed_accounts_are_deleted_under_the_versions_their_review_saw,
)
from parallax.core.db_error import DatabaseError
from tests._support.db_port import (
    Read,
    ScriptedAdapter,
    Transact,
    Write,
)

_LINUS = {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}
_GRACE = {"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}


def test_a_deletion_failing_for_any_other_reason_is_never_counted_as_refused() -> None:
    lock_wait = DatabaseError(category="lockWaitTimeout", native_code="55P03", message="busy")
    port = ScriptedAdapter(
        Transact(Read(rows=[_LINUS, _GRACE])),
        Transact(Read(rows=[_LINUS]), Write()),
        Transact(Write(raises=lock_wait)),
    )
    with pytest.raises(DatabaseError) as failed:
        reviewed_accounts_are_deleted_under_the_versions_their_review_saw(port, MODELS["account"])
    assert failed.value is lock_wait
